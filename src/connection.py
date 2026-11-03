"""Read-only command adapters. No shell execution or mock fallback."""
from dataclasses import dataclass, asdict
from pathlib import Path
import os
import subprocess

# All remote shell text is fixed; no configuration is interpolated into it.
EDAC_COMMAND = """sudo -n sh -c 'root=/sys/devices/system/edac/mc; found=0; for mc in "$root"/mc[0-9]*; do [ -d "$mc" ] || continue; found=1; for name in ce_count ue_count; do f="$mc/$name"; [ -r "$f" ] || exit 13; printf "%s=" "$f"; cat "$f" || exit; done; done; [ "$found" = 1 ] || exit 4'"""
COMMANDS = {
    "inventory": ("ssh", "sudo -n dmidecode -t 17"),
    "kernel": ("ssh", "sudo -n dmesg -T"),
    "edac": ("ssh", EDAC_COMMAND),
    "sel": ("ipmi", "sel", "elist"),
    "sdr": ("ipmi", "sdr", "elist"),
}

@dataclass
class Collection:
    source: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    error: str | None = None
    command: list[str] | None = None

    @property
    def ok(self):
        return self.error is None and self.returncode == 0

    def to_dict(self):
        return {**asdict(self), "ok": self.ok}

class MockConnection:
    def __init__(self, scenario: str):
        from .config_loader import SCENARIOS
        if scenario not in SCENARIOS:
            raise ValueError("Invalid mock scenario")
        self.root = Path(__file__).resolve().parents[1] / "mock" / scenario

    def collect(self, source: str) -> Collection:
        try:
            raw = json_load(self.root / f"{source}.json")
            return Collection(source=source, **raw)
        except (OSError, ValueError, TypeError) as exc:
            return Collection(source, error=f"Missing or invalid fixture: {exc}")

def json_load(path):
    import json
    return json.loads(path.read_text())

class RealConnection:
    def __init__(self, config):
        self.connection = config["connection"]
        self.timeout = config["execution"]["timeout_seconds"]

    def collect(self, source: str) -> Collection:
        spec = COMMANDS[source]
        c = self.connection
        if spec[0] == "ssh":
            argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "--", f'{c["host_username"]}@{c["host_ip"]}', spec[1]]
        else:
            if not os.environ.get("IPMI_PASSWORD"):
                return Collection(source, error="IPMI_PASSWORD environment variable is required")
            argv = ["ipmitool", "-I", "lanplus", "-H", c["bmc_ip"], "-U", c["bmc_username"], "-E", *spec[1:]]
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout, check=False)
            error = None if completed.returncode == 0 else f"Command failed (exit {completed.returncode}): {completed.stderr.strip()}"
            return Collection(source, completed.stdout, completed.stderr, completed.returncode, error, argv)
        except subprocess.TimeoutExpired:
            return Collection(source, error=f"Command timeout after {self.timeout}s", command=argv)
        except OSError as exc:
            return Collection(source, error=f"Command unavailable: {exc}", command=argv)
