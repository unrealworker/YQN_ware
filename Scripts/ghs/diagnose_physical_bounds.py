import json,math,collections
D=json.load(open('SourceAssets/GHS/cad_layout.json',encoding='utf8'))
def corners(e):
 x,y=e['position_m'][:2];sx,sy=e['size_m'];r=math.radians(e['rotation_deg']);c,s=math.cos(r),math.sin(r)
 return [(x+a*c-b*s,y+a*s+b*c) for a,b in [(-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2)]]
def intersect(a,b):
 pa,pb=corners(a),corners(b)
 for e in (a,b):
  r=math.radians(e['rotation_deg'])
  for n in [(math.cos(r),math.sin(r)),(-math.sin(r),math.cos(r))]:
   va=[sum(p[i]*n[i] for i in range(2)) for p in pa];vb=[sum(p[i]*n[i] for i in range(2)) for p in pb]
   if min(max(va),max(vb))-max(min(va),min(vb))<.001:return False
 return True
correct={};gidx=collections.defaultdict(list)
for g in D['geometry']:
 if g['source_handles'][-1] in ('3297EB','366DCE','366DCF','366DD0','366DD1'):gidx[tuple(g['source_handles'][:-1])].extend(g['points_m'])
for kind in ['storage','racks']:
 correct[kind]=[]
 for e in D[kind]:
  ps=gidx[tuple(e['source_handles'])];r=math.radians(e['rotation_deg']);c,s=math.cos(r),math.sin(r)
  qs=[(p[0]*c+p[1]*s,-p[0]*s+p[1]*c) for p in ps];lo=[min(p[k] for p in qs) for k in range(2)];hi=[max(p[k] for p in qs) for k in range(2)];mid=[(lo[k]+hi[k])/2 for k in range(2)]
  v=dict(e);v['position_m']=[mid[0]*c-mid[1]*s,mid[0]*s+mid[1]*c];v['size_m']=[hi[k]-lo[k] for k in range(2)];correct[kind].append(v)
report={'counts':{},'collision_pairs':{},'added_column_nearest_base':[]}
base=[c for c in D['columns'] if c['block']!='PILLAR'];extra=[c for c in D['columns'] if c['block']=='PILLAR']
for c in extra:
 near=min(base,key=lambda x:math.dist(c['position_m'],x['position_m']));report['added_column_nearest_base'].append({'added':c['id'],'base':near['id'],'distance_m':math.dist(c['position_m'],near['position_m']),'added_xy':c['position_m'],'base_xy':near['position_m']})
for kind in ['storage','racks']:
 for ver,items in [('original',D[kind]),('physical',correct[kind])]:
  pairs=[]
  for c in D['columns']:
   for e in items:
    if abs(c['position_m'][0]-e['position_m'][0])>4 or abs(c['position_m'][1]-e['position_m'][1])>4:continue
    if intersect(c,e):pairs.append({'column':c['id'],'object':e['id'],'column_xy':c['position_m'],'object_xy':e['position_m'],'column_block':c['block']})
  key=kind+'_'+ver;report['collision_pairs'][key]=pairs;report['counts'][key]=len(pairs)
json.dump(report,open('SourceAssets/GHS/column_overlap_diagnosis.json','w',encoding='utf8'),ensure_ascii=False,indent=2)
json.dump(correct,open('SourceAssets/GHS/physical_bounds_proposed.json','w',encoding='utf8'),ensure_ascii=False,indent=2)
print(report['counts']);print('nearest added columns',report['added_column_nearest_base']);print('physical storage collisions',report['collision_pairs']['storage_physical'][:8]);print('physical rack collisions',report['collision_pairs']['racks_physical'][:8])
