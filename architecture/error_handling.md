# SOP: Error Handling

## Purpose

Define how errors are detected, logged, and handled across the system. Support self-healing loop: analyze error, patch tool, test fix, update SOP.

## Inputs

- Tool exit codes (non-zero).
- Exceptions in app or tools.
- Health check failures (missing env, unreachable URL).

## Outputs

- Structured log messages (timestamp, component, error message, optional traceback).
- Non-zero exit codes propagated to caller (e.g. app returns 500 or 503).
- progress.md updated with errors and fixes when SOP is updated.

## Edge Cases

- Connection timeouts: log and fail; do not retry indefinitely (single attempt or env-defined retries).
- Invalid input data: tool fails with clear message; do not write partial/corrupt output.
- Router/LLM errors: log; return safe response (e.g. route to health or generic message); do not crash app.
- Missing .tmp/ directory: create on startup (app or first tool that needs it).
- Disk full: log and exit non-zero; do not truncate existing files silently.

## Golden Rule

When a failure recurs after a fix, update this SOP and the relevant tool SOP to prevent recurrence. Log in progress.md.
