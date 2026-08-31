from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/check_inventory.py"
SPEC = spec_from_file_location("check_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_inventory = module_from_spec(SPEC)
SPEC.loader.exec_module(check_inventory)


def test_probe_reference_gaps_report_missing_and_duplicate_ids():
    result = check_inventory.probe_reference_gaps(
        ["sync_mmeb_v2", "sync_open_asr"],
        ["sync_open_asr", "sync_open_asr"],
    )

    assert result == {
        "probe_missing": ["sync_mmeb_v2"],
        "probe_extra": [],
        "probe_duplicates": ["sync_open_asr"],
    }
