"""Scoped replay derivatives from existing editable assets, background Blender only."""
import bpy,sys,json,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/GHS/OrderReplay'; OUT.mkdir(parents=True,exist_ok=True)
SOURCES=[ROOT/'SourceAssets/GHS_Normal/MannedForklift/manned_forklift_50k.blend',
 ROOT/'SourceAssets/GHS_Normal/TrucksLong/dock_truck_long.blend',
 ROOT/'SourceAssets/GHS/DoublePallet/double_pallet_storage.blend',
 ROOT/'SourceAssets/GHS/RefinementV2/Envelope/envelope_v2.blend']
protected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}
parts=[]; material_specs={}

def export_part(name,objects,offset=(0,0,0)):
    deps=bpy.context.evaluated_depsgraph_get(); vertices=[];faces=[];slots=[];indices=[]
    for obj in objects:
        if obj.type not in {'MESH','CURVE','FONT'}:continue
        ev=obj.evaluated_get(deps); mesh=ev.to_mesh()
        if not mesh:continue
        start=len(vertices); vertices.extend(tuple(obj.matrix_world@v.co-Vector(offset)) for v in mesh.vertices)
        mapping=[]
        for mat in mesh.materials:
            if mat is None:continue
            if mat.name not in slots:slots.append(mat.name)
            mapping.append(slots.index(mat.name))
            if mat.name not in material_specs:
                shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None) if mat.use_nodes else None
                material_specs[mat.name]=dict(name=mat.name,color=list(shader.inputs['Base Color'].default_value if shader else mat.diffuse_color),roughness=shader.inputs['Roughness'].default_value if shader else .6,metallic=shader.inputs['Metallic'].default_value if shader else 0)
        for p in mesh.polygons:
            faces.append(tuple(start+v for v in p.vertices));indices.append(mapping[p.material_index] if mapping else 0)
        ev.to_mesh_clear()
    assert vertices,(name,'empty source')
    data=bpy.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
    for slot in slots:data.materials.append(bpy.data.materials[slot])
    for p,idx in zip(data.polygons,indices):p.material_index=idx
    obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    triang=obj.modifiers.new('Export triangulation','TRIANGULATE')
    bpy.ops.export_scene.fbx(filepath=str(OUT/(name+'.fbx')),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_space_transform=False,add_leaf_bones=False,use_mesh_modifiers=True)
    bounds=[[min(v[i] for v in vertices),max(v[i] for v in vertices)] for i in range(3)]
    parts.append(dict(name=name,fbx=str(OUT/(name+'.fbx')),slots=slots,bounds_m=bounds,source_parts=len(objects),triangles=sum(len(f)-2 for f in faces),sha256=hashlib.sha256((OUT/(name+'.fbx')).read_bytes()).hexdigest()))
    bpy.data.objects.remove(obj,do_unlink=True)

bpy.ops.wm.open_mainfile(filepath=str(SOURCES[0]))
objects=[o for o in bpy.data.objects if o.name.startswith('MF_') or any(c.name=='05_Driver' for c in o.users_collection)]
(OUT/'fork_source_parts.json').write_text(json.dumps([o.name for o in objects],indent=2))
carriage=[o for o in objects if o.name.startswith(('MF_Carriage','MF_LoadBackrest','MF_Fork','MF_V2_TaperedForgedFork','MF_V2_ForkCarriageHook'))]
mast=[o for o in objects if o.name.startswith(('MF_InnerMastRail','MF_LiftRamChrome'))]
body=[o for o in objects if o not in carriage+mast]
assert carriage and mast and len(body)>300
for name,group in [('ForkliftBody',body),('ForkliftCarriage',carriage),('ForkliftMast',mast)]:export_part('SM_Replay_'+name,group)

bpy.ops.wm.open_mainfile(filepath=str(SOURCES[1]))
objects=[o for o in bpy.data.objects if o.type=='MESH' and not o.name.startswith('Studio')]
(OUT/'truck_source_parts.json').write_text(json.dumps([o.name for o in objects],indent=2))
body=[o for o in objects if not any(token in o.name.lower() for token in ('folded rear','rear cargo door','cargo door hinge'))]
export_part('SM_Replay_TruckBody',body)
# Same white metal panels, authored at each hinge; closed at yaw=0. Open 100 degrees.
mat=next(m for m in bpy.data.materials if m.name.endswith('_Body'))
def box(name,center,size):
    x,y,z=center;a,b,c=[v/2 for v in size]
    vs=[(x+i*a,y+j*b,z+k*c) for i,j,k in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    me=bpy.data.meshes.new(name);me.from_pydata(vs,[],[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);me.materials.append(mat)
    ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob);return ob
for side in [-1,1]:
    # Blender Y is reflected in UE; names refer to UE side.
    o=box('ReplayHingedDoor',(.015,side*.61,2.38),(.055,1.22,2.47))
    export_part('SM_Replay_TruckDoor'+('Left' if side<0 else 'Right'),[o]);bpy.data.objects.remove(o,do_unlink=True)

bpy.ops.wm.open_mainfile(filepath=str(SOURCES[2]))
for suffix in ['Low','Mid','High']:
    col=bpy.data.collections.get('SM_GHS_Presentation_Cargo'+suffix);assert col
    group=[o for o in col.objects if o.name.startswith(('Lower ','Tier0 '))]
    export_part('SM_Replay_Cargo'+suffix,group)

bpy.ops.wm.open_mainfile(filepath=str(SOURCES[3]))
col=bpy.data.collections.get('SM_GHS_V2DockDoor');assert col
group=[o for o in col.objects if not o.name.startswith(('Two-sided Panel','Lifted bottom','Narrow guide seal'))]
export_part('SM_Replay_DockDoorOpen',group)
assert protected=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES},'Source files changed'
(OUT/'replay_assets.json').write_text(json.dumps(dict(success=True,source_hashes=protected,meshes=parts,materials=list(material_specs.values())),indent=2),encoding='utf8')
print('REPLAY_ASSETS_READY',len(parts))
