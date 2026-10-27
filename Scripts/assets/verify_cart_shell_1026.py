"""Reopen the saved Blender asset and round-trip the FBX; audit the GLB payload."""
import bpy
import json
import struct
import hashlib
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/CartShell_1026'
DETAIL_20K='--20k' in sys.argv
if DETAIL_20K:OUT=OUT/'20k'
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))

def audit(objects):
    meshes=[o for o in objects if o.type=='MESH' and len(o.data.polygons)]
    points=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
    low=[min(p[k] for p in points) for k in range(3)]
    high=[max(p[k] for p in points) for k in range(3)]
    total=0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        total+=len(obj.data.loop_triangles)
        assert all(len(p.vertices)==3 for p in obj.data.polygons), obj.name
        assert not obj.modifiers, obj.name
        if DETAIL_20K:
            assert obj.data.uv_layers, ('Missing UVs for UE tangents', obj.name)
    return dict(meshes=len(meshes),triangles=total,bounds_m=[low,high],size_mm=[(high[k]-low[k])*1000 for k in range(3)])

bpy.ops.wm.open_mainfile(filepath=str(OUT/'CartShell_1026.blend'))
native=audit(bpy.data.collections['GHS_CART | CAD assembly'].objects)
assert native['triangles']==manifest['triangle_count']
budget=20000 if DETAIL_20K else 10000
assert budget*.9<=native['triangles']<=budget
assert max(abs(a-b) for a,b in zip(native['size_mm'],manifest['source_size_mm']))<1.5
blue=bpy.data.materials['GHS | Industrial blue']
shader=next(n for n in blue.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
assert all(abs(a-b)<1e-6 for a,b in zip(shader.inputs['Base Color'].default_value[:3],(.015,.06,.42)))
assert abs(native['bounds_m'][0][2])<.001
assert hashlib.sha256(Path(manifest['source']).read_bytes()).hexdigest()==manifest['source_sha256']

protected_audit=[]
open_hole_checks=0

def triangle_distance(point, triangle):
    """Double-precision distance for the very long, thin CAD triangles."""
    a,b,c=triangle
    ab,ac=b-a,c-a
    normal=np.cross(ab,ac)
    n2=np.dot(normal,normal)
    if n2>1e-30:
        signed=np.dot(point-a,normal)
        q=point-normal*(signed/n2)
        u=np.dot(np.cross(q-a,ac),normal)/n2
        v=np.dot(np.cross(ab,q-a),normal)/n2
        if u>=-1e-9 and v>=-1e-9 and u+v<=1+1e-9:
            return abs(signed)/np.sqrt(n2)
    distances=[]
    for start,end in ((a,b),(b,c),(c,a)):
        edge=end-start
        t=np.clip(np.dot(point-start,edge)/max(np.dot(edge,edge),1e-30),0,1)
        distances.append(np.linalg.norm(point-(start+t*edge)))
    return min(distances)

if DETAIL_20K:
    source=json.loads((ROOT/'Saved/CartShell1026/assembly_mesh.json').read_text(encoding='utf8'))
    optimized=json.loads((ROOT/'Saved/CartShell1026/optimized_parts_20k.json').read_text(encoding='utf8'))
    origin=Vector(manifest['cad_origin_mm'])
    for part in optimized:
        protected=set(part.get('protected_cad_patches',[]))
        protected_indices=set(part.get('protected_source_triangles',[]))
        if not protected and not protected_indices:continue
        obj=next(o for o in bpy.data.collections['GHS_CART | CAD assembly'].objects if o.get('source_index')==part['index'])
        tree=BVHTree.FromPolygons([obj.matrix_world@v.co for v in obj.data.vertices],
                                 [tuple(p.vertices) for p in obj.data.polygons],all_triangles=True)
        final_vertices=np.array([tuple(obj.matrix_world@v.co) for v in obj.data.vertices],dtype=np.float64)
        final_triangles=final_vertices[np.array([tuple(p.vertices) for p in obj.data.polygons])]
        original=source['parts'][part['index']]
        vertices=[(Vector(v)-origin)/1000 for v in original['vertices_mm']]
        distances=[]
        for index,(face,fid) in enumerate(zip(original['triangles'],original['face_ids'])):
            if fid not in protected and index not in protected_indices:continue
            a,b,c=(vertices[k] for k in face)
            for point in ((a+b+c)/3,(a+b)/2,(b+c)/2,(c+a)/2):
                hit=tree.find_nearest(point)
                assert hit[0] is not None
                distance=hit[3]
                if distance>.00001:
                    # Float32 BVH alone reports up to 0.3 mm even against the
                    # unchanged source itself. Use it only to find candidates.
                    candidates=tree.find_nearest_range(point,max(.001,distance*2))
                    distance=min(triangle_distance(np.array(point,dtype=np.float64),final_triangles[h[2]]) for h in candidates)
                distances.append(distance*1000)
        worst=max(distances)
        assert worst<.025,(part['index'],worst)
        protected_audit.append(dict(part_index=part['index'],cad_patches=len(protected),samples=len(distances),max_surface_error_mm=worst))
    upper=next(o for o in bpy.data.collections['GHS_CART | CAD assembly'].objects if o.get('source_index')==1)
    tree=BVHTree.FromPolygons([upper.matrix_world@v.co for v in upper.data.vertices],
                             [tuple(p.vertices) for p in upper.data.polygons],all_triangles=True)
    # Original 3 mm through-holes and handle slots must stay clear below the lid.
    centers=[(x,y) for x in (-115,-90,-65,-40,-15,15,40,65,90,115) for y in (160,175,190)]
    centers.extend([(-155,0),(155,0),(0,220)])
    for x,y in centers:
        hit=tree.ray_cast(Vector((x/1000,y/1000,.1965)),Vector((0,0,-1)),.0041)
        assert hit[0] is None,('blocked top opening',x,y,hit)
        open_hole_checks+=1

payload=(OUT/'CartShell_1026.glb').read_bytes()
assert payload[:4]==b'glTF'
size,kind=struct.unpack_from('<II',payload,12)
gltf=json.loads(payload[20:20+size])
primitives=[p for m in gltf['meshes'] for p in m['primitives']]
glb_triangles=sum(gltf['accessors'][p['indices']]['count']//3 for p in primitives)
assert glb_triangles==native['triangles']
if DETAIL_20K:
    assert all('TEXCOORD_0' in p['attributes'] for p in primitives)
assert all(n.get('name','').startswith(('GHS_Cart','0','1','2','3','4')) for n in gltf['nodes'])
assert 'cameras' not in gltf

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(OUT/'SM_CartShell_1026.fbx'))
fbx=audit(bpy.context.scene.objects)
assert fbx['triangles']==native['triangles']
assert max(abs(a-b) for a,b in zip(fbx['size_mm'],native['size_mm']))<.01
report=dict(passed=True,blender_version=bpy.app.version_string,native=native,fbx_roundtrip=fbx,
            glb_triangles=glb_triangles,material_nodes_verified=True,source_hash_unchanged=True,
            export_studio_excluded=True,triangle_budget=budget)
if DETAIL_20K:
    report['protected_cad_surfaces']=protected_audit
    report['clear_top_openings']=open_hole_checks
    report['uvs_verified_for_ue_tangents']=True
(OUT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('VERIFIED',json.dumps(report),flush=True)
