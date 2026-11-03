"""Extract plan-view context footprints; never use perspective calibration.

Small closed components are physical building candidates. A 3px ink closing
bridges drawn door gaps only for segmentation; the unmodified source remains
the audit background. Final orthogonal fitting uses the registered CAD plane.
"""
from pathlib import Path
import hashlib,json,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageFont
from extract_mpr_road_outline import label_runs,boundary_rings,simplify_ring

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/reference_v4/references/building-road-outline-20261103.png'
OUT=ROOT/'Saved/MPR/road_v5'


def main():
    OUT.mkdir(parents=True,exist_ok=True);im=Image.open(SOURCE).convert('RGB');gray=np.asarray(im.convert('L'))
    ink=Image.fromarray((gray<230).astype(np.uint8)*255)
    closed=ink.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    labels=label_runs(np.asarray(closed)==0);rows=[]
    for label in range(1,int(labels.max())+1):
        yy,xx=np.nonzero(labels==label)
        if len(xx)<60 or xx.max()>435 or np.ptp(xx)>90 or np.ptp(yy)>90:continue
        x0,y0,x1,y1=map(int,(xx.min(),yy.min(),xx.max(),yy.max()))
        if (x0<2 or y0<2 or y1>907) and len(xx)<120:continue
        if x0>275 and y0>790:continue # clipped landscape tip, not a house
        rings=boundary_rings(labels==label);outline=simplify_ring(rings[0],1.5)
        if label in {1,3,43,44,64,132,145,203}:continue # split connected houses; reject parcel/door fragments
        rows.append(dict(id=f'plan_house_{label:03}',type='house_gable',pixel_outline=outline,
                         pixel_center=[float(xx.mean()),float(yy.mean())],pixel_area=len(xx),bbox_px=[x0,y0,x1,y1],
                         clipped_to_image=x0<2 or y0<2 or y1>907,
                         segmentation='230 grayscale threshold and 3px closing recover faint drawn boundaries; audited against original image'))
    # Disconnected door strokes connect these roof/floor interiors into one
    # raster component. Trace each actual house; do not stretch one long module.
    manual_houses=[
        ('split_043a',[[188,78],[209,87],[194,107],[175,96]]),
        ('split_043b',[[175,98],[195,108],[181,129],[160,117]]),
        ('split_044a',[[296,77],[316,85],[304,107],[284,98]]),
        ('split_044b',[[283,98],[304,108],[289,129],[269,119]]),
        ('split_044c',[[270,120],[291,130],[277,150],[256,140]]),
        ('split_132a',[[257,392],[271,406],[258,420],[243,406]]),
        ('split_132b',[[242,406],[259,420],[242,438],[226,423]]),
        ('split_145a',[[244,589],[264,603],[251,619],[232,605]]),
        ('split_145b',[[227,607],[246,622],[233,639],[214,623]]),
        ('open_01',[[316,263],[335,280],[319,296],[299,281]]),
        ('open_02',[[313,451],[332,465],[315,489],[297,475]]),
        ('open_03',[[372,164],[382,168],[373,195],[361,191]]),
    ]
    for identifier,points in manual_houses:
        q=np.array(points,float)
        rows.append(dict(id='plan_house_'+identifier,type='house_gable',pixel_outline=points,pixel_center=q.mean(axis=0).tolist(),
                         bbox_px=[*q.min(axis=0).tolist(),*q.max(axis=0).tolist()],clipped_to_image=False,
                         segmentation='Manually checked independent footprint where raster door gaps join interiors'))
    # Explicit architectural polygons retain genuine concavities. No minimum
    # bounding rectangle is allowed to erase the northwest L-shaped building.
    industrial=[
        dict(id='northwest_l_office',type='orthogonal_l_industrial',pixel_outline=[[509,10],[596,10],[596,42],[571,42],[571,55],[564,55],[564,130],[480,130],[480,55],[520,55],[520,35],[509,35]],estimated_height_m=8.),
        dict(id='north_office_warehouse',type='flat_industrial',pixel_outline=[[991,20],[1185,20],[1185,130],[991,130]],estimated_height_m=12.),
        dict(id='neighbor_warehouse',type='warehouse_deep_docks',pixel_outline=[[445,172],[1096,172],[1096,328],[1067,328],[1067,317],[471,317],[471,328],[445,328]],estimated_height_m=17.,dock_facade_pixel_edge=[[471,317],[1067,317]],dock_count=28),
        dict(id='west_workshop_small_01',type='flat_industrial',pixel_outline=[[11,359],[31,359],[31,392],[11,392]],estimated_height_m=5.2),
        dict(id='west_workshop_small_02',type='flat_industrial',pixel_outline=[[38,351],[64,351],[64,387],[38,387]],estimated_height_m=5.7),
        dict(id='west_workshop_annex',type='orthogonal_l_industrial',pixel_outline=[[48,407],[89,407],[89,490],[48,490],[48,481],[34,481],[34,419],[48,419]],estimated_height_m=7.),
        dict(id='west_detached_industrial',type='flat_industrial',pixel_outline=[[145,607],[179,630],[142,684],[108,661]],estimated_height_m=7.),
        dict(id='east_industrial',type='flat_industrial',pixel_outline=[[1533,501],[1691,453],[1727,597],[1570,633]],estimated_height_m=10.5),
        dict(id='rail_service_shed_01',type='sawtooth_industrial',pixel_outline=[[1049,835],[1099,805],[1113,825],[1061,855]],estimated_height_m=5.2),
        dict(id='rail_service_shed_02',type='sawtooth_industrial',pixel_outline=[[1111,794],[1152,772],[1166,793],[1123,816]],estimated_height_m=5.2),
        dict(id='rail_service_shed_03',type='sawtooth_industrial',pixel_outline=[[1165,767],[1205,743],[1219,765],[1178,786]],estimated_height_m=5.2),
    ]
    # Remove components manually represented by industrial outlines above.
    manual_boxes=[(10,350,65,393),(33,405,91,492),(106,605,181,686)]
    rows=[row for row in rows if not any(a<=row['pixel_center'][0]<=c and b<=row['pixel_center'][1]<=d for a,b,c,d in manual_boxes)]
    tanks=[dict(id='tank_%02d'%(i+1),pixel_center=center,pixel_radius=radius,height_m=height)
           for i,(center,radius,height) in enumerate([([1402,688],38.5,12),([1506,780],45.5,12),([1398,815],43.5,12),
                ([1264,860],40.5,12),([1156,910],44.,12),([1598,868],34.5,12),([1517,888],19.5,9),([1462,900],19.,9)])]
    data=dict(schema_version=5,source=SOURCE.relative_to(ROOT).as_posix(),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),image_size=list(im.size),
              coordinate_space='Orthographic plan pixels; requires new plan-to-CAD affine registration, never old perspective inverse',
              houses=rows,industrial=industrial,tanks=tanks,rail_service_sheds_policy='User authorized plan placement on the southeast service parcel; track geometry is owned separately',
              main_warehouse_policy='Reference for registration only; never generated or changed by context tools',
              status='Pixel extraction candidate; dimensions, clipping and omitted/open strokes need geometric review before final export')
    (OUT/'context_plan_pixels.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    draw=ImageDraw.Draw(im)
    for row in rows+industrial:
        points=[tuple(p)for p in row['pixel_outline']];color=(25,80,245) if row in industrial else (245,50,30)
        draw.line(points+points[:1],fill=color,width=2)
        x,y=np.mean(points,axis=0);draw.text((x,y),row['id'].replace('plan_house_',''),fill=color)
    im.save(OUT/'context_plan_extraction_overlay.png')
    print(json.dumps(dict(houses=len(rows),industrial=len(industrial),output=str(OUT/'context_plan_pixels.json')),ensure_ascii=False))


if __name__=='__main__':main()
