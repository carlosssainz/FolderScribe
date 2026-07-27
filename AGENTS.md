# AGENTS.md

## Documentation map by task type

| Task | Read first |
|---|---|
| Scan, inventory, filesystem | `docs/content/docs/mvp.mdx`, `docs/content/docs/architecture.mdx`, `docs/content/docs/privacy.mdx` |
| Domain models, data changes | `docs/content/docs/data-model.mdx` |
| UI, GUI, user-facing features | `docs/content/docs/architecture.mdx` |
| Privacy, file reading, content processing | `docs/content/docs/privacy.mdx` |
| Scope changes, feature requests | `docs/content/docs/mvp.mdx` (scope control rule) |
| Any change that affects behaviour | `docs/content/docs/product.mdx`, `docs/content/docs/mvp.mdx`, `docs/content/docs/architecture.mdx` |

## Project purpose

FolderScribe is a supervised, physical file organizer for Ubuntu 24.04. It
analyzes a user-selected folder, proposes classification and renaming, explains
its decisions, requests approval, and then executes the changes reversibly. The
first target use case is the Downloads folder. Windows support will come after
the main flow stabilizes.

Before making changes, agents must consult:
- `docs/content/docs/product.mdx` — vision, principles, privacy levels
- `docs/content/docs/mvp.mdx` — included/excluded features, safety rules
- `docs/content/docs/architecture.mdx` — when it contains applicable guidance
- `docs/content/docs/data-model.mdx` — for data or persistence changes
- `docs/content/docs/privacy.mdx` — for file reading or processing

## Current MVP

**Included (progressive implementation):** PDF/DOCX/TXT/Markdown support,
recursive inventory, format identification, exclusions, no symlink traversal,
code project detection and omission, local index, exact duplicate detection
(SHA-256), text extraction, scanned PDF detection, fast and full OCR,
classification proposals, rename proposals, confidence levels, current vs.
proposed tree view, individual and group approval, supervised folder creation,
approved move and rename, 30-day operation history, undo, and four privacy
levels.

**Excluded from MVP:** photos/screenshots, visual classification, compressed
archives, code project organization, continuous watching, advanced symlinks,
automatic deletion, cross-device sync, shared templates, knowledge graph,
Windows.

See `docs/content/docs/mvp.mdx` for the full list and scope control rule.

## Non-negotiable safety rules

- Analysis never modifies files.
- No file may be moved or renamed without approval.
- Never delete files automatically.
- Never overwrite files automatically.
- Do not follow symbolic links during scanning.
- Skip code projects by default.
- Validate that all destinations reside within an authorized root.
- Log operations before executing them.
- Keep sufficient information to attempt an undo.
- Always respect the most restrictive privacy level.
- Do not send content to external services without explicit permission.
- Tests must never use personal files or real Downloads folders.

## Architecture rules

Layers: `domain`, `application`, `infrastructure`, `ui`.

- `domain` must not import PySide6, SQLite, OCR, AI, or OS-specific details.
- `application` coordinates use cases.
- `infrastructure` implements filesystem access, database, extractors, OCR, and
  classifiers.
- `ui` presents information; it does not contain core logic.
- Use `pathlib.Path` for all paths.
- Never use an AI-generated path directly as a destination.
- External services must be consumed through interfaces.

These rules may be extended in `docs/content/docs/architecture.mdx`.

## Development workflow

Before implementing a task:
1. Read the relevant documentation.
2. State which files will be modified.
3. Make the minimal change required.
4. Add or update tests.
5. Run available checks.
6. Summarize changes, assumptions, and limitations.

Rules:
- Do not add dependencies without justification.
- Do not implement future features without first updating `docs/content/docs/mvp.mdx`.
- Do not perform unsolicited refactoring.
- Do not commit automatically.
- Do not modify files outside the task scope.

## Testing rules

- Use temporary directories for filesystem tests.
- Never use real user paths.
- OCR, AI, and external services must be replaced by deterministic doubles or
  fakes in unit tests.
- Test errors, collisions, permissions, and cancellations where applicable.
- A test must not leave files outside its temporary directory.

## Definition of done

A task is complete only when:
- it meets its criteria;
- it does not exceed the requested scope;
- it includes necessary tests;
- it does not compromise user data;
- documentation is updated if behaviour changes;
- checks performed are reported;
- modified files are listed.

## Current project status

- Project structure is created.
- `docs/content/docs/product.mdx` and `docs/content/docs/mvp.mdx` are defined.
- CLI inventory works (scan, exclusions, code project detection).
- Documentation site lives in `docs/` (Fumadocs).
- The next technical goal is the local SQLite index.
