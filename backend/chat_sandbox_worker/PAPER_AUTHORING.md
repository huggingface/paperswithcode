# Private paper authoring guide

Use this guide only when trusted metadata enables paper artifacts for an
ordinary research chat. The selected model decides whether the user's request
is an explicit manuscript request.

Run `pwc-paper create --title "..."` only to create the one private project for
the current chat. It compiles a neutral standard-article scaffold and prints a
bounded receipt. For the first complete draft, research first, create only
`.tex` and `.bib` files under `/workspace/paper`, then submit the bounded
candidate with `pwc-paper draft --directory /workspace/paper --artifact-id
<artifact-id> --expected-parent-version-id <source-head-version-id>`. If
metadata already contains a project, use `pwc-paper begin-edit` to inspect its
current head, then check out its source with `pwc-paper edit-context
--directory /workspace/paper` before making a narrow change. Edit only the
checked-out files and submit them with `pwc-paper draft`: a draft replaces the
whole text source, so keep every file you did not mean to remove. The backend
exposes no arbitrary file-write API: never claim a source edit unless
`pwc-paper` reports a published version.

Run each `pwc-paper` command directly with its documented arguments. Do not
wrap it in shell syntax, chain it, pipe it, or use shell substitutions; only a
single direct invocation can produce a trusted receipt.

For an explicit repair request, run `pwc-paper repair-context --directory
/workspace/paper`, inspect the checked-out source and diagnostics, then make a
narrow source change. Submit it with `pwc-paper repair --directory
/workspace/paper --artifact-id <artifact-id> --expected-parent-version-id
<failed-id>`. The service permits at most three failed repair attempts;
intermediate failures are not paper versions.

Use `pwc` first for catalog evidence, `s2` for citation identities beyond the
catalog, and restricted `hf` only for relevant public Hub evidence. Preserve
unknown facts as TODOs. Never fabricate bibliography entries, results, or
claim-level support. The project uses pdfLaTeX, BibTeX, and natbib, and its
preamble already loads amsmath, amssymb, graphicx, booktabs, url, and hyperref.
Keep that preamble; do not add packages, shell escape, remote files, or
unsupported assets.
