"""Export original green triangles plus the two scoped green extensions."""
from pathlib import Path
import hashlib
import json
import sys
import bpy

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_blender_common import Geometry
OUT=ROOT/'SourceAssets/MPR/green_extension_20261106'
plan=json.loads((OUT/'plan.json').read_text(encoding='utf-8'))
geometry=Geometry()
for surface in plan['surfaces']:
    for triangle in surface['triangles_m']:
        if (triangle[1][0]-triangle[0][0])*(triangle[2][1]-triangle[0][1])-(triangle[1][1]-triangle[0][1])*(triangle[2][0]-triangle[0][0])<0:
            triangle=list(reversed(triangle))
        geometry.mesh(plan['name'],surface['role'],triangle,[(0,1,2)])
bpy.context.preferences.filepaths.save_version=0
manifest=geometry.export(OUT,'MPR_GreenExtension',dict(map=plan['map'],namespace=plan['namespace'],
    plan_sha256=hashlib.sha256((OUT/'plan.json').read_bytes()).hexdigest(),source_hashes=plan['source_hashes'],
    new_actors=0,replace_mesh_references_only=True))
for row in manifest['meshes']:
    row.update(sha256=hashlib.sha256((ROOT/row['fbx']).read_bytes()).hexdigest(),category='Site',full_precision_uvs=True)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('GREEN_EXTENSION_EXPORTED',len(manifest['meshes']),flush=True)
