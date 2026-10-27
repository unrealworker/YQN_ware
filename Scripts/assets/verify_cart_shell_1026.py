"""Reopen the saved Blender asset and round-trip the FBX; audit the GLB payload."""
import bpy
import json
import struct
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/CartShell_1026'
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
    return dict(meshes=len(meshes),triangles=total,bounds_m=[low,high],size_mm=[(high[k]-low[k])*1000 for k in range(3)])

bpy.ops.wm.open_mainfile(filepath=str(OUT/'CartShell_1026.blend'))
native=audit(bpy.data.collections['GHS_CART | CAD assembly'].objects)
assert native['triangles']==manifest['triangle_count']
assert 9000<=native['triangles']<=10000
assert max(abs(a-b) for a,b in zip(native['size_mm'],manifest['source_size_mm']))<1.5
blue=bpy.data.materials['GHS | Industrial blue']
shader=next(n for n in blue.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
assert all(abs(a-b)<1e-6 for a,b in zip(shader.inputs['Base Color'].default_value[:3],(.015,.06,.42)))
assert abs(native['bounds_m'][0][2])<.001
assert hashlib.sha256(Path(manifest['source']).read_bytes()).hexdigest()==manifest['source_sha256']

payload=(OUT/'CartShell_1026.glb').read_bytes()
assert payload[:4]==b'glTF'
size,kind=struct.unpack_from('<II',payload,12)
gltf=json.loads(payload[20:20+size])
primitives=[p for m in gltf['meshes'] for p in m['primitives']]
glb_triangles=sum(gltf['accessors'][p['indices']]['count']//3 for p in primitives)
assert glb_triangles==native['triangles']
assert all(n.get('name','').startswith(('GHS_Cart','0','1','2','3','4')) for n in gltf['nodes'])
assert 'cameras' not in gltf

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(OUT/'SM_CartShell_1026.fbx'))
fbx=audit(bpy.context.scene.objects)
assert fbx['triangles']==native['triangles']
assert max(abs(a-b) for a,b in zip(fbx['size_mm'],native['size_mm']))<.01
report=dict(passed=True,blender_version=bpy.app.version_string,native=native,fbx_roundtrip=fbx,
            glb_triangles=glb_triangles,material_nodes_verified=True,source_hash_unchanged=True,
            export_studio_excluded=True)
(OUT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('VERIFIED',json.dumps(report),flush=True)
