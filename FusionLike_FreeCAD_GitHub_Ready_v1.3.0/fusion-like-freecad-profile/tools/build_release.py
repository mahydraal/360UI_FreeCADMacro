#!/usr/bin/env python3
"""Build or verify the self-contained FreeCAD installer and release ZIP."""

from __future__ import annotations

import argparse
import ast
import hashlib
import pathlib
import tempfile
import zipfile

FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def build_installer(root: pathlib.Path) -> tuple[str, str]:
    version = read(root / "VERSION").strip()
    template = read(root / "installer/Install_FusionLike_FreeCAD.template.py")
    runtime = read(root / "src/fusion_like_ui_runtime.py")
    installed_readme = read(root / "packaging/installed_README.txt")
    output = (
        template.replace("__PROFILE_VERSION_LITERAL__", repr(version))
        .replace("__README_SOURCE_LITERAL__", repr(installed_readme))
        .replace("__RUNTIME_SOURCE_LITERAL__", repr(runtime))
    )
    # Syntax and payload sanity.
    tree = ast.parse(output)
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {"PROFILE_VERSION", "README_SOURCE", "RUNTIME_SOURCE"}:
                values[node.targets[0].id] = ast.literal_eval(node.value)
    assert values["PROFILE_VERSION"] == version
    assert values["README_SOURCE"] == installed_readme
    assert values["RUNTIME_SOURCE"] == runtime
    return version, output


def release_files(root: pathlib.Path, version: str, installer_text: str) -> dict[str, bytes]:
    files = {
        f"Install_FusionLike_FreeCAD_v{version}.FCMacro": installer_text.encode("utf-8"),
        f"FusionLikeUI_Profile_Source_v{version}.py": (root / "src/fusion_like_ui_runtime.py").read_bytes(),
        f"Uninstall_FusionLike_FreeCAD_v{version}.FCMacro": (root / "macros" / f"Uninstall_FusionLike_FreeCAD_v{version}.FCMacro").read_bytes(),
        f"FusionLikeUI_README_v{version}.txt": (root / "packaging/installed_README.txt").read_bytes(),
        f"FusionLikeUI_CHANGELOG_v{version}.txt": (root / "release" / f"FusionLikeUI_CHANGELOG_v{version}.txt").read_bytes(),
        f"FusionLikeUI_SmokeTest_v{version}.FCMacro": (root / "macros" / f"FusionLikeUI_SmokeTest_v{version}.FCMacro").read_bytes(),
        f"FusionLikeUI_VALIDATION_v{version}.txt": (root / "release" / f"FusionLikeUI_VALIDATION_v{version}.txt").read_bytes(),
    }
    return files


def write_zip(path: pathlib.Path, files: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])


def zip_contents(path: pathlib.Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = pathlib.Path(args.repo).resolve()
    version, installer = build_installer(root)
    installer_path = root / "macros" / f"Install_FusionLike_FreeCAD_v{version}.FCMacro"
    files = release_files(root, version, installer)
    zip_path = root / "dist" / f"FusionLike_FreeCAD_Profile_v{version}.zip"
    guide_source = root / "docs/FusionLikeUI_User_Guide.pdf"
    guide_dist = root / "dist" / f"FusionLikeUI_User_Guide_v{version}.pdf"

    if args.check:
        errors = []
        if not installer_path.exists() or installer_path.read_text(encoding="utf-8") != installer:
            errors.append(f"checked-in installer differs from generated installer: {installer_path}")
        if not zip_path.exists():
            errors.append(f"release ZIP is missing: {zip_path}")
        else:
            actual = zip_contents(zip_path)
            if actual != files:
                errors.append("release ZIP members differ from source inputs")
        if guide_source.exists():
            if not guide_dist.exists() or guide_dist.read_bytes() != guide_source.read_bytes():
                errors.append("versioned PDF guide differs from docs source")
        if errors:
            for error in errors:
                print("[FAIL]", error)
            return 1
        print(f"[PASS] installer and release ZIP are reproducible for v{version}")
        return 0

    installer_path.write_text(installer, encoding="utf-8", newline="\n")
    write_zip(zip_path, files)
    if guide_source.exists():
        guide_dist.write_bytes(guide_source.read_bytes())

    sums = []
    checksum_paths = [installer_path, zip_path]
    if guide_dist.exists():
        checksum_paths.append(guide_dist)
    for path in checksum_paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sums.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (root / "dist/SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"Built {installer_path.relative_to(root)}")
    print(f"Built {zip_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
