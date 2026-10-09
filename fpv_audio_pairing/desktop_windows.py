"""Keep Windows media children owned by the desktop backend's lifetime."""
from __future__ import annotations

import ctypes
import os


# Windows uses 32-bit DWORDs even in a 64-bit process. SIZE_T and ULONG_PTR
# follow the pointer width; ctypes applies the platform's native alignment.
class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_JOB_HANDLE = None


def _last_error(operation):
    return ctypes.WinError(ctypes.get_last_error(),
                           f"Windows desktop child cleanup: {operation} failed")


def enable_child_cleanup():
    """Assign this backend to a job whose final handle dies with the process.

    Child processes automatically join the job, including children created by
    FFmpeg. Supported Windows versions allow nesting under a launcher's job.
    Fail startup if ownership cannot be established rather than allow orphans.
    """
    global _JOB_HANDLE
    if os.name != "nt" or _JOB_HANDLE is not None:
        return

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int32,
                                               ctypes.c_void_p, ctypes.c_uint32]
    kernel.SetInformationJobObject.restype = ctypes.c_int32
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.AssignProcessToJobObject.restype = ctypes.c_int32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int32

    # NULL security attributes make this handle non-inheritable. Children must
    # join the job without owning a handle that could keep it alive themselves.
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise _last_error("CreateJobObjectW")
    try:
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise _last_error("SetInformationJobObject")
        if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
            raise _last_error("AssignProcessToJobObject")
    except BaseException:
        kernel.CloseHandle(handle)
        raise

    # Keep the raw handle until Windows closes it during process teardown,
    # including TerminateProcess/crashes. Explicitly closing it here or in an
    # atexit handler would also terminate this backend, which belongs to the job.
    _JOB_HANDLE = handle
