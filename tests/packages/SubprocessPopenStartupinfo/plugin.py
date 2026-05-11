import subprocess

startupinfo = subprocess.STARTUPINFO()
subprocess.Popen(["tool"], startupinfo=startupinfo)
