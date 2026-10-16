import json,collections,math
r=json.load(open('SourceAssets/GHS/column_overlap_diagnosis.json',encoding='utf8'));d=json.load(open('SourceAssets/GHS/cad_layout.json',encoding='utf8'))
for k,v in r['collision_pairs'].items():print(k,'pairs',len(v),'objects',len({p['object'] for p in v}),'cols',len({p['column'] for p in v}),'base_pairs',sum(p['column_block']!='PILLAR' for p in v))
print('near duplicate',sum(v['distance_m']<.15 for v in r['added_column_nearest_base']))
for c in d['columns'][:1]:print(c)
reg=json.load(open('SourceAssets/GHS/ue_scene_registry.json',encoding='utf8'));print(reg.keys())
