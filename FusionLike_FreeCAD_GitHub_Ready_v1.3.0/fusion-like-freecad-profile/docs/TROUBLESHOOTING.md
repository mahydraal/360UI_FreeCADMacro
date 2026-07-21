# Troubleshooting

## First diagnostic steps

1. Open **View → Panels → Report view**.
2. Reproduce the problem once.
3. Copy all lines prefixed `[Fusion-like UI]` plus any adjacent Python traceback.
4. Run the v1.3 smoke-test macro.
5. Record the FreeCAD version from **Help → About FreeCAD → Copy to clipboard**.

## Sketch ribbon does not appear

- Confirm that a `Sketcher::SketchObject` is actually in edit mode.
- Wait a fraction of a second for late Sketcher command registration.
- Choose **Fusion-like → Apply / rebuild Fusion-like profile**.
- Activate the Sketcher workbench once, then return to Part Design and edit the Sketch again.
- Check Report view for `_refresh_ui_context_if_needed` errors.

## Sketch primitive button is missing

The runtime uses grouped-command IDs first and individual-command fallbacks. A missing button can indicate that the corresponding native command is not registered in that build. Search for the primitive with **S** and include its action object name in the issue report.

## Projection fails

Common causes:

- destination Sketch is not in edit mode
- source is the destination Sketch itself
- source feature occurs later in the same Body
- source already depends on the destination Sketch
- cross-document direct links are attempted
- the selected subelement was deleted or renamed by a topology change

For cross-document workflows, import or link the source into the destination document first.

## Pad or Pocket cannot use a projected profile

- Confirm that **P**, not Shift+P, created defining geometry.
- Check that the resulting loops are closed and non-self-intersecting.
- Confirm the Sketch belongs to the active Body.
- Use Sketch validation and inspect redundant/conflicting constraints.

## Modeled thread is slow or fails

- Try cosmetic mode to verify the standard/size metadata first.
- Reduce thread length.
- Remove extreme custom clearance.
- Confirm the selected face is cylindrical and belongs to the current Body Tip source.
- Check for self-intersecting helical profiles or a boolean failure in Report view.

## Drawing view cannot be dimensioned

- Confirm it is a model-linked TechDraw view, not `ActiveView` / `DrawViewImage`.
- Select the actual projected edge or vertex on the drawing page.
- Wait for HLR recomputation to finish.
- Confirm the source object has a valid shape.
- Try a specific dimension command after Smart Dimension explains the selection.

## Assembly component cannot be added

- Activate or create an Assembly.
- Save both source and Assembly documents for cross-document links.
- Confirm the source object has a shape or is a supported Part/Body/Link.
- Avoid linking a document back into itself through a dependency cycle.

## Two parts look compatible but will not mate

Check in this order:

1. The references belong to two different **component instances**, not two faces of the same source object.
2. One component is grounded or connected to ground.
3. Connector geometry matches the joint type: axial references for revolute/cylindrical; point-like references for ball.
4. An earlier joint has not already removed the same degrees of freedom.
5. Offsets and reverse direction are not forcing an impossible placement.
6. Linked face/edge names are still valid after source-model edits.

Run **Why won’t this mate?** before creation and **Solve and show diagnostics** afterward.

## Solver status guide

- `-6`: ground a component
- `-4`: suppress the newest joint or replace multiple constraints with a single intended joint
- `-3`: inspect conflicting joints and connector directions
- `-5`: re-pick broken references
- `-2`: remove redundant joints
- `-1`: simplify the graph, check offsets, and report a minimal case

## Restore does not recover the exact window layout

Qt window-state serialization depends on available docks and workbenches. Manually restore remaining panels through **View → Panels** and toolbars through **View → Toolbars**, then report the FreeCAD build and before/after state.
