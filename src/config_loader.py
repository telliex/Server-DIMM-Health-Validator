"""Validate external configuration; resolve paths relative to the YAML file."""
from pathlib import Path
import re
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/test_env.yaml"
SCENARIOS = ("healthy", "corrected_error", "uncorrected_error", "unavailable")

def load_config(path=DEFAULT_CONFIG):
    path = Path(path).resolve()
    try:
        with path.open() as stream:
            cfg = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc
    if not isinstance(cfg, dict):
        raise ValueError("Configuration must be a mapping")
    for key in ("server", "connection", "execution", "tests", "thresholds", "report"):
        if not isinstance(cfg.get(key), dict):
            raise ValueError(f"Missing configuration section: {key}")
    execution = cfg["execution"]
    if execution.get("mode") not in ("mock", "real"):
        raise ValueError("mode must be mock or real")
    if execution.get("mock_scenario") not in SCENARIOS:
        raise ValueError("Invalid mock scenario")
    timeout = execution.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 3600:
        raise ValueError("timeout_seconds must be between 0 and 3600")
    for key in ("max_corrected_errors", "max_uncorrected_errors"):
        value = cfg["thresholds"].get(key)
        if type(value) is not int or value < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
    if type(cfg["thresholds"].get("fail_on_explicit_dimm_sensor", False)) is not bool:
        raise ValueError("fail_on_explicit_dimm_sensor must be boolean")
    slots = cfg["thresholds"].get("expected_slots")
    if not isinstance(slots, list) or not slots or any(not isinstance(s, str) or not s for s in slots) or len(set(slots)) != len(slots):
        raise ValueError("expected_slots must contain unique slot names")
    for key in ("check_dimm_inventory", "check_bmc_sel", "check_bmc_sdr", "check_linux_edac", "check_kernel_logs"):
        if type(cfg["tests"].get(key)) is not bool:
            raise ValueError(f"{key} must be boolean")
    for key in ("host_ip", "host_username", "bmc_ip", "bmc_username"):
        value = cfg["connection"].get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:]+", value) or value.startswith("-"):
            raise ValueError(f"Invalid connection field: {key}")
    for key in ("serial_number", "project", "test_stage"):
        if not isinstance(cfg["server"].get(key), str) or not cfg["server"][key]:
            raise ValueError(f"Missing server field: {key}")
    if cfg["report"].get("format") != "json":
        raise ValueError("Only JSON reports are supported")
    directory = cfg["report"].get("output_directory")
    if not isinstance(directory, str) or not directory:
        raise ValueError("output_directory is required")
    cfg["report"]["output_directory"] = str((path.parent / directory).resolve())
    return cfg
