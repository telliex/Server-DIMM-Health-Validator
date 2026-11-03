"""Keep historical event evidence separate from current counters."""
import re

def memory_events(text, source):
    events = []
    for line in text.splitlines():
        if not re.search(r"memory|dimm|edac|ecc", line, re.I):
            continue
        if not re.search(r"error|fail|disabled|correctable|uncorrect|\bCE\b|\bUE\b", line, re.I):
            continue
        severity = "uncorrected" if re.search(r"uncorrect|\bUE\b", line, re.I) else "corrected" if re.search(r"correctable|corrected|\bCE\b", line, re.I) else "memory_issue"
        events.append({"source": source, "severity": severity, "raw": line,
                       "time_context": "historical; no configured test window", "physical_slot": "unknown"})
    return events

def parse_sel(text):
    return memory_events(text, "sel")

def parse_sdr(text):
    sensors = []
    for line in text.splitlines():
        if re.search(r"dimm|memory|\bmem\b", line, re.I):
            parts = [p.strip() for p in line.split("|")]
            status = next((s.lower() for s in parts[1:] if s.lower() in ("ok", "ns", "na", "nr", "cr", "nc", "lnr", "unr", "lcr", "ucr")), "unknown")
            sensors.append({"name": parts[0], "status": status, "raw": line})
    return sensors
