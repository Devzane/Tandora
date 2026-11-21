---
name: git-workflow
description: Git version control standards for Tandora — atomic commits, conventional commit message formatting, branch management, and repository hygiene.
risk: low
source: project
date_added: '2026-11-21'
---

# Git Workflow Skill — Tandora

## Purpose

This skill governs version control practices, atomic commit standards, conventional commit formatting, and repository hygiene for the Tandora application.

## When to Use

Read this skill before creating branches, staging files, crafting commit messages, or synchronizing with the remote GitHub repository (`https://github.com/Devzane/Tandora.git`).

## Required Engineering Practices

### Atomic Commit Principle

- **One logical change per commit**: Each commit must encapsulate a single, coherent unit of work.
- **At least one commit per file / component**: For new architectural assets, documentation files, or distinct modules, commit each file independently with its own clear, context-specific commit message.
- **Reviewable history**: Each commit must stand on its own, compile or parse cleanly, and leave the repository in a stable state.

### Commit Message Structure

Follow the Conventional Commits specification:

```
<type>(<scope>): <subject>

[optional body explaining what and why, not how]

[optional footer]
```

#### Allowed Types

| Type | Purpose | Example |
|------|---------|---------|
| `docs` | Documentation changes or additions | `docs(spec): Add project specification document` |
| `feat` | New features, skills, or capabilities | `feat(skills): Add python-backend skill definition` |
| `fix` | Bug fixes or correction of errors | `fix(auth): Correct extension secret validation` |
| `ref` | Code refactoring without behavioral change | `ref(db): Reorganize session lifecycle helper` |
| `test` | Adding or updating unit/integration tests | `test(sending): Add 10-point pre-send checklist tests` |
| `chore` | Maintenance, configuration, or repo setup | `chore(repo): Initialize git repository and gitignore` |
| `style` | Formatting, whitespace, or style corrections | `style(models): Align type annotations with PEP 8` |

#### Subject Line Rules

- Imperative, present tense: `"Add"` not `"Added"`, `"Fix"` not `"Fixed"`.
- Capitalize the first letter of the subject: `docs(arch): Add system architecture overview`.
- No period at the end of the subject line.
- Keep the header line under 70 characters.

#### Body Guidelines

- Explain **what** was changed and **why**.
- Use bullet points for multi-part changes within the same atomic scope.

### Repository Hygiene & Safety

- **Never commit secrets**: Verify that `.env`, private keys, and credential tokens are excluded via `.gitignore`.
- **Never commit runtime state**: SQLite database files (`*.db`), temporary test artifacts, and Python cache directories (`__pycache__`) must remain untracked.
- **Check status before staging**: Run `git status` to verify that only the intended file is staged for the atomic commit.

## Implementation Guidelines

### Step-by-Step Atomic Commit Routine

```bash
# 1. Stage only the specific file
git add path/to/specific-file.md

# 2. Check staged diff
git diff --cached

# 3. Create conventional commit
git commit -m "docs(spec): Add project specification document"
```

## Common Mistakes

- Running `git add .` or `git add -A` and bundling multiple unrelated files into a single generic commit.
- Vague commit messages such as `"Update files"`, `"WIP"`, or `"Fixed stuff"`.
- Committing sensitive files (`.env`) or database binaries (`*.db`).

## Project-Specific Constraints

- Remote repository: `https://github.com/Devzane/Tandora.git`.
- Primary branch: `main`.
- Every documentation asset and skill file must be committed atomically.
