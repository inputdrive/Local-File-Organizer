---
name: repo-quality-gate
user-invocable: true
description: "Use when: you need static and dynamic code analysis on a repository, before a commit, or for an on-demand repo review. Run a fast quality gate: dependency check, static linting, unit/integration tests, build validation, and a targeted review for correctness, security, and maintainability."
---

# Repo Quality Gate

## Purpose

This skill creates a repeatable code-quality review for any repository before a commit or on-demand review request. It combines static analysis, runtime validation, and manual code review into one workflow so the agent can detect issues early without relying on a single tool.

Use this when the user asks for:
- a code review
- a repo audit
- pre-commit validation
- static analysis and runtime verification
- quality gate before merge or commit
- find issues before shipping changes

## Workflow

### 1. Establish the repo baseline

- Identify the project's root and relevant language/framework.
- Check for existing configs first: package manifests, test runners, linters, build systems, CI files.
- Prefer repo-native tools over generic ones.
- If tooling is missing, use the lightest effective toolchain for that repo.

Completion check:
- You know the project language, package manager, and validation commands.
- You know which files are likely in scope.

### 2. Run static analysis first

Run the project’s existing static checks if present. If not present, use the best lightweight standard for the repo.

Common examples:
- Python: `ruff`, `pyright`, `mypy`, `bandit`, `pylint`
- JavaScript/TypeScript: `eslint`, `tsc --noEmit`, `biome`, `oxlint`
- Go: `gofmt`, `go vet`, `staticcheck`
- Rust: `cargo clippy`
- Java/Kotlin: `gradlew check` or `mvn test`

Look for:
- unused imports/variables
- undefined or shadowed symbols
- type mismatches
- security-sensitive patterns
- obvious dead code
- formatting and lint regressions

Completion check:
- Static analysis output is reviewed and triaged.
- The agent distinguishes blocking issues from low-priority warnings.

### 3. Run the smallest relevant dynamic validation

After static checks, run the narrowest test/build command that checks changed behavior.

Prefer:
- changed-file tests
- focused unit tests
- a build or compile step
- smoke tests for entrypoints
- a minimal reproduction for the bug/fix

Avoid broad suites unless the repo is small or the request explicitly calls for full validation.

Completion check:
- The command executed successfully or a failing case is clearly identified.
- The failure is tied to a real behavior, not a missing tooling/environment issue.

### 4. Review code paths for correctness and risk

Examine the changed files and the surrounding behavior, especially:
- file I/O and path handling
- data transformations and parsing
- unsafe external calls or subprocess execution
- secrets, credentials, or environment assumptions
- concurrency, locking, retries, and error handling
- API contracts and assumptions about response shapes
- dependency/version drift or missing install metadata

For a repo review, ask:
- What can fail in production?
- What assumptions are hidden?
- What is the failure mode if input is unexpected?
- Is the code safe for repeated runs, parallel runs, or CI environments?

Completion check:
- At least one risk review pass is performed on the changed area.
- The review result includes both code-quality and runtime-risk observations.

### 5. Create a concise gate report

Summarize findings in a short, actionable format:

- Passes: what validated successfully
- Blocking issues: must fix before merge/commit
- Warnings: non-blocking but worth addressing
- Risks: likely production or maintainability issues
- Recommended next steps: exact commands or patches

Use severity labels like:
- High: breakage, security, data loss, corrupted output, invalid runtime assumptions
- Medium: reliability or maintainability concerns
- Low: style or cleanup

### 6. Pre-commit policy

Before committing, require at least:
- repo-native static analysis pass
- targeted dynamic verification for changed behavior
- a quick risk review of modified files

If any blocking issue is found, do not recommend commit/merge until it is fixed or explicitly documented.

## Branching logic

### If the repo already has tooling
- use its configured linter, test runner, and build pipeline
- do not invent a second toolchain unless needed

### If the repo has no static analysis configured
- add the smallest practical toolchain for the repo language
- prefer one fast linter and one type checker or compile check

### If the repo is large
- prioritize changed files and impacted modules first
- run full suite only when the change is cross-cutting or risk is high

### If the repo is small
- run the broader suite and static pass to increase confidence

## Quality bar for completion

A review is complete only when:
- static analysis has been attempted or ruled out
- dynamic validation has been attempted or ruled out
- changed behavior has been checked for correctness
- risks are documented with severity and clear next steps
- the final answer makes a recommendation: pass, needs fixes, or blocked

## Example prompts

- “Run a repo-quality gate on this project before I commit.”
- “Do a static and dynamic code review of this repo and tell me what is blocking.”
- “Audit the changed files for security, reliability, and maintainability risks.”
- “Check this repo for lint, type, and test issues before merge.”
- “Give me a pre-commit review pass with only blocking issues and fixes.”

## Useful customizations to add later

- a repo-specific `pre-commit` hook configuration
- an `eslint`/`ruff` config tuned to the repo
- a `pyright` or `mypy` config for Python repos
- a CI workflow that runs lint + test + build on every push
- a custom prompt for “security-only review” or “performance-only review”
