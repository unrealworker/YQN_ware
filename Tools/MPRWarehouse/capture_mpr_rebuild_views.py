"""Actual native game frames of the independent rebuild; no asset writes."""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as base
base.MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
base.MAP_FILE=base.ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
base.result['map']=base.MAP
import capture_mpr_reference_runtime_views as capture
capture.OUT=base.ROOT/'Saved/MPR/rebuild_20261104/runtime_views'
capture.OUT.mkdir(parents=True,exist_ok=True)
capture.VIEWS=[
 ('01-main-aerial',[0,0,0],90000,-52,-90,False),
 ('02-full-surroundings',[-80,160,0],170000,-63,-90,False),
 ('03-north-context',[-100,480,0],85000,-58,-85,False),
 ('04-west-residential',[-460,80,0],65000,-55,-95,False),
 ('05-south-surroundings',[-50,-320,0],65000,-55,-100,False),
 ('06-east-rail-yard',[330,40,0],60000,-50,-65,False),
 ('07-west-houses-close',[-410,70,0],20000,-38,-130,False),
 ('08-dock-vehicles',[0,-98,0],20000,-32,-90,False),
 ('09-north-warehouse',[0,205,0],45000,-45,-100,False),
 ('10-interior-preserved',[0,0,4],49000,-60,-90,True),
 ('11-main-reverse',[0,0,8],65000,-45,90,False),
 ('12-south-rail-crossing',[-100,-465,0],18000,-40,-65,False),
 ('13-northeast-edge',[400,470,0],50000,-55,-80,False),
 ('14-west-edge',[-680,-50,0],50000,-65,-110,False),
 ('15-lumen-aerial',[0,0,0],90000,-52,-90,False),
 ('16-lumen-docks',[0,-98,0],20000,-32,-90,False),
 ('17-solar-overview',[50,0,14],45000,-66,-90,False),
 ('18-solar-close',[58,38,14],10000,-42,-105,False),
 ('19-solar-reverse',[50,0,14],45000,-58,90,False),
]
_set_view=capture.set_view
def set_view():
    _set_view()
    base.console('r.Lumen.Visualize '+('1' if capture.VIEWS[capture.index][0].split('-')[1]=='lumen' else '0'))
    if capture.index==0:
        settings={}
        for actor in u.GameplayStatics.get_all_actors_of_class(base.world,u.PostProcessVolume):
            s=actor.get_editor_property('settings')
            settings[actor.get_name()]=dict(unbound=actor.get_editor_property('unbound'),**{
                k:str(s.get_editor_property(k)) for k in ('auto_exposure_method','auto_exposure_min_brightness',
                'auto_exposure_max_brightness','auto_exposure_bias','bloom_intensity','color_grading_intensity',
                'local_exposure_highlight_contrast_scale','local_exposure_shadow_contrast_scale',
                'local_exposure_detail_strength','local_exposure_middle_grey_bias','dynamic_global_illumination_method',
                'reflection_method','lumen_scene_detail','lumen_scene_view_distance','lumen_max_trace_distance')})
        capture.report['runtime_postprocess']=settings
        capture.report['renderer_cvars']={k:u.SystemLibrary.get_console_variable_string_value(k)
            for k in ('r.Shadow.Virtual.Enable','r.RayTracing','r.Lumen.HardwareRayTracing',
                      'r.LumenScene.FarField','r.LumenScene.GlobalSDF.ClipmapExtent','r.GenerateMeshDistanceFields')}
        capture.report['fog_actor_count']=len(u.GameplayStatics.get_all_actors_of_class(base.world,u.ExponentialHeightFog))
capture.set_view=set_view
