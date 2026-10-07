# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
