"""Station gating, immutable run traceability and hardware orchestration."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from . import SFCSError
from ..dimm_validator import validate

TEST_VERSION = '1.0.0'


def eligible_unit(adapter, serial_number, stage, station):
    if stage not in ('IST', 'SAT') or not station:
        raise SFCSError('Valid IST/SAT stage and station required')
    unit = adapter.get_unit(serial_number)
    if unit.get('serial_number') != serial_number or not unit.get('part_number'):
        raise SFCSError('Invalid unit identity')
    if unit.get('stage') != stage:
        raise SFCSError('Manufacturing stage mismatch')
    verdict = adapter.validate_station(serial_number, station)
    if verdict.get('eligible') is not True:
        raise SFCSError('Station eligibility rejected')
    return unit


def execute(config, connection, adapter, station, store, retest_of=None):
    sn, stage = config['server']['serial_number'], config['server']['test_stage']
    run_id = str(uuid4())
    started = datetime.now(timezone.utc).isoformat()
    unit = eligible_unit(adapter, sn, stage, station)
    if retest_of:
        # Include pending local runs; a network outage must not erase lineage.
        history = store.history(sn)
        if not any(r['run_id'] == retest_of and r['test_stage'] == stage
                   and r['station'] == station for r in history):
            raise SFCSError('Retest parent must be a local run for this unit, stage and station')
    report = validate(deepcopy(config), connection)
    result = {
        'schema_version': 1, 'run_id': run_id, 'server_sn': sn,
        'server_pn': unit['part_number'], 'test_stage': stage, 'station': station,
        'test_name': 'DIMM_HEALTH_VALIDATION', 'test_version': TEST_VERSION,
        'started_at': started, 'timestamp': datetime.now(timezone.utc).isoformat(),
        'execution_type': 'RETEST' if retest_of else 'INITIAL', 'retest_of': retest_of,
        'result': 'PASS' if report['overall_result'] == 'PASS' else 'FAIL',
        'diagnostic_result': report['overall_result'],
        'failure_information': report['failures'] + report['unavailable_data'] + report['warnings'],
        'dimm_health': report,
    }
    store.save(result)
    return result
