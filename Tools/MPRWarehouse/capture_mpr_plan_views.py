"""Actual UE game views for the new plan/straight-building acceptance.

Run isolated with -game -RenderOffscreen -ResX=1920 -ResY=1080. The overview
uses a true orthographic camera, with natural metric proportions. No image
warping or misleading match to the independently scaled raster is performed.
"""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_reference_runtime_views as capture

capture.OUT=capture.ROOT/'Saved/MPR/road_v5/runtime_views'
capture.OUT.mkdir(parents=True,exist_ok=True)
capture.VIEWS=[
    ('09-plan-overview',[82,25,0],150000,-90,-90,False),
    ('10-houses-close',[-306,166,3],15000,-42,-55,False),
    ('11-houses-reverse',[-306,166,3],14500,-35,125,False),
    ('12-neighbor-docks',[-50,128,5],18500,-22,-90,False),
    ('13-east-context',[450,-228,3],40000,-47,-50,False),
]
original=capture.set_view
def set_view():
    component=capture.base.camera.get_component_by_class(u.CameraComponent)
    component.set_editor_property('projection_mode',u.CameraProjectionMode.ORTHOGRAPHIC if capture.index==0 else u.CameraProjectionMode.PERSPECTIVE)
    if capture.index==0:
        component.set_editor_property('ortho_width',120000.)
        component.set_editor_property('auto_calculate_ortho_planes',True)
    original()
capture.set_view=set_view
