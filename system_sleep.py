"""Put the workstation to sleep (best-effort, platform-specific)."""
import ctypes
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def sleep_system():
    """Suspend the computer. Returns (ok, error_message)."""
    if sys.platform == "win32":
        try:
            ctypes.windll.PowrProf.SetSuspendState(False, False, False)
            return True, ""
        except Exception as e:
            logger.warning("SetSuspendState failed: %s", e)
            try:
                subprocess.run(
                    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                    check=False,
                    creationflags=CREATE_NO_WINDOW,
                )
                return True, ""
            except Exception as e2:
                return False, str(e2)
    if sys.platform == "darwin":
        try:
            subprocess.run(["pmset", "sleepnow"], check=False)
            return True, ""
        except Exception as e:
            return False, str(e)
    for cmd in (
        ["systemctl", "suspend"],
        [
            "dbus-send",
            "--system",
            "--print-reply",
            "--dest=org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager.Suspend",
            "boolean:true",
        ],
    ):
        try:
            subprocess.run(cmd, check=False)
            return True, ""
        except Exception:
            continue
    return False, "Suspend is not supported on this platform"
