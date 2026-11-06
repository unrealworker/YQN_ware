"""Validate retained CAD evidence and module placement contracts."""
import json,pathlib,math,collections
from mpr_cad_semantics import DRAFTING_SYMBOLS,turn_requires_reflection
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
symbols=d.get('drafting_symbols',[])
symbol_handles={h for row in symbols for h in row['source_handles']}
drive_handles={h for row in op['merged_drive_units'] for h in row['source_handles']}
assert len(op['merged_drive_units'])==9
assert collections.Counter(row['block'] for row in symbols)=={'terwrq434':164,'*U257':3,'*U1667':6}
assert all(row['block'] not in DRAFTING_SYMBOLS for row in d['equipment'])
for row in op['instances']:
 assert row['mesh'] in meshes or row['mesh'].startswith('/Game/')
 assert len(row['position_m'])==3
 assert all(math.isfinite(v) for v in row['position_m']+row['scale'])
 assert all(v>0 for v in row['scale'])
 assert row['collision'] is False and row['tick'] is False
 assert row['source_handles']
 assert not symbol_handles.intersection(row['source_handles']),'A drafting symbol was generated as physical equipment'
 assert not drive_handles.intersection(row['source_handles']),'A drive detail duplicated an existing transport deck'
 assert row['mesh']!='SM_MPR_StationChute','Personnel silhouettes must not become ramps'
 duplicates[(row['mesh'],tuple(round(v,3) for v in row['position_m']),round(row['rotation_deg'],2))]+=1
turns=[v for v in d['equipment'] if v['block']=='*U33']
reference=next(v for v in turns if v['source_handles']==['2CB2DE'])
for v in turns:
 matches=[r for r in op['instances'] if r['source_handles']==v['source_handles']]
 assert len(matches)==1
 assert matches[0]['mesh']==('SM_MPR_Turn__U33_Reflected' if turn_requires_reflection(reference,v) else 'SM_MPR_Turn__U33')
feed_evidence=json.loads((SRC/'operations/cad_loose_feed_geometry.json').read_text(encoding='utf8'))
assert op['recovered_loose_feeds']==feed_evidence['feeds']
for feed in feed_evidence['feeds']:
 matches=[r for r in op['instances'] if r['source_handles']==feed['source_handles']]
 assert len(matches)==1 and matches[0]['mesh'].startswith('SM_MPR_CADFeed'),feed['id']
 assert matches[0]['height_basis']==feed['height_policy']
report={'source_racks':len(d['racks']),'source_columns':len(d['columns']),'dock_doors':72,'drive_in_doors':2,'module_count':len(meshes),'module_triangles':sum(m['triangles'] for m in meshes.values()),'operation_instances':len(op['instances']),'additional_measured_pallets':len(op['additional_pallet_positions']),'duplicate_identical_mesh_poses':[{'mesh':k[0],'position':k[1],'count':v} for k,v in duplicates.items() if v>1],'reserved_zones':len(op['reserved_zones']),'unmodeled_components':len(op['unmodeled_components']),'notes':['CAD layout checks do not prove runtime performance or final scene rendering.','Equipment height and some simplified silhouette details are visual estimates.']}
(SRC/'operations/verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
