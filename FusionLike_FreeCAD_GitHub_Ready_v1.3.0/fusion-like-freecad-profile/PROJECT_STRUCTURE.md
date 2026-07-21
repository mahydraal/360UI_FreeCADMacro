# Project structure

| Path | Purpose |
|---|---|
| `src/fusion_like_ui_runtime.py` | Runtime source of truth loaded by FreeCAD |
| `macros/Install_*.FCMacro` | Self-contained public installer with embedded runtime and installed README |
| `macros/Uninstall_*.FCMacro` | Restores state and removes the add-on module |
| `macros/FusionLikeUI_SmokeTest_*.FCMacro` | Non-destructive live FreeCAD checks |
| `installer/*.template.py` | Installer source with generated payload placeholders |
| `packaging/Init.py` | FreeCAD module initialization stub |
| `packaging/InitGui.py` | Delayed GUI autoload logic |
| `packaging/installed_README.txt` | README written into the user add-on directory |
| `release/` | Versioned plain-text release and validation notes |
| `dist/` | Generated release ZIP and checksums |
| `docs/` | User, developer, testing, and publishing documentation |
| `tools/build_release.py` | Rebuilds installer and release ZIP deterministically |
| `tools/validate_package.py` | Static validation and consistency checks |
| `.github/` | Public issue forms, PR template, and CI |
