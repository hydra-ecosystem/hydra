# AGENTS.md

Repo-specific directives for coding agents working in this project.

## Behavioral defaults

These guidelines are intended to reduce common LLM coding mistakes. Apply them
alongside the repo-specific rules below. They bias toward caution over speed,
and for truly trivial tasks you may use judgment.

### Think before coding

- Do not assume.
- Do not hide confusion.
- Surface tradeoffs.
- State assumptions explicitly when they matter to the implementation.
- If multiple reasonable interpretations exist, present them instead of silently picking one.
- If a simpler approach exists, say so.
- Push back when warranted.
- If something material is unclear or risky, stop, name what is confusing, and ask instead of guessing.

### Simplicity first

- Solve the requested problem with the minimum code necessary.
- No features beyond what was asked.
- No abstractions for single-use code.
- No flexibility or configurability that was not requested.
- No error handling for scenarios that are effectively impossible in context.
- If a solution feels overbuilt for the task, simplify it before considering it done.
- If you write 200 lines and the same result could be achieved in 50, rewrite it.
- Ask: would a senior engineer say this is overcomplicated? If yes, simplify.

### Surgical changes

- Touch only what is needed for the request.
- Do not "clean up" adjacent code, comments, formatting, or structure unless the change requires it.
- Match the existing style and patterns of the codebase unless the user asks for a broader refactor.
- If you notice unrelated dead code or issues nearby, mention them instead of fixing them opportunistically.
- Remove imports, variables, functions, or other artifacts that your change makes unused.
- Do not delete unrelated pre-existing dead code unless asked.
- Every changed line should trace directly to the user's request.

### Prefer focused tools over ad hoc shell

Use repository-aware file inspection and edit tools for file operations. Reserve
shell commands for things that genuinely require shell execution: `sl`
(Sapling) commands, `gh`, dependency installation, or `nox` / `pytest` /
`python` for tests, linting, and other repo tooling.

- Use `rg` for text search and `rg --files` for file discovery.
- Avoid inline Python snippets (`python -c ...`) when a dedicated tool or standard CLI utility is sufficient.
- Use structured tools such as `jq` to parse JSON shell output instead of piping to Python.

### Goal-driven execution

- Translate requests into concrete success criteria that can be verified.
- For bug fixes, prefer reproducing the issue with a test or other reliable check before fixing it.
- For refactors, prefer checks that demonstrate behavior is preserved before and after.
- For multi-step tasks, keep a brief plan in mind and verify each step before calling the work complete.
- Favor specific goals over vague ones:
  - "Add validation" -> write tests for invalid inputs, then make them pass.
  - "Fix the bug" -> reproduce it with a test or reliable check, then make it pass.
  - "Refactor X" -> verify behavior before and after the refactor.

## Documentation map

- Website and docs source: [`website/`](./website/)
- Current docs: [`website/docs/`](./website/docs/)
- Development docs: [`website/docs/development/`](./website/docs/development/)
- Plugin docs: [`website/docs/plugins/`](./website/docs/plugins/)
- Versioned docs: [`website/versioned_docs/`](./website/versioned_docs/)

## Reproduction files

When asked to create a reproduction for an issue, place files under
`temp/repro/`:

- Single-file repro: `temp/repro/<issue_number>.py`
- Multi-file repro: `temp/repro/<issue_number>/`

## Scratch files

Place low-value, disposable temporary files under `temp/scratch/`. Its contents
may be cleared weekly without review. Do not store reproductions, resumable
workflow state, unique evidence, or drafts awaiting use there.

## Stop and ask

- If a tracked repo file appears unexpectedly renamed, moved, regenerated, deleted, or otherwise changed, stop and ask before reverting, recreating, reclassifying, or staging over that change.
- Do not change supported Python versions, CI matrices, packaging metadata, release automation, or workflow triggers unless the request explicitly includes that scope.

## Verification

- For any new or changed functionality, test it in two layers when practical:
  - run relevant focused tests with `pytest path/to/test_file.py`
  - run the relevant `nox` session to ensure no regressions
- Hydra core tests run with `pytest` from the repository root.
- Plugin tests run from the plugin directory after installing the plugin, or via `nox -s test_plugins`.
- Use `PLUGINS=<plugin_dir_name>` with `nox` when validating one plugin.
- If the broader suite disagrees with focused tests, trust the broader result and do not call the change verified.
- If live verification is blocked by the current environment, request escalation if that would unblock it. If not, stop and ask for guidance.

## Linting and formatting

Run linting through `nox -s lint` when validating broad changes. It covers Hydra
core and all plugins; use `nox -t lint-core` or `nox -t lint-plugins` for a subset.
The repo's lint sessions include formatting, import sorting, type checks, style,
YAML linting, and security checks.

For focused local checks, use the same tools the noxfile runs:

- `ruff format .` / `ruff format --check .`
- `ruff check .` / `ruff check --fix .`
- `pyrefly check --config pyproject.toml`
- `yamllint --strict .`
- `bandit --exclude ./.nox/** -ll -r .`

## Environment and hooks

- Run commands from the repo-local `.venv` by default. Prefer
  `.venv/bin/python`, `.venv/bin/pip`, `.venv/bin/pytest`, and
  `.venv/bin/nox` when those entry points exist.
- If `.venv` is missing and dependency installation is in scope, create it
  with `python -m venv .venv`, then install `requirements/dev.txt` and the
  editable checkout into that environment.
- Use a separate environment only when testing a specific supported Python
  version or reproducing an environment-specific issue.
- When validating contributor setup, shell initialization, or hook behavior, verify it from the same environment a developer would actually use, such as a normal shell session or `sl commit`, not only from a temporary sandbox-only environment.
- Prefer hooks that do not depend on nontrivial user-environment tooling.
- If an environment override is required for one command, explain why it must be part of that same process invocation.
- If a small system tool would materially simplify the workflow, it is fine to suggest it or ask the user to install it.

## Source control and PRs

Use the VCS tooling that matches the current checkout. Some Hydra worktrees are
Sapling (`sl`) checkouts, while others may be plain Git clones.

- Prefer the checkout's native tool for local operations such as status, log, diff, commit, amend, and stack inspection.
- In a Sapling checkout, use `sl` for normal local VCS operations.
- Keep escalated VCS commands minimal and single-purpose.
- Do not bundle staging, environment bootstrapping, dependency installation, and commit creation into one escalated shell command unless there is no practical alternative.
- If a VCS operation requires escalation, ask only for the specific action that needs it.
- Do not force-push, submit, or otherwise update a remote branch unless the user explicitly asks for that outward action.
- Before using low-level fallback commands, such as `git --git-dir .sl/store/git` in a Sapling checkout, stop and explain why the normal workflow is not sufficient.

## Release and news fragments

- Do not commit, push, merge, publish, or otherwise send changes outside the local working tree unless the user explicitly asks for that outward action.
- If a change alters release automation, workflow triggers, deployment behavior, or other externally visible project mechanics, require an explicit user review checkpoint before any commit, push, merge, publish, or deployment action.
- All non-trivial product-user-visible changes should have a news fragment.
- Core Hydra fragments go under `news/`; plugin-specific fragments go under the relevant plugin's `news/` directory.
- Fragment filenames follow the pattern `<issue_or_pr_number>.<category>`.
- Supported categories are `api_change`, `feature`, `bugfix`, `docs`, `config`, and `maintenance`.
- Fragment text must be concise, user-facing, sentence case, and preferably under 80 characters.
- Developer-only tooling, repo maintenance, and CI-only changes do not need a fragment unless they change the shipped product experience.
- The user handles releases. Do not edit version numbers, create release files, assemble release notes, or otherwise perform release-cut steps unless explicitly asked.
- The documented release process lives in [`website/docs/development/release.md`](./website/docs/development/release.md). Do not improvise a manual release flow.

## Reviews

- When asked to review a commit, pull request, or diff, cover correctness, completeness, documentation, and internal consistency.
- Verify that each product-user-visible change includes an appropriate news fragment and that the fragment matches the implementation and docs.
