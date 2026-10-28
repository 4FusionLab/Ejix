# Support

**English** · [Русский](SUPPORT.ru.md)

## Before opening an issue

Check [installation](docs/INSTALLATION.md), [known limitations](docs/GUIDE.md#limitations), the [changelog](CHANGELOG.md), and existing issues.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Eject is missing | Confirm the folder containing `Ejix.py` and `Ejix.manifest` was added and started; switch to Design / Solid; try command search |
| Add-in fails to load | Check the Fusion log and that the extracted folder was not moved after registration |
| No intersection | Check Objects, direction/Flip, extent, offset and whether a positive solid volume is intersected |
| Scope error | Profiles and Objects must belong to one component occurrence; Start Object must be parallel to the source plane |
| Entire Object rejected | Reduce the region or disable Subtract from Objects |
| Unexpected arrow or preview | Record a short capture, full settings and plane/occurrence orientation |
| Eject Feature fails after reopening | Start the owning Ejix version before recompute; preserve the original file and report the issue with a minimal model |

Do not force-quit Fusion as a troubleshooting step while it contains unsaved work. Cancel the command first and capture the error when possible.

## Choose a report

- **Bug report:** reproducible failure, wrong geometry, preview, performance, history or installation issue.
- **Feature request:** explain the modeling task, present workaround and intended result.
- **CAD validation:** record the exact build, platform and scenario evidence.

Use English or Russian. Include a minimal shareable model or construction steps. Remove sensitive data from logs and attachments. For vulnerabilities, follow [Security](SECURITY.md). There is no promised response time or commercial support SLA.
