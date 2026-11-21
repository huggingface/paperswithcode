# ADR 0004: GitHub evaluation outreach

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Eval outreach comments on an existing HF release issue

When the outreach account already opened a Hugging Face release request on a repository, the verify-evals message is posted as a comment on that thread instead of a second issue. This avoids spamming maintainers with two issues from the same account.

Code: `backend/services/github_eval_outreach_service.py::GithubEvalOutreach.process`

## Eval outreach excludes evaluations the authors added themselves

GitHub eval outreach announces only evaluations PwC curated. Rows that are external or were contributed by the paper's own authors are excluded from the candidate query, since there is nothing for PwC to announce to authors about their own submissions.

Code: `backend/services/github_eval_outreach_catalog.py::candidates`

## Eval outreach recognizes 'Release X on Hugging Face' issues

The community-science paper-parsing pipeline opens 'Release X on Hugging Face' artifact-release issues from the same GitHub account used for eval outreach. RELEASE_ISSUE_TITLE matches those titles so eval outreach can recognize them and post the verify-evals message as a comment there instead of opening a second issue on the repository.

Code: `backend/services/github_eval_outreach_body.py`

## GitHub issue searches are paced at two seconds

GitHub allows 30 authenticated search requests per minute. The eval outreach job sleeps two seconds before every search call so that a full repository pass stays under that cap instead of tripping secondary rate limits.

Code: `backend/services/github_eval_outreach_service.py::SEARCH_PACE_SECONDS`

## Outreach coverage uses search instead of listing repository issues

GitHub's repository-wide issue list rejects page-based pagination beyond a limit on large repositories with HTTP 422. Coverage detection therefore uses the search API (and creator-filtered listings) rather than walking every issue in the repository.

Code: `backend/services/github_eval_outreach_service.py::site_issues`

## Outreach issue coverage is found by site-name phrase search

GitHub issue search ignores URL paths, so searching for a paperswithcode.co link does not find earlier outreach issues. Coverage detection searches for the site-name phrase that every outreach issue carries instead (seen on GAIR-NLP/ASI-Evolve#12). Switching back to URL-based queries would miss prior contact and post duplicates.

Code: `backend/services/github_eval_outreach_service.py::site_issues`

## Outreach issues are found by the site name, not paper URLs

GitHub issue search does not match URL paths or arXiv ids inside issue bodies. Existing Papers with Code outreach issues are therefore located by searching for the literal "Papers with Code" that every such issue carries, and then filtered locally.

Code: `backend/services/github_issue_publish_service.py::SITE_ISSUE_QUERY`

## Outreach login identifies already-contacted repositories

An open issue authored by github_outreach_login marks a repository as already contacted for evaluation outreach, and the outreach token must belong to that same login. A token for a different account would create issues the dedup check does not recognise, causing repeat outreach.

Code: `backend/config.py::Settings.github_outreach_login`

## Outreach posts are checkpointed before the POST and never blindly retried

The job writes a pending record to its state store before sending the GitHub POST, so a crash mid-request leaves evidence of a possible post. Definitive 4xx validation or permission rejections clear the pending record; any uncertain outcome keeps it and re-raises without retrying. This gives at-most-once issue creation instead of duplicate issues.

When a GitHub POST fails with an uncertain outcome, the pre-POST pending checkpoint is retained and the error re-raised; the job never retries blindly, because the issue may already exist.

Code: `backend/services/github_eval_outreach_service.py::GithubEvalOutreach.process`

## Outreach prioritises new evaluations but reserves one slot for the oldest repo

Each outreach pass checks a bounded number of repositories. Newly settled evaluations are ordered before routine rechecks, but the first check is reserved for the oldest eligible repository so long-waiting repositories are never starved by a steady stream of new work.

Code: `backend/services/github_eval_outreach_service.py::GithubEvalOutreach.run`

## Outreach rechecks catalog and author gates immediately before posting

Drafting an outreach message can be slow. Just before posting, the job re-reads committed catalog state and the open-issue author gate; if the paper group changed or an issue was opened meanwhile, it defers to a later pass. This prevents posting drafts that cite removed links or evaluations, or opening a duplicate issue.

Drafting can be slow, so the open-issue author gate is re-queried immediately before the write. An issue opened during drafting blocks the post rather than producing a duplicate.

Code: `backend/services/github_eval_outreach_service.py::GithubEvalOutreach.process`
