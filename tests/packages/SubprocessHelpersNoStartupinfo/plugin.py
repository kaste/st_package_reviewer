import subprocess as sp
from subprocess import call as subprocess_call
from subprocess import check_call, check_output, Popen, run

sp.Popen(["tool"])
Popen(["tool"])
run(["tool"])
subprocess_call(["tool"])
check_call(["tool"])
check_output(["tool"])
