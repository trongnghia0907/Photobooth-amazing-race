"""SQLite FIFO with a single cross-process worker lease. Never auto-retry a job."""
import hashlib
import json
import os
import threading
import uuid
from fastapi import HTTPException
from .mock_printer import MockPrinterAdapter
from .printers import WindowsPrinterAdapter, PrinterError
from .cups_printer import CupsPrinterAdapter
from .repository import now, canonical, digest


class PrintingService:
    def __init__(self, repository, adapter=None):
        self.repo, self.settings = repository, repository.settings
        self.adapter = adapter or (MockPrinterAdapter(self.settings.storage_root/'mock_prints')
                                  if self.settings.printer_mode == 'mock' else
                                  WindowsPrinterAdapter(self.settings.enable_physical_printing)
                                  if self.settings.printer_mode == 'windows' else
                                  CupsPrinterAdapter(self.settings.enable_physical_printing,self.settings.cups_lp,self.settings.cups_lpstat))
        self.stop_event = threading.Event()
        self.thread = None

    def printers(self):
        return self.adapter.list_printers() if self.adapter else []

    def selected(self, db):
        row = db.execute('SELECT value FROM host_settings WHERE key=?', ('printer:'+self.settings.printer_mode,)).fetchone()
        if row:
            return row[0]
        if self.settings.printer_mode == 'mock':
            return 'mock'
        if self.settings.printer_name:
            return self.settings.printer_name
        if self.settings.printer_mode == 'windows':
            return self.adapter.default_printer()
        return ''

    def inventory(self):
        with self.repo.db.connect() as db:
            selected = self.selected(db)
        devices = self.printers()
        return {'items':devices,'selected':selected,**self.config(selected, devices)}

    def config(self, selected=None, devices=None):
        if selected is None:
            with self.repo.db.connect() as db:
                selected = self.selected(db)
        if devices is None:
            devices = self.printers()
        mode = self.settings.printer_mode
        enabled = (self.settings.printer_mode == 'mock' and self.settings.demo_hardware_allowed) or (self.settings.printer_mode != 'mock' and self.settings.enable_physical_printing)
        diagnostic = getattr(self.adapter,'diagnostic',lambda:'')()
        device = next((p for p in devices if p['id']==selected), None)
        state = device['status'] if device else 'unavailable'
        if diagnostic:
            message = diagnostic
        elif mode == 'mock':
            message = 'Mock Printer: không in giấy.' if enabled else 'Chế độ Event không cho phép MockPrinter.'
        elif not enabled:
            message = 'Chưa bật in thật trên Host.'
        elif not devices:
            message = 'Không tìm thấy máy in khả dụng. Kiểm tra cáp, driver và dịch vụ in của hệ điều hành.'
        elif not device:
            message = 'Máy in đã chọn hoặc mặc định không khả dụng. Hãy chọn máy in trong Dashboard.'
        elif state == 'offline':
            message = 'Máy in đang ngoại tuyến. Kiểm tra nguồn và cáp.'
        elif state == 'blocked':
            message = 'Windows báo máy in lỗi hoặc tạm dừng. Kiểm tra giấy, mực và hàng đợi in.'
        else:
            message = 'Máy in sẵn sàng nhận lệnh theo trạng thái hệ điều hành.'
        return {'mode':mode,'max_copies':self.settings.max_print_copies,'device_status':state,
                'available':enabled and not diagnostic and device is not None and state not in ('offline','blocked'),
                'message':message}

    @staticmethod
    def metadata(row):
        result = {k:row[k] for k in ('id','session_id','final_id','copies','status','mode','printer_id','retry_of','error_message','created_at','updated_at')}
        result.update(uncertain=bool(row['uncertain']),physical_print_confirmed=False)
        if row['receipt_json']:
            result['receipt'] = json.loads(row['receipt_json'])
        return result

    def checked_file(self, relative, expected_hash):
        root = self.settings.storage_root.resolve()
        path = (root/relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise HTTPException(409, 'File print-ready bị mất/thay đổi; cần khôi phục storage. Không in.')
        return path

    def enqueue(self, sid, final_id, copies, key, owner=None, retry_of=None, acknowledge=False):
        if type(copies) is not int or not 1 <= copies <= self.settings.max_print_copies:
            raise HTTPException(422, f'Số bản in phải từ 1 đến {self.settings.max_print_copies}')
        scope = 'owner:'+sid if owner is not None else 'host'
        fingerprint = digest(canonical({'session':sid,'final':final_id,'copies':copies,'retry':retry_of}))
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if owner is not None:
                self.repo.authorize(db, sid, owner)
            existing = db.execute('SELECT * FROM print_jobs WHERE scope=? AND request_key=?', (scope,key)).fetchone()
            if existing:
                if existing['payload_hash'] != fingerprint:
                    raise HTTPException(409, 'Idempotency-Key đã dùng cho yêu cầu khác')
                return self.metadata(existing)
            ready = db.execute('SELECT p.* FROM print_ready p JOIN shares s ON s.id=p.final_id WHERE s.id=? AND s.session_id=? AND s.revoked_at IS NULL AND (s.expires_at IS NULL OR s.expires_at>?)', (final_id,sid,now())).fetchone()
            if not ready:
                share=db.execute('SELECT 1 FROM shares WHERE id=? AND session_id=? AND revoked_at IS NULL',(final_id,sid)).fetchone()
                if share and not self.repo.print_ready.url(db,final_id):raise HTTPException(503,'Chờ URL HTTPS công khai hoạt động để tạo bản in có QR. Không in QR localhost.')
                raise HTTPException(409, 'Cần xác nhận ảnh, tạo QR và lưu print-ready trước khi in.')
            ready=self.repo.print_ready.ensure(db,final_id,[])
            if not ready:raise HTTPException(503,'Chờ URL HTTPS công khai hoạt động để tạo bản in có QR. Không in QR localhost.')
            self.checked_file(ready['path'], ready['sha256'])
            if retry_of:
                previous = db.execute('SELECT * FROM print_jobs WHERE id=?', (retry_of,)).fetchone()
                if not previous or previous['status'] != 'failed' or previous['final_id'] != final_id:
                    raise HTTPException(409, 'Chỉ retry job thất bại')
                if previous['uncertain'] and not acknowledge:
                    raise HTTPException(409, 'Chưa rõ job đã in hay chưa. Kiểm tra spooler/giấy và xác nhận trước khi retry.')
            selected = self.selected(db)
            printer = self.config(selected)
            if not printer['available']:
                raise HTTPException(503, printer['message'])
            job_id, stamp = str(uuid.uuid4()), now()
            db.execute('''INSERT INTO print_jobs
                (id,session_id,final_id,print_ready_file,sha256,copies,status,mode,printer_id,scope,request_key,payload_hash,retry_of,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'queued',?,?,?,?,?,?,?,?)''',
                (job_id,sid,final_id,ready['path'],ready['sha256'],copies,self.settings.printer_mode,selected,scope,key,fingerprint,retry_of,stamp,stamp))
            result = self.metadata(db.execute('SELECT * FROM print_jobs WHERE id=?', (job_id,)).fetchone())
            db.commit()
            return result

    def get(self, job_id, sid=None, owner=None):
        with self.repo.db.connect() as db:
            if owner is not None:
                self.repo.authorize(db, sid, owner)
            row = db.execute('SELECT * FROM print_jobs WHERE id=?', (job_id,)).fetchone()
            if not row or (sid and row['session_id'] != sid):
                raise HTTPException(404, 'Không tìm thấy print job')
            return self.metadata(row)

    def process_one(self):
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM print_jobs WHERE status='processing'").fetchone():
                return False
            row = db.execute("SELECT * FROM print_jobs WHERE status='queued' ORDER BY seq LIMIT 1").fetchone()
            if not row:
                return False
            db.execute("UPDATE print_jobs SET status='processing',updated_at=? WHERE id=?", (now(),row['id']))
            db.commit()
        receipt, error, uncertain, status = None, None, False, 'submitted'
        try:
            if row['mode']=='mock' and not self.settings.demo_hardware_allowed:
                raise PrinterError('Event mode blocks MockPrinter; Host must explicitly select a physical printer.')
            if row['mode'] != self.settings.printer_mode or not self.adapter:
                raise PrinterError('Printer mode đã thay đổi. Host cần kiểm tra rồi retry rõ ràng.')
            with self.repo.db.connect() as db:
                active = db.execute('SELECT 1 FROM shares WHERE id=? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)', (row['final_id'],now())).fetchone()
            if not active:
                raise PrinterError('QR đã hết hạn/bị thu hồi khi job đang chờ. Không gửi in.')
            path = self.checked_file(row['print_ready_file'],row['sha256'])
            receipt = self.adapter.print_image(path,row['copies'],{'job_id':row['id'],'printer_id':row['printer_id']})
        except Exception as exc:
            status = 'failed'
            uncertain = getattr(exc,'uncertain',not isinstance(exc,(HTTPException,PrinterError)))
            error = str(exc.detail) if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,PrinterError) else 'Adapter lỗi; kiểm tra spooler trước khi in lại.'
        with self.repo.db.connect() as db:
            db.execute('UPDATE print_jobs SET status=?,receipt_json=?,error_message=?,uncertain=?,updated_at=? WHERE id=?',
                       (status,canonical(receipt) if receipt else None,error,int(uncertain),now(),row['id']))
        return True

    def _run(self):
        # OS lock is released on process death; another worker then marks an
        # interrupted processing job ambiguous rather than silently printing twice.
        lock = open(self.settings.storage_root/'.print-worker.lock','a+b')
        acquired = False
        try:
            while not self.stop_event.is_set() and not acquired:
                try:
                    lock.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        if lock.read(1) == b'':
                            lock.write(b'0'); lock.flush()
                        lock.seek(0); msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    self.stop_event.wait(.5)
            if not acquired:
                return
            with self.repo.db.connect() as db:
                db.execute("UPDATE print_jobs SET status='failed',uncertain=1,error_message=?,updated_at=? WHERE status='processing'",
                           ('Backend bị ngắt khi đang gửi in. Kiểm tra spooler trước khi retry.',now()))
            while not self.stop_event.is_set():
                try:
                    if not self.process_one():
                        self.stop_event.wait(.3)
                except Exception:
                    # Keep persisted state, avoid retrying a possibly dispatched job.
                    self.stop_event.wait(1)
        finally:
            lock.close()

    def start(self):
        self.thread = threading.Thread(target=self._run,daemon=True,name='amazing-race-print-worker')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(5)
