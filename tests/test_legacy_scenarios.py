"""Collect the historical scripts without importing their top-level side effects."""

import os

import pytest

from tools.legacy_test_check import PRIVATE_FIXTURES, SAFE, run_suite

pytestmark = [pytest.mark.oracle, pytest.mark.legacy]


@pytest.mark.parametrize("scenario", (*SAFE, *PRIVATE_FIXTURES))
def test_legacy_scenario(scenario, tmp_path):
    if scenario in PRIVATE_FIXTURES:
        pytest.skip(
            "Private biometric fixtures are unavailable and were not accessed; this is not a Docker dependency."
        )
    if os.getenv("AMRS_TEST_ORACLE") != "1":
        pytest.skip("Use the disposable native Oracle runner.")
    result = run_suite(
        dict(os.environ),
        tmp_path / "result.json",
        names=(scenario,),
        include_private=False,
    )[0]
    assert result["status"] == "passed", result["detail"]
