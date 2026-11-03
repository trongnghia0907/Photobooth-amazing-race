"""Cross-process OS lease: released automatically when a process exits."""
import os


class RuntimeLock:
    def __init__(self,path):self.path,self.stream=path,None

    def acquire(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        stream=open(self.path,'a+b')
        try:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                if not stream.read(1):stream.write(b'0');stream.flush()
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            stream.close();raise RuntimeError(f'Another process already owns this runtime service: {self.path.name}') from None
        self.stream=stream
        return self

    def close(self):
        if self.stream:self.stream.close();self.stream=None
