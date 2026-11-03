from src.connection import MockConnection
from src.linux_checker import parse_inventory, parse_edac, parse_kernel
from src.bmc_checker import parse_sel, parse_sdr

def test_inventory():
    rows = parse_inventory(MockConnection("healthy").collect("inventory").stdout)
    assert len(rows) == 4
    assert rows[0]["capacity_gb"] == 32
    assert rows[0]["manufacturer"] == "Fictional Memory Co"
    assert parse_inventory("Memory Device\n Size: No Module Installed\n Locator: DIMM_X")[0]["present"] is False

def test_inventory_incomplete():
    assert parse_inventory("garbage") == []
    assert parse_inventory("Memory Device\n Size: Unknown\n Locator: DIMM_X")[0]["present"] is None

def test_edac():
    parsed = parse_edac(MockConnection("corrected_error").collect("edac").stdout)
    assert parsed["available"] and parsed["corrected_errors"] == 3
    assert parsed["physical_slot"] == "unknown"

def test_edac_incomplete():
    assert not parse_edac("")["available"]
    assert not parse_edac("/sys/devices/system/edac/mc/mc0/ce_count=0")["available"]
    assert not parse_edac("/sys/devices/system/edac/mc/mc0/ce_count=-1")["available"]

def test_events():
    events = parse_sel(MockConnection("uncorrected_error").collect("sel").stdout)
    assert events[0]["severity"] == "uncorrected"
    assert "01/05/2026" in events[0]["raw"]
    assert "historical" in events[0]["time_context"]
    assert parse_sel("SEL has no entries") == []
    assert parse_kernel("EDAC MC0: 3 CE on channel 1")[0]["severity"] == "corrected"

def test_sdr_formats():
    assert parse_sdr("DIMM_B1_STATE | ns")[0]["status"] == "ns"
    assert parse_sdr("DIMM_A1 | 42h | ok | 32.1 | Presence detected")[0]["status"] == "ok"
    assert parse_sdr("Memory sensor | platform-specific")[0]["status"] == "unknown"
    assert parse_sdr("CPU_TEMP | ok") == []
