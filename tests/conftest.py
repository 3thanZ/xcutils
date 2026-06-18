"""Make shared test helpers (e.g. ``fakes``) importable from any test module."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
