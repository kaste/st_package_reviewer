import subprocess as sp
from subprocess import check_output

startupinfo = sp.STARTUPINFO()
sp.run(["tool"], startupinfo=startupinfo)
check_output(["tool"], creationflags=sp.CREATE_NO_WINDOW)
