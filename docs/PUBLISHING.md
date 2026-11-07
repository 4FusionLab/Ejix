# Release process

**English** · [Русский](PUBLISHING.ru.md)

CI checks repository metadata, tests, Python compilation and deterministic packages on Linux, macOS and Windows. Native Fusion validation is performed separately.

To prepare a release, calculate the numeric release version with GitVersion 6.8.2, then update the changelog and English/Russian release notes. Packaging embeds the GitVersion number in the archived manifest without editing the checked-in manifest. Check the runtime source digest and complete the platform and API evidence in `release/acceptance.json`.

Run the **Publish release** workflow on the default branch with a GitVersion-matching tag: `vX.Y.Z` for stable, `vX.Y.Z-IDENTIFIER` for prerelease, and the matching release channel. The workflow runs CI, validates the candidate, builds source and add-in ZIPs with SHA-256 checksums, and publishes the release against the tested commit. Stable releases require native CAD and API evidence, or an explicit documented limitations policy. Partial and untested platforms remain labelled as such. Prereleases are marked as such.

Verify the published tag, release notes, assets and checksums. Archive installation instructions are in [Installation](INSTALLATION.md).
