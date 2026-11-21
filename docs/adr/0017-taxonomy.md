# ADR 0017: Tasks, methods and taxonomy linking

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## "Diagnosis" alone does not tag Healthcare without medical context

"Diagnosis" is common in medical papers but also refers to failures, software, models and reasoning. When it is the only Healthcare keyword that matched, the Healthcare tag is kept only if `has_healthcare_context` finds healthcare context in the text or title.

Code: `backend/utils/keyword_matching.py::apply_task_supersession_rules`

## A paper holds either Reinforcement Learning or Classic RL, not both

Reinforcement Learning (task 22) covers RL for LLMs and foundation models, while Classic Reinforcement Learning covers control, games, offline RL and MARL. Both share generic RL keywords, so keyword linking assigns only one of them, using LLM/foundation-model signals (`_LLM_RL_PATTERN`) to decide.

Code: `backend/utils/keyword_matching.py::_LLM_RL_PATTERN`

## Cross-type surface collisions keep one owner per type for the judge

A surface can legitimately name entities of different types, such as the GQA benchmark and Grouped-Query Attention (GQA). Instead of letting rank pick a single owner, the index keeps the best owner per other entity type and leaves the choice to the LLM judge, which disambiguates from abstract context.

Code: `backend/services/abstract_mention_service.py::build_index`

## Framework mentions match case-sensitively

Framework entities are product names (for example Browser Use) that often coincide with ordinary phrases or package spellings. Abstract linking matches them case-sensitively so 'browser-use agents' is not linked to the Browser Use framework.

Code: `backend/services/abstract_mention_service.py::_case_sensitive`

## Image classification is dropped from audio classification papers without strong IC evidence

Audio papers frequently cite ViT, ImageNet or ResNet as cross-modal pretraining baselines, which triggers the image-classification keywords. When both audio- and image-classification match, image-classification is removed unless the abstract names an explicit IC task or benchmark (CIFAR, ILSVRC, VTAB, etc.).

Code: `backend/utils/keyword_matching.py::apply_task_supersession_rules`

## Image/video task conflicts are resolved by the title's modality

Image and video task phrases often co-occur in related-work text. When a paper title names only one modality, the matching task (e.g. image-generation vs video-generation) wins over the automatic tag from the abstract's mention of the other. Titles naming both keep both; when neither is named, both are kept only with coordinated contribution/evaluation evidence, and broad edge cases are tagged manually.

Code: `backend/utils/keyword_matching.py::_MODALITY_TASK_PAIRS`

## Keyword prefilter maps İ and ı to i before casefold

The substring prefilter must accept every text that a case-insensitive regex would match. Python's `re.IGNORECASE` treats "İ" and "ı" as case variants of ASCII "i", but `str.casefold()` does not map them to "i" (they are the only such characters in Python 3.12). `fold_for_keyword_prefilter` translates them explicitly before casefolding so the prefilter never rejects a real regex match.

Code: `backend/utils/keyword_matching.py::_IGNORECASE_ONLY_FOLDS`

## Keyword regexes are cached per keyword with an unbounded lru_cache

With thousands of task keywords, relying on the `re` module's ~512-entry pattern cache recompiled every keyword pattern for every paper; on 2026-11-15 this pushed the weekly keyword linker past its 6-hour timeout. `_keyword_pattern` compiles each keyword once under an unbounded `lru_cache`.

Code: `backend/utils/keyword_matching.py::_keyword_pattern`

## Lower surface ranks win name collisions

Each matchable surface is registered with a rank: canonical NAME 0, ABBREVIATION 1, curated ALIAS 1.5, generated PLURAL 2. When two catalog entities claim the same surface, the entity holding it at the lowest rank owns it, so a real name always beats another entity's abbreviation, alias or plural.

Code: `backend/services/abstract_mention_service.py::NAME`

## Masked spans are blanked with equal-length spaces

Math, URLs and infix abbreviations are masked out of abstracts before matching by replacing them with the same number of spaces. Mention offsets are computed on the masked text and applied to the original abstract, so masking must never change string length.

Code: `backend/services/abstract_mention_service.py::_blank`

## Method full names add only their abbreviation as a surface

A method's full_name (e.g. a spelled-out expansion) is often a generic phrase that would cause false-positive links. Index building registers only the bracketed abbreviation from full_name as a matchable surface, while the method's own name is indexed with its long form.

Code: `backend/services/abstract_mention_service.py::build_index`

## Paper-task links record auto vs manual provenance

paper_tasks.source is 'auto' for links inserted by the keyword matcher and 'manual' for links set through the admin API or one-off scripts. The keyword rebuild may delete and re-insert auto rows but must leave manual rows untouched, so curated links survive rebuilds.

Code: `backend/models/database/papers.py::PaperTask.source`

## Related methods require at least 3 shared papers and cosine 0.05

Co-tagging alone links almost every method to generic components. A co-tagged method only counts as related when it shares at least three papers and reaches a cosine score of 0.05; below those thresholds the overlap is dominated by generic building blocks.

Code: `backend/services/method_related_service.py::MIN_SHARED_PAPERS`

## Task keyword batch retries only idempotent operations

_run_batch retries a database operation up to three times, which is safe for reads and ON CONFLICT inserts even if a commit acknowledgement was lost and the work already landed. The linker's destructive rebuild operation must never be passed through this retry helper, because replaying it after a lost acknowledgement could delete work.

Code: `backend/services/task_keyword_batches.py::_run_batch`

## Task keyword matching uses word boundaries with an optional plural s

Task keyword matching wraps each keyword in word boundaries with an optional trailing 's', so acronyms such as "NER" or "VLM" do not match inside "FINER" or "OpenCLIP", and "transformer" does not match "transformed", while plurals like "Large Language Models" still match. Compound acronyms that should tag a task (LVLMs, MLLMs) must be added as their own keywords; method matching (`find_matching_items_longest_match`) deliberately uses substring matching for case-sensitive keywords instead.

Code: `backend/utils/keyword_matching.py::find_matching_items_simple`

## Task list counts are pre-aggregated per relation

The task list returns paper, benchmark and evaluation counts. Each count is aggregated in its own subquery before joining to tasks, because joining the three relations directly would multiply rows and inflate counts. This keeps the endpoint to one bounded query with exact direct-association counts.

Code: `backend/services/task_service.py::TaskService.get_tasks`

## Tokens keep @ so metric names match only as written

The abstract mention tokenizer treats @ as part of a token, so names such as Pass@1 or pass@k form a single token. This prevents a catalog entry like Pass@1 from matching a bare 'Pass' or splitting into unrelated tokens; a separate plain tokenizer without @ exists for contexts that need it.

Code: `backend/services/abstract_mention_service.py::_TOKEN`

## methods_scanned_at NULL marks papers the references method cron has not processed

The references-based method tagging cron selects papers whose methods_scanned_at is NULL and skips any row with a timestamp. Resetting the column to NULL is how a paper is queued for a rescan; setting it marks the paper done even if no methods were linked.

Code: `backend/models/database/papers.py::Paper.methods_scanned_at`
