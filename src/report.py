"""Atomic run history plus a latest convenience copy; readable console evidence."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import tempfile
from uuid import uuid4
from textwrap import fill

def _atomic_write(report, target):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False, suffix=".tmp") as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def save_report(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Never interpolate server identifiers or arbitrary path components.
    scenario = re.sub(r"[^a-zA-Z0-9_-]", "_", str(report.get("mock_scenario") or "real"))[:40]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"dimm_{stamp}_{scenario}_{uuid4().hex}.json"
    _atomic_write(report, target)
    _atomic_write(report, directory / "dimm_report.json")
    return target

def print_report(report, path):
    def line(text):
        print(fill(str(text), width=72, subsequent_indent="  "))
    def section(title):
        print("\n" + title + "\n" + "-" * len(title))
    print("SERVER DIMM HEALTH VALIDATOR")
    section("Server / test context")
    for label, field in (("Server SN", "server_sn"), ("Test stage", "test_stage"), ("Mode", "execution_mode")):
        line(f"{label}: {report[field]}")
    section("Collection status")
    for source, check in report["checks"].items():
        line(f"{source}: {check['collection_status']} | evidence: {check['evidence_status']} | diagnosis: {check['diagnostic_result']}")
    section("Memory inventory")
    for dimm in report["dimm_results"]:
        line(f"{dimm['slot']} | {dimm['capacity_gb']} GB | present: {dimm['present']} | {dimm['status']}")
    line("Per-DIMM CE/UE: N/A (controller-level only). Overall PASS can coexist with UNKNOWN physical-slot ECC attribution.")
    section("Controller-level ECC counts")
    edac = report["observations"]["edac"]
    value = lambda n: "UNKNOWN" if n is None else str(n)
    line(f"CE: {value(edac['corrected_errors'])} | UE: {value(edac['uncorrected_errors'])} | complete: {edac['available']}")
    for mc, counters in edac["controllers"].items():
        line(f"{mc}: observed CE={value(counters['ce_count'])}, UE={value(counters['ue_count'])}")
    section("Historical events and warnings")
    for event in report["observations"]["events"]:
        line(f"{event['source']} / {event['event_type']} / {event['assertion']}: {event['raw']}")
    for message in report["warnings"]:
        line(message)
    section("Overall diagnostic result")
    line(report["overall_result"])
    for message in report["failures"] + report["unavailable_data"]:
        line(message)
    section("Recommendations")
    for message in report["recommended_next_steps"]:
        line(message)
    print(f"\nReport saved: {path}")
