# 4FusionLab — release policy

This repository follows the organization-wide release contract. The **GitVersion.Tool version is pinned to 6.8.2**. This file defines eligibility; it does not independently start publication.

## Version identity

- `GitVersion.yml` plus Git history and existing immutable `v*` tags define the next version. Conventional commit messages `feat:`, `fix:`, `perf:` and breaking-change markers determine the intended bump.
- A Fusion manifest and filename of a distributable ZIP use the numeric **MAJOR.MINOR.PATCH** from GitVersion (not a PR branch identifier). An optional prerelease suffix belongs to the Git tag and GitHub Release metadata, not to Fusion's numeric manifest.
- A released artifact, its embedded manifest, checksum, Git tag and GitHub Release must describe the same product version. Do not retarget tags or replace assets of a published release.
- Product IDs, Fusion manifest compatibility metadata, packaging contents and release-note history must not change as a side effect of version calculation.

## Release gates

1. Development changes enter `main` through a reviewed PR with successful required tests; full Git history is fetched to calculate versions.
2. Every release requires a deliberately prepared, nonempty version-specific release note, recorded compatibility limitations and applicable native Fusion acceptance evidence. A passing Python workflow **is not** proof of native Fusion CAD testing.
3. Stable: `vMAJOR.MINOR.PATCH`, `prerelease=false`. Prerelease: `vMAJOR.MINOR.PATCH-IDENTIFIER`, `prerelease=true`; never mark a prerelease as Latest. Preserve each project's additional channel-specific gates.
4. Publish only the tested commit. Before publication, validate archive filenames, embedded manifest version and SHA-256; a failed gate must leave the existing release untouched.
5. GitHub Actions uses minimum necessary permissions; jobs and pull requests must not gain write permission merely to calculate a version.
6. Avoid opportunistic releases on a routine PR merge. When required release notes or project-specific approval/evidence is absent, skip publication safely rather than inventing notes or issuing an unintended version.
7. A broken release is corrected by a new patch version. Existing public tags, release notes and downloadable files remain immutable.

## Explicit release trigger (organization-wide)

- A product GitHub Release may start **only** after deliberately pushing an immutable tag `vMAJOR.MINOR.PATCH` (stable) or `vMAJOR.MINOR.PATCH-IDENTIFIER` (prerelease) for a tested commit reachable from `main`. An ordinary branch push, PR merge or `workflow_dispatch` is never a release trigger.
- GitVersion.Tool **6.8.2** resolves the numeric `MajorMinorPatch`; the release tag must agree. Fusion manifests and ZIP filenames carry the numeric version only; the prerelease suffix is GitHub metadata.
- The tag workflow must pass the repository's existing automated tests, package/manifest checks, SHA-256 and reviewed release-note gates; retain any native CAD acceptance, platform limitations and project-specific controls. A failed explicit release attempt must fail closed rather than invent notes or publish unverified assets.
- Never create or move a version tag implicitly, reuse an existing tag for another commit, overwrite published release assets, or make a prerelease Latest. Retrying a published tag must leave the existing release unchanged.
- Projects with no approved distribution pipeline **do not publish** on tags. Enabling their releases requires a separate reviewed implementation; GitVersion validation and unrelated deployments are not release publication.

## Repository-specific publishing gate

Only a new version-tag push initiates `Publish release`. Its existing Linux/macOS/Windows CI, source/add-in packaging, bilingual notes, CAD/API acceptance, SHA-256 and stable/prerelease gates remain mandatory.
