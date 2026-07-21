# User-facing feature reference

This document describes commands exposed by the profile. Native command availability still depends on the active document, selection, workbench registration, and installed FreeCAD build.

## Global interface

| Function | Access | Preconditions | Result |
|---|---|---|---|
| Apply / rebuild profile | Fusion-like menu | FreeCAD GUI available | Recreates profile toolbars, docks, event filters, shortcuts, and timeline |
| Restore original interface | Fusion-like menu | Original state captured | Removes profile UI and restores saved workbench/layout/navigation preferences |
| Command Search | `S` | No modal dialog or text input | Searchable list of registered FreeCAD actions |
| Workspace selector | top-left combo | Corresponding workbench installed | Activates Design, Surface, Mesh, Sheet Metal, Assembly, Drawing, Manufacture, or Render |
| Timeline | bottom dock / menu toggle | Active document | Displays compatible features and supports Body-Tip rollback |

## Design and sketch

| Function | Access | Selection/context | Output |
|---|---|---|---|
| New Body | Create | active document | native `PartDesign::Body` |
| New Sketch | Create | plane/face/body context | native `Sketcher::SketchObject` |
| Extrude | `E` or Create | finished Sketch/profile | native Pad or Pocket |
| Press/Pull | `Q` | compatible selection | menu over native Pad, Pocket, Thickness, Draft, Transform |
| Project linked profile | `P` | active edited Sketch; source geometry | defining external Sketch geometry, direct or binder-mediated |
| Project linked reference | `Shift+P` | active edited Sketch | construction/reference external geometry |
| Intersect with sketch plane | Project/Include | active edited Sketch | linked defining intersection curves |
| End projection | `Esc` | projection session active | removes selection observer/callback and ends picking |
| Carbon Copy | Sketch ribbon | active edited Sketch; source Sketch | native Sketcher carbon copy |
| Finish sketch and feature | `E` in Sketch | active edited Sketch | exits edit and starts Pad/Pocket |

## Hole and thread

| Function | Access | Selection/context | Output |
|---|---|---|---|
| Hole & Thread | `H` | selected Sketch or existing Hole | native `PartDesign::Hole` configured by Fusion-like dialog |
| Native Hole command | Hole menu | native command active | standard FreeCAD Hole task |
| Independent Thread | `Shift+T` | cylindrical faces on current Body Tip, or selected existing Thread | persistent `PartDesign::FeaturePython` helical cut or cosmetic metadata |
| Thread callout | Drawing annotation group | selected Hole/Thread and TechDraw page | linked TechDraw annotation |

## Drawing

| Function | Access | Selection/context | Output |
|---|---|---|---|
| New Sheet | Create | active document | native TechDraw page/template |
| Insert Model View | Create | source Body/Part/Link/Assembly | model-linked TechDraw view and native projected-view task |
| Active View Snapshot | Reference Capture | TechDraw page and open 3D view | raster `TechDraw::DrawViewImage`, not associative geometry |
| Smart Dimension | Dimensions | drawing edge/vertex/face selection | validated launch of native dimension command |
| Section / Detail / Broken View | Create | compatible base view/geometry | native TechDraw view object |
| BOM / Spreadsheet view | Output | active Assembly/page as required | native Assembly BOM and TechDraw Spreadsheet view |
| Export PDF | Output | selected or active TechDraw page | PDF through TechDraw GUI export helper |
| Export SVG/DXF | Output | selected or active page | native TechDraw export |

## Assembly

| Function | Access | Selection/context | Output |
|---|---|---|---|
| Create Assembly | Assemble | active document | native `Assembly::AssemblyObject` |
| Insert Component | Assemble | active Assembly | native Assembly insertion task |
| Add Selected | Assemble | selected Body/Part/Feature/Link | component instance at current placement |
| Copy Components | `Ctrl+C` | source objects or component instances selected | JSON payload in custom clipboard MIME type |
| Paste with offset | `Ctrl+V` | active Assembly; valid clipboard | new component instances offset along X |
| Paste in place | `Ctrl+Shift+V` | active Assembly; valid clipboard | new instances at source placements |
| Duplicate selected | `Ctrl+D` | component instances selected | copy and paste with offset |
| Ground/Unground | Assemble | selected component | native grounded-joint state |
| Guided Joint | Joint menus | two connector subelements | native joint task plus diagnostics |
| Why won’t this mate? | Inspect Solver | selection or active Assembly | textual connector/constraint analysis |
| Solve and show diagnostics | Solve menu | active Assembly | native solve plus decoded status report |
| Exploded View / Snapshot / Simulation / BOM | Motion/Output | active Assembly and suitable joints/components | native Assembly objects/tasks |

## Selection conventions

- Tree selection chooses whole objects; 3D or drawing-canvas selection can include subelements.
- Joint creation generally needs two subelement references on different component instances.
- Drawing dimensions generally need TechDraw edge/vertex/face subelements, not only a page or view tree item.
- Projection accepts whole earlier Sketches, faces, edges, and vertices, but dependency checks can reject later or circular sources.
