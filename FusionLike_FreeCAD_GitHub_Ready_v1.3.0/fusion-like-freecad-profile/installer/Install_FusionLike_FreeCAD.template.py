# -*- coding: utf-8 -*-
"""Install and apply Fusion-like Design, Sketch, Assembly, and Drawing workflows."""

import importlib
import os
import re
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui

try:
    from PySide import QtWidgets
except ImportError:
    QtWidgets = QtGui

PROFILE_VERSION = __PROFILE_VERSION_LITERAL__
PREF_PATH = "User parameter:BaseApp/Preferences/FusionLike"
ADDON_DIR = os.path.join(App.getUserAppDataDir(), "Mod", "FusionLikeUI")
RUNTIME_NAME = "fusion_like_ui_runtime"
RUNTIME_PATH = os.path.join(ADDON_DIR, RUNTIME_NAME + ".py")

INIT_SOURCE = '# -*- coding: utf-8 -*-\n# Fusion-like UI profile: runtime initialization is handled by InitGui.py.\n'
INIT_GUI_SOURCE = '# -*- coding: utf-8 -*-\n"""Autoload the reversible Fusion-like UI profile after FreeCAD\'s GUI starts."""\n\nimport os\nimport sys\nimport traceback\n\nimport FreeCAD as App\nimport FreeCADGui as Gui\nfrom PySide import QtCore\n\n_HERE = os.path.dirname(__file__)\nif _HERE not in sys.path:\n    sys.path.insert(0, _HERE)\n\n_ATTEMPTS = 0\n\n\ndef _fusion_like_boot():\n    global _ATTEMPTS\n    _ATTEMPTS += 1\n    try:\n        if Gui.getMainWindow() is None:\n            raise RuntimeError("FreeCAD main window is not ready")\n        import fusion_like_ui_runtime\n\n        fusion_like_ui_runtime.start()\n    except Exception:\n        if _ATTEMPTS < 12:\n            QtCore.QTimer.singleShot(500, _fusion_like_boot)\n        else:\n            App.Console.PrintWarning(\n                "[Fusion-like UI] Startup failed after repeated attempts:\\n{}\\n".format(\n                    traceback.format_exc()\n                )\n            )\n\n\nQtCore.QTimer.singleShot(900, _fusion_like_boot)\n'
README_SOURCE = __README_SOURCE_LITERAL__
RUNTIME_SOURCE = __RUNTIME_SOURCE_LITERAL__


def _write_text(path, text):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, path)


def _message(kind, title, text):
    parent = Gui.getMainWindow()
    method = getattr(QtWidgets.QMessageBox, kind)
    method(parent, title, text)


def _version_tuple():
    values = []
    for part in list(App.Version())[:3]:
        match = re.match(r"\d+", str(part))
        values.append(int(match.group(0)) if match else 0)
    while len(values) < 3:
        values.append(0)
    return tuple(values)


def install():
    if _version_tuple() < (1, 1, 0):
        raise RuntimeError(
            "This profile requires FreeCAD 1.1 or newer. The installed version is {}."
            .format(".".join(App.Version()[:3]))
        )

    first_install = not os.path.exists(RUNTIME_PATH)
    os.makedirs(ADDON_DIR, exist_ok=True)

    # Restore a loaded older copy before replacing its widgets and event hooks.
    old_runtime = sys.modules.get(RUNTIME_NAME)
    if old_runtime is not None and hasattr(old_runtime, "restore"):
        try:
            old_runtime.restore()
        except Exception:
            App.Console.PrintWarning(
                "[Fusion-like UI] Old profile restore reported an error:\n{}\n".format(
                    traceback.format_exc()
                )
            )

    _write_text(os.path.join(ADDON_DIR, "Init.py"), INIT_SOURCE)
    _write_text(os.path.join(ADDON_DIR, "InitGui.py"), INIT_GUI_SOURCE)
    _write_text(RUNTIME_PATH, RUNTIME_SOURCE)
    _write_text(os.path.join(ADDON_DIR, "README.txt"), README_SOURCE)

    pref = App.ParamGet(PREF_PATH)
    if first_install:
        pref.SetBool("OriginalStateCaptured", False)
        pref.SetBool("OriginalSketcherProjectionStateCaptured", False)
    pref.SetString("InstalledVersion", PROFILE_VERSION)
    pref.SetBool("Enabled", True)

    if ADDON_DIR not in sys.path:
        sys.path.insert(0, ADDON_DIR)

    importlib.invalidate_caches()
    runtime = importlib.import_module(RUNTIME_NAME)
    runtime = importlib.reload(runtime)
    runtime.start(force=True)

    _message(
        "information",
        "Fusion-like profile installed",
        "Version {} was installed and applied.\n\n"
        "Sketch edit mode now switches to a contextual Sketch ribbon. In DRAWING, use "
        "Insert Model View for dimensionable views; Active View Snapshot is raster. In "
        "ASSEMBLE, Ctrl+C/V/D manage component instances and failed mates now show decoded "
        "connector and solver diagnostics.\n\n"
        "Threaded Hole, independent Thread, and persistent Project / Include remain available."
        .format(PROFILE_VERSION),
    )


try:
    install()
except Exception:
    details = traceback.format_exc()
    App.Console.PrintError("[Fusion-like UI] Installation failed:\n{}\n".format(details))
    _message(
        "critical",
        "Fusion-like UI installation failed",
        "The installer could not complete. Details were written to FreeCAD's Report view.\n\n{}"
        .format(details),
    )
