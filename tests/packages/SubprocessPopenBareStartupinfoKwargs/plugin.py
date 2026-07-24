import subprocess


def _startupinfo_kwargs():
    startupinfo = subprocess.STARTUPINFO()
    return {"startupinfo": startupinfo}


subprocess.Popen(["tool"], **_startupinfo_kwargs())
