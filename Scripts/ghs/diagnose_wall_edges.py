import json,math,collections
from pathlib import Path
root=Path('D:/UEPro/Test');d=json.loads((root/'SourceAssets/GHS/cad_layout.json').read_text(encoding='utf8'));r=json.loads((root/'SourceAssets/GHS/ue_scene_registry.json').read_text(encoding='utf8'));print(type(r['groups']),[(g['actor'],g['count']) for g in r['groups'] if 'Wall' in g['actor']]);print([g for g in r['groups'] if g['actor']=='GHS_CAD_WallFaces'][0]['instances'][:1])
w=d['walls'];near=[]
for i,a in enumerate(w):
 for b in w[i+1:]:
  da=[a['points_m'][1][k]-a['points_m'][0][k] for k in (0,1)];db=[b['points_m'][1][k]-b['points_m'][0][k] for k in (0,1)]
  dot=abs(sum(da[k]*db[k] for k in (0,1))/(math.hypot(*da)*math.hypot(*db)))
  dist=min(math.dist(x,y) for x in a['points_m'] for y in b['points_m'])
  if dist<.4:near.append({'a':a['id'],'b':b['id'],'endpoint_gap_m':dist,'parallel_cos':dot,'a_points':a['points_m'],'b_points':b['points_m'],'a_thickness':a['thickness_m'],'b_thickness':b['thickness_m']})
report={'source_wall_mesh_bounds_m':[[-.5,.5],[-.1,.1],[-.5,.5]],'source_wall_mesh_dimensions_m':[1,.2,1],'cube_expected_dimensions_m':[1,1,1],'horizontal_length_formula_equal':True,'wall_skin_top_for_height_2_8_m':2.775,'cap_top_m':2.8,'trim_center_m':2.803,'trim_top_m':2.811,'wall_count':len(w),'independent_top_edge_count':2*len(w),'near_endpoint_pairs':near,'near_endpoint_pair_count':len(near),'nonparallel_near_endpoint_pair_count':sum(x['parallel_cos']<.99 for x in near),'notes':['Source metadata proves no intentional wall-vs-trim horizontal scale mismatch: panel X dimension1m * length and cube1m * length. Live imported mesh bounds must still be checked.','Each segment receives independent endcaps and two full-length offset top strips. No miter, butt-junction clipping, union, shared seam removal or CAD node welding exists.','At L/T joints, independently offset lines cross and overlap rather than following the boundary of wall-volume union.','Wall pairing uses overlap interval endpoints and can shorten measured side lines before centerline conversion, leaving near-connected CAD nodes unjoined.','Wall skins top 25mm below nominal wall height, top cap bridges to h, cyan trim is partly above h. This can accentuate floating edges but does not explain long XY protrusion.']}
(root/'Saved/GHS_WallEdgeDiagnosis.json').write_text(json.dumps(report,indent=2));print('near',len(near),'nonparallel',report['nonparallel_near_endpoint_pair_count']);print(sorted([x for x in near if x['parallel_cos']<.1],key=lambda x:x['endpoint_gap_m'])[:5])

