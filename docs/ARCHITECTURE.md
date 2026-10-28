# Architecture

**English** · [Русский](ARCHITECTURE.ru.md) · [Home](../README.md)

| Module | Responsibility |
| --- | --- |
| `settings.py` | Settings, expressions and validation |
| `scope.py` | Plane comparisons |
| `engine.py` | Extraction, region ordering and per-source subtraction |
| `fusion_adapter.py` | Fusion geometry, features and components |
| `preview.py`, `solid.py` | Temporary BRep intersections and preview graphics |
| `feature.py` | Eject Feature dependencies, grouping and editing |
| `Ejix.py` | Command inputs, events and lifecycle |

## Geometry

Each source body is handled independently. Separate regions are extracted in selection order; earlier results are removed from subsequent copies before intersection. Connected results can instead be joined before subtraction. The original is cut with its own results only after extraction. The add-in preserves all resulting bodies when an operation splits a source.

## Preview and timeline

Preview uses temporary BRep data and Custom Graphics; it does not create model bodies or timeline operations. Native modeling is performed when the command is confirmed. The Eject Feature groups native operations and stores source/result mappings for editing; Native Features uses an expandable timeline group.

Fusion uses centimetres internally. Length expressions are retained where possible. Entity tokens are resolved through Fusion rather than compared as identity strings. Runtime code depends only on Fusion and its bundled Python standard library.

Autodesk designates the [Custom Feature API](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomFeatures_UM.htm) as Preview.
