import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".agents/skills/pwc-cron-health/scripts/check_inventory.py"
)
spec = importlib.util.spec_from_file_location("cron_skill_inventory", SCRIPT)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def test_combined_probe_heading_covers_both_jobs(tmp_path):
    reference = tmp_path / "probes.md"
    reference.write_text("## `first` and `second`\n\nMention `not_a_job` in prose.\n")
    assert inventory.probe_ids(reference) == ["first", "second"]


def test_registered_jobs_have_probe_sections():
    jobs = inventory.registry_jobs(SCRIPT.parents[4])
    gaps = inventory.probe_reference_gaps(
        [job["id"] for job in jobs], inventory.probe_ids()
    )
    assert gaps == {"probe_missing": [], "probe_extra": [], "probe_duplicates": []}
