#!/usr/bin/env python3
"""Static consistency checks that do not import FreeCAD."""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys
import zipfile


def compile_file(path: pathlib.Path) -> None:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def assignments(path: pathlib.Path, names: set[str]) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in names:
                result[name] = ast.literal_eval(node.value)
    return result


def local_markdown_links(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    links = []
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = target.split("#", 1)[0]
        if target and not re.match(r"^[a-z]+://", target) and not target.startswith("mailto:"):
            links.append(target)
    for target in re.findall(r"<img[^>]+src=\"([^\"]+)\"", text):
        if target and not re.match(r"^[a-z]+://", target):
            links.append(target)
    return links


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    root = pathlib.Path(args.repo).resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    failures = []
    passes = []

    def check(condition: bool, message: str) -> None:
        (passes if condition else failures).append(message)

    runtime = root / "src/fusion_like_ui_runtime.py"
    installer = root / "macros" / f"Install_FusionLike_FreeCAD_v{version}.FCMacro"
    uninstaller = root / "macros" / f"Uninstall_FusionLike_FreeCAD_v{version}.FCMacro"
    smoke = root / "macros" / f"FusionLikeUI_SmokeTest_v{version}.FCMacro"
    for path in [runtime, installer, uninstaller, smoke, root / "tools/build_release.py", root / "tools/validate_package.py"]:
        try:
            compile_file(path)
            check(True, f"syntax: {path.relative_to(root)}")
        except Exception as exc:
            check(False, f"syntax: {path.relative_to(root)}: {exc}")

    try:
        vals = assignments(installer, {"PROFILE_VERSION", "RUNTIME_SOURCE", "README_SOURCE"})
        check(vals.get("PROFILE_VERSION") == version, "installer version matches VERSION")
        check(vals.get("RUNTIME_SOURCE") == runtime.read_text(encoding="utf-8"), "embedded runtime matches src")
        check(vals.get("README_SOURCE") == (root / "packaging/installed_README.txt").read_text(encoding="utf-8"), "embedded installed README matches packaging source")
    except Exception as exc:
        check(False, f"installer payload inspection: {exc}")

    try:
        tree = ast.parse(runtime.read_text(encoding="utf-8"))
        profile = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FusionProfile")
        method_names = [node.name for node in profile.body if isinstance(node, ast.FunctionDef)]
        check(len(method_names) == len(set(method_names)), "FusionProfile method names are unique")
        calls = set()
        for node in ast.walk(profile):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                calls.add(node.func.attr)
        unresolved = sorted(calls - set(method_names))
        check(not unresolved, "FusionProfile self-calls resolve" + (f": {unresolved}" if unresolved else ""))
        required = {
            "_refresh_ui_context_if_needed", "insert_dimensionable_model_view", "start_drawing_dimension",
            "copy_assembly_components", "paste_assembly_components", "_install_assembly_task_diagnostics_patch",
            "_post_joint_accept_diagnostics", "project_profile", "project_reference", "open_fusion_hole", "open_fusion_thread"
        }
        check(required.issubset(set(method_names)), "required workflow methods present")
    except Exception as exc:
        check(False, f"runtime AST inspection: {exc}")

    for md in root.rglob("*.md"):
        for target in local_markdown_links(md):
            resolved = (md.parent / target).resolve()
            check(resolved.exists(), f"local link: {md.relative_to(root)} -> {target}")

    zip_path = root / "dist" / f"FusionLike_FreeCAD_Profile_v{version}.zip"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            names = set(zf.namelist())
        expected = {
            f"Install_FusionLike_FreeCAD_v{version}.FCMacro",
            f"FusionLikeUI_Profile_Source_v{version}.py",
            f"Uninstall_FusionLike_FreeCAD_v{version}.FCMacro",
            f"FusionLikeUI_README_v{version}.txt",
            f"FusionLikeUI_CHANGELOG_v{version}.txt",
            f"FusionLikeUI_SmokeTest_v{version}.FCMacro",
            f"FusionLikeUI_VALIDATION_v{version}.txt",
        }
        check(bad is None, "release ZIP CRC")
        check(names == expected, "release ZIP member list")
    except Exception as exc:
        check(False, f"release ZIP: {exc}")

    for message in passes:
        print("[PASS]", message)
    for message in failures:
        print("[FAIL]", message)
    print(f"\n{len(passes)} passed; {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
