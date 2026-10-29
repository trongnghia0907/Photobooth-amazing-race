"""Dry-run adapter for CI; no queue, OS driver, spooler or physical printing."""
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
