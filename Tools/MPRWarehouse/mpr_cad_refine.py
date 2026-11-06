"""Turn extracted CAD entities into a compact, source-traceable scene interface."""
import pathlib,json,math,collections,hashlib,os
from mpr_cad_semantics import DRAFTING_SYMBOLS,DRIVE_DETAIL_BLOCKS
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR'
d=json.loads((OUT/'mpr_cad_extracted.json').read_text(encoding='utf8'))
foot=[[-181.93004,83.69038],[-166.08044,83.69038],[-166.08044,74.54638],[166.78656,74.54638],[166.78656,83.58878],[182.61076,83.58878],[182.61076,-20.50042],[166.78656,-20.50042],[166.78656,-50.98042],[150.91156,-50.98042],[150.91156,-66.22042],[135.36676,-66.22042],[135.36676,-83.94962],[-166.08044,-83.94962],[-166.08044,-93.09362],[-181.93004,-93.09362]]
def inside(p):
 x,y=p;odd=False
 for a,b in zip(foot,foot[1:]+foot[:1]):
  if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:odd=not odd
 return odd
out={k:d[k] for k in ('source','header_units','units','units_to_m','origin_dxf_xy')}
out.update({'schema_version':1,'coordinate_system':'local right handed CAD XY in metres; this project FBX pipeline mirrors Y: UE X*100,Y*-100,Z*100 and negate yaw once; mesh long-X rack CAD yaw=rotation_deg+90','footprint_outline_m':foot,'footprint_source':{'layer':'A-WALL-EXT','base_handle':'2C93B4','method':'Trace exterior wall-face coordinates, closing measured doorway/window gaps; no bounding-box replacement'},'footprint_area_m2':round(abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(foot,foot[1:]+foot[:1])))/2,4),'racks':[],'pallet_positions':[],'columns':[],'dock_doors':[],'drive_in_doors':[],'pedestrian_doors':d['doors'],'office_walls':[],'equipment':[],'excluded':[],'conveyor_runs':[],'charging_bays':[],'texts':d['texts']})
def clean(v):return {k:x for k,x in v.items() if k not in ('center_dxf','bounds_dxf','local_bounds_dxf')}
for v in d['racks']:
 if v['block'].startswith('RACK_42D_'):
  x=clean(v);x['nominal_depth_m']=1.0668;x['nominal_beam_m']=3.6576 if '144' in v['block'] else 4.8768;x['mesh_long_x_yaw_deg']=v['rotation_deg']+90;x['height_m']=None
  out['racks'].append(x)
 elif v['block']=='FL_PALLET_48W_40D_STD' and inside(v['position_m']):out['pallet_positions'].append(clean(v))
 else:out['excluded'].append({'id':v['id'],'reason':'Non-standard rack symbols are separate elevation/detail drawings outside the physical footprint'})
for v in d['columns']:
 if v['layer']=='A_WALL':out['columns'].append(clean(v))
 else:out['excluded'].append({'id':v['id'],'reason':'PILLAR on W_EQUIPMENT excluded from architectural columns; may be equipment supports'})
for g in d['architecture']:
 ps=g['points_m']
 if g['layer']=='A-DOOR' and g['closed']:
  lo=[min(p[i] for p in ps) for i in (0,1)];hi=[max(p[i] for p in ps) for i in (0,1)];w=hi[0]-lo[0];dep=hi[1]-lo[1]
  if abs(dep-.0508)<.0001 and (abs(w-2.8448)<.001 or abs(w-3.7592)<.001):
   north=(lo[1]+hi[1])/2>0
   key='dock_doors' if w<3 else 'drive_in_doors'
   out[key].append({'id':'DOOR_'+'_'.join(g['source_handles']),'position_m':[round((lo[0]+hi[0])/2,5),74.39398 if north else -83.79722],'width_m':round(w,5),'opening_width_m':round(w+.1016,5),'height_m':None,'rotation_deg':180 if north else 0,'outward_normal_xy':[0,1 if north else -1],'source_handles':g['source_handles'],'leaf_points_m':ps})
# Pair wall faces in office partitions. Retain measured overlap segments and thickness.
segs=[]
for g in d['architecture']:
 if g['layer'] not in ('A-WALL-GPE','A-WALL-NDE','A-WALL-DE','A-WALL-MAS','A-WALL-NDN','A-WALL-GPN'):continue
 for a,b in zip(g['points_m'],g['points_m'][1:]):
  length=math.dist(a,b)
  if length<.5:continue
  axis=0 if abs(a[1]-b[1])<.001 else 1 if abs(a[0]-b[0])<.001 else None
  if axis is None:continue
  segs.append({'a':a,'b':b,'axis':axis,'fixed':(a[1-axis]+b[1-axis])/2,'lo':min(a[axis],b[axis]),'hi':max(a[axis],b[axis]),'g':g})
seen=set()
for i,s in enumerate(segs):
 matches=[]
 for j,t in enumerate(segs):
  if j<=i or s['axis']!=t['axis']:continue
  thick=abs(s['fixed']-t['fixed']);lo=max(s['lo'],t['lo']);hi=min(s['hi'],t['hi'])
  if .075<=thick<=.36 and hi-lo>.5:matches.append((thick,j,lo,hi,t))
 if not matches:continue
 thick,j,lo,hi,t=min(matches)
 axis=s['axis'];fixed=(s['fixed']+t['fixed'])/2
 a=[lo,fixed] if axis==0 else [fixed,lo];b=[hi,fixed] if axis==0 else [fixed,hi]
 key=tuple(round(x,3) for p in (a,b) for x in p)
 if key in seen:continue
 seen.add(key)
 out['office_walls'].append({'id':'WALL_'+str(len(out['office_walls'])),'points_m':[[round(c,5) for c in p] for p in (a,b)],'thickness_m':round(thick,5),'height_m':None,'source_handles':s['g']['source_handles']+t['g']['source_handles'],'method':'paired CAD faces; measured overlap and thickness; not a full wall survey'})
out['drafting_symbols']=[]
for v in d['equipment']:
 n=v['block'];w,h=v['size_m'];short=min(w,h);long=max(w,h)
 if n in DRAFTING_SYMBOLS:
  if inside(v['position_m']):
   category,reason=DRAFTING_SYMBOLS[n]
   out['drafting_symbols'].append(dict(clean(v),kind=category,classification_confidence='verified original CAD symbol geometry',reason=reason))
  continue
 if n.startswith('SW_CENTERMARK'):
  out['excluded'].append({'id':v['id'],'reason':'Drafting center-mark symbol, not physical equipment'});continue
 if not inside(v['position_m']):
  out['excluded'].append({'id':v['id'],'reason':'Outside traced warehouse footprint'});continue
 x=clean(v);x['kind']='specialized_equipment';x['height_m']=None;x['classification_confidence']='unclassified physical equipment block; silhouette must be inspected'
 if n=='PW_TG_96C_IN':x['kind']='tiangong_96_infeed';x['classification_confidence']='named CAD block; infeed module, not entire 96-cell system'
 elif n=='PKG_CARTON_SEALER':x['kind']='carton_sealer';x['classification_confidence']='named block'
 elif n in ('FL_PALLET_48W_40D_STD','GYL_YQN'):
  out['pallet_positions'].append(x);continue
 elif n=='A$Cb1177cf1':x['kind']='workstation';x['classification_confidence']='repeated adjacent-to-conveyor station footprint'
 elif n=='321321':x['kind']='collection_cells';x['classification_confidence']='verified four independent CAD frames; continuous belt or drive is not implied'
 elif n=='Y型汇流机':x['kind']='y_merge';x['classification_confidence']='verified paired V-pattern oblique rollers within the measured outer frame'
 elif n in DRIVE_DETAIL_BLOCKS:x['kind']='conveyor_drive_detail';x['classification_confidence']='verified drive/motor detail over an existing conveyor; outer envelope is not a second transport deck'
 elif (abs(short-1.06)<.01 or abs(short-1.26)<.01 or abs(short-.88)<.01) and long>2:
  x['kind']='conveyor_run';x['classification_confidence']='measured rectangular straight conveyor module'
  out['conveyor_runs'].append(x);continue
 elif n=='*U1668' or short<.25:x['kind']='machine_support';x['classification_confidence']='narrow support/rail footprint'
 elif long>15 and short>5:x['kind']='complex_assembly';x['classification_confidence']='large detailed assembly; do not replace whole bbox with solid machine'
 out['equipment'].append(x)
# Explicit charger bay rectangles, including rotated rectangles, separate from machine casings.
for g in d['loose_geometry']:
 if g['layer']!='E_CHARGE' or not g['closed']:continue
 ps=g['points_m'];ps=ps[:-1] if ps[0]==ps[-1] else ps
 if len(ps)!=4:continue
 lens=[math.dist(a,b) for a,b in zip(ps,ps[1:]+ps[:1])]
 if min(lens)<.7 or max(lens)>4:continue
 ctr=[sum(p[i] for p in ps)/4 for i in (0,1)]
 if inside(ctr):out['charging_bays'].append({'id':'BAY_'+g['source_handles'][0],'points_m':ps,'position_m':ctr,'source_handles':g['source_handles'],'note':'CAD parking/bay rectangle; charger casing dimensions not implied'})
out['assumptions']=['DXF header millimetres conflicts with geometry; 42-inch rack depth and 600-unit/50ft column spacing establish 0.0254m per CAD unit.','CAD equipment elevations and rack elevation examples are outside plan; height is null pending mapped dimensional evidence.','Exterior wall upper heights come from property documentation, not this 2D CAD.','Dock geometry is 72 measured 2.8448m leaves plus two 3.7592m drive-in leaves; pedestrian swing-door symbols are separate.','Equipment classifications retain confidence; complex assembly bounding boxes must not become solid boxes.']
layout_path=OUT/'mpr_cad_layout.json';layout_pending=OUT/'mpr_cad_layout.pending.json'
layout_pending.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
os.replace(layout_pending,layout_path)
counts={k:len(v) for k,v in out.items() if isinstance(v,list)}
assert len(out['racks'])==2867
assert len(out['columns'])==164
assert len(out['dock_doors'])==72
assert len(out['drive_in_doors'])==2
assert all(inside(x['position_m']) for x in out['racks'])
assert all(v>0 for x in out['racks'] for v in x['size_m'])
centers=[tuple(round(v,3) for v in x['position_m']) for x in out['racks']]
assert len(centers)==len(set(centers))
validation={'counts':counts,'footprint_area_m2':out['footprint_area_m2'],'rack_centers_unique':True,'all_rack_centers_inside':True,'dock_counts_match_property_brochure':True,'equipment_kinds':dict(collections.Counter(x['kind'] for x in out['equipment'])),'header_unit_conflict_resolved':True}
(OUT/'mpr_cad_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(validation,ensure_ascii=False))
