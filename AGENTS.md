# Repository Guidelines

## Project Structure & Module Organization

This repository is currently a design baseline for a local-first autonomous coding system; application code is not implemented yet.

- `README.md`: minimal project entry point.
- `docs/SPEC.md`: authoritative scope, architecture, invariants, and acceptance gates.
- `docs/TODO.md`: ordered implementation checklist and evidence template.
- Other `docs/*.md` files: historical architecture proposals and reviews, not normative requirements.
- `LICENSE`: Apache 2.0 license.

No source, test, or asset directories exist yet. Follow the specification when introducing them and document their actual locations.

## Build, Test, and Development Commands

No build, installation, lint, or test commands are configured. The proposed application uses Python, `uv`, and local or remote Ollama; these are design targets, not working setup instructions.

Useful checks for documentation changes:

```sh
git diff --check          # Detect whitespace errors
git diff -- docs/        # Review documentation changes
```

When adding executable code, document reproducible setup and verification commands alongside its configuration.

## Coding Style & Naming Conventions

Use descriptive Markdown headings, short paragraphs, fenced command examples, and relative links between documents. Preserve existing checklist identifiers such as `P1C-01` and specification section references.

No language formatter, linter, or indentation policy is configured yet. Establish these explicitly when introducing code. Keep proposed interfaces small and follow the deterministic, single-loop architecture in `docs/SPEC.md`.

## Testing Guidelines

No testing framework or coverage threshold exists yet. Future verification must follow the specification: reproduce bugs on the base revision, run deterministic checks, and distinguish environment failures from regressions.

Record milestone evidence using the template in `docs/TODO.md`, including revision, command, outcome, artifacts, and limitations. Check a milestone only when its acceptance criteria are satisfied.

## Commit & Pull Request Guidelines

Recent commits use short, descriptive subjects such as `Add Claude second review of revised architecture`; no mandatory prefix convention is established. Use concise, action-oriented subjects.

Pull requests should describe the change, reference affected specification sections or checklist IDs, and report verification performed. Explain scope or architecture changes and update related documents consistently. Distinguish implemented behavior from proposals and unvalidated assumptions.
