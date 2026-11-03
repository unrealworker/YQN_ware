"""CPU-only source audit before Blender export; never imports bpy or writes assets.

Executes the real PV generation statements with an in-memory mesh collector,
checks macro boundaries/holes, triangulated far topology, CAD wall interfaces,
and texture output. Generated diagnostic textures/reports go under Saved only.
"""
from pathlib import Path
from collections import defaultdict
import ast,hashlib,json,math,sys,struct,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import shapely
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
from mpr_plan_layout import plan_to_world,load_registration

OUT=ROOT/'Saved/MPR/pv_v6';OUT.mkdir(parents=True,exist_ok=True)
SCRIPT=ROOT/'Tools/MPRWarehouse/build_mpr_reference_shell_v4.py'
LIB=ROOT/'Tools/MPRWarehouse/mpr_reference_shell_v4_lib.py'
PLAN=ROOT/'SourceAssets/MPR/reference_v4/architecture/plan_solar_v5.json'

class Collector:
 def __init__(self):self.data=defaultdict(lambda:defaultdict(lambda:[[],[]]));self.uv_checks=[]
 def mesh(self,name,role,verts,faces,uvs=None):
  vv,ff=self.data[name][role];n=len(vv);vv.extend(verts);ff.extend(tuple(i+n for i in f)for f in faces)
  if role=='MPR4_SolarMid':
   assert uvs is not None
   for face,uv in zip(faces,uvs):
    for index,(u,v) in zip(face,uv):
     p=verts[index];self.uv_checks.append(max(abs(u*1.12-60.-1.12/2-p[0]),abs(v*1.95-79.-1.95/2-p[1])))

def run():
 # The Saved pre-change snapshot is optional. A clean checkout uses its
 # delivered manifest for non-PV comparisons; the approved outline digest
 # remains fixed independently of the implementation.
 previous=json.loads((PLAN.parent/'reference_shell_manifest.json').read_text(encoding='utf8'))
 baseline_path=OUT/'baseline.json'
 baseline=json.loads(baseline_path.read_text(encoding='utf8')) if baseline_path.exists() else dict(old_architecture_materials=previous['materials'],old_apertures=previous['cad_apertures'])
 plan=json.loads(PLAN.read_text(encoding='utf8'))
 source=ROOT/plan['source_image']
 assert hashlib.sha256(source.read_bytes()).hexdigest()==plan['source_sha256']=='1f7a067a885a7ffe27f03e6abdf2f3298b3da15b3006ed1114a9b2b1149f9f54','Actual aerial source mismatch'
 assert plan['method']['review_version']=='aerial-roof-v1'
 assert plan['photo_registration']['maximum_anchor_error_m']<2.2
 for row in plan['regions']:
  p=Polygon(row['exterior_px'],row['holes_px']);assert p.is_valid
  assert all(Polygon(row['exterior_px']).contains(Polygon(h))for h in row['holes_px'])
 assert len(plan['clearances'])==plan['interior_hole_count']==18
 equipment_count=sum(r['feature']=='rooftop_equipment_clearance'for r in plan['clearances'])
 assert all(row['clear']for row in plan['validation']['clear_aisle_samples'])
 tree=ast.parse(SCRIPT.read_text(encoding='utf8'));lib=ast.parse(LIB.read_text(encoding='utf8'))
 scope=dict(ROOT=ROOT,np=np,math=math,json=json,hashlib=hashlib,Path=Path,sys=sys,
            Polygon=Polygon,shape_box=box,unary_union=unary_union,plan_to_world=plan_to_world,
            load_registration=load_registration,ROOF=13.4,OUT=PLAN.parent)
 cad=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'));scope['fp']=cad['footprint_outline_m']
 methods=next(n for n in lib.body if isinstance(n,ast.ClassDef)and n.name=='Geometry')
 for name in ('box','solar_surface'):
  node=next(n for n in methods.body if isinstance(n,ast.FunctionDef)and n.name==name)
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(LIB),'exec'),scope)
  setattr(Collector,name,scope[name])
 def segment(self,n,r,a,b,w,z,h):
  dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
  if length>.002:self.box(n,r,((a[0]+b[0])/2,(a[1]+b[1])/2,z),(length,w,h),math.degrees(math.atan2(dy,dx)))
 Collector.segment=segment
 g=Collector();scope['g']=g
 definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in ('inside','clear','plan_xy')]
 exec(compile(ast.Module(body=definitions,type_ignores=[]),str(SCRIPT),'exec'),scope)
 start=next(i for i,n in enumerate(tree.body)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='solar_path'for t in n.targets))
 end=next(i for i,n in enumerate(tree.body[start:],start)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Constant)and n.value.value=='SM_MPR4_RoofLight')
 exec(compile(ast.Module(body=tree.body[start:end],type_ignores=[]),str(SCRIPT),'exec'),scope)
 solar=scope['solar_area'];holes=unary_union([Polygon([q[:2]for q in plan_to_world(r['exterior_px'])])for r in plan['clearances']])
 banks=[]
 for name,roles in sorted(g.data.items()):
  surfaces=[];triangles=0
  for role,(v,faces) in roles.items():
   triangles+=sum(len(f)-2 for f in faces)
   for f in faces:
    p=np.asarray([v[i]for i in f]);assert np.isfinite(p).all()
    if np.ptp(p[:,2])<1e-9 and abs(float(p[0,2])-13.64)<1e-7 and role!='MPR4_SolarFrame':surfaces.append(Polygon(p[:,:2]))
  region=unary_union(surfaces);assert region.is_valid
  assert region.difference(solar).area<1e-6,(name,'Outside field')
  assert region.intersection(holes).area<1e-6,(name,'Hole covered')
  assert abs(sum(p.area for p in surfaces)-region.area)<1e-6,(name,'Duplicate top surface')
  banks.append(dict(name=name,triangles=triangles,material_roles=list(roles),top_area_m2=region.area,source_clearance_overlap_m2=region.intersection(holes).area))
 for row in scope['solar_lod_audit']:
  name=row['name'];mid=next(r for r in banks if r['name']==name+'_LOD1');far=next(r for r in banks if r['name']==name+'_LOD2')
  assert abs(mid['top_area_m2']-far['top_area_m2'])<1e-6
 helper=next(n for n in lib.body if isinstance(n,ast.FunctionDef)and n.name=='solar_lod_screen_sizes')
 exec(compile(ast.Module(body=[helper],type_ignores=[]),str(LIB),'exec'),scope)
 normalized=[]
 for name,roles in g.data.items():
  if name.endswith(('_LOD1','_LOD2')):continue
  vertices=[p for v,f in roles.values()for p in v]
  bounds=[[min(p[i]for p in vertices),max(p[i]for p in vertices)]for i in range(3)]
  radius=math.sqrt(sum(((hi-lo)*.5)**2 for lo,hi in bounds))
  screens=scope['solar_lod_screen_sizes'](bounds)
  assert 1>screens[1]>screens[2]>0,(name,radius,screens)
  assert abs(screens[1]/radius-.9/70)<1e-12 and abs(screens[2]/radius-.35/70)<1e-12
  normalized.append(dict(mesh=name,bounds_radius_m=radius,screen_sizes=screens))
 assert g.uv_checks and max(g.uv_checks)<1e-8,'Module grid must match physical module origins and pitches'
 # Evaluate the unchanged aperture construction against the CAD and prior
 # manifest. Only role selection differs; no wall position/cut is invented.
 wall_scope=dict(scope);wall_scope.update(g=Collector(),instances={},apertures=[],facade_bands=[],CAD=cad)
 add=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='add')
 exec(compile(ast.Module(body=[add],type_ignores=[]),str(SCRIPT),'exec'),wall_scope)
 ws=next(i for i,n in enumerate(tree.body)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='openings'for t in n.targets))
 we=next(i for i,n in enumerate(tree.body[ws:],ws)if isinstance(n,ast.Assert))
 # Bevelled wall lamps are reusable instances, not evaluated here; boxes in
 # facade construction have no bevel and execute the real helper above.
 exec(compile(ast.Module(body=tree.body[ws:we+1],type_ignores=[]),str(SCRIPT),'exec'),wall_scope)
 apertures=sorted(wall_scope['apertures'],key=lambda r:r['id']);old=sorted(baseline['old_apertures'],key=lambda r:r['id'])
 assert apertures==old,'CAD aperture interfaces changed'
 assert len(apertures)==74
 for row in wall_scope['facade_bands']:
  assert row['blue_top_z_m']==(4.5 if row['dock_facade'] else 1.4)
 wall_checks=[];previous_meshes={r['name']:r for r in previous['meshes']}
 for name,roles in wall_scope['g'].data.items():
  if not name.startswith('SM_MPR4_Facade_'):continue
  vertices=[p for v,f in roles.values()for p in v]
  bounds=[[min(p[i]for p in vertices),max(p[i]for p in vertices)]for i in range(3)]
  triangles=sum(len(face)-2 for v,f in roles.values()for face in f)
  assert np.max(np.abs(np.array(bounds)-previous_meshes[name]['bounds_m']))<1e-8
  assert triangles==previous_meshes[name]['triangles']
  wall_checks.append(dict(mesh=name,bounds_unchanged=True,triangles=triangles))
 fixture_scope=dict(scope);fixture_scope.update(instances={},rooflights=[],Point=Point)
 exec(compile(ast.Module(body=[add],type_ignores=[]),str(SCRIPT),'exec'),fixture_scope)
 fixture_loop=next(n for n in tree.body if isinstance(n,ast.For)and isinstance(n.iter,ast.Call)and 'roof_fixtures' in ast.unparse(n.iter))
 exec(compile(ast.Module(body=[fixture_loop],type_ignores=[]),str(SCRIPT),'exec'),fixture_scope)
 fixture_rows=[r for rows in fixture_scope['instances'].values()for r in rows]
 equipment=[r for r in fixture_rows if r.get('clearance_id')]
 assert len(fixture_rows)>20,'Aerial roof fixtures were lost'
 for row in fixture_rows:
  x,y,z=row['position_m'];scale=row['scale'][0]
  assert not box(x-.925*scale,y-.675*scale,x+.925*scale,y+.675*scale).intersects(solar),'Roof device overlaps PV'
 by_id={r['id']:r for r in plan['clearances']}
 for row in equipment:
  x,y,z=row['position_m'];s=row['scale'][0];footprint=box(x-.925*s,y-.675*s,x+.925*s,y+.675*s)
  clearance=Polygon([p[:2]for p in plan_to_world(by_id[row['clearance_id']]['exterior_px'])])
  assert clearance.contains(footprint) and not footprint.intersects(solar)
 # Execute only texture helpers, without importing bpy or creating geometry.
 texscope=dict(ROOT=ROOT,Path=Path,np=np,math=math,struct=struct,zlib=zlib)
 exec(compile(ast.Module(body=[n for n in lib.body if isinstance(n,ast.FunctionDef)and n.name in ('png','make_textures')],type_ignores=[]),str(LIB),'exec'),texscope)
 textures=texscope['make_textures'](OUT/'texture_audit')
 unchanged=[]
 for kind in ('paint','fabric','checker'):
  for path in textures[kind].values():
   old=PLAN.parent/'textures'/Path(path).name
   assert hashlib.sha256(old.read_bytes()).hexdigest()==hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),('Non-PV texture changed',kind)
   unchanged.append(old.relative_to(ROOT).as_posix())
 # Material expression evaluation verifies the only changed old role is PV.
 material_node=next(n for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='materials'for t in n.targets))
 mat_eval=ast.Expression(material_node.value);materials=eval(compile(mat_eval,str(SCRIPT),'eval'),dict(dict=dict,textures=textures))
 for role,old in baseline['old_architecture_materials'].items():
  if role=='MPR4_SolarCells':continue
  for key in ('color','roughness','metallic','normal_strength'):
   if role=='MPR4_RoofMembrane' and key=='color':
    assert materials[role][key]==[1.,1.,1.];continue
   if key in old:assert materials[role].get(key,0)==old[key],('Non-PV material changed',role,key)
 report=dict(success=True,scope='CPU source generation/geometry/texture audit only; no Blender export, UE LOD/mip readback, temporal video or visual acceptance yet.',
  source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in (SCRIPT,LIB,PLAN,source,ROOT/'Tools/MPRWarehouse/extract_mpr_plan_solar.py')},
  fields=len(plan['regions']),clearances=len(plan['clearances']),device_clearances=equipment_count,unchanged_macro_outlines=True,
  macro_outline_scope='Unchanged from current aerial measurement; user explicitly superseded old schematic outlines.',
  aerial_source_sha256=plan['source_sha256'],photo_registration_max_error_m=plan['photo_registration']['maximum_anchor_error_m'],
  preserved_cad_apertures=len(apertures),facade_blue_bands=wall_scope['facade_bands'],
  module_uv_alignment_max_error_m=max(g.uv_checks),
  facade_geometry_checks=wall_checks,placed_roof_devices=len(fixture_rows),placed_array_devices=len(equipment),
  unchanged_non_pv_textures=unchanged,unchanged_non_pv_materials_except_authorized_roof_tint=True,
  authorized_roof_membrane_tint=[1.,1.,1.],banks=banks,
  solar_lod_audit=scope['solar_lod_audit'],reference_screen_sizes=[1,.9,.35],reference_bounds_radius_m=70.,
  normalized_bank_lod_thresholds=normalized,visual_modules=len(scope['grid']),continuous_strips=len(scope['strips']),
  dynamic_validation_required=['Force near/mid/far and compare silhouettes/clearances','Actual 1920x1080 orbit and continuous zoom across each LOD threshold','Read back mip/filter/LOD settings and measure pixel-aligned temporal stability'])
 (OUT/'source_audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
 (OUT/'generated_aerial_modules.json').write_text(json.dumps(dict(strips=scope['strips'],roof_fixtures=fixture_rows),indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in report.items()if k not in ('source_sha256','banks','solar_lod_audit','unchanged_non_pv_textures','facade_blue_bands','facade_geometry_checks')},indent=2))

if __name__=='__main__':run()
