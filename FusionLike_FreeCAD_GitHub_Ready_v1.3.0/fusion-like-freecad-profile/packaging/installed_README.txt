FUSION-LIKE FREECAD WORKFLOW PROFILE
====================================
Version: 1.3.0
Target: FreeCAD 1.1 or newer

PURPOSE
-------
This package is an in-place update to the Fusion-like FreeCAD profile. Version
1.3 concentrates on three workflow corrections:

1. Sketch editing now has a true contextual Sketch ribbon instead of remaining
   frozen on the Part Design ribbon.
2. The Drawing workspace distinguishes dimensionable model views from raster
   Active View snapshots and provides a guided model-view/dimension workflow.
3. The Assembly workspace adds fast instance copy/paste and much more explicit
   connector and solver diagnostics.

The threaded Hole, independent Thread, persistent face/edge projection,
Part Design, Assembly, Drawing, and restoration features from versions 1.1 and
1.2 remain installed.

This is a workflow compatibility layer. FreeCAD and Autodesk Fusion use
different kernels, object models, solvers, drawing systems, and history graphs,
so exact implementation identity is not possible. The profile reuses native
FreeCAD commands and document objects wherever they provide the required
behavior.

INSTALL OR UPGRADE
------------------
1. Copy Install_FusionLike_FreeCAD_v1.3.0.FCMacro into the User macros location
   shown by Macro -> Macros.
2. Run the installer macro.
3. Install directly over v1.0, v1.1, or v1.2. Do not uninstall first.
4. The original FreeCAD interface backup captured by the first installation is
   retained.
5. Restarting is normally unnecessary. Restart once if the previous runtime was
   loaded for a long session or an old task dialog remains open.

Installed files:

<FreeCAD user data>/Mod/FusionLikeUI/
    Init.py
    InitGui.py
    fusion_like_ui_runtime.py
    README.txt

SKETCH MODE: CONTEXTUAL RIBBON
------------------------------
The profile no longer chooses the ribbon solely from the active workbench name.
FreeCAD normally stays in PartDesignWorkbench while a Sketch is in edit mode,
so version 1.3 also watches the active edited object.

When a Sketch enters edit mode, the top interface changes automatically to:

SKETCH / FINISH
* Leave Sketch
* Cancel Sketch
* View Sketch
* Section View
* Stop current sketch operation

CREATE
* Line / Polyline
* Rectangle tools
* Arc tools
* Circle
* Conic tools
* Slot tools
* Point
* Text
* Toggle construction geometry
* Project / Include

PROJECT / INCLUDE
* Project selected or clicked faces, edges, vertices, or previous sketches as
  linked defining geometry (P)
* Project as linked construction/reference geometry (Shift+P)
* Intersect external geometry with the sketch plane
* Carbon Copy another sketch
* End continuous projection picking (Esc)

MODIFY
* Trim, split, and extend
* Fillet / chamfer
* Offset
* Move, rotate, scale, and symmetry
* Copy, cut, and paste sketch geometry

CONSTRAIN
* Smart dimension and separated dimension tools
* Coincident, horizontal/vertical, parallel, perpendicular, tangent, equal,
  symmetric, block, and constraint-state tools

INSPECT
* Select under-constrained geometry
* Select conflicting or redundant constraints
* Constraint selection and visual diagnostics
* Sketch validation

The profile checks context every 250 ms. It also includes Sketcher command
availability in the context signature, so it rebuilds once more if FreeCAD
finishes registering edit-mode commands shortly after the Sketch opens.

DRAWING WORKFLOW
----------------
Choose DRAWING in the workspace selector.

IMPORTANT: ACTIVE VIEW IS NOT A MODEL VIEW
------------------------------------------
TechDraw's native Active View command captures the visible 3D viewport as an
image. It is useful for a shaded illustration, but it contains no associative
model edges or vertices. It therefore cannot be used for normal TechDraw
geometry dimensions.

Version 1.3 moves that command into:

    CREATE -> Reference Capture -> Active View Snapshot — raster, not dimensionable

Use the following workflow for engineering drawings:

1. Create a sheet with New Sheet, or let Insert Model View create the default
   sheet.
2. Click Insert Model View.
3. Select a Body, App Part, component Link, native Assembly, or eligible root
   Part feature. Multiple source objects may be selected for one view.
4. Choose an existing sheet or Create a new default sheet.
5. Confirm. FreeCAD's native model-view/projected-view task opens.
6. Set the base orientation and add the desired Front, Top, Right, Left, Rear,
   Bottom, or other projected views supported by the installed TechDraw build.
7. Finish the view task.
8. On the drawing sheet, click the actual projected Edge or Vertex geometry.
   Selecting only the Page or the view item in the model tree is not enough.
9. Click Smart Dimension or choose a specific dimension type.

Insert Model View uses a model-linked TechDraw DrawViewPart/Projection Group
workflow. The resulting geometry remains associated with the source model and
is suitable for TechDraw dimensions, section views, details, hatching, and
annotations.

SMART DIMENSION CHECKS
----------------------
Before a dimension command starts, the profile checks the current selection.
It explains these common problems:

* Nothing is selected.
* Only a drawing Page or view tree item is selected.
* The selected object is an Active View raster snapshot.
* No drawing Edge, Vertex, or Face subelement is selected.

You may deliberately choose Continue anyway when using an unusual native
TechDraw selection pattern.

The Drawing workflow guide is also available under Reference Capture.

ASSEMBLY: ADD, COPY, PASTE, AND DUPLICATE
-----------------------------------------
Choose ASSEMBLE in the workspace selector and create or activate a native
FreeCAD Assembly.

The ASSEMBLE group now includes:

Add Selected
    Select a Body, App Part, Part feature, Link, or existing component and click
    Add Selected. A new component instance is inserted at its current placement.

Copy (Ctrl+C)
    Copies the selected component instances or selected source Parts/Bodies to
    a Fusion-like component clipboard.

Paste with offset (Ctrl+V)
    Creates new unconstrained component instances with a small X offset so the
    copies are immediately visible and can be positioned or mated.

Paste in place (Ctrl+Shift+V)
    Creates instances at the source placements. This is useful for replacing,
    patterning, or assembling geometrically coincident source models, but the
    copies initially overlap.

Duplicate selected (Ctrl+D)
    Copies and immediately pastes the selected component instances with an
    offset.

The inserted components are native App::Link instances. Subassemblies use
Assembly::AssemblyLink when the installed FreeCAD build exposes it; otherwise
an App::Link fallback is used and reported.

For links between separate documents, save both the Assembly document and the
source document first. The profile rejects insertions that would produce a
document dependency loop and reports every skipped source.

GUIDED MATE / JOINT DIAGNOSTICS
-------------------------------
The Joint, As-Built Joint, and Constraint menus run FreeCAD's native Assembly
commands with additional preflight analysis.

Before opening a joint task, the profile describes the selected connector
geometry and checks for:

* Fewer or more than two connector references
* Two references resolving to the same component instance
* Whole-object selections where a face, edge, vertex, datum, axis, or coordinate
  system is needed
* Missing or broken linked subelements
* Joint types that require axial geometry but received only arbitrary geometry
* Ball joints without point-like references
* Parallel/perpendicular/angle constraints without directional references
* Two already-connected components that may close a redundant constraint loop
* No grounded component or no grounded path
* Obvious cylindrical/circular diameter mismatch between axial connectors

While the native joint task is open, a Fusion-like Mate Diagnostics panel is
inserted into the task form and refreshed as references change.

If the native task rejects a reference, throws an exception, or cannot commit a
mate, the profile presents the current reference analysis rather than only a
generic failure.

POST-MATE SOLVER STATUS
-----------------------
Some Assembly failures return a numeric solver status instead of raising a
Python exception. Version 1.3 checks the native status immediately after a mate
is committed and decodes:

  0    solved successfully
 -6    no grounded/fixed component
 -4    over-constrained assembly
 -3    conflicting joints
 -5    malformed or broken joint reference
 -1    solver error
 -2    redundant joints

A failed mate report names the newly committed joint, summarizes the active
joint inventory, identifies likely causes, and recommends the relevant Inspect
Solver selection command. The failed joint is selected in the model tree when
possible.

The Solve dropdown also includes Solve and show diagnostics, which always opens
this decoded report. Inspect Solver exposes the native selectors for conflicting,
redundant, malformed, and under-constrained components when those commands are
available in the installed build.

MATE SELECTION GUIDANCE
-----------------------
Typical reference choices:

Fixed / rigid
    Suitable faces, edges, vertices, datums, axes, or coordinate systems on two
    different components.

Revolute or cylindrical
    Prefer two cylindrical faces, circular edges, or explicit axes. Verify that
    they represent the intended common axis.

Slider
    Prefer straight edges, axes, planar references, or coordinate systems whose
    Z axis is the intended motion direction.

Ball
    Prefer vertices, spherical centers, or other point-like references.

Parallel, perpendicular, or angle
    Use planar faces, straight edges, axes, datum planes, or coordinate systems
    that define an orientation.

Distance
    May use point, edge, face, axis, or datum references according to the
    distance relation intended.

If two apparently compatible cylindrical parts will not mate, first verify that
both selections belong to different component instances, that one component is
grounded or connected to ground, and that no earlier joints already remove the
same degrees of freedom.

RETAINED THREAD FEATURES
------------------------
H opens the Fusion-style native PartDesign Hole & Thread dialog.
Shift+T creates or edits the independent cylindrical Thread feature.

The Hole workflow retains FreeCAD's native thread standards, sizes, classes,
modeled/cosmetic options, direction, thread depth, counterbore/countersink,
drill-point, taper, and clearance properties.

The independent Thread feature remains a persistent PartDesign::FeaturePython
that can model a helical cut or store cosmetic callout metadata. Reinstall this
profile before editing or recomputing independent Thread objects after an
uninstall.

RETAINED PROJECTION WORKFLOW
----------------------------
P           Linked defining projection
Shift+P     Linked construction/reference projection
Esc         End projection picking
E           Finish sketch and choose Pad or Pocket

Imported and cross-body geometry continues to use synchronized
PartDesign::SubShapeBinder references where direct Sketcher links are not valid.

OTHER SHORTCUTS
---------------
S           Command search
H           Hole / threaded-hole menu
Shift+T     Independent Thread
E           Pad / Pocket menu
Q           Press / Pull approximation
F           Fillet or sketch fillet
M           Transform or sketch move
V           Toggle visibility
I           Measure

While editing a sketch:
L           Line
R           Rectangle
C           Circle
T           Trim
O           Offset
D           Dimension
X           Construction geometry

RESTORE OR UNINSTALL
--------------------
Use Fusion-like -> Restore original FreeCAD interface to disable the profile and
restore the saved window layout and navigation preferences.

Run Uninstall_FusionLike_FreeCAD_v1.3.0.FCMacro to restore the interface, remove
the startup module, and request one FreeCAD restart.

OPTIONAL SMOKE TEST
-------------------
After installation, run FusionLikeUI_SmokeTest_v1.3.0.FCMacro for a
non-destructive check of the installed version, required runtime methods, and
currently registered FreeCAD command actions. Workbench-specific actions may be
reported as not loaded until that workbench has been activated once.

LIMITATIONS
-----------
* Active View Snapshot remains raster by design and cannot be converted into an
  associative dimensionable model view.
* TechDraw dimension selection semantics remain FreeCAD's semantics; the profile
  can guide and validate but does not replace TechDraw's dimension engine.
* Assembly connector compatibility is partly geometric and partly dependent on
  the existing constraint graph. Preflight diagnostics cannot prove that every
  nonlinear assembly will solve.
* Topological changes that replace referenced faces or edges may still require
  repairing projections, threads, drawing dimensions, or joint references.
* Modeled helical threads can significantly increase recompute time and file
  complexity. Cosmetic threads are usually preferable for large assemblies.
* The profile uses no Autodesk assets.

TROUBLESHOOTING
---------------
Open View -> Panels -> Report view. Runtime messages are prefixed:

    [Fusion-like UI]

For a reproducible problem, record:

* FreeCAD version from Help -> About FreeCAD -> Copy to clipboard
* Operating system
* Exact command sequence
* Selected objects and subelements
* Report-view traceback or solver report
* Whether the file is local or links external component documents
