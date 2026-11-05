"""Export the CPU-validated site plan with Blender, without loading GEOS."""
import hashlib
import json
import math
import sys
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Tools/MPRWarehouse'))
from mpr_blender_common import Geometry

SRC = ROOT/'SourceAssets/MPR/site_completion_20261105'
plan_path = SRC/'site_plan.json'
plan = json.loads(plan_path.read_text(encoding='utf8'))
G = Geometry()
for surface in plan['surfaces']:
    role = surface['role']
    name = 'SM_MPRSC_'+role
    for tri in surface['triangles_m']:
        assert len(tri) == 3
        if ((tri[1][0]-tri[0][0])*(tri[2][1]-tri[0][1])
                -(tri[1][1]-tri[0][1])*(tri[2][0]-tri[0][0])) < 0:
            tri = list(reversed(tri))
        G.mesh(name, role, tri, [(0, 1, 2)])

for feature in plan['linear_features']:
    points = feature['points_m']
    role = feature['role']
    name = 'SM_MPRSC_'+role
    half = feature['width_m']/2
    height = feature['height_m']
    for a,b in zip(points, points[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        if length < .001:
            continue
        nx,ny=-dy/length*half,dx/length*half
        za=a[2] if len(a)>2 else feature['z_m']
        zb=b[2] if len(b)>2 else feature['z_m']
        verts=[(a[0]-nx,a[1]-ny,za+height),(b[0]-nx,b[1]-ny,zb+height),
               (b[0]+nx,b[1]+ny,zb+height),(a[0]+nx,a[1]+ny,za+height)]
        faces=[(0,1,2,3)]
        if height > 0:
            verts += [(x,y,z-height) for x,y,z in verts]
            faces += [(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        G.mesh(name, role, verts, faces)

bpy.context.preferences.filepaths.save_version=0
manifest=G.export(SRC/'geometry','MPR_SiteCompletion',dict(
    plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
    source_plan=plan_path.relative_to(ROOT).as_posix()))
for row in manifest['meshes']:
    row['sha256']=hashlib.sha256((ROOT/row['fbx']).read_bytes()).hexdigest()
    row['category']='Site'
(SRC/'geometry/manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print('MPR_SITE_EXPORT',len(manifest['meshes']),sum(r['triangles'] for r in manifest['meshes']),flush=True)
