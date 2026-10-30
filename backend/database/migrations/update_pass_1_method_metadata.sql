-- Fill in the Pass@1 method's metadata and match the general pass@k form.
--
-- Pass@k has no single introducing paper we treat as its source: SPoC
-- (arXiv 1906.04908, 2019) first reported pass@k for program synthesis, and
-- Codex (arXiv 2107.03374) popularized it with the unbiased estimator that
-- benchmarks use today. source_paper_id therefore stays NULL, and the Codex
-- paper, the standard reference for how pass@k is computed, is the explainer.
--
-- "pass@1" means only this metric in ML abstracts, so abstracts always link it.

UPDATE methods
SET
    full_name = 'Pass@1',
    description = 'Pass@1 is the standard metric for code generation and other tasks with automatically checkable answers: the fraction of problems for which a model''s first sampled solution passes all unit tests. It is the k = 1 case of pass@k, the probability that at least one of k samples is correct. [SPoC](/paper/1906.04908) first reported pass@k for program synthesis, and [Codex](/paper/2107.03374) popularized it with an unbiased estimator that draws n ≥ k samples per problem, counts the c correct ones, and computes 1 − C(n−c, k) / C(n, k). Benchmarks such as HumanEval, MBPP, LiveCodeBench and SWE-bench report pass@1, and math and reasoning benchmarks have adopted it for verifiable answers, often averaged over several samples to reduce variance.',
    keywords = 'pass@1, pass@k, pass at 1, pass at k',
    introduced_year = 2019,
    source_url = 'https://paperswithcode.co/paper/2107.03374',
    source_title = 'Evaluating Large Language Models Trained on Code',
    abstract_linking = 'always',
    aliases = ARRAY['pass@k']::text[],
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'pass-1';
