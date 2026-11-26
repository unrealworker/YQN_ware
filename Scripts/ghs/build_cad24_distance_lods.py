"""Build distant CAD24 rack LODs with pallet-by-pallet capacity UVs (background Blender)."""
import hashlib
import json
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Content/GHSTwinUI/data'
OUT = ROOT / 'Saved/GHS_RenderStability/RackLODs'
ROLES = ['Upright', 'Beam', 'Braces', 'Pallet', 'Cargo']
CORNERS = [(-1,-1,-1), (-1,-1,1), (-1,1,-1), (-1,1,1),
           (1,-1,-1), (1,-1,1), (1,1,-1), (1,1,1)]
QUADS = [(0,2,6,4), (1,5,7,3), (0,4,5,1), (2,3,7,6), (0,1,3,2), (4,6,7,5)]


def build(variant, spec, rack, storage, lod):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    vertices, faces, materials, slots = [], [], [], []

    def cuboid(center, extents, material, slot=-1):
        start = len(vertices)
        vertices.extend(tuple(center[i]+c[i]*extents[i]*.5 for i in range(3)) for c in CORNERS)
        faces.extend(tuple(start+i for i in face) for face in QUADS)
        materials.extend([material]*6)
        slots.extend([slot]*6)

    width, depth = rack['physical_span_m'], rack['physical_depth_m']
    post = spec.get('post_width_m', .0762)
    height = spec['post_height_m']
    clear = width - 2*post
    for side in (-1,1):
        x = side*(width-post)/2
        for face in (-1,1):
            y = face*(depth-post)/2
            cuboid((x,y,height/2),(post,post,height),0)
        for z in (.12,height-.09):
            cuboid((x,0,z),(.032,depth-2*post,.032),2)
    for z in spec['support_z_m']:
        if z > .001:
            thickness = spec['beam_height_m']
            for side in (-1,1):
                cuboid((0,side*(depth-post)/2,z-thickness/2),(clear,.065,thickness),1)

    for index, stack in enumerate(storage['cargo_stacks']):
        slot = storage['slots'][index]
        assert (slot['index'],slot['level'],slot['column']) == (index,stack['level'],stack['column'])
        x,z = stack['pallet_center_x_m'],stack['base_z_m']
        wood = .123952
        cuboid((x,0,z+wood/2),(storage['cargo_width_m'],storage['cargo_depth_m'],wood),3,index)
        h = stack['stack_top_z_m']-z-wood
        # The CAD24 carton pattern is 2x2 rigid boxes per layer. At mid distance
        # retain the central vertical seam. At far distance use its silhouette.
        for dx in ((-.235,.235) if lod==2 else (0,)):
            cuboid((x+dx,0,z+wood+h/2),(.45 if lod==2 else .944,1.136,h),4,index)

    name = storage['name']+'_LOD'+str(lod)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    obj = bpy.data.objects.new(name,mesh)
    bpy.context.scene.collection.objects.link(obj)
    for role in ROLES:
        mesh.materials.append(bpy.data.materials.new('M_GHS_CADRack_'+role))
    uv0 = mesh.uv_layers.new(name='UVMap')
    uv1 = mesh.uv_layers.new(name='CapacitySlot')
    for face,role,index in zip(mesh.polygons,materials,slots):
        face.material_index = role
        for corner,coord in zip(face.loop_indices,[(0,0),(0,1),(1,1),(1,0)]):
            uv0.data[corner].uv = coord
            uv1.data[corner].uv = (index,0)
    mesh.uv_layers.active_index = 0
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = OUT/(name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
        mesh_smooth_type='FACE',add_leaf_bones=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path))
    [restored] = [o for o in bpy.context.scene.objects if o.type=='MESH']
    m = restored.data
    assert [v.name for v in m.materials]==['M_GHS_CADRack_'+role for role in ROLES]
    assert len(m.uv_layers)==2
    seen = {}
    for poly in m.polygons:
        slot_uv = {tuple(m.uv_layers[1].data[i].uv) for i in poly.loop_indices}
        assert len(slot_uv)==1
        u,v = slot_uv.pop()
        assert v==0 and u==int(u) and ((u==-1)==(poly.material_index<3))
        seen.setdefault(int(u),set()).add(poly.material_index)
    assert seen.pop(-1)=={0,1,2}
    assert set(seen)==set(range(len(storage['slots']))) and all(v=={3,4} for v in seen.values())
    points = [restored.matrix_world@v.co for v in m.vertices]
    expected = (width/2,max(depth,storage['cargo_depth_m'])/2,height)
    bounds = [[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]
    for actual,want in zip(bounds,[[-expected[0],expected[0]],[-expected[1],expected[1]],[0,height]]):
        assert all(abs(a-b)<.001 for a,b in zip(actual,want)),(name,actual,want)
    m.calc_loop_triangles()
    return dict(fbx=path.name,triangles=len(m.loop_triangles),slots=len(seen),bounds_m=bounds,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main(meshes=None):
    OUT.mkdir(parents=True,exist_ok=True)
    cad = json.loads((ROOT/'SourceAssets/GHS/CAD24/racks.json').read_bytes())
    if meshes is None:
        meshes = json.loads((DATA/'storage-capacity.json').read_bytes())['meshes']
    report = {}
    for variant,spec in cad['catalog'].items():
        rack = next(r for r in cad['racks'] if r['variant']==variant)
        storage = next(m for m in meshes if m['name']=='SM_GHS_V2Rack_CAD24_'+variant+'_Capacity')
        report[storage['name']] = {str(lod):build(variant,spec,rack,storage,lod) for lod in (2,3)}
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('RACK_DISTANCE_LODS', {n:[x['triangles'] for x in lods.values()] for n,lods in report.items()})


if __name__=='__main__':
    main()
