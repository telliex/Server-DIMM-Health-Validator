"""Separate manufacturing CLI; the original diagnostic CLI is unchanged."""
import argparse
import json
import logging
from pathlib import Path
import sqlite3
import yaml
from .config_loader import load_config
from .connection import MockConnection, RealConnection
from .sfcs import SFCSError
from .sfcs.store import ResultStore
from .sfcs.mock import MockSFCSAdapter
from .sfcs.rest import RestSFCSAdapter
from .sfcs.workflow import execute
from .sfcs.delivery import Delivery, event


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Manufacturing YAML configuration')
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--serial-number', required=True)
    run.add_argument('--stage', choices=('IST', 'SAT'), required=True)
    run.add_argument('--station', required=True)
    run.add_argument('--scenario')
    run.add_argument('--retest-of')
    history = commands.add_parser('history')
    history.add_argument('--serial-number', required=True)
    history.add_argument('--remote', action='store_true')
    commands.add_parser('retry')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        path = Path(args.config).resolve()
        cfg = yaml.safe_load(path.read_text())
        if not isinstance(cfg, dict) or cfg.get('adapter') not in ('mock', 'rest'):
            raise ValueError('adapter must be mock or rest')
        store = ResultStore(path.parent / cfg['database'])
        adapter = (MockSFCSAdapter(path.parent / cfg['mock_database'], offline=cfg.get('mock_offline', False))
                   if cfg['adapter'] == 'mock' else RestSFCSAdapter(**cfg['rest']))
        if args.command == 'history':
            print(json.dumps(adapter.get_test_history(args.serial_number) if args.remote else store.history(args.serial_number), indent=2))
            return 0
        delivery = Delivery(store)
        options = cfg.get('retry', {})
        if args.command == 'retry':
            statuses = delivery.retry(adapter, **options)
            print(json.dumps(statuses))
            return 0 if all(s == 'sent' for s in statuses.values()) else 4
        hardware_path = path.parent / cfg['hardware_config']
        hardware = load_config(hardware_path)
        hardware['server'].update(serial_number=args.serial_number, test_stage=args.stage)
        if args.scenario:
            if hardware['execution']['mode'] != 'mock':
                raise ValueError('--scenario requires mock hardware mode')
            hardware['execution']['mock_scenario'] = args.scenario
        connection = (MockConnection(hardware['execution']['mock_scenario']) if hardware['execution']['mode'] == 'mock'
                      else RealConnection(hardware))
        result = execute(hardware, connection, adapter, args.station, store, args.retest_of)
        status = delivery.submit(adapter, result, **options)
        print(json.dumps({'run_id': result['run_id'], 'result': result['result'],
                          'diagnostic_result': result['diagnostic_result'], 'upload_status': status}))
        return 4 if status != 'sent' else 0 if result['result'] == 'PASS' else 2
    except (SFCSError, ValueError, OSError, KeyError, TypeError, sqlite3.Error, yaml.YAMLError):
        event('manufacturing_error', message='Check configuration, eligibility and service availability')
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
