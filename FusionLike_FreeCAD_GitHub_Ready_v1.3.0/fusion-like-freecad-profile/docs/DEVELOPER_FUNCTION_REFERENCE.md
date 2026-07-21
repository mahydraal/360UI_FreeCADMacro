# Developer function reference

> Generated from `src/fusion_like_ui_runtime.py` v1.3.0. Line numbers refer to this repository version. Private names are implementation details and may change between releases.

## Module-level constants and responsibilities

- `PROFILE_VERSION`: installed runtime version.
- `PREF_PATH`, `VIEW_PREF_PATH`, `SKETCHER_PREF_PATH`: FreeCAD preference groups.
- `ASSEMBLY_CLIPBOARD_MIME`: custom clipboard payload type.
- `ASSEMBLY_SOLVER_CODES`: decoded native solver results and user guidance.
- thread standard tables and labels: independent/native thread dialog support.

## Module functions

| Function | Line | Purpose |
|---|---:|---|
| `_console(message, warning=False)` | 55 | Write a prefixed message or warning to FreeCAD Report view. |
| `_strip_action_text(text)` | 63 | Internal helper for strip action text. |
| `_menu_exec(menu, pos)` | 67 | Internal helper for menu exec. |
| `_active_workbench_name()` | 73 | Resolve active workbench name. |
| `_set_item_user_data(item, value)` | 82 | Set item user data. |
| `_item_user_data(item)` | 86 | Internal helper for item user data. |
| `_freecad_version_tuple()` | 90 | Return a numeric (major, minor, patch) tuple without trusting suffixes. |
| `_element_leaf(sub_name)` | 105 | Extract the final FaceN/EdgeN/VertexN token from a subelement path. |
| `_dialog_exec(dialog)` | 154 | Internal helper for dialog exec. |
| `_quantity_value(value, default=0.0)` | 160 | Internal helper for quantity value. |
| `_enum_options(obj, property_name)` | 170 | Internal helper for enum options. |
| `_set_enum_value(obj, property_name, value)` | 177 | Set enum value. |
| `_is_derived(obj, type_name)` | 188 | Internal helper for is derived. |
| `_global_body_for_object(obj)` | 197 | Internal helper for global body for object. |
| `_active_partdesign_body(doc=None, preferred=None)` | 216 | Resolve the most relevant active Part Design Body from preferred object, GUI state, selection, or document. |
| `_active_edited_sketch_global()` | 243 | Return the Sketch currently in GUI edit mode. |
| `_normalized_vector(value)` | 257 | Internal helper for normalized vector. |
| `_shape_element(source, sub_name)` | 265 | Internal helper for shape element. |
| `_face_sample_points(face)` | 281 | Internal helper for face sample points. |
| `_analyze_cylindrical_face(source, sub_name)` | 301 | Analyze a selected face and return cylindrical axis/radius/extent information. |
| `_thread_profile_depth(pitch, standard)` | 351 | Internal helper for thread profile depth. |
| `_thread_profile_wire(pitch, major_radius, standard, radial_clearance=0.0)` | 358 | Internal helper for thread profile wire. |
| `_make_thread_cutter(analysis, pitch, standard, length, offset, start_side, direction, mode, clearance)` | 396 | Build helical thread-cutting geometry from thread specification and cylindrical-face analysis. |
| `_thread_callout(standard, designation, thread_class, pitch, direction)` | 455 | Format a human-readable thread designation/callout. |
| `register_commands()` | 5518 | Register the custom Hole and independent Thread commands with FreeCAD. |
| `install_menu()` | 5533 | Install a persistent control menu, even when the profile is disabled. |
| `start(force=False)` | 5605 | Create/apply the singleton profile when enabled. |
| `enable()` | 5617 | Enable the profile preference and force startup. |
| `restore()` | 5622 | Restore original UI state and reinstall the control menu. |
| `rebuild()` | 5630 | Rebuild the active profile UI. |
| `show_palette()` | 5638 | Show palette. |
| `toggle_timeline()` | 5645 | Toggle timeline. |
| `open_fusion_hole()` | 5652 | Open fusion hole. |
| `open_fusion_thread()` | 5659 | Open fusion thread. |
| `insert_dimensionable_model_view()` | 5667 | Insert dimensionable model view. |
| `show_drawing_workflow_help()` | 5674 | Show drawing workflow help. |
| `copy_assembly_components()` | 5681 | Copy assembly components. |
| `paste_assembly_components()` | 5688 | Paste assembly components. |
| `add_selected_to_assembly()` | 5695 | Add selected to assembly. |
| `duplicate_assembly_components()` | 5702 | Duplicate assembly components. |
| `show_assembly_mate_diagnostics()` | 5709 | Show assembly mate diagnostics. |
| `solve_assembly_with_diagnostics()` | 5716 | Internal helper for solve assembly with diagnostics. |
| `project_profile()` | 5723 | Project profile. |
| `project_reference()` | 5730 | Project reference. |
| `project_intersection()` | 5737 | Project intersection. |
| `end_projection()` | 5744 | Internal helper for end projection. |

## Classes

### `ProjectionSelectionObserver`

Forward FreeCAD selection events to an active projection session.

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self, profile)` | 114 | Initialize ProjectionSelectionObserver state and UI/data handles. |
| `addSelection(self, document, object_name, element, position)` | 117 | Internal helper for addSelection. |

### `NativeThreadCatalog`

Use a temporary native Hole object as FreeCAD's authoritative thread table.

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self, document)` | 479 | Initialize NativeThreadCatalog state and UI/data handles. |
| `close(self)` | 492 | Internal helper for close. |
| `standards(self, standalone=False)` | 501 | Internal helper for standards. |
| `set_standard(self, standard)` | 507 | Internal helper for set standard. |
| `sizes(self, standard=None)` | 511 | Internal helper for sizes. |
| `classes(self, standard=None, designation=None)` | 516 | Internal helper for classes. |
| `spec(self, standard, designation, thread_class=None)` | 523 | Internal helper for spec. |
| `closest_designation(self, standard, surface_diameter, internal=False)` | 536 | Return the native size whose expected cylinder best matches the selection. |

### `HoleThreadDialog`

Fusion-style front end over FreeCAD's native threaded Hole feature.

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self, hole, is_new=False, parent=None)` | 559 | Initialize HoleThreadDialog state and UI/data handles. |
| `_set_combo(self, combo, values, current=None, label_map=None)` | 690 | Set combo. |
| `_load_from_hole(self)` | 702 | Internal helper for load from hole. |
| `_connect_controls(self)` | 765 | Internal helper for connect controls. |
| `_current_data(self, combo)` | 802 | Internal helper for current data. |
| `_refresh_sizes(self, preferred=None)` | 806 | Refresh sizes. |
| `_refresh_classes(self, preferred=None)` | 819 | Refresh classes. |
| `_refresh_head_types(self, preferred=None)` | 832 | Refresh head types. |
| `_standard_changed(self, *args)` | 839 | Internal helper for standard changed. |
| `_size_changed(self, *args)` | 844 | Internal helper for size changed. |
| `_control_changed(self, *args)` | 849 | Internal helper for control changed. |
| `_update_enabled(self)` | 855 | Internal helper for update enabled. |
| `_update_specification(self)` | 885 | Internal helper for update specification. |
| `_apply_to_hole(self)` | 910 | Internal helper for apply to hole. |
| `_schedule_preview(self, *args)` | 949 | Internal helper for schedule preview. |
| `_preview_now(self)` | 954 | Internal helper for preview now. |
| `accept(self)` | 961 | Validate current dialog/task state and commit the operation. |

### `StandaloneThreadDialog`

Fusion-like independent Thread dialog for selected cylindrical faces.

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self, catalog, analyses, existing=None, parent=None)` | 974 | Initialize StandaloneThreadDialog state and UI/data handles. |
| `_current_data(self, combo)` | 1072 | Internal helper for current data. |
| `_set_combo_values(self, combo, values, preferred=None)` | 1076 | Set combo values. |
| `_load_initial(self)` | 1087 | Internal helper for load initial. |
| `_standard_changed(self, *args)` | 1130 | Internal helper for standard changed. |
| `_size_changed(self, *args)` | 1144 | Internal helper for size changed. |
| `_refresh_sizes(self, preferred=None)` | 1149 | Refresh sizes. |
| `_refresh_classes(self, preferred=None)` | 1153 | Refresh classes. |
| `_spec(self)` | 1159 | Internal helper for spec. |
| `_update_callout(self, *args)` | 1166 | Internal helper for update callout. |
| `_extent_changed(self, *args)` | 1188 | Internal helper for extent changed. |
| `_modeled_changed(self, *args)` | 1200 | Internal helper for modeled changed. |
| `settings(self)` | 1211 | Internal helper for settings. |
| `accept(self)` | 1239 | Validate current dialog/task state and commit the operation. |

### `FusionThreadFeatureProxy`

Persistent Part Design subtractive thread feature.

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self, obj=None)` | 1255 | Initialize FusionThreadFeatureProxy state and UI/data handles. |
| `attach(self, obj)` | 1259 | Internal helper for attach. |
| `dumps(self)` | 1334 | Internal helper for dumps. |
| `loads(self, state)` | 1337 | Internal helper for loads. |
| `onDocumentRestored(self, obj)` | 1341 | Internal helper for onDocumentRestored. |
| `execute(self, fp)` | 1344 | Internal helper for execute. |
| `_execute_feature(self, fp)` | 1354 | Internal helper for execute feature. |

### `FusionHoleCommand`

Internal helper for FusionHoleCommand.

| Method | Line | Purpose |
|---|---:|---|
| `GetResources(self)` | 1414 | Return FreeCAD command label, icon, shortcut, and tooltip metadata. |
| `IsActive(self)` | 1422 | Determine whether the command is currently available. |
| `Activated(self)` | 1425 | Execute the command in the current FreeCAD context. |

### `FusionThreadCommand`

Internal helper for FusionThreadCommand.

| Method | Line | Purpose |
|---|---:|---|
| `GetResources(self)` | 1430 | Return FreeCAD command label, icon, shortcut, and tooltip metadata. |
| `IsActive(self)` | 1438 | Determine whether the command is currently available. |
| `Activated(self)` | 1441 | Execute the command in the current FreeCAD context. |

### `DrawingSourceDialog`

Choose a TechDraw page and model sources for a dimensionable vector view.

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self, document, pages, candidates, selected_names=None, selected_page=None, parent=None)` | 1448 | Initialize DrawingSourceDialog state and UI/data handles. |
| `_accept_checked(self)` | 1524 | Internal helper for accept checked. |
| `selected_source_names(self)` | 1534 | Internal helper for selected source names. |
| `selected_page_name(self)` | 1537 | Internal helper for selected page name. |

### `CommandPalette`

Search and trigger any registered FreeCAD QAction.

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self, profile)` | 1544 | Initialize CommandPalette state and UI/data handles. |
| `_collect(self)` | 1577 | Internal helper for collect. |
| `open_palette(self)` | 1603 | Open palette. |
| `_filter(self, text)` | 1617 | Internal helper for filter. |
| `_run_current(self)` | 1633 | Run current. |
| `_run_item(self, item)` | 1638 | Run item. |
| `keyPressEvent(self, event)` | 1648 | Internal helper for keyPressEvent. |

## `FusionProfile`

Owns the reversible UI profile and its runtime helpers.

### Lifecycle and reversible state

| Method | Line | Purpose |
|---|---:|---|
| `__init__(self)` | 1684 | Initialize main-window handles, preferences, timers, clipboard state, projection state, and runtime widget references. |
| `_capture_original_state(self)` | 1730 | Persist the pre-profile Qt layout, workbench, navigation, and related preferences once. |
| `apply(self)` | 1762 | Enable preferences, configure navigation, activate Part Design when available, and schedule UI construction. |
| `_finish_apply(self)` | 1785 | Remove stale runtime UI, build current toolbars/timeline, install hooks, and start context refresh. |
| `restore(self)` | 1811 | Disable the profile, remove hooks/widgets/patches, and restore saved FreeCAD state. |
| `rebuild(self)` | 1861 | Rebuild the active profile UI. |

### Navigation, docks, toolbars, workspaces, and context routing

| Method | Line | Purpose |
|---|---:|---|
| `_set_fusion_navigation(self)` | 1869 | Set fusion navigation. |
| `_arrange_docks(self)` | 1877 | Internal helper for arrange docks. |
| `_remove_runtime_widgets(self)` | 1915 | Remove runtime widgets. |
| `_make_toolbar(self, object_name, title, style=None)` | 1940 | Internal helper for make toolbar. |
| `_section_label(self, toolbar, text)` | 1952 | Internal helper for section label. |
| `_find_action(self, command_id)` | 1961 | Find action. |
| `_add_command(self, toolbar, command_id)` | 1970 | Internal helper for add command. |
| `_add_first_command(self, toolbar, command_ids)` | 1977 | Add the first registered command from a compatibility fallback list. |
| `_proxy_action(self, parent, label, original)` | 1985 | Internal helper for proxy action. |
| `_add_dropdown(self, toolbar, label, command_rows, icon_command=None)` | 1992 | Internal helper for add dropdown. |
| `_callback_action(self, parent, label, callback, object_name, tooltip='', icon=None)` | 2027 | Internal helper for callback action. |
| `_add_callback_command(self, toolbar, label, callback, object_name, tooltip='', icon_command=None)` | 2036 | Internal helper for add callback command. |
| `_add_callback_dropdown(self, toolbar, label, rows, icon_command=None)` | 2051 | Add a Fusion-style dropdown whose rows call Python workflow helpers. |
| `_clear_profile_toolbars(self)` | 2074 | Internal helper for clear profile toolbars. |
| `_build_quick_toolbar(self)` | 2082 | Build quick toolbar. |
| `_build_design_toolbars(self)` | 2104 | Build design toolbars. |
| `_build_sketch_toolbars(self)` | 2240 | Build the contextual Sketch Finish/Create/Project/Modify/Constrain/Inspect ribbons. |
| `_build_assembly_toolbars(self)` | 2353 | Build assembly toolbars. |
| `_build_drawing_toolbars(self)` | 2522 | Build drawing toolbars. |
| `_build_toolbars(self)` | 2684 | Build toolbars. |
| `_populate_workspaces(self)` | 2709 | Internal helper for populate workspaces. |
| `_switch_workspace(self, index)` | 2727 | Internal helper for switch workspace. |
| `_post_workspace_switch(self)` | 2739 | Internal helper for post workspace switch. |
| `_hide_native_toolbars(self)` | 2748 | Internal helper for hide native toolbars. |
| `_ui_context_signature_value(self)` | 2757 | Internal helper for ui context signature value. |
| `_refresh_ui_context_if_needed(self)` | 2784 | Detect context-signature changes and rebuild the ribbon when workspace or Sketch edit state changes. |

### Drawing model-view and dimension workflow

| Method | Line | Purpose |
|---|---:|---|
| `_drawing_candidate_objects(self)` | 2802 | Internal helper for drawing candidate objects. |
| `_show_techdraw_page(self, page)` | 2838 | Show techdraw page. |
| `insert_dimensionable_model_view(self)` | 2854 | Guide source/page selection and launch the native TechDraw model-linked view workflow. |
| `_drawing_dimension_selection_report(self)` | 2928 | Internal helper for drawing dimension selection report. |
| `start_drawing_dimension(self, command_id)` | 2981 | Validate TechDraw selection and run the requested native dimension command. |
| `show_drawing_workflow_help(self)` | 2996 | Show drawing workflow help. |

### Assembly clipboard, joint diagnostics, and solver reporting

| Method | Line | Purpose |
|---|---:|---|
| `_joint_task_failure_report(self, task, heading, exception=None, extra=None, modal=False)` | 3011 | Internal helper for joint task failure report. |
| `_install_assembly_task_diagnostics_patch(self)` | 3047 | Wrap the native Assembly joint task with live diagnostic UI and failure reporting. |
| `_remove_assembly_task_diagnostics_patch(self)` | 3169 | Remove assembly task diagnostics patch. |
| `_assembly_utils(self)` | 3194 | Internal helper for assembly utils. |
| `_active_assembly(self)` | 3201 | Resolve active assembly. |
| `_assembly_contains(self, assembly, obj)` | 3217 | Internal helper for assembly contains. |
| `_assembly_selected_components(self, allow_model_sources=True)` | 3233 | Internal helper for assembly selected components. |
| `_placement_to_json(self, placement)` | 3278 | Internal helper for placement to json. |
| `_placement_from_json(self, row)` | 3288 | Internal helper for placement from json. |
| `copy_assembly_components(self)` | 3302 | Serialize selected component sources and placements into the custom clipboard MIME payload. |
| `_read_assembly_clipboard(self)` | 3346 | Internal helper for read assembly clipboard. |
| `_source_offset_distance(self, source)` | 3360 | Internal helper for source offset distance. |
| `paste_assembly_components(self, in_place=False)` | 3367 | Create component link instances from the clipboard, with optional placement offset. |
| `add_selected_to_assembly(self)` | 3490 | One-click insertion of selected model objects at their current placements. |
| `duplicate_assembly_components(self)` | 3496 | Duplicate assembly components. |
| `_assembly_refs_from_selection(self, assembly)` | 3501 | Internal helper for assembly refs from selection. |
| `_joint_reference_info(self, ref)` | 3530 | Internal helper for joint reference info. |
| `_assembly_joint_report(self, joint_type, refs, assembly=None, extra_notes=None)` | 3621 | Analyze selected joint connector references and return compatibility/grounding/loop guidance. |
| `start_guided_joint(self, command_id, joint_type, as_built=False)` | 3728 | Start guided joint. |
| `_refresh_joint_diagnostics_panel(self)` | 3773 | Refresh joint diagnostics panel. |
| `_assembly_joint_inventory_report(self, assembly)` | 3826 | Internal helper for assembly joint inventory report. |
| `_show_text_report(self, title, text)` | 3891 | Show text report. |
| `show_assembly_mate_diagnostics(self)` | 3909 | Show assembly mate diagnostics. |
| `_assembly_solver_result_report(self, assembly, result_code, error=None, joint=None)` | 3937 | Internal helper for assembly solver result report. |
| `_post_joint_accept_diagnostics(self, assembly, joint)` | 3982 | Solve after mate acceptance, decode status, select failed joint, and show a targeted report. |
| `solve_assembly_with_diagnostics(self)` | 4018 | Run the active Assembly solver and always present the decoded status/inventory report. |

### Drawing thread callouts and export

| Method | Line | Purpose |
|---|---:|---|
| `_selected_techdraw_page(self)` | 4049 | Resolve selected techdraw page. |
| `_thread_callout_from_object(self, obj)` | 4066 | Internal helper for thread callout from object. |
| `_selected_thread_source(self)` | 4081 | Resolve selected thread source. |
| `insert_thread_callout(self)` | 4101 | Insert thread callout. |
| `export_active_drawing_pdf(self)` | 4157 | Export active drawing pdf. |

### Parametric timeline and Body Tip control

| Method | Line | Purpose |
|---|---:|---|
| `_build_timeline(self)` | 4190 | Create the bottom feature timeline dock and connect selection/context actions. |
| `_timeline_objects(self)` | 4237 | Internal helper for timeline objects. |
| `_timeline_icon(self, obj)` | 4269 | Internal helper for timeline icon. |
| `_body_for_object(self, obj)` | 4308 | Internal helper for body for object. |
| `_tip_names(self)` | 4318 | Internal helper for tip names. |
| `_timeline_signature_value(self)` | 4330 | Internal helper for timeline signature value. |
| `_refresh_timeline_if_needed(self)` | 4339 | Refresh timeline if needed. |
| `_refresh_timeline(self, force=False)` | 4353 | Refresh timeline. |
| `_timeline_object_from_item(self, item)` | 4381 | Internal helper for timeline object from item. |
| `_timeline_select(self, item)` | 4387 | Internal helper for timeline select. |
| `_timeline_context_menu(self, pos)` | 4394 | Internal helper for timeline context menu. |
| `_set_body_tip(self, body, obj)` | 4422 | Set body tip. |
| `_set_body_tip_to_latest(self, body)` | 4439 | Set body tip to latest. |
| `toggle_timeline(self)` | 4458 | Toggle timeline. |

### Hole and independent Thread workflow

| Method | Line | Purpose |
|---|---:|---|
| `_selected_hole_or_sketch(self)` | 4469 | Resolve selected hole or sketch. |
| `open_fusion_hole(self)` | 4487 | Create or edit a native Hole through the Fusion-like threaded-hole dialog. |
| `show_hole_menu(self)` | 4572 | Show hole menu. |
| `_thread_existing_selection(self)` | 4597 | Internal helper for thread existing selection. |
| `_thread_context_from_selection(self)` | 4611 | Internal helper for thread context from selection. |
| `_apply_thread_settings(self, feature, settings)` | 4685 | Internal helper for apply thread settings. |
| `open_fusion_thread(self)` | 4702 | Create or edit an independent persistent cylindrical Thread feature. |

### Sketch projection and SubShapeBinder workflow

| Method | Line | Purpose |
|---|---:|---|
| `_active_edited_sketch(self)` | 4805 | Resolve active edited sketch. |
| `_projection_warning(self, text)` | 4826 | Internal helper for projection warning. |
| `_projection_requirements(self)` | 4830 | Internal helper for projection requirements. |
| `_projection_selection_rows(self, sketch)` | 4845 | Internal helper for projection selection rows. |
| `_shape_is_null(self, shape)` | 4869 | Internal helper for shape is null. |
| `_object_shape_subnames(self, source)` | 4877 | Expand an object-level selection into its projected boundary elements. |
| `_latest_feature_before_sketch(self, body, sketch)` | 4905 | Internal helper for latest feature before sketch. |
| `_normalize_projection_source(self, source, sub_name, sketch)` | 4919 | Resolve Body-display selections to the actual feature carrying the shape. |
| `_source_depends_on_sketch(self, source, sketch)` | 4933 | Internal helper for source depends on sketch. |
| `_source_precedes_sketch(self, body, source, sketch)` | 4941 | Internal helper for source precedes sketch. |
| `_direct_projection_allowed(self, source, sketch)` | 4951 | Internal helper for direct projection allowed. |
| `_binder_key(self, source, sub_name, sketch)` | 4964 | Internal helper for binder key. |
| `_find_projection_binder(self, body, key)` | 4973 | Find projection binder. |
| `_set_binder_metadata(self, binder, key, source, sub_name, sketch)` | 4983 | Set binder metadata. |
| `_create_or_reuse_projection_binder(self, body, source, sub_name, sketch)` | 5005 | Create or reuse projection binder. |
| `_binder_projection_subnames(self, binder, source, source_sub_name)` | 5046 | Internal helper for binder projection subnames. |
| `_add_external(self, sketch, source_name, sub_name, defining, intersection)` | 5073 | Internal helper for add external. |
| `_project_direct(self, sketch, source, sub_name, defining, intersection)` | 5084 | Internal helper for project direct. |
| `_project_through_binder(self, sketch, source, sub_name, defining, intersection)` | 5092 | Internal helper for project through binder. |
| `_project_rows(self, sketch, rows, defining, intersection)` | 5104 | Project normalized source rows directly or through binders inside a document transaction. |
| `_project_selected_or_start(self, defining, intersection)` | 5172 | Internal helper for project selected or start. |
| `project_profile(self)` | 5182 | Project selected/picked geometry as linked defining sketch profiles. |
| `project_reference(self)` | 5186 | Project selected/picked geometry as linked construction references. |
| `project_intersection(self)` | 5190 | Intersect selected/picked geometry with the active sketch plane. |
| `start_projection_mode(self, defining=True, intersection=False, sketch=None)` | 5194 | Install continuous projection selection observers/callbacks for the active Sketch. |
| `_queue_projection_selection(self, document_name, object_name, sub_name)` | 5234 | Internal helper for queue projection selection. |
| `_projection_mouse_event(self, event_callback)` | 5246 | Pick external faces/edges even when Sketcher suppresses normal selection. |
| `_projection_observer_selection(self, document_name, object_name, sub_name)` | 5276 | Internal helper for projection observer selection. |
| `end_projection_mode(self, silent=False)` | 5309 | Remove projection callbacks/observer and clear session state. |

### Command execution, popups, palette, and shortcuts

| Method | Line | Purpose |
|---|---:|---|
| `start_extrude(self, command_id)` | 5336 | Start extrude. |
| `_finish_sketch_and_run(self, sketch, command_id)` | 5342 | Internal helper for finish sketch and run. |
| `_command_active(self, command_id)` | 5360 | Internal helper for command active. |
| `_run_command(self, command_id)` | 5369 | Run command. |
| `_run_first_active(self, command_ids)` | 5382 | Run first active. |
| `_popup_commands(self, title, rows)` | 5388 | Internal helper for popup commands. |
| `show_extrude_menu(self)` | 5404 | Show extrude menu. |
| `show_press_pull_menu(self)` | 5421 | Show press pull menu. |
| `show_palette(self)` | 5435 | Show palette. |
| `_focus_is_text_input(self)` | 5440 | Internal helper for focus is text input. |
| `eventFilter(self, watched, event)` | 5457 | Handle global context-sensitive shortcuts while protecting text inputs and modal dialogs. |

## Public wrapper functions

The final module functions (`open_fusion_hole`, `project_profile`, `solve_assembly_with_diagnostics`, and similar) lazily create the singleton `FusionProfile` and delegate to the corresponding method. They provide stable call targets for menus and registered FreeCAD commands.
