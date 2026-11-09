"""Manufacturing integration, independent of hardware collectors."""
from typing import Protocol


class SFCSError(Exception):
    """Safe public integration error; contains no remote response or credentials."""


class RetryableError(SFCSError):
    """Temporary transport or service failure."""


class ConflictError(SFCSError):
    """A Run ID already identifies a different payload."""


class SFCSAdapter(Protocol):
    def get_unit(self, serial_number: str) -> dict: ...
    def validate_station(self, serial_number: str, station: str) -> dict: ...
    def upload_result(self, test_result: dict) -> dict: ...
    def get_test_history(self, serial_number: str) -> list[dict]: ...
