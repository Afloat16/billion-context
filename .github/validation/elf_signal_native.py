from pathlib import Path
import hashlib, json, os, platform, subprocess

root=Path(os.environ["RUNNER_TEMP"])/"elf-signal-native"
root.mkdir(exist_ok=True)
source=Path("validation/.github/validation/elf_signal_fixture.c").resolve()
program=root/"signal-fixture"
subprocess.run(["gcc","-g","-O0","-fno-pie","-no-pie","-Wall","-Wextra","-Werror",str(source),"-lrt","-o",str(program)],check=True)
script=root/"signal_metadata.py"
script.write_text("""import gdb, json
s=gdb.parse_and_eval("$_siginfo")
print("NATIVE_SIGNAL="+json.dumps({"signo":int(s["si_signo"]),"errno":int(s["si_errno"]),"code":int(s["si_code"]),"union_addr":hex(int(s["_sifields"]["_sigfault"]["si_addr"]))}))
""")
cases=[
    ("kill-segv",11,0,None,"sent by a process"),
    ("raise-ill",4,-6,None,"sent to a thread"),
    ("queue-bus",7,-1,None,"queued by a process"),
    ("timer-segv",11,-2,None,"timer"),
    ("kill-abrt",6,0,None,"sent by a process"),
    ("fault-segv",11,2,"native",None),
    ("illegal-ill",4,2,"native",None),
    ("divide-fpe",8,1,"native",None),
    ("kernel-trap",5,128,None,None),
]
rows=[]
for name,signo,code,fault,meaning in cases:
    core=root/(name+".core")
    command=["gdb","-nx","-q","-batch","-ex","set auto-load off","-ex","set debuginfod enabled off","-ex","set confirm off","-ex","set disable-randomization off","-ex","run","-ex","python exec(open("+repr(str(script))+").read())","-ex","generate-core-file "+str(core),"--args",str(program),name]
    run=subprocess.run(command,text=True,capture_output=True,timeout=30)
    lines=[line for line in run.stdout.splitlines() if line.startswith("NATIVE_SIGNAL=")]
    assert run.returncode == 0 and len(lines) == 1 and core.exists(), (name,run.returncode,run.stdout[-3000:],run.stderr[-2000:])
    native=json.loads(lines[0].split("=",1)[1])
    assert (native["signo"],native["code"]) == (signo,code), (name,native)
    notes=subprocess.run(["readelf","-n",str(core)],text=True,capture_output=True,timeout=20)
    assert notes.returncode == 0 and "NT_SIGINFO" in notes.stdout, (name,notes.returncode,notes.stderr)
    expected_fault=native["union_addr"] if fault == "native" else None
    row={"name":name,"file":core.name,"native":native,"expected_fault":expected_fault,"meaning_contains":meaning,"bytes":core.stat().st_size,"sha256":hashlib.sha256(core.read_bytes()).hexdigest()}
    rows.append(row)
    print("NATIVE_CORE="+json.dumps(row),flush=True)
environment={"kernel":platform.release(),"machine":platform.machine(),"gcc":subprocess.check_output(["gcc","--version"],text=True).splitlines()[0],"gdb":subprocess.check_output(["gdb","--version"],text=True).splitlines()[0],"readelf":subprocess.check_output(["readelf","--version"],text=True).splitlines()[0]}
(root/"cases.json").write_text(json.dumps(rows,indent=2)+"\n")
print("NATIVE_CORE_ENV="+json.dumps(environment),flush=True)
