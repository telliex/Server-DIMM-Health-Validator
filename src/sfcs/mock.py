"""Synthetic manufacturing records and durable local result receipts."""
from copy import deepcopy
from . import SFCSError, RetryableError
from .store import ResultStore

DEFAULT_UNITS = {
    'DEMO-SERVER-001': {'serial_number': 'DEMO-SERVER-001', 'part_number': 'DEMO-PN-001',
                        'stage': 'SAT', 'stations': ['SAT-DIMM-01'], 'status': 'READY'},
    'DEMO-SERVER-002': {'serial_number': 'DEMO-SERVER-002', 'part_number': 'DEMO-PN-002',
                        'stage': 'IST', 'stations': ['IST-DIMM-01'], 'status': 'READY'},
}


class MockSFCSAdapter:
    def __init__(self, path, units=None, offline=False):
        self.store = ResultStore(path)
        self.units = deepcopy(DEFAULT_UNITS if units is None else units)
        self.offline = offline

    def _available(self):
        if self.offline:
            raise RetryableError('Mock SFCS unavailable')

    def get_unit(self, serial_number):
        self._available()
        if serial_number not in self.units:
            raise SFCSError('Unknown serial number')
        return deepcopy(self.units[serial_number])

    def validate_station(self, serial_number, station):
        unit = self.get_unit(serial_number)
        eligible = station in unit['stations'] and unit['status'] == 'READY'
        return {'eligible': eligible, 'reason': 'ready' if eligible else 'station or unit status rejected'}

    def upload_result(self, test_result):
        self._available()
        self.get_unit(test_result['server_sn'])
        self.store.save(test_result)
        return {'run_id': test_result['run_id'], 'accepted': True}

    def get_test_history(self, serial_number):
        self.get_unit(serial_number)
        return self.store.history(serial_number)
