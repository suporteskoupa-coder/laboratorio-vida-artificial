E.L.B.E.R.R. v0.9 — SELF_TEST storage helper import fix

This patch changes ONLY self_test.py.

Observed failure:
  [90/120] ...
  NameError: name 'read_json' is not defined

Cause:
The new Digital Ecology tests use supervisor.storage.read_json/write_json,
but self_test.py did not import those helpers.

Fix:
  from supervisor.storage import read_json, write_json

Both helpers are imported now because later ecology tests also use write_json.

Install:
1. Extract this ZIP into ELLBERR_Lab_v0.9_DIGITAL_ECOLOGY.
2. Replace self_test.py.
3. Run SELF_TEST.bat again from the beginning.

Expected final result:
  ALL 120 TESTS PASSED

No runtime, ecology, model, state, containment, or evolution code is changed.
