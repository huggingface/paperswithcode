-- Separate single-pass code generation from coding agents (2026-10-20).
--
-- SciCode, MultiPL-E, CRUX-O and Design2Code give the model one prompt and
-- grade one answer, with no repository, terminal or tool loop, so their
-- coding-agents leaderboards move to code-generation, following HumanEval,
-- MBPP and LiveCodeBench in move_code_and_registration_benchmarks_to_new_tasks.sql.
-- Leaderboards are keyed by (task, dataset), so the task link, the leaderboard
-- metrics, the evaluation rows and the badge tombstones move together.
-- The coding-agents description now states the boundary explicitly.

UPDATE tasks
SET
    description = 'Coding agents are LLM-driven systems that complete software engineering tasks over many steps inside a real repository or terminal: they explore the codebase, edit files, run commands and tests, read the feedback and iterate until the task is done. Their benchmarks provide an environment rather than a single prompt, such as resolving real GitHub issues in SWE-bench, finishing command-line tasks in Terminal-Bench, or building whole projects in ProgramBench and NL2Repo, and score whether the final state passes hidden tests. Results depend on both the model and the agent harness, for example Claude Code, Codex CLI or OpenHands. Benchmarks where a model writes a single function or program in one pass without tools, such as HumanEval, MBPP and LiveCodeBench, are tracked under [code generation](/tasks/code-generation).',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'coding-agents';

CREATE TEMP TABLE single_pass_code_moves ON COMMIT DROP AS
SELECT d.id AS dataset_id, old_t.id AS old_task_id, new_t.id AS new_task_id, new_t.slug AS new_task_slug
FROM (
    VALUES ('scicode'), ('multipl-e'), ('crux-o'), ('design2code')
) AS v(dataset_slug)
JOIN datasets d ON d.slug = v.dataset_slug
JOIN tasks old_t ON old_t.slug = 'coding-agents'
JOIN tasks new_t ON new_t.slug = 'code-generation';

INSERT INTO task_datasets (task_id, dataset_id, created_at, updated_at, supports_harness)
SELECT m.new_task_id, td.dataset_id, td.created_at, now(), td.supports_harness
FROM task_datasets td
JOIN single_pass_code_moves m ON m.dataset_id = td.dataset_id AND m.old_task_id = td.task_id
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id, created_at)
SELECT m.new_task_id, tdm.dataset_id, tdm.metric_id, tdm.created_at
FROM task_dataset_metrics tdm
JOIN single_pass_code_moves m ON m.dataset_id = tdm.dataset_id AND m.old_task_id = tdm.task_id
ON CONFLICT DO NOTHING;

UPDATE evaluations e
SET task_id = m.new_task_id, updated_at = now()
FROM single_pass_code_moves m
WHERE e.dataset_id = m.dataset_id AND e.task_id = m.old_task_id;

UPDATE evaluation_badge_tombstones t
SET task_id = m.new_task_id, task_slug = m.new_task_slug
FROM single_pass_code_moves m
WHERE t.dataset_id = m.dataset_id AND t.task_id = m.old_task_id;

DELETE FROM task_dataset_metrics tdm
USING single_pass_code_moves m
WHERE tdm.dataset_id = m.dataset_id AND tdm.task_id = m.old_task_id;

DELETE FROM task_datasets td
USING single_pass_code_moves m
WHERE td.dataset_id = m.dataset_id AND td.task_id = m.old_task_id;

-- Papers with a result on a moved leaderboard belong to code generation.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT e.paper_id, m.new_task_id, 'manual'
FROM evaluations e
JOIN single_pass_code_moves m ON m.dataset_id = e.dataset_id AND m.new_task_id = e.task_id
ON CONFLICT DO NOTHING;
