"""Run with python -m src.main. Exit: PASS=0 WARNING=1 FAIL=2 UNKNOWN=3."""
import argparse
import logging
from .config_loader import DEFAULT_CONFIG, SCENARIOS, load_config
from .connection import MockConnection, RealConnection
from .dimm_validator import validate
from .report import save_report, print_report

def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only DIMM health evidence validator")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mode", choices=("mock", "real"))
    parser.add_argument("--scenario", choices=SCENARIOS, help="Offline synthetic diagnostic scenario (mock mode only)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    try:
        logging.info("Loading configuration")
        cfg = load_config(args.config or DEFAULT_CONFIG)
        if args.mode:
            cfg["execution"]["mode"] = args.mode
        if args.scenario:
            cfg["execution"]["mock_scenario"] = args.scenario
        real = cfg["execution"]["mode"] == "real"
        if real and args.config is None:
            parser.error("Real mode requires --config with explicit authorized server configuration")
        if real and args.scenario:
            parser.error("--scenario is only valid in mock mode")
        adapter = RealConnection(cfg) if real else MockConnection(cfg["execution"]["mock_scenario"])
        report = validate(cfg, adapter)
        path = save_report(report, cfg["report"]["output_directory"])
        print_report(report, path)
        return {"PASS": 0, "WARNING": 1, "FAIL": 2, "UNKNOWN": 3}[report["overall_result"]]
    except (ValueError, OSError) as exc:
        logging.error("%s", exc)
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
