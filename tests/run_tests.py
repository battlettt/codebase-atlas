"""Run every tests/test_*.py module without pytest and print a pass/fail count."""
import importlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from atlas_test_support import run_module_tests  # noqa: E402


def main():
    started = time.time()
    total_passed = total_failed = 0
    for filename in sorted(os.listdir(HERE)):
        if not (filename.startswith("test_") and filename.endswith(".py")):
            continue
        module = importlib.import_module(filename[:-3])
        passed, failed = run_module_tests(vars(module))
        total_passed += passed
        total_failed += failed
        print(f"{filename:32} {passed:3} passed  {failed:3} failed")
    elapsed = time.time() - started
    print(f"\nTOTAL: {total_passed} passed, {total_failed} failed in {elapsed:.1f}s")
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
