import os as _os
# Redirect __file__ so Python's unittest loader realpath check passes.
# finance/tests.py exists alongside this package; the loader discovers
# tests.py, imports finance.tests (this package), and compares __file__
# against tests.py's path. Without this redirect the check mismatches
# and raises ImportError.  Tests live in test_finance_core.py (app root)
# and test_admin_index.py (this package).
_f = _os.path.abspath(__file__)
__file__ = _os.path.normpath(_os.path.join(_os.path.dirname(_f), '..', 'tests.py'))
del _os, _f
