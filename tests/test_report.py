import json
from src.config_loader import load_config
from src.connection import MockConnection
from src.dimm_validator import validate
from src.report import save_report, print_report

def test_history_and_latest(tmp_path):
    report=validate(load_config(),MockConnection("healthy"))
    report["mock_scenario"]="../../unsafe/\\name"
    first=save_report(report,tmp_path)
    second=save_report(report,tmp_path)
    assert first != second and first.parent == second.parent == tmp_path
    assert len(list(tmp_path.glob("dimm_*.json"))) == 3
    for path in (first,second,tmp_path/"dimm_report.json"):
        assert json.loads(path.read_text()) == report
    assert not list(tmp_path.glob("*.tmp"))

def test_console_unknown_and_sections(tmp_path,capsys):
    report=validate(load_config(),MockConnection("unavailable"))
    print_report(report,tmp_path/"example.json")
    output=capsys.readouterr().out
    assert "CE: UNKNOWN | UE: UNKNOWN" in output
    assert "N/A (controller-level only)" in output
    for title in ("Collection status","Memory inventory","Controller-level ECC counts","Historical events and warnings","Overall diagnostic result","Recommendations"):
        assert title in output
    assert all(len(line)<=72 for line in output.splitlines() if not line.startswith("Report saved:"))

def test_atomic_write_failure_cleans_temporary(tmp_path,monkeypatch):
    import pytest
    import src.report as module
    def fail(*args): raise OSError("simulated replacement failure")
    monkeypatch.setattr(module.os,"replace",fail)
    with pytest.raises(OSError):
        save_report({},tmp_path)
    assert not list(tmp_path.iterdir())
