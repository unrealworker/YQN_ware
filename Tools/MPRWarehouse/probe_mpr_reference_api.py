"""Read-only check of UE 5.8 reflection used by the exterior importer."""
import unreal as u,json
from pathlib import Path
root=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()))
settings=u.MeshNaniteSettings();settings.enabled=True;settings.shape_preservation=u.NaniteShapePreservation.PRESERVE_AREA
overrides=u.MaterialInstanceBasePropertyOverrides();overrides.set_editor_property('override_two_sided',True);overrides.set_editor_property('two_sided',True)
matrix=u.Matrix(x_plane=u.Plane(1,0,0,0),y_plane=u.Plane(0,1,0,0),z_plane=u.Plane(0,0,0,1),w_plane=u.Plane(0,0,10,0))
rotation=u.MathLibrary.make_rotation_from_axes(u.Vector(1,0,0),u.Vector(0,1,0),u.Vector(0,0,1))
report=dict(success=True,nanite_preservation=str(settings.shape_preservation),projection=str(matrix),rotation=str(rotation),capture_source=str(u.SceneCaptureSource.SCS_FINAL_COLOR_LDR),target_format=str(u.TextureRenderTargetFormat.RTF_RGBA8))
(root/'Saved/MPR/reference_v4_api_probe.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('MPR_REFERENCE_API_PROBE_OK')
