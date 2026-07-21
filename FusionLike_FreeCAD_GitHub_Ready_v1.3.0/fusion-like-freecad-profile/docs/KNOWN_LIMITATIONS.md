# Known limitations

## Not an implementation clone

The project reorganizes and extends FreeCAD workflows. It does not reproduce Autodesk’s kernels, cloud data model, T-spline environment, timeline engine, assembly solver, CAM system, or drawing implementation.

## Topological naming

References to `FaceN`, `EdgeN`, and `VertexN` can break when upstream topology changes. FreeCAD’s element naming helps but cannot guarantee every reference survives a major feature rewrite. Projection, threads, dimensions, and joints may need repair.

## Independent Thread dependency

The independent Thread is a custom `PartDesign::FeaturePython`. Its last saved shape can remain visible without the profile, but editing or recomputing it requires the runtime to be installed.

## Modeled thread cost

Physical helical threads can greatly increase recomputation time, file size, boolean complexity, meshing time, and drawing HLR time. Use cosmetic threads unless physical flank geometry is required.

## Thread standards

The independent cylindrical Thread intentionally omits standalone NPT-style tapered-face behavior. Use the native threaded Hole workflow for tapered internal threads supported by FreeCAD.

## Projection boundaries

Direct cross-document Sketch external geometry is not supported. Cross-Body and imported geometry are mediated through SubShapeBinders when valid. Circular and future-history dependencies are rejected.

## Drawing snapshots

Active View Snapshot is a raster image by design. It cannot be converted automatically into an associative model view and is not a source for normal TechDraw dimensions.

## Drawing dimensions

The profile validates common selection mistakes but does not replace TechDraw’s dimension engine. Dimension semantics, HLR completion, and reference repair remain native FreeCAD behavior.

## Assembly diagnostics

Preflight is advisory. Assembly compatibility depends on the complete nonlinear constraint graph, connector frames, offsets, grounding, and solver state. Geometrically similar parts are not guaranteed to solve under a chosen joint type.

## Assembly document links

Cross-document components require saved files and stable source object identities. Moving, renaming, closing, or replacing source documents can break links.

## UI themes and platform differences

Qt widget sizes, action registration timing, menu text, and icons vary across platforms and FreeCAD builds. The profile uses command IDs and compatibility fallbacks, but some visual differences are expected.

## Static validation boundary

Repository CI can compile and inspect the code without importing FreeCAD. It cannot exercise the live GUI, FreeCAD document model, Qt signal behavior, or Open CASCADE geometry operations.
