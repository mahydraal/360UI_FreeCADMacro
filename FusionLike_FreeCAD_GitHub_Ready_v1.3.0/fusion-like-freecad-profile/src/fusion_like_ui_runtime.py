# -*- coding: utf-8 -*-
"""Fusion-like design, sketch, thread, assembly, and drawing workflow for FreeCAD 1.1+.

This module is loaded by the installer-created InitGui.py file. It uses native
FreeCAD commands and geometry APIs, adds a standards-driven independent Thread
feature, and preserves the persistent projection workflow from version 1.1.
"""

import base64
import json
import math
import re
import traceback

import Part

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

try:
    from PySide import QtWidgets
except ImportError:  # Older FreeCAD/PySide compatibility layer
    QtWidgets = QtGui


QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction
QCursor = getattr(QtGui, "QCursor", None) or QtWidgets.QCursor
QIcon = getattr(QtGui, "QIcon", None) or QtWidgets.QIcon
QKeySequence = getattr(QtGui, "QKeySequence", None) or QtWidgets.QKeySequence

PREF_PATH = "User parameter:BaseApp/Preferences/FusionLike"
VIEW_PREF_PATH = "User parameter:BaseApp/Preferences/View"
SKETCHER_PREF_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher/General"
TOOLBAR_PREFIX = "FusionLike_"
TIMELINE_NAME = "FusionLike_Timeline"
MENU_NAME = "FusionLike_Menu"
STATE_VERSION = 1
PROFILE_VERSION = "1.3.0"
ASSEMBLY_CLIPBOARD_MIME = "application/x-fusionlike-freecad-assembly-components"
ASSEMBLY_SOLVER_CODES = {
    0: ("Solved successfully", "The native Assembly solver accepted the current joint graph."),
    -6: ("No grounded component", "Ground at least one component before solving. Without a fixed reference, the whole assembly can move freely."),
    -4: ("Over-constrained assembly", "One or more joints constrain the same degree of freedom more than once. Suppress the newest joint or replace several constraints with one joint that expresses the intended motion."),
    -3: ("Conflicting joints", "Two or more active joints demand incompatible positions or orientations. Inspect the conflicting/redundant joint set and verify connector directions and offsets."),
    -5: ("Malformed joint", "At least one joint has a missing, broken, circular, or unsupported reference. Re-pick its two connector subelements."),
    -1: ("Solver error", "The solver could not obtain a valid numerical solution. Check invalid references, extreme offsets, closed loops, and component placements."),
    -2: ("Redundant joints", "The assembly contains constraints that do not add independent information. Suppress or remove redundant joints to make the kinematic graph unambiguous."),
}

_PROFILE = None
_MENU = None


def _console(message, warning=False):
    text = "[Fusion-like UI] {}\n".format(message)
    if warning:
        App.Console.PrintWarning(text)
    else:
        App.Console.PrintMessage(text)


def _strip_action_text(text):
    return re.sub(r"\s+", " ", (text or "").replace("&", "").replace("…", "").strip())


def _menu_exec(menu, pos):
    if hasattr(menu, "exec"):
        return menu.exec(pos)
    return menu.exec_(pos)


def _active_workbench_name():
    try:
        workbench = Gui.activeWorkbench()
        name = workbench.name()
        return str(name)
    except Exception:
        return ""


def _set_item_user_data(item, value):
    item.setData(QtCore.Qt.UserRole, value)


def _item_user_data(item):
    return item.data(QtCore.Qt.UserRole)


def _freecad_version_tuple():
    """Return a numeric (major, minor, patch) tuple without trusting suffixes."""
    try:
        raw = App.Version()
    except Exception:
        return (0, 0, 0)
    values = []
    for part in list(raw)[:3]:
        match = re.match(r"\d+", str(part))
        values.append(int(match.group(0)) if match else 0)
    while len(values) < 3:
        values.append(0)
    return tuple(values)


def _element_leaf(sub_name):
    """Extract the final FaceN/EdgeN/VertexN token from a subelement path."""
    matches = re.findall(r"(?:Face|Edge|Vertex)\d+", str(sub_name or ""))
    return matches[-1] if matches else ""


class ProjectionSelectionObserver(object):
    """Forward FreeCAD selection events to an active projection session."""

    def __init__(self, profile):
        self.profile = profile

    def addSelection(self, document, object_name, element, position):
        del position
        document = str(document or "")
        object_name = str(object_name or "")
        element = str(element or "")
        self.profile._queue_projection_selection(document, object_name, element)


THREAD_FEATURE_VERSION = 1
THREAD_COMMAND_ID = "FusionLike_Thread"
HOLE_COMMAND_ID = "FusionLike_Hole"
THREAD_SUPPORTED_STANDARDS = (
    "ISOMetricProfile",
    "ISOMetricFineProfile",
    "UNC",
    "UNF",
    "UNEF",
    "BSP",
    "BSW",
    "BSF",
)
THREAD_WHITWORTH_STANDARDS = {"BSP", "BSW", "BSF"}
THREAD_STANDARD_LABELS = {
    "None": "None",
    "ISOMetricProfile": "ISO Metric Profile",
    "ISOMetricFineProfile": "ISO Metric Fine Profile",
    "UNC": "Unified National Coarse (UNC)",
    "UNF": "Unified National Fine (UNF)",
    "UNEF": "Unified National Extra Fine (UNEF)",
    "NPT": "National Pipe Taper (NPT)",
    "BSP": "British Standard Pipe (BSP)",
    "BSW": "British Standard Whitworth (BSW)",
    "BSF": "British Standard Fine (BSF)",
    "ISOTyre": "ISO Tyre Valve",
}


def _dialog_exec(dialog):
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def _quantity_value(value, default=0.0):
    try:
        return float(value.Value)
    except Exception:
        try:
            return float(value)
        except Exception:
            return float(default)


def _enum_options(obj, property_name):
    try:
        return [str(value) for value in obj.getEnumerationsOfProperty(property_name)]
    except Exception:
        return []


def _set_enum_value(obj, property_name, value):
    options = _enum_options(obj, property_name)
    if not options:
        return False
    text = str(value)
    if text not in options:
        text = options[0]
    setattr(obj, property_name, text)
    return True


def _is_derived(obj, type_name):
    if obj is None:
        return False
    try:
        return bool(obj.isDerivedFrom(type_name))
    except Exception:
        return str(getattr(obj, "TypeId", "")) == str(type_name)


def _global_body_for_object(obj):
    if obj is None:
        return None
    if _is_derived(obj, "PartDesign::Body"):
        return obj
    visited = set()
    queue = list(getattr(obj, "InList", []) or [])
    while queue:
        parent = queue.pop(0)
        marker = id(parent)
        if marker in visited:
            continue
        visited.add(marker)
        if _is_derived(parent, "PartDesign::Body"):
            return parent
        queue.extend(list(getattr(parent, "InList", []) or []))
    return None


def _active_partdesign_body(doc=None, preferred=None):
    doc = doc or App.ActiveDocument
    body = _global_body_for_object(preferred)
    if body is not None:
        return body
    gui_document = getattr(Gui, "ActiveDocument", None)
    if gui_document is not None:
        try:
            body = gui_document.ActiveView.getActiveObject("pdbody")
            if body is not None:
                return body
        except Exception:
            pass
    try:
        for selected in Gui.Selection.getSelection():
            body = _global_body_for_object(selected)
            if body is not None:
                return body
    except Exception:
        pass
    if doc is not None:
        for obj in doc.Objects:
            if _is_derived(obj, "PartDesign::Body"):
                return obj
    return None


def _active_edited_sketch_global():
    gui_document = getattr(Gui, "ActiveDocument", None)
    if gui_document is None:
        return None
    try:
        edit = gui_document.getInEdit()
    except Exception:
        return None
    obj = getattr(edit, "Object", None) if edit is not None else None
    if obj is not None and _is_derived(obj, "Sketcher::SketchObject"):
        return obj
    return None


def _normalized_vector(value):
    vector = App.Vector(value)
    length = float(vector.Length)
    if length <= 1e-12:
        raise ValueError("The cylindrical face has an invalid axis direction.")
    return vector / length


def _shape_element(source, sub_name):
    shape = getattr(source, "Shape", None)
    if shape is None:
        raise ValueError("The selected source has no shape.")
    leaf = _element_leaf(sub_name)
    if not leaf:
        raise ValueError("Select a cylindrical face, not the whole object.")
    try:
        return shape.getElement(leaf), leaf
    except Exception:
        try:
            return getattr(shape, leaf), leaf
        except Exception:
            raise ValueError("The selected subelement {} is unavailable.".format(leaf))


def _face_sample_points(face):
    points = []
    for vertex in list(getattr(face, "Vertexes", []) or []):
        try:
            points.append(App.Vector(vertex.Point))
        except Exception:
            pass
    try:
        u1, u2, v1, v2 = face.ParameterRange
        for u in (u1, (u1 + u2) / 2.0, u2):
            for v in (v1, (v1 + v2) / 2.0, v2):
                try:
                    points.append(App.Vector(face.valueAt(u, v)))
                except Exception:
                    pass
    except Exception:
        pass
    return points


def _analyze_cylindrical_face(source, sub_name):
    face, leaf = _shape_element(source, sub_name)
    if str(getattr(face, "ShapeType", "")) != "Face":
        raise ValueError("{} is not a face.".format(leaf))
    surface = getattr(face, "Surface", None)
    if surface is None or not hasattr(surface, "Radius") or not hasattr(surface, "Axis"):
        raise ValueError("{} is not cylindrical.".format(leaf))
    radius = _quantity_value(surface.Radius)
    if radius <= 0.0:
        raise ValueError("{} has an invalid radius.".format(leaf))
    axis = _normalized_vector(surface.Axis)
    center = App.Vector(getattr(surface, "Center", App.Vector(0, 0, 0)))
    samples = _face_sample_points(face)
    if not samples:
        raise ValueError("Could not sample the cylindrical face.")
    axial = [(point - center).dot(axis) for point in samples]
    t_min = min(axial)
    t_max = max(axial)
    span = t_max - t_min
    if span <= 1e-7:
        raise ValueError("The cylindrical face has no usable axial length.")

    outward = True
    try:
        u1, u2, v1, v2 = face.ParameterRange
        u = (u1 + u2) / 2.0
        v = (v1 + v2) / 2.0
        point = App.Vector(face.valueAt(u, v))
        normal = _normalized_vector(face.normalAt(u, v))
        axial_point = center + axis * ((point - center).dot(axis))
        radial = point - axial_point
        if radial.Length > 1e-9:
            outward = normal.dot(radial) >= 0.0
    except Exception:
        pass

    return {
        "source": source,
        "sub_name": leaf,
        "face": face,
        "axis": axis,
        "axis_center": center,
        "t_min": t_min,
        "t_max": t_max,
        "span": span,
        "radius": radius,
        "external": bool(outward),
    }


def _thread_profile_depth(pitch, standard):
    pitch = float(pitch)
    if standard in THREAD_WHITWORTH_STANDARDS:
        return 5.0 * (0.960491 * pitch) / 6.0
    return 7.0 * ((math.sqrt(3.0) / 2.0) * pitch) / 8.0


def _thread_profile_wire(pitch, major_radius, standard, radial_clearance=0.0):
    pitch = float(pitch)
    major_radius = float(major_radius)
    clearance = float(radial_clearance)
    margin_z = min(0.001, max(1e-6, pitch * 0.001))
    if standard in THREAD_WHITWORTH_STANDARDS:
        height = 0.960491 * pitch
        depth = 5.0 * height / 6.0 + clearance
        if depth <= max(1e-7, pitch * 0.02):
            raise ValueError("Thread clearance makes the Whitworth profile depth non-positive.")
        crest_radius = 0.137329 * pitch
        root_x = major_radius - depth + math.tan(math.radians(62.5)) * margin_z
        flank_x = major_radius - crest_radius * 0.58284013094
        p1 = App.Vector(root_x, 0.0, -pitch / 2.0 + margin_z)
        p2 = App.Vector(flank_x, 0.0, -pitch / 8.0)
        crest = App.Vector(major_radius, 0.0, 0.0)
        p3 = App.Vector(flank_x, 0.0, pitch / 8.0)
        p4 = App.Vector(root_x, 0.0, pitch / 2.0 - margin_z)
        edges = [Part.makeLine(p1, p2)]
        try:
            edges.append(Part.Arc(p2, crest, p3).toShape())
        except Exception:
            edges.extend([Part.makeLine(p2, crest), Part.makeLine(crest, p3)])
        edges.extend([Part.makeLine(p3, p4), Part.makeLine(p4, p1)])
        return Part.Wire(edges), depth

    height = (math.sqrt(3.0) / 2.0) * pitch
    depth = 7.0 * height / 8.0 + clearance
    if depth <= max(1e-7, pitch * 0.02):
        raise ValueError("Thread clearance makes the profile depth non-positive.")
    root_x = major_radius - depth + math.tan(math.radians(60.0)) * margin_z
    p1 = App.Vector(root_x, 0.0, -pitch / 2.0 + margin_z)
    p2 = App.Vector(major_radius, 0.0, -pitch / 16.0)
    p3 = App.Vector(major_radius, 0.0, pitch / 16.0)
    p4 = App.Vector(root_x, 0.0, pitch / 2.0 - margin_z)
    return Part.makePolygon([p1, p2, p3, p4, p1]), depth


def _make_thread_cutter(analysis, pitch, standard, length, offset, start_side, direction, mode, clearance):
    pitch = float(pitch)
    length = float(length)
    offset = max(0.0, float(offset))
    clearance = float(clearance)
    if pitch <= 0.0 or length <= 0.0:
        raise ValueError("Thread pitch and length must be positive.")
    span = float(analysis["span"])
    if offset + length > span + 1e-7:
        raise ValueError("Thread offset plus length exceeds the selected cylindrical face.")

    if mode == "Internal":
        internal = True
    elif mode == "External":
        internal = False
    else:
        internal = not bool(analysis["external"])

    nominal_depth = _thread_profile_depth(pitch, standard)
    surface_radius = float(analysis["radius"])
    if internal:
        major_radius = surface_radius + nominal_depth + clearance
        profile_clearance = clearance
    else:
        major_radius = surface_radius
        profile_clearance = clearance
    if major_radius <= nominal_depth * 0.25:
        raise ValueError("The selected cylinder is too small for this thread profile.")

    profile, profile_depth = _thread_profile_wire(
        pitch, major_radius, standard, profile_clearance
    )
    left_handed = str(direction).lower().startswith("left")
    sweep_height = length + 2.0 * pitch
    helix = Part.makeHelix(pitch, sweep_height, major_radius, 0.0, left_handed)
    helix_wire = Part.Wire(list(helix.Edges))
    cutter = helix_wire.makePipeShell([profile], True, True)

    clip_radius = major_radius + abs(profile_depth) + pitch + abs(clearance)
    clip = Part.makeCylinder(
        clip_radius,
        length,
        App.Vector(0.0, 0.0, 0.0),
        App.Vector(0.0, 0.0, 1.0),
    )
    cutter = cutter.common(clip)
    if cutter.isNull():
        raise ValueError("The thread sweep did not intersect its length envelope.")

    if str(start_side).lower().startswith("high"):
        start_t = float(analysis["t_max"]) - offset - length
    else:
        start_t = float(analysis["t_min"]) + offset
    origin = analysis["axis_center"] + analysis["axis"] * start_t
    rotation = App.Rotation(App.Vector(0.0, 0.0, 1.0), analysis["axis"])
    cutter.Placement = App.Placement(origin, rotation)
    return cutter, internal


def _thread_callout(standard, designation, thread_class, pitch, direction):
    standard = str(standard)
    designation = str(designation)
    thread_class = str(thread_class or "").strip()
    if standard in ("ISOMetricProfile", "ISOMetricFineProfile"):
        text = designation
    elif standard in ("UNC", "UNF", "UNEF", "BSP", "BSW", "BSF"):
        try:
            tpi = int(round(25.4 / float(pitch)))
            text = "{}-{} {}".format(designation, tpi, standard)
        except Exception:
            text = "{} {}".format(designation, standard)
    else:
        text = "{} {}".format(designation, standard)
    if thread_class and thread_class not in ("None", "-"):
        text += " - {}".format(thread_class)
    if str(direction).lower().startswith("left"):
        text += " LH"
    return text.strip()


class NativeThreadCatalog(object):
    """Use a temporary native Hole object as FreeCAD's authoritative thread table."""

    def __init__(self, document):
        self.document = document
        self.probe = document.addObject("PartDesign::Hole", "FusionThreadCatalog")
        self.probe.Label = "Temporary Fusion-like thread catalog"
        try:
            self.probe.Visibility = False
        except Exception:
            pass
        try:
            self.probe.Threaded = True
        except Exception:
            pass

    def close(self):
        probe = self.probe
        self.probe = None
        if probe is not None and self.document is not None:
            try:
                self.document.removeObject(probe.Name)
            except Exception:
                pass

    def standards(self, standalone=False):
        values = _enum_options(self.probe, "ThreadType")
        if standalone:
            values = [value for value in values if value in THREAD_SUPPORTED_STANDARDS]
        return values

    def set_standard(self, standard):
        _set_enum_value(self.probe, "ThreadType", standard)
        return str(self.probe.ThreadType)

    def sizes(self, standard=None):
        if standard is not None:
            self.set_standard(standard)
        return _enum_options(self.probe, "ThreadSize")

    def classes(self, standard=None, designation=None):
        if standard is not None:
            self.set_standard(standard)
        if designation is not None:
            _set_enum_value(self.probe, "ThreadSize", designation)
        return _enum_options(self.probe, "ThreadClass")

    def spec(self, standard, designation, thread_class=None):
        self.set_standard(standard)
        _set_enum_value(self.probe, "ThreadSize", designation)
        if thread_class is not None:
            _set_enum_value(self.probe, "ThreadClass", thread_class)
        return {
            "standard": str(self.probe.ThreadType),
            "designation": str(self.probe.ThreadSize),
            "thread_class": str(self.probe.ThreadClass),
            "pitch": _quantity_value(self.probe.ThreadPitch),
            "diameter": _quantity_value(self.probe.ThreadDiameter),
        }

    def closest_designation(self, standard, surface_diameter, internal=False):
        """Return the native size whose expected cylinder best matches the selection."""
        standard = self.set_standard(standard)
        target = max(0.0, float(surface_diameter))
        best = None
        for designation in self.sizes(standard):
            try:
                spec = self.spec(standard, designation)
                expected = float(spec["diameter"])
                if internal:
                    expected -= 2.0 * _thread_profile_depth(spec["pitch"], standard)
                error = abs(expected - target)
                row = (error, designation)
                if best is None or row < best:
                    best = row
            except Exception:
                continue
        return best[1] if best is not None else None


class HoleThreadDialog(QtWidgets.QDialog):
    """Fusion-style front end over FreeCAD's native threaded Hole feature."""

    def __init__(self, hole, is_new=False, parent=None):
        super(HoleThreadDialog, self).__init__(parent or Gui.getMainWindow())
        self.hole = hole
        self.document = hole.Document
        self.is_new = bool(is_new)
        self._updating = False
        self.setWindowTitle("Hole — Fusion-style Threaded Hole")
        self.resize(560, 820)

        outer = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "Native Part Design Hole geometry with FreeCAD's standards, cosmetic thread, "
            "and true modeled thread options.",
            self,
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        form = QtWidgets.QFormLayout()
        self.threaded = QtWidgets.QCheckBox("Threaded", self)
        self.modeled = QtWidgets.QCheckBox("Modeled thread", self)
        self.cosmetic = QtWidgets.QCheckBox("Cosmetic thread metadata", self)
        model_row = QtWidgets.QWidget(self)
        model_layout = QtWidgets.QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(self.threaded)
        model_layout.addWidget(self.modeled)
        model_layout.addWidget(self.cosmetic)
        form.addRow("Thread mode", model_row)

        self.standard = QtWidgets.QComboBox(self)
        self.size = QtWidgets.QComboBox(self)
        self.thread_class = QtWidgets.QComboBox(self)
        self.thread_fit = QtWidgets.QComboBox(self)
        self.direction = QtWidgets.QComboBox(self)
        self.direction.addItems(["Right hand", "Left hand"])
        form.addRow("Standard", self.standard)
        form.addRow("Size", self.size)
        form.addRow("Class", self.thread_class)
        form.addRow("Clearance fit", self.thread_fit)
        form.addRow("Direction", self.direction)

        self.specification = QtWidgets.QLabel(self)
        self.specification.setWordWrap(True)
        form.addRow("Calculated", self.specification)

        self.depth_type = QtWidgets.QComboBox(self)
        self.depth = QtWidgets.QDoubleSpinBox(self)
        self.depth.setRange(0.001, 1000000.0)
        self.depth.setDecimals(4)
        self.depth.setSuffix(" mm")
        form.addRow("Hole depth type", self.depth_type)
        form.addRow("Hole depth", self.depth)

        self.thread_depth_type = QtWidgets.QComboBox(self)
        self.thread_depth = QtWidgets.QDoubleSpinBox(self)
        self.thread_depth.setRange(0.001, 1000000.0)
        self.thread_depth.setDecimals(4)
        self.thread_depth.setSuffix(" mm")
        form.addRow("Thread depth type", self.thread_depth_type)
        form.addRow("Thread depth", self.thread_depth)

        self.head_type = QtWidgets.QComboBox(self)
        self.custom_head = QtWidgets.QCheckBox("Use custom head values", self)
        self.head_diameter = QtWidgets.QDoubleSpinBox(self)
        self.head_diameter.setRange(0.0, 1000000.0)
        self.head_diameter.setDecimals(4)
        self.head_diameter.setSuffix(" mm")
        self.head_depth = QtWidgets.QDoubleSpinBox(self)
        self.head_depth.setRange(0.0, 1000000.0)
        self.head_depth.setDecimals(4)
        self.head_depth.setSuffix(" mm")
        self.countersink_angle = QtWidgets.QDoubleSpinBox(self)
        self.countersink_angle.setRange(0.01, 179.99)
        self.countersink_angle.setDecimals(3)
        self.countersink_angle.setSuffix(" deg")
        form.addRow("Head type", self.head_type)
        form.addRow("Head override", self.custom_head)
        form.addRow("Head diameter", self.head_diameter)
        form.addRow("Head depth", self.head_depth)
        form.addRow("Countersink angle", self.countersink_angle)

        self.drill_point = QtWidgets.QComboBox(self)
        self.drill_angle = QtWidgets.QDoubleSpinBox(self)
        self.drill_angle.setRange(1.0, 179.0)
        self.drill_angle.setDecimals(3)
        self.drill_angle.setSuffix(" deg")
        self.drill_for_depth = QtWidgets.QCheckBox(
            "Hole depth includes the angled drill tip", self
        )
        self.tapered = QtWidgets.QCheckBox("Tapered hole / pipe thread", self)
        self.taper_angle = QtWidgets.QDoubleSpinBox(self)
        self.taper_angle.setRange(90.0, 179.99)
        self.taper_angle.setDecimals(4)
        self.taper_angle.setSuffix(" deg included angle")
        self.reversed = QtWidgets.QCheckBox("Reverse hole direction", self)
        form.addRow("Drill point", self.drill_point)
        form.addRow("Drill point angle", self.drill_angle)
        form.addRow("Depth interpretation", self.drill_for_depth)
        form.addRow("Taper", self.tapered)
        form.addRow("Taper angle", self.taper_angle)
        form.addRow("Direction", self.reversed)

        self.custom_clearance = QtWidgets.QCheckBox("Use custom thread clearance", self)
        self.clearance = QtWidgets.QDoubleSpinBox(self)
        self.clearance.setRange(-1000.0, 1000.0)
        self.clearance.setDecimals(5)
        self.clearance.setSuffix(" mm")
        form.addRow("Thread clearance", self.custom_clearance)
        form.addRow("Clearance value", self.clearance)

        self.preview = QtWidgets.QCheckBox("Live preview (modeled threads can be slow)", self)
        self.preview.setChecked(False)
        form.addRow("Preview", self.preview)
        outer.addLayout(form)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, self
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self.preview_timer = QtCore.QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(220)
        self.preview_timer.timeout.connect(self._preview_now)
        self._load_from_hole()
        self._connect_controls()
        self._update_enabled()

    def _set_combo(self, combo, values, current=None, label_map=None):
        combo.blockSignals(True)
        combo.clear()
        for value in values:
            label = label_map.get(value, value) if label_map else value
            combo.addItem(str(label), str(value))
        index = combo.findData(str(current)) if current is not None else -1
        if index < 0 and combo.count():
            index = 0
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _load_from_hole(self):
        actual_standard = str(getattr(self.hole, "ThreadType", "None"))
        self._set_combo(
            self.standard,
            _enum_options(self.hole, "ThreadType"),
            actual_standard,
            THREAD_STANDARD_LABELS,
        )
        self._refresh_sizes(str(getattr(self.hole, "ThreadSize", "")))
        self._set_combo(
            self.thread_fit,
            _enum_options(self.hole, "ThreadFit"),
            str(getattr(self.hole, "ThreadFit", "")),
        )
        self.threaded.setChecked(bool(getattr(self.hole, "Threaded", False)))
        self.modeled.setChecked(bool(getattr(self.hole, "ModelThread", False)))
        self.cosmetic.setChecked(bool(getattr(self.hole, "CosmeticThread", True)))
        current_direction = str(getattr(self.hole, "ThreadDirection", "Right hand"))
        self.direction.setCurrentIndex(1 if "Left" in current_direction else 0)

        self._set_combo(
            self.depth_type,
            _enum_options(self.hole, "DepthType"),
            str(getattr(self.hole, "DepthType", "Dimension")),
        )
        self.depth.setValue(_quantity_value(getattr(self.hole, "Depth", 10.0), 10.0))
        self._set_combo(
            self.thread_depth_type,
            _enum_options(self.hole, "ThreadDepthType"),
            str(getattr(self.hole, "ThreadDepthType", "Hole Depth")),
        )
        self.thread_depth.setValue(
            _quantity_value(getattr(self.hole, "ThreadDepth", self.depth.value()), self.depth.value())
        )
        self._refresh_head_types(str(getattr(self.hole, "HoleCutType", "None")))
        self.custom_head.setChecked(bool(getattr(self.hole, "HoleCutCustomValues", False)))
        self.head_diameter.setValue(_quantity_value(getattr(self.hole, "HoleCutDiameter", 0.0)))
        self.head_depth.setValue(_quantity_value(getattr(self.hole, "HoleCutDepth", 0.0)))
        self.countersink_angle.setValue(
            _quantity_value(getattr(self.hole, "HoleCutCountersinkAngle", 90.0), 90.0)
        )
        self._set_combo(
            self.drill_point,
            _enum_options(self.hole, "DrillPoint"),
            str(getattr(self.hole, "DrillPoint", "Flat")),
        )
        self.drill_angle.setValue(
            _quantity_value(getattr(self.hole, "DrillPointAngle", 118.0), 118.0)
        )
        self.drill_for_depth.setChecked(bool(getattr(self.hole, "DrillForDepth", False)))
        self.tapered.setChecked(bool(getattr(self.hole, "Tapered", False)))
        self.taper_angle.setValue(
            _quantity_value(getattr(self.hole, "TaperedAngle", 90.0), 90.0)
        )
        self.reversed.setChecked(bool(getattr(self.hole, "Reversed", False)))
        self.custom_clearance.setChecked(
            bool(getattr(self.hole, "UseCustomThreadClearance", False))
        )
        self.clearance.setValue(
            _quantity_value(getattr(self.hole, "CustomThreadClearance", 0.0))
        )
        self._update_specification()

    def _connect_controls(self):
        self.standard.currentIndexChanged.connect(self._standard_changed)
        self.size.currentIndexChanged.connect(self._size_changed)
        self.thread_class.currentIndexChanged.connect(self._schedule_preview)
        for widget in (
            self.threaded,
            self.modeled,
            self.cosmetic,
            self.custom_head,
            self.drill_for_depth,
            self.tapered,
            self.reversed,
            self.custom_clearance,
            self.preview,
        ):
            widget.toggled.connect(self._control_changed)
        for combo in (
            self.direction,
            self.thread_fit,
            self.depth_type,
            self.thread_depth_type,
            self.head_type,
            self.drill_point,
        ):
            combo.currentIndexChanged.connect(self._control_changed)
        for spin in (
            self.depth,
            self.thread_depth,
            self.head_diameter,
            self.head_depth,
            self.countersink_angle,
            self.drill_angle,
            self.taper_angle,
            self.clearance,
        ):
            spin.valueChanged.connect(self._control_changed)

    def _current_data(self, combo):
        value = combo.currentData()
        return str(value if value is not None else combo.currentText())

    def _refresh_sizes(self, preferred=None):
        standard = self._current_data(self.standard)
        try:
            _set_enum_value(self.hole, "ThreadType", standard)
        except Exception:
            pass
        self._set_combo(
            self.size,
            _enum_options(self.hole, "ThreadSize"),
            preferred or str(getattr(self.hole, "ThreadSize", "")),
        )
        self._refresh_classes(str(getattr(self.hole, "ThreadClass", "")))

    def _refresh_classes(self, preferred=None):
        try:
            _set_enum_value(self.hole, "ThreadSize", self._current_data(self.size))
        except Exception:
            pass
        self._set_combo(
            self.thread_class,
            _enum_options(self.hole, "ThreadClass"),
            preferred or str(getattr(self.hole, "ThreadClass", "")),
        )
        self._refresh_head_types(str(getattr(self.hole, "HoleCutType", "None")))
        self._update_specification()

    def _refresh_head_types(self, preferred=None):
        self._set_combo(
            self.head_type,
            _enum_options(self.hole, "HoleCutType"),
            preferred or str(getattr(self.hole, "HoleCutType", "None")),
        )

    def _standard_changed(self, *args):
        del args
        self._refresh_sizes()
        self._control_changed()

    def _size_changed(self, *args):
        del args
        self._refresh_classes()
        self._control_changed()

    def _control_changed(self, *args):
        del args
        self._update_enabled()
        self._update_specification()
        self._schedule_preview()

    def _update_enabled(self):
        threaded = self.threaded.isChecked()
        for widget in (
            self.modeled,
            self.cosmetic,
            self.standard,
            self.size,
            self.thread_class,
            self.direction,
            self.thread_depth_type,
            self.thread_depth,
            self.custom_clearance,
            self.clearance,
        ):
            widget.setEnabled(threaded)
        self.thread_fit.setEnabled(not threaded)
        self.thread_depth.setEnabled(
            threaded and self._current_data(self.thread_depth_type) == "Dimension"
        )
        self.depth.setEnabled(self._current_data(self.depth_type) == "Dimension")
        self.clearance.setEnabled(threaded and self.custom_clearance.isChecked())
        custom_head = self.custom_head.isChecked()
        self.head_diameter.setEnabled(custom_head)
        self.head_depth.setEnabled(custom_head)
        self.countersink_angle.setEnabled(custom_head)
        angled = self._current_data(self.drill_point) == "Angled"
        self.drill_angle.setEnabled(angled)
        self.drill_for_depth.setEnabled(angled)
        self.taper_angle.setEnabled(self.tapered.isChecked())

    def _update_specification(self):
        try:
            standard = self._current_data(self.standard)
            designation = self._current_data(self.size)
            thread_class = self._current_data(self.thread_class)
            _set_enum_value(self.hole, "ThreadType", standard)
            _set_enum_value(self.hole, "ThreadSize", designation)
            _set_enum_value(self.hole, "ThreadClass", thread_class)
            pitch = _quantity_value(self.hole.ThreadPitch)
            diameter = _quantity_value(self.hole.ThreadDiameter)
            callout = _thread_callout(
                standard,
                designation,
                thread_class,
                pitch,
                self._current_data(self.direction),
            )
            self.specification.setText(
                "{}    major diameter {:.4g} mm    pitch {:.4g} mm".format(
                    callout, diameter, pitch
                )
            )
        except Exception:
            self.specification.setText("Thread specification is not currently available.")

    def _apply_to_hole(self):
        standard = self._current_data(self.standard)
        if self.threaded.isChecked() and standard == "None":
            raise ValueError("Choose a thread standard for a threaded hole.")
        _set_enum_value(self.hole, "ThreadType", standard)
        _set_enum_value(self.hole, "ThreadSize", self._current_data(self.size))
        _set_enum_value(self.hole, "ThreadClass", self._current_data(self.thread_class))
        _set_enum_value(self.hole, "ThreadFit", self._current_data(self.thread_fit))
        self.hole.Threaded = self.threaded.isChecked()
        self.hole.ModelThread = self.threaded.isChecked() and self.modeled.isChecked()
        try:
            self.hole.CosmeticThread = self.threaded.isChecked() and self.cosmetic.isChecked()
        except Exception:
            pass
        native_direction = (
            "Left" if self._current_data(self.direction).lower().startswith("left") else "Right"
        )
        _set_enum_value(self.hole, "ThreadDirection", native_direction)
        _set_enum_value(self.hole, "DepthType", self._current_data(self.depth_type))
        self.hole.Depth = self.depth.value()
        _set_enum_value(
            self.hole, "ThreadDepthType", self._current_data(self.thread_depth_type)
        )
        self.hole.ThreadDepth = self.thread_depth.value()
        _set_enum_value(self.hole, "HoleCutType", self._current_data(self.head_type))
        self.hole.HoleCutCustomValues = self.custom_head.isChecked()
        if self.custom_head.isChecked():
            self.hole.HoleCutDiameter = self.head_diameter.value()
            self.hole.HoleCutDepth = self.head_depth.value()
            self.hole.HoleCutCountersinkAngle = self.countersink_angle.value()
        _set_enum_value(self.hole, "DrillPoint", self._current_data(self.drill_point))
        self.hole.DrillPointAngle = self.drill_angle.value()
        self.hole.DrillForDepth = self.drill_for_depth.isChecked()
        self.hole.Tapered = self.tapered.isChecked()
        self.hole.TaperedAngle = self.taper_angle.value()
        self.hole.Reversed = self.reversed.isChecked()
        self.hole.UseCustomThreadClearance = self.custom_clearance.isChecked()
        self.hole.CustomThreadClearance = self.clearance.value()

    def _schedule_preview(self, *args):
        del args
        if self.preview.isChecked():
            self.preview_timer.start()

    def _preview_now(self):
        try:
            self._apply_to_hole()
            self.document.recompute()
        except Exception as exc:
            self.specification.setText("Preview error: {}".format(exc))

    def accept(self):
        try:
            self._apply_to_hole()
            self.document.recompute()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Threaded Hole", str(exc))
            return
        super(HoleThreadDialog, self).accept()


class StandaloneThreadDialog(QtWidgets.QDialog):
    """Fusion-like independent Thread dialog for selected cylindrical faces."""

    def __init__(self, catalog, analyses, existing=None, parent=None):
        super(StandaloneThreadDialog, self).__init__(parent or Gui.getMainWindow())
        self.catalog = catalog
        self.analyses = analyses
        self.existing = existing
        self.setWindowTitle("Thread — Fusion-style Independent Feature")
        self.resize(500, 560)
        outer = QtWidgets.QVBoxLayout(self)

        summary = QtWidgets.QLabel(self)
        external_count = sum(1 for row in analyses if row["external"])
        internal_count = len(analyses) - external_count
        summary.setText(
            "{} cylindrical face(s): {} external, {} internal. "
            "Modeled threads perform a real subtractive helical cut.".format(
                len(analyses), external_count, internal_count
            )
        )
        summary.setWordWrap(True)
        outer.addWidget(summary)

        form = QtWidgets.QFormLayout()
        self.modeled = QtWidgets.QCheckBox("Modeled", self)
        self.modeled.setChecked(True)
        self.standard = QtWidgets.QComboBox(self)
        self.size = QtWidgets.QComboBox(self)
        self.thread_class = QtWidgets.QComboBox(self)
        self.direction = QtWidgets.QComboBox(self)
        self.direction.addItems(["Right hand", "Left hand"])
        self.mode = QtWidgets.QComboBox(self)
        self.mode.addItems(["Auto", "Internal", "External"])
        self.full_length = QtWidgets.QCheckBox("Full length", self)
        self.full_length.setChecked(True)
        self.length = QtWidgets.QDoubleSpinBox(self)
        self.length.setRange(0.001, 1000000.0)
        self.length.setDecimals(4)
        self.length.setSuffix(" mm")
        self.offset = QtWidgets.QDoubleSpinBox(self)
        self.offset.setRange(0.0, 1000000.0)
        self.offset.setDecimals(4)
        self.offset.setSuffix(" mm")
        self.start_side = QtWidgets.QComboBox(self)
        self.start_side.addItems(["Low end", "High end"])
        self.clearance = QtWidgets.QDoubleSpinBox(self)
        self.clearance.setRange(-1000.0, 1000.0)
        self.clearance.setDecimals(5)
        self.clearance.setSuffix(" mm radial")
        self.refine = QtWidgets.QCheckBox("Refine result", self)
        self.refine.setChecked(False)
        self.specification = QtWidgets.QLabel(self)
        self.specification.setWordWrap(True)

        form.addRow("Representation", self.modeled)
        form.addRow("Standard", self.standard)
        form.addRow("Size", self.size)
        form.addRow("Class", self.thread_class)
        form.addRow("Direction", self.direction)
        form.addRow("Face type", self.mode)
        form.addRow("Extent", self.full_length)
        form.addRow("Length", self.length)
        form.addRow("Offset", self.offset)
        form.addRow("Start side", self.start_side)
        form.addRow("Extra clearance", self.clearance)
        form.addRow("Post-process", self.refine)
        form.addRow("Callout", self.specification)
        outer.addLayout(form)

        note = QtWidgets.QLabel(
            "Cosmetic mode stores the standards-based callout and keeps the solid unchanged. "
            "Tapered NPT is intentionally handled by the native threaded Hole command, not by "
            "the standalone cylindrical Thread command.",
            self,
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, self
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        standards = self.catalog.standards(standalone=True)
        for value in standards:
            self.standard.addItem(THREAD_STANDARD_LABELS.get(value, value), value)
        self.standard.currentIndexChanged.connect(self._standard_changed)
        self.size.currentIndexChanged.connect(self._size_changed)
        self.thread_class.currentIndexChanged.connect(self._update_callout)
        self.direction.currentIndexChanged.connect(self._update_callout)
        self.full_length.toggled.connect(self._extent_changed)
        self.modeled.toggled.connect(self._modeled_changed)
        self.mode.currentIndexChanged.connect(self._update_callout)

        self._load_initial()
        self._extent_changed()
        self._modeled_changed()

    def _current_data(self, combo):
        value = combo.currentData()
        return str(value if value is not None else combo.currentText())

    def _set_combo_values(self, combo, values, preferred=None):
        combo.blockSignals(True)
        combo.clear()
        for value in values:
            combo.addItem(str(value), str(value))
        index = combo.findData(str(preferred)) if preferred is not None else -1
        if index < 0 and combo.count():
            index = 0
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _load_initial(self):
        if self.existing is not None:
            standard = str(getattr(self.existing, "ThreadStandard", "ISOMetricProfile"))
            designation = str(getattr(self.existing, "ThreadDesignation", ""))
            thread_class = str(getattr(self.existing, "ThreadClassName", ""))
        else:
            standard = "ISOMetricProfile"
            first = self.analyses[0]
            designation = self.catalog.closest_designation(
                standard,
                2.0 * float(first["radius"]),
                internal=not bool(first["external"]),
            ) or ""
            thread_class = ""
        index = self.standard.findData(standard)
        if index >= 0:
            self.standard.setCurrentIndex(index)
        self._refresh_sizes(designation)
        self._refresh_classes(thread_class)

        shortest = min(row["span"] for row in self.analyses)
        self.length.setMaximum(shortest)
        self.offset.setMaximum(shortest)
        self.length.setValue(shortest)
        if self.existing is not None:
            self.modeled.setChecked(bool(getattr(self.existing, "Modeled", True)))
            self.full_length.setChecked(bool(getattr(self.existing, "FullLength", True)))
            self.length.setValue(_quantity_value(getattr(self.existing, "Length", shortest), shortest))
            self.offset.setValue(_quantity_value(getattr(self.existing, "Offset", 0.0)))
            self.clearance.setValue(
                _quantity_value(getattr(self.existing, "RadialClearance", 0.0))
            )
            self.refine.setChecked(bool(getattr(self.existing, "RefineThread", False)))
            direction = str(getattr(self.existing, "Direction", "Right hand"))
            self.direction.setCurrentIndex(1 if direction.startswith("Left") else 0)
            mode = str(getattr(self.existing, "FaceType", "Auto"))
            mode_index = self.mode.findText(mode)
            if mode_index >= 0:
                self.mode.setCurrentIndex(mode_index)
            side = str(getattr(self.existing, "StartSide", "Low end"))
            self.start_side.setCurrentIndex(1 if side.startswith("High") else 0)
        self._update_callout()

    def _standard_changed(self, *args):
        del args
        preferred = None
        if self.existing is None and self.analyses:
            first = self.analyses[0]
            preferred = self.catalog.closest_designation(
                self._current_data(self.standard),
                2.0 * float(first["radius"]),
                internal=not bool(first["external"]),
            )
        self._refresh_sizes(preferred)
        self._refresh_classes()
        self._update_callout()

    def _size_changed(self, *args):
        del args
        self._refresh_classes()
        self._update_callout()

    def _refresh_sizes(self, preferred=None):
        values = self.catalog.sizes(self._current_data(self.standard))
        self._set_combo_values(self.size, values, preferred)

    def _refresh_classes(self, preferred=None):
        values = self.catalog.classes(
            self._current_data(self.standard), self._current_data(self.size)
        )
        self._set_combo_values(self.thread_class, values, preferred)

    def _spec(self):
        return self.catalog.spec(
            self._current_data(self.standard),
            self._current_data(self.size),
            self._current_data(self.thread_class),
        )

    def _update_callout(self, *args):
        del args
        try:
            spec = self._spec()
            callout = _thread_callout(
                spec["standard"],
                spec["designation"],
                spec["thread_class"],
                spec["pitch"],
                self.direction.currentText(),
            )
            selected_diameters = ", ".join(
                "{:.4g}".format(2.0 * row["radius"]) for row in self.analyses[:4]
            )
            self.specification.setText(
                "{}\nNominal Ø {:.4g} mm; pitch {:.4g} mm. Selected Ø: {} mm".format(
                    callout, spec["diameter"], spec["pitch"], selected_diameters
                )
            )
        except Exception as exc:
            self.specification.setText("Thread specification unavailable: {}".format(exc))

    def _extent_changed(self, *args):
        del args
        modeled = self.modeled.isChecked()
        full = self.full_length.isChecked()
        if full:
            self.offset.blockSignals(True)
            self.offset.setValue(0.0)
            self.offset.blockSignals(False)
        self.length.setEnabled(modeled and not full)
        self.offset.setEnabled(modeled and not full)
        self.start_side.setEnabled(modeled and not full)

    def _modeled_changed(self, *args):
        del args
        enabled = self.modeled.isChecked()
        for widget in (
            self.full_length,
            self.clearance,
            self.refine,
        ):
            widget.setEnabled(enabled)
        self._extent_changed()

    def settings(self):
        spec = self._spec()
        direction = self.direction.currentText()
        callout = _thread_callout(
            spec["standard"],
            spec["designation"],
            spec["thread_class"],
            spec["pitch"],
            direction,
        )
        return {
            "standard": spec["standard"],
            "designation": spec["designation"],
            "thread_class": spec["thread_class"],
            "pitch": spec["pitch"],
            "diameter": spec["diameter"],
            "direction": direction,
            "face_type": self.mode.currentText(),
            "modeled": self.modeled.isChecked(),
            "full_length": self.full_length.isChecked(),
            "length": self.length.value(),
            "offset": self.offset.value(),
            "start_side": self.start_side.currentText(),
            "clearance": self.clearance.value(),
            "refine": self.refine.isChecked(),
            "callout": callout,
        }

    def accept(self):
        try:
            values = self.settings()
            shortest = min(row["span"] for row in self.analyses)
            if values["modeled"] and not values["full_length"]:
                if values["offset"] + values["length"] > shortest + 1e-7:
                    raise ValueError("Thread offset plus length exceeds the shortest selected face.")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Thread", str(exc))
            return
        super(StandaloneThreadDialog, self).accept()


class FusionThreadFeatureProxy(object):
    """Persistent Part Design subtractive thread feature."""

    def __init__(self, obj=None):
        if obj is not None:
            self.attach(obj)

    def attach(self, obj):
        if "FusionThreadVersion" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyInteger",
                "FusionThreadVersion",
                "Thread",
                "Fusion-like thread feature schema version",
            )
        if "SourceFeature" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyLink",
                "SourceFeature",
                "Thread",
                "Solid feature before this thread operation",
            )
        if "ThreadFaces" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyLinkSubList",
                "ThreadFaces",
                "Thread",
                "Cylindrical faces receiving the thread",
            )
        for name, label in (
            ("ThreadStandard", "Thread standard"),
            ("ThreadDesignation", "Thread designation"),
            ("ThreadClassName", "Thread class"),
            ("ThreadCallout", "Drawing callout"),
            ("Status", "Execution status"),
        ):
            if name not in obj.PropertiesList:
                obj.addProperty("App::PropertyString", name, "Thread", label)
        for name, label in (
            ("Pitch", "Thread pitch"),
            ("NominalDiameter", "Nominal major diameter"),
            ("Length", "Modeled thread length"),
            ("Offset", "Offset from selected end"),
            ("RadialClearance", "Additional radial clearance"),
        ):
            if name not in obj.PropertiesList:
                obj.addProperty("App::PropertyLength", name, "Thread", label)
        for name, label in (
            ("Modeled", "Create actual helical geometry"),
            ("FullLength", "Use the full cylindrical face length"),
            ("RefineThread", "Refine the boolean result"),
        ):
            if name not in obj.PropertiesList:
                obj.addProperty("App::PropertyBool", name, "Thread", label)
        if "Direction" not in obj.PropertiesList:
            obj.addProperty("App::PropertyEnumeration", "Direction", "Thread", "Thread hand")
            obj.Direction = ["Right hand", "Left hand"]
        if "FaceType" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyEnumeration", "FaceType", "Thread", "Internal/external classification"
            )
            obj.FaceType = ["Auto", "Internal", "External"]
        if "StartSide" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyEnumeration", "StartSide", "Thread", "End from which length/offset is measured"
            )
            obj.StartSide = ["Low end", "High end"]
        obj.FusionThreadVersion = THREAD_FEATURE_VERSION
        obj.Proxy = self
        for name in (
            "FusionThreadVersion",
            "SourceFeature",
            "ThreadCallout",
            "Pitch",
            "NominalDiameter",
            "Status",
        ):
            try:
                obj.setEditorMode(name, 1)
            except Exception:
                pass

    def dumps(self):
        return {"version": THREAD_FEATURE_VERSION}

    def loads(self, state):
        del state
        return None

    def onDocumentRestored(self, obj):
        self.attach(obj)

    def execute(self, fp):
        try:
            self._execute_feature(fp)
        except Exception as exc:
            try:
                fp.Status = "ERROR: {}".format(exc)
            except Exception:
                pass
            raise

    def _execute_feature(self, fp):
        source = getattr(fp, "SourceFeature", None)
        if source is None or not hasattr(source, "Shape"):
            raise ValueError("Thread source feature is missing.")
        base = source.Shape.copy()
        if base.isNull():
            raise ValueError("Thread source shape is empty.")
        if not bool(fp.Modeled):
            fp.Shape = base
            status = "Cosmetic thread: {}".format(fp.ThreadCallout)
            if str(fp.Status) != status:
                fp.Status = status
            return

        refs = list(getattr(fp, "ThreadFaces", []) or [])
        if not refs:
            raise ValueError("No cylindrical thread faces are linked.")
        pitch = _quantity_value(fp.Pitch)
        if pitch <= 0.0:
            raise ValueError("Thread pitch must be positive.")
        result = base
        modeled_count = 0
        for linked, sub_names in refs:
            if linked is None:
                continue
            if isinstance(sub_names, str):
                sub_names = [sub_names]
            for sub_name in list(sub_names or []):
                analysis = _analyze_cylindrical_face(linked, sub_name)
                length = analysis["span"] if bool(fp.FullLength) else _quantity_value(fp.Length)
                cutter, internal = _make_thread_cutter(
                    analysis,
                    pitch,
                    str(fp.ThreadStandard),
                    length,
                    _quantity_value(fp.Offset),
                    str(fp.StartSide),
                    str(fp.Direction),
                    str(fp.FaceType),
                    _quantity_value(fp.RadialClearance),
                )
                cut_result = result.cut(cutter)
                if cut_result.isNull():
                    raise ValueError("The modeled thread cut returned an empty result.")
                result = cut_result
                modeled_count += 1
        if modeled_count == 0:
            raise ValueError("No valid cylindrical faces were available for the thread.")
        if bool(fp.RefineThread):
            try:
                result = result.removeSplitter()
            except Exception:
                pass
        fp.Shape = result
        status = "Modeled {} face(s): {}".format(modeled_count, fp.ThreadCallout)
        if str(fp.Status) != status:
            fp.Status = status


class FusionHoleCommand(object):
    def GetResources(self):
        return {
            "Pixmap": "PartDesign_Hole",
            "MenuText": "Hole & Thread",
            "ToolTip": "Create or edit a Fusion-style threaded Hole using native FreeCAD geometry",
            "Accel": "H",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        open_fusion_hole()


class FusionThreadCommand(object):
    def GetResources(self):
        return {
            "Pixmap": "PartDesign_SubtractiveHelix",
            "MenuText": "Thread",
            "ToolTip": "Create or edit an independent modeled/cosmetic thread on cylindrical faces",
            "Accel": "Shift+T",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        open_fusion_thread()


class DrawingSourceDialog(QtWidgets.QDialog):
    """Choose a TechDraw page and model sources for a dimensionable vector view."""

    def __init__(self, document, pages, candidates, selected_names=None, selected_page=None, parent=None):
        super(DrawingSourceDialog, self).__init__(parent)
        self.document = document
        self.setWindowTitle("Insert Dimensionable Model View")
        self.resize(560, 520)

        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "This creates a model-linked TechDraw view with selectable edges and vertices. "
            "Use it for dimensions. ‘Active View Snapshot’ is a raster image and is not dimensionable.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        page_row = QtWidgets.QHBoxLayout()
        page_row.addWidget(QtWidgets.QLabel("Drawing sheet:", self))
        self.page_combo = QtWidgets.QComboBox(self)
        self.page_combo.addItem("Create a new default sheet", "")
        selected_page_name = getattr(selected_page, "Name", "") if selected_page is not None else ""
        for page in pages:
            self.page_combo.addItem(str(page.Label), str(page.Name))
            if page.Name == selected_page_name:
                self.page_combo.setCurrentIndex(self.page_combo.count() - 1)
        page_row.addWidget(self.page_combo, 1)
        layout.addLayout(page_row)

        layout.addWidget(QtWidgets.QLabel("3D part, Body, component, or assembly to draw:", self))
        self.source_list = QtWidgets.QListWidget(self)
        self.source_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.source_list.setAlternatingRowColors(True)
        chosen = set(selected_names or [])
        first_selected = None
        for obj in candidates:
            label = "{}    [{}]".format(str(obj.Label), str(obj.TypeId))
            view_object = getattr(obj, "ViewObject", None)
            icon = QIcon()
            try:
                icon_value = getattr(view_object, "Icon", None)
                if isinstance(icon_value, QIcon):
                    icon = icon_value
                elif icon_value:
                    icon = QIcon(str(icon_value))
            except Exception:
                pass
            item = QtWidgets.QListWidgetItem(icon, label)
            _set_item_user_data(item, str(obj.Name))
            item.setToolTip("{}\n{}".format(obj.Name, obj.TypeId))
            self.source_list.addItem(item)
            if obj.Name in chosen:
                item.setSelected(True)
                if first_selected is None:
                    first_selected = item
        if first_selected is not None:
            self.source_list.scrollToItem(first_selected)
        elif self.source_list.count() == 1:
            self.source_list.item(0).setSelected(True)
        layout.addWidget(self.source_list, 1)

        note = QtWidgets.QLabel(
            "After this dialog, FreeCAD’s native base/projected-view task opens. "
            "Choose the projection orientation and any projected views there. "
            "To dimension, click model edges or vertices on the drawing sheet—not the raster snapshot and not only the tree item.",
            self,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept_checked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_checked(self):
        if not self.source_list.selectedItems():
            QtWidgets.QMessageBox.warning(
                self,
                "Insert Model View",
                "Select at least one 3D source object. A drawing Page or an existing TechDraw view is not a model source.",
            )
            return
        self.accept()

    def selected_source_names(self):
        return [str(_item_user_data(item)) for item in self.source_list.selectedItems()]

    def selected_page_name(self):
        return str(self.page_combo.currentData() or "")


class CommandPalette(QtWidgets.QDialog):
    """Search and trigger any registered FreeCAD QAction."""

    def __init__(self, profile):
        super(CommandPalette, self).__init__(profile.mw)
        self.profile = profile
        self.entries = []

        flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
        self.setWindowFlags(flags)
        self.setObjectName("FusionLike_CommandPaletteDialog")
        self.setWindowTitle("Command Search")
        self.resize(620, 430)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        self.search = QtWidgets.QLineEdit(self)
        self.search.setPlaceholderText("Search commands — Fusion-style shortcut: S")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self.results = QtWidgets.QListWidget(self)
        self.results.setAlternatingRowColors(True)
        self.results.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.results, 1)

        hint = QtWidgets.QLabel("Enter: run command    Esc: close", self)
        layout.addWidget(hint)

        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._run_current)
        self.results.itemActivated.connect(self._run_item)
        self.results.itemDoubleClicked.connect(self._run_item)

    def _collect(self):
        entries = []
        seen = set()
        for action in self.profile.mw.findChildren(QAction):
            if action.isSeparator():
                continue
            command_id = str(action.objectName() or "")
            label = _strip_action_text(action.text())
            if not label:
                continue
            if command_id == "FusionLike_CommandPalette":
                continue
            # FreeCAD command actions normally have an object name. Empty-name
            # menu actions create many duplicates, so skip them.
            if not command_id:
                continue
            key = (command_id, label)
            if key in seen:
                continue
            seen.add(key)
            haystack = "{} {}".format(label, command_id).lower()
            entries.append((label, command_id, haystack, action))

        entries.sort(key=lambda row: (row[0].lower(), row[1].lower()))
        self.entries = entries

    def open_palette(self):
        self._collect()
        self.search.clear()
        self._filter("")

        frame = self.profile.mw.frameGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(frame.center())
        self.move(geo.topLeft())
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def _filter(self, text):
        needle = (text or "").strip().lower()
        words = [word for word in needle.split() if word]
        self.results.clear()
        for index, (label, command_id, haystack, action) in enumerate(self.entries):
            if words and not all(word in haystack for word in words):
                continue
            item = QtWidgets.QListWidgetItem(action.icon(), label)
            item.setToolTip(command_id)
            _set_item_user_data(item, index)
            if not action.isEnabled():
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def _run_current(self):
        item = self.results.currentItem()
        if item is not None:
            self._run_item(item)

    def _run_item(self, item):
        if item is None or not (item.flags() & QtCore.Qt.ItemIsEnabled):
            return
        index = int(_item_user_data(item))
        if not 0 <= index < len(self.entries):
            return
        action = self.entries[index][3]
        self.hide()
        QtCore.QTimer.singleShot(0, action.trigger)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super(CommandPalette, self).keyPressEvent(event)


class FusionProfile(QtCore.QObject):
    """Owns the reversible UI profile and its runtime helpers."""

    WORKSPACES = (
        ("DESIGN", ("PartDesignWorkbench",)),
        ("SURFACE", ("SurfaceWorkbench",)),
        ("MESH", ("MeshWorkbench",)),
        ("SHEET METAL", ("SheetMetalWorkbench",)),
        ("ASSEMBLE", ("AssemblyWorkbench", "Assembly4Workbench", "A2plusWorkbench")),
        ("DRAWING", ("TechDrawWorkbench",)),
        ("MANUFACTURE", ("CAMWorkbench", "PathWorkbench")),
        ("RENDER", ("RenderWorkbench", "RaytracingWorkbench")),
    )

    KEY_COMMANDS = {
        QtCore.Qt.Key_F: ("PartDesign_Fillet", "Sketcher_CreateFillet"),
        QtCore.Qt.Key_M: ("Std_TransformManip", "Sketcher_Translate"),
        QtCore.Qt.Key_V: ("Std_ToggleVisibility",),
        QtCore.Qt.Key_I: ("Std_Measure",),
        QtCore.Qt.Key_L: ("Sketcher_CreateLine",),
        QtCore.Qt.Key_R: ("Sketcher_CreateRectangle",),
        QtCore.Qt.Key_C: ("Sketcher_CreateCircle",),
        QtCore.Qt.Key_T: ("Sketcher_Trimming",),
        QtCore.Qt.Key_O: ("Sketcher_Offset",),
        QtCore.Qt.Key_D: ("Sketcher_Dimension", "Sketcher_ConstrainDistance"),
        QtCore.Qt.Key_X: ("Sketcher_ToggleConstruction",),
    }

    def __init__(self):
        self.mw = Gui.getMainWindow()
        super(FusionProfile, self).__init__(self.mw)
        self.pref = App.ParamGet(PREF_PATH)
        self.view_pref = App.ParamGet(VIEW_PREF_PATH)
        self.sketcher_pref = App.ParamGet(SKETCHER_PREF_PATH)
        self.app = QtWidgets.QApplication.instance()
        self.active = False
        self.toolbars = []
        self.timeline_dock = None
        self.timeline_list = None
        self.workspace_combo = None
        self.palette = None
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setInterval(800)
        self.refresh_timer.timeout.connect(self._refresh_timeline_if_needed)
        self.context_timer = QtCore.QTimer(self)
        self.context_timer.setInterval(250)
        self.context_timer.timeout.connect(self._refresh_ui_context_if_needed)
        self.joint_diagnostic_timer = QtCore.QTimer(self)
        self.joint_diagnostic_timer.setInterval(300)
        self.joint_diagnostic_timer.timeout.connect(self._refresh_joint_diagnostics_panel)
        self.timeline_signature = None
        self.ui_context_signature = None
        self.rebuilding_toolbars = False
        self.current_workbench = ""
        self.assembly_clipboard_rows = []
        self.assembly_paste_serial = 0
        self.pending_joint_type = ""
        self.joint_diagnostic_seen_task = False
        self.joint_diagnostic_wait_ticks = 0
        self.joint_diagnostic_panel = None
        self.joint_diagnostic_label = None
        self.last_assembly_diagnostic_report = ""
        self.last_assembly_solver_code = None
        self.projection_observer = None
        self.projection_view = None
        self.projection_mouse_callback = None
        self.projection_target = None
        self.projection_defining = True
        self.projection_intersection = False
        self.projection_busy = False
        self.projection_pending = set()

    # ---------- reversible profile state ----------

    def _capture_original_state(self):
        # v1.0 did not capture this Sketcher preference. Preserve it once during
        # an in-place upgrade before the profile switches defining projection on.
        if not self.pref.GetBool("OriginalSketcherProjectionStateCaptured", False):
            self.pref.SetBool(
                "OriginalAlwaysExtGeoReference",
                self.sketcher_pref.GetBool("AlwaysExtGeoReference", False),
            )
            self.pref.SetBool("OriginalSketcherProjectionStateCaptured", True)

        if self.pref.GetBool("OriginalStateCaptured", False):
            return

        try:
            encoded = bytes(self.mw.saveState(STATE_VERSION).toBase64()).decode("ascii")
        except Exception:
            encoded = base64.b64encode(bytes(self.mw.saveState(STATE_VERSION))).decode("ascii")

        self.pref.SetString("OriginalMainWindowState", encoded)
        self.pref.SetString("OriginalWorkbench", _active_workbench_name())
        self.pref.SetString(
            "OriginalNavigationStyle",
            self.view_pref.GetString("NavigationStyle", "Gui::CADNavigationStyle"),
        )
        self.pref.SetInt("OriginalOrbitStyle", self.view_pref.GetInt("OrbitStyle", 4))
        self.pref.SetBool(
            "OriginalSameStyleForAllViews",
            self.view_pref.GetBool("SameStyleForAllViews", True),
        )
        self.pref.SetBool("OriginalShowNaviCube", self.view_pref.GetBool("ShowNaviCube", True))
        self.pref.SetBool("OriginalStateCaptured", True)

    def apply(self):
        self._capture_original_state()
        self.pref.SetBool("Enabled", True)
        self._set_fusion_navigation()
        # In FreeCAD 1.1 normal external projection can be defining geometry.
        # Keep the global preference in that mode while this profile is active.
        self.sketcher_pref.SetBool("AlwaysExtGeoReference", False)

        # Reopen the last Fusion-like workspace when it still exists. Part
        # Design remains the safe default and ensures Sketcher/Part Design
        # commands are registered on a first installation.
        try:
            available = Gui.listWorkbenches()
            target = self.pref.GetString("LastWorkbench", "PartDesignWorkbench")
            if target not in available:
                target = "PartDesignWorkbench"
            if target in available:
                Gui.activateWorkbench(target)
        except Exception:
            _console("Could not activate the saved workspace; keeping the current workbench.", warning=True)

        QtCore.QTimer.singleShot(250, self._finish_apply)

    def _finish_apply(self):
        try:
            self._remove_runtime_widgets()
            self._arrange_docks()
            self._build_toolbars()
            self._build_timeline()
            self._hide_native_toolbars()

            filter_target = self.app or self.mw
            try:
                filter_target.removeEventFilter(self)
            except Exception:
                pass
            filter_target.installEventFilter(self)
            self.refresh_timer.start()
            self.context_timer.start()
            self.active = True
            self.ui_context_signature = self._ui_context_signature_value()
            self._refresh_timeline(force=True)
            self.mw.statusBar().showMessage(
                "Fusion-like profile active — Sketch mode is contextual; Drawing uses Insert Model View; Assembly Ctrl+C/V duplicates instances",
                7000,
            )
        except Exception:
            _console("Profile application failed:\n{}".format(traceback.format_exc()), warning=True)

    def restore(self):
        self.pref.SetBool("Enabled", False)
        self.active = False
        self.refresh_timer.stop()
        self.context_timer.stop()
        self.joint_diagnostic_timer.stop()
        self._remove_assembly_task_diagnostics_patch()
        filter_target = self.app or self.mw
        try:
            filter_target.removeEventFilter(self)
        except Exception:
            pass
        self._remove_runtime_widgets()

        if self.pref.GetBool("OriginalSketcherProjectionStateCaptured", False):
            self.sketcher_pref.SetBool(
                "AlwaysExtGeoReference",
                self.pref.GetBool("OriginalAlwaysExtGeoReference", False),
            )

        if self.pref.GetBool("OriginalStateCaptured", False):
            self.view_pref.SetBool(
                "SameStyleForAllViews",
                self.pref.GetBool("OriginalSameStyleForAllViews", True),
            )
            self.view_pref.SetString(
                "NavigationStyle",
                self.pref.GetString("OriginalNavigationStyle", "Gui::CADNavigationStyle"),
            )
            self.view_pref.SetInt("OrbitStyle", self.pref.GetInt("OriginalOrbitStyle", 4))
            self.view_pref.SetBool(
                "ShowNaviCube", self.pref.GetBool("OriginalShowNaviCube", True)
            )
            original_wb = self.pref.GetString("OriginalWorkbench", "")
            try:
                if original_wb and original_wb in Gui.listWorkbenches():
                    Gui.activateWorkbench(original_wb)
            except Exception:
                pass

            encoded = self.pref.GetString("OriginalMainWindowState", "")
            if encoded:
                try:
                    state = QtCore.QByteArray.fromBase64(encoded.encode("ascii"))
                    self.mw.restoreState(state, STATE_VERSION)
                except Exception:
                    _console("Could not restore the saved Qt layout state.", warning=True)

        self.mw.statusBar().showMessage("Original FreeCAD interface restored", 5000)

    def rebuild(self):
        if not self.active:
            self.apply()
            return
        self._finish_apply()

    # ---------- navigation and docks ----------

    def _set_fusion_navigation(self):
        # Revit navigation is the native FreeCAD style whose primary controls
        # match Fusion: MMB pan, Shift+MMB orbit, wheel zoom.
        self.view_pref.SetBool("SameStyleForAllViews", True)
        self.view_pref.SetString("NavigationStyle", "Gui::RevitNavigationStyle")
        self.view_pref.SetInt("OrbitStyle", 0)  # Turntable/upright orbit
        self.view_pref.SetBool("ShowNaviCube", True)

    def _arrange_docks(self):
        dock_type = QtWidgets.QDockWidget
        docks = self.mw.findChildren(dock_type)
        combo = None
        tree = None
        task = None

        for dock in docks:
            descriptor = "{} {}".format(dock.objectName(), dock.windowTitle()).lower()
            if "combo" in descriptor and "view" in descriptor:
                combo = dock
            elif "tree" in descriptor and "view" in descriptor:
                tree = dock
            elif "task" in descriptor and "view" in descriptor:
                task = dock

            if any(token in descriptor for token in ("python console", "report view", "selection view")):
                dock.hide()

        browser = combo or tree
        if browser is not None:
            browser.setFloating(False)
            self.mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, browser)
            browser.show()
            try:
                self.mw.resizeDocks([browser], [300], QtCore.Qt.Horizontal)
            except Exception:
                pass

        # A standalone task panel is useful on the right, like Fusion's
        # contextual command panels. Combo View already includes Tasks.
        if combo is None and task is not None:
            task.setFloating(False)
            self.mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, task)
            task.show()

    # ---------- toolbars and workspace selector ----------

    def _remove_runtime_widgets(self):
        self.end_projection_mode(silent=True)
        self.joint_diagnostic_timer.stop()
        self.joint_diagnostic_panel = None
        self.joint_diagnostic_label = None
        for toolbar in list(self.mw.findChildren(QtWidgets.QToolBar)):
            if str(toolbar.objectName()).startswith(TOOLBAR_PREFIX):
                self.mw.removeToolBar(toolbar)
                toolbar.deleteLater()
        self.toolbars = []
        self.workspace_combo = None

        if self.palette is not None:
            self.palette.hide()
            self.palette.deleteLater()
            self.palette = None

        dock = self.mw.findChild(QtWidgets.QDockWidget, TIMELINE_NAME)
        if dock is not None:
            self.mw.removeDockWidget(dock)
            dock.deleteLater()
        self.timeline_dock = None
        self.timeline_list = None
        self.timeline_signature = None

    def _make_toolbar(self, object_name, title, style=None):
        toolbar = QtWidgets.QToolBar(title, self.mw)
        toolbar.setObjectName(object_name)
        toolbar.setAllowedAreas(QtCore.Qt.TopToolBarArea)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QtCore.QSize(26, 26))
        toolbar.setToolButtonStyle(style or QtCore.Qt.ToolButtonTextUnderIcon)
        self.mw.addToolBar(QtCore.Qt.TopToolBarArea, toolbar)
        self.toolbars.append(toolbar)
        return toolbar

    def _section_label(self, toolbar, text):
        label = QtWidgets.QLabel(" {} ".format(text), toolbar)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        label.setAlignment(QtCore.Qt.AlignCenter)
        toolbar.addWidget(label)
        toolbar.addSeparator()

    def _find_action(self, command_id):
        action = self.mw.findChild(QAction, command_id)
        if action is not None:
            return action
        for candidate in self.mw.findChildren(QAction):
            if str(candidate.objectName()) == command_id:
                return candidate
        return None

    def _add_command(self, toolbar, command_id):
        action = self._find_action(command_id)
        if action is not None:
            toolbar.addAction(action)
            return action
        return None

    def _add_first_command(self, toolbar, command_ids):
        """Add the first registered command from a compatibility fallback list."""
        for command_id in command_ids:
            action = self._add_command(toolbar, command_id)
            if action is not None:
                return action
        return None

    def _proxy_action(self, parent, label, original):
        proxy = QAction(original.icon(), label, parent)
        proxy.setToolTip(original.toolTip())
        proxy.setEnabled(original.isEnabled())
        proxy.triggered.connect(lambda checked=False, action=original: action.trigger())
        return proxy

    def _add_dropdown(self, toolbar, label, command_rows, icon_command=None):
        available = []
        for row_label, command_id in command_rows:
            action = self._find_action(command_id)
            if action is not None:
                available.append((row_label, action))
        if not available:
            return None

        button = QtWidgets.QToolButton(toolbar)
        button.setObjectName("{}Dropdown_{}".format(TOOLBAR_PREFIX, re.sub(r"\W+", "", label)))
        button.setText(label)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        icon_source = self._find_action(icon_command) if icon_command else available[0][1]
        if icon_source is not None:
            button.setIcon(icon_source.icon())
        button.setIconSize(QtCore.QSize(26, 26))

        menu = QtWidgets.QMenu(button)
        pairs = []
        for row_label, original in available:
            proxy = self._proxy_action(menu, row_label, original)
            menu.addAction(proxy)
            pairs.append((proxy, original))

        def sync_menu():
            for proxy, original in pairs:
                proxy.setEnabled(original.isEnabled())

        menu.aboutToShow.connect(sync_menu)
        button.setMenu(menu)
        button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        toolbar.addWidget(button)
        return button

    def _callback_action(self, parent, label, callback, object_name, tooltip="", icon=None):
        action = QAction(icon or QIcon(), label, parent)
        action.setObjectName(object_name)
        if tooltip:
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
        action.triggered.connect(lambda checked=False, fn=callback: fn())
        return action

    def _add_callback_command(
        self, toolbar, label, callback, object_name, tooltip="", icon_command=None
    ):
        icon_source = self._find_action(icon_command) if icon_command else None
        action = self._callback_action(
            toolbar,
            label,
            callback,
            object_name,
            tooltip,
            icon_source.icon() if icon_source is not None else QIcon(),
        )
        toolbar.addAction(action)
        return action

    def _add_callback_dropdown(self, toolbar, label, rows, icon_command=None):
        """Add a Fusion-style dropdown whose rows call Python workflow helpers."""
        button = QtWidgets.QToolButton(toolbar)
        button.setObjectName("{}Dropdown_{}".format(TOOLBAR_PREFIX, re.sub(r"\W+", "", label)))
        button.setText(label)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        icon_source = self._find_action(icon_command) if icon_command else None
        if icon_source is not None:
            button.setIcon(icon_source.icon())
        button.setIconSize(QtCore.QSize(26, 26))

        menu = QtWidgets.QMenu(button)
        for row_label, callback, object_name, tooltip in rows:
            icon = icon_source.icon() if icon_source is not None else QIcon()
            menu.addAction(
                self._callback_action(menu, row_label, callback, object_name, tooltip, icon)
            )
        button.setMenu(menu)
        button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        toolbar.addWidget(button)
        return button


    def _clear_profile_toolbars(self):
        for toolbar in list(self.mw.findChildren(QtWidgets.QToolBar)):
            if str(toolbar.objectName()).startswith(TOOLBAR_PREFIX):
                self.mw.removeToolBar(toolbar)
                toolbar.deleteLater()
        self.toolbars = []
        self.workspace_combo = None

    def _build_quick_toolbar(self):
        quick = self._make_toolbar(
            "FusionLike_Quick", "Fusion-like: Workspace", QtCore.Qt.ToolButtonTextBesideIcon
        )
        self.workspace_combo = QtWidgets.QComboBox(quick)
        self.workspace_combo.setObjectName("FusionLike_WorkspaceSelector")
        self.workspace_combo.setMinimumWidth(145)
        self.workspace_combo.setToolTip("Fusion-style workspace selector")
        self._populate_workspaces()
        quick.addWidget(self.workspace_combo)
        quick.addSeparator()
        for command_id in ("Std_New", "Std_Open", "Std_Save", "Std_Undo", "Std_Redo"):
            self._add_command(quick, command_id)
        palette_action = QAction("Command Search", quick)
        palette_action.setObjectName("FusionLike_CommandPalette")
        search_icon = self._find_action("Std_DlgCustomize") or self._find_action("Std_ViewStatusBar")
        if search_icon is not None:
            palette_action.setIcon(search_icon.icon())
        palette_action.setToolTip("Search all commands (S)")
        palette_action.triggered.connect(self.show_palette)
        quick.addAction(palette_action)

    def _build_design_toolbars(self):
        create = self._make_toolbar("FusionLike_Create", "Fusion-like: Create")
        self._section_label(create, "CREATE")
        self._add_command(create, "PartDesign_Body")
        self._add_command(create, "PartDesign_NewSketch")
        self._add_callback_dropdown(
            create,
            "Project / Include",
            (
                (
                    "Project selected / pick faces (P)",
                    self.project_profile,
                    "FusionLike_ProjectProfile",
                    "Project faces, edges, or a previous sketch as live defining geometry",
                ),
                (
                    "Project as reference (Shift+P)",
                    self.project_reference,
                    "FusionLike_ProjectReference",
                    "Project linked construction/reference geometry",
                ),
                (
                    "Intersect with sketch plane",
                    self.project_intersection,
                    "FusionLike_ProjectIntersection",
                    "Create linked defining intersections with the active sketch plane",
                ),
                (
                    "Carbon Copy another sketch",
                    lambda: self._run_command("Sketcher_CarbonCopy"),
                    "FusionLike_CarbonCopy",
                    "Copy another sketch with native Sketcher Carbon Copy",
                ),
                (
                    "End projection picking (Esc)",
                    self.end_projection_mode,
                    "FusionLike_EndProjection",
                    "End the continuous face/edge picking session",
                ),
            ),
            "Sketcher_Projection",
        )
        self._add_callback_dropdown(
            create,
            "Extrude",
            (
                (
                    "Add / Pad",
                    lambda: self.start_extrude("PartDesign_Pad"),
                    "FusionLike_ExtrudeAdd",
                    "Finish the active sketch when needed and create a Pad",
                ),
                (
                    "Cut / Pocket",
                    lambda: self.start_extrude("PartDesign_Pocket"),
                    "FusionLike_ExtrudeCut",
                    "Finish the active sketch when needed and create a Pocket",
                ),
            ),
            "PartDesign_Pad",
        )
        self._add_dropdown(
            create,
            "Hole",
            (
                ("Hole & Thread (Fusion-style)", HOLE_COMMAND_ID),
                ("Native FreeCAD Hole", "PartDesign_Hole"),
            ),
            "PartDesign_Hole",
        )
        self._add_command(create, THREAD_COMMAND_ID)
        self._add_dropdown(
            create,
            "Revolve",
            (("Add / Revolution", "PartDesign_Revolution"), ("Cut / Groove", "PartDesign_Groove")),
            "PartDesign_Revolution",
        )
        self._add_dropdown(
            create,
            "Loft",
            (("Additive Loft", "PartDesign_AdditiveLoft"), ("Subtractive Loft", "PartDesign_SubtractiveLoft")),
            "PartDesign_AdditiveLoft",
        )
        self._add_dropdown(
            create,
            "Sweep",
            (("Additive Pipe", "PartDesign_AdditivePipe"), ("Subtractive Pipe", "PartDesign_SubtractivePipe")),
            "PartDesign_AdditivePipe",
        )

        modify = self._make_toolbar("FusionLike_Modify", "Fusion-like: Modify")
        self._section_label(modify, "MODIFY")
        for command_id in (
            "PartDesign_Fillet",
            "PartDesign_Chamfer",
            "PartDesign_Draft",
            "PartDesign_Thickness",
        ):
            self._add_command(modify, command_id)
        self._add_dropdown(
            modify,
            "Press/Pull",
            (
                ("Add / Pad", "PartDesign_Pad"),
                ("Cut / Pocket", "PartDesign_Pocket"),
                ("Shell / Thickness", "PartDesign_Thickness"),
                ("Draft Faces", "PartDesign_Draft"),
            ),
            "PartDesign_Pad",
        )
        self._add_command(modify, "Std_TransformManip")
        self._add_command(modify, "PartDesign_Mirrored")
        self._add_dropdown(
            modify,
            "Pattern",
            (("Linear Pattern", "PartDesign_LinearPattern"), ("Circular Pattern", "PartDesign_PolarPattern")),
            "PartDesign_LinearPattern",
        )

        inspect = self._make_toolbar("FusionLike_Inspect", "Fusion-like: Construct and Inspect")
        self._section_label(inspect, "CONSTRUCT / INSPECT")
        for command_id in (
            "Part_DatumPlane",
            "Part_DatumLine",
            "Part_DatumPoint",
            "Part_CoordinateSystem",
            "Std_Measure",
            "Std_MassProperties",
            "Part_CheckGeometry",
            "Std_ViewFitAll",
            "Std_ViewIsometric",
            "Std_ToggleVisibility",
        ):
            self._add_command(inspect, command_id)


    def _build_sketch_toolbars(self):
        finish = self._make_toolbar(
            "FusionLike_SketchFinish", "Fusion-like: Finish Sketch", QtCore.Qt.ToolButtonTextBesideIcon
        )
        self._section_label(finish, "SKETCH")
        for command_id in (
            "Sketcher_LeaveSketch",
            "Sketcher_CancelSketch",
            "Sketcher_ViewSketch",
            "Sketcher_ViewSection",
            "Sketcher_StopOperation",
        ):
            self._add_command(finish, command_id)

        create = self._make_toolbar("FusionLike_SketchCreate", "Fusion-like: Sketch Create")
        self._section_label(create, "CREATE")
        for command_ids in (
            ("Sketcher_CompLine", "Sketcher_CreatePolyline", "Sketcher_CreateLine"),
            ("Sketcher_CompCreateRectangles", "Sketcher_CreateRectangle", "Sketcher_CreateRectangle_Center"),
            ("Sketcher_CompCreateArc", "Sketcher_CreateArc", "Sketcher_Create3PointArc"),
            ("Sketcher_CreateCircle", "Sketcher_Create3PointCircle"),
            ("Sketcher_CompCreateConic", "Sketcher_CreateEllipseByCenter", "Sketcher_CreateEllipseBy3Points"),
            ("Sketcher_CompSlot", "Sketcher_CreateSlot", "Sketcher_CreateArcSlot"),
            ("Sketcher_CreatePoint",),
            ("Sketcher_CreateText",),
            ("Sketcher_ToggleConstruction",),
        ):
            self._add_first_command(create, command_ids)
        self._add_callback_dropdown(
            create,
            "Project / Include",
            (
                (
                    "Project selected / pick faces (P)",
                    self.project_profile,
                    "FusionLike_SketchProjectProfile",
                    "Project faces, edges, or a previous sketch as live defining geometry",
                ),
                (
                    "Project as reference (Shift+P)",
                    self.project_reference,
                    "FusionLike_SketchProjectReference",
                    "Project linked construction/reference geometry",
                ),
                (
                    "Intersect with sketch plane",
                    self.project_intersection,
                    "FusionLike_SketchProjectIntersection",
                    "Create linked defining intersections with the active sketch plane",
                ),
                (
                    "Carbon Copy another sketch",
                    lambda: self._run_command("Sketcher_CarbonCopy"),
                    "FusionLike_SketchCarbonCopy",
                    "Copy another sketch with native Sketcher Carbon Copy",
                ),
                (
                    "End projection picking (Esc)",
                    self.end_projection_mode,
                    "FusionLike_SketchEndProjection",
                    "End continuous face/edge projection picking",
                ),
            ),
            "Sketcher_Projection",
        )

        modify = self._make_toolbar("FusionLike_SketchModify", "Fusion-like: Sketch Modify")
        self._section_label(modify, "MODIFY")
        for command_ids in (
            ("Sketcher_CompCurveEdition", "Sketcher_Trimming", "Sketcher_Split", "Sketcher_Extend"),
            ("Sketcher_CompCreateFillets", "Sketcher_CreateFillet", "Sketcher_CreateChamfer"),
            ("Sketcher_Offset",),
            ("Sketcher_Translate",),
            ("Sketcher_Rotate",),
            ("Sketcher_Scale",),
            ("Sketcher_Symmetry",),
            ("Sketcher_RemoveAxesAlignment",),
            ("Sketcher_CopyClipboard",),
            ("Sketcher_Cut",),
            ("Sketcher_Paste",),
        ):
            self._add_first_command(modify, command_ids)

        constrain = self._make_toolbar("FusionLike_SketchConstrain", "Fusion-like: Sketch Constrain")
        self._section_label(constrain, "CONSTRAIN")
        for command_ids in (
            ("Sketcher_CompDimensionTools", "Sketcher_Dimension", "Sketcher_ConstrainDistance"),
            ("Sketcher_ConstrainCoincidentUnified", "Sketcher_ConstrainCoincident"),
            ("Sketcher_CompHorVer", "Sketcher_ConstrainHorVer", "Sketcher_ConstrainHorizontal"),
            ("Sketcher_ConstrainParallel",),
            ("Sketcher_ConstrainPerpendicular",),
            ("Sketcher_ConstrainTangent",),
            ("Sketcher_ConstrainEqual",),
            ("Sketcher_ConstrainSymmetric",),
            ("Sketcher_ConstrainBlock",),
            ("Sketcher_CompToggleConstraints", "Sketcher_ToggleDrivingConstraint"),
        ):
            self._add_first_command(constrain, command_ids)

        inspect = self._make_toolbar("FusionLike_SketchInspect", "Fusion-like: Sketch Inspect")
        self._section_label(inspect, "INSPECT")
        for command_id in (
            "Sketcher_SelectElementsWithDoFs",
            "Sketcher_SelectConflictingConstraints",
            "Sketcher_SelectRedundantConstraints",
            "Sketcher_SelectConstraints",
            "Sketcher_ArcOverlay",
            "Sketcher_RestoreInternalAlignmentGeometry",
            "Sketcher_SwitchVirtualSpace",
            "Sketcher_ValidateSketch",
        ):
            self._add_command(inspect, command_id)

    def _build_assembly_toolbars(self):
        self._install_assembly_task_diagnostics_patch()
        assemble = self._make_toolbar("FusionLike_Assembly", "Fusion-like: Assemble")
        self._section_label(assemble, "ASSEMBLE")
        for command_id in ("Assembly_CreateAssembly", "Assembly_ActivateAssembly"):
            self._add_command(assemble, command_id)
        self._add_dropdown(
            assemble,
            "Insert",
            (
                ("Insert Existing Component", "Assembly_Insert"),
                ("Create and Insert New Part", "Assembly_InsertNewPart"),
            ),
            "Assembly_Insert",
        )
        self._add_callback_command(
            assemble,
            "Add Selected",
            self.add_selected_to_assembly,
            "FusionLike_AssemblyAddSelected",
            "Add the selected Part, Body, Link, or component as a new assembly instance at its current placement",
            "Assembly_Insert",
        )
        self._add_callback_command(
            assemble,
            "Copy",
            self.copy_assembly_components,
            "FusionLike_AssemblyCopy",
            "Copy selected component instances (Ctrl+C)",
            "Std_Copy",
        )
        self._add_callback_dropdown(
            assemble,
            "Paste / Duplicate",
            (
                (
                    "Paste new instance with offset (Ctrl+V)",
                    self.paste_assembly_components,
                    "FusionLike_AssemblyPaste",
                    "Paste copied components as unconstrained App::Link instances with a small X offset",
                ),
                (
                    "Paste in place (Ctrl+Shift+V)",
                    lambda: self.paste_assembly_components(in_place=True),
                    "FusionLike_AssemblyPasteInPlace",
                    "Paste copied components at their original placements",
                ),
                (
                    "Duplicate selected (Ctrl+D)",
                    self.duplicate_assembly_components,
                    "FusionLike_AssemblyDuplicate",
                    "Copy and immediately paste the selected component instances",
                ),
            ),
            "Std_Paste",
        )
        self._add_command(assemble, "Assembly_ToggleGrounded")
        self._add_callback_dropdown(
            assemble,
            "Solve",
            (
                (
                    "Solve and show diagnostics",
                    self.solve_assembly_with_diagnostics,
                    "FusionLike_AssemblySolveDiagnose",
                    "Solve the active assembly and decode the native solver result",
                ),
                (
                    "Native Solve",
                    lambda: self._run_command("Assembly_SolveAssembly"),
                    "FusionLike_AssemblyNativeSolve",
                    "Run FreeCAD's native Assembly solve command",
                ),
            ),
            "Assembly_SolveAssembly",
        )
        self._add_dropdown(
            assemble,
            "Inspect Solver",
            (
                ("Select Conflicting Joints", "Assembly_SelectConflictingConstraints"),
                ("Select Redundant Joints", "Assembly_SelectRedundantConstraints"),
                ("Select Malformed Joints", "Assembly_SelectMalformedConstraints"),
                ("Select Components With Free DoF", "Assembly_SelectComponentsWithDoFs"),
            ),
            "Part_CheckGeometry",
        )
        self._add_command(assemble, "Assembly_LinkSelectLinked")
        self._add_command(assemble, "Std_TransformManip")

        joints = self._make_toolbar("FusionLike_AssemblyJoints", "Fusion-like: Assembly Joints")
        self._section_label(joints, "MATE / JOINT")
        joint_defs = (
            ("Rigid / Fixed", "Assembly_CreateJointFixed", "Fixed"),
            ("Revolute", "Assembly_CreateJointRevolute", "Revolute"),
            ("Cylindrical", "Assembly_CreateJointCylindrical", "Cylindrical"),
            ("Slider", "Assembly_CreateJointSlider", "Slider"),
            ("Ball", "Assembly_CreateJointBall", "Ball"),
        )
        joint_rows = tuple(
            (
                label,
                (lambda cid=command_id, jtype=joint_type: self.start_guided_joint(cid, jtype)),
                "FusionLike_Mate_{}".format(joint_type),
                "Run the native {} joint with live selection diagnostics".format(joint_type),
            )
            for label, command_id, joint_type in joint_defs
        )
        self._add_callback_dropdown(joints, "Joint", joint_rows, "Assembly_CreateJointRevolute")
        as_built_rows = tuple(
            (
                label,
                (lambda cid=command_id, jtype=joint_type: self.start_guided_joint(cid, jtype, as_built=True)),
                "FusionLike_AsBuiltMate_{}".format(joint_type),
                "Create a native {} joint while preserving the current component arrangement as the starting condition".format(joint_type),
            )
            for label, command_id, joint_type in joint_defs
        )
        self._add_callback_dropdown(joints, "As-Built Joint", as_built_rows, "Assembly_CreateJointFixed")
        constraint_defs = (
            ("Distance", "Assembly_CreateJointDistance", "Distance"),
            ("Parallel", "Assembly_CreateJointParallel", "Parallel"),
            ("Perpendicular", "Assembly_CreateJointPerpendicular", "Perpendicular"),
            ("Angle", "Assembly_CreateJointAngle", "Angle"),
        )
        constraint_rows = tuple(
            (
                label,
                (lambda cid=command_id, jtype=joint_type: self.start_guided_joint(cid, jtype)),
                "FusionLike_Mate_{}".format(joint_type),
                "Run the native {} constraint with live selection diagnostics".format(joint_type),
            )
            for label, command_id, joint_type in constraint_defs
        )
        self._add_callback_dropdown(joints, "Constraint", constraint_rows, "Assembly_CreateJointDistance")
        self._add_callback_command(
            joints,
            "Why won't this mate?",
            self.show_assembly_mate_diagnostics,
            "FusionLike_AssemblyMateDiagnostics",
            "Explain the current mate selection and inspect existing joint references",
            "Part_CheckGeometry",
        )
        self._add_command(joints, "Assembly_SelectJointsOfComponent")

        motion = self._make_toolbar("FusionLike_AssemblyMotion", "Fusion-like: Motion and Output")
        self._section_label(motion, "MOTION / OUTPUT")
        self._add_dropdown(
            motion,
            "Motion Link",
            (
                ("Rack and Pinion", "Assembly_CreateJointRackPinion"),
                ("Screw", "Assembly_CreateJointScrew"),
                ("Gear / Belt", "Assembly_CreateJointGearBelt"),
            ),
            "Assembly_CreateJointGearBelt",
        )
        for command_id in (
            "Assembly_CreateSimulation",
            "Assembly_CreateSnapshot",
            "Assembly_CreateView",
            "Assembly_CreateBom",
            "Assembly_ExportASMT",
            "Std_Measure",
            "Part_CheckGeometry",
            "Std_ViewFitAll",
        ):
            self._add_command(motion, command_id)

    def _build_drawing_toolbars(self):
        create = self._make_toolbar("FusionLike_DrawingCreate", "Fusion-like: Drawing Create")
        self._section_label(create, "CREATE")
        self._add_dropdown(
            create,
            "New Sheet",
            (
                ("Default Sheet", "TechDraw_PageDefault"),
                ("Choose Template", "TechDraw_PageTemplate"),
            ),
            "TechDraw_PageDefault",
        )
        self._add_callback_command(
            create,
            "Insert Model View",
            self.insert_dimensionable_model_view,
            "FusionLike_DrawingInsertModelView",
            "Guided insertion of a model-linked, dimensionable TechDraw base view",
            "TechDraw_View",
        )
        self._add_command(create, "TechDraw_ProjectionGroup")
        self._add_dropdown(
            create,
            "Section View",
            (
                ("Section View", "TechDraw_SectionView"),
                ("Section Group", "TechDraw_SectionGroup"),
                ("Complex Section", "TechDraw_ComplexSection"),
            ),
            "TechDraw_SectionGroup",
        )
        self._add_command(create, "TechDraw_DetailView")
        self._add_command(create, "TechDraw_BrokenView")
        self._add_callback_dropdown(
            create,
            "Reference Capture",
            (
                (
                    "Active View Snapshot — raster, not dimensionable",
                    lambda: self._run_command("TechDraw_ActiveView"),
                    "FusionLike_DrawingActiveViewSnapshot",
                    "Insert a bitmap capture of the 3D viewport. It has no model edges and cannot be dimensioned.",
                ),
                (
                    "Drawing workflow guide",
                    self.show_drawing_workflow_help,
                    "FusionLike_DrawingWorkflowGuide",
                    "Explain sheets, model views, snapshots, projected views, and dimension selection",
                ),
            ),
            "TechDraw_ActiveView",
        )

        modify = self._make_toolbar("FusionLike_DrawingModify", "Fusion-like: Drawing Modify")
        self._section_label(modify, "MODIFY / GEOMETRY")
        for command_id in (
            "TechDraw_StackGroup",
            "TechDraw_ExtensionLockUnlockView",
            "TechDraw_ExtensionPositionSectionView",
            "TechDraw_ToggleFrame",
            "TechDraw_Hatch",
            "TechDraw_GeometricHatch",
            "TechDraw_DimensionRepair",
        ):
            self._add_command(modify, command_id)

        dims = self._make_toolbar("FusionLike_DrawingDimensions", "Fusion-like: Drawing Dimensions")
        self._section_label(dims, "DIMENSIONS")
        self._add_callback_command(
            dims,
            "Smart Dimension",
            lambda: self.start_drawing_dimension("TechDraw_Dimension"),
            "FusionLike_DrawingSmartDimension",
            "Validate the selected drawing geometry, then start the general TechDraw dimension command",
            "TechDraw_Dimension",
        )
        dimension_defs = (
            ("General Dimension", "TechDraw_Dimension"),
            ("Length", "TechDraw_LengthDimension"),
            ("Horizontal", "TechDraw_HorizontalDimension"),
            ("Vertical", "TechDraw_VerticalDimension"),
            ("Radius", "TechDraw_RadiusDimension"),
            ("Diameter", "TechDraw_DiameterDimension"),
            ("Angle", "TechDraw_AngleDimension"),
            ("Three-Point Angle", "TechDraw_3PtAngleDimension"),
            ("Area", "TechDraw_AreaDimension"),
        )
        dimension_rows = tuple(
            (
                label,
                (lambda cid=command_id: self.start_drawing_dimension(cid)),
                "FusionLike_DrawingDimension_{}".format(re.sub(r"\W+", "", label)),
                "Start {} after checking that model edges or vertices—not a raster snapshot—are selected".format(label),
            )
            for label, command_id in dimension_defs
        )
        self._add_callback_dropdown(dims, "Dimension", dimension_rows, "TechDraw_Dimension")
        self._add_dropdown(
            dims,
            "Ordinate / Chain",
            (
                ("Horizontal Chain", "TechDraw_ExtensionCreateHorizChainDimension"),
                ("Vertical Chain", "TechDraw_ExtensionCreateVertChainDimension"),
                ("Horizontal Coordinate", "TechDraw_ExtensionCreateHorizCoordDimension"),
                ("Vertical Coordinate", "TechDraw_ExtensionCreateVertCoordDimension"),
                ("Arc Length", "TechDraw_ExtensionCreateLengthArc"),
            ),
            "TechDraw_ExtensionCreateChainDimensionGroup",
        )
        self._add_command(dims, "TechDraw_Balloon")
        self._add_callback_command(
            dims,
            "Dimension Help",
            self.show_drawing_workflow_help,
            "FusionLike_DrawingDimensionHelp",
            "Show what must be selected for dimensionable TechDraw geometry",
            "TechDraw_DimensionRepair",
        )

        annotate = self._make_toolbar("FusionLike_DrawingAnnotate", "Fusion-like: Drawing Annotate")
        self._section_label(annotate, "ANNOTATE / SYMBOLS")
        for command_id in (
            "TechDraw_RichTextAnnotation",
            "TechDraw_LeaderLine",
            "TechDraw_CenterLineGroup",
            "TechDraw_ExtensionCircleCenterLinesGroup",
            "TechDraw_ExtensionThreadsGroup",
            "TechDraw_WeldSymbol",
            "TechDraw_SurfaceFinishSymbols",
            "TechDraw_HoleShaftFit",
        ):
            self._add_command(annotate, command_id)
        self._add_callback_command(
            annotate,
            "Thread Callout",
            self.insert_thread_callout,
            "FusionLike_DrawingThreadCallout",
            "Insert or refresh a standards-based callout from a native Hole or Fusion-like Thread",
            "TechDraw_RichTextAnnotation",
        )

        output = self._make_toolbar("FusionLike_DrawingOutput", "Fusion-like: Drawing Output")
        self._section_label(output, "TABLES / OUTPUT")
        for command_id in (
            "Assembly_CreateBom",
            "TechDraw_SpreadsheetView",
            "TechDraw_FillTemplateFields",
            "TechDraw_RedrawPage",
            "TechDraw_PrintAll",
            "TechDraw_ExportPageSVG",
            "TechDraw_ExportPageDXF",
        ):
            self._add_command(output, command_id)
        self._add_callback_command(
            output,
            "Export PDF",
            self.export_active_drawing_pdf,
            "FusionLike_DrawingExportPDF",
            "Export the selected or active TechDraw page as PDF",
            "TechDraw_ExportPageSVG",
        )

    def _build_toolbars(self):
        if self.rebuilding_toolbars:
            return
        self.rebuilding_toolbars = True
        try:
            self._clear_profile_toolbars()
            self._build_quick_toolbar()
            current = _active_workbench_name()
            self.current_workbench = current
            if current:
                self.pref.SetString("LastWorkbench", current)
            if self._active_edited_sketch() is not None:
                self._build_sketch_toolbars()
            elif "Assembly" in current or current in ("Assembly4Workbench", "A2plusWorkbench"):
                self._build_assembly_toolbars()
            elif current == "TechDrawWorkbench" or "TechDraw" in current:
                self._build_drawing_toolbars()
            else:
                self._build_design_toolbars()
            for toolbar in self.toolbars:
                toolbar.show()
            self.ui_context_signature = self._ui_context_signature_value()
        finally:
            self.rebuilding_toolbars = False

    def _populate_workspaces(self):
        combo = self.workspace_combo
        combo.blockSignals(True)
        combo.clear()
        available = Gui.listWorkbenches()
        current = _active_workbench_name()
        current_index = 0
        for label, candidates in self.WORKSPACES:
            workbench_id = next((candidate for candidate in candidates if candidate in available), None)
            if workbench_id is None:
                continue
            combo.addItem(label, workbench_id)
            if workbench_id == current:
                current_index = combo.count() - 1
        combo.setCurrentIndex(current_index)
        combo.blockSignals(False)
        combo.currentIndexChanged.connect(self._switch_workspace)

    def _switch_workspace(self, index):
        if self.workspace_combo is None or index < 0:
            return
        workbench_id = self.workspace_combo.itemData(index)
        if not workbench_id:
            return
        try:
            Gui.activateWorkbench(str(workbench_id))
            QtCore.QTimer.singleShot(450, self._post_workspace_switch)
        except Exception:
            _console("Could not activate workspace {}".format(workbench_id), warning=True)

    def _post_workspace_switch(self):
        self.end_projection_mode(silent=True)
        current = _active_workbench_name()
        if current:
            self.pref.SetString("LastWorkbench", current)
        self._build_toolbars()
        self._hide_native_toolbars()
        self._refresh_timeline(force=True)

    def _hide_native_toolbars(self):
        for toolbar in self.mw.findChildren(QtWidgets.QToolBar):
            if not str(toolbar.objectName()).startswith(TOOLBAR_PREFIX):
                toolbar.hide()



    # ---------- contextual Sketcher toolbar switching ----------

    def _ui_context_signature_value(self):
        document = App.ActiveDocument
        sketch = self._active_edited_sketch()
        # Sketcher actions can finish registering a fraction of a second after
        # edit mode begins. Including their availability in the signature makes
        # the timer rebuild once more instead of leaving an incomplete ribbon.
        sketch_action_state = ()
        if sketch is not None:
            sketch_action_state = tuple(
                bool(self._find_action(command_id))
                for command_id in (
                    "Sketcher_LeaveSketch",
                    "Sketcher_CompLine",
                    "Sketcher_CompCreateRectangles",
                    "Sketcher_CompCreateArc",
                    "Sketcher_CreateCircle",
                    "Sketcher_CompDimensionTools",
                    "Sketcher_ConstrainCoincidentUnified",
                )
            )
        return (
            _active_workbench_name(),
            str(getattr(document, "Name", "")),
            str(getattr(sketch, "Name", "")),
            sketch_action_state,
        )

    def _refresh_ui_context_if_needed(self):
        if not self.active or self.rebuilding_toolbars:
            return
        app = self.app or QtWidgets.QApplication.instance()
        if app is not None and app.activePopupWidget() is not None:
            return
        signature = self._ui_context_signature_value()
        if signature == self.ui_context_signature:
            return
        old_sketch = self.ui_context_signature[2] if self.ui_context_signature else ""
        new_sketch = signature[2]
        if old_sketch and old_sketch != new_sketch:
            self.end_projection_mode(silent=True)
        self._build_toolbars()
        self._hide_native_toolbars()

    # ---------- guided TechDraw model-view and dimension workflow ----------

    def _drawing_candidate_objects(self):
        document = App.ActiveDocument
        if document is None:
            return []
        candidates = []
        seen = set()
        for obj in document.Objects:
            type_id = str(getattr(obj, "TypeId", ""))
            if type_id.startswith("TechDraw::") or type_id.startswith("Sketcher::"):
                continue
            if type_id in ("App::Origin", "App::Line", "App::Plane", "PartDesign::FeatureBase"):
                continue
            eligible = (
                _is_derived(obj, "Assembly::AssemblyObject")
                or _is_derived(obj, "PartDesign::Body")
                or _is_derived(obj, "App::Part")
                or _is_derived(obj, "App::Link")
            )
            if not eligible and _is_derived(obj, "Part::Feature"):
                in_model_container = any(
                    _is_derived(parent, "PartDesign::Body")
                    or _is_derived(parent, "App::Part")
                    or _is_derived(parent, "Assembly::AssemblyObject")
                    for parent in list(getattr(obj, "InList", []) or [])
                )
                eligible = not in_model_container
            if not eligible:
                continue
            key = (getattr(obj.Document, "Name", ""), obj.Name)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(obj)
        candidates.sort(key=lambda obj: str(obj.Label).lower())
        return candidates

    def _show_techdraw_page(self, page):
        if page is None:
            return
        try:
            page.ViewObject.show()
            QtWidgets.QApplication.processEvents()
            return
        except Exception:
            pass
        try:
            gui_obj = Gui.getDocument(page.Document.Name).getObject(page.Name)
            gui_obj.show()
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    def insert_dimensionable_model_view(self):
        document = App.ActiveDocument
        if document is None:
            QtWidgets.QMessageBox.warning(self.mw, "Insert Model View", "Open or create a model document first.")
            return False
        pages = [obj for obj in document.Objects if _is_derived(obj, "TechDraw::DrawPage")]
        selected_page = self._selected_techdraw_page()
        selected_names = set()
        try:
            for obj in Gui.Selection.getSelection():
                if not str(getattr(obj, "TypeId", "")).startswith("TechDraw::"):
                    selected_names.add(obj.Name)
        except Exception:
            pass
        candidates = self._drawing_candidate_objects()
        if not candidates:
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Insert Model View",
                "No drawable Body, Part, component, assembly, Link, or root Part feature was found in the active document.",
            )
            return False
        dialog = DrawingSourceDialog(
            document,
            pages,
            candidates,
            selected_names=selected_names,
            selected_page=selected_page,
            parent=self.mw,
        )
        if _dialog_exec(dialog) != QtWidgets.QDialog.Accepted:
            return False
        source_objects = [document.getObject(name) for name in dialog.selected_source_names()]
        source_objects = [obj for obj in source_objects if obj is not None]
        page_name = dialog.selected_page_name()
        page = document.getObject(page_name) if page_name else None
        if page is None:
            before = {obj.Name for obj in document.Objects if _is_derived(obj, "TechDraw::DrawPage")}
            if not self._run_command("TechDraw_PageDefault"):
                QtWidgets.QMessageBox.warning(
                    self.mw,
                    "Insert Model View",
                    "FreeCAD could not create a default TechDraw page. Set a readable default template in TechDraw preferences.",
                )
                return False
            QtWidgets.QApplication.processEvents()
            new_pages = [
                obj
                for obj in document.Objects
                if _is_derived(obj, "TechDraw::DrawPage") and obj.Name not in before
            ]
            page = new_pages[-1] if new_pages else self._selected_techdraw_page()
        if page is None:
            QtWidgets.QMessageBox.warning(self.mw, "Insert Model View", "No TechDraw page is available.")
            return False
        self._show_techdraw_page(page)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(page)
        for source in source_objects:
            Gui.Selection.addSelection(source)
        QtWidgets.QApplication.processEvents()
        if not self._run_command("TechDraw_View"):
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Insert Model View",
                "The native TechDraw model-view command is not active. Ensure the selected sheet is open and the source objects are in the same active document or represented by App::Link objects.",
            )
            return False
        self.mw.statusBar().showMessage(
            "Dimensionable model view started. Choose orientation/projected views, then select edges or vertices on the drawing sheet before dimensioning.",
            10000,
        )
        return True

    def _drawing_dimension_selection_report(self):
        try:
            selection = list(Gui.Selection.getSelectionEx())
        except Exception:
            selection = []
        if not selection:
            return False, (
                "Nothing is selected. Click one model edge for radius/diameter/length, two vertices or edges for distance, "
                "or the geometry required by the chosen dimension command on the TechDraw page."
            )
        image_views = []
        dimensionable_hits = 0
        subelement_hits = 0
        for sel in selection:
            obj = getattr(sel, "Object", None)
            if obj is None:
                continue
            if _is_derived(obj, "TechDraw::DrawViewImage"):
                image_views.append(str(obj.Label))
            if _is_derived(obj, "TechDraw::DrawViewPart"):
                dimensionable_hits += 1
            names = list(getattr(sel, "SubElementNames", []) or [])
            subelement_hits += sum(
                1 for name in names if re.search(r"(?:Edge|Vertex|Face)\d+", str(name))
            )
            # Some TechDraw selection paths are reported through the Page or a
            # parent object, e.g. ``View.Edge4``. Resolve that prefix so valid
            # page geometry is not mistaken for a tree-only selection.
            document = getattr(obj, "Document", None)
            if document is not None:
                for name in names:
                    prefix = str(name).split(".", 1)[0]
                    try:
                        selected_view = document.getObject(prefix)
                    except Exception:
                        selected_view = None
                    if selected_view is not None and _is_derived(
                        selected_view, "TechDraw::DrawViewPart"
                    ):
                        dimensionable_hits += 1
                        break
        if image_views:
            return False, (
                "The selection contains Active View snapshot(s): {}. These are DrawViewImage raster objects and have no model edges. "
                "Use Insert Model View to create a dimensionable vector view."
            ).format(", ".join(image_views))
        if dimensionable_hits == 0 or subelement_hits == 0:
            return False, (
                "Select visible model geometry directly on a dimensionable TechDraw model view. Selecting only the Page or the view's tree item is not enough; "
                "the dimension command needs drawing Edge/Vertex/Face subelements."
            )
        return True, "Drawing geometry selection is suitable for a TechDraw dimension command."

    def start_drawing_dimension(self, command_id):
        valid, message = self._drawing_dimension_selection_report()
        if not valid:
            box = QtWidgets.QMessageBox(self.mw)
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle("Dimension Selection")
            box.setText("The current selection cannot be dimensioned as selected.")
            box.setInformativeText(message)
            continue_button = box.addButton("Continue anyway", QtWidgets.QMessageBox.AcceptRole)
            box.addButton(QtWidgets.QMessageBox.Cancel)
            _dialog_exec(box)
            if box.clickedButton() != continue_button:
                return False
        return self._run_command(command_id)

    def show_drawing_workflow_help(self):
        QtWidgets.QMessageBox.information(
            self.mw,
            "Fusion-like Drawing Workflow",
            "1. Create or choose a sheet.\n"
            "2. Use Insert Model View—not Active View Snapshot—and choose the Body, Part, component, or Assembly.\n"
            "3. Complete FreeCAD's base/projected-view task. The resulting DrawViewPart geometry is dimensionable.\n"
            "4. On the drawing sheet, click the model edges or vertices required by the dimension. Do not select only the tree item.\n"
            "5. Choose Smart Dimension or a specific dimension type.\n\n"
            "Active View Snapshot is intentionally retained only for shaded/raster reference images; it cannot supply associative model dimensions.",
        )
        return True

    # ---------- native Assembly task diagnostics patch ----------

    def _joint_task_failure_report(self, task, heading, exception=None, extra=None, modal=False):
        refs = list(getattr(task, "refs", []) or [])
        joint_type = str(
            getattr(task, "jType", self.pending_joint_type)
            or self.pending_joint_type
            or "Joint"
        )
        try:
            report = self._assembly_joint_report(
                joint_type,
                refs,
                getattr(task, "assembly", None),
                [extra] if extra else None,
            )["text"]
        except Exception:
            report = (
                "Joint type: {}\nReferences selected: {}\n"
                "The diagnostic analyzer could not fully resolve the selected linked geometry."
            ).format(joint_type, len(refs))
        sections = [heading, "", report]
        if exception is not None:
            sections += ["", "Native FreeCAD exception:", str(exception), "", traceback.format_exc()]
        details = "\n".join(sections)
        self.last_assembly_diagnostic_report = details
        _console("Assembly mate diagnostic:\n{}".format(details), warning=True)
        try:
            self._refresh_joint_diagnostics_panel()
            if self.joint_diagnostic_label is not None:
                self.joint_diagnostic_label.setText(details)
        except Exception:
            pass
        self.mw.statusBar().showMessage(heading, 10000)
        if modal:
            self._show_text_report("Assembly Mate Failure", details)
        return details

    def _install_assembly_task_diagnostics_patch(self):
        try:
            import JointObject
        except Exception:
            return False
        cls = getattr(JointObject, "TaskAssemblyCreateJoint", None)
        if cls is None:
            return False
        if getattr(cls, "_fusionlike_diagnostics_patch", False):
            return True

        original_update = getattr(cls, "updateJoint", None)
        original_accept = getattr(cls, "accept", None)
        original_add = getattr(cls, "addSelection", None)
        if not callable(original_update) or not callable(original_accept) or not callable(original_add):
            return False

        cls._fusionlike_original_updateJoint = original_update
        cls._fusionlike_original_accept = original_accept
        cls._fusionlike_original_addSelection = original_add

        def profile_for_task():
            profile = _PROFILE
            return profile if profile is not None and getattr(profile, "active", False) else None

        def patched_update(task, *args, **kwargs):
            try:
                return original_update(task, *args, **kwargs)
            except Exception as exc:
                profile = profile_for_task()
                if profile is not None:
                    profile._joint_task_failure_report(
                        task,
                        "The native Assembly solver rejected the current connector pair.",
                        exception=exc,
                        extra=(
                            "Remove one connector, choose geometry that defines the required axis/plane/point, "
                            "or inspect whether both components are already constrained."
                        ),
                        modal=True,
                    )
                return False

        def patched_accept(task, *args, **kwargs):
            profile = profile_for_task()
            assembly = getattr(task, "assembly", None)
            joint = getattr(task, "joint", None)
            if profile is not None:
                refs = list(getattr(task, "refs", []) or [])
                try:
                    report = profile._assembly_joint_report(
                        str(getattr(task, "jType", profile.pending_joint_type) or "Joint"),
                        refs,
                        assembly,
                    )
                except Exception:
                    report = {"errors": ["The selected references could not be resolved."]}
                if len(refs) != 2 or report["errors"]:
                    profile._joint_task_failure_report(
                        task,
                        "The mate is incomplete or uses incompatible references.",
                        extra="Select exactly two valid connectors on two different component instances.",
                        modal=True,
                    )
                    return False
            try:
                accepted = original_accept(task, *args, **kwargs)
            except Exception as exc:
                if profile is not None:
                    profile._joint_task_failure_report(
                        task,
                        "FreeCAD could not commit or solve this mate.",
                        exception=exc,
                        extra="Check for a redundant closed constraint loop, broken linked geometry, or incompatible connector orientations.",
                        modal=True,
                    )
                return False
            if accepted and profile is not None and assembly is not None:
                # Native task acceptance primarily commits and recomputes. Query the
                # solver's numeric status immediately afterward so a non-exception
                # conflict is not mistaken for a successful mate.
                QtCore.QTimer.singleShot(
                    250,
                    lambda p=profile, a=assembly, j=joint: p._post_joint_accept_diagnostics(a, j),
                )
            return accepted

        def patched_add(task, *args, **kwargs):
            before = len(list(getattr(task, "refs", []) or []))
            try:
                result = original_add(task, *args, **kwargs)
            except Exception as exc:
                profile = profile_for_task()
                if profile is not None:
                    profile._joint_task_failure_report(
                        task,
                        "The selected geometry could not be used as a mate connector.",
                        exception=exc,
                        extra="Pick a face, edge, vertex, datum, axis, or coordinate system belonging to the active Assembly.",
                        modal=True,
                    )
                return False
            profile = profile_for_task()
            after = len(list(getattr(task, "refs", []) or []))
            if profile is not None and after == before and bool(getattr(task, "addition_rejected", False)):
                profile._joint_task_failure_report(
                    task,
                    "That connector was rejected.",
                    extra=(
                        "Native Assembly rejects a third connector and rejects two connectors that resolve to the same component instance. "
                        "Select a connector on the other component, or remove an existing connector first."
                    ),
                    modal=False,
                )
            return result

        cls.updateJoint = patched_update
        cls.accept = patched_accept
        cls.addSelection = patched_add
        cls._fusionlike_diagnostics_patch = True
        return True

    def _remove_assembly_task_diagnostics_patch(self):
        try:
            import JointObject
        except Exception:
            return
        cls = getattr(JointObject, "TaskAssemblyCreateJoint", None)
        if cls is None or not getattr(cls, "_fusionlike_diagnostics_patch", False):
            return
        mappings = (
            ("updateJoint", "_fusionlike_original_updateJoint"),
            ("accept", "_fusionlike_original_accept"),
            ("addSelection", "_fusionlike_original_addSelection"),
        )
        for public_name, stored_name in mappings:
            original = getattr(cls, stored_name, None)
            if callable(original):
                setattr(cls, public_name, original)
            try:
                delattr(cls, stored_name)
            except Exception:
                pass
        cls._fusionlike_diagnostics_patch = False

    # ---------- Assembly instance clipboard and mate diagnostics ----------

    def _assembly_utils(self):
        try:
            import UtilsAssembly
            return UtilsAssembly
        except Exception:
            return None

    def _active_assembly(self):
        utils = self._assembly_utils()
        if utils is not None:
            try:
                assembly = utils.activeAssembly()
                if assembly is not None:
                    return assembly
            except Exception:
                pass
        document = App.ActiveDocument
        if document is not None:
            assemblies = [obj for obj in document.Objects if _is_derived(obj, "Assembly::AssemblyObject")]
            if len(assemblies) == 1:
                return assemblies[0]
        return None

    def _assembly_contains(self, assembly, obj):
        if assembly is None or obj is None:
            return False
        try:
            return bool(assembly.hasObject(obj, True))
        except TypeError:
            try:
                return bool(assembly.hasObject(obj))
            except Exception:
                pass
        except Exception:
            pass
        return assembly in list(getattr(obj, "InListRecursive", []) or []) or assembly in list(
            getattr(obj, "InList", []) or []
        )

    def _assembly_selected_components(self, allow_model_sources=True):
        assembly = self._active_assembly()
        if assembly is None:
            return []
        utils = self._assembly_utils()
        result = []
        seen = set()

        def add(obj):
            if obj is None or obj is assembly:
                return
            key = (getattr(obj.Document, "Name", ""), obj.Name)
            if key not in seen:
                seen.add(key)
                result.append(obj)

        try:
            for obj in Gui.Selection.getSelection():
                if self._assembly_contains(assembly, obj):
                    add(obj)
                elif allow_model_sources and (
                    _is_derived(obj, "App::Part")
                    or _is_derived(obj, "PartDesign::Body")
                    or _is_derived(obj, "Part::Feature")
                    or _is_derived(obj, "App::Link")
                ):
                    add(obj)
        except Exception:
            pass
        if utils is not None:
            try:
                for sel in Gui.Selection.getSelectionEx("*", 0):
                    for sub_name in list(getattr(sel, "SubElementNames", []) or []):
                        try:
                            component, _new_sub = utils.getComponentReference(
                                assembly, sel.Object, sub_name
                            )
                        except Exception:
                            component = None
                        if component is not None:
                            add(component)
            except Exception:
                pass
        return result

    def _placement_to_json(self, placement):
        try:
            quaternion = list(placement.Rotation.Q)
        except Exception:
            quaternion = [0.0, 0.0, 0.0, 1.0]
        return {
            "base": [float(placement.Base.x), float(placement.Base.y), float(placement.Base.z)],
            "rotation": [float(value) for value in quaternion],
        }

    def _placement_from_json(self, row):
        data = row or {}
        base = list(data.get("base", [0.0, 0.0, 0.0]))
        rotation = list(data.get("rotation", [0.0, 0.0, 0.0, 1.0]))
        while len(base) < 3:
            base.append(0.0)
        while len(rotation) < 4:
            rotation.append(0.0)
        try:
            rot = App.Rotation(rotation[0], rotation[1], rotation[2], rotation[3])
        except Exception:
            rot = App.Rotation()
        return App.Placement(App.Vector(base[0], base[1], base[2]), rot)

    def copy_assembly_components(self):
        assembly = self._active_assembly()
        if assembly is None:
            QtWidgets.QMessageBox.warning(
                self.mw, "Copy Assembly Components", "Create or activate a native FreeCAD Assembly first."
            )
            return False
        components = self._assembly_selected_components(allow_model_sources=True)
        if not components:
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Copy Assembly Components",
                "Select one or more component instances in the assembly, or select a Part/Body to copy as a new assembly instance.",
            )
            return False
        rows = []
        for component in components:
            source = getattr(component, "LinkedObject", None)
            if source is None:
                source = component
            placement = getattr(component, "Placement", App.Placement())
            rows.append(
                {
                    "source_document": str(source.Document.Name),
                    "source_object": str(source.Name),
                    "label": str(getattr(component, "Label", source.Label)),
                    "placement": self._placement_to_json(placement),
                    "rigid": bool(getattr(component, "Rigid", True)),
                    "source_is_assembly": bool(_is_derived(source, "Assembly::AssemblyObject")),
                }
            )
        payload = json.dumps({"version": 1, "components": rows})
        self.assembly_clipboard_rows = rows
        clipboard = QtWidgets.QApplication.clipboard()
        mime = QtCore.QMimeData()
        mime.setData(ASSEMBLY_CLIPBOARD_MIME, QtCore.QByteArray(payload.encode("utf-8")))
        mime.setText("FreeCAD assembly components: {}".format(", ".join(row["label"] for row in rows)))
        clipboard.setMimeData(mime)
        self.mw.statusBar().showMessage(
            "Copied {} assembly component source(s). Ctrl+V creates new unconstrained instances.".format(len(rows)),
            7000,
        )
        return True

    def _read_assembly_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is not None and mime.hasFormat(ASSEMBLY_CLIPBOARD_MIME):
            try:
                payload = bytes(mime.data(ASSEMBLY_CLIPBOARD_MIME)).decode("utf-8")
                rows = json.loads(payload).get("components", [])
                if isinstance(rows, list):
                    self.assembly_clipboard_rows = rows
                    return rows
            except Exception:
                pass
        return list(self.assembly_clipboard_rows)

    def _source_offset_distance(self, source):
        try:
            box = source.Shape.BoundBox
            return max(5.0, min(50.0, max(float(box.XLength), float(box.YLength), float(box.ZLength)) * 0.15))
        except Exception:
            return 10.0

    def paste_assembly_components(self, in_place=False):
        assembly = self._active_assembly()
        if assembly is None:
            QtWidgets.QMessageBox.warning(
                self.mw, "Paste Assembly Components", "Create or activate a native FreeCAD Assembly first."
            )
            return False
        rows = self._read_assembly_clipboard()
        if not rows:
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Paste Assembly Components",
                "The Fusion-like assembly clipboard is empty. Select component instances and use Copy first.",
            )
            return False

        document = assembly.Document
        created = []
        problems = []
        try:
            recursive_inputs = set(list(getattr(assembly, "InListRecursive", []) or []))
        except Exception:
            recursive_inputs = set()

        document.openTransaction("Paste assembly component instances")
        try:
            serial = self.assembly_paste_serial + 1
            for index, row in enumerate(rows):
                source_doc_name = str(row.get("source_document", ""))
                source_name = str(row.get("source_object", ""))
                try:
                    source_doc = App.getDocument(source_doc_name)
                except Exception:
                    source_doc = None
                source = source_doc.getObject(source_name) if source_doc is not None else None
                label = str(row.get("label") or source_name or "Component")

                if source is None:
                    problems.append(
                        "{}: source {}.{} is not open or no longer exists".format(
                            label, source_doc_name or "?", source_name or "?"
                        )
                    )
                    continue
                if source is assembly or source in recursive_inputs:
                    problems.append(
                        "{}: inserting this source would create an Assembly dependency loop".format(label)
                    )
                    continue
                if source.Document is not document:
                    if not str(getattr(document, "FileName", "") or ""):
                        problems.append(
                            "{}: save the Assembly document before linking a component from another document".format(label)
                        )
                        continue
                    if not str(getattr(source.Document, "FileName", "") or ""):
                        problems.append(
                            "{}: save the source document before creating an external component link".format(label)
                        )
                        continue

                is_subassembly = bool(
                    row.get("source_is_assembly", False)
                    or _is_derived(source, "Assembly::AssemblyObject")
                )
                object_type = "Assembly::AssemblyLink" if is_subassembly else "App::Link"
                try:
                    link = assembly.newObject(object_type, "Component")
                except Exception:
                    # Older FreeCAD builds may not expose AssemblyLink even though the
                    # Assembly workbench exists. A normal App::Link is still a valid
                    # component instance, but it will behave as a rigid subassembly.
                    link = assembly.newObject("App::Link", "Component")
                    if is_subassembly:
                        problems.append(
                            "{}: AssemblyLink was unavailable; inserted as a rigid App::Link".format(label)
                        )
                link.LinkedObject = source
                link.Label = "{} copy".format(label)
                placement = self._placement_from_json(row.get("placement", {}))
                if not in_place:
                    distance = self._source_offset_distance(source)
                    placement.Base = placement.Base + App.Vector(
                        distance * (serial + index - 1), 0.0, 0.0
                    )
                link.Placement = placement
                if hasattr(link, "Rigid"):
                    link.Rigid = bool(row.get("rigid", True))
                created.append(link)
            document.recompute()
            document.commitTransaction()
        except Exception as exc:
            try:
                document.abortTransaction()
            except Exception:
                pass
            details = traceback.format_exc()
            _console("Assembly paste failed:\n{}".format(details), warning=True)
            self._show_text_report(
                "Paste Assembly Components — failure",
                "The component instances could not be created.\n\n{}\n\n{}".format(exc, details),
            )
            return False

        self.assembly_paste_serial = serial
        Gui.Selection.clearSelection()
        for link in created:
            Gui.Selection.addSelection(link)
        if problems:
            self._show_text_report(
                "Paste Assembly Components — details",
                "Created {} component instance(s).\n\nThe following items need attention:\n\n{}".format(
                    len(created), "\n".join("• " + value for value in problems)
                ),
            )
        self.mw.statusBar().showMessage(
            "Created {} new unconstrained assembly instance(s){}.".format(
                len(created), " in place" if in_place else " with an offset"
            ),
            7000,
        )
        return bool(created)

    def add_selected_to_assembly(self):
        """One-click insertion of selected model objects at their current placements."""
        if not self.copy_assembly_components():
            return False
        return self.paste_assembly_components(in_place=True)

    def duplicate_assembly_components(self):
        if not self.copy_assembly_components():
            return False
        return self.paste_assembly_components(in_place=False)

    def _assembly_refs_from_selection(self, assembly):
        utils = self._assembly_utils()
        if utils is None or assembly is None:
            return [], ["Native Assembly utilities are unavailable in this workbench."]
        refs = []
        notes = []
        try:
            selections = list(Gui.Selection.getSelectionEx("*", 0))
        except Exception:
            selections = []
        for sel in selections:
            sub_names = list(getattr(sel, "SubElementNames", []) or [])
            if not sub_names and sel.Object is not assembly:
                notes.append(
                    "{} is selected only as a tree object. Pick a face, edge, vertex, datum, or coordinate system for a mate connector.".format(
                        str(sel.Object.Label)
                    )
                )
            for sub_name in sub_names:
                try:
                    component, new_sub = utils.getComponentReference(assembly, sel.Object, sub_name)
                except Exception:
                    component, new_sub = None, ""
                if component is None:
                    notes.append("{} is not a selectable reference inside the active assembly.".format(sub_name))
                    continue
                refs.append([component, [new_sub, new_sub]])
        return refs, notes

    def _joint_reference_info(self, ref):
        utils = self._assembly_utils()
        component = ref[0] if ref else None
        moving = None
        actual = None
        sub_name = ""
        try:
            moving = utils.getMovingPart(ref) if utils is not None else component
        except Exception:
            moving = component
        try:
            actual = utils.getObject(ref) if utils is not None else component
        except Exception:
            actual = component
        try:
            sub_name = str(ref[1][0])
        except Exception:
            pass
        leaf = _element_leaf(sub_name)
        kind = "object coordinate system" if not leaf else leaf
        directional = not bool(leaf.startswith("Vertex")) if leaf else True
        axial = False
        point_like = bool(leaf.startswith("Vertex"))
        geometry_detail = ""
        size_detail = ""
        radius = None
        if actual is not None and leaf:
            try:
                element = actual.Shape.getElement(leaf)
                if leaf.startswith("Face"):
                    surface_name = type(element.Surface).__name__
                    low = surface_name.lower()
                    if "cylinder" in low:
                        kind = "cylindrical face"
                        axial = True
                        try:
                            radius = float(element.Surface.Radius)
                            size_detail = "diameter {:.6g} mm".format(2.0 * radius)
                        except Exception:
                            pass
                    elif "plane" in low:
                        kind = "planar face"
                    elif "sphere" in low:
                        kind = "spherical face"
                        point_like = True
                    elif "cone" in low:
                        kind = "conical face"
                        axial = True
                    else:
                        kind = "{} face".format(surface_name)
                    geometry_detail = surface_name
                elif leaf.startswith("Edge"):
                    curve_name = type(element.Curve).__name__
                    low = curve_name.lower()
                    if "circle" in low:
                        kind = "circular edge"
                        axial = True
                        try:
                            radius = float(element.Curve.Radius)
                            size_detail = "diameter {:.6g} mm".format(2.0 * radius)
                        except Exception:
                            pass
                    elif "line" in low:
                        kind = "straight edge"
                        try:
                            size_detail = "length {:.6g} mm".format(float(element.Length))
                        except Exception:
                            pass
                    else:
                        kind = "{} edge".format(curve_name)
                    geometry_detail = curve_name
                elif leaf.startswith("Vertex"):
                    kind = "vertex"
                    point_like = True
                    directional = False
            except Exception:
                geometry_detail = "unresolved subelement"
        return {
            "component": moving or component,
            "actual": actual,
            "sub_name": sub_name,
            "leaf": leaf,
            "kind": kind,
            "directional": directional,
            "axial": axial,
            "point_like": point_like,
            "detail": geometry_detail,
            "size_detail": size_detail,
            "radius": radius,
        }

    def _assembly_joint_report(self, joint_type, refs, assembly=None, extra_notes=None):
        assembly = assembly or self._active_assembly()
        utils = self._assembly_utils()
        lines = ["Joint type: {}".format(joint_type or "unspecified")]
        errors = []
        warnings = []
        infos = []
        infos.extend(extra_notes or [])
        reference_info = [self._joint_reference_info(ref) for ref in refs]
        lines.append("References selected: {}".format(len(refs)))
        for index, info in enumerate(reference_info, 1):
            component = info["component"]
            component_label = str(getattr(component, "Label", getattr(component, "Name", "unknown")))
            lines.append(
                "  {}. {} — {} ({}{})".format(
                    index,
                    component_label,
                    info["sub_name"] or "object origin",
                    info["kind"],
                    "; " + info["size_detail"] if info["size_detail"] else "",
                )
            )
            if utils is not None:
                try:
                    if not utils.isRefValid(refs[index - 1], 2):
                        errors.append("Reference {} is broken or incomplete.".format(index))
                except Exception:
                    pass
        if len(refs) == 0:
            infos.append("Pick the first connector, then pick the second connector on a different component instance.")
        elif len(refs) == 1:
            infos.append("Pick the second connector on a different component instance. A second face on the same instance is rejected by native Assembly.")
        elif len(refs) > 2:
            errors.append("Basic joints accept exactly two references; clear extra selections.")
        if len(reference_info) >= 2:
            component1 = reference_info[0]["component"]
            component2 = reference_info[1]["component"]
            if component1 is not None and component1 is component2:
                errors.append("Both references resolve to the same component instance. A component cannot be mated to itself.")
            if joint_type in ("Revolute", "Cylindrical"):
                for index, info in enumerate(reference_info[:2], 1):
                    if not info["axial"]:
                        warnings.append(
                            "Reference {} is {}. Revolute/Cylindrical joints are most predictable with cylindrical faces, circular edges, axes, or coordinate systems.".format(
                                index, info["kind"]
                            )
                        )
                radii = [info.get("radius") for info in reference_info[:2]]
                if all(value is not None for value in radii):
                    difference = abs(float(radii[0]) - float(radii[1])) * 2.0
                    if difference > 1e-6:
                        infos.append(
                            "The selected axial diameters differ by {:.6g} mm. This is allowed by the solver, but it often means the wrong cylindrical face or circular edge was picked.".format(difference)
                        )
            elif joint_type == "Slider":
                for index, info in enumerate(reference_info[:2], 1):
                    if not info["directional"]:
                        warnings.append(
                            "Reference {} is {} and does not define a clear slide direction. Prefer planar faces, straight edges, axes, or coordinate systems.".format(
                                index, info["kind"]
                            )
                        )
            elif joint_type == "Ball":
                if not any(info["point_like"] for info in reference_info[:2]):
                    warnings.append("Ball joints are easiest to diagnose when at least one connector is a vertex, point, spherical face, or explicit coordinate system.")
            elif joint_type in ("Parallel", "Perpendicular", "Angle"):
                for index, info in enumerate(reference_info[:2], 1):
                    if not info["directional"]:
                        errors.append(
                            "Reference {} is {} and does not define an orientation for a {} constraint.".format(
                                index, info["kind"], joint_type
                            )
                        )
            if assembly is not None and hasattr(assembly, "isPartConnected"):
                try:
                    connected = [assembly.isPartConnected(info["component"]) for info in reference_info[:2]]
                    if not any(connected):
                        warnings.append("Neither selected component is connected to ground. Ground one component first for a deterministic assembly solution.")
                    elif all(connected):
                        warnings.append("Both selected components are already connected. Adding another joint may overconstrain a closed kinematic loop.")
                except Exception:
                    pass
        if joint_type in ("Perpendicular", "Angle"):
            infos.append("If the initial connector axes are exactly parallel, use Reverse/Rotate 90° in the native task panel or choose a different orientation-bearing reference.")
        if errors:
            status = "ERROR — the mate selection is not valid yet."
        elif warnings:
            status = "WARNING — the native solver may accept this, but the selection has likely failure or ambiguity risks."
        elif len(refs) == 2:
            status = "READY — two distinct, valid-looking component references are selected."
        else:
            status = "WAITING — complete the two-reference selection."
        report = [status, ""] + lines
        if errors:
            report += ["", "Errors:"] + ["  • " + value for value in errors]
        if warnings:
            report += ["", "Warnings:"] + ["  • " + value for value in warnings]
        if infos:
            report += ["", "Guidance:"] + ["  • " + value for value in infos]
        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "text": "\n".join(report),
        }

    def start_guided_joint(self, command_id, joint_type, as_built=False):
        assembly = self._active_assembly()
        if assembly is None:
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Assembly Mate",
                "Create and activate a native FreeCAD Assembly before creating a joint.",
            )
            return False
        refs, notes = self._assembly_refs_from_selection(assembly)
        report = self._assembly_joint_report(joint_type, refs, assembly, notes)
        if report["errors"]:
            box = QtWidgets.QMessageBox(self.mw)
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle("Mate Selection Diagnostics")
            box.setText(report["status"])
            box.setInformativeText("Correct the selection, or continue and pick valid references in the native joint task.")
            box.setDetailedText(report["text"])
            continue_button = box.addButton("Continue to joint tool", QtWidgets.QMessageBox.AcceptRole)
            box.addButton(QtWidgets.QMessageBox.Cancel)
            _dialog_exec(box)
            if box.clickedButton() != continue_button:
                return False
        if as_built:
            self.mw.statusBar().showMessage(
                "As-built starting condition: the current component placements are retained while the native joint task opens.",
                7000,
            )
        if not self._run_command(command_id):
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Assembly Mate",
                "The native {} joint command is not currently active. Activate an Assembly and ensure it contains at least two component instances.".format(joint_type),
            )
            return False
        self.pending_joint_type = joint_type
        self.joint_diagnostic_seen_task = False
        self.joint_diagnostic_wait_ticks = 0
        self.joint_diagnostic_panel = None
        self.joint_diagnostic_label = None
        self.last_assembly_diagnostic_report = report["text"]
        self.joint_diagnostic_timer.start()
        QtCore.QTimer.singleShot(0, self._refresh_joint_diagnostics_panel)
        return True

    def _refresh_joint_diagnostics_panel(self):
        try:
            import JointObject
            task = getattr(JointObject, "activeTask", None)
        except Exception:
            task = None
        if task is None:
            self.joint_diagnostic_wait_ticks += 1
            if self.joint_diagnostic_seen_task or self.joint_diagnostic_wait_ticks > 20:
                self.joint_diagnostic_timer.stop()
                self.joint_diagnostic_panel = None
                self.joint_diagnostic_label = None
            return
        self.joint_diagnostic_seen_task = True
        self.joint_diagnostic_wait_ticks = 0
        form = getattr(task, "form", None)
        if form is None:
            return
        try:
            panel = form.findChild(QtWidgets.QGroupBox, "FusionLike_MateDiagnosticsPanel")
        except Exception:
            panel = None
        if panel is None:
            panel = QtWidgets.QGroupBox("Mate diagnostics", form)
            panel.setObjectName("FusionLike_MateDiagnosticsPanel")
            panel_layout = QtWidgets.QVBoxLayout(panel)
            label = QtWidgets.QLabel(panel)
            label.setObjectName("FusionLike_MateDiagnosticsLabel")
            label.setWordWrap(True)
            label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            panel_layout.addWidget(label)
            button = QtWidgets.QPushButton("Open full diagnostics", panel)
            button.clicked.connect(self.show_assembly_mate_diagnostics)
            panel_layout.addWidget(button)
            try:
                form.layout().insertWidget(0, panel)
            except Exception:
                return
            self.joint_diagnostic_panel = panel
            self.joint_diagnostic_label = label
        else:
            self.joint_diagnostic_panel = panel
            self.joint_diagnostic_label = panel.findChild(QtWidgets.QLabel, "FusionLike_MateDiagnosticsLabel")
        refs = list(getattr(task, "refs", []) or [])
        joint_type = str(getattr(task, "jType", self.pending_joint_type) or self.pending_joint_type)
        report = self._assembly_joint_report(joint_type, refs, getattr(task, "assembly", None))
        self.last_assembly_diagnostic_report = report["text"]
        if self.joint_diagnostic_label is not None:
            try:
                self.joint_diagnostic_label.setText(report["text"])
            except RuntimeError:
                self.joint_diagnostic_label = None

    def _assembly_joint_inventory_report(self, assembly):
        document = getattr(assembly, "Document", None)
        if document is None:
            return "No active assembly document."
        lines = ["Assembly: {} ({})".format(assembly.Label, assembly.Name)]
        if self.last_assembly_solver_code is not None:
            title, explanation = ASSEMBLY_SOLVER_CODES.get(
                self.last_assembly_solver_code,
                ("Unknown solver result", "FreeCAD returned an unrecognized Assembly solver status."),
            )
            lines.append(
                "Last native solve: {} (code {})".format(title, self.last_assembly_solver_code)
            )
            lines.append("Meaning: {}".format(explanation))
        try:
            lines.append("Assembly state: {}".format(", ".join(str(value) for value in assembly.State) or "OK"))
        except Exception:
            pass
        joints = [obj for obj in document.Objects if "JointType" in getattr(obj, "PropertiesList", [])]
        lines.append("Joint objects: {}".format(len(joints)))
        invalid_count = 0
        utils = self._assembly_utils()
        for joint in joints:
            refs = []
            for prop in ("Reference1", "Reference2"):
                try:
                    value = getattr(joint, prop)
                    if value:
                        refs.append(value)
                except Exception:
                    pass
            report = self._assembly_joint_report(str(getattr(joint, "JointType", "Joint")), refs, assembly)
            if report["errors"]:
                invalid_count += 1
            suppressed = bool(getattr(joint, "Suppressed", False))
            lines.append("\n{} [{}]{}".format(joint.Label, getattr(joint, "JointType", "?"), " — suppressed" if suppressed else ""))
            lines.append(report["text"])
            try:
                state = ", ".join(str(value) for value in joint.State)
                if state:
                    lines.append("Object state: {}".format(state))
            except Exception:
                pass
        diagnostic_props = []
        for prop in getattr(assembly, "PropertiesList", []):
            if any(token in prop.lower() for token in ("error", "solver", "status", "message")):
                try:
                    diagnostic_props.append("{} = {}".format(prop, getattr(assembly, prop)))
                except Exception:
                    pass
        if diagnostic_props:
            lines += ["", "Solver/status properties:"] + diagnostic_props
        lines += [
            "",
            "Common causes:",
            "  • Two references resolve to the same component instance.",
            "  • A whole tree object was selected instead of a face, edge, vertex, datum, axis, or coordinate system.",
            "  • Neither component is grounded/connected, or both are already fully constrained.",
            "  • The chosen geometry does not define the axis, plane, point, or orientation required by the joint type.",
            "  • A closed joint loop adds redundant degrees-of-freedom constraints.",
            "  • A linked source object or subelement was renamed, removed, or is in a document that is not open.",
        ]
        lines.insert(2, "Invalid-looking joints: {}".format(invalid_count))
        return "\n".join(lines)

    def _show_text_report(self, title, text):
        dialog = QtWidgets.QDialog(self.mw)
        dialog.setWindowTitle(title)
        dialog.resize(760, 620)
        layout = QtWidgets.QVBoxLayout(dialog)
        viewer = QtWidgets.QPlainTextEdit(dialog)
        viewer.setReadOnly(True)
        viewer.setPlainText(text)
        layout.addWidget(viewer, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        try:
            buttons.button(QtWidgets.QDialogButtonBox.Close).clicked.connect(dialog.accept)
        except Exception:
            buttons.clicked.connect(dialog.accept)
        layout.addWidget(buttons)
        _dialog_exec(dialog)

    def show_assembly_mate_diagnostics(self):
        try:
            import JointObject
            task = getattr(JointObject, "activeTask", None)
        except Exception:
            task = None
        if task is not None:
            report = self._assembly_joint_report(
                str(getattr(task, "jType", self.pending_joint_type)),
                list(getattr(task, "refs", []) or []),
                getattr(task, "assembly", None),
            )["text"]
        else:
            assembly = self._active_assembly()
            if assembly is None:
                QtWidgets.QMessageBox.warning(
                    self.mw, "Assembly Diagnostics", "Create or activate a native FreeCAD Assembly first."
                )
                return False
            refs, notes = self._assembly_refs_from_selection(assembly)
            selection_report = self._assembly_joint_report(
                self.pending_joint_type or "Current selection", refs, assembly, notes
            )["text"]
            report = selection_report + "\n\n" + self._assembly_joint_inventory_report(assembly)
        self.last_assembly_diagnostic_report = report
        self._show_text_report("Assembly Mate Diagnostics", report)
        return True

    def _assembly_solver_result_report(self, assembly, result_code, error=None, joint=None):
        title, explanation = ASSEMBLY_SOLVER_CODES.get(
            result_code,
            ("Unknown solver result", "FreeCAD returned an unrecognized Assembly solver status."),
        )
        lines = ["{} (code {})".format(title, result_code), explanation]
        if joint is not None:
            lines += [
                "",
                "Mate just committed: {} ({})".format(
                    str(getattr(joint, "Label", getattr(joint, "Name", "Joint"))),
                    str(getattr(joint, "JointType", "unknown type")),
                ),
            ]
        if error is not None:
            lines += ["", "Native solver exception:", str(error)]
        lines += ["", self._assembly_joint_inventory_report(assembly)]
        if result_code in (-3, -4):
            lines += [
                "",
                "Next action: use Inspect Solver → Select Conflicting Joints and Select Redundant Joints. "
                "Suppress the newest joint temporarily, then verify that both connector coordinate systems describe the intended axis or plane.",
            ]
        elif result_code == -5:
            lines += [
                "",
                "Next action: use Inspect Solver → Select Malformed Joints, then edit each reported joint and re-pick both connector references.",
            ]
        elif result_code == -6:
            lines += [
                "",
                "Next action: select the component that should remain stationary and choose Ground / Unground before solving again.",
            ]
        elif result_code == -2:
            lines += [
                "",
                "Next action: use Inspect Solver → Select Redundant Joints and suppress or delete the newest unnecessary joint.",
            ]
        elif result_code == -1:
            lines += [
                "",
                "Next action: inspect connector references for renamed/deleted subelements, excessive offsets, or a closed constraint loop; then try solving with the newest joint suppressed.",
            ]
        return "\n".join(lines)

    def _post_joint_accept_diagnostics(self, assembly, joint):
        if assembly is None or getattr(assembly, "Document", None) is None:
            return False
        error = None
        try:
            result_code = int(assembly.solve(False))
            self.last_assembly_solver_code = result_code
            try:
                assembly.updateSolveStatus()
            except Exception:
                pass
            assembly.Document.recompute()
        except Exception as exc:
            error = exc
            result_code = -1
            self.last_assembly_solver_code = result_code
            _console("Post-mate Assembly solve failed:\n{}".format(traceback.format_exc()), warning=True)
        if result_code == 0 and error is None:
            self.mw.statusBar().showMessage(
                "Mate accepted and Assembly solved successfully.", 7000
            )
            return True
        report = self._assembly_solver_result_report(
            assembly, result_code, error=error, joint=joint
        )
        self.last_assembly_diagnostic_report = report
        try:
            if joint is not None and getattr(joint, "Document", None) is not None:
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(joint)
        except Exception:
            pass
        _console("Assembly mate failed after commit:\n{}".format(report), warning=True)
        self._show_text_report("Assembly Mate Failure", report)
        return False

    def solve_assembly_with_diagnostics(self):
        assembly = self._active_assembly()
        if assembly is None:
            QtWidgets.QMessageBox.warning(
                self.mw, "Solve Assembly", "Create or activate a native FreeCAD Assembly first."
            )
            return False
        error = None
        result_code = None
        try:
            result_code = int(assembly.solve(False))
            self.last_assembly_solver_code = result_code
            try:
                assembly.updateSolveStatus()
            except Exception:
                pass
            assembly.Document.recompute()
        except Exception as exc:
            error = exc
            result_code = -1
            self.last_assembly_solver_code = result_code
            _console("Assembly solve failed:\n{}".format(traceback.format_exc()), warning=True)
        report = self._assembly_solver_result_report(
            assembly, result_code, error=error
        )
        self.last_assembly_diagnostic_report = report
        self._show_text_report("Assembly Solve Diagnostics", report)
        return error is None and result_code == 0

    # ---------- drawing workflow helpers ----------

    def _selected_techdraw_page(self):
        document = App.ActiveDocument
        if document is None:
            return None
        try:
            selected = list(Gui.Selection.getSelection())
        except Exception:
            selected = []
        for obj in selected:
            if _is_derived(obj, "TechDraw::DrawPage"):
                return obj
            for parent in list(getattr(obj, "InList", []) or []):
                if _is_derived(parent, "TechDraw::DrawPage"):
                    return parent
        pages = [obj for obj in document.Objects if _is_derived(obj, "TechDraw::DrawPage")]
        return pages[-1] if pages else None

    def _thread_callout_from_object(self, obj):
        if obj is None:
            return ""
        if "ThreadCallout" in getattr(obj, "PropertiesList", []):
            return str(getattr(obj, "ThreadCallout", "")).strip()
        if _is_derived(obj, "PartDesign::Hole") and bool(getattr(obj, "Threaded", False)):
            return _thread_callout(
                str(getattr(obj, "ThreadType", "")),
                str(getattr(obj, "ThreadSize", "")),
                str(getattr(obj, "ThreadClass", "")),
                _quantity_value(getattr(obj, "ThreadPitch", 0.0)),
                str(getattr(obj, "ThreadDirection", "Right hand")),
            )
        return ""

    def _selected_thread_source(self):
        try:
            selected = list(Gui.Selection.getSelection())
        except Exception:
            selected = []
        for obj in selected:
            source = getattr(obj, "FusionThreadSource", None)
            if source is not None and self._thread_callout_from_object(source):
                return source, obj
            if self._thread_callout_from_object(obj):
                return obj, None
            linked = getattr(obj, "Source", None)
            if isinstance(linked, (list, tuple)):
                for candidate in linked:
                    if isinstance(candidate, (list, tuple)) and candidate:
                        candidate = candidate[0]
                    if self._thread_callout_from_object(candidate):
                        return candidate, None
        return None, None

    def insert_thread_callout(self):
        document = App.ActiveDocument
        page = self._selected_techdraw_page()
        if document is None or page is None:
            QtWidgets.QMessageBox.warning(
                self.mw, "Thread Callout", "Create or select a TechDraw page first."
            )
            return False
        source, existing_annotation = self._selected_thread_source()
        if source is None:
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Thread Callout",
                "Select a threaded Part Design Hole, a Fusion-like Thread feature, or an existing thread-callout annotation.",
            )
            return False
        callout = self._thread_callout_from_object(source)
        if not callout:
            QtWidgets.QMessageBox.warning(self.mw, "Thread Callout", "No thread callout data is available.")
            return False
        document.openTransaction("Insert thread callout")
        try:
            annotation = existing_annotation
            if annotation is None or not _is_derived(annotation, "TechDraw::DrawViewAnnotation"):
                annotation = document.addObject("TechDraw::DrawViewAnnotation", "ThreadCallout")
                annotation.Label = "Thread Callout"
                page.addView(annotation)
                annotation.X = 30.0
                annotation.Y = 30.0
                if "FusionThreadSource" not in annotation.PropertiesList:
                    annotation.addProperty(
                        "App::PropertyLink",
                        "FusionThreadSource",
                        "Fusion-like",
                        "Source Hole or Thread feature for this annotation",
                    )
            annotation.FusionThreadSource = source
            annotation.Text = [callout]
            try:
                annotation.TextStyle = "Bold"
            except Exception:
                pass
            document.recompute()
            document.commitTransaction()
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(annotation)
            self.mw.statusBar().showMessage("Thread callout inserted: {}".format(callout), 6000)
            return True
        except Exception as exc:
            try:
                document.abortTransaction()
            except Exception:
                pass
            QtWidgets.QMessageBox.critical(self.mw, "Thread Callout", str(exc))
            return False

    def export_active_drawing_pdf(self):
        page = self._selected_techdraw_page()
        if page is None:
            QtWidgets.QMessageBox.warning(
                self.mw, "Export Drawing PDF", "Create or select a TechDraw page first."
            )
            return False
        suggested = "{}.pdf".format(re.sub(r"[^A-Za-z0-9_.-]+", "_", str(page.Label)))
        result = QtWidgets.QFileDialog.getSaveFileName(
            self.mw,
            "Export Drawing as PDF",
            suggested,
            "PDF files (*.pdf)",
        )
        filename = result[0] if isinstance(result, (tuple, list)) else result
        filename = str(filename or "")
        if not filename:
            return False
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        try:
            import TechDrawGui

            TechDrawGui.exportPageAsPdf(page, filename)
            self.mw.statusBar().showMessage("Drawing exported to {}".format(filename), 7000)
            return True
        except Exception as exc:
            _console("PDF export failed:\n{}".format(traceback.format_exc()), warning=True)
            QtWidgets.QMessageBox.critical(self.mw, "Export Drawing PDF", str(exc))
            return False

    # ---------- timeline ----------

    def _build_timeline(self):
        dock = QtWidgets.QDockWidget("PARAMETRIC TIMELINE", self.mw)
        dock.setObjectName(TIMELINE_NAME)
        dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetClosable | QtWidgets.QDockWidget.DockWidgetMovable
        )

        container = QtWidgets.QWidget(dock)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(2)

        explanation = QtWidgets.QLabel(
            "Feature order. Right-click a feature to roll a Part Design Body tip backward/forward.",
            container,
        )
        layout.addWidget(explanation)

        timeline = QtWidgets.QListWidget(container)
        timeline.setObjectName("FusionLike_TimelineList")
        timeline.setViewMode(QtWidgets.QListView.IconMode)
        timeline.setFlow(QtWidgets.QListView.LeftToRight)
        timeline.setWrapping(False)
        timeline.setMovement(QtWidgets.QListView.Static)
        timeline.setResizeMode(QtWidgets.QListView.Adjust)
        timeline.setIconSize(QtCore.QSize(24, 24))
        timeline.setSpacing(3)
        timeline.setUniformItemSizes(True)
        timeline.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        timeline.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        timeline.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        timeline.itemClicked.connect(self._timeline_select)
        timeline.customContextMenuRequested.connect(self._timeline_context_menu)
        layout.addWidget(timeline, 1)

        dock.setWidget(container)
        self.mw.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        dock.show()
        try:
            self.mw.resizeDocks([dock], [112], QtCore.Qt.Vertical)
        except Exception:
            pass

        self.timeline_dock = dock
        self.timeline_list = timeline

    def _timeline_objects(self):
        doc = App.ActiveDocument
        if doc is None:
            return []
        result = []
        skip_names = {
            "Origin",
            "X_Axis",
            "Y_Axis",
            "Z_Axis",
            "XY_Plane",
            "XZ_Plane",
            "YZ_Plane",
        }
        for obj in doc.Objects:
            if obj.Name in skip_names:
                continue
            type_id = str(getattr(obj, "TypeId", ""))
            if type_id in ("App::Origin", "App::Line", "App::Plane"):
                continue
            if (
                type_id.startswith("PartDesign::")
                or type_id.startswith("Sketcher::")
                or type_id.startswith("Part::Feature")
                or type_id.startswith("Assembly::")
                or type_id.startswith("TechDraw::")
                or type_id.startswith("Spreadsheet::")
                or type_id == "App::Link"
            ):
                result.append(obj)
        return result

    def _timeline_icon(self, obj):
        key = "{} {}".format(obj.Name, getattr(obj, "TypeId", "")).lower()
        mapping = (
            ("subshapebinder", "PartDesign_SubShapeBinder"),
            ("shapebinder", "PartDesign_SubShapeBinder"),
            ("thread", THREAD_COMMAND_ID),
            ("body", "PartDesign_Body"),
            ("sketch", "PartDesign_NewSketch"),
            ("pocket", "PartDesign_Pocket"),
            ("pad", "PartDesign_Pad"),
            ("hole", "PartDesign_Hole"),
            ("fillet", "PartDesign_Fillet"),
            ("chamfer", "PartDesign_Chamfer"),
            ("thickness", "PartDesign_Thickness"),
            ("draft", "PartDesign_Draft"),
            ("revolution", "PartDesign_Revolution"),
            ("groove", "PartDesign_Groove"),
            ("loft", "PartDesign_AdditiveLoft"),
            ("pipe", "PartDesign_AdditivePipe"),
            ("mirror", "PartDesign_Mirrored"),
            ("linearpattern", "PartDesign_LinearPattern"),
            ("polarpattern", "PartDesign_PolarPattern"),
            ("assembly", "Assembly_CreateAssembly"),
            ("joint", "Assembly_CreateJointRevolute"),
            ("exploded", "Assembly_CreateView"),
            ("bom", "Assembly_CreateBom"),
            ("page", "TechDraw_PageDefault"),
            ("dimension", "TechDraw_Dimension"),
            ("balloon", "TechDraw_Balloon"),
            ("annotation", "TechDraw_RichTextAnnotation"),
            ("view", "TechDraw_View"),
        )
        for token, command_id in mapping:
            if token in key:
                action = self._find_action(command_id)
                if action is not None:
                    return action.icon()
        return QIcon()

    def _body_for_object(self, obj):
        if obj is None:
            return None
        if getattr(obj, "TypeId", "") == "PartDesign::Body":
            return obj
        for parent in getattr(obj, "InList", []):
            if getattr(parent, "TypeId", "") == "PartDesign::Body":
                return parent
        return None

    def _tip_names(self):
        doc = App.ActiveDocument
        if doc is None:
            return set()
        names = set()
        for obj in doc.Objects:
            if getattr(obj, "TypeId", "") == "PartDesign::Body":
                tip = getattr(obj, "Tip", None)
                if tip is not None:
                    names.add(tip.Name)
        return names

    def _timeline_signature_value(self):
        doc = App.ActiveDocument
        if doc is None:
            return (None, ())
        rows = []
        for obj in self._timeline_objects():
            rows.append((obj.Name, str(obj.Label), str(obj.TypeId)))
        return (doc.Name, tuple(rows), tuple(sorted(self._tip_names())))

    def _refresh_timeline_if_needed(self):
        # Workbench changes made through FreeCAD's native selector do not pass
        # through _switch_workspace(). Detect them here and rebuild the compact
        # Fusion-like groups after the new workbench has registered its actions.
        current = _active_workbench_name()
        if current and current != self.current_workbench:
            self.end_projection_mode(silent=True)
            self.pref.SetString("LastWorkbench", current)
            self._build_toolbars()
            self._hide_native_toolbars()
            self._refresh_timeline(force=True)
            return
        self._refresh_timeline(force=False)

    def _refresh_timeline(self, force=False):
        if self.timeline_list is None:
            return
        signature = self._timeline_signature_value()
        if not force and signature == self.timeline_signature:
            return
        self.timeline_signature = signature

        timeline = self.timeline_list
        timeline.blockSignals(True)
        timeline.clear()
        tips = self._tip_names()
        for obj in self._timeline_objects():
            label = str(obj.Label)
            if obj.Name in tips:
                label += "  ◀ TIP"
            item = QtWidgets.QListWidgetItem(self._timeline_icon(obj), label)
            _set_item_user_data(item, obj.Name)
            item.setToolTip("{}\n{}".format(obj.Name, obj.TypeId))
            item.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
            item.setSizeHint(QtCore.QSize(112, 58))
            if obj.Name in tips:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            timeline.addItem(item)
        timeline.blockSignals(False)

    def _timeline_object_from_item(self, item):
        if item is None or App.ActiveDocument is None:
            return None
        name = str(_item_user_data(item) or "")
        return App.ActiveDocument.getObject(name) if name else None

    def _timeline_select(self, item):
        obj = self._timeline_object_from_item(item)
        if obj is None:
            return
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)

    def _timeline_context_menu(self, pos):
        item = self.timeline_list.itemAt(pos) if self.timeline_list is not None else None
        obj = self._timeline_object_from_item(item)
        if obj is None:
            return

        menu = QtWidgets.QMenu(self.timeline_list)
        select_action = menu.addAction("Select in model tree")
        visibility_action = menu.addAction("Toggle visibility")
        body = self._body_for_object(obj)
        roll_action = None
        latest_action = None
        if body is not None and obj is not body:
            menu.addSeparator()
            roll_action = menu.addAction("Set Body tip here (roll history to this feature)")
            latest_action = menu.addAction("Restore Body tip to latest feature")

        chosen = _menu_exec(menu, self.timeline_list.viewport().mapToGlobal(pos))
        if chosen == select_action:
            self._timeline_select(item)
        elif chosen == visibility_action:
            self._timeline_select(item)
            self._run_command("Std_ToggleVisibility")
        elif roll_action is not None and chosen == roll_action:
            self._set_body_tip(body, obj)
        elif latest_action is not None and chosen == latest_action:
            self._set_body_tip_to_latest(body)

    def _set_body_tip(self, body, obj):
        doc = App.ActiveDocument
        if doc is None:
            return
        try:
            doc.openTransaction("Roll Part Design body tip")
            body.Tip = obj
            doc.recompute()
            doc.commitTransaction()
            self._refresh_timeline(force=True)
        except Exception:
            try:
                doc.abortTransaction()
            except Exception:
                pass
            _console("Could not set Body tip:\n{}".format(traceback.format_exc()), warning=True)

    def _set_body_tip_to_latest(self, body):
        candidates = list(getattr(body, "Group", []) or [])
        if not candidates and App.ActiveDocument is not None:
            candidates = [
                obj
                for obj in App.ActiveDocument.Objects
                if body in getattr(obj, "InList", [])
            ]
        solid_features = []
        for obj in candidates:
            try:
                if obj.isDerivedFrom("PartDesign::Feature"):
                    solid_features.append(obj)
            except Exception:
                if str(getattr(obj, "TypeId", "")).startswith("PartDesign::Feature"):
                    solid_features.append(obj)
        if solid_features:
            self._set_body_tip(body, solid_features[-1])

    def toggle_timeline(self):
        if self.timeline_dock is None:
            if self.active:
                self._build_timeline()
                self._refresh_timeline(force=True)
            return
        self.timeline_dock.setVisible(not self.timeline_dock.isVisible())


    # ---------- Fusion-like Hole and independent Thread workflows ----------

    def _selected_hole_or_sketch(self):
        hole = None
        sketch = self._active_edited_sketch()
        try:
            selected = list(Gui.Selection.getSelection())
        except Exception:
            selected = []
        for obj in selected:
            if _is_derived(obj, "PartDesign::Hole"):
                hole = obj
                break
        if hole is None and sketch is None:
            for obj in selected:
                if _is_derived(obj, "Sketcher::SketchObject"):
                    sketch = obj
                    break
        return hole, sketch

    def open_fusion_hole(self):
        document = App.ActiveDocument
        if document is None:
            QtWidgets.QMessageBox.warning(self.mw, "Hole & Thread", "Create or open a document first.")
            return False
        hole, sketch = self._selected_hole_or_sketch()
        is_new = hole is None
        body = _global_body_for_object(hole) if hole is not None else _active_partdesign_body(document, sketch)
        if body is None:
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Hole & Thread",
                "Activate a Part Design Body and select a sketch containing points, circles, or arcs.",
            )
            return False
        if is_new and sketch is None:
            QtWidgets.QMessageBox.warning(
                self.mw,
                "Hole & Thread",
                "Select or edit the Hole placement sketch first. The sketch may contain points, circles, or arcs.",
            )
            return False

        if is_new and self._active_edited_sketch() is sketch:
            try:
                document.recompute()
                Gui.ActiveDocument.resetEdit()
            except Exception:
                pass

        transaction_name = "Create Fusion-style threaded Hole" if is_new else "Edit threaded Hole"
        document.openTransaction(transaction_name)
        try:
            if is_new:
                hole = body.newObject("PartDesign::Hole", "Hole")
                hole.Label = "Hole"
                hole.Profile = sketch
                try:
                    hole.ThreadType = "ISOMetricProfile"
                    options = _enum_options(hole, "ThreadSize")
                    preferred = "M6x1.0" if "M6x1.0" in options else (options[0] if options else None)
                    if preferred:
                        hole.ThreadSize = preferred
                    hole.Threaded = True
                    hole.ModelThread = True
                    hole.CosmeticThread = True
                    hole.ThreadDepthType = "Hole Depth"
                except Exception:
                    pass
                try:
                    sketch.Visibility = False
                except Exception:
                    pass
                try:
                    body.Tip = hole
                except Exception:
                    pass
            dialog = HoleThreadDialog(hole, is_new=is_new, parent=self.mw)
            accepted = _dialog_exec(dialog) == QtWidgets.QDialog.Accepted
            if not accepted:
                document.abortTransaction()
                return False
            document.recompute()
            shape = getattr(hole, "Shape", None)
            if shape is None or shape.isNull():
                raise RuntimeError(
                    "The Hole produced no solid. Check the placement sketch, direction, and thread dimensions."
                )
            document.commitTransaction()
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(hole)
            self._refresh_timeline(force=True)
            self.mw.statusBar().showMessage(
                "Threaded Hole created with native modeled/cosmetic thread data", 6000
            )
            return True
        except Exception as exc:
            try:
                document.abortTransaction()
            except Exception:
                pass
            _console("Threaded Hole failed:\n{}".format(traceback.format_exc()), warning=True)
            QtWidgets.QMessageBox.critical(self.mw, "Hole & Thread", str(exc))
            return False

    def show_hole_menu(self):
        menu = QtWidgets.QMenu("Hole", self.mw)
        custom_source = self._find_action(HOLE_COMMAND_ID)
        native_source = self._find_action("PartDesign_Hole")
        custom = QAction(
            custom_source.icon() if custom_source is not None else QIcon(),
            "Hole & Thread (Fusion-style)",
            menu,
        )
        native = QAction(
            native_source.icon() if native_source is not None else QIcon(),
            "Native FreeCAD Hole task panel",
            menu,
        )
        native.setEnabled(bool(native_source is not None and native_source.isEnabled()))
        menu.addAction(custom)
        menu.addAction(native)
        chosen = _menu_exec(menu, QCursor.pos())
        if chosen == custom:
            return bool(self.open_fusion_hole())
        if chosen == native and native_source is not None:
            native_source.trigger()
            return True
        return True

    def _thread_existing_selection(self):
        try:
            selections = list(Gui.Selection.getSelectionEx())
        except Exception:
            selections = []
        if len(selections) != 1:
            return None
        selection = selections[0]
        obj = getattr(selection, "Object", None)
        sub_names = list(getattr(selection, "SubElementNames", []) or [])
        if obj is not None and not sub_names and "FusionThreadVersion" in getattr(obj, "PropertiesList", []):
            return obj
        return None

    def _thread_context_from_selection(self):
        existing = self._thread_existing_selection()
        if existing is not None:
            analyses = []
            for linked, sub_names in list(getattr(existing, "ThreadFaces", []) or []):
                if isinstance(sub_names, str):
                    sub_names = [sub_names]
                for sub_name in list(sub_names or []):
                    analyses.append(_analyze_cylindrical_face(linked, sub_name))
            return {
                "existing": existing,
                "document": existing.Document,
                "body": _global_body_for_object(existing),
                "source": getattr(existing, "SourceFeature", None),
                "sub_names": [row["sub_name"] for row in analyses],
                "analyses": analyses,
            }

        try:
            selections = list(Gui.Selection.getSelectionEx())
        except Exception:
            selections = []
        if not selections:
            raise ValueError("Select one or more cylindrical faces first.")

        source = None
        body = None
        sub_names = []
        analyses = []
        seen = set()
        for selection in selections:
            selected_obj = getattr(selection, "Object", None)
            if selected_obj is None:
                continue
            selected_body = _global_body_for_object(selected_obj)
            candidate = selected_obj
            if _is_derived(selected_obj, "PartDesign::Body"):
                selected_body = selected_obj
                candidate = getattr(selected_obj, "Tip", None)
            if candidate is None:
                continue
            if body is None:
                body = selected_body
            if selected_body is not body:
                raise ValueError("All threaded faces must belong to the same active Part Design Body.")
            if source is None:
                source = candidate
            if candidate is not source:
                raise ValueError("Create one Thread feature per source solid feature.")
            for raw_sub in list(getattr(selection, "SubElementNames", []) or []):
                leaf = _element_leaf(raw_sub)
                if not leaf or leaf in seen:
                    continue
                seen.add(leaf)
                analyses.append(_analyze_cylindrical_face(source, leaf))
                sub_names.append(leaf)

        if body is None or source is None or not analyses:
            raise ValueError("Select cylindrical faces on the current Part Design Body tip.")
        tip = getattr(body, "Tip", None)
        if source is not tip:
            raise ValueError(
                "The independent Thread command operates on the current Body tip. "
                "Roll the timeline to the desired feature or select faces on the latest solid."
            )
        return {
            "existing": None,
            "document": source.Document,
            "body": body,
            "source": source,
            "sub_names": sub_names,
            "analyses": analyses,
        }

    def _apply_thread_settings(self, feature, settings):
        feature.ThreadStandard = settings["standard"]
        feature.ThreadDesignation = settings["designation"]
        feature.ThreadClassName = settings["thread_class"]
        feature.ThreadCallout = settings["callout"]
        feature.Pitch = settings["pitch"]
        feature.NominalDiameter = settings["diameter"]
        feature.Direction = settings["direction"]
        feature.FaceType = settings["face_type"]
        feature.Modeled = settings["modeled"]
        feature.FullLength = settings["full_length"]
        feature.Length = settings["length"]
        feature.Offset = settings["offset"]
        feature.StartSide = settings["start_side"]
        feature.RadialClearance = settings["clearance"]
        feature.RefineThread = settings["refine"]

    def open_fusion_thread(self):
        document = App.ActiveDocument
        if document is None:
            QtWidgets.QMessageBox.warning(self.mw, "Thread", "Create or open a document first.")
            return False
        try:
            context = self._thread_context_from_selection()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self.mw, "Thread", str(exc))
            return False
        if not context["analyses"]:
            QtWidgets.QMessageBox.warning(self.mw, "Thread", "No valid cylindrical faces were found.")
            return False

        catalog = None
        try:
            catalog = NativeThreadCatalog(context["document"])
            dialog = StandaloneThreadDialog(
                catalog, context["analyses"], existing=context["existing"], parent=self.mw
            )
            accepted = _dialog_exec(dialog) == QtWidgets.QDialog.Accepted
            settings = dialog.settings() if accepted else None
        except Exception as exc:
            _console("Thread dialog failed:\n{}".format(traceback.format_exc()), warning=True)
            QtWidgets.QMessageBox.critical(self.mw, "Thread", str(exc))
            return False
        finally:
            if catalog is not None:
                catalog.close()
        if settings is None:
            return False

        existing = context["existing"]
        body = context["body"]
        source = context["source"]
        if body is None or source is None:
            QtWidgets.QMessageBox.warning(self.mw, "Thread", "The thread's Body or source feature is missing.")
            return False

        context["document"].openTransaction(
            "Edit Fusion-like Thread" if existing is not None else "Create Fusion-like Thread"
        )
        try:
            feature = existing
            if feature is None:
                feature = body.newObject("PartDesign::FeaturePython", "Thread")
                feature.Label = "Thread"
                FusionThreadFeatureProxy(feature)
                feature.SourceFeature = source
                feature.ThreadFaces = [(source, list(context["sub_names"]))]
                try:
                    body.Tip = feature
                except Exception:
                    pass
            elif not isinstance(getattr(feature, "Proxy", None), FusionThreadFeatureProxy):
                FusionThreadFeatureProxy(feature)
            self._apply_thread_settings(feature, settings)
            context["document"].recompute()
            state_text = " ".join(str(value) for value in list(getattr(feature, "State", []) or []))
            if str(getattr(feature, "Status", "")).startswith("ERROR"):
                raise RuntimeError(str(feature.Status))
            if "error" in state_text.lower() or "invalid" in state_text.lower():
                raise RuntimeError(
                    str(getattr(feature, "Status", "")) or "FreeCAD reported an invalid Thread feature."
                )
            if feature.Shape.isNull():
                raise RuntimeError("The Thread feature produced no shape.")
            if settings["callout"]:
                feature.Label = "Thread ({})".format(settings["callout"])
            try:
                source.Visibility = False
                feature.Visibility = True
            except Exception:
                pass
            context["document"].commitTransaction()
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(feature)
            self._refresh_timeline(force=True)
            self.mw.statusBar().showMessage(
                "{} thread feature created: {}".format(
                    "Modeled" if settings["modeled"] else "Cosmetic", settings["callout"]
                ),
                7000,
            )
            return True
        except Exception as exc:
            try:
                context["document"].abortTransaction()
            except Exception:
                pass
            _console("Thread feature failed:\n{}".format(traceback.format_exc()), warning=True)
            QtWidgets.QMessageBox.critical(
                self.mw,
                "Thread",
                "The independent thread could not be created.\n\n{}\n\n"
                "Try a shorter length, zero extra clearance, or cosmetic mode."
                .format(exc),
            )
            return False


    # ---------- Fusion-like persistent projection workflow ----------

    def _active_edited_sketch(self):
        gui_document = getattr(Gui, "ActiveDocument", None)
        if gui_document is None:
            return None
        try:
            edit = gui_document.getInEdit()
        except Exception:
            return None
        obj = getattr(edit, "Object", None) if edit is not None else None
        if obj is None:
            return None
        type_id = str(getattr(obj, "TypeId", ""))
        if type_id.startswith("Sketcher::"):
            return obj
        try:
            if obj.isDerivedFrom("Sketcher::SketchObject"):
                return obj
        except Exception:
            pass
        return None

    def _projection_warning(self, text):
        self.mw.statusBar().showMessage(text, 8000)
        QtWidgets.QMessageBox.warning(self.mw, "Fusion-like projection", text)

    def _projection_requirements(self):
        if _freecad_version_tuple() < (1, 1, 0):
            self._projection_warning(
                "Defining face projection requires FreeCAD 1.1 or newer. "
                "Upgrade FreeCAD, then run Fusion-like → Apply / rebuild."
            )
            return None
        sketch = self._active_edited_sketch()
        if sketch is None:
            self._projection_warning(
                "Edit the destination sketch first, then press P or choose Project / Include."
            )
            return None
        return sketch

    def _projection_selection_rows(self, sketch):
        rows = []
        seen = set()
        try:
            selections = Gui.Selection.getSelectionEx()
        except Exception:
            selections = []
        for selection in selections:
            source = getattr(selection, "Object", None)
            if source is None or source is sketch:
                continue
            sub_names = [str(value) for value in (getattr(selection, "SubElementNames", []) or [])]
            if not sub_names:
                sub_names = [""]
            document = getattr(source, "Document", None)
            document_name = str(getattr(document, "Name", ""))
            for sub_name in sub_names:
                key = (document_name, str(getattr(source, "Name", "")), sub_name)
                if key in seen:
                    continue
                seen.add(key)
                rows.append((source, sub_name))
        return rows

    def _shape_is_null(self, shape):
        if shape is None:
            return True
        try:
            return bool(shape.isNull())
        except Exception:
            return False

    def _object_shape_subnames(self, source):
        """Expand an object-level selection into its projected boundary elements."""
        type_id = str(getattr(source, "TypeId", ""))
        if any(token in type_id for token in ("Plane", "DatumLine", "DatumPoint")):
            return [""]
        shape = getattr(source, "Shape", None)
        if self._shape_is_null(shape):
            return [""]
        try:
            edge_count = len(shape.Edges)
        except Exception:
            edge_count = 0
        if edge_count:
            return ["Edge{}".format(index + 1) for index in range(edge_count)]
        try:
            face_count = len(shape.Faces)
        except Exception:
            face_count = 0
        if face_count:
            return ["Face{}".format(index + 1) for index in range(face_count)]
        try:
            vertex_count = len(shape.Vertexes)
        except Exception:
            vertex_count = 0
        if vertex_count:
            return ["Vertex{}".format(index + 1) for index in range(vertex_count)]
        return [""]

    def _latest_feature_before_sketch(self, body, sketch):
        group = list(getattr(body, "Group", []) or [])
        try:
            stop = group.index(sketch)
        except ValueError:
            stop = len(group)
        for candidate in reversed(group[:stop]):
            if candidate is sketch:
                continue
            shape = getattr(candidate, "Shape", None)
            if not self._shape_is_null(shape):
                return candidate
        return None

    def _normalize_projection_source(self, source, sub_name, sketch):
        """Resolve Body-display selections to the actual feature carrying the shape."""
        if str(getattr(source, "TypeId", "")) != "PartDesign::Body":
            return source, str(sub_name or "")
        target_body = self._body_for_object(sketch)
        if source is target_body:
            candidate = self._latest_feature_before_sketch(source, sketch)
        else:
            candidate = getattr(source, "Tip", None)
        if candidate is None:
            return source, str(sub_name or "")
        leaf = _element_leaf(sub_name)
        return candidate, leaf or str(sub_name or "")

    def _source_depends_on_sketch(self, source, sketch):
        if source is sketch:
            return True
        try:
            return sketch in list(getattr(source, "OutListRecursive", []) or [])
        except Exception:
            return False

    def _source_precedes_sketch(self, body, source, sketch):
        type_id = str(getattr(source, "TypeId", ""))
        if any(token in type_id for token in ("Plane", "DatumLine", "DatumPoint", "Origin")):
            return True
        group = list(getattr(body, "Group", []) or [])
        try:
            return group.index(source) < group.index(sketch)
        except ValueError:
            return False

    def _direct_projection_allowed(self, source, sketch):
        if getattr(source, "Document", None) is not getattr(sketch, "Document", None):
            return False
        if self._source_depends_on_sketch(source, sketch):
            return False
        target_body = self._body_for_object(sketch)
        if target_body is None:
            return True
        source_body = self._body_for_object(source)
        if source_body is target_body:
            return self._source_precedes_sketch(target_body, source, sketch)
        return False

    def _binder_key(self, source, sub_name, sketch):
        document = getattr(source, "Document", None)
        return "{}|{}|{}|{}".format(
            str(getattr(document, "Name", "")),
            str(getattr(source, "Name", "")),
            str(sub_name or "<whole-object>"),
            str(getattr(sketch, "Name", "")),
        )

    def _find_projection_binder(self, body, key):
        for candidate in list(getattr(body, "Group", []) or []):
            if str(getattr(candidate, "TypeId", "")) != "PartDesign::SubShapeBinder":
                continue
            if "FusionLikeProjectionKey" not in list(getattr(candidate, "PropertiesList", []) or []):
                continue
            if str(getattr(candidate, "FusionLikeProjectionKey", "")) == key:
                return candidate
        return None

    def _set_binder_metadata(self, binder, key, source, sub_name, sketch):
        properties = list(getattr(binder, "PropertiesList", []) or [])
        definitions = (
            ("FusionLikeProjectionKey", "Persistent identity for automatic binder reuse"),
            ("FusionLikeProjectionSource", "Human-readable source of this projected reference"),
            ("FusionLikeProjectionTarget", "Destination sketch using this projected reference"),
        )
        for name, description in definitions:
            if name not in properties:
                binder.addProperty("App::PropertyString", name, "Fusion-like Projection", description)
        binder.FusionLikeProjectionKey = key
        binder.FusionLikeProjectionSource = "{} {}".format(
            str(getattr(source, "Label", getattr(source, "Name", "Source"))),
            str(sub_name or "whole object"),
        )
        binder.FusionLikeProjectionTarget = str(getattr(sketch, "Label", sketch.Name))
        for name, _description in definitions:
            try:
                binder.setEditorMode(name, 1)
            except Exception:
                pass

    def _create_or_reuse_projection_binder(self, body, source, sub_name, sketch):
        key = self._binder_key(source, sub_name, sketch)
        binder = self._find_projection_binder(body, key)
        if binder is None:
            binder = body.newObject("PartDesign::SubShapeBinder", "ProjectedReference")
            try:
                body.insertObject(binder, sketch, False)
            except Exception:
                # newObject normally inserts at the current body insertion point;
                # insertObject is the preferred ordering path when available.
                pass
            leaf = _element_leaf(sub_name) or "geometry"
            binder.Label = "Projected reference — {} {}".format(
                str(getattr(source, "Label", source.Name)), leaf
            )
            if sub_name:
                binder.Support = [(source, (str(sub_name),))]
            else:
                binder.Support = source
            if "Relative" in list(getattr(binder, "PropertiesList", []) or []):
                binder.Relative = True
            if "BindMode" in list(getattr(binder, "PropertiesList", []) or []):
                binder.BindMode = "Synchronized"
            if "Refine" in list(getattr(binder, "PropertiesList", []) or []):
                binder.Refine = False
            self._set_binder_metadata(binder, key, source, sub_name, sketch)
        else:
            try:
                body.insertObject(binder, sketch, False)
            except Exception:
                pass
        try:
            binder.Visibility = False
        except Exception:
            try:
                binder.ViewObject.Visibility = False
            except Exception:
                pass
        sketch.Document.recompute()
        return binder

    def _binder_projection_subnames(self, binder, source, source_sub_name):
        shape = getattr(binder, "Shape", None)
        if self._shape_is_null(shape):
            raise RuntimeError("The synchronized SubShapeBinder produced no geometry.")
        leaf = _element_leaf(source_sub_name)
        if leaf.startswith("Face"):
            count = len(shape.Faces)
            return ["Face{}".format(index + 1) for index in range(count)]
        if leaf.startswith("Edge"):
            count = len(shape.Edges)
            return ["Edge{}".format(index + 1) for index in range(count)]
        if leaf.startswith("Vertex"):
            count = len(shape.Vertexes)
            return ["Vertex{}".format(index + 1) for index in range(count)]

        source_type = str(getattr(source, "TypeId", ""))
        if source_type.startswith("Sketcher::"):
            count = len(shape.Edges)
            return ["Edge{}".format(index + 1) for index in range(count)]
        if len(shape.Edges):
            return ["Edge{}".format(index + 1) for index in range(len(shape.Edges))]
        if len(shape.Faces):
            return ["Face{}".format(index + 1) for index in range(len(shape.Faces))]
        if len(shape.Vertexes):
            return ["Vertex{}".format(index + 1) for index in range(len(shape.Vertexes))]
        return [""]

    def _add_external(self, sketch, source_name, sub_name, defining, intersection):
        try:
            sketch.addExternal(str(source_name), str(sub_name), bool(defining), bool(intersection))
        except TypeError:
            if defining or intersection:
                raise RuntimeError(
                    "This FreeCAD build does not expose defining/intersection external geometry. "
                    "FreeCAD 1.1 or newer is required."
                )
            sketch.addExternal(str(source_name), str(sub_name))

    def _project_direct(self, sketch, source, sub_name, defining, intersection):
        sub_names = [str(sub_name)] if sub_name else self._object_shape_subnames(source)
        if not sub_names:
            raise RuntimeError("The selected object has no projectable shape elements.")
        for name in sub_names:
            self._add_external(sketch, source.Name, name, defining, intersection)
        return len(sub_names)

    def _project_through_binder(self, sketch, source, sub_name, defining, intersection):
        body = self._body_for_object(sketch)
        if body is None:
            raise RuntimeError("A cross-body projection requires the destination sketch to be in a Body.")
        binder = self._create_or_reuse_projection_binder(body, source, sub_name, sketch)
        projected = self._binder_projection_subnames(binder, source, sub_name)
        if not projected:
            raise RuntimeError("The reference binder contains no projectable elements.")
        for name in projected:
            self._add_external(sketch, binder.Name, name, defining, intersection)
        return len(projected)

    def _project_rows(self, sketch, rows, defining, intersection):
        if not rows:
            return False
        document = getattr(sketch, "Document", None)
        if document is None:
            self._projection_warning("The destination sketch is not attached to a document.")
            return False

        self.projection_busy = True
        try:
            document.openTransaction("Project linked geometry")
            count = 0
            for source, sub_name in rows:
                source, sub_name = self._normalize_projection_source(source, sub_name, sketch)
                if source is None or source is sketch:
                    raise RuntimeError("The destination sketch cannot project itself.")
                if getattr(source, "Document", None) is not document:
                    raise RuntimeError("Projection across separate FreeCAD documents is not supported.")
                if self._source_depends_on_sketch(source, sketch):
                    raise RuntimeError(
                        "The selected source depends on this sketch and would create a circular reference."
                    )

                target_body = self._body_for_object(sketch)
                source_body = self._body_for_object(source)
                if (
                    target_body is not None
                    and source_body is target_body
                    and not self._source_precedes_sketch(target_body, source, sketch)
                ):
                    raise RuntimeError(
                        "Select geometry from an earlier feature. A later feature in the same Body "
                        "would create a circular history dependency."
                    )

                if self._direct_projection_allowed(source, sketch):
                    count += self._project_direct(
                        sketch, source, sub_name, defining, intersection
                    )
                else:
                    count += self._project_through_binder(
                        sketch, source, sub_name, defining, intersection
                    )

            document.recompute()
            document.commitTransaction()
            Gui.Selection.clearSelection()
            kind = "intersection" if intersection else ("profile" if defining else "reference")
            self.mw.statusBar().showMessage(
                "Projected {} linked element(s) as {} geometry. Press E for Pad/Pocket or Esc to stop picking.".format(
                    count, kind
                ),
                9000,
            )
            self._refresh_timeline(force=True)
            return True
        except Exception as error:
            try:
                document.abortTransaction()
            except Exception:
                pass
            Gui.Selection.clearSelection()
            _console("Projection failed:\n{}".format(traceback.format_exc()), warning=True)
            self._projection_warning("Projection failed: {}".format(error))
            return False
        finally:
            self.projection_busy = False

    def _project_selected_or_start(self, defining, intersection):
        sketch = self._projection_requirements()
        if sketch is None:
            return False
        rows = self._projection_selection_rows(sketch)
        if rows:
            self.end_projection_mode(silent=True)
            return self._project_rows(sketch, rows, defining, intersection)
        return self.start_projection_mode(defining, intersection, sketch)

    def project_profile(self):
        """Project selected/picked geometry as linked defining sketch profiles."""
        return self._project_selected_or_start(True, False)

    def project_reference(self):
        """Project selected/picked geometry as linked construction references."""
        return self._project_selected_or_start(False, False)

    def project_intersection(self):
        """Intersect selected/picked geometry with the active sketch plane."""
        return self._project_selected_or_start(True, True)

    def start_projection_mode(self, defining=True, intersection=False, sketch=None):
        sketch = sketch or self._projection_requirements()
        if sketch is None:
            return False
        self.end_projection_mode(silent=True)
        self.projection_target = (
            str(getattr(sketch.Document, "Name", "")),
            str(getattr(sketch, "Name", "")),
        )
        self.projection_defining = bool(defining)
        self.projection_intersection = bool(intersection)
        observer = ProjectionSelectionObserver(self)
        self.projection_observer = observer
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(observer)
        try:
            from pivy import coin

            view = Gui.ActiveDocument.ActiveView
            callback = view.addEventCallbackPivy(
                coin.SoMouseButtonEvent.getClassTypeId(), self._projection_mouse_event
            )
            self.projection_view = view
            self.projection_mouse_callback = callback
        except Exception:
            self.projection_view = None
            self.projection_mouse_callback = None
            _console(
                "Direct canvas picking could not be armed; tree and normal selection still work.",
                warning=True,
            )
        label = "intersection" if intersection else ("profile" if defining else "reference")
        self.mw.statusBar().showMessage(
            "Projection picking: click faces, edges, or a previous sketch for {} geometry; Esc ends.".format(
                label
            ),
            0,
        )
        return True

    def _queue_projection_selection(self, document_name, object_name, sub_name):
        key = (str(document_name or ""), str(object_name or ""), str(sub_name or ""))
        if key in self.projection_pending:
            return
        self.projection_pending.add(key)

        def dispatch():
            self.projection_pending.discard(key)
            self._projection_observer_selection(*key)

        QtCore.QTimer.singleShot(0, dispatch)

    def _projection_mouse_event(self, event_callback):
        """Pick external faces/edges even when Sketcher suppresses normal selection."""
        if self.projection_observer is None or self.projection_busy:
            return
        try:
            from pivy import coin

            event = event_callback.getEvent()
            if event.getButton() != coin.SoMouseButtonEvent.BUTTON1:
                return
            if event.getState() != coin.SoButtonEvent.DOWN:
                return
            position = event.getPosition().getValue()
            view = self.projection_view or Gui.ActiveDocument.ActiveView
            hits = view.getObjectsInfo((int(position[0]), int(position[1]))) or []
            if not hits:
                return
            target_document_name, target_name = self.projection_target or ("", "")
            for hit in hits:
                object_name = str(hit.get("Object", "") or "")
                if not object_name or object_name == target_name:
                    continue
                document_name = str(hit.get("Document", "") or target_document_name)
                component = str(hit.get("Component", "") or "")
                event_callback.setHandled()
                self._queue_projection_selection(document_name, object_name, component)
                return
        except Exception:
            _console("Projection canvas picking failed:\n{}".format(traceback.format_exc()), warning=True)

    def _projection_observer_selection(self, document_name, object_name, sub_name):
        if self.projection_observer is None or self.projection_busy:
            return
        if not self.projection_target:
            return
        target_document_name, target_name = self.projection_target
        if document_name != target_document_name:
            Gui.Selection.clearSelection()
            self._projection_warning("Pick geometry from the same FreeCAD document as the sketch.")
            return
        try:
            target_document = App.getDocument(target_document_name)
        except Exception:
            target_document = None
        if target_document is None:
            self.end_projection_mode(silent=True)
            return
        sketch = target_document.getObject(target_name)
        if sketch is None or sketch is not self._active_edited_sketch():
            self.end_projection_mode(silent=True)
            self._projection_warning("The destination sketch is no longer being edited.")
            return
        source = target_document.getObject(object_name)
        if source is None or source is sketch:
            Gui.Selection.clearSelection()
            return
        self._project_rows(
            sketch,
            [(source, str(sub_name or ""))],
            self.projection_defining,
            self.projection_intersection,
        )

    def end_projection_mode(self, silent=False):
        observer = self.projection_observer
        view = self.projection_view
        callback = self.projection_mouse_callback
        self.projection_observer = None
        self.projection_view = None
        self.projection_mouse_callback = None
        self.projection_pending.clear()
        self.projection_target = None
        if view is not None and callback is not None:
            try:
                from pivy import coin

                view.removeEventCallbackPivy(
                    coin.SoMouseButtonEvent.getClassTypeId(), callback
                )
            except Exception:
                pass
        if observer is not None:
            try:
                Gui.Selection.removeObserver(observer)
            except Exception:
                pass
        if not silent and self.mw is not None:
            self.mw.statusBar().showMessage("Projection picking ended", 3500)
        return observer is not None

    def start_extrude(self, command_id):
        sketch = self._active_edited_sketch()
        if sketch is None:
            return self._run_command(command_id)
        return self._finish_sketch_and_run(sketch, command_id)

    def _finish_sketch_and_run(self, sketch, command_id):
        self.end_projection_mode(silent=True)
        document = getattr(sketch, "Document", None)
        try:
            if document is not None:
                document.recompute()
            Gui.ActiveDocument.resetEdit()
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(sketch)
        except Exception:
            _console("Could not finish the projected sketch:\n{}".format(traceback.format_exc()), warning=True)
            return False

        QtCore.QTimer.singleShot(180, lambda cid=command_id: self._run_command(cid))
        return True

    # ---------- command execution, menus, and shortcuts ----------

    def _command_active(self, command_id):
        try:
            if hasattr(Gui, "isCommandActive"):
                return bool(Gui.isCommandActive(command_id))
        except Exception:
            pass
        action = self._find_action(command_id)
        return bool(action is not None and action.isEnabled())

    def _run_command(self, command_id):
        if not self._command_active(command_id):
            return False
        try:
            Gui.runCommand(command_id, 0)
            return True
        except Exception:
            action = self._find_action(command_id)
            if action is not None and action.isEnabled():
                action.trigger()
                return True
        return False

    def _run_first_active(self, command_ids):
        for command_id in command_ids:
            if self._run_command(command_id):
                return True
        return False

    def _popup_commands(self, title, rows):
        active_rows = []
        for label, command_id in rows:
            action = self._find_action(command_id)
            if action is not None and self._command_active(command_id):
                active_rows.append((label, action))
        if not active_rows:
            return False

        menu = QtWidgets.QMenu(title, self.mw)
        for label, original in active_rows:
            proxy = self._proxy_action(menu, label, original)
            menu.addAction(proxy)
        _menu_exec(menu, QCursor.pos())
        return True

    def show_extrude_menu(self):
        menu = QtWidgets.QMenu("Extrude", self.mw)
        pad_source = self._find_action("PartDesign_Pad")
        pocket_source = self._find_action("PartDesign_Pocket")
        pad = QAction(pad_source.icon() if pad_source else QIcon(), "Add / Pad", menu)
        pocket = QAction(
            pocket_source.icon() if pocket_source else QIcon(), "Cut / Pocket", menu
        )
        menu.addAction(pad)
        menu.addAction(pocket)
        chosen = _menu_exec(menu, QCursor.pos())
        if chosen == pad:
            return bool(self.start_extrude("PartDesign_Pad"))
        if chosen == pocket:
            return bool(self.start_extrude("PartDesign_Pocket"))
        return True

    def show_press_pull_menu(self):
        if self._active_edited_sketch() is not None:
            return self.show_extrude_menu()
        return self._popup_commands(
            "Press / Pull",
            (
                ("Add / Pad", "PartDesign_Pad"),
                ("Cut / Pocket", "PartDesign_Pocket"),
                ("Shell / Thickness", "PartDesign_Thickness"),
                ("Draft Faces", "PartDesign_Draft"),
                ("Transform", "Std_TransformManip"),
            ),
        )

    def show_palette(self):
        if self.palette is None:
            self.palette = CommandPalette(self)
        self.palette.open_palette()

    def _focus_is_text_input(self):
        focus = QtWidgets.QApplication.focusWidget()
        if focus is None:
            return False
        text_types = tuple(
            cls
            for cls in (
                getattr(QtWidgets, "QLineEdit", None),
                getattr(QtWidgets, "QTextEdit", None),
                getattr(QtWidgets, "QPlainTextEdit", None),
                getattr(QtWidgets, "QAbstractSpinBox", None),
                getattr(QtWidgets, "QComboBox", None),
            )
            if cls is not None
        )
        return isinstance(focus, text_types)

    def eventFilter(self, watched, event):
        if not self.active or event.type() != QtCore.QEvent.KeyPress:
            return False

        app = self.app or QtWidgets.QApplication.instance()
        if app is not None:
            if app.activeModalWidget() is not None or app.activePopupWidget() is not None:
                return False
            focus = app.focusWidget()
            if focus is not None and focus is not self.mw and not self.mw.isAncestorOf(focus):
                return False

        if event.isAutoRepeat() or self._focus_is_text_input():
            return False

        key = event.key()
        modifiers = event.modifiers()
        if key == QtCore.Qt.Key_Escape and self.projection_observer is not None:
            self.end_projection_mode()
            return True
        if key == QtCore.Qt.Key_P and modifiers == QtCore.Qt.NoModifier:
            return bool(self.project_profile())
        if key == QtCore.Qt.Key_P and modifiers == QtCore.Qt.ShiftModifier:
            return bool(self.project_reference())
        if key == QtCore.Qt.Key_T and modifiers == QtCore.Qt.ShiftModifier:
            return bool(self.open_fusion_thread())
        assembly_context = (
            "Assembly" in _active_workbench_name()
            or _active_workbench_name() in ("Assembly4Workbench", "A2plusWorkbench")
        )
        copy_modifier = modifiers in (QtCore.Qt.ControlModifier, QtCore.Qt.MetaModifier)
        if assembly_context and copy_modifier and key == QtCore.Qt.Key_C:
            return bool(self.copy_assembly_components())
        if assembly_context and modifiers in (
            QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
            QtCore.Qt.MetaModifier | QtCore.Qt.ShiftModifier,
        ) and key == QtCore.Qt.Key_V:
            return bool(self.paste_assembly_components(in_place=True))
        if assembly_context and copy_modifier and key == QtCore.Qt.Key_V:
            return bool(self.paste_assembly_components(in_place=False))
        if assembly_context and copy_modifier and key == QtCore.Qt.Key_D:
            return bool(self.duplicate_assembly_components())
        if modifiers != QtCore.Qt.NoModifier:
            return False
        if key == QtCore.Qt.Key_S:
            self.show_palette()
            return True
        if key == QtCore.Qt.Key_H:
            return bool(self.show_hole_menu())
        if key == QtCore.Qt.Key_E:
            return bool(self.show_extrude_menu())
        if key == QtCore.Qt.Key_Q:
            return bool(self.show_press_pull_menu())
        if key in self.KEY_COMMANDS:
            return bool(self._run_first_active(self.KEY_COMMANDS[key]))
        return False


_COMMANDS_REGISTERED = False


def register_commands():
    global _COMMANDS_REGISTERED
    if _COMMANDS_REGISTERED:
        return
    try:
        Gui.addCommand(HOLE_COMMAND_ID, FusionHoleCommand())
    except Exception:
        pass
    try:
        Gui.addCommand(THREAD_COMMAND_ID, FusionThreadCommand())
    except Exception:
        pass
    _COMMANDS_REGISTERED = True


def install_menu():
    """Install a persistent control menu, even when the profile is disabled."""
    global _MENU
    register_commands()
    mw = Gui.getMainWindow()
    menu_bar = mw.menuBar()

    old_menu = menu_bar.findChild(QtWidgets.QMenu, MENU_NAME)
    if old_menu is not None:
        menu_bar.removeAction(old_menu.menuAction())
        old_menu.deleteLater()

    menu = QtWidgets.QMenu("Fusion-like", menu_bar)
    menu.setObjectName(MENU_NAME)

    apply_action = menu.addAction("Apply / rebuild Fusion-like profile")
    search_action = menu.addAction("Command Search (S)")
    timeline_action = menu.addAction("Show / hide parametric timeline")
    menu.addSeparator()
    hole_action = menu.addAction("Hole & Thread (H)")
    thread_action = menu.addAction("Independent Thread (Shift+T)")

    projection_menu = menu.addMenu("Project / Include")
    project_profile_action = projection_menu.addAction("Project linked profile (P)")
    project_reference_action = projection_menu.addAction("Project linked reference (Shift+P)")
    project_intersection_action = projection_menu.addAction("Intersect with sketch plane")
    projection_menu.addSeparator()
    end_projection_action = projection_menu.addAction("End projection picking (Esc)")
    project_profile_action.setObjectName("FusionLike_MenuProjectProfile")
    project_reference_action.setObjectName("FusionLike_MenuProjectReference")
    project_intersection_action.setObjectName("FusionLike_MenuProjectIntersection")
    end_projection_action.setObjectName("FusionLike_MenuEndProjection")

    drawing_menu = menu.addMenu("Drawing workflow")
    drawing_insert_action = drawing_menu.addAction("Insert dimensionable model view")
    drawing_help_action = drawing_menu.addAction("Drawing workflow guide")
    assembly_menu = menu.addMenu("Assembly workflow")
    assembly_add_action = assembly_menu.addAction("Add selected model to Assembly")
    assembly_copy_action = assembly_menu.addAction("Copy components")
    assembly_paste_action = assembly_menu.addAction("Paste component instances")
    assembly_duplicate_action = assembly_menu.addAction("Duplicate selected components")
    assembly_menu.addSeparator()
    assembly_diagnostics_action = assembly_menu.addAction("Mate diagnostics")
    assembly_solve_action = assembly_menu.addAction("Solve and diagnose")

    menu.addSeparator()
    restore_action = menu.addAction("Restore original FreeCAD interface")

    apply_action.triggered.connect(enable)
    search_action.triggered.connect(show_palette)
    timeline_action.triggered.connect(toggle_timeline)
    hole_action.triggered.connect(open_fusion_hole)
    thread_action.triggered.connect(open_fusion_thread)
    project_profile_action.triggered.connect(project_profile)
    project_reference_action.triggered.connect(project_reference)
    project_intersection_action.triggered.connect(project_intersection)
    end_projection_action.triggered.connect(end_projection)
    drawing_insert_action.triggered.connect(insert_dimensionable_model_view)
    drawing_help_action.triggered.connect(show_drawing_workflow_help)
    assembly_add_action.triggered.connect(add_selected_to_assembly)
    assembly_copy_action.triggered.connect(copy_assembly_components)
    assembly_paste_action.triggered.connect(paste_assembly_components)
    assembly_duplicate_action.triggered.connect(duplicate_assembly_components)
    assembly_diagnostics_action.triggered.connect(show_assembly_mate_diagnostics)
    assembly_solve_action.triggered.connect(solve_assembly_with_diagnostics)
    restore_action.triggered.connect(restore)

    menu_bar.addMenu(menu)
    _MENU = menu
    return menu


def start(force=False):
    global _PROFILE
    register_commands()
    install_menu()
    pref = App.ParamGet(PREF_PATH)
    if not force and not pref.GetBool("Enabled", True):
        return
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    _PROFILE.apply()


def enable():
    App.ParamGet(PREF_PATH).SetBool("Enabled", True)
    start(force=True)


def restore():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    _PROFILE.restore()
    install_menu()


def rebuild():
    global _PROFILE
    if _PROFILE is None:
        start(force=True)
    else:
        _PROFILE.rebuild()


def show_palette():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    _PROFILE.show_palette()


def toggle_timeline():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    _PROFILE.toggle_timeline()


def open_fusion_hole():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.open_fusion_hole()


def open_fusion_thread():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.open_fusion_thread()



def insert_dimensionable_model_view():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.insert_dimensionable_model_view()


def show_drawing_workflow_help():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.show_drawing_workflow_help()


def copy_assembly_components():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.copy_assembly_components()


def paste_assembly_components():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.paste_assembly_components()


def add_selected_to_assembly():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.add_selected_to_assembly()


def duplicate_assembly_components():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.duplicate_assembly_components()


def show_assembly_mate_diagnostics():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.show_assembly_mate_diagnostics()


def solve_assembly_with_diagnostics():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.solve_assembly_with_diagnostics()


def project_profile():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.project_profile()


def project_reference():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.project_reference()


def project_intersection():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = FusionProfile()
    return _PROFILE.project_intersection()


def end_projection():
    global _PROFILE
    if _PROFILE is None:
        return False
    return _PROFILE.end_projection_mode()
