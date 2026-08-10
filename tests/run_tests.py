# -*- coding: utf-8 -*-
"""
Unified Test Runner for GEMMA QGIS Plugin.
Discovers and executes all unit and integration tests under tests/ directory.

Usage:
  python tests/run_tests.py
"""

import sys
import unittest
import time
from pathlib import Path

# Add project root to python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()


def run_all_tests():
    start_time = time.time()
    loader = unittest.TestLoader()
    tests_dir = PROJECT_ROOT / "tests"

    print("======================================================================")
    print(" GEMMA QGIS Plugin — Test Suite Runner")
    print("======================================================================")
    print(f"Discovering tests under: {tests_dir}")

    suite = loader.discover(start_dir=str(tests_dir), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    duration = time.time() - start_time
    print("======================================================================")
    print(f"Tests run: {result.testsRun}")
    print(f"Errors: {len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"Elapsed time: {duration:.3f}s")
    print("======================================================================")

    passed = result.testsRun - len(result.errors) - len(result.failures) - len(result.skipped)
    summary = {
        "tests_run": result.testsRun,
        "passed": passed,
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skipped": len(result.skipped),
        "elapsed_seconds": round(duration, 3),
        "success": result.wasSuccessful()
    }
    
    import json
    json_path = PROJECT_ROOT / "tests" / "test_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    if result.wasSuccessful():
        print("[STATUS] PASSED — All unit & integration tests succeeded.")
        return True
    else:
        print("[STATUS] FAILED — Test suite reported errors or failures.")
        return False


def main():
    success = run_all_tests()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
