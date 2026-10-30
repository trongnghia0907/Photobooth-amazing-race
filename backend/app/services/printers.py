"""Printer contract. CUPS can implement this interface without changing the queue."""
from pathlib import Path
from typing import Protocol
from PIL import Image, ImageWin


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

    def list_printers(self):
        try:
            import win32print
            return [{'id': p[2], 'name': p[2], 'status': 'driver_available'} for p in
                    win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
        except Exception:
            # pywintypes.error is not an OSError. A stopped spooler must make
            # printing unavailable rather than crash /print-config or /admin.
            return []

    def print_image(self, file_path, copies, options):
        if not self.enabled:
            raise PrinterError('In thật chưa được bật trên host.')
        printer = options['printer_id']
        if printer not in [p['id'] for p in self.list_printers()]:
            raise PrinterError('Máy in đã chọn không còn khả dụng.')
        dc, started = None, False
        try:
            import win32ui
            dc = win32ui.CreateDC()
            dc.CreatePrinterDC(printer)
            spool_id = dc.StartDoc('OSA ' + options['job_id'])
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
