# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add keyword-only `Confease(..., autoload=False)` for deferred destination loading. First ordinary reads, mutations, saves, and source overlays initialize existing file values before use; failed loads preserve uninitialized state for retry. Default construction remains eager, and deferred loading interoperates with `reload=True`.
- Support public fresh-instance repair, template reset, and backup restore over malformed destinations without an initial parse. Successful recovery initializes entries; cancelled editing and failed recovery preserve deferred state. Configuration defaults named `autoload` use `items` independently of the loading option.

### Changed

- Use destination-bound deferred construction in CLI restore instead of private path mutation, removing its runtime-only diagnostic.

### Breaking Changes

- Replace arbitrary `Confease` constructor keyword defaults with `items: dict | None = None`. Migrate `Confease(DEBUG=False)` to `Confease(items={"DEBUG": False})`. Configuration keys can now use any constructor option name without collisions; non-dictionary, non-`None` items raise `TypeError`.
- Rename constructor `__backup__` to `backup`, without a legacy alias. Migrate `Confease(__backup__=True, backup="daily")` to `Confease(backup=True, items={"backup": "daily"})`. Templates remain incompatible with nonempty defaults, but accept omitted, `None`, or empty `items`.

## [3.0.0] - 2026-10-10

### Added

- Add `Confease.edit_file(template=PATH)` and `confease init PATH --template PATH` to preload exact template text for missing destinations without changing configured defaults. Explicit acceptance creates the target even when the template is unchanged.
- Provide embedded terminal editing through Edital 0.2.0, including contextual help, literal and regular-expression find/replace, and undoable replacements.
- Retain accepted text in a recovery file when backup or installation fails, reporting its path through CLI diagnostics or exception notes.

### Changed

- Validate interactive edits in the same session, keeping invalid candidates available for correction without changing destination content or live configuration entries.
- Install accepted text without reserialization, preserving comments, formatting, uniform LF/CRLF line endings, and final-newline presence. Cancelled sessions preserve existing files and unsaved in-memory values, and leave missing destinations absent.
- Refuse to overwrite a destination created while a missing-target editing session is open.
- Install the published `edital>=0.2.0,<0.3` dependency automatically and document its current keyboard controls and configuration-editing workflows.
- Use F2 or F3 to validate and accept text, Ctrl+Q to cancel, and Escape to dismiss interactions. F4 opens Find and F5 opens Find/Replace.

### Breaking Changes

- Interactive CLI editing and `Confease.edit_file()` now default to an embedded transactional editor requiring interactive terminal input and output, rather than external-editor discovery. Library callers can assign `conf.editor = TextEditor(...)` to retain external direct-file editing; scripted CLI updates and deletions remain noninteractive.
- Default manual-edit backups now occur after explicit acceptance and validation, immediately before installation. Cancellation and rejected candidates create no backup. Explicitly selected external editors retain pre-launch backups and their existing invalid-save behavior.

## [2.0.0] - 2026-10-07

### Added

- Add the `confease init` and `confease edit` commands, with format inference, typed assignments, leaf and section deletion, and `confease PATH` edit shorthand.
- Support interactive CLI repair through retained drafts that reopen for correction and install exact bytes only after validation.
- Add `Confease.delete()` for removing leaves or sections, with automatic persistence when `reload=True`.
- Add opt-in exact-byte backups through the `__backup__` constructor policy, per-operation `backup=` overrides, and CLI `-b|--backup` flags. Timestamped sibling backups use numeric suffixes to avoid collisions.
- Add `Confease.restore()` and `confease restore PATH [--from BACKUP]` for explicit or latest-backup recovery, including malformed or missing destinations. Backed-up restores allow consecutive restores to toggle between versions.

### Changed

- Preserve comments during structured YAML, TOML, INI-family, and XML writes, retaining the destination's latest annotations and unaffected presentation where supported.
- Validate complete serialized candidates before replacing destination files, rejecting unrepresentable values without partial writes.
- Leave missing files absent until the editor saves them; `TextEditor.open()` no longer pre-creates its target.

### Fixed

- Load configured templates as memory-only default-origin values and separate lazy initialization from explicit reset.
- Complete template-backed `reset()` with validated exact-content restoration, preserving template comments and formatting.
- Validate complete configuration content before replacing in-memory entries, preserving prior state when loading fails.

### Breaking Changes

- Remove `user_only` from `Confease.edit_file()`; migrate calls to `edit_file()`. The API now opens the real configured path without serialization, preserving comments and formatting. `save(user_only=...)` remains supported.
- Invalid manually saved edits now remain on disk and raise validation errors while preserving previous in-memory entries. Correct and save the file before reloading, or use interactive CLI repair.
- Structured saves now reject invalid existing configuration files instead of overwriting them. Repair the destination before saving, or use `confease edit PATH` to repair it interactively.
- Reserve `restore` as a CLI command. To edit a configuration file named `restore`, use `confease ./restore` and supply `--format` when needed.

## [1.0.0] - 2026-08-13

### Added

- Add the `Confease` configuration container with defaults, user/system files, environment variables, and `argparse.Namespace` source loading.
- Add configurable source precedence with CLI, environment, system, user, and default origins.
- Add typed configuration persistence for YAML, JSON, TOML, CSV, INI-family formats, and XML.
- Add one-level nested configuration keys with dotted leaf access and section snapshots.
- Add indexed access and assignment through `conf[key]` and `conf[key] = value`.
- Add safe config-file editing through a blocking `TextEditor` and `Confease.edit_file()` draft-validation workflow.
- Add release, documentation deployment, and pre-commit automation for package maintenance.

### Changed

- Preserve original Python value types instead of stringifying `Confitem.value`.
- Store CSV and INI-family scalar values as YAML text so common Python values round-trip across flat formats.
- Keep defaults memory-only unless callers explicitly save the full effective configuration with `save(user_only=False)`.
- Treat nested-capable parsers as nested mappings while CSV persists flat dotted keys with a `key,value` header.

### Documentation

- Add practical README guidance for installation, quickstart usage, precedence, nested keys, environment variables, supported file formats, and editor workflows.
- Add Sphinx documentation with user guides, parser/file-format guidance, troubleshooting notes, and autodoc-based API reference pages.

### Tests

- Add focused coverage for core configuration behavior, parser round-tripping, source precedence, persistence, indexed access, and editor safety.
