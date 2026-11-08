# Changelog

All notable changes to `paperlint` are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/). The authoritative version string lives in
`pyproject.toml`, `src/paperlint/__init__.py` and `CITATION.cff` — all three must
agree (see [RELEASING.md](RELEASING.md)).

## [Unreleased]

### Added

- `tests/test_report.py` — 13 tests pinning the shared PASS/FAIL object, including
  the rule that an empty report is **not** a pass (`ok is False`, exit code 1).
- `tests/test_zenodo.py` — 9 tests pinning the deposit-record gate: unreachable
  record, restricted record with zero public files (the "publicly archived"
  overclaim), concept-vs-version labelling, licence returned as an object, and
  both branches of the 30-day file window. Network call is monkeypatched, so the
  suite stays offline.

### Changed

- Packaging metadata migrated to PEP 639: `license = "MIT"` plus
  `license-files = ["LICENSE"]`, build requirement raised to `setuptools>=77`, and
  the now-superseded `License :: OSI Approved :: MIT License` classifier removed.
  Without this, `python -m pip wheel .` fails on setuptools ≥ 84
  (`InvalidConfigError: License classifiers have been superseded`).
- `[tool.pytest.ini_options] pythonpath = ["src"]` — `pytest` now runs directly
  from a checkout without an editable install.
- README "Development" gains the artefact-verification recipe (build wheel,
  install into a clean venv, check the console script and module entry point).

## [0.1.0] — 2026-11-08

First release. Ten subcommands, each one a check that had previously been a
throwaway script during a real submission round.

### Added

- `manuscript package` — one PASS/FAIL table across every deliverable.
- `manuscript refs` — rewrites `\ref` from `.aux` so the DOCX has no `??`.
- `manuscript paths` — dangling path references and stale-claim wording.
- `manuscript docx-structure` — paragraph-level dump to compare template vs build.
- `manuscript docx-restyle` — restyles a pandoc DOCX, then re-reads it to verify.
- `manuscript figure` — measures the rendered figure instead of eyeballing it.
- `repo ci` — workflow placement, triggers, working directories, HEAD status.
- `repo divergence` — which files exist in only one of two git roots.
- `verify manifest` — recomputes sha256/bytes for every artefact in a manifest.
- `verify zenodo` — deposit record type, access setting, public file count, age.
- `--json` on any command for machine-readable reports in CI.
- Optional extras: `docx` (python-docx), `figures` (matplotlib, Pillow),
  `ci` (PyYAML), `dev` (pytest, ruff).

[Unreleased]: https://github.com/afiqandico/paperlint/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/afiqandico/paperlint/releases/tag/v0.1.0
