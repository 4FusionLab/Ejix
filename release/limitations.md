# Compatibility and validation

Eject Feature uses Autodesk Fusion's [Custom Feature API](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomFeatures_UM.htm). Autodesk designates this API as Preview and advises against shipping production programs that depend on preview capabilities. Future Fusion changes may affect Eject Feature creation, editing or recompute. Keep a compatible Ejix version available for models containing an Eject Feature.

The runtime was exercised in Fusion 2706.1.14 on macOS 27.0.1 using API-driven scenarios for separate and combined regions, body and component results, subtraction, split sources, editing, recompute and F3D reopening. This is partial native validation; full interactive acceptance was not completed.

Native Autodesk Fusion acceptance on Windows has not been performed. The Windows CI job checks Python tests, metadata and packaging, but does not run Fusion.
