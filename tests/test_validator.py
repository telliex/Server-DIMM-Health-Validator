from copy import deepcopy
import pytest
import yaml
from src.config_loader import load_config
from src.connection import MockConnection, Collection, RealConnection
from src.dimm_validator import validate

@pytest.fixture
def cfg():
    return load_config()

class Altered(MockConnection):
    def __init__(self, source, output=None, error=None):
        super().__init__("healthy")
        self.source, self.output, self.error = source, output, error
    def collect(self, source):
        if source == self.source:
            return Collection(source, stdout=self.output or "", returncode=1 if self.error else 0, error=self.error)
        return super().collect(source)

def test_config(cfg):
    assert cfg["execution"]["mode"] == "mock"
    assert cfg["report"]["output_directory"].endswith("/reports")

@pytest.mark.parametrize("section,key,value", [("thresholds","max_corrected_errors",-1),("execution","timeout_seconds",0),("connection","host_username","-oProxyCommand=x"),("tests","check_bmc_sel","yes"),("thresholds","expected_slots",[])])
def test_invalid_config(tmp_path,cfg,section,key,value):
    cfg[section][key] = value
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError):
        load_config(path)

def test_thresholds(cfg):
    cfg["thresholds"]["max_corrected_errors"] = 3
    report = validate(cfg, MockConnection("corrected_error"))
    assert report["overall_result"] == "WARNING" # historical events remain visible
    cfg["thresholds"]["max_corrected_errors"] = 2
    assert validate(cfg, MockConnection("corrected_error"))["overall_result"] == "FAIL"

def test_missing_dimm(cfg):
    text = MockConnection("healthy").collect("inventory").stdout.replace("Size: 32 GB", "Size: No Module Installed", 1)
    report = validate(cfg, Altered("inventory", text))
    assert report["overall_result"] == "FAIL"
    assert "Missing expected DIMM" in report["failures"][0]

def test_missing_inventory_is_unknown(cfg):
    assert validate(cfg, Altered("inventory",error="permission denied"))["overall_result"] == "UNKNOWN"

def test_unknown_sensor(cfg):
    report = validate(cfg, Altered("sdr","DIMM_B1_STATE | ns"))
    assert report["overall_result"] == "WARNING"
    assert not report["failures"]

def test_no_memory_sensors(cfg):
    assert validate(cfg, Altered("sdr","Fan1 | ok"))["overall_result"] == "WARNING"

@pytest.mark.parametrize("source",["edac","inventory","sel","kernel","sdr"])
def test_failed_required_source(cfg,source):
    assert validate(cfg,Altered(source,error="command failed"))["overall_result"] == "UNKNOWN"

@pytest.mark.parametrize("source,text",[("inventory","garbage"),("edac","not supported"),("sel","nonsense"),("sdr","nonsense"),("kernel","")])
def test_incomplete_data(cfg,source,text):
    assert validate(cfg,Altered(source,text))["overall_result"] == "UNKNOWN"

def test_failure_precedes_unknown(cfg):
    class Mixed(MockConnection):
        def collect(self,source):
            return Collection(source,error="timeout") if source == "kernel" else super().collect(source)
    assert validate(cfg,Mixed("uncorrected_error"))["overall_result"] == "FAIL"

def test_historical_sel_is_warning(cfg):
    report=validate(cfg,Altered("sel","1 | 01/05/2020 | 10:05:00 | Memory | Uncorrectable ECC | Asserted"))
    assert report["overall_result"] == "WARNING"
    assert not report["failures"]

def test_disabled_essential(cfg):
    cfg["tests"]["check_linux_edac"]=False
    assert validate(cfg,MockConnection("healthy"))["overall_result"] == "UNKNOWN"

@pytest.mark.parametrize("text", ["Memory Device\n Size: 32 GB\n Locator: DIMM_A1\nMemory Device\n Size: 32 GB\n Locator: DIMM_A1", " Memory Device\n Size: Unknown\n Locator: DIMM_A1"])
def test_untrustworthy_inventory(cfg,text):
    assert validate(cfg,Altered("inventory",text))["overall_result"] == "UNKNOWN"

def test_explicit_sensor_policy(cfg):
    adapter=Altered("sdr","DIMM_A1 | cr | DIMM failure asserted")
    assert validate(cfg,adapter)["overall_result"] == "WARNING"
    cfg["thresholds"]["fail_on_explicit_dimm_sensor"] = True
    assert validate(cfg,adapter)["overall_result"] == "FAIL"
    assert validate(cfg,Altered("sdr","DIMM_A1 | cr | temperature high"))["overall_result"] == "WARNING"
