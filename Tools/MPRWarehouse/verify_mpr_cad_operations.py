"""Validate retained CAD evidence and module placement contracts."""
import json,pathlib,math,collections
ROOT=pathlib.Path(__file__).resolve().parents[2];SRC=ROOT/'SourceAssets/MPR'
d=json.loads((SRC/'mpr_cad_layout.json').read_text(encoding='utf8'))
op=json.loads((SRC/'operations/instances.json').read_text(encoding='utf8'))
manifest=json.loads((SRC/'operations/mpr_operations.json').read_text(encoding='utf8'))
meshes={m['name']:m for m in manifest['meshes']}
assert len(d['racks'])==2867 and len(d['columns'])==164
assert len(d['dock_doors'])==72 and len(d['drive_in_doors'])==2
assert abs(d['footprint_area_m2']-607400*.09290304)<100
for m in meshes.values():
 assert (ROOT/m['fbx']).is_file()
 assert 0<m['triangles']<1800
 assert len(m['material_roles'])<=6
 assert m['instance_only']
duplicates=collections.Counter()
for row in op['instances']:
 assert row['mesh'] in meshes or row['mesh'].startswith('/Game/')
 assert len(row['position_m'])==3
 assert all(math.isfinite(v) for v in row['position_m']+row['scale'])
 assert all(v>0 for v in row['scale'])
 assert row['collision'] is False and row['tick'] is False
 assert row['source_handles']
 duplicates[(row['mesh'],tuple(round(v,3) for v in row['position_m']),round(row['rotation_deg'],2))]+=1
report={'source_racks':len(d['racks']),'source_columns':len(d['columns']),'dock_doors':72,'drive_in_doors':2,'module_count':len(meshes),'module_triangles':sum(m['triangles'] for m in meshes.values()),'operation_instances':len(op['instances']),'additional_measured_pallets':len(op['additional_pallet_positions']),'duplicate_identical_mesh_poses':[{'mesh':k[0],'position':k[1],'count':v} for k,v in duplicates.items() if v>1],'reserved_zones':len(op['reserved_zones']),'unmodeled_components':len(op['unmodeled_components']),'notes':['CAD layout checks do not prove runtime performance or final scene rendering.','Equipment height and some simplified silhouette details are visual estimates.']}
(SRC/'operations/verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
