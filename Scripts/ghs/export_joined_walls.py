"""Export joined wall geometry in background Blender, preserving CAD XY axes."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'Scripts/video_reference'))
import common as c
import bpy
c.OUT=ROOT/'SourceAssets/GHS';c.reset()
g=json.loads((c.OUT/'joined_walls_geometry.json').read_text(encoding='utf8'));specs=json.loads((ROOT/'SourceAssets/VideoReference/walls.json').read_text(encoding='utf8'))['materials'];mats={}
for spec in specs:
 name=spec['name'];mats[name]=c.material(name,spec['base_color'][:3],spec['roughness'],spec['metallic'],**{k:v for k,v in spec.items() if k not in ['name','base_color','roughness','metallic']})
checks={}
for name,mat in [('SM_GHS_JoinedWallFaces','M_VR_WallVolume'),('SM_GHS_JoinedWallSections','M_VR_WallSection'),('SM_GHS_JoinedWallEdges','M_VR_WallTrim')]:
 data=g['meshes'][name];c.begin_asset(name);o=c.mesh(name,data['vertices'],data['faces'],mats[mat]);o['source_wall_count']=330;o['geometry_policy']='Union of exact CAD rectangles; no snapping; only exposed perimeter';o['source_mapping_file']='joined_walls_geometry.json'
 if name.endswith('Faces'):assert all(abs(p.normal.z)<.0001 for p in o.data.polygons)
 if name.endswith('Edges'):assert all(p.normal.z>.99 for p in o.data.polygons)
 if name.endswith('Sections'):assert all(abs(p.normal.z)>.99 for p in o.data.polygons)
 checks[name]={'polygons':len(o.data.polygons),'vertices':len(o.data.vertices),'normal_test_passed':True}
c.save_library('joined_walls')
p=c.OUT/'joined_walls.json';meta=json.loads(p.read_text(encoding='utf8'));meta['geometry_verification']=g['verification'];meta['blender_checks']=checks;meta['coordinate_contract']='CAD XY metres; exported using common.save_library axis_forward=-Y axis_up=Z; UE imports at origin unit scale';p.write_text(json.dumps(meta,indent=2),encoding='utf8')
print('JOINED_WALLS_EXPORT_VERIFIED',json.dumps(checks))
