# -*- coding: utf-8 -*-
"""Autoload the reversible Fusion-like UI profile after FreeCAD's GUI starts."""

import os
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_ATTEMPTS = 0


def _fusion_like_boot():
    global _ATTEMPTS
    _ATTEMPTS += 1
    try:
        if Gui.getMainWindow() is None:
            raise RuntimeError("FreeCAD main window is not ready")
        import fusion_like_ui_runtime

        fusion_like_ui_runtime.start()
    except Exception:
        if _ATTEMPTS < 12:
            QtCore.QTimer.singleShot(500, _fusion_like_boot)
        else:
            App.Console.PrintWarning(
                "[Fusion-like UI] Startup failed after repeated attempts:\n{}\n".format(
                    traceback.format_exc()
                )
            )


QtCore.QTimer.singleShot(900, _fusion_like_boot)
