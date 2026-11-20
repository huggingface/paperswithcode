# ADR 0012: Conferences and AI deadlines

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Agent budget limits are terminal; only turn limits get a follow-up

A Claude Agent SDK error_max_turns result triggers one no-tools follow-up that answers from what was already seen. Other error_max* results (budget, structured-output retries) are terminal and recorded as a limit status, because retrying or following up would spend past the configured cap.

Code: `backend/services/conference_deadline_agent.py::_consume`

## Biennial conference series are listed explicitly

ICCV and ECCV run every other year, and most series have too little recorded history to infer cadence automatically. They are hardcoded as biennial so expected-next-edition logic does not flag a missing edition in off years.

Code: `backend/services/conference_deadline_service.py::BIENNIAL_SERIES`

## Conference browse index lists only editions with imported papers

Conference rows also exist for deadline tracking before proceedings are imported. The browse-papers-by-conference index filters with HAVING count(papers) > 0 so those deadline-only rows do not appear as empty conference pages.

Code: `backend/services/conference_service.py::ConferenceService.get_conferences`

## Conference deadline research runs on HF Jobs, writes on the VPS

AI conference deadline research runs off-box on Hugging Face Jobs with the Claude Agent SDK; only validated, bounded database writes happen on the VPS, keeping heavy agent work off the 16 GB host. The Jobs namespace and token fall back to the codex_jobs credentials when the conference-specific ones are unset.

Code: `backend/config.py::Settings.conference_deadlines_hf_namespace`

## Conference snapshots query deadlines directly, not via the relationship

Deadline writers remove rows with bulk deletes, which bypass the SQLAlchemy session and leave a loaded Conference.deadlines relationship stale. Snapshots therefore query the deadline table directly to reflect the true state.

Code: `backend/services/conference_deadline_service.py::conference_snapshot`

## Deadline aggregation never falls back to an unchecked retrieval

If the aggregation agent produces no structured output, the series fails with an error instead of applying one retrieval agent's proposal. A misconfigured aggregation model must fail loudly rather than publish data that no majority vote verified.

Code: `backend/services/conference_deadline_agent.py::research_series`

## Deadline import owns tier, tags and location but only fills other conference metadata

Conference rows are shared between the deadlines feature and curated proceedings pages. The deadline import always overwrites the columns it owns (tier, tags, country, city), but only fills url, venue, location and dates when they are empty so curated proceedings data such as descriptions, hero images and hf_url is never clobbered.

Code: `backend/services/conference_deadline_service.py::upsert_yaml_conference`

## Deadline retrieval without output is an error, not a no-op

When every retrieval agent fails to produce structured output (SDK errors or silent exits), the pipeline reports an error instead of concluding that no deadline update is needed. Treating silence as no change would hide broken sweeps and leave stale deadlines marked verified.

Code: `backend/services/conference_deadline_agent.py::retrieval_short_circuit`

## Deadline shifts over 120 days need human review

The deadline research agent may move existing deadlines, but a move of more than 120 days is far more likely a wrong year or edition than a real extension. Such changes are rejected from automatic application and left for a human.

Code: `backend/services/conference_deadline_service.py::MAX_DEADLINE_SHIFT`

## Deadline sweep pins Agent SDK 0.2.165 for Opus 5.5 support

The conference deadline sweep pins Claude Agent SDK 0.2.165 because it bundles Claude Code 2.1.294, and claude-opus-5-5 requires Claude Code 2.1.280 or newer. Downgrading the SDK below a version bundling 2.1.280 breaks the aggregation model.

Code: `backend/config.py::Settings.conference_deadlines_sdk_version`

## Deadline sweeps require claude-agent-sdk 0.2.165 or newer

The conference-deadline sweep aggregates with claude-opus-5-5, which needs a bundled Claude Code of at least 2.1.280. claude-agent-sdk 0.2.165 bundles Claude Code 2.1.294 (0.2.115 bundled 2.1.206), so conference_deadlines_sdk_version must stay at or above 0.2.165.

Code: `backend/tests/test_conference_deadline_service.py::test_job_command_runs_the_worker_as_a_non_root_user`

## Edition deadlines must fall from the prior January to the next July

Submissions can open up to a year before an edition and camera-ready or other post-conference deadlines can fall early in the following year. Proposed deadlines for edition year Y are accepted from 1 Jan Y-1 to 1 Jul Y+1, each widened by one day so AoE and UTC+14 times on boundary days are not rejected.

Code: `backend/services/conference_deadline_service.py::_plan_deadlines`

## New editions may be created from official dates alone

An agent may create a new conference edition with no deadlines as long as official conference dates are known. Such editions appear on /ai-deadlines as 'deadlines TBA' until a later sweep adds deadlines; an edition with neither is rejected.

Code: `backend/services/conference_deadline_service.py::plan_edition_change`

## One failing conference series does not end the deadline sweep

Each conference series is researched inside its own exception boundary so a single broken series is recorded as an error result and the sweep continues with the next one. Systemic failure is instead detected by the consecutive aggregation failure counter.

Code: `backend/services/conference_deadline_agent.py::main_async`

## Repeated aggregation failures abort the sweep without DONE

After MAX_CONSECUTIVE_AGGREGATION_FAILURES consecutive aggregation failures the sweep assumes a systemic model, CLI or credential problem and exits to stop paying for retrieval. It omits the DONE marker, which is how the VPS side records the sweep as failed.

Code: `backend/services/conference_deadline_agent.py::main_async`

## Sweeps whose aggregation failed everywhere are not fresh

A deadline sweep in which aggregation failed (error, timeout or crash, for example an aggregation model the bundled CLI cannot run) and no majority vote succeeded has verified nothing. Such a sweep is never recorded as a fresh completion, so freshness monitoring keeps flagging the series.

Code: `backend/services/conference_deadline_sweep_service.py::ConferenceDeadlineSweeps.collect_one`

## Sweeps without a recorded HF Job id fail after one hour

A sweep ledger row is inserted before the Hugging Face Job is launched, so a crash between the insert and run_job returning leaves a row with no hf_job_id. Collection treats such rows as failed once they are more than an hour old instead of waiting on them forever.

Code: `backend/services/conference_deadline_sweep_service.py::ConferenceDeadlineSweeps.collect_one`

## UTC+12 deadline timezones from agents are rejected as ambiguous

Research agents frequently write UTC+12 when they mean Anywhere on Earth (UTC-12). Agent-supplied timezones starting with UTC+12 or GMT+12 are rejected with a message to write AoE; a genuine UTC+12 deadline must be entered by a human.

Code: `backend/services/conference_deadline_service.py::canonical_timezone`

## Unexpected series errors count against the aggregation streak

An exception escaping research_series is recorded with aggregation_failed set. This prevents it from resetting the consecutive aggregation failure streak and from making the sweep look verified.

Code: `backend/services/conference_deadline_agent.py::main_async`
