"""Printer contract. CUPS can implement this interface without changing the queue."""
from pathlib import Path
from typing import Protocol
import sys
from PIL import Image


class PrinterAdapter(Protocol):
    def list_printers(self) -> list[dict]: ...
    def print_image(self, file_path: Path, copies: int, options: dict) -> dict: ...
    def get_job_status(self, job_id: str) -> dict: ...


class PrinterError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class WindowsPrinterAdapter:
    """Render PNG through a GDI printer DC; never send PNG bytes as RAW data."""
    def __init__(self, enabled=False):
        self.enabled = enabled

    def diagnostic(self):
        if sys.platform!='win32':return 'Chế độ máy in Windows cần chạy Host trên Windows.'
        try:import win32print, win32ui
        except ImportError:return 'Thiếu pywin32. Cài lại dependencies của backend và driver máy in.'
        return ''

    def default_printer(self):
        try:
            import win32print
            return win32print.GetDefaultPrinter() or ''
        except Exception:
            return ''

    def list_printers(self):
        try:
            import win32print
            # Local queues include USB drivers. Do not open remote print servers
            # every time the dashboard refreshes.
            queues = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL, None, 2)
        except Exception:
            # pywintypes.error is not an OSError. A stopped spooler must make
            # printing unavailable rather than crash /print-config or /admin.
            return []
        devices = []
        for queue in queues:
            name = queue['pPrinterName']
            driver = (queue.get('pDriverName') or '').casefold()
            ports = {port.strip().casefold() for port in (queue.get('pPortName') or '').split(',')}
            attributes, status = queue['Attributes'], queue['Status']
            if (ports & {'portprompt:', 'file:', 'nul:'}
                    or any(port.startswith('microsoft.office.onenotevirtualprinter') for port in ports)
                    or any(virtual in driver for virtual in ('onenote', 'print to pdf', 'xps document', 'pdfcreator', 'adobe pdf'))
                    or attributes & win32print.PRINTER_ATTRIBUTE_FAX):
                continue
            if status & win32print.PRINTER_STATUS_OFFLINE or attributes & win32print.PRINTER_ATTRIBUTE_WORK_OFFLINE:
                state = 'offline'
            elif status & (win32print.PRINTER_STATUS_ERROR | win32print.PRINTER_STATUS_PAUSED |
                           win32print.PRINTER_STATUS_NOT_AVAILABLE | win32print.PRINTER_STATUS_PAPER_OUT |
                           win32print.PRINTER_STATUS_PAPER_JAM | win32print.PRINTER_STATUS_USER_INTERVENTION |
                           win32print.PRINTER_STATUS_NO_TONER | win32print.PRINTER_STATUS_DOOR_OPEN):
                state = 'blocked'
            else:
                state = 'driver_available'
            devices.append({'id': name, 'name': name, 'status': state})
        return devices

    def print_image(self, file_path, copies, options):
        if not self.enabled:
            raise PrinterError('In thật chưa được bật trên host.')
        printer = options['printer_id']
        device = next((p for p in self.list_printers() if p['id'] == printer), None)
        if device is None:
            raise PrinterError('Máy in không còn khả dụng. Kiểm tra cáp, driver và Windows Print Spooler.')
        if device['status'] == 'offline':
            raise PrinterError('Máy in đang ngoại tuyến. Kiểm tra nguồn và cáp trước khi in lại.')
        if device['status'] == 'blocked':
            raise PrinterError('Windows báo máy in lỗi hoặc tạm dừng. Kiểm tra giấy, mực và hàng đợi in.')
        dc, started = None, False
        try:
            import win32ui
            from PIL import ImageWin
            dc = win32ui.CreateDC()
            dc.CreatePrinterDC(printer)
            spool_id = dc.StartDoc('AMAZING RACE 2026 ' + options['job_id'])
            started = True
            width, height = dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)  # HORZRES / VERTRES
            with Image.open(file_path) as image:
                dib = ImageWin.Dib(image.convert('RGB'))
                scale = min(width / image.width, height / image.height)
                w, h = round(image.width * scale), round(image.height * scale)
                x, y = (width-w)//2, (height-h)//2
                for _ in range(copies):
                    dc.StartPage()
                    dib.draw(dc.GetHandleOutput(), (x,y,x+w,y+h))
                    dc.EndPage()
            dc.EndDoc()
            return {'mode':'windows','spooler_job_id':spool_id,'copies':copies,'physical_print_confirmed':False}
        except Exception as error:
            if dc and started:
                try:
                    dc.AbortDoc()
                except Exception:
                    pass
            raise PrinterError('Windows driver không nhận trọn job. Host cần kiểm tra spooler trước khi in lại.', started) from error
        finally:
            if dc:
                dc.DeleteDC()

    def get_job_status(self, job_id):
        return {'status':'unknown', 'physical_print_confirmed':False}
