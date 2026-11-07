# 4FusionLab — automatic runtime release policy

## Trigger

- A direct push to `main` or a PR merge into `main` is the only normal release event. PR checks, manual CI dispatch and version-tag pushes **do not** initiate publication.
- Before publishing, compare `GITHUB_SHA` to the newest **published** GitHub Release tag that is an ancestor of `main`. If no ZIP Release exists, use the original `github.event.before..GITHUB_SHA` push range. Deleted and renamed runtime files remain release-eligible.
- The repository's `.github/release-paths.txt` remains the audited release allowlist. README, guides, tests and CI-only changes **do not independently create a release**. A docs-only push may recover an earlier failed runtime release when eligible changes since the last published tag are still pending.
- All required existing CI checks must succeed before publishing. A failed gate means no release, no mutable tag and no replaced assets.

## Version and distribution

- GitVersion.Tool **6.8.2** derives numeric `MAJOR.MINOR.PATCH` using `GitVersion.yml` and the full Git history. The package ZIP, embedded Fusion manifest (where applicable), auto-created immutable `vMAJOR.MINOR.PATCH` tag and GitHub Release refer to the same commit/version.
- The pipeline creates the tag **automatically** when it publishes the GitHub Release. Contributors never create or push release tags manually. A pre-existing version tag pointing to another commit is an error; a published release is never overwritten.
- Existing reviewed, version-specific release notes are used when present; otherwise notes are automatically generated from Git history. No manually prepared release-note file is required just to ship a code change.
- Stable releases become Latest. Prereleases never become Latest. Project-specific native-CAD acceptance, tests, signed/hashed archives, OS compatibility and publication limitations remain in force.

## This repository

Runtime allowlist: `Ejix/**`, `scripts/build.py`. If release/acceptance.json proves the current source digest and native CAD compatibility, publish Stable. Otherwise publish an automatically numbered `-beta.N` prerelease and retain the stated limitations.

When no eligible runtime input has changed since the last published release, CI may run but publication is skipped even if GitVersion computes a different version. A failed publication is retried by the next push to `main` after all normal CI gates pass; existing released tags/assets are never overwritten.

## Shared release actions

GitVersion 6.8.2, runtime impact filtering, release-note generation and ZIP integrity verification use Actions pinned to `4FusionLab/.github` commit `ad9d60ba4aabc494b4f2c85d6c566a50ca423751`. Ejix keeps its native CAD acceptance/limitations gate, original source and add-in builders, stable/prerelease decisions, and publishing job. Retired local release-gate and release-note helper scripts are no longer authoritative.

**Recovery platform:** The published-release classifier is pinned separately to `2e961620a068c3ad754f6e1be05fb6e4ac68e843` with `recover-unpublished: 'true'` and read-only `github.token`. Other shared actions retain the reviewed `ad9d60ba4aabc494b4f2c85d6c566a50ca423751` pin.
