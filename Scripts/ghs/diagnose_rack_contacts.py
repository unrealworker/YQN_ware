import json,math,collections
r=json.load(open('Saved/GHS_ClearancePlan.json',encoding='utf8'));d=json.load(open('SourceAssets/GHS/clearance_layout.json',encoding='utf8'));idx={e['id']:e for e in d['racks']}
vals=[]
for p in r['after_collision_pairs']:
 a,b=idx[p['a_id']],idx[p['b_id']];over=[(a['size_m'][k]+b['size_m'][k])/2-abs(a['position_m'][k]-b['position_m'][k]) for k in (0,1)];vals.append(min(over))
print('range',min(vals),max(vals));print(collections.Counter(round(x,5) for x in vals).most_common(12));print([p for p,v in zip(r['after_collision_pairs'],vals) if v>.001][:5])
