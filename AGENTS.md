# AGENTS.md

## Local collaboration rules

- Do not use Playwright CLI, browser automation, or screenshot-based visual QA by default.
- Prefer code review, type checks, builds, API checks, and lightweight DOM/content checks for routine verification.
- Use Playwright CLI or screenshots only when the user explicitly asks for visual verification, or after asking first and getting confirmation.
- After completing and verifying each feature, report the changes and verification results to the user and wait for explicit confirmation. Once confirmed, automatically commit any uncommitted work for that feature, push its feature branch, and create a ready-for-review pull request without asking again. Do not create the pull request before confirmation.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `TobeALeg/jetBao`; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The repo uses the default five triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain docs layout. See `docs/agents/domain.md`.
