# Release process

**English** · [Русский](PUBLISHING.ru.md)

CI checks repository metadata, tests, Python compilation and deterministic packages on Linux, macOS and Windows. Native Fusion validation is performed separately.

To prepare a release, calculate the numeric release version with GitVersion 6.8.2, then update the changelog and English/Russian release notes. Packaging embeds the GitVersion number in the archived manifest without editing the checked-in manifest. Check the runtime source digest and complete the platform and API evidence in `release/acceptance.json`.

Push an immutable version tag on a tested commit reachable from `main`: `vX.Y.Z` for stable, or `vX.Y.Z-IDENTIFIER` for prerelease. **The tag push automatically starts Publish release**; no manual workflow launch or separate channel input is required. The channel is derived from the tag. The workflow runs CI, validates the candidate, builds source and add-in ZIPs with SHA-256 checksums, and publishes the release against the tagged commit. Ordinary merges and branch pushes never publish. Stable releases require native CAD and API evidence, or an explicit documented limitations policy. Partial and untested platforms remain labelled as such. Prereleases are marked as such.

Verify the published tag, release notes, assets and checksums. Archive installation instructions are in [Installation](INSTALLATION.md).
