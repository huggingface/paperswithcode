# Security Policy

## Reporting a vulnerability

Please report security issues privately. Do not open a public GitHub issue,
pull request, or discussion for a suspected vulnerability.

- Email [security@huggingface.co](mailto:security@huggingface.co), where the
  Hugging Face security team will review the report and recommend next steps.
- Or use GitHub's **Report a vulnerability** button on this repository's
  **Security** tab to open a private security advisory.

Include what you can of:

- the affected component (website, public API, chat, MCP server, deployment
  tooling, or a specific file and line);
- steps to reproduce, or a proof of concept;
- the impact you believe it has;
- whether you think it is already being exploited.

We will acknowledge your report, keep you updated as we investigate, and credit
you in the fix if you wish.

## Scope

In scope:

- the source code in this repository;
- the hosted deployment at <https://paperswithcode.co> and its API, chat, and
  MCP endpoints.

Out of scope:

- volumetric denial of service or load testing;
- social engineering of maintainers or users;
- issues that require an already compromised account, device, or host;
- reports from automated scanners without a demonstrated, exploitable impact;
- vulnerabilities in third-party services or dependencies that are not caused
  by how this project uses them (please report those upstream).

## Testing against paperswithcode.co

Use your own account and data. Do not access, modify, or delete other users'
data, chats, or artifacts; do not degrade the service for others; and stop and
report as soon as you have shown an issue exists. Good-faith research that
follows these rules is welcome.

## Supported versions

Only the current `main` branch, which is what paperswithcode.co runs, receives
security fixes.
