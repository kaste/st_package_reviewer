import os
import subprocess


def _startupinfo_kwargs():
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": startupinfo}
    return {}


subprocess.Popen(["handled"], **_startupinfo_kwargs())
subprocess.Popen(["unhandled"])
