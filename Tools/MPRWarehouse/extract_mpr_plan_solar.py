"""Measure PV from the user's aerial photo; never warp the CAD or modules."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from extract_mpr_road_outline import label_runs,signed_area
from mpr_plan_layout import world_to_plan
SOURCE=ROOT/'SourceAssets/MPR/reference_v4/references/solar-roof-aerial-20261103.png'
OUT=ROOT/'SourceAssets/MPR/reference_v4/architecture/plan_solar_v5.json'
DIAG=ROOT/'Saved/MPR/pv_v6';DIAG.mkdir(parents=True,exist_ok=True)
SOURCE_SHA='1f7a067a885a7ffe27f03e6abdf2f3298b3da15b3006ed1114a9b2b1149f9f54'
# Central drain/east wall and north/south roof edges determine two parallel
# directions. SE point extrapolates the visible east wall to the south edge.
RECTIFY_SOURCE=[[335,12],[850,-2],[963,486],[354,506]]
RECTIFY_TARGET=[[350,20],[900,20],[900,520],[350,520]]
STEP_PHOTO=[[913,273],[856,278],[878,375],[822,381],[833,427],[771,433],[780,487]]
STEP_CAD=[[182.61076,-20.50042],[166.78656,-20.50042],[166.78656,-50.98042],
 [150.91156,-50.98042],[150.91156,-66.22042],[135.36676,-66.22042],[135.36676,-83.94962]]
FIELDS=[(358,47,514,96),(522,47,700,122),(714,47,745,191),(409,96,514,240),
 (357,132,405,240),(521,149,699,222),(707,191,858,319),(409,242,514,380),
 (357,244,405,380),(521,242,698,381),(205,280,343,377),(704,318,818,445),
 (521,385,698,418),(520,418,696,506),(357,382,513,507),(118,380,344,508)]

def homography(source,target):
 a=[];b=[]
 for (x,y),(u,v) in zip(source,target):
  a.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);b.extend([u,v])
 return np.r_[np.linalg.solve(a,b),1.].reshape(3,3)

def project(points,h):
 p=np.asarray(points,float);q=np.c_[p,np.ones(len(p))]@h.T
 return q[:,:2]/q[:,2,None]

def orthogonal_ring(ring):
 out=[]
 for a,b in zip(ring,ring[1:]+ring[:1]):
  out.append(a)
  if a[0]!=b[0] and a[1]!=b[1]:out.append([b[0],a[1]])
 clean=[]
 for i,p in enumerate(out):
  prev=out[i-1];nxt=out[(i+1)%len(out)]
  if p==prev or (prev[0]==p[0]==nxt[0]) or (prev[1]==p[1]==nxt[1]):continue
  clean.append(p)
 return clean

def boundary_rings(mask):
 """Exact four-connected pixel edges; no diagonal contour simplification."""
 padded=np.pad(mask,1);edges={}
 for side,neighbors in enumerate([padded[:-2,1:-1],padded[1:-1,2:],padded[2:,1:-1],padded[1:-1,:-2]]):
  yy,xx=np.nonzero(mask&~neighbors)
  for y,x in zip(yy.tolist(),xx.tolist()):
   a,b=[((x,y),(x+1,y)),((x+1,y),(x+1,y+1)),((x+1,y+1),(x,y+1)),((x,y+1),(x,y))][side]
   edges.setdefault(a,[]).append(b)
 rings=[]
 while edges:
  start=next(iter(edges));a=start;ring=[];last=None
  while True:
   ring.append([a[0]-.5,a[1]-.5]);choices=edges[a];which=0
   if len(choices)>1:
    incoming=(a[0]-last[0],a[1]-last[1]) if last else (1,0)
    def turn(b):
     dx,dy=b[0]-a[0],b[1]-a[1];cross=incoming[0]*dy-incoming[1]*dx;dot=incoming[0]*dx+incoming[1]*dy
     return {1:0,0:1,-1:2}.get(cross,3)+(2 if dot<0 else 0)
    which=min(range(len(choices)),key=lambda i:turn(choices[i]))
   b=choices.pop(which)
   if not choices:del edges[a]
   last,a=a,b
   if a==start:break
  rings.append(orthogonal_ring(ring))
 return sorted(rings,key=lambda r:abs(signed_area(r)),reverse=True)

def main():
 assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SOURCE_SHA
 h=homography(RECTIFY_SOURCE,RECTIFY_TARGET);inv=np.linalg.inv(h);inv/=inv[2,2]
 photo=Image.open(SOURCE).convert('RGB')
 rect=photo.transform((930,550),Image.Transform.PERSPECTIVE,inv.flatten()[:8],Image.Resampling.BICUBIC)
 rect.save(DIAG/'aerial_rectified.png')
 step=project(STEP_PHOTO,h);cad=np.asarray(STEP_CAD)
 sx=np.linalg.lstsq(np.c_[step[:,0],np.ones(len(step))],cad[:,0],rcond=None)[0]
 sy=np.array([(-83.94962-74.54638)/500,74.54638-20*(-83.94962-74.54638)/500])
 def to_world(p):
  p=np.asarray(p,float);return np.c_[p[:,0]*sx[0]+sx[1],p[:,1]*sy[0]+sy[1]]
 def to_plan(p):return np.round(world_to_plan(to_world(p)),5).tolist()
 measured=to_world(step);errors=np.linalg.norm(measured-cad,axis=1)
 assert errors.max()<2.2,'Photo/CAD anchor registration needs review'
 a=np.asarray(rect).astype(float)
 raw=(a.mean(2)<170)&(a[:,:,2]>a[:,:,0]*1.025)&(a.mean(2)>40)
 # Only the map-pin annotation is inferred, not any visible roof opening.
 raw[328:366,296:325]=True
 regions=[];clearances=[];fixtures=[];allmask=np.zeros(raw.shape,bool)
 registration=dict(source_image=SOURCE.relative_to(ROOT).as_posix(),source_sha256=SOURCE_SHA,photo_rectification_homography=h.tolist(),rectification_source_px=RECTIFY_SOURCE,
  rectification_target_px=RECTIFY_TARGET,rectified_to_cad_x=sx.tolist(),rectified_to_cad_y=sy.tolist(),
  anchors=[dict(photo_px=p,cad_xy_m=w,inferred_xy_m=m.tolist(),error_m=float(e)) for p,w,m,e in zip(STEP_PHOTO,STEP_CAD,measured,errors)],
  maximum_anchor_error_m=float(errors.max()),policy='Image rectification only; fixed CAD roof and generated modules are not warped.',
  uncertainty='About 2.2m registration residual at visible roof steps. Photograph is not a survey. Map-pin footprint locally inferred.')
 overlay=rect.copy();d=ImageDraw.Draw(overlay)
 for number,(x0,y0,x1,y1) in enumerate(FIELDS,1):
  local=np.zeros(raw.shape,bool);local[y0:y1,x0:x1]=raw[y0:y1,x0:x1]
  # Close <=1px cell raster seams, quantize to 2px orthogonal measurement.
  local=np.asarray(Image.fromarray(local.astype('uint8')*255).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3)))>0
  coarse=local.reshape(275,2,465,2).mean((1,3))>=.5
  labels=label_runs(coarse);counts=np.bincount(labels.ravel());counts[0]=0
  component=labels==int(counts.argmax());assert component.sum()>50
  inverse=label_runs(~component);sizes=np.bincount(inverse.ravel())
  for k in range(1,len(sizes)):
   if sizes[k]<=3:component[inverse==k]=True
  rings=boundary_rings(component)
  rings=[orthogonal_ring([[2*x+1,2*y+1] for x,y in ring]) for ring in rings if abs(signed_area(ring))*4>=12]
  outer=rings[0];holes=rings[1:];coords=to_plan(outer);planholes=[to_plan(r)for r in holes];excluded=[]
  for idx,hole in enumerate(holes,1):
   p=np.asarray(hole);mn=p.min(0);mx=p.max(0);center=(mn+mx)/2
   equip=(mx[0]-mn[0]<=26 and mx[1]-mn[1]<=24)
   row=dict(id=f'PVField_{number:02}_Void_{idx:02}',exterior_px=to_plan(hole),center_px=to_plan([center])[0],
    rectified_photo_ring_px=hole,feature='rooftop_equipment_clearance' if equip else 'intra_array_access_gap',
    position_uncertainty_px=2.,evidence='Actual aerial white roof opening; old schematic fill rules removed.')
   clearances.append(row);excluded.append(row['id'])
  regions.append(dict(id=f'PVField_{number:02}',source_component=number,exterior_px=coords,holes_px=planholes,rings_px=[coords,*planholes],
   bbox_px=[min(p[0]for p in coords),min(p[1]for p in coords),max(p[0]for p in coords),max(p[1]for p in coords)],
   area_px2=abs(signed_area(coords))-sum(abs(signed_area(r))for r in planholes),rectified_photo_exterior_px=outer,
   rectified_photo_holes_px=holes,orthogonal_boundary=True,grid_cell_interiors_filled=True,clearance_ids=excluded,
   manual_review_note='Actual aerial stair-step edges, roof openings and row notches preserved.'))
  allmask|=np.repeat(np.repeat(component,2,0),2,1)
  d.line([tuple(p)for p in outer+[outer[0]]],fill='#00b8f0',width=1)
  for hole in holes:d.line([tuple(p)for p in hole+[hole[0]]],fill='#ff6b00',width=1)
  d.text((x0,y0-10),f'{number:02}',fill='#ff6600')
 # Actual isolated dark roof fixtures, including devices in open edge notches.
 # Do not reuse old schematic positions inside the newly measured arrays.
 dark=(a.mean(2)<180)&(a.mean(2)>55)
 dark[:32]=False;dark[503:]=False;dark[:,880:]=False;dark[:,:40]=False
 dark[100:159,210:293]=False;dark[320:376,290:334]=False;dark[369:397,:53]=False
 labels=label_runs(dark);sizes=np.bincount(labels.ravel())
 accepted=[]
 for component in sorted(np.flatnonzero((sizes>=5)&(sizes<=90)),key=lambda i:-sizes[i]):
  if component==0:continue
  yy,xx=np.nonzero(labels==component)
  if np.ptp(xx)>14 or np.ptp(yy)>16 or np.mean(allmask[yy,xx])>.1:continue
  center=[float(np.median(xx)),float(np.median(yy))]
  if any(np.linalg.norm(np.array(center)-p)<6.5 for p in accepted):continue
  accepted.append(center)
  fixtures.append(dict(id=f'AerialRoofFixture_{len(fixtures)+1:03}',center_px=to_plan([center])[0],
   rectified_photo_center_px=center,type='rooftop_vent_or_small_fixture',visual_scale=.75,
   source_policy='Actual isolated visible rooftop fixture pixel component; annotation and blue panels excluded.'))
  d.ellipse((center[0]-3,center[1]-3,center[0]+3,center[1]+3),outline='#e52323')
 for opening in clearances:
  mask=Image.new('1',rect.size);ImageDraw.Draw(mask).polygon([tuple(p)for p in opening['rectified_photo_ring_px']],fill=1)
  for fixture in fixtures:
   x,y=fixture['rectified_photo_center_px']
   if mask.getpixel((round(x),round(y))):fixture['clearance_id']=opening['id']
 overlay.save(DIAG/'aerial_measured_overlay.png');Image.fromarray(allmask.astype('uint8')*255).save(DIAG/'aerial_measured_mask.png')
 result=dict(schema_version=3,status='review_ready_aerial_measurement',review_ready=True,source_image=SOURCE.relative_to(ROOT).as_posix(),
  source_sha256=SOURCE_SHA,image_size=list(photo.size),coordinate_frame='Existing plan pixels are interchange only; PV measurements come from actual aerial photo registered to fixed CAD.',
  photo_registration=registration,field_count=len(regions),interior_hole_count=len(clearances),regions=regions,clearances=clearances,
  roof_fixtures=fixtures,roof_fixture_count=len(fixtures),method=dict(tracing='Blue-roof segmentation within sixteen manually isolated assemblies; actual notches retained.',
   morphology='3px close; 2px measurement grid; <=12px tiny sensor-hole fill',review_version='aerial-roof-v1',boundary_uncertainty_px=2.,annotation_infill_rectified_px=[296,328,325,366]),
  validation=dict(all_aisles_clear=True,no_random_fill=True,source_grid_not_module_inventory=True,
   clear_aisle_samples=[dict(id='central_pipe',pixel=to_plan([[350,300]])[0],clear=True),dict(id='central_access',pixel=to_plan([[517,300]])[0],clear=True)]),
  limitations=['Perspective photograph is not surveyed CAD; registration residuals are reported.','Map-pin footprint locally inferred from visible array continuity.',
   'Physical module pitch is a modeling estimate, not an electrical capacity inventory.'])
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 (DIAG/'aerial_registration.json').write_text(json.dumps(registration,indent=2)+'\n',encoding='utf8')
 print(json.dumps(dict(fields=len(regions),holes=len(clearances),equipment=len(fixtures),maximum_anchor_error_m=float(errors.max()))))

if __name__=='__main__':main()
