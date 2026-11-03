"""Optional CUPS adapter. Queue acceptance never confirms physical output."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from .printers import PrinterError


class CupsPrinterAdapter:
    def __init__(self, enabled=False, lp='lp', lpstat='lpstat'):
        self.enabled,self.lp,self.lpstat=enabled,lp,lpstat

    def diagnostic(self):
        if sys.platform not in ('darwin','linux'):
            return 'CUPS requires macOS/Linux; use Windows Print Spooler on Windows.'
        if not shutil.which(self.lp) or not shutil.which(self.lpstat):
            return 'CUPS lp/lpstat unavailable. Install CUPS or configure CUPS_LP_COMMAND/CUPS_LPSTAT_COMMAND.'
        return ''

    def _run(self, command, *args):
        return subprocess.run([shutil.which(command) or command,*args],check=True,capture_output=True,
                              text=True,timeout=5,env={**os.environ,'LC_ALL':'C','LANG':'C'})

    def list_printers(self):
        if self.diagnostic():return []
        try:
            devices=self._run(self.lpstat,'-p').stdout
            accepting={line.split()[0] for line in self._run(self.lpstat,'-a').stdout.splitlines()
                       if ' accepting requests' in line}
            return [{'id':name,'name':name,'status':'driver_available'}
                    for name in re.findall(r'^printer (\S+) is (?:idle|printing)\b',devices,re.M)
                    if name in accepting and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',name)]
        except (OSError,subprocess.SubprocessError):return []

    def print_image(self, file_path:Path, copies:int, options:dict):
        if not self.enabled:raise PrinterError('Physical printing is not enabled on this host.')
        if self.diagnostic():raise PrinterError(self.diagnostic())
        printer=options['printer_id']
        if printer not in [p['id'] for p in self.list_printers()]:
            raise PrinterError('Selected CUPS printer is unavailable, disabled or not accepting jobs.')
        if type(copies) is not int or not 1<=copies<=100:raise PrinterError('Invalid copy count.')
        try:
            result=self._run(self.lp,'-d',printer,'-n',str(copies),'-t','AMAZING RACE 2026 '+options['job_id'],
                             '-o','fit-to-page','--',str(Path(file_path).resolve()))
        except OSError as error:raise PrinterError('CUPS executable could not be started.') from error
        except subprocess.SubprocessError as error:
            raise PrinterError('CUPS submission interrupted. Check the queue/paper before retrying.',True) from error
        receipt=re.search(r'request id is ([A-Za-z0-9_.-]+-\d+)',result.stdout)
        if not receipt:raise PrinterError('CUPS returned no recognizable receipt. Check the queue before retrying.',True)
        return {'mode':'cups','spooler_job_id':receipt[1],'copies':copies,'physical_print_confirmed':False}

    def get_job_status(self, job_id):
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*-\d+',str(job_id)):
            return {'status':'unknown','physical_print_confirmed':False}
        try:
            output=self._run(self.lpstat,'-W','all','-o',str(job_id)).stdout
            status='spooler_known' if output.strip() else 'unknown'
        except (OSError,subprocess.SubprocessError):status='unknown'
        return {'status':status,'physical_print_confirmed':False}
