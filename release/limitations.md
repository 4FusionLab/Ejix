# Compatibility and validation

Eject Feature uses Autodesk Fusion's [Custom Feature API](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomFeatures_UM.htm). Autodesk designates this API as Preview and advises against shipping production programs that depend on preview capabilities. Future Fusion changes may affect Eject Feature creation, editing or recompute. Keep a compatible Ejix version available for models containing an Eject Feature.

For 1.1.0, the installed release candidate was exercised in Fusion 2706.1.17 on macOS 27.0.1. The native fixtures passed for overlapping planes, component output, body output with Eject Feature, multi-plane features, split sources with local F3D reopening, and feature editing and recompute. The candidate reported Pavel Kuznetsov as the author in Fusion. This validation covers the scripted native scenarios. The full interactive matrix remains pending.

Native Autodesk Fusion acceptance on Windows has not been performed. The Windows CI job checks Python tests, metadata and packaging, but does not run Fusion.
