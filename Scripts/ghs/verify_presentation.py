"""Read-only presentation verification, retaining historical applied/verification reports."""
import json,math,sys,traceback,collections
from pathlib import Path
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import unreal
import verify_ue_scene as common
import verify_clearance_scene as clearance
import verify_column_outlines as column
import verify_joined_walls as joined
REPORT=ROOT/'Saved/GHS_PresentationVerification.json'
CARGO=['GHS_CAD_PalletCargo','GHS_CAD_PalletCargoLow','GHS_CAD_PalletCargoHigh']
def read(p):return common.read_json(p)
def prop(o,k):return o.get_editor_property(k)
def close(a,b,where,tol=.0002):assert abs(float(a)-float(b))<=tol,(where,a,b)

def assert_xy_contained(inner,outer,context,tolerance=.001):
 for x,y in inner.corners:
  dx,dy=x-outer.x,y-outer.y
  assert abs(dx*outer.co+dy*outer.si)<=outer.hx+tolerance,(context,'local X outside')
  assert abs(-dx*outer.si+dy*outer.co)<=outer.hy+tolerance,(context,'local Y outside')

def baseline_transform(row):
 x,y,z=row['position_m']
 return unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100),rotation=unreal.Rotator(pitch=0,yaw=-row['rotation_deg'],roll=0),scale=unreal.Vector(*row['scale']))

def main(report):
 src=ROOT/'SourceAssets/GHS';build=read(ROOT/'Saved/GHS_BuildReport.json');assert build.get('presentation_refined')
 before=read(ROOT/'Saved/GHS_PresentationBefore.json');applied=read(ROOT/'Saved/GHS_PresentationApplied.json');assert applied['success']
 baseline_path=Path(before['backup'])/'ue_scene_registry.json';baseline=read(baseline_path)
 plan=read(src/'Presentation/visual_layout.json');registry=read(src/'ue_scene_registry.json');layout=read(src/'clearance_layout.json');cad=read(src/'cad_layout.json')
 assert clearance.sha(baseline_path)==before['registry_sha256']==plan['presentation']['source_baseline_sha256']
 historical={p:clearance.sha(p) for p in (ROOT/'Saved').glob('GHS_*Verification.json') if p!=REPORT}
 map_path=ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap';map_sha=clearance.sha(map_path);reg_sha=clearance.sha(src/'ue_scene_registry.json')
 assert registry['groups']==plan['groups'] and registry['individuals']==baseline['individuals']==plan['individuals']
 groups={g['actor']:g for g in registry['groups']};old={g['actor']:g for g in baseline['groups']}
 assert len(groups)==18 and sum(g['count'] for g in groups.values())==14116
 for label,g in old.items():
  if label not in plan['presentation']['modified_labels']:assert groups[label]==g,label
 oldcargo={r['id']:r for r in old[CARGO[0]]['instances']};newcargo={r['id']:r for label in CARGO for r in groups[label]['instances']}
 assert len(newcargo)==7408 and set(newcargo)==set(oldcargo)
 for id,r in newcargo.items():
  for k in ['position_m','rotation_deg','scale','source_handles']:assert r[k]==oldcargo[id][k],(id,k)
 for label in ['GHS_CAD_Racks','GHS_CAD_Columns','GHS_ColumnEdgeOutlines']:
  a={r['id']:r for r in old[label]['instances']};b={r['id']:r for r in groups[label]['instances']};assert set(a)==set(b)
  for id,r in b.items():
   assert r['position_m'][:2]==a[id]['position_m'][:2] and r['scale'][:2]==a[id]['scale'][:2]
   assert r['rotation_deg']==a[id]['rotation_deg'] and r['source_handles']==a[id]['source_handles']
 report['lineage']=clearance.lineage_checks(layout,registry,cad)
 common.report=report;common.main(clearance_layout=layout);report['success']=False
 assert (report['actor_count'],report['hism_group_count'],report['instanced_count'])==(227,18,14116)
 actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors();labels={a.get_actor_label():a for a in actors}
 components={k:labels[k].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent) for k in groups}
 old_rows={r['id']:(g['mesh'],r) for g in old.values() for r in g['instances']};old_bounds={name:unreal.EditorAssetLibrary.load_asset(common.expected_mesh_path(name)).get_bounds() for name in {g['mesh'] for g in old.values()}}
 objects=[];boxes={};mapping={label:'cargo' for label in CARGO};mapping.update({'GHS_CAD_Racks':'rack','GHS_CAD_DockRacks':'dock_rack','GHS_CAD_Columns':'column','GHS_ColumnBases':'column_base'})
 expected_rows={r['id']:r for k in ['storage','racks','equipment','columns'] for r in layout[k]}
 for label,kind in mapping.items():
  c=components[label];bounds=prop(c,'static_mesh').get_bounds()
  for i,r in enumerate(groups[label]['instances']):
   box=clearance.actual_box(c.get_instance_transform(i,world_space=True),bounds);boxes[r['id']]=box;objects.append(dict(actor=label,kind=kind,id=r['id'],box=box))
   if r['id'] in expected_rows:
    e=expected_rows[r['id']];size=list(e['size_m']);size=size[::-1] if kind=='rack' else size
    if kind in ['cargo','rack']:
     old_name,old_row=old_rows[r['id']];oldbox=clearance.actual_box(baseline_transform(old_row),old_bounds[old_name]);assert_xy_contained(box,oldbox,r['id']+' inside old actual mesh')
     yaw=math.radians(e['rotation_deg']+(90 if kind=='rack' else 0));cadbox=clearance.geometry.Box(e['position_m'][0],e['position_m'][1],size[0]/2,size[1]/2,math.cos(yaw),math.sin(yaw),0,10);assert_xy_contained(box,cadbox,r['id']+' inside CAD footprint')
    else:common.compare([box.x,box.y,box.hx*2,box.hy*2],list(e['position_m'])+size,.001,r['id']+' actual unchanged CAD XY')
   if kind=='column':close(box.zmax-box.zmin,5.6,r['id']+' height');close(box.zmin,0,r['id']+' grounded')
 report['intersections']=clearance.check_intersections(objects);assert report['intersections']['overlap_count']==0
 # Validate every physical outline against twelve disjoint expected edge boxes.
 outlines=collections.defaultdict(list);ec=components['GHS_ColumnEdgeOutlines'];eb=prop(ec,'static_mesh').get_bounds()
 for i,r in enumerate(groups['GHS_ColumnEdgeOutlines']['instances']):outlines[r['parent_column_id']].append(clearance.actual_box(ec.get_instance_transform(i,world_space=True),eb))
 assert len(outlines)==170
 for id,rows in outlines.items():
  body=boxes[id];size=(body.hx*2,body.hy*2,body.zmax-body.zmin);expected=column.expected_edges(*size);remaining=set(range(12));assert len(rows)==12;local=[]
  for b in rows:
   center,half,pts=column.box_in_column_frame(b,body);assert max(abs(p[k])-size[k]/2 for p in pts for k in range(3))<=column.TOLERANCE_M
   best=min(remaining,key=lambda j:max([abs(center[k]-expected[j][0][k]) for k in range(3)]+[abs(half[k]-expected[j][1][k]) for k in range(3)]))
   assert max([abs(center[k]-expected[best][0][k]) for k in range(3)]+[abs(half[k]-expected[best][1][k]) for k in range(3)])<=column.TOLERANCE_M;remaining.remove(best);local.append((center,half))
  assert not remaining and not any(column.local_positive_overlap(a,b) for i,a in enumerate(local) for b in local[i+1:])
 assert components['GHS_CAD_Columns'].get_material(0)==components['GHS_CAD_WallFaces'].get_material(0)
 assert ec.get_material(0)==components['GHS_CAD_WallEdges'].get_material(0)
 # Independently recover saved wall triangles, compare exact source and exposure boundaries.
 geometry=read(src/'joined_walls_geometry.json')
 if registry.get('wall_height_profile'):
  from wall_height_profile import projected_geometry
  geometry=projected_geometry(geometry)
 rect_list=joined.wall_rectangles(cad);rectangles=joined.PolygonGrid(rect_list);expanded=joined.PolygonGrid(joined.wall_rectangles(cad,joined.TOLERANCE_M));union_area=sum(rectangles.outside_area(poly,{i for i in rectangles.candidates(poly) if i<index}) for index,poly in enumerate(rect_list));editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);report['joined_walls']=[]
 for label,(name,material) in joined.WALLS.items():
  c=components[label];assert c.get_instance_count()==1;triangles,metrics=joined.saved_mesh_triangles(prop(c,'static_mesh'),c.get_instance_transform(0,world_space=True),editor);metrics.update(joined.compare_geometry(triangles,geometry['meshes'][name]));metrics.update(joined.validate_surfaces(name,triangles,rectangles,expanded,union_area,geometry['verification']));report['joined_walls'].append(metrics)
 manifest=read(src/'Presentation/presentation_storage.json');report['presentation_meshes']=[]
 for spec in manifest['meshes']:
  mesh=unreal.EditorAssetLibrary.load_asset(common.DEST+'/Meshes/'+spec['name']);assert mesh and editor.get_lod_count(mesh)==4
  bs=mesh.get_bounds();expected=spec['bounds_m'];center=[(a+b)*50 for a,b in expected];center[1]*=-1;extent=[(b-a)*50 for a,b in expected];common.compare(common.xyz(bs.origin),center,.05,spec['name']+' center');common.compare(common.xyz(bs.box_extent),extent,.05,spec['name']+' extent')
  original_name='SM_GHS_Shared_RackBay' if 'RackTall' in spec['name'] else 'SM_GHS_Shared_PalletCargo';ob=old_bounds[original_name]
  for k in ['x','y']:
   assert getattr(bs.origin,k)-getattr(bs.box_extent,k)>=getattr(ob.origin,k)-getattr(ob.box_extent,k)-.02
   assert getattr(bs.origin,k)+getattr(bs.box_extent,k)<=getattr(ob.origin,k)+getattr(ob.box_extent,k)+.02
  report['presentation_meshes'].append(dict(name=spec['name'],lod_count=4,height_m=bs.box_extent.z*.02))
 material_style=read(src/'Presentation/material_style.json');ml=unreal.MaterialEditingLibrary;report['material_parameter_readback']={}
 for name,item in material_style.items():
  mat=unreal.EditorAssetLibrary.load_asset(common.DEST+'/Materials/Instanced/M_GHS_'+name);assert isinstance(mat,unreal.Material)
  assert prop(mat,'used_with_instanced_static_meshes') and prop(mat,'shading_model')==unreal.MaterialShadingModel.MSM_DEFAULT_LIT
  assert prop(mat,'blend_mode')==(unreal.BlendMode.BLEND_TRANSLUCENT if 'opacity' in item else unreal.BlendMode.BLEND_OPAQUE)
  assert prop(mat,'two_sided')==('opacity' in item)
  tint=ml.get_material_default_vector_parameter_value(mat,'SurfaceTint');common.compare([tint.r,tint.g,tint.b],item['base_color'],1e-5,name+' SurfaceTint')
  base_node=ml.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR);assert isinstance(base_node,unreal.MaterialExpressionVectorParameter) and str(prop(base_node,'parameter_name'))=='SurfaceTint'
  expected={'Roughness':(item['roughness'],unreal.MaterialProperty.MP_ROUGHNESS),'Metallic':(item['metallic'],unreal.MaterialProperty.MP_METALLIC),'Specular':(.22,unreal.MaterialProperty.MP_SPECULAR)}
  if 'opacity' in item:expected['EnvelopeOpacity']=(item['opacity'],unreal.MaterialProperty.MP_OPACITY)
  values={}
  for param,(value,slot) in expected.items():
   actual=ml.get_material_default_scalar_parameter_value(mat,param);close(actual,value,name+' '+param,1e-5);node=ml.get_material_property_input_node(mat,slot);assert isinstance(node,unreal.MaterialExpressionScalarParameter) and str(prop(node,'parameter_name'))==param;values[param]=actual
  if 'emission' in item:
   actual=ml.get_material_default_scalar_parameter_value(mat,'EdgeGlow');close(actual,item['emission'],name+' EdgeGlow',1e-5);assert isinstance(ml.get_material_property_input_node(mat,unreal.MaterialProperty.MP_EMISSIVE_COLOR),unreal.MaterialExpressionMultiply);values['EdgeGlow']=actual
  else:assert ml.get_material_property_input_node(mat,unreal.MaterialProperty.MP_EMISSIVE_COLOR) is None
  report['material_parameter_readback'][name]={'SurfaceTint':[tint.r,tint.g,tint.b],**values}
 style=read(src/'lighting_style.json');sky=[a for a in actors if isinstance(a,unreal.SkyLight)];directions=[a for a in actors if isinstance(a,unreal.DirectionalLight)];assert len(sky)==len(directions)==1 and not any(isinstance(a,(unreal.RectLight,unreal.PointLight,unreal.SpotLight)) for a in actors)
 sc=sky[0].get_component_by_class(unreal.SkyLightComponent);dc=directions[0].get_component_by_class(unreal.DirectionalLightComponent)
 close(prop(sc,'intensity'),style['skylight_intensity'],'sky style');close(prop(dc,'intensity'),style['directional_intensity'],'directional style');assert not prop(sc,'real_time_capture') and not prop(sc,'cast_shadows') and bool(prop(dc,'cast_shadows'))==bool(style.get('directional_cast_shadows',False));assert prop(sc,'cubemap').get_path_name()==style['skylight_cubemap']
 if 'directional_source_angle' in style:close(prop(dc,'light_source_angle'),style['directional_source_angle'],'directional source angle')
 for comp,key in [(sc,'skylight_color'),(dc,'directional_color')]:
  if key in style:
   actual=comp.get_light_color();common.compare([actual.r,actual.g,actual.b],style[key],.01,key)
 if 'directional_rotation' in style:
  rot=directions[0].get_actor_rotation();actual=[rot.pitch,rot.yaw,rot.roll]
  assert all(abs((a-b+180)%360-180)<.02 for a,b in zip(actual,style['directional_rotation']))
 pp=prop(labels['GHS_ApprovedDigitalTwinLook'],'settings')
 for k,v in [('ambient_occlusion_intensity',style['ambient_occlusion_intensity']),('ambient_occlusion_radius',style['ambient_occlusion_radius_cm']),('ambient_occlusion_quality',style['ambient_occlusion_quality']),('vignette_intensity',0),('auto_exposure_min_brightness',0),('auto_exposure_max_brightness',0),('auto_exposure_bias',0)]:assert prop(pp,'override_'+k);close(prop(pp,k),v,k)
 assert prop(pp,'dynamic_global_illumination_method')==unreal.DynamicGlobalIlluminationMethod.NONE and prop(pp,'reflection_method')==unreal.ReflectionMethod.NONE
 assert clearance.sha(map_path)==map_sha and clearance.sha(src/'ue_scene_registry.json')==reg_sha and clearance.sha(ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap')==clearance.SOURCE_SHA
 assert all(clearance.sha(p)==digest for p,digest in historical.items())
 report.update(success=True,presentation_refined=True,baseline_sha256=before['registry_sha256'],all_cargo_xy_unchanged=True,all_column_frames_closed=True,blocked_slots_preserved=122,lighting_style=style,historical_reports_unchanged=True,non_surveyed_height_assumptions=plan['presentation']['assumptions'])

def run():
 report=dict(success=False,map=common.MAP,groups=[],individuals=[],effects=[],meshes=[],verification_mode='Fresh UE reload; read-only actual transforms and mesh geometry')
 try:main(report)
 except Exception:report['error']=traceback.format_exc();raise
 finally:REPORT.write_text(json.dumps(report,indent=2),encoding='utf8')
 unreal.log('GHS_PRESENTATION_VERIFIED '+json.dumps({k:report[k] for k in ['success','actor_count','hism_group_count','instanced_count']}))
if __name__=='__main__':run()
