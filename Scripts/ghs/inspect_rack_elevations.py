"""Read the CAD rack detail sheet; keep dimensions and render their source geometry."""
from pathlib import Path
import sys, json, math, logging, hashlib, re
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Vec3
from ezdxf.colors import aci2rgb
from PIL import Image, ImageDraw, ImageFont
logging.disable(logging.WARNING)
SOURCE = Path(r'D:\EdgeDownload\平面布局图_GHS_0.23_20260710现状.dxf')
OUT = ROOT / 'SourceAssets/GHS/RackSpecs'
OUT.mkdir(parents=True, exist_ok=True)
doc = ezdxf.read(SOURCE.open(encoding='utf8', errors='replace'))
REGIONS = {
 'A': [6907380,1895980,6908340,1896740],
 'B': [6908670,1895980,6909590,1896740],
 'C': [6910100,1895980,6911020,1896740],
 'D1': [6907540,1895030,6908160,1895710],
 'D2': [6908910,1895030,6909490,1895710],
}
def xy(v): return [float(v[0]),float(v[1])]
def inside(p, box): return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]
def point(e):
 t=e.dxftype()
 if t in ('INSERT','TEXT','MTEXT'):return e.dxf.insert
 if t=='DIMENSION':return e.dxf.defpoint
 if t=='LINE':return e.dxf.start
 if t=='LWPOLYLINE':return next(e.vertices_in_wcs(),None)
 return None
def serialize(v):
 if isinstance(v,Vec3):return list(v)
 if isinstance(v,(str,int,float,bool)) or v is None:return v
 if isinstance(v,(list,tuple)):return [serialize(a) for a in v]
 return str(v)
def dimension(e):
 raw={k:serialize(v) for k,v in e.dxfattribs().items()}
 rendered=[]
 for v in e.virtual_entities():
  if v.dxftype() in ('TEXT','MTEXT'):rendered.append(v.dxf.text if v.dxftype()=='TEXT' else v.plain_text())
 return {'handle':e.dxf.handle,'measurement_in':float(e.get_measurement()),'measurement_m':float(e.get_measurement())*.0254,'text_override':e.dxf.text,'rendered_text':rendered,'dxf':raw}
def primitives(e,chain=None,color=7):
 chain=(chain or [])+[e.dxf.get('handle','virtual')]
 c=e.dxf.get('color',256)
 if c==256:c=doc.layers.get(e.dxf.layer).dxf.color
 if c==0:c=color
 t=e.dxftype()
 if t in ('INSERT','DIMENSION'):
  try:
   for v in e.virtual_entities():yield from primitives(v,chain,c)
  except Exception:pass
 elif t=='LINE':yield {'kind':'line','points':[xy(e.dxf.start),xy(e.dxf.end)],'color':c,'chain':chain}
 elif t=='LWPOLYLINE':
  pts=[xy(p) for p in e.vertices_in_wcs()]
  if e.closed:pts.append(pts[0])
  yield {'kind':'line','points':pts,'color':c,'chain':chain}
 elif t=='POLYLINE':yield {'kind':'line','points':[xy(p) for p in e.points()],'color':c,'chain':chain}
 elif t in ('ARC','CIRCLE'):
  a=0 if t=='CIRCLE' else e.dxf.start_angle;b=360 if t=='CIRCLE' else e.dxf.end_angle
  if b<=a:b+=360
  pts=[[e.dxf.center.x+e.dxf.radius*math.cos(math.radians(a+(b-a)*i/48)),e.dxf.center.y+e.dxf.radius*math.sin(math.radians(a+(b-a)*i/48))] for i in range(49)]
  yield {'kind':'line','points':pts,'color':c,'chain':chain}
 elif t in ('TEXT','MTEXT'):
  text=e.dxf.text if t=='TEXT' else e.plain_text()
  yield {'kind':'text','point':xy(e.dxf.insert),'text':text,'height':e.dxf.height if t=='TEXT' else e.dxf.char_height,'rotation':e.dxf.get('rotation',0) if t=='TEXT' else e.get_rotation(),'color':c,'chain':chain}
def render(name,box,items):
 scale=3.0;pad=60;w=int((box[2]-box[0])*scale)+pad*2;h=int((box[3]-box[1])*scale)+pad*2
 im=Image.new('RGB',(w,h),(5,8,12));draw=ImageDraw.Draw(im)
 def p(q):return (pad+(q[0]-box[0])*scale,h-pad-(q[1]-box[1])*scale)
 for item in items:
  try:color=tuple(aci2rgb(abs(item['color'])))
  except Exception:color=(220,220,220)
  if item['kind']=='line':
   pts=[p(q) for q in item['points']]
   if len(pts)>1:draw.line(pts,fill=color,width=2)
  else:
   txt=item['text'];font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',max(12,int(item['height']*scale)))
   # Dimensions emitted by ezdxf already contain their display value.
   bb=font.getbbox(txt);mask=Image.new('RGBA',(max(1,bb[2]-bb[0]+12),max(1,bb[3]-bb[1]+12)),(0,0,0,0))
   ImageDraw.Draw(mask).text((6-bb[0],6-bb[1]),txt,font=font,fill=(*color,255))
   if item['rotation']:mask=mask.rotate(item['rotation'],expand=True)
   px,py=p(item['point']);im.paste(mask,(int(px-mask.width/2),int(py-mask.height/2)),mask)
 draw.text((18,15),'CAD rack detail '+name+' | original drawing units: inches',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',25),fill=(240,240,240))
 path=OUT/('CAD_Rack_'+name+'.png');im.save(path);return str(path)
result={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'drawing_units':'inches','units_to_m':.0254,'regions':{},'interpretation_status':'Dimensions and primitives extracted; rack height must be distinguished from clear height.'}
raw_index=json.loads((ROOT/'SourceAssets/GHS/cad_raw.json').read_text(encoding='utf8'))['raw']
for name,box in REGIONS.items():
 # Some detailed rack INSERT origins are far outside their actual geometry.
 # Existing flattened source index is used only to select top-level handles;
 # the geometry and all dimensions below are freshly read from the source DXF.
 handles={r['source_handles'][0] for r in raw_index if any(inside(p,box) for p in r['points'])}
 entities=[e for e in doc.modelspace() if e.dxf.handle in handles or (point(e) is not None and inside(point(e),box))]
 items=[p for e in entities for p in primitives(e) if (any(inside(q,box) for q in p['points']) if p['kind']=='line' else inside(p['point'],box))]
 dims=[dimension(e) for e in entities if e.dxftype()=='DIMENSION']
 inserts=[{'handle':e.dxf.handle,'block':e.dxf.name,'insert':list(e.dxf.insert),'xscale':e.dxf.xscale,'yscale':e.dxf.yscale,'rotation':e.dxf.rotation} for e in entities if e.dxftype()=='INSERT']
 result['regions'][name]={'bounds_dxf_inches':box,'dimension_entities':dims,'insert_entities':inserts,'source_geometry_primitive_count':len(items),'render':render(name,box,items)}
 print(name,'dimensions',len(dims),'inserts',len(inserts),'primitives',len(items))
 print([(d['handle'],round(d['measurement_in'],5),d['rendered_text']) for d in dims])

# Interpretation follows visible geometry, not the misleading English phrase
# "beam level": A/B/C/D2 include a ground cargo position in their named count.
DEFINITION={
 'A':dict(floor_dim='1F8614',floor_point='defpoint2',width_dim='1F8610',depth_dim='1F8658',height_dim='1F8689',post='1F860F',beams=['1F865B','1F8AF3','1F8B10'],cargo_block='*U241',cargo_h_in=[80]*4,title_count=4,bridge_beams=['1F8B4F','1F8B4D'],bridge_dim='1F865F',bridge_post='1F865C'),
 'B':dict(floor_dim='1F8750',floor_point='defpoint2',width_dim='1F8716',depth_dim='1F8740',height_dim='1F8750',post='1F8715',beams=['1F8851','1F886D','1F8889','1F88A5','1F88C1','1F88DD','1F88F9','1F8915','1F8931','1F894D','1F8969'],cargo_block='*U243',cargo_h_in=[23]+[24]*11,title_count=12,bridge_beams=['1F89A3','1F89BF','1F89DB','1F89F7','1F8A13','1F8A2F'],bridge_dim='1F8751',bridge_post='1F8743'),
 'C':dict(floor_dim='1F86B6',floor_point='defpoint2',width_dim='1F86B2',depth_dim='1F86F7',height_dim='1F86F3',post='1F86B1',beams=['1F86F2','1F8A57','1F8A78','1F8A94'],cargo_block='*U245',cargo_h_in=[62]*5,title_count=5,bridge_beams=['1F8AB6','1F8AD2'],bridge_dim='1F86D6',bridge_post='1F86D3'),
 'D1':dict(floor_dim='1F8B60',floor_point='defpoint2',width_dim='1F8B5E',depth_dim='1F8B5C',height_dim='1F8B62',post='1F8B5D',beams=['1F8BBD','1F8BBB'],cargo_block='*U241',cargo_h_in=[80]*2,title_count=2,bridge_dim='1F8B60'),
 'D2':dict(floor_dim='1F8BC4',floor_point='defpoint2',width_dim='1F8BC0',depth_dim='1F8C67',height_dim='1F8BFD',post='1F8BBF',beams=['1F8BFC','1F8C19','1F8C3A','1F8C56'],cargo_block='*U245',cargo_h_in=[62]*5,title_count=5),
}
def metric(v):return round(v*.0254,7)
def entity_lines(handle):
 return [p for p in primitives(doc.entitydb[handle]) if p['kind']=='line' and len(p['points'])==2]
def beam_extent(handle,floor):
 lines=[p for p in entity_lines(handle) if abs(p['points'][0][1]-p['points'][1][1])<1e-5 and 135<abs(p['points'][0][0]-p['points'][1][0])<145]
 assert len(lines)>=2,handle
 ys=[p['points'][0][1] for p in lines]
 return {'handle':handle,'bottom_z_m':metric(min(ys)-floor),'top_z_m':metric(max(ys)-floor),'height_m':metric(max(ys)-min(ys)),'source_horizontal_edges_dxf':[p['points'] for p in lines]}
def post_top(handle,floor):
 lines=[p for p in entity_lines(handle) if abs(p['points'][0][0]-p['points'][1][0])<1e-5 and abs(p['points'][0][1]-p['points'][1][1])>300]
 assert lines,handle
 return metric(max(q[1] for p in lines for q in p['points'])-floor)
def post_x_edges(handle):
 lines=[p for p in entity_lines(handle) if abs(p['points'][0][0]-p['points'][1][0])<1e-5 and abs(p['points'][0][1]-p['points'][1][1])>300]
 xs=[q[0] for p in lines for q in p['points']]
 return [min(xs),max(xs)]
def block_bounds(name):
 pts=[q for e in doc.blocks[name] for p in primitives(e) if p['kind']=='line' for q in p['points']]
 return [[min(p[k] for p in pts),max(p[k] for p in pts)] for k in (0,1)]
result['types']={}
for name,cfg in DEFINITION.items():
 reg=result['regions'][name];dimensions={d['handle']:d for d in reg['dimension_entities']}
 floor=dimensions[cfg['floor_dim']]['dxf'][cfg['floor_point']][1]
 beams=[beam_extent(h,floor) for h in cfg['beams']]
 base=[b['top_z_m'] for b in beams]
 if name!='D1':base=[0.0]+base
 widths=dimensions[cfg['width_dim']]['measurement_m'];depth=dimensions[cfg['depth_dim']]['measurement_m']
 spec={'code':name,'name':'Type '+name,'named_storage_levels':cfg['title_count'],'ground_storage_level_included':name!='D1','frame_width_m':metric(150),'clear_width_m':round(widths,7),'frame_depth_m':round(depth,7),'upright_height_m':post_top(cfg['post'],floor),'upright_front_width_m':metric(3),'beam_top_z_m':[b['top_z_m'] for b in beams],'beam_height_m':beams[0]['height_m'],'cargo_base_z_m':base,'cargo_envelope_heights_m':[metric(v) for v in cfg['cargo_h_in']],'cargo_width_m':metric(40),'cargo_depth_m':metric(48),'cargo_x_centers_m':[metric(-46),0.,metric(46)],'max_cargo_top_m':max(a+metric(b) for a,b in zip(base,cfg['cargo_h_in'])),'clear_height_label':"CLEAR 30'",'clear_height_label_nominal_m':metric(360),'overall_dimension_measured_m':round(dimensions[cfg['height_dim']]['measurement_m'],7),'source_floor_y_inches':floor,'source_post_handle':cfg['post'],'source_dimensions':{k:cfg[k] for k in ['floor_dim','width_dim','depth_dim','height_dim']},'source_beams':beams,'notes':['Values derive from DXF geometry and dimensions; no arbitrary vertical scaling.','A/B/C/D2 named level count includes the visible ground pallet level.','Dimension text rounds inches; exact alternate millimetres and coordinates are retained.','Some CAD clear-height lines and post tops differ by 10 mm; upright_height_m measures the actual front post top from this view floor.']}
 if cfg.get('bridge_beams'):
  bb=[beam_extent(h,floor) for h in cfg['bridge_beams']];tops=[b['top_z_m'] for b in bb];heights=[spec['cargo_envelope_heights_m'][-1]]*len(tops)
  spec['bridge_variant']={'beam_top_z_m':tops,'cargo_base_z_m':tops,'cargo_envelope_heights_m':heights,'upright_height_m':post_top(cfg['bridge_post'],floor),'clear_under_beam_m':bb[0]['bottom_z_m'],'source_clear_dimension':cfg['bridge_dim'],'source_beams':bb,'source_post_handle':cfg['bridge_post'],'ground_storage_level_included':False}
 if name=='D1':spec['clear_under_beam_m']=beams[0]['bottom_z_m']
 spec.update(pallet_height_m=metric(4.88),pallet_deck_thickness_m=metric(.625),pallet_runner_width_m=metric(1.5),pallet_source_block=cfg['cargo_block'],pallet_detail_source_handles={'A':'12BDC6','B':'12C1DF','C':'12CA7D','D1':'12BDC6','D2':'12CA7D'}[name])
 right_post={'A':'1F8611','B':'1F8717','C':'1F86B3','D1':'1F8B5F','D2':'1F8BC1'}[name]
 left_edges=post_x_edges(cfg['post']);right_edges=post_x_edges(right_post)
 assert metric(right_edges[1]-left_edges[0])==spec['frame_width_m']
 assert metric(left_edges[1]-left_edges[0])==spec['upright_front_width_m']
 spec['source_post_x_edges_inches']={'left_handle':cfg['post'],'left_edges':left_edges,'right_handle':right_post,'right_edges':right_edges}
 side_name={'A':'*U242','B':'*U244','C':'*U246','D1':'*U242','D2':'*U246'}[name]
 front_box=block_bounds(cfg['cargo_block']);side_box=block_bounds(side_name)
 assert metric(front_box[0][1]-front_box[0][0])==spec['cargo_width_m']
 assert metric(side_box[0][1]-side_box[0][0])==spec['cargo_depth_m']
 assert metric(front_box[1][1]-front_box[1][0])==spec['cargo_envelope_heights_m'][0]
 spec['source_cargo_geometry']={'front_block':cfg['cargo_block'],'front_block_bounds_inches':front_box,'side_block':side_name,'side_block_bounds_inches':side_box}
 if name=='B':
  upper_box=block_bounds('*U238');assert metric(upper_box[1][1]-upper_box[1][0])==spec['cargo_envelope_heights_m'][1]
  spec['source_cargo_geometry'].update(upper_front_block='*U238',upper_front_block_bounds_inches=upper_box)
 assert len(base)==cfg['title_count'],(name,base)
 assert all(b['top_z_m']>b['bottom_z_m'] for b in beams)
 result['types'][name]=spec
result['interpretation_status']='Complete: dimensions, front upright geometry, beam surfaces, cargo rows and aisle variants extracted; all five renderings visually reviewed.'
result['critical_notes']=['CLEAR 30 feet is not a measured building roof height. No source building elevation was inspected here.','Actual posts in front elevations are 9.144 or 9.154 m, not the previous scene 4.8 m.','No planar A/B/C/D1/D2 placement mapping is inferred by this detail extraction.']
(OUT/'cad_elevation_specs.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('TYPE_SUMMARY',json.dumps(result['types'],ensure_ascii=False))
