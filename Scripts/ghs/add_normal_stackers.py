"""Add individually editable floor-storage stackers to the Normal map only."""
import hashlib, itertools, json, math, shutil, sys, traceback
from datetime import datetime
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot, normalized, transform, xyz
MAP='/Game/Maps/GHS_CAD_NormalWarehouse'
MAP_FILE='Content/Maps/GHS_CAD_NormalWarehouse.umap'
ASSET='/Game/VideoDigitalTwin/Meshes/SM_VR_BlueStacker'
FOLDER='GHS_Normal/Vehicles/FloorStackers'
REPORT=ROOT/'Saved/GHS_NormalStackers.json'
VERIFICATION=ROOT/'Saved/GHS_NormalStackersVerification.json'
A=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
E=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
L=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
LIB=unreal.EditorAssetLibrary
MAT_ROOT='/Game/GHSDigitalTwin/Materials/M_VR_GHS_AGV_'
MATERIALS=[MAT_ROOT+'Rubber',MAT_ROOT+'Fasteners',MAT_ROOT+'Chassis',
 '/Game/GHSNormalWarehouse/Materials/M_GHN_RackSilver',
 '/Game/GHSNormalWarehouse/Materials/M_GHN_BluePallet',MAT_ROOT+'WarmWhite',
 MAT_ROOT+'WarmWhite',MAT_ROOT+'OpticalGlass',MAT_ROOT+'KukaOrange',
 MAT_ROOT+'EmergencyRed',MAT_ROOT+'GreenLED']

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def content():return {p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}
def labels():return {a.get_actor_label():a for a in A.get_all_level_actors()}

def mesh_box(mesh,t):
 b=mesh.get_bounds();o=xyz(b.origin);e=xyz(b.box_extent)
 ps=[xyz(unreal.MathLibrary.transform_location(t,unreal.Vector(*(o[i]+s[i]*e[i] for i in range(3))))) for s in itertools.product((-1,1),repeat=3)]
 return [min(p[i] for p in ps) for i in range(3)]+[max(p[i] for p in ps) for i in range(3)]

def gap_xy(a,b):
 return math.hypot(max(a[0]-b[3],b[0]-a[3],0),max(a[1]-b[4],b[1]-a[4],0))

def triangles(actor):
 c=actor.get_component_by_class(unreal.StaticMeshComponent)
 d=c.static_mesh.get_static_mesh_description(0);assert d
 t=c.get_world_transform();count=d.get_triangle_count();seen=0
 for i in range(count*4+1024):
  tid=unreal.TriangleID(id_value=i)
  if not d.is_triangle_valid(tid):continue
  seen+=1
  ps=[xyz(unreal.MathLibrary.transform_location(t,d.get_vertex_position(d.get_vertex_instance_vertex(d.get_triangle_vertex_instance(tid,j))))) for j in range(3)]
  yield ps
  if seen==count:break
 assert seen==count

def contains_xy(p,t):
 a,b,c=t;x,y=p
 den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
 if abs(den)<1e-8:return False
 u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
 v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
 return min(u,v,1-u-v)>=-1e-8

def check_geometry(by,rows,probe):
 # Conservative full-vehicle bounds include the fork overhang, not just chassis.
 excluded=[];obstacles=[]
 walls={'GHS_CAD_WallFaces','GHS_CAD_WallSections','GHS_CAD_WallEdges'}
 for item in probe['items']:
  n=item['label']
  if (not item['visible'] or item['hidden'] or n in walls or n=='GHS_CAD_ExactFootprint'
      or n.startswith('CAM_') or any(s in n for s in ('Studio','Surround','ContextGrid','Outlines','Clearances'))):
   excluded.append(n);continue
  for ins in item['instances']:
   b=ins['bounds']
   if b[5]>3 and b[2]<182:obstacles.append((n,ins['index'],b))
 result=[]
 for row in rows:
  box=row['bounds_cm'];nearest=min((gap_xy(box,b),n,i) for n,i,b in obstacles)
  assert nearest[0]>=19.99,(row['label'],'obstacle',nearest)
  assert .49<=box[2]<=.51,('ground',row['label'],box)
  result.append(dict(label=row['label'],nearest_clearance_cm=nearest[0],nearest_actor=nearest[1],nearest_instance=nearest[2]))
 for i,row in enumerate(rows):
  for other in rows[:i]:assert gap_xy(row['bounds_cm'],other['bounds_cm'])>=20
 floor=[t for t in triangles(by['GHS_CAD_ExactFootprint']) if all(abs(p[2])<.001 for p in t)]
 assert floor
 for row in rows:
  b=row['bounds_cm']
  for x in (b[0],(b[0]+b[3])/2,b[3]):
   for y in (b[1],(b[1]+b[4])/2,b[4]):assert any(contains_xy((x,y),t) for t in floor),(row['label'],'outside floor',x,y)
 wall_triangles=0
 for name in sorted(walls):
  if name not in by:continue
  for t in triangles(by[name]):
   wall_triangles+=1
   b=[min(p[i] for p in t) for i in range(3)]+[max(p[i] for p in t) for i in range(3)]
   if b[2]>182 or b[5]<0:continue
   for row in rows:assert gap_xy(row['bounds_cm'],b)>=20,(row['label'],'wall triangle',name,b)
 return dict(full_vehicle_including_forks=True,placements=result,obstacle_count=len(obstacles),wall_triangles_checked=wall_triangles,
  floor_coverage_points_per_vehicle=9,ground_clearance_cm=.5,excluded_from_solid_aabb_check=excluded)

def validate(by,before,plan,probe):
 expected={r['label'] for r in plan['placements']}
 assert len(expected)==12 and set(by)==set(before)|expected
 after=snapshot(by)
 for n,v in before.items():assert after[n]==v,('Unrelated object modified',n)
 checked=[]
 for r in plan['placements']:
  a=by[r['label']];c=a.get_component_by_class(unreal.StaticMeshComponent)
  assert a.get_class()==unreal.StaticMeshActor.static_class() and a.get_attach_parent_actor() is None
  assert str(a.get_folder_path())==FOLDER
  assert c.static_mesh.get_path_name()==ASSET+'.'+ASSET.rsplit('/',1)[1]
  assert [c.get_material(i).get_path_name().split('.')[0] for i in range(11)]==MATERIALS
  t=transform(a.get_actor_transform())
  assert all(abs(x-y)<.001 for x,y in zip(t['position_cm'],r['position_cm']))
  assert all(abs(s-1)<1e-6 for s in t['scale'])
  assert abs((t['rotation_deg'][1]-r['yaw_deg']+180)%360-180)<.001
  assert abs(t['rotation_deg'][0])+abs(t['rotation_deg'][2])<.001
  b=mesh_box(c.static_mesh,c.get_world_transform())
  assert max(abs(x-y) for x,y in zip(b,r['bounds_cm']))<.01
  assert not c.get_editor_property('receives_decals')
  checked.append(dict(r,bounds_cm=b))
 return check_geometry(by,checked,probe)

def run():
 assert not REPORT.exists(),'Inspect existing stacker report before reapplying'
 assert E.get_editor_world().get_path_name().split('.')[0]==MAP
 plan=read(ROOT/'Saved/GHS_NormalStackerPlan.json');probe=read(ROOT/'Saved/GHS_NormalStackerProbe.json')
 assert plan['success'] and plan['map']==MAP and plan['asset'].split('.')[0]==ASSET
 assert plan['source_probe_sha256']==sha(ROOT/'Saved/GHS_NormalStackerProbe.json')
 assert plan['source_live_baseline_sha256']==sha(ROOT/'Saved/GHS_NormalStackerLiveBaseline.json')
 before=read(ROOT/'Saved/GHS_NormalStackerLiveBaseline.json');by=labels()
 assert snapshot(by)==normalized(before),'Scene changed after planning; refresh probe before applying'
 assert not any(n.startswith('GHN_FloorStacker_') for n in by)
 geometry=check_geometry(by,plan['placements'],probe)
 old=content();backup=ROOT/'Saved/Backups'/('GHS_NormalStackers_'+datetime.now().strftime('%Y%m%d_%H%M%S'));backup.mkdir(parents=True)
 shutil.copy2(ROOT/MAP_FILE,backup/'GHS_CAD_NormalWarehouse.umap')
 write(backup/'content_hashes.json',old);write(backup/'live_scene_before.json',before)
 write(backup/'plan.json',plan);write(backup/'probe.json',probe)
 history={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Saved').glob('GHS_*.json')}
 write(backup/'history_hashes.json',history)
 report=dict(success=False,map=MAP,backup_root=str(backup),original_actor_count=len(by),materials=MATERIALS)
 try:
  mesh=LIB.load_asset(ASSET);assert mesh and len(mesh.static_materials)==11
  mats=[LIB.load_asset(m) for m in MATERIALS];assert all(mats)
  with unreal.ScopedEditorTransaction('Add floor-storage stackers to NormalWarehouse'):
   for r in plan['placements']:
    a=A.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*r['position_cm']),unreal.Rotator(yaw=r['yaw_deg']))
    assert a;a.set_actor_label(r['label']);a.set_folder_path(FOLDER)
    a.set_actor_scale3d(unreal.Vector(1,1,1));a.tags=[unreal.Name('NormalWarehouseFloorStacker'),unreal.Name('WorkArea=FloorStorage')]
    c=a.get_component_by_class(unreal.StaticMeshComponent);assert c.set_static_mesh(mesh)
    for i,m in enumerate(mats):c.set_material(i,m)
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property('receives_decals',False);c.set_editor_property('cast_shadow',True)
    c.set_collision_profile_name('NoCollision')
  geometry=validate(labels(),before,plan,probe)
  assert L.save_current_level()
  now=content();assert set(now)==set(old)
  changed=[p for p,h in old.items() if now[p]!=h];assert changed==[MAP_FILE],changed
  for p,h in history.items():assert sha(ROOT/p)==h,p
  report.update(success=True,added=plan['placements'],added_count=12,actor_count=len(labels()),geometry=geometry,
    changed_content=changed,map_sha256=sha(ROOT/MAP_FILE),shared_assets_and_other_maps_unchanged=True,
    original_actors_unchanged=True,individually_editable=True)
  unreal.log('GHS_NORMAL_STACKERS_SAVED: 12 independent placements, unchanged shared assets and other maps')
 except Exception:
  report['error']=traceback.format_exc();raise
 finally:write(REPORT,report)

def verify():
 assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
 result=dict(success=False)
 try:
  report=read(REPORT);assert report['success'];backup=Path(report['backup_root'])
  initial=content();old=read(backup/'content_hashes.json')
  assert set(initial)==set(old) and [p for p,h in old.items() if initial[p]!=h]==[MAP_FILE]
  assert sha(ROOT/MAP_FILE)==report['map_sha256']
  assert L.load_level(MAP)
  geometry=validate(labels(),read(backup/'live_scene_before.json'),read(backup/'plan.json'),read(backup/'probe.json'))
  assert content()==initial
  for p,h in read(backup/'history_hashes.json').items():assert sha(ROOT/p)==h,p
  result.update(success=True,map=MAP,independent_stackers=12,original_actors_preserved=report['original_actor_count'],
   geometry=geometry,only_normal_map_modified=True,shared_assets_unchanged=True)
  unreal.log('GHS_NORMAL_STACKERS_VERIFIED: placements, full bounds clearance, floor/walls, materials, and map isolation passed')
 except Exception:
  result['error']=traceback.format_exc();raise
 finally:write(VERIFICATION,result)

if __name__=='__main__':run()
