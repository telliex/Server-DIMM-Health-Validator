"""Station gating and hardware execution orchestration."""
from . import SFCSError
from ..dimm_validator import validate


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


def execute(config, connection, adapter, station):
    eligible_unit(adapter, config['server']['serial_number'], config['server']['test_stage'], station)
    return validate(config, connection)
