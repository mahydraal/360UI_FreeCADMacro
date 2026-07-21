# GitHub publishing and release guide

## One-time repository setup

1. Create an empty GitHub repository, for example `fusion-like-freecad-profile`.
2. Upload or push the contents of this repository root, not the enclosing ZIP folder.
3. Keep GitHub Actions enabled so `.github/workflows/static-checks.yml` runs.
4. Enable Issues and Discussions if public testing will use both.
5. Review the LGPL license and repository ownership details before the first public release.
6. Add screenshots only if they are your own and contain no proprietary Autodesk assets.

## Suggested first commit

```bash
git init
git add .
git commit -m "Prepare Fusion-like FreeCAD profile v1.3.0 for public testing"
git branch -M main
git remote add origin <repository-url>
git push -u origin main
```

## Validate before tagging

```bash
python tools/validate_package.py --repo .
python tools/build_release.py --repo . --check
```

For a live release candidate, also complete the manual matrix in `docs/TESTING.md` on at least one supported FreeCAD build.

## Create a release

1. Update `VERSION`.
2. Update `src/fusion_like_ui_runtime.py` and `packaging/installed_README.txt`.
3. Add release notes to `CHANGELOG.md` and the versioned plain-text file under `release/`.
4. Update the smoke-test and uninstaller filenames if the version changes.
5. Run:

```bash
python tools/build_release.py --repo .
python tools/validate_package.py --repo .
```

6. Commit generated `macros/`, `dist/`, and `SHA256SUMS` changes.
7. Tag the commit:

```bash
git tag -a v1.3.0 -m "Fusion-like FreeCAD profile v1.3.0"
git push origin v1.3.0
```

8. Create a GitHub Release from the tag.
9. Attach the versioned ZIP from `dist/` and optionally the PDF guide.
10. Mark the release as **pre-release** while public testing is active.

## Recommended release description

Include:

- FreeCAD minimum version
- major added/fixed workflows
- upgrade instructions
- static/live validation status
- known limitations
- SHA-256 checksum
- link to issue templates and testing matrix

## Triage labels

Suggested labels:

- `bug`
- `compatibility`
- `documentation`
- `drawing`
- `assembly`
- `sketch`
- `projection`
- `threading`
- `needs-reproduction`
- `good-first-issue`
- `public-test`

## Security and trust

Macro files execute Python inside FreeCAD. Publish checksums, keep release files generated from tagged source, and do not accept opaque binary payloads in pull requests.
