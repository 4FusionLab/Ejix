# Contributing to Ejix

**English** · [Русский](CONTRIBUTING.ru.md)

Bug reports, reproducible CAD scenarios, documentation and code contributions are welcome. Read the [guide](docs/GUIDE.md), check existing repository issues, and discuss changes that alter the operation model before implementing them.

## Report an issue

Use the repository's issue chooser. Include the Ejix version or source commit, full Fusion version, OS, modeling history mode, source selections, result settings, steps, expected result and actual result. A small model you are allowed to share is ideal; construction instructions are also useful. Screenshots explain appearance but do not replace geometry or reproduction steps. See [Support](SUPPORT.md) and [Security](SECURITY.md).

## Make a change

1. Create a focused branch. Use `codex/` for Codex-created branches and Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).
2. Keep numeric/settings logic independent of `adsk`. Runtime dependencies are the standard library and Fusion API only.
3. Preserve explicit Objects participation, per-source result identity and extraction of all sources before the first Cut. Never silently expand scope.
4. Run the checks below. For UI, geometry, adapter or lifecycle changes, perform the affected [CAD scenarios](docs/VALIDATION.md) when Fusion is available. Use a separate unsaved design and one CAD operator at a time.
5. Update English and Russian user-facing documentation together, and record behavior changes under Unreleased in both changelogs.
6. Open a PR using the template. Describe the resulting behavior, relevant evidence, limitations and checks not performed.

```sh
python -m unittest discover -s tests -v
python -m compileall -q Ejix scripts tests
python scripts/check_project.py
python scripts/build.py
```

Use Python 3.12+ for offline tooling; the actual runtime is Fusion's bundled Python. Avoid unsupported syntax until tested in the declared Fusion versions. Tests should check behavior and failure recovery. Passing offline tests is not native CAD acceptance.

## Review and licensing

Keep changes reviewable and preserve work from other contributors. Avoid committing models with confidential data, logs with credentials, caches, generated archives or local installation backups. Contributions are licensed under [GPL-3.0-only](LICENSE). Preserve compatible copyright notices and attribution.

Follow the [Code of Conduct](CODE_OF_CONDUCT.md). The [architecture](docs/ARCHITECTURE.md), [UX contract](docs/UX.md) and [release process](docs/PUBLISHING.md) define the current project conventions.
