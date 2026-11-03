"""Keep Windows venv wrappers and their children in one owned lifetime.

Closing the job (including launcher crashes) releases orphaned runtime locks.
No PID enumeration or termination of pre-existing processes is performed.
"""
import os
import uuid


class OwnedProcesses:
    def __init__(self):
        self.handle=None;self.name=''
        if os.name!='nt':return
        import ctypes
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),
                      ('flags',w.DWORD),('min_working',ctypes.c_size_t),('max_working',ctypes.c_size_t),
                      ('active_limit',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_uint64) for name in ('reads','writes','other','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                      ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];api.CreateJobObjectW.restype=w.HANDLE
        api.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
        api.CloseHandle.argtypes=[w.HANDLE]
        self.name='Photobooth-'+uuid.uuid4().hex
        self.api=api;self.handle=api.CreateJobObjectW(None,self.name)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limits=Extended();limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            error=ctypes.WinError(ctypes.get_last_error());self.close();raise error

    def add(self,process):
        if self.handle:
            import ctypes
            if not self.api.AssignProcessToJobObject(self.handle,int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:self.api.CloseHandle(self.handle);self.handle=None


def join_owned_job():
    """Join in the real interpreter too, closing the venv-wrapper spawn race."""
    name=os.environ.get('PHOTOBOOTH_OWNED_JOB','')
    if os.name!='nt' or not name:return
    import ctypes
    from ctypes import wintypes as w
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenJobObjectW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR];api.OpenJobObjectW.restype=w.HANDLE
    api.GetCurrentProcess.restype=w.HANDLE
    api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    api.IsProcessInJob.argtypes=[w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)]
    api.CloseHandle.argtypes=[w.HANDLE]
    handle=api.OpenJobObjectW(0x1|0x4,False,name)  # ASSIGN_PROCESS | QUERY
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        member=w.BOOL();process=api.GetCurrentProcess()
        if not api.IsProcessInJob(process,handle,ctypes.byref(member)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not member.value and not api.AssignProcessToJobObject(handle,process):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:api.CloseHandle(handle)
