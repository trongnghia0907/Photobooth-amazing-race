"""Dry-run printer used by the durable queue; never sends data to an OS printer."""
from pathlib import Path
import hashlib
from .images import atomic_write


class MockPrinterAdapter:
    def __init__(self, output: Path):
        self.output = output

    def preview(self, image: Path, job_id: str):
        # Accept a generated hex identifier, never a customer-supplied path.
        if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
            raise ValueError('Invalid dry-run job id')
        data = image.read_bytes()
        destination = self.output / f'{job_id}.png'
        atomic_write(destination, data)
        return {'mode': 'mock', 'printed': False, 'sha256': hashlib.sha256(data).hexdigest()}

    def list_printers(self):
        return [{'id':'mock', 'name':'Mock Printer (không in giấy)', 'status':'ready'}]

    def print_image(self, file_path, copies, options):
        receipt = self.preview(file_path, options['job_id'].replace('-', ''))
        return {**receipt, 'copies':copies, 'physical_print_confirmed':False}

    def get_job_status(self, job_id):
        return {'status':'simulated', 'physical_print_confirmed':False}
