# Release process

**English** · [Русский](PUBLISHING.ru.md)

CI checks repository metadata, tests, Python compilation and deterministic packages on Linux, macOS and Windows. Native Fusion validation is performed separately.

To prepare a release, update the manifest version, changelog and English/Russian release notes. Check the runtime source digest and complete the platform and API evidence in `release/acceptance.json`.

Run the **Publish release** workflow on the default branch with the matching tag and release channel. The workflow runs CI, validates the candidate, builds source and add-in ZIPs with SHA-256 checksums, and publishes the release against the tested commit. Stable releases require the native CAD and API evidence gate to pass. Prereleases are marked as such.

Verify the published tag, release notes, assets and checksums. Archive installation instructions are in [Installation](INSTALLATION.md).
