# Contributing

Thank you for helping test and improve the project.

## Before opening an issue

- confirm the problem on the current public-test release
- run the smoke-test macro
- reproduce in a minimal document when possible
- search existing issues
- collect Report-view output and exact FreeCAD build information

Use the supplied issue forms so selection context and environment details are not lost.

## Development setup

No pip package is required for static work.

```bash
python tools/validate_package.py --repo .
python tools/build_release.py --repo . --check
```

For live work, manually install the source tree as described in `docs/INSTALLATION.md` or run the generated installer in a separate FreeCAD user profile.

## Source-of-truth rules

- Edit `src/fusion_like_ui_runtime.py`, not the embedded runtime inside the installer.
- Edit `packaging/installed_README.txt` for the README written into FreeCAD.
- Regenerate release artifacts with `tools/build_release.py`.
- Do not hand-edit generated `dist/` contents.
- Keep the installer runtime byte-for-byte consistent with `src/`.

## Coding guidelines

- Support FreeCAD 1.1+ and both Qt/PySide compatibility paths used by the runtime.
- Prefer native FreeCAD commands and objects.
- Wrap document changes in transactions and recompute deliberately.
- Every installed event filter, selection observer, timer, callback, dock, toolbar, or monkey patch needs a removal/restoration path.
- Do not capture or override shortcuts while a user is typing in a text/quantity control or modal dialog.
- Use command-ID fallback lists where action names vary by build.
- Prefix actionable runtime logs with `[Fusion-like UI]`.
- Avoid broad exception swallowing; report tracebacks when recovery is not certain.
- Do not add Autodesk assets, copied proprietary UI graphics, or misleading claims of implementation identity.

## Pull requests

A pull request should include:

- problem statement and intended workflow
- affected FreeCAD versions/platforms
- static validation output
- live manual test results and test IDs
- screenshots made from your own FreeCAD installation when UI changes are involved
- updated documentation and changelog
- explicit note about any persistent document-object schema change

Keep changes focused. Large redesigns should start as a discussion or issue.

## Licensing

Contributions are accepted under GNU LGPL 2.1 or later. By submitting a contribution, you affirm that you have the right to license it and that it does not contain proprietary Autodesk or other third-party assets.
