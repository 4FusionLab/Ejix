# Installation and updates

**English** · [Русский](INSTALLATION.ru.md) · [Home](../README.md)

## Install

1. Download the add-in ZIP from [Ejix releases](https://github.com/4FusionLab/Ejix/releases). The separate `.sha256` file lets you verify the archive.
2. Extract the archive to a permanent folder. Find the `Ejix` directory containing `Ejix.py` and `Ejix.manifest`.
3. In Fusion, open **Utilities → Scripts and Add-Ins**. In the **Add-Ins** tab, use **+** to add the `Ejix` directory.
4. Select **Ejix** and click **Run**. Enable **Run on Startup** if you want it loaded automatically.
5. Open a design with Capture Design History enabled and choose **Design → Solid → Modify → Eject**.

Keep the extracted folder in place: Fusion loads the add-in from that location. No separate Python installation or external packages are required.

## Update

Finish any active Eject command, stop the add-in in **Scripts and Add-Ins**, and replace the complete `Ejix` folder with the new version. Start Ejix again. Replacing files alone does not reload a running add-in.

## Remove

Stop Ejix and remove its entry from **Scripts and Add-Ins**, then remove the extracted folder. Designs containing Eject Features need a compatible Ejix installation for editing and recompute.

## Build from source

```sh
python -m unittest discover -s tests -v
python scripts/check_project.py
python scripts/build.py --kind addin --channel release
```

The build produces an add-in archive and SHA-256 checksum in `dist/`. See [Support](../SUPPORT.md) for troubleshooting.
