# GHS Refinement V2: complete bays and restored floor slots

`rack_spacing.json` is the integration artifact. It preserves CAD right-handed XY metres: local rack X is depth, local Y is span. Use the existing registry's `rotation_deg = CAD rotation_deg + 90` convention for rack meshes; the layout file itself retains the CAD angle.

- `racks`: all 1629 complete physical bays, including 58 pass bays. The 70 original column-cut bays replace 80 split instances. `replaces_instance_ids` accounts for every former rack exactly once; `parent_cad_id`, `parent_ids`, source handles, CAD type and mapping key remain explicit.
- `groundcargo`: all 7530 original CAD floor slots, including all 122 formerly blocked slots. Original dimensions are retained. `was_blocked` distinguishes restored slots, and `displacement_m` is relative to the original CAD physical centre.
- `proposed_groundcargo`: 1166 changed entries, comprising 1044 moved existing slots and 122 restored slots. For existing UE instances, add the displacement to their registered position so the existing mesh-pivot correction and scale remain intact. For restored slots, reuse the correction and scale of the same `presentation_variant`.
- `row_changes`, `transverse_gaps`, and `ground_block_changes` document movements and clearances.

Rack rows move only in X, at most 0.964 m. The minimum longitudinal rack aisle is 2.0002 m; back-to-back clearance is at least 0.3048 m. Pass bay widths and Y positions remain unchanged; the smallest source-model pass clear span is 3.4652 m.

Floor columns move only in X, at most 0.754 m. All 166 original block boundaries remain protected: every load stays inside its original block rectangle, so no inter-block aisle is narrowed. The narrowest floor-block aisle remains 1.6764 m. Internal side gaps may reduce to 0.0202 m; these packing gaps are not circulation aisles.

The geometry checks use full loaded rack envelopes (depth at least 1.2192 m), full floor-pallet envelopes, and each actual column base expanded by 100 mm per side. All rack/rack, rack/floor, floor/floor, column and loading-door combinations have zero envelope intersections. All loaded envelopes remain within the CAD building polygon. The audit is conservative in XY; UE world bounds should additionally be verified after import.

Files:

- `rack_spacing_validation.json`: independent artifact-read audit, passed with 0 failures.
- `rack_spacing_before_after.png`: verified before/after closeups of rack and floor restoration.
- `Scripts/ghs/prepare_rack_spacing_v2.py`: deterministic planner, original files read-only.
- `Scripts/ghs/audit_rack_spacing_v2.py`: independent validation of the final artifact.
- `Scripts/ghs/test_rack_spacing_v2.py`: 4 tests for forbidden motion intervals and constrained row placement.
- `Scripts/ghs/render_rack_spacing_v2.py`: reproducible comparison drawing.

The plan records source SHA256 values including the pre-integration registry. That source-integrity check is expected to change after the root integration updates the registry; the pre-integration audit report remains the baseline evidence.
