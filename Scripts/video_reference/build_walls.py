"""Thick editable cutaway walls derived from the warehouse segment specification."""
import ast
import json
import math
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *

root=Path(r'D:\UEPro\Test')
tree=ast.parse((root/'Scripts/build_video_warehouse.py').read_text(encoding='utf-8'))
segments=None
for fn in tree.body:
    if isinstance(fn,ast.FunctionDef) and fn.name=='create_architecture':
        for statement in fn.body:
            if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='segments' for t in statement.targets):
                segments=ast.literal_eval(statement.value)
assert segments and len(segments)==27,'Expected 27 architectural wall segments'

reset()
bpy.context.preferences.filepaths.save_version=0
volume=material('WallVolume',(.026,.13,.28),.55,0,opacity=.40,unlit=True,emission=.5,wall_gradient=True,two_sided=False)
section=material('WallSection',(.035,.105,.15),.55,.1,unlit=True,emission=.65)
trim=material('WallTrim',(.10,.27,.34),.48,.1,unlit=True,emission=.45)
foot=material('WallFootTrim',(.032,.10,.13),.58,0,unlit=True,emission=.16)
metadata={}

for label,a,b in segments:
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    name='SM_VR_Wall_'+label
    collection=begin_asset(name)
    half=length/2
    height=2.8
    thickness=.20
    end=.028
    # Exactly two outward-facing transparent quads. No coincident reverse faces,
    # no nested boxes, no multiplied translucent shell layers.
    x0,x1=-half+end,half-end
    z0,z1=-1.365,1.365
    verts=[(x0,-.10,z0),(x1,-.10,z0),(x1,-.10,z1),(x0,-.10,z1),
           (x0,.10,z0),(x0,.10,z1),(x1,.10,z1),(x1,.10,z0)]
    surfaces=mesh('OutwardFrontAndBack',verts,[(0,1,2,3),(4,5,6,7)],volume)
    assert surfaces.data.polygons[0].normal.y<-.99
    assert surfaces.data.polygons[1].normal.y>.99
    # Full opaque horizontal top section: 20 cm wide, 35 mm overall height.
    # Raised outer trims meet the central slab without coplanar top surfaces.
    box('WideGrayBlueCopingCenter',(0,0,1.3825),(length,.176,.035),section,.003)
    box('CopingLowerFullWidth',(0,0,1.3765),(length,.20,.023),section,.003)
    for side in (-1,1):
        box('UpperInnerOuterEdge',(0,side*.094,1.394),(length,.012,.012),trim,.002)
    box('BottomClosedSection',(0,0,-1.3875),(length,.20,.025),section,.003)
    # Opaque end sections expose true thickness at door openings and wall ends.
    for side in (-1,1):
        box('OpaqueDoorwayEndSection',(side*(half-end/2),0,0),(end,.20,2.8),section,.003)
    # Thin subdued lower edges close the gap between bottom cap and volume faces.
    for side in (-1,1):
        box('LowerSubduedEdge',(0,side*.094,-1.370),(length,.012,.010),foot,.0015)
    collection['wall_label']=label
    collection['length']=length
    collection['thickness']=thickness
    collection['height']=height
    metadata[name]=dict(wall_label=label,length=length,thickness=thickness,height=height,
                        source_start_m=list(a),source_end_m=list(b),
                        origin='centered_xyz; place at UE actor z=140 cm',
                        translucent_faces=2)

save_library('walls')
manifest_path=OUT/'walls.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
for item in manifest['meshes']:
    item['metadata']=metadata[item['name']]
    bounds=item['bounds_m']
    assert abs(bounds[0][0]+metadata[item['name']]['length']/2)<.0001
    assert abs(bounds[0][1]-metadata[item['name']]['length']/2)<.0001
    assert abs(bounds[1][0]+.10)<.0001 and abs(bounds[1][1]-.10)<.0001
    assert abs(bounds[2][0]+1.4)<.0001 and abs(bounds[2][1]-1.4)<.0001
manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('WALL_LIBRARY_VERIFIED',len(manifest['meshes']),'meshes',
      sum(item['polygons'] for item in manifest['meshes']),'polygons total; all 0.20 m thick x 2.8 m high')
