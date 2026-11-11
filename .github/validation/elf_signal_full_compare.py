from pathlib import Path
import hashlib, json, os, re, subprocess, sys

base=Path("base")
source=base/"crates/formats/src/elf.rs"
fixed=source.read_bytes()
claim="36531c4ba20b7a4d081ef0d7a08c235dcb9778f4"
targets=[
    ("craft-anything-formats","elf_signal_origins",{
        "process_thread_and_queued_signals_do_not_publish_sender_bytes_as_fault_addresses",
        "timer_and_asynchronous_notifications_do_not_publish_their_union_as_an_address",
        "kernel_signals_without_a_fault_code_do_not_interpret_sender_storage",
        "unknown_positive_codes_and_ptrace_event_codes_do_not_invent_fault_addresses",
        "signal_specific_traps_keep_the_address_that_their_variant_records",
        "a_prstatus_signal_without_siginfo_keeps_its_origin_unknown",
        "a_truncated_siginfo_header_does_not_invent_a_zero_code_or_replace_prstatus",
    },3),
    ("craft-anything-engine","elf_signal_evidence",{
        "explicit_signal_sources_do_not_produce_a_false_fault_file_or_hardware_diagnosis",
        "prstatus_without_a_signal_origin_note_does_not_diagnose_a_memory_access",
    },1),
]
def cargo(*args):
    subprocess.run(["cargo",*args],cwd=base,check=True)
probe=base/"crates/engine/examples/core_signal_probe.rs"
probe.parent.mkdir(exist_ok=True)
probe.write_bytes(Path("validation/.github/validation/core_signal_probe.rs").read_bytes())
try:
    original=subprocess.check_output(["git","show",claim+":crates/formats/src/elf.rs"],cwd=base)
    source.write_bytes(original)
    for package,target,expected_failed,expected_passed in targets:
        command=["cargo","test","--locked","-p",package,"--test",target]
        run=subprocess.run(command,cwd=base,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        print(run.stdout,flush=True)
        outcomes=dict(re.findall(r"^test (\S+) \.\.\. (ok|FAILED)$",run.stdout,re.M))
        failed={name for name,state in outcomes.items() if state == "FAILED"}
        passed={name for name,state in outcomes.items() if state == "ok"}
        report={"target":target,"returncode":run.returncode,"failed":sorted(failed),"passed":sorted(passed)}
        print("ELF_REGRESSION_BASELINE="+json.dumps(report),flush=True)
        assert run.returncode != 0 and failed == expected_failed and len(passed) == expected_passed, report
    cargo("build","--locked","-p","craft-anything-engine","--example","core_signal_probe")
    subprocess.run([sys.executable,"validation/.github/validation/elf_signal_compare.py","baseline"],check=True)
finally:
    source.write_bytes(fixed)
try:
    cargo("build","--locked","-p","craft-anything-engine","--example","core_signal_probe")
    subprocess.run([sys.executable,"validation/.github/validation/elf_signal_compare.py","fixed"],check=True)
finally:
    probe.unlink(missing_ok=True)
print("ELF_NATIVE_AND_NEGATIVE_CONTROLS_COMPLETE",flush=True)
