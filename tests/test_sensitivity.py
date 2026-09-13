"""Author-prepared destination change moves the derived assertion target."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["INVARIANT_USE_LIVE_MODEL"] = "0"
os.environ["INVARIANT_WRITE_CONSOLE"] = "0"

from invariant.interpret import heuristic_contract, load_incident
from invariant.sensitivity import PACKET


class TestSensitivity(unittest.TestCase):
    def test_heuristic_destination_moves_to_staging(self):
        packet = load_incident(PACKET)
        contract = heuristic_contract(packet)
        self.assertEqual(contract.destination, "C-STAGING")
        self.assertNotEqual(contract.destination, "C-RELEASES")
