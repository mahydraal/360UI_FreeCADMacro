# Public testing guide

## Test philosophy

The repository supports three levels of validation:

1. **Static validation** outside FreeCAD: syntax, embedded payload equality, internal method resolution, documentation links, release contents, and ZIP integrity.
2. **Smoke testing** inside FreeCAD: installation state and command registration without modifying a document.
3. **Manual workflow testing** inside FreeCAD: real GUI interactions and document recomputation.

Static checks cannot prove GUI or Open CASCADE behavior. Public test reports are essential.

## Static validation

From the repository root:

```bash
python tools/validate_package.py --repo .
python tools/build_release.py --repo . --check
```

The GitHub Actions workflow runs the same checks on pull requests.

## FreeCAD smoke test

Install the profile, then execute:

```text
macros/FusionLikeUI_SmokeTest_v1.3.0.FCMacro
```

Record its output from Report view.

## Manual test matrix

### Installation and recovery

- **I-01** Fresh install into a clean FreeCAD user profile.
- **I-02** Upgrade directly from v1.0, v1.1, and v1.2 where available.
- **I-03** Rebuild the profile twice; confirm no duplicate toolbars.
- **I-04** Restore original interface, re-enable, then uninstall.
- **I-05** Restart FreeCAD and confirm automatic startup.

### Sketch context

- **S-01** Enter Sketch from Part Design; confirm contextual ribbon appears.
- **S-02** Leave Sketch; confirm Design ribbon returns.
- **S-03** Test line, rectangle, circle, arc, slot, trim, offset, dimension, and construction commands.
- **S-04** Open Sketch immediately after workbench activation; confirm delayed command registration triggers a rebuild.

### Projection

- **P-01** Project a same-Body earlier edge and Pad/Pocket the result.
- **P-02** Project an entire planar face boundary.
- **P-03** Project a whole earlier Sketch.
- **P-04** Project imported STEP geometry through a binder.
- **P-05** Project across Bodies.
- **P-06** Confirm later-feature and circular-reference attempts are rejected.
- **P-07** Change the source dimensions and confirm linked projection updates.

### Hole and Thread

- **H-01** Native plain, counterbore, and countersink holes.
- **H-02** Cosmetic and modeled ISO metric threads.
- **H-03** Left-hand and partial-depth thread.
- **T-01** External independent thread on a cylinder.
- **T-02** Internal independent thread where supported by selected face geometry.
- **T-03** Edit an existing independent Thread with Shift+T.
- **T-04** Save, close, reopen, and recompute.

### Drawing

- **D-01** Insert Model View from a Body and add projected views.
- **D-02** Dimension visible linear, circular, and angular geometry.
- **D-03** Confirm Active View Snapshot is identified as raster.
- **D-04** Insert an Assembly as a source.
- **D-05** Create section/detail views and hatching.
- **D-06** Create a thread callout.
- **D-07** Export PDF, SVG, and DXF.

### Assembly

- **A-01** Add Selected from same document.
- **A-02** Add a component from a saved external document.
- **A-03** Copy, paste with offset, paste in place, and duplicate.
- **A-04** Ground a component and create fixed/revolute/cylindrical/slider/ball joints.
- **A-05** Deliberately select two connectors from the same component; verify diagnostic.
- **A-06** Deliberately create a redundant or conflicting joint; verify decoded result.
- **A-07** Test broken linked subelements after changing source topology.
- **A-08** Create exploded view, BOM, and simulation where applicable.

## Recommended test environments

Report the exact environment rather than assuming equivalence:

- FreeCAD version and build hash
- Windows, macOS, or Linux distribution
- Qt/PySide generation if known
- Open CASCADE version if shown by About FreeCAD
- graphics backend/driver for display-specific failures

## Bug report minimum

A useful report includes:

1. test ID or exact workflow
2. minimal `.FCStd` file when shareable
3. starting selection and active workbench
4. expected result
5. actual result
6. all `[Fusion-like UI]` messages and traceback
7. whether the problem persists after restart and profile rebuild

Remove confidential geometry before uploading a document.
