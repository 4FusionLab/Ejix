# Validation

**English** · [Русский](VALIDATION.ru.md)

Automated checks cover settings, geometry orchestration, Fusion API boundaries, package contents, documentation links and release metadata. CI runs these checks on Linux, macOS and Windows; it does not run Autodesk Fusion.

```sh
python -m unittest discover -s tests -v
python -m compileall -q Ejix scripts tests
python scripts/check_project.py
python scripts/build.py --kind addin --channel release
```

Native Fusion checks exercise geometry, previews, Eject Feature creation and editing, recompute, and F3D reopening. The macOS checks cover separate and combined regions, split source bodies, and body/component results. Native Windows Fusion acceptance has not been completed.

Stable release checks use `release/acceptance.json` to tie platform and API evidence to the exact runtime source digest. Autodesk's Custom Feature API remains designated Preview; its distribution status must be resolved before that gate can pass.
