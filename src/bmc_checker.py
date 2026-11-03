"""Conservative memory event and sensor classification; no slot inference."""
import re

MEMORY = re.compile(r"\b(?:memory|dimm\w*|edac|ecc)\b", re.I)

def memory_events(text, source):
    events = []
    for line in text.splitlines():
        if not MEMORY.search(line):
            continue
        # Normal initialization and explicit zero-error messages are not faults.
        if re.search(r"\b(?:no|zero|0)\s+(?:(?:corrected|uncorrected|ecc|memory)\s+)*errors?\b", line, re.I):
            continue
        if not re.search(r"error|fail|disabled|correctable|uncorrect|\bCE\b|\bUE\b", line, re.I):
            continue
        severity = "uncorrected" if re.search(r"uncorrect|\bUE\b", line, re.I) else "corrected" if re.search(r"correctable|corrected|\bCE\b", line, re.I) else "memory_issue"
        kind = "ecc" if severity != "memory_issue" or re.search(r"\bECC\b",line,re.I) else "training_failure" if re.search("training",line,re.I) else "configuration_error" if re.search("config",line,re.I) else "dimm_disabled" if re.search("disabled",line,re.I) else "memory_failure"
        assertion = "deasserted" if re.search(r"\bdeasserted\b",line,re.I) else "asserted" if re.search(r"\basserted\b",line,re.I) else "unknown"
        events.append({"source": source, "event_type": kind, "severity": severity, "assertion": assertion,
                       "raw": line, "time_context": "historical; no configured test window", "physical_slot": "unknown"})
    return events

def parse_sel(text):
    return memory_events(text, "sel")

def parse_sdr(text):
    sensors = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if not MEMORY.search(parts[0]):
            continue
        status = next((s.lower() for s in parts[1:] if s.lower() in ("ok", "ns", "na", "nr", "cr", "nc", "lnr", "unr", "lcr", "ucr")), "unknown")
        # Critical code alone can refer to temperature or another platform-specific
        # condition. Only explicit, current DIMM failure text is unambiguous here.
        explicit = status in ("cr", "lnr", "unr", "lcr", "ucr") and bool(re.search(r"\bdimm\w*\b.*\b(?:failure|failed)\b", line, re.I)) and not re.search(r"deasserted|no failure|not failed",line,re.I)
        sensors.append({"name": parts[0], "status": status, "raw": line,
                        "classification": "explicit_dimm_failure" if explicit else "normal" if status == "ok" else "unsupported" if status in ("ns","na","nr") else "ambiguous",
                        "unambiguous_failure": bool(explicit)})
    return sensors
