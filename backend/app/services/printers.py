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


def printable_box(width, height, dpi_x, dpi_y, image_width, image_height):
    scale = min(width / (image_width * dpi_x), height / (image_height * dpi_y))
    w, h = max(1, round(image_width * dpi_x * scale)), max(1, round(image_height * dpi_y * scale))
    x, y = (width - w) // 2, (height - h) // 2
    return x, y, x + w, y + h


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

    def capabilities(self, printer):
        import win32con as con
        import win32print

        handle = win32print.OpenPrinter(printer)
        try:
            port = win32print.GetPrinter(handle, 2)['pPortName'].split(',')[0].strip()
        finally:
            win32print.ClosePrinter(handle)
        ids = win32print.DeviceCapabilities(printer, port, con.DC_PAPERS)
        names = win32print.DeviceCapabilities(printer, port, con.DC_PAPERNAMES)
        sizes = win32print.DeviceCapabilities(printer, port, con.DC_PAPERSIZE)
        papers = []
        if isinstance(ids,tuple) and isinstance(names,tuple) and isinstance(sizes,tuple):
            papers = [{'id': ident, 'name': name, 'width_mm': size['x']/10, 'height_mm': size['y']/10}
                      for ident, name, size in zip(ids, names, sizes) if ident > 0 and size['x'] > 0 and size['y'] > 0]
        orientations = ['portrait', 'landscape'] if win32print.DeviceCapabilities(printer, port, con.DC_ORIENTATION) in (90, 270) else []
        return {'papers': papers, 'orientations': orientations}

    def create_dc(self, printer, paper_id=None, orientation=None):
        import win32ui

        if paper_id is None and orientation is None:
            dc = win32ui.CreateDC()
            dc.CreatePrinterDC(printer)
            return dc
        import win32con as con
        import win32gui
        import win32print

        handle = win32print.OpenPrinter(printer)
        try:
            requested = win32print.GetPrinter(handle, 2)['pDevMode']
            accepted = win32print.GetPrinter(handle, 2)['pDevMode']
            if paper_id is not None:
                requested.Fields &= ~(con.DM_PAPERLENGTH | con.DM_PAPERWIDTH | con.DM_FORMNAME)
                requested.Fields |= con.DM_PAPERSIZE
                requested.PaperSize = paper_id
            if orientation:
                requested.Fields |= con.DM_ORIENTATION
                requested.Orientation = con.DMORIENT_PORTRAIT if orientation == 'portrait' else con.DMORIENT_LANDSCAPE
            result = win32print.DocumentProperties(0, handle, printer, accepted, requested, con.DM_IN_BUFFER | con.DM_OUT_BUFFER)
            if (result != con.IDOK or (paper_id is not None and accepted.PaperSize != paper_id)
                    or (orientation and accepted.Orientation != requested.Orientation)):
                raise PrinterError('Driver từ chối khổ giấy hoặc hướng in đã chọn.')
            dc_handle = win32gui.CreateDC('WINSPOOL', printer, accepted)
            try:
                return win32ui.CreateDCFromHandle(dc_handle)
            except Exception:
                win32gui.DeleteDC(dc_handle)
                raise
        finally:
            win32print.ClosePrinter(handle)

    @staticmethod
    def page_metrics(dc):
        return tuple(dc.GetDeviceCaps(cap) for cap in (8, 10, 88, 90, 110, 111, 112, 113))

    def preview(self, printer, paper_id, orientation):
        dc = self.create_dc(printer, paper_id, orientation)
        try:
            w, h, dx, dy, full_w, full_h, x, y = self.page_metrics(dc)
            if min(w, h, dx, dy, full_w, full_h) <= 0:
                raise PrinterError('Driver không trả về khổ giấy hợp lệ.')
            return {'ratio': (full_w/dx)/(full_h/dy), 'left': x/full_w, 'top': y/full_h,
                    'width': w/full_w, 'height': h/full_h}
        finally:
            dc.DeleteDC()

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
            from PIL import ImageWin
            dc = self.create_dc(printer, options.get('paper_id'), options.get('orientation'))
            width, height, dpi_x, dpi_y, *_ = self.page_metrics(dc)
            if min(width, height, dpi_x, dpi_y) <= 0:
                raise PrinterError('Driver không trả về vùng in hợp lệ.')
            with Image.open(file_path) as image:
                dib = ImageWin.Dib(image.convert('RGB'))
                box = printable_box(width, height, dpi_x, dpi_y, image.width, image.height)
                spool_id = dc.StartDoc('AMAZING RACE 2026 ' + options['job_id'])
                started = True
                for _ in range(copies):
                    dc.StartPage()
                    dib.draw(dc.GetHandleOutput(), box)
                    dc.EndPage()
            dc.EndDoc()
            return {'mode':'windows','spooler_job_id':spool_id,'copies':copies,'physical_print_confirmed':False}
        except Exception as error:
            if isinstance(error, PrinterError) and not started:
                raise
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
