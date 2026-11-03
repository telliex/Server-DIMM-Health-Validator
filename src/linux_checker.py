"""Parse inventory, EDAC counters and kernel memory observations."""
import re

def parse_inventory(text):
    """Parse type-17 sections without absorbing adjacent DMI records."""
    blocks, current = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "Memory Device":
            current = {}
            blocks.append(current)
        elif stripped.startswith("Handle ") or (stripped and ":" not in stripped):
            current = None
        elif current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            # Duplicate fields make the relevant value untrustworthy.
            current[key] = value.strip() if key not in current else "Unknown"
    result = []
    unknown = {"", "unknown", "not specified", "none"}
    for fields in blocks:
        size = fields.get("Size", "")
        match = re.fullmatch(r"([0-9]+)\s+(MB|GB|TB)", size, re.I)
        capacity = int(match[1]) * {"GB": 1, "MB": 1/1024, "TB": 1024}[match[2].upper()] if match else None
        empty = size.lower() in ("no module installed", "not installed")
        locator = fields.get("Locator", "")
        result.append({"slot": "unknown" if locator.lower() in unknown else locator,
                       "capacity_gb": capacity,
                       "present": False if empty else True if capacity and capacity > 0 else None,
                       **{key: None if fields.get(label, "").lower() in unknown else fields[label]
                          for key, label in (("manufacturer", "Manufacturer"), ("part_number", "Part Number"),
                                             ("serial_number", "Serial Number"), ("speed", "Speed"))}})
    return result

def parse_edac(text):
    controllers = {}
    invalid = []
    for line in text.splitlines():
        match = re.fullmatch(r"/sys/devices/system/edac/mc/(mc\d+)/(ce_count|ue_count)=(\d+)", line.strip())
        if match:
            mc, kind, value = match.groups()
            if kind in controllers.setdefault(mc, {}):
                invalid.append(line)
            controllers[mc][kind] = int(value)
        elif line.strip():
            invalid.append(line)
    complete = bool(controllers) and not invalid and all(set(c) == {"ce_count", "ue_count"} for c in controllers.values())
    return {"available": complete, "controllers": controllers, "invalid_lines": invalid,
            "corrected_errors": sum(c.get("ce_count", 0) for c in controllers.values()),
            "uncorrected_errors": sum(c.get("ue_count", 0) for c in controllers.values()),
            "physical_slot": "unknown", "scope": "current cumulative controller counters; reset epoch unknown"}

def parse_kernel(text):
    from .bmc_checker import memory_events
    return memory_events(text, "kernel")
