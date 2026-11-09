# v2 validation record

Environment: Python 3.13.6; offline synthetic fixtures, no physical hardware.

Before commits 1–5, `python -m pytest -q` (commit 1 selected all three existing test modules) passed respectively: 61, 72, 82, 84, 97 tests. Baseline: 47 passed.

Final pre-documentation verification command: `.venv/bin/python -m pytest -q`

```text
........................................................................ [ 74%]
.........................                                                [100%]
97 passed in 0.49s
```

Each row was executed with `.venv/bin/python -m src.main --mode mock --scenario NAME`.

| Scenario | Actual result | Actual exit |
| --- | --- | --- |
| healthy | PASS | 0 |
| corrected_error | FAIL | 2 |
| uncorrected_error | FAIL | 2 |
| unavailable | UNKNOWN | 3 |
| missing_dimm | FAIL | 2 |
| sensor_unsupported | WARNING | 1 |
| sensor_critical | WARNING | 1 |
| malformed_inventory | UNKNOWN | 3 |
| incomplete_edac | UNKNOWN | 3 |

Actual retained history filenames:

- `dimm_20261103T041828873405Z_healthy_a90e8e3ea3b741e9ab59667e1835579a.json`
- `dimm_20261103T041828974232Z_corrected_error_7e45bbbb5dcc4a268966b21222838767.json`
- `dimm_20261103T041829069144Z_uncorrected_error_54e470e08b024b53b7d29a47b764eaf0.json`
- `dimm_20261103T041829178401Z_unavailable_9f41d2f5fe2f429a9d9f6b5e0c827732.json`
- `dimm_20261103T041829290181Z_missing_dimm_5d3d35cad34f4b779e4fb6c5b6e133e4.json`
- `dimm_20261103T041829399932Z_sensor_unsupported_1cccd31a0dc5441691af9da216e93e83.json`
- `dimm_20261103T041829501809Z_sensor_critical_3bff9182ee364f1db0e0e07912e9880f.json`
- `dimm_20261103T041829606158Z_malformed_inventory_ae47398b88cf458c96253af5518d2399.json`
- `dimm_20261103T041829711156Z_incomplete_edac_d96d35e7c9d248569ffcdf0015d93e41.json`

All original scenario expectations are preserved. Additional sensor critical scenario defaults to WARNING; opt-in FAIL policy is covered by unit tests. Subprocess failure cases use mocks; no network/root/hardware needed for tests. Real Mode remains implemented but not physically validated. Input planning documents are intentionally untracked. No changes pushed.

# SFCS / MES integration verification

Environment: Python 3.12; synthetic fixtures and loopback HTTP only.
Baseline before changes: 97 passed. Final command: `.venv/bin/python -m pytest -q`.

```text
129 passed in 6.81s
```

32 new parametrized cases cover diagnostic outcomes and submission, eligibility gates,
offline retry and database reopen, crash recovery before enqueue, idempotency/conflicts,
multiple retests, REST headers and contract, HTTP/connection/timeout failures,
malformed JSON and acknowledgements, and manufacturing CLI execution/history.
All original 97 tests pass unchanged.

Executed the documented manufacturing Mock run command successfully: PASS, upload
sent, unique Run ID returned. The subsequent retry command returned an empty queue.
No physical hardware, proprietary data or real manufacturing service was used.
