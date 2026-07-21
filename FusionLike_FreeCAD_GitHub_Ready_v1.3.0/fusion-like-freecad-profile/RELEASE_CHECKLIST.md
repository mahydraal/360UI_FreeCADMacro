# Release checklist

- [ ] Update `VERSION`.
- [ ] Update runtime `PROFILE_VERSION`.
- [ ] Update installed README and changelog.
- [ ] Update versioned macro filenames and smoke-test expectations.
- [ ] Run `python tools/build_release.py --repo .`.
- [ ] Run `python tools/validate_package.py --repo .`.
- [ ] Run `python tools/build_release.py --repo . --check`.
- [ ] Complete relevant manual test matrix entries in FreeCAD.
- [ ] Test fresh install, upgrade, restore, and uninstall.
- [ ] Review generated SHA-256 checksums.
- [ ] Commit generated artifacts.
- [ ] Tag the exact tested commit.
- [ ] Create a pre-release and attach the `dist/` ZIP and PDF guide.
- [ ] State live-test environments and known failures in release notes.
