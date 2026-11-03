import json
import subprocess
import sys
from pathlib import Path
import pytest
import yaml
from src.config_loader import load_config
from src.connection import RealConnection
from src.main import main

@pytest.mark.parametrize("scenario,result,code", [("healthy","PASS",0),("corrected_error","FAIL",2),("uncorrected_error","FAIL",2),("unavailable","UNKNOWN",3)])
def test_mock_cli(tmp_path,scenario,result,code,monkeypatch):
    cfg=load_config()
    cfg["report"]["output_directory"]=str(tmp_path / "reports")
    path=tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    monkeypatch.setattr(subprocess,"run",lambda *a,**k: pytest.fail("mock must never execute external commands"))
    assert main(["--config",str(path),"--mode","mock","--scenario",scenario]) == code
    report=json.loads((tmp_path / "reports/dimm_report.json").read_text())
    assert report["overall_result"] == result
    assert report["timestamp"] and report["checks"] and report["observations"]
    assert report["execution_mode"] == "mock"

@pytest.mark.parametrize("source",["inventory","kernel","edac","sel","sdr"])
def test_real_commands(monkeypatch,source):
    monkeypatch.setenv("IPMI_PASSWORD","test-secret")
    captured={}
    def run(argv,**kwargs):
        captured.update(argv=argv,kwargs=kwargs)
        return subprocess.CompletedProcess(argv,0,"data","")
    monkeypatch.setattr(subprocess,"run",run)
    result=RealConnection(load_config()).collect(source)
    assert result.ok
    assert "test-secret" not in repr(result.to_dict())
    assert captured["kwargs"]["timeout"] == 30
    assert not captured["kwargs"].get("shell",False)
    if source in ("sel","sdr"):
        assert "-E" in captured["argv"]
    else:
        assert "BatchMode=yes" in captured["argv"]
        assert "StrictHostKeyChecking=yes" in captured["argv"]

@pytest.mark.parametrize("error",[FileNotFoundError("utility missing"),subprocess.TimeoutExpired("ssh",30)])
def test_real_exception(monkeypatch,error):
    def run(*a,**k): raise error
    monkeypatch.setattr(subprocess,"run",run)
    result=RealConnection(load_config()).collect("inventory")
    assert not result.ok and result.error

@pytest.mark.parametrize("source,message",[("inventory","Permission denied (publickey)"),("sel","Unable to establish IPMI session"),("edac","sudo: a password is required"),("kernel","dmesg: command not found")])
def test_real_nonzero(monkeypatch,source,message):
    monkeypatch.setenv("IPMI_PASSWORD","test-secret")
    monkeypatch.setattr(subprocess,"run",lambda argv,**kw:subprocess.CompletedProcess(argv,1,"",message))
    result=RealConnection(load_config()).collect(source)
    assert not result.ok and message in result.error

def test_missing_password(monkeypatch):
    monkeypatch.delenv("IPMI_PASSWORD",raising=False)
    assert "IPMI_PASSWORD" in RealConnection(load_config()).collect("sel").error

def test_real_requires_explicit_config():
    with pytest.raises(SystemExit) as exc:
        main(["--mode","real"])
    assert exc.value.code == 2
