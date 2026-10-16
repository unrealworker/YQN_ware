"""Reload optimized lighting and run the entire geometry/FX/material regression chain.
Read-only in Unreal: does not save levels or modify actors. Historical reports remain intact.
"""
import json,math,sys,traceback
from datetime import datetime,timezone
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import verify_ue_scene as common
import verify_clearance_scene as clearance
import verify_column_outlines as column
REPORT_PATH=ROOT/'Saved/GHS_LightingVerification.json'
CUBEMAP='/Engine/EngineResources/GrayLightTextureCube.GrayLightTextureCube'

def prop(o,k):return o.get_editor_property(k)
def close(value,expected,context,tolerance=1e-5):
 assert math.isfinite(float(value)) and abs(float(value)-expected)<=tolerance,(context,value,expected)

def main(report):
 build=common.read_json(ROOT/'Saved/GHS_BuildReport.json')
 applied=common.read_json(ROOT/'Saved/GHS_LightingApplied.json')
 assert build.get('lighting_optimized') and applied['success']
 assert build['actor_count']==225
 registry_path=ROOT/'SourceAssets/GHS/ue_scene_registry.json'
 before_registry=clearance.sha(registry_path)
 backup=Path(applied['backup'])/'ue_scene_registry.json'
 assert backup.is_file(), 'Lighting backup must preserve pre-lighting geometry registry'
 assert common.read_json(backup)==common.read_json(registry_path),'Lighting changed geometry registry'
 history_names=['GHS_Verification.json','GHS_ClearanceVerification.json','GHS_JoinedWallsVerification.json','GHS_ColumnOutlinesVerification.json']
 histories={name:clearance.sha(ROOT/'Saved'/name) for name in history_names}
 # Existing applied files retain their original historical actor counts.
 column.main(report)
 report['success']=False
 assert (report['actor_count'],report['hism_group_count'],report['instanced_count'])==(225,16,14116)
 actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
 labels={a.get_actor_label():a for a in actors}
 directionals=[a for a in actors if isinstance(a,unreal.DirectionalLight)]
 skies=[a for a in actors if isinstance(a,unreal.SkyLight)]
 local=[a for a in actors if isinstance(a,(unreal.RectLight,unreal.PointLight,unreal.SpotLight))]
 assert not local, 'Local lights remain: '+str([a.get_actor_label() for a in local])
 assert len(directionals)==len(skies)==1
 assert directionals[0].get_actor_label()=='GHS_CoolOverheadKey'
 assert skies[0].get_actor_label()=='GHS_UniformAmbient'
 dc=directionals[0].get_component_by_class(unreal.DirectionalLightComponent)
 sc=skies[0].get_component_by_class(unreal.SkyLightComponent)
 assert not prop(dc,'cast_shadows') and not prop(sc,'cast_shadows')
 close(prop(dc,'intensity'),.22,'Directional intensity')
 assert prop(sc,'mobility')==unreal.ComponentMobility.MOVABLE
 assert prop(sc,'source_type')==unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP
 assert not prop(sc,'real_time_capture')
 assert prop(sc,'cubemap') and prop(sc,'cubemap').get_path_name()==CUBEMAP
 assert not prop(sc,'lower_hemisphere_is_black')
 target_intensity=float(applied['settings']['skylight']['intensity'])
 close(prop(sc,'intensity'),target_intensity,'Skylight approved intensity')
 assert target_intensity>0 and math.isfinite(target_intensity)
 pp=labels['GHS_ApprovedDigitalTwinLook'];assert isinstance(pp,unreal.PostProcessVolume) and prop(pp,'unbound')
 settings=prop(pp,'settings')
 expected={'vignette_intensity':0.,'ambient_occlusion_intensity':.2,'ambient_occlusion_radius':40.,'ambient_occlusion_quality':25.,'auto_exposure_min_brightness':0.,'auto_exposure_max_brightness':0.,'auto_exposure_bias':0.}
 checks={}
 for k,value in expected.items():
  assert prop(settings,'override_'+k), 'Missing override '+k
  close(prop(settings,k),value,k);checks[k]=float(prop(settings,k))
 for k,expected_enum in [('dynamic_global_illumination_method',unreal.DynamicGlobalIlluminationMethod.NONE),('reflection_method',unreal.ReflectionMethod.NONE)]:
  assert prop(settings,'override_'+k),'Missing override '+k
  assert prop(settings,k)==expected_enum,(k,str(prop(settings,k)))
  checks[k]=str(prop(settings,k))
 assert clearance.sha(registry_path)==before_registry
 assert all(clearance.sha(ROOT/'Saved'/n)==digest for n,digest in histories.items()),'Historical verification report modified'
 report.update(success=True,lighting_optimized=True,geometry_registry_unchanged=True,historical_verification_reports_unchanged=True,
  light_counts={'directional':1,'skylight':1,'rect':0,'point':0,'spot':0},
  directional={'intensity':float(prop(dc,'intensity')),'cast_shadows':False},
  skylight={'intensity':float(prop(sc,'intensity')),'cubemap':CUBEMAP,'real_time_capture':False,'cast_shadows':False,'mobility':'MOVABLE','cubemap_resolution':int(prop(sc,'cubemap_resolution'))},
  post_process=checks,performance_scope='No GPU timing claim. Verified removal of 24 local rect lights and disabled GI/reflection overrides; actual render cost requires profiling.',
  historical_column_applied_actor_count=common.read_json(ROOT/'Saved/GHS_ColumnOutlinesApplied.json')['actor_count'])

def run():
 report={'success':False,'map':common.MAP,'verification_mode':'Fresh UE reload; no actor mutation or level save','utc':datetime.now(timezone.utc).isoformat(),
         'groups':[],'individuals':[],'effects':[],'meshes':[]}
 try:main(report)
 except Exception:
  report['error']=traceback.format_exc();raise
 finally:REPORT_PATH.write_text(json.dumps(report,indent=2),encoding='utf8')
 unreal.log('GHS_LIGHTING_VERIFIED '+json.dumps({k:report[k] for k in ['success','actor_count','hism_group_count','instanced_count','light_counts']}))
if __name__=='__main__':run()
