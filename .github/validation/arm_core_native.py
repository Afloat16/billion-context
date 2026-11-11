from pathlib import Path
import hashlib, json, os, resource, shutil, subprocess

root=Path(os.environ["RUNNER_TEMP"])/"arm32-native"
root.mkdir(exist_ok=True)
template=Path("validation/.github/validation/arm_core_fixture.s").read_text()
registers=[*[f"r{i}" for i in range(13)],"sp","lr","pc","cpsr"]
gdbscript=root/"registers.py"
gdbscript.write_text('import gdb, json\nframe=gdb.selected_frame()\nprint("ARM_NATIVE_REGS="+json.dumps({name:int(frame.read_register(name)) for name in '+repr(registers)+'}))\n')
def limit_core():
    resource.setrlimit(resource.RLIMIT_CORE,(16*1024*1024,16*1024*1024))
rows=[]
for big,thumb in [(False,False),(False,True),(True,False),(True,True)]:
    name=("be" if big else "le")+("-thumb" if thumb else "-arm")
    case=root/name
    case.mkdir(exist_ok=True)
    source=case/"fixture.s"
    mode=".thumb\n.thumb_func" if thumb else ".arm"
    source.write_text(template.replace("MODE",mode))
    program=case/"fixture"
    target="armebv7-linux-gnueabi" if big else "armv7-linux-gnueabi"
    command=["clang","--target="+target,"-march=armv7-a","-nostdlib","-static","--ld-path=/usr/bin/ld.lld-18","-Wl,--build-id=none","-Wl,-e,_start","-g",str(source),"-o",str(program)]
    build=subprocess.run(command,text=True,capture_output=True,timeout=60)
    assert build.returncode == 0, (name,build.stdout,build.stderr)
    symbols=subprocess.check_output(["readelf","-Ws",str(program)],text=True)
    matches=[line.split() for line in symbols.splitlines() if line.split() and line.split()[-1] == "fault_site"]
    assert len(matches) == 1, (name,symbols)
    fault=int(matches[0][1],16)&~1
    emulator="qemu-armeb" if big else "qemu-arm"
    run=subprocess.run([emulator,"-s","65536",str(program)],cwd=case,env={"PATH":os.environ["PATH"],"LANG":"C.UTF-8"},preexec_fn=limit_core,text=True,capture_output=True,timeout=30)
    guest=[]
    for path in case.iterdir():
        if not path.is_file() or path == program or path == source:
            continue
        with path.open("rb") as stream:
            head=stream.read(20)
        if head[:5] == b"\x7fELF\x01" and int.from_bytes(head[16:18],"big" if big else "little") == 4 and int.from_bytes(head[18:20],"big" if big else "little") == 40:
            guest.append(path)
    assert run.returncode != 0 and len(guest) == 1, (name,run.returncode,[str(p) for p in guest],run.stdout[-2000:],run.stderr[-2000:])
    core=root/(name+".core")
    shutil.move(guest[0],core)
    command=["gdb-multiarch","-nx","-q","-batch","-ex","set auto-load off","-ex","set debuginfod enabled off","-ex","file "+str(program),"-ex","core-file "+str(core),"-ex","python exec(open("+repr(str(gdbscript))+").read())"]
    debugger=subprocess.run(command,text=True,capture_output=True,timeout=30)
    records=[line.split("=",1)[1] for line in debugger.stdout.splitlines() if line.startswith("ARM_NATIVE_REGS=")]
    assert debugger.returncode == 0 and len(records) == 1, (name,debugger.returncode,debugger.stdout[-4000:],debugger.stderr[-2000:])
    values=json.loads(records[0])
    for i in range(13):
        assert values["r"+str(i)] == 0x1010+0x101*i, (name,i,values)
    assert values["lr"] == 0x1e1e and values["pc"] == fault, (name,values,fault)
    assert bool(values["cpsr"]&0x20) == thumb, (name,values["cpsr"])
    row={"name":name,"file":core.name,"big":big,"thumb":thumb,"registers":values,"expected_pc":fault,"bytes":core.stat().st_size,"core_sha256":hashlib.sha256(core.read_bytes()).hexdigest(),"binary_sha256":hashlib.sha256(program.read_bytes()).hexdigest()}
    rows.append(row)
    print("ARM_NATIVE_CORE="+json.dumps(row),flush=True)
(root/"cases.json").write_text(json.dumps(rows,indent=2)+"\n")
environment={name:subprocess.check_output([name,"--version"],text=True).splitlines()[0] for name in ["qemu-arm","qemu-armeb","gdb-multiarch","clang","readelf"]}
environment["packages"]=subprocess.check_output(["dpkg-query","-W","-f=${Package}=${Version}\n","qemu-user","gdb-multiarch"],text=True).splitlines()
print("ARM_NATIVE_ENV="+json.dumps(environment),flush=True)
