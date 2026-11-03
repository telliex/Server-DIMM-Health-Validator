"""Parse inventory, EDAC counters and kernel memory observations."""
import re

def parse_inventory(text):
    result = []
    for block in re.split(r"(?m)^Memory Device\s*$", text)[1:]:
        fields = dict(re.findall(r"(?m)^\s*([^:\n]+):\s*([^\n]*)", block))
        size = fields.get("Size", "")
        match = re.fullmatch(r"(\d+) (GB|MB|TB)", size)
        empty = size in ("No Module Installed", "Not Installed")
        result.append({"slot": fields.get("Locator", "unknown"),
                       "capacity_gb": int(match[1]) * {"GB": 1, "MB": 1/1024, "TB": 1024}[match[2]] if match else None,
                       "present": False if empty else True if match else None,
                       **{key: fields.get(label) for key, label in (("manufacturer", "Manufacturer"), ("part_number", "Part Number"), ("serial_number", "Serial Number"), ("speed", "Speed"))}})
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
