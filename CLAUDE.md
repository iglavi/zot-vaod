# CLAUDE.md

This file provides guidance for AI assistants (Claude and others) working in the `zot-vaod` repository.

## Repository Status

This is a **newly initialized repository** with minimal content. Only a `README.md` exists at the time this file was generated. The sections below serve as a living template — update them as the project grows.

## Project Overview

- **Repository:** zot-vaod
- **Primary author/owner:** iglavi
- **Status:** Early initialization; no source code, build system, or dependencies yet

## Directory Structure

```
zot-vaod/
├── CLAUDE.md          # This file — AI assistant guidance
└── README.md          # Project title placeholder
```

Update this tree as directories and files are added.

## Development Workflow

### Branching

- The default long-lived branch is `main` (or `master`).
- Feature work is done on short-lived branches, typically prefixed with the author or context (e.g., `feature/`, `fix/`, `claude/`).
- AI-generated branches follow the pattern `claude/<session-slug>`.

### Commits

- Write clear, imperative commit messages (e.g., `Add authentication module`, `Fix null pointer in parser`).
- Keep commits focused; avoid mixing unrelated changes.

### Pull Requests

- Open a PR against `main` for all changes.
- Include a short summary of what changed and why.

## Build & Run

_No build system has been configured yet. Update this section when one is added._

Placeholder commands (fill in when applicable):

```bash
# Install dependencies
<package-manager> install

# Run development server / main entry point
<run-command>

# Run tests
<test-command>

# Build for production
<build-command>
```

## Testing

_No test framework has been chosen yet. Update this section when tests are added._

- Document the testing framework (e.g., Jest, pytest, Go test, RSpec).
- Describe where tests live (e.g., `tests/`, `__tests__/`, co-located `*.test.ts`).
- Note any required environment setup before running tests.

## Code Conventions

_No source code exists yet. Add conventions here as the codebase takes shape._

Common things to document once relevant:
- Linter / formatter in use (ESLint, Prettier, Black, Rustfmt, etc.)
- Naming conventions (files, functions, variables, constants).
- Module/package organization patterns.
- Error-handling approach.
- Logging strategy.

## Environment & Configuration

_No configuration files or environment variables defined yet._

When added, document:
- Required environment variables and their purpose.
- Where `.env` / secret files live and how to obtain values locally.
- Any external services the project depends on.

## Key Files to Know

| File | Purpose |
|------|---------|
| `README.md` | Project title (expand with a real description) |
| `CLAUDE.md` | This file — guidance for AI assistants |

Update this table as important files are created.

## AI Assistant Notes

- **Read before editing:** Always read a file before modifying it.
- **Minimal changes:** Only change what is directly required by the task.
- **No speculative features:** Do not add features, abstractions, or configuration that was not requested.
- **Commit and push:** After completing a task, commit with a descriptive message and push to the working branch.
- **Keep CLAUDE.md current:** Update this file whenever the project structure, workflow, or conventions change significantly.
