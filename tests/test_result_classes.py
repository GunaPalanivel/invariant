"""Import errors and timeouts are not detections."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.models import ExecutionResultClass


def classify_execution_error(exc: BaseException) -> ExecutionResultClass:
    if isinstance(exc, (ImportError, ModuleNotFoundError, SyntaxError)):
        return ExecutionResultClass.INVALID_TEST
    if isinstance(exc, TimeoutError):
        return ExecutionResultClass.INFRASTRUCTURE_FAILURE
    return ExecutionResultClass.INFRASTRUCTURE_FAILURE


class TestResultClasses(unittest.TestCase):
    def test_import_error_is_invalid_test_not_detection(self):
        try:
            import invariant._does_not_exist_mod  # type: ignore
        except ImportError as exc:
            cls = classify_execution_error(exc)
        self.assertEqual(cls, ExecutionResultClass.INVALID_TEST)
        self.assertNotEqual(cls, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_timeout_is_infrastructure_failure(self):
        cls = classify_execution_error(TimeoutError("ci timed out"))
        self.assertEqual(cls, ExecutionResultClass.INFRASTRUCTURE_FAILURE)
        self.assertNotEqual(cls, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_fixture_file_import_error(self):
        fixture = ROOT / "tests" / "fixtures" / "broken_import.py"
        self.assertIn("definitely_not_a_real_module_for_invariant_invalid_test", fixture.read_text(encoding="utf-8"))
        cls = classify_execution_error(
            ModuleNotFoundError("definitely_not_a_real_module_for_invariant_invalid_test")
        )
        self.assertEqual(cls, ExecutionResultClass.INVALID_TEST)
