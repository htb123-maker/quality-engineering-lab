"""Make the local SUT module importable for contract-level unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUT_DIRECTORY = PROJECT_ROOT / "apps" / "compose" / "api"

if str(SUT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SUT_DIRECTORY))
