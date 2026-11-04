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
    """Totals require a complete dataset; retain partial controller observations."""
    controllers, invalid, seen = {}, [], set()
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"/sys/devices/system/edac/mc/(mc\d+)/(ce_count|ue_count)=(.*)", line.strip())
        if not match:
            invalid.append(line)
            continue
        mc, kind, value = match.groups()
        counters = controllers.setdefault(mc, {"ce_count": None, "ue_count": None})
        key = (mc, kind)
        if key in seen or not re.fullmatch(r"[0-9]+", value):
            counters[kind] = None
            invalid.append(line)
        else:
            counters[kind] = int(value)
        seen.add(key)
    complete = bool(controllers) and not invalid and all(all(v is not None for v in c.values()) for c in controllers.values())
    return {"available": complete, "controllers": controllers, "invalid_lines": invalid,
            "corrected_errors": sum(c["ce_count"] for c in controllers.values()) if complete else None,
            "uncorrected_errors": sum(c["ue_count"] for c in controllers.values()) if complete else None,
            "physical_slot": "unknown", "scope": "current cumulative controller counters; reset epoch unknown"}

def parse_kernel(text):
    from .bmc_checker import memory_events
    return memory_events(text, "kernel")
