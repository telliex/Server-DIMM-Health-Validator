"""JSON persistence and concise interview-friendly console output."""
from pathlib import Path
import json
import os
import tempfile

def save_report(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "dimm_report.json"
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False, suffix=".tmp") as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, target)
    return target

def print_report(report, path):
    print("=" * 48 + "\n SERVER DIMM HEALTH VALIDATOR\n" + "=" * 48)
    print(f"Server SN: {report['server_sn']}\nTest Stage: {report['test_stage']}\nExecution Mode: {report['execution_mode'].upper()}")
    for source, check in report["checks"].items():
        print(f"[{check['status']}] {source}")
    for dimm in report["dimm_results"]:
        print(f"{dimm['slot']} | {dimm['capacity_gb']} GB | CE: unknown | UE: unknown | {dimm['status']}")
    edac = report["observations"]["edac"]
    print(f"Controller counters: CE={edac['corrected_errors']}, UE={edac['uncorrected_errors']} (complete={edac['available']})")
    print(f"OVERALL RESULT: {report['overall_result']}")
    for key in ("failures", "warnings", "unavailable_data", "recommended_next_steps"):
        for message in report[key]:
            print(f"{key}: {message}")
    print(f"Report saved: {path}")
