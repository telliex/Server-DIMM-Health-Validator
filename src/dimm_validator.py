"""Combine evidence conservatively. Confirmed failures dominate missing data."""
from datetime import datetime, timezone
from .linux_checker import parse_inventory, parse_edac, parse_kernel
from .bmc_checker import parse_sel, parse_sdr

SOURCES = {"inventory": "check_dimm_inventory", "sel": "check_bmc_sel", "sdr": "check_bmc_sdr", "edac": "check_linux_edac", "kernel": "check_kernel_logs"}

def validate(config, connection):
    checks, raw, missing, failures, warnings = {}, {}, [], [], []
    for source, flag in SOURCES.items():
        if not config["tests"][flag]:
            checks[source] = {"status": "SKIPPED", "required": False}
            continue
        collection = connection.collect(source)
        raw[source] = collection
        valid = collection.ok and bool(collection.stdout.strip())
        checks[source] = {"status": "PASS" if valid else "UNKNOWN", "required": True, **collection.to_dict()}
        if not valid:
            missing.append(f"{source}: {collection.error or 'empty diagnostic output'}")
    def content(source):
        return raw[source].stdout if source in raw and raw[source].ok else ""
    inventory = parse_inventory(content("inventory"))
    edac = parse_edac(content("edac"))
    sensors = parse_sdr(content("sdr"))
    events = parse_sel(content("sel")) + parse_kernel(content("kernel"))
    def incomplete(source, reason):
        if source in raw and raw[source].ok:
            missing.append(f"{source}: {reason}")
            checks[source]["status"] = "UNKNOWN"
    inventory_complete = bool(inventory) and all(d["slot"] != "unknown" and d["present"] is not None for d in inventory) and len({d["slot"] for d in inventory}) == len(inventory)
    if not inventory_complete:
        incomplete("inventory", "incomplete or unrecognized inventory")
    if not edac["available"]:
        incomplete("edac", "EDAC unavailable or incomplete")
    # Successful SEL with an explicit empty-log response is valid evidence.
    sel_text = content("sel")
    if sel_text and "SEL has no entries" not in sel_text and not all(len(line.split("|")) >= 5 for line in sel_text.splitlines() if line.strip()):
        incomplete("sel", "unrecognized SEL format")
    if content("sdr") and not any(len(line.split("|")) >= 2 for line in content("sdr").splitlines()):
        incomplete("sdr", "unrecognized sensor output")
    dimms = []
    expected = config["thresholds"]["expected_slots"]
    for slot in sorted(set(expected) | {d["slot"] for d in inventory}):
        item = next((d for d in inventory if d["slot"] == slot), None)
        absent = inventory_complete and slot in expected and (item is None or item["present"] is False)
        if absent:
            failures.append(f"Missing expected DIMM: {slot}")
        dimms.append({**(item or {"slot": slot, "present": None, "capacity_gb": None}),
                      "corrected_errors": None, "uncorrected_errors": None,
                      "status": "FAIL" if absent else "UNKNOWN",
                      "evidence": ["Controller counters cannot be reliably attributed to this physical slot."],
                      "recommendation": "Verify physical slot mapping and review hardware diagnostics."})
    # Preserve observed failures even when another controller/source is incomplete.
    for field, threshold in (("corrected_errors", "max_corrected_errors"), ("uncorrected_errors", "max_uncorrected_errors")):
        if edac[field] > config["thresholds"][threshold]:
            failures.append(f"EDAC {field}: {edac[field]} exceeds {config['thresholds'][threshold]} (controller scope)")
    for sensor in sensors:
        if sensor["status"] != "ok":
            warnings.append(f"Sensor {sensor['name']}: {sensor['status']}; physical fault not established")
    if not sensors and "sdr" in raw and raw["sdr"].ok:
        warnings.append("BMC exposes no recognized memory sensors; per-DIMM health unavailable")
    if events:
        warnings.append("Historical memory events require timestamp/context review; not classified as new failures")
    if not raw:
        missing.append("No diagnostic checks enabled")
    # Inventory and EDAC are essential to this validator even when collection is disabled.
    for source in ("inventory", "edac"):
        if source not in raw:
            missing.append(f"{source}: essential diagnostic check disabled")
    result = "FAIL" if failures else "UNKNOWN" if missing else "WARNING" if warnings else "PASS"
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "server_sn": config["server"]["serial_number"],
            "project": config["server"]["project"], "test_stage": config["server"]["test_stage"],
            "execution_mode": config["execution"]["mode"], "mock_scenario": config["execution"].get("mock_scenario") if config["execution"]["mode"] == "mock" else None,
            "test_name": "DIMM_HEALTH_VALIDATION", "overall_result": result, "dimm_results": dimms,
            "checks": checks, "observations": {"inventory": inventory, "edac": edac, "sensors": sensors, "events": events},
            "failures": failures, "warnings": warnings, "unavailable_data": missing,
            "limitations": ["Zero reported errors is not comprehensive memory testing.", "No defined test window: counters are cumulative and logs historical.", "Physical DIMM attribution is unavailable from controller-only counters."],
            "recommended_next_steps": ["Review EDAC and BMC SEL timestamps.", "Verify physical DIMM slot mapping.", "Check for recurring errors using an approved troubleshooting procedure."]}
