from pathlib import Path
import json, re, subprocess, sys

base=Path("base")
source=base/"crates/formats/src/elf.rs"
fixed=source.read_bytes()
claim="efa47e7433b14da740cbe0f21e219a13ad48694b"
targets=[
    ("craft-anything-formats","elf_arm_core_registers",{
        "linux_arm_registers_decode_in_little_endian_cores",
        "linux_arm_registers_decode_in_big_endian_cores",
        "thumb_state_is_preserved_without_changing_the_recorded_pc",
        "truncated_register_words_are_not_invented_or_read_from_the_next_note",
        "a_second_thread_keeps_its_own_registers_and_does_not_replace_the_crashing_pc",
    },3),
    ("craft-anything-engine","elf_arm_crash_evidence",{
        "arm_core_evidence_locates_the_recorded_program_counter_in_both_byte_orders",
        "arm_thread_registers_reach_the_verified_public_evidence_without_truncating_values",
    },1),
]
probe=base/"crates/engine/examples/arm_core_probe.rs"
probe.parent.mkdir(exist_ok=True)
probe.write_bytes(Path("validation/.github/validation/arm_core_probe.rs").read_bytes())
def cargo(*args):
    subprocess.run(["cargo",*args],cwd=base,check=True)
try:
    source.write_bytes(subprocess.check_output(["git","show",claim+":crates/formats/src/elf.rs"],cwd=base))
    for package,target,expected_failed,expected_passed in targets:
        run=subprocess.run(["cargo","test","--locked","-p",package,"--test",target],cwd=base,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        print(run.stdout,flush=True)
        outcomes=dict(re.findall(r"^test (\S+) \.\.\. (ok|FAILED)$",run.stdout,re.M))
        failed={name for name,state in outcomes.items() if state == "FAILED"}
        passed={name for name,state in outcomes.items() if state == "ok"}
        report={"target":target,"returncode":run.returncode,"failed":sorted(failed),"passed":sorted(passed)}
        print("ARM_REGRESSION_BASELINE="+json.dumps(report),flush=True)
        assert run.returncode != 0 and failed == expected_failed and len(passed) == expected_passed, report
    cargo("build","--locked","-p","craft-anything-engine","--example","arm_core_probe")
    subprocess.run([sys.executable,"validation/.github/validation/arm_core_compare.py","baseline"],check=True)
    source.write_bytes(fixed)
    cargo("build","--locked","-p","craft-anything-engine","--example","arm_core_probe")
    subprocess.run([sys.executable,"validation/.github/validation/arm_core_compare.py","fixed"],check=True)
finally:
    source.write_bytes(fixed)
    probe.unlink(missing_ok=True)
print("ARM_NATIVE_AND_NEGATIVE_CONTROLS_COMPLETE",flush=True)
