"""Une seule copie de RazerLite à la fois (sinon deux icônes, et deux programmes qui parlent aux appareils)."""

import sys
import time

from . import profiles

MUTEX = "Local\\RazerLite.Instance"
ERROR_ALREADY_EXISTS = 183


def _show_flag():
    return profiles.config_dir() / "show.flag"


def acquire(wait=0.0):
    """Prend le verrou. Renvoie un jeton à garder ouvert, ou None si une autre copie tourne encore après `wait` s."""
    if sys.platform != "win32":
        return True
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    deadline = time.monotonic() + wait
    while True:
        handle = kernel32.CreateMutexW(None, False, MUTEX)
        if handle and ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
            return handle
        if handle:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def ask_existing_to_show():
    try:
        _show_flag().touch()
    except OSError:
        pass


def show_requested():
    """Vrai si une autre copie a demandé d'afficher la fenêtre (double-clic alors que RazerLite tourne déjà)."""
    flag = _show_flag()
    if flag.exists():
        flag.unlink(missing_ok=True)
        return True
    return False
