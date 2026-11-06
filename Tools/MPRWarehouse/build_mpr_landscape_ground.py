"""Export only the two planting-bed meshes from the CPU-validated source plan."""
from pathlib import Path
import hashlib
import json
import math
import sys
import bpy

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_blender_common import Geometry
OUT=ROOT/'SourceAssets/MPR/landscape_layout_20261106/ground'
plan=json.loads((OUT/'plan.json').read_text(encoding='utf-8'))
G=Geometry()
for s in plan['surfaces']:
    for tri in s['triangles_m']:
        if (tri[1][0]-tri[0][0])*(tri[2][1]-tri[0][1])-(tri[1][1]-tri[0][1])*(tri[2][0]-tri[0][0])<0:
            tri=list(reversed(tri))
        G.mesh('SM_MPRLG_CampusGreen',s['role'],tri,[(0,1,2)])
for f in plan['linear_features']:
    if not f['id'].startswith('WheelStop_'):continue
    half=f['width_m']/2;height=f['height_m']
    for a,b in zip(f['points_m'],f['points_m'][1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<.001:continue
        nx,ny=-dy/length*half,dx/length*half
        v=[(a[0]-nx,a[1]-ny,a[2]+height),(b[0]-nx,b[1]-ny,b[2]+height),
           (b[0]+nx,b[1]+ny,b[2]+height),(a[0]+nx,a[1]+ny,a[2]+height)]
        faces=[(0,1,2,3)];v += [(x,y,z-height) for x,y,z in v]
        faces += [(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        G.mesh('SM_MPRLG_LandscapeCurb',f['role'],v,faces)
solid=plan['curb_solid'];name='SM_MPRLG_LandscapeCurb';role=solid['role'];height=solid['height_m']
for tri in solid['bottom_triangles_m']:
    top=[(x,y,z+height) for x,y,z in tri]
    G.mesh(name,role,top+tri,[(0,1,2),(5,4,3)])
for ring in solid['boundary_loops_m']:
    for a,b in zip(ring,ring[1:]):
        G.mesh(name,role,[a,b,(b[0],b[1],b[2]+height),(a[0],a[1],a[2]+height)],[(0,1,2,3)])
bpy.context.preferences.filepaths.save_version=0
manifest=G.export(OUT,'MPR_LandscapeGround',dict(map=plan['map'],namespace=plan['namespace'],
                   plan_sha256=hashlib.sha256((OUT/'plan.json').read_bytes()).hexdigest(),
                   source_hashes=plan['source_hashes'],mesh_mappings=plan['mesh_mappings'],
                   new_actors=0,replace_mesh_references_only=True))
for row in manifest['meshes']:
    row.update(sha256=hashlib.sha256((ROOT/row['fbx']).read_bytes()).hexdigest(),
               category='Site',full_precision_uvs=True)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('LANDSCAPE_GROUND_EXPORTED',len(manifest['meshes']),flush=True)
