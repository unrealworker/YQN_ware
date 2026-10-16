"""Reuse approved animated green decals for the twelve Normal-map stackers."""
import hashlib,json,math,shutil,sys,traceback
from pathlib import Path
from datetime import datetime
import unreal
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot,transform,xyz
from normal_fx_style import connected_nodes
MAP='/Game/Maps/GHS_CAD_NormalWarehouse';FILE='Content/Maps/GHS_CAD_NormalWarehouse.umap'
REPORT=ROOT/'Saved/GHS_NormalStackerFX.json';VERIFY=ROOT/'Saved/GHS_NormalStackerFXVerification.json'
FX='/Game/GHSNormalWarehouse/FX/';FOLDER='GHS_Normal/Vehicles/FloorStackers/Effects'
A=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);E=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
L=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);LIB=unreal.EditorAssetLibrary;ML=unreal.MaterialEditingLibrary

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def content():return {p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}
def labels():return {a.get_actor_label():a for a in A.get_all_level_actors()}
def near(a,b,tol=.001):assert len(a)==len(b) and max(abs(x-y) for x,y in zip(a,b))<tol,(a,b)
def basis(t):
 return [xyz(t.translation),xyz(t.scale3d)]+[xyz(unreal.MathLibrary.transform_direction(t,unreal.Vector(*v))) for v in ((1,0,0),(0,1,0),(0,0,1))]
def records():
 return [dict(actor=f'FX_GHN_FloorStacker_{i:02d}_{kind}',parent=f'GHN_FloorStacker_{i:02d}',kind=kind,
  radius_cm=155 if kind=='Diffusion' else 300,material=FX+f'MI_GHN_FX_GHS_AGV_{29+(i-1)%6:02d}_{kind}')
  for i in range(1,13) for kind in ('Diffusion','Radar')]

def check_material(row):
 mi=LIB.load_asset(row['material']);assert isinstance(mi,unreal.MaterialInstanceConstant)
 parent=mi.get_editor_property('parent');assert parent.get_path_name().split('.')[0]==FX+'M_GHN_FX_'+row['kind']
 assert parent.get_editor_property('material_domain')==unreal.MaterialDomain.MD_DEFERRED_DECAL
 nodes=connected_nodes(parent)
 assert any(isinstance(n,unreal.MaterialExpressionTime) for n in nodes)
 custom=[n for n in nodes if isinstance(n,unreal.MaterialExpressionCustom)];assert len(custom)==1
 assert 'T + Phase' in custom[0].get_editor_property('code')
 speed=float(ML.get_material_instance_scalar_parameter_value(mi,'Speed'));assert speed>0
 tint=ML.get_material_instance_vector_parameter_value(mi,'Tint');near([tint.r,tint.g,tint.b],[.04,.8,.30],1e-5)
 near([ML.get_material_instance_scalar_parameter_value(mi,n) for n in ('OpacityScale','EmissionScale')],[1.8,.12],1e-5)
 return dict(material=row['material'],speed=speed,phase=ML.get_material_instance_scalar_parameter_value(mi,'Phase'),
  time_connected=True,tint=[tint.r,tint.g,tint.b],shader_sha256=hashlib.sha256(custom[0].get_editor_property('code').encode()).hexdigest())

def validate(before,rows,by):
 assert set(by)==set(before)|{r['actor'] for r in rows}
 state=snapshot(by)
 for n,v in before.items():assert state[n]==v,('Existing object changed',n)
 mats=[]
 for r in rows:
  a=by[r['actor']];p=by[r['parent']];c=a.get_component_by_class(unreal.DecalComponent)
  assert isinstance(a,unreal.DecalActor) and c and a.get_attach_parent_actor()==p
  assert str(a.get_folder_path())==FOLDER
  assert not a.get_components_by_class(unreal.StaticMeshComponent)
  assert c.get_editor_property('mobility')==unreal.ComponentMobility.MOVABLE
  assert c.get_editor_property('visible') and not c.get_editor_property('hidden_in_game') and not a.get_editor_property('hidden')
  near(xyz(c.get_editor_property('decal_size')),[.5,r['radius_cm'],r['radius_cm']])
  pos=p.get_actor_location();near(xyz(a.get_actor_location()),[pos.x,pos.y,pos.z-.25])
  near(xyz(a.get_actor_scale3d()),[1,1,1])
  # At pitch=-90 Euler yaw/roll are ambiguous; validate actual decal axes.
  sign=-1 if r['kind']=='Radar' else 1
  near(xyz(c.get_forward_vector()),[0,0,-1],1e-4)
  near(xyz(c.get_right_vector()),[sign*v for v in xyz(p.get_actor_right_vector())],1e-4)
  near(xyz(c.get_up_vector()),[sign*v for v in xyz(p.get_actor_forward_vector())],1e-4)
  assert c.get_decal_material().get_path_name().split('.')[0]==r['material']
  assert abs(c.get_editor_property('fade_screen_size')-.001)<1e-6
  assert c.get_editor_property('sort_order')==(30 if r['kind']=='Diffusion' else 20)
  assert c.get_editor_property('fade_start_delay')==c.get_editor_property('fade_duration')==0
  assert not p.get_component_by_class(unreal.StaticMeshComponent).get_editor_property('receives_decals')
  mats.append(check_material(r))
 return mats

def run():
 assert not REPORT.exists(),'Already applied; inspect the report rather than duplicating effects'
 assert E.get_editor_world().get_path_name().split('.')[0]==MAP
 by=labels();before=snapshot(by);rows=records()
 assert not ({r['actor'] for r in rows}&set(by))
 for row in rows:
  p=by[row['parent']];c=p.get_component_by_class(unreal.StaticMeshComponent)
  assert c.static_mesh.get_name()=='SM_VR_BlueStacker' and c.get_editor_property('mobility')==unreal.ComponentMobility.MOVABLE
  near(xyz(p.get_actor_scale3d()),[1,1,1]);assert abs(p.get_actor_location().z-.5)<.001
  check_material(row)
 old=content();backup=ROOT/'Saved/Backups'/('GHS_NormalStackerFX_'+datetime.now().strftime('%Y%m%d_%H%M%S'));backup.mkdir(parents=True)
 shutil.copy2(ROOT/FILE,backup/'NormalWarehouse_before.umap');write(backup/'live_before.json',before);write(backup/'content_hashes.json',old)
 history={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Saved').glob('GHS_*.json')};write(backup/'history_hashes.json',history)
 report=dict(success=False,map=MAP,backup_root=str(backup),effects=rows,original_actor_count=len(by))
 try:
  with unreal.ScopedEditorTransaction('Add green diffusion and radar to floor stackers'):
   for r in rows:
    p=by[r['parent']];pos=p.get_actor_location();yaw=p.get_actor_rotation().yaw+(180 if r['kind']=='Radar' else 0)
    a=A.spawn_actor_from_class(unreal.DecalActor,unreal.Vector(pos.x,pos.y,pos.z-.25),unreal.Rotator(pitch=-90,yaw=yaw,roll=0));assert a
    a.set_actor_label(r['actor']);a.set_folder_path(FOLDER);a.set_actor_scale3d(unreal.Vector(1,1,1))
    c=a.get_component_by_class(unreal.DecalComponent);c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property('decal_size',unreal.Vector(.5,r['radius_cm'],r['radius_cm']))
    c.set_decal_material(LIB.load_asset(r['material']));c.set_fade_screen_size(.001);c.set_sort_order(30 if r['kind']=='Diffusion' else 20)
    c.set_editor_property('fade_start_delay',0.0);c.set_editor_property('fade_duration',0.0)
    rule=unreal.AttachmentRule.KEEP_WORLD;assert a.attach_to_actor(p,'',rule,rule,rule,False)
    a.tags=[unreal.Name('AGVAnimatedFX'),unreal.Name('FXOwner='+r['parent']),unreal.Name('NoEffectMesh')]
  material_states=validate(before,rows,labels())
  assert L.save_current_level()
  now=content();assert set(now)==set(old)
  changed=[p for p,h in old.items() if now[p]!=h];assert changed==[FILE],changed
  for p,h in history.items():assert sha(ROOT/p)==h,p
  report.update(success=True,effect_count=24,actor_count=len(labels()),materials=material_states,
   changed_content=changed,map_sha256=sha(ROOT/FILE),new_material_assets=0,new_lights=0,effect_meshes=0,
   projection_depth_cm=1,projection_z_range_cm=[-.25,.75],unchanged_original_objects=True)
  unreal.log('GHS_NORMAL_STACKER_FX_SAVED: 12 diffusion + 12 radar, native time-driven green decals attached to vehicles')
 except Exception:
  report['error']=traceback.format_exc();raise
 finally:write(REPORT,report)

def verify():
 assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
 result=dict(success=False)
 try:
  report=read(REPORT);assert report['success'];backup=Path(report['backup_root']);old=read(backup/'content_hashes.json');initial=content()
  assert set(initial)==set(old) and [p for p,h in old.items() if initial[p]!=h]==[FILE]
  assert sha(ROOT/FILE)==report['map_sha256'];assert L.load_level(MAP)
  by=labels();before=read(backup/'live_before.json');rows=report['effects']
  material_states=validate(before,rows,by)
  # Exercise attachment in this disposable, unsaved verification world.
  p=by['GHN_FloorStacker_05'];original=p.get_actor_transform()
  children=[by[r['actor']] for r in rows if r['parent']==p.get_actor_label()]
  local=[basis(a.get_component_by_class(unreal.DecalComponent).get_relative_transform()) for a in children]
  try:
   p.set_actor_location(p.get_actor_location()+unreal.Vector(173,-89,0),False,False)
   rot=p.get_actor_rotation();rot.yaw+=37;p.set_actor_rotation(rot,False)
   for a,expected in zip(children,local):
    for actual,wanted in zip(basis(a.get_component_by_class(unreal.DecalComponent).get_relative_transform()),expected):near(actual,wanted,1e-4)
    near(xyz(a.get_actor_location()),[p.get_actor_location().x,p.get_actor_location().y,p.get_actor_location().z-.25])
  finally:p.set_actor_transform(original,False,False)
  validate(before,rows,by)
  assert content()==initial
  for path,h in read(backup/'history_hashes.json').items():assert sha(ROOT/path)==h,path
  result.update(success=True,vehicles=12,effects=24,materials=material_states,attached_movement_test_passed=True,
   only_normal_map_modified=True,shared_materials_unchanged=True,effect_meshes=0,new_lights=0,original_objects_preserved=len(before))
  unreal.log('GHS_NORMAL_STACKER_FX_VERIFIED: animation, green style, 24 decals, attachment movement and asset isolation passed')
 except Exception:
  result['error']=traceback.format_exc();raise
 finally:write(VERIFY,result)

if __name__=='__main__':run()
