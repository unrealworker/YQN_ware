import json,math,collections
p='SourceAssets/GHS/cad_layout.json';d=json.load(open(p,encoding='utf8'))
d['schema_version']=2
d['coordinate_contract']='position_m is transformed local bounding-box center; size_m is local-axis extent after scale; rotation_deg is world local-X direction. Z ignored for 2D plan because source annotations have arbitrary elevations.'
d['footprint_outline_m']=next(g['points_m'] for g in d['geometry'] if g['source_handles']==['2379D1','4F2C8'])
d['footprint_source_handles']=['2379D1','4F2C8'];d['bounds_m']=[[-239.33385,-76.91981],[226.40055,60.24019]]
# Greedy pairing of same-layer parallel faces with >90% coincident longitudinal coverage.
faces=d['walls'];used=set();walls=[]
for i,w in enumerate(faces):
 if i in used:continue
 a,b=w['points_m'];L=math.dist(a,b);u=[(b[k]-a[k])/L for k in range(2)];n=[-u[1],u[0]];best=None
 for j,v in enumerate(faces):
  if j<=i or j in used or v['layer']!=w['layer']:continue
  c,e=v['points_m'];lv=math.dist(c,e)
  if abs((e[0]-c[0])*n[0]+(e[1]-c[1])*n[1])>.003:continue
  off=sum((c[k]-a[k])*n[k] for k in range(2));dist=abs(off)
  if not .06<=dist<=.5:continue
  lo,hi=sorted(sum((p[k]-a[k])*u[k] for k in range(2)) for p in (c,e));over=max(0,min(L,hi)-max(0,lo))
  if over/min(L,lv)<.9 or abs(L-lv)>.55:continue
  score=dist+abs(L-lv)*.1
  if best is None or score<best[0]:best=(score,j,off,lo,hi)
 w=w.copy();w['height_m']=2.8
 if best:
  _,j,off,lo,hi=best;used.add(j);w['points_m']=[[round(a[k]+u[k]*t+n[k]*off/2,5) for k in range(2)] for t in (max(0,lo),min(L,hi))];w['thickness_m']=round(abs(off),5);w['source_handles']=list(dict.fromkeys(w['source_handles']+faces[j]['source_handles']));w['confidence']=.98;w['note']='Paired parallel CAD faces; measured thickness; estimated cutaway height'
 else:w['confidence']=.65;w['note']='Unpaired CAD wall-face line; 0.15m visual thickness estimated; 2.8m cutaway height'
 walls.append(w)
d['wall_faces_original']=faces;d['walls']=walls
roots={c['source_handles'][0] for c in d['candidates']}
for g in d['geometry']:
 if g['source_handles'][0] in roots and len(g['points_m'])==5:
  ps=g['points_m'][:4];center=[sum(p[k] for p in ps)/4 for k in range(2)];a,b=ps[:2];ang=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]));lens=[math.dist(ps[0],ps[1]),math.dist(ps[1],ps[2])]
  d['chargers'].append({'id':'CH_'+'_'.join(g['source_handles']),'position_m':center,'parking_center_m':center,'size_m':lens,'rotation_deg':ang,'layer':g['layer'],'source_handles':g['source_handles']+['251362'],'confidence':.95,'kind':'charging_bay','dock_point_m':None,'note':'CAD angled 60x120 inch charging bay, not physical charger casing. Charger mounting point/support must be designed; not present in CAD.'})
d['candidates']=[]
for name,items,note in [('RackStorage',d['racks'],'西侧大件货架区；1296顶层块+311嵌套块，均为不同中心'),('FloorPalletStorage',d['storage'],'东侧地堆区；7530个储位'),('ChargingBays',d['chargers'],'东北侧56充电位，7排各8个'),('DockRacking',d['equipment'],'南侧装卸区的87个W_DOCK货架符号')]:
 pts=[x['position_m'] for x in items]
 d['zones'].append({'id':name,'label':name,'notes_zh':note,'bounds_m':[[min(p[k] for p in pts) for k in range(2)],[max(p[k] for p in pts) for k in range(2)]],'confidence':.95})
d['limitations']=['No explicit AGV vehicle or motion-path entity identified; agvs empty.','No conveyor equipment confirmed: layer named 皮带机(蓝) contains annotation texts only. conveyors empty.','56 charging bay centers measured; physical wall mount/charger socket points are absent.','Rack heights and stored load heights are not established by plan; elevations below footprint are separate illustration details.','Grid, future, ceiling, lighting, roof, drain, annotation geometry retained for traceability but not structural construction.','DXF is UTF-8 despite ANSI_936 header; explicit UTF-8 stream required.']
# Tag geometry rather than silently treating all lines as physical.
for g in d['geometry']:
 l=g['layer'].upper();g['physical_candidate']=not any(s in l for s in ['GRID','FUTURE','ROOF','LIGHT','RCL','SOFFIT','DRAIN','RD','REVISION','SKYLIGHT','ABOVE','DIM']) and g['source_handles'][0] not in ('3297A2','3297A3','3297A4')
json.dump(d,open(p,'w',encoding='utf8'),ensure_ascii=False,indent=2)
summary={'counts':{k:len(d[k]) for k in ['walls','wall_faces_original','columns','racks','storage','equipment','doors','chargers','conveyors','agvs']},'paired_walls':sum(w['confidence']>.9 for w in walls),'rack_unique_centers':len(set(tuple(round(v,3) for v in r['position_m']) for r in d['racks'])),'footprint_area_m2':abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(d['footprint_outline_m'],d['footprint_outline_m'][1:])))/2}
json.dump(summary,open('SourceAssets/GHS/cad_validation.json','w'),indent=2);print(summary)
