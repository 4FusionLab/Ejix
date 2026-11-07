# Ejix development

[Русская версия](AGENTS.ru.md)

Ejix is a Fusion add-in for extracting volumes from profiles and faces, with a parametric Eject Feature.

## Shared 4FusionLab rules

- Shared standards: https://github.com/4FusionLab/.github/blob/main/AGENTS.md; shared CI model: https://github.com/4FusionLab/.github/blob/main/RELEASE_PLATFORM.md.
- Communicate with the user and make plans in Russian; use English for Fusion command names, code and UI. Retain separate README.md and README.ru.md where the project has them.
- Inspect current code and `git status` before changes; preserve unrelated work. Use Conventional Commits; small PRs with tests are preferred, while direct pushes to `main` are allowed by the existing policy.
- Do not change the Fusion manifest UUID, command IDs, OS support or distribution structure without a separate task and migration plan. Keep secrets, personal CAD files, tokens and unauthorized external services out of the repository.
- Where shippable runtime exists, release is triggered only by a push/merge to `main` affecting `.github/release-paths.txt`. CI checks code, GitVersion.Tool 6.8.2 determines the version, and GitHub automatically creates the tag and Release. **Never create or move release tags manually**, or overwrite published ZIPs.
- README, docs, tests, CI settings and `AGENTS.md` must not independently trigger a release. Pin shared Actions to an **immutable commit SHA** from `4FusionLab/.github`, not `@main`.
- Unit tests and ZIP checks are not live Autodesk Fusion tests. For API/UX changes record what was actually tested and on which OS.

## Product and API boundaries

- Behavioral sources: `README.md`, `README.ru.md`, `docs/GUIDE.md` and `docs/VALIDATION.md`. Treat `Ejix/engine.py` as the independent kernel; use `Ejix/fusion_adapter.py` and `Ejix/feature.py` only in Autodesk Fusion context.
- Maintain existing Extent/Direction, multiple profiles, source-body subtraction, Preview and temporary-object cleanup on Cancel. Do not leave model changes before user confirmation.
- Autodesk's `Custom Feature API` has Preview limitations; do not promise production compatibility without fresh native validation. Preserve `release/acceptance.json` and `release/limitations.md`; a release with changed runtime but no current CAD acceptance must remain a prerelease.
- Verify official Autodesk definitions before changing Fusion API calls; do not invent methods. Fusion objects and event handlers have limited lifetimes; handle cancellation and disappearing objects.

## Verification

- `python -m unittest discover -s tests -v`
- `python scripts/check_project.py`
- `python scripts/build.py --kind addin --channel release --version X.Y.Z` (local package verification only, no publication)
- For interactive changes use a separate unsaved CAD document without interfering with the active user model; follow `docs/VALIDATION.md`.
- Preserve SPDX license headers and existing macOS/Windows limitations.
