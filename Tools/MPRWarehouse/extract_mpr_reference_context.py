"""Reference-only pixel-domain roof inventory; no CAD or Unreal mutations.

Neutral bright roof components are inspected against the supplied overall.
The detected outlines are image evidence, not a surveyed building footprint.
Heights and hidden facades are explicitly estimated for the reference rebuild.
"""
from pathlib import Path
import json
import math
import hashlib
import itertools
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_NAME = 'ChatGPT 图像 2026年11月2日 15_56_24.png'
LOCAL_REFERENCE = ROOT/'SourceAssets/MPR/reference_v4/references'/REFERENCE_NAME
SOURCE = LOCAL_REFERENCE if LOCAL_REFERENCE.is_file() else Path(r'D:/CodexTemp/output/imagegen/industrial-saas/multiview')/REFERENCE_NAME
OUT = ROOT/'SourceAssets/MPR/reference_v4/context'


def hull(points):
    points = sorted(set(points))
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower, upper = [], []
    for p in points:
        while len(lower)>1 and cross(lower[-2], lower[-1], p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>1 and cross(upper[-2], upper[-1], p)<=0:upper.pop()
        upper.append(p)
    return lower[:-1]+upper[:-1]


def components(mask):
    seen=np.zeros(mask.shape,dtype=bool);rows=[];height,width=mask.shape
    for y,x in zip(*np.where(mask)):
        if seen[y,x]:continue
        queue=[(int(x),int(y))];seen[y,x]=True;points=[]
        while queue:
            px,py=queue.pop();points.append((px,py))
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                a,b=px+dx,py+dy
                if 0<=a<width and 0<=b<height and mask[b,a] and not seen[b,a]:seen[b,a]=True;queue.append((a,b))
        rows.append(points)
    return rows


def rectangle(poly):
    pts=np.asarray(poly,dtype=float);best=None
    for a,b in zip(poly,poly[1:]+poly[:1]):
        angle=math.atan2(b[1]-a[1],b[0]-a[0]);c,s=math.cos(angle),math.sin(angle)
        rotation=np.array([[c,s],[-s,c]]);local=pts@rotation.T;lo=local.min(axis=0);hi=local.max(axis=0)
        area=float(np.prod(hi-lo))
        if best is None or area<best[0]:
            corners=np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]])@rotation
            best=area,corners.tolist(),[float(v) for v in hi-lo],angle
    return best


def roof_quad(poly):
    """Largest quadrilateral INSIDE the actual roof hull, not its empty bbox."""
    best=None
    for indices in itertools.combinations(range(len(poly)),4):
        q=[poly[i] for i in indices]
        area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(q,q[1:]+q[:1])))/2
        if best is None or area>best[0]:best=(area,q)
    return best[1]


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    im=Image.open(SOURCE).convert('RGB');a=np.asarray(im).astype(int);y,x=np.indices(a.shape[:2])
    # The visible housing strip narrows toward the bottom. This hand-checked
    # boundary excludes the main campus roads/parking and large neighbor.
    right=np.interp(y,[0,150,350,500,650,800,910],[430,400,365,330,300,295,295])
    mask=(x<right)&(a.min(axis=2)>=198)&(a[:,:,2]>=a[:,:,1]-5)&(a[:,:,0]>=a[:,:,1]-4)
    rows=[]
    for pts in components(mask):
        if not 55<=len(pts)<=2600:continue
        p=hull(pts)
        if len(p)<3:continue
        area,corners,size,angle=rectangle(p)
        if min(size)<5 or max(size)>85 or max(size)/min(size)>4.0:continue
        center=np.mean(pts,axis=0).tolist()
        q=roof_quad(p)
        rows.append(dict(id='',type='house_gable',pixel_outline=[[round(v,2) for v in p] for p in q],
                         visible_roof_hull_px=p,pixel_roof_center=[round(v,2) for v in center],
                         pixel_size=[round(v,2) for v in size],pixel_long_edge_angle_deg=round(math.degrees(angle),2),
                         estimated_height_m=6.4 if area>800 else 5.6,visible_roof_pixels=len(pts),
                         confidence='segmented bright neutral roof; manually review overlay',
                         geometry_origin='reference image roof, not CAD footprint'))
    rows.sort(key=lambda r:(int(r['pixel_roof_center'][1]/100),r['pixel_roof_center'][0]))
    for i,r in enumerate(rows):r['id']='house_%03d'%(i+1)
    # Pixel overlay review: these narrow neutral pieces are driveway/porch
    # fragments of an already-counted building, not additional houses.
    rejected={'house_%03d'%i for i in (49,57,86,97,99,101,114,123,127,137)}
    rows=[r for r in rows if r['id'] not in rejected]
    for row in rows:
        row['confidence']='roof component visually checked against reference overlay'
        if row['id'] in {'house_084','house_085','house_100','house_116'}:
            row.update(type='flat_industrial',estimated_height_m=7.0)
    # The five longest connected bright components contain attached/adjacent
    # roof pairs. Split along their long screen axis to keep separate ridges.
    split_ids={'house_001','house_002','house_070','house_091','house_095'}
    refined=[]
    for row in rows:
        if row['id'] not in split_ids:refined.append(row);continue
        q=row['pixel_outline']
        if math.dist(q[0],q[1])<math.dist(q[1],q[2]):q=q[1:]+q[:1]
        lerp=lambda a,b,t:[a[i]*(1-t)+b[i]*t for i in (0,1)]
        for suffix,(t0,t1) in [('a',(0,.47)),('b',(.53,1))]:
            part=dict(row);part['id']=row['id']+'_'+suffix
            part['pixel_outline']=[lerp(q[0],q[1],t0),lerp(q[0],q[1],t1),lerp(q[3],q[2],t1),lerp(q[3],q[2],t0)]
            part['pixel_roof_center']=np.mean(part['pixel_outline'],axis=0).tolist();part['confidence']='manually separated adjacent roofs within one bright connected component'
            refined.append(part)
    rows=refined
    # Shaded roofs missed by the brightness segmentation are explicitly traced.
    for identifier,points in [('house_manual_01',[[254,650],[272,642],[283,654],[265,673]]),
                              ('house_manual_02',[[251,758],[280,758],[282,777],[253,777]])]:
        rows.append(dict(id=identifier,type='house_gable',pixel_outline=points,
                         pixel_roof_center=np.mean(points,axis=0).tolist(),estimated_height_m=5.6,
                         confidence='manual roof trace; shaded surface below segmentation threshold',geometry_origin='reference image roof'))
    # Large context roofs are explicitly traced, including the visible roof's
    # top plane. Heights allow the camera calibration to back-project correctly.
    large=[
      dict(id='neighbor_warehouse',type='warehouse_deep_docks',pixel_outline=[[469,137],[1090,137],[1116,261],[447,261]],estimated_height_m=30.0,
           height_basis='visual reconstruction: calibrated reference roof edge y261 and wall foot y295; not surveyed height',
           dock_facade_pixel_edge=[[447,261],[1116,261]],dock_count=28,roof_node_columns=7,roof_node_rows=2),
      dict(id='north_office_warehouse',type='flat_industrial',pixel_outline=[[990,7],[1174,8],[1199,99],[1003,99]],estimated_height_m=12.0),
      dict(id='northwest_industrial',type='flat_industrial',pixel_outline=[[487,49],[568,49],[554,101],[475,102]],estimated_height_m=7.0),
      dict(id='northwest_cropped_industrial',type='flat_industrial',pixel_outline=[[518,0],[601,0],[594,30],[508,30]],estimated_height_m=8.0),
      dict(id='east_industrial',type='flat_industrial',pixel_outline=[[1598,463],[1728,418],[1728,569],[1644,584]],estimated_height_m=10.5),
      dict(id='rail_service_shed_01',type='sawtooth_industrial',pixel_outline=[[1123,793],[1175,770],[1204,800],[1152,827]],estimated_height_m=5.2),
      dict(id='rail_service_shed_02',type='sawtooth_industrial',pixel_outline=[[1196,749],[1231,732],[1259,758],[1223,779]],estimated_height_m=5.2),
      dict(id='rail_service_shed_03',type='sawtooth_industrial',pixel_outline=[[1251,719],[1284,704],[1310,730],[1277,748]],estimated_height_m=5.2),
    ]
    tanks=[dict(id='tank_%02d'%i,type='cylindrical_tank',pixel_roof_center=p,pixel_roof_ellipse_radius_px=r,estimated_height_m=h)
           for i,p,r,h in [(1,[1474,631],[46,35],12),(2,[1619,729],[50,40],12),(3,[1507,774],[52,41],12),
                          (4,[1353,829],[51,40],12),(5,[1253,890],[53,39],12),(6,[1719,830],[46,38],12),
                          (7,[1563,883],[23,18],9),(8,[1631,871],[22,18],9)]]
    blocks=[dict(id='left_north',pixel_polygon=[[0,0],[429,0],[396,154],[0,132]],road_alignment='diagonal blocks; traced houses retain independent rotations'),
            dict(id='left_middle',pixel_polygon=[[0,145],[394,190],[351,445],[0,293]],road_alignment='NW-SE / NE-SW diagonal residential grid'),
            dict(id='left_south',pixel_polygon=[[0,309],[329,484],[292,910],[0,910]],road_alignment='curving collector and detached-house loops')]
    streets=[dict(name='HousingStreet_%02d'%(i+1),width_px=w,radius_px=8,points=pts)
             for i,(w,pts) in enumerate([
              (11,[[-25,-8],[164,35],[420,79]]),(14,[[-25,119],[159,156],[388,198]]),
              (13,[[89,-20],[-20,121]]),(13,[[197,-20],[78,139]]),
              (8,[[288,-20],[171,161]]),(6,[[388,-18],[371,15],[360,29],[347,51],[320,97],[290,147],[271,177]]),
              (13,[[103,145],[-20,237]]),(13,[[208,166],[28,305]]),
              (13,[[306,189],[133,329]]),(16,[[-25,255],[123,370],[221,436],[305,477]]),
              (12,[[351,269],[311,288],[228,352],[173,395]]),
              (16,[[-25,610],[110,715],[198,785],[248,804],[298,805]]),
              (12,[[306,558],[270,562],[223,613],[153,679],[99,727]]),
              (13,[[275,695],[227,695],[174,745]]),(13,[[106,735],[16,813],[-20,843]]),
              (10,[[187,814],[118,875],[68,927]]),
             ])]
    tank_pads=[dict(id='tank_upper_pad',outline=[[1378,604],[1448,576],[1580,636],[1598,683],[1434,737],[1341,680]]),
               dict(id='tank_lower_pad',outline=[[1215,787],[1379,714],[1581,685],[1728,744],[1728,910],[1090,910]]),
               dict(id='service_shed_pad',outline=[[1094,821],[1260,710],[1309,718],[1393,799],[1180,910],[1073,897]])]
    tank_pipes=[[[1110,842],[1195,797],[1369,737],[1590,680]],[[1160,909],[1369,830],[1631,747],[1719,688]],
                [[1292,705],[1376,790],[1484,910]],[[1548,696],[1641,797],[1728,877]]]
    data=dict(schema_version=4,source=str(SOURCE),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),image_size=list(im.size),
              coordinate_space='pixel x right, y down; roof points must back-project at estimated roof elevation',
              source_policy='Entire exterior layout follows the approved image. No surrounding CAD position constraint.',
              buildings=rows+large,tanks=tanks,tank_pads=tank_pads,tank_pipes=tank_pipes,neighborhoods=blocks,residential_streets=streets,streets=streets,rejected_fragment_ids=sorted(rejected),
              assumptions=['Roof height, unseen walls/windows/porches and out-of-frame continuation are visual estimates.',
                           'Visible roof outlines are traced/extracted, not randomly scattered. Main interior and assets remain unchanged.'])
    (OUT/'reference_context_layout.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    # Diagnostic overlay, not a modified user design deliverable.
    draw=ImageDraw.Draw(im)
    for row in rows:
        points=[tuple(p) for p in row['pixel_outline']];draw.line(points+[points[0]],fill=(255,70,30),width=1)
        p=row['pixel_roof_center'];draw.text((p[0],p[1]),row['id'][6:],fill=(15,20,230))
    for row in large:draw.line([tuple(p) for p in row['pixel_outline']]+[tuple(row['pixel_outline'][0])],fill=(20,65,255),width=2)
    im.save(OUT/'reference_context_pixel_audit.png')
    print('REFERENCE_CONTEXT_LAYOUT',len(rows),'houses',len(large),'large buildings',len(tanks),'tanks')


if __name__=='__main__':main()
