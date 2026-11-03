"""Inspect the completed surroundings from all four sides in the game viewport."""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_reference_runtime_views as capture
capture.OUT=capture.ROOT/'Saved/MPR/road_v5/outside_views';capture.OUT.mkdir(parents=True,exist_ok=True)
capture.VIEWS=[
 ('14-complete-context',[80,10,0],180000,-90,-90,False),
 ('15-northwest-context',[-330,310,0],62000,-58,-75,False),
 ('16-southwest-context',[-345,-185,0],60000,-57,-115,False),
 ('17-northeast-context',[570,270,0],62000,-60,70,False),
 ('18-southeast-context',[550,-245,0],62000,-58,120,False),
]
original=capture.set_view
def set_view():
    c=capture.base.camera.get_component_by_class(u.CameraComponent)
    c.set_editor_property('projection_mode',u.CameraProjectionMode.ORTHOGRAPHIC if capture.index==0 else u.CameraProjectionMode.PERSPECTIVE)
    if capture.index==0:c.set_editor_property('ortho_width',165000.);c.set_editor_property('auto_calculate_ortho_planes',True)
    original()
capture.set_view=set_view
