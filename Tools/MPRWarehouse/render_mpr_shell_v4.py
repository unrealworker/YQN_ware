"""Render only the V4 main shell with the frozen overview camera, source read-only."""
import bpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v4/architecture'
sys.path.insert(0,str(Path(__file__).parent))
import compose_mpr_reference_v4 as composition
bpy.ops.wm.open_mainfile(filepath=str(OUT/'mpr_reference_shell.blend'))
composition.configure();scene=bpy.context.scene;scene.render.film_transparent=True
scene.render.image_settings.color_mode='RGBA';scene.render.filepath=str(OUT/'preview_reference_camera.png')
bpy.ops.render.render(write_still=True)
print('MPR4_SHELL_REFERENCE_RENDERED')
