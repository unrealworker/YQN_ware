"""Extract tree crown symbols from the supplied plan, in pixels only.

Uses closed white components and the scalloped radial silhouette of a tree
symbol. No old perspective camera, random fill, Blender or UE dependency.
"""
from pathlib import Path
import argparse, hashlib, json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from extract_mpr_road_outline import label_runs, boundary_rings, signed_area, simplify_ring

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'SourceAssets/MPR/reference_v4/references/all-elements-outline-20261103.png'
OUT = ROOT/'SourceAssets/MPR/reference_v4/site/plan_vegetation_v5.json'
DIAG = ROOT/'Saved/MPR/road_v5'

# Reviewed against source crops/contact sheets. IDs refer to this exact source
# hash and threshold, not arbitrary semantic guesses. Small circles and crowns
# crossed by parking lines otherwise fail the conservative polygon classifier.
REVIEW_ACCEPT = {
    12,19,20,31,45,61,67,70,75,80,88,89,100,105,134,147,206,220,235,236,
    241,245,248,274,276,287,291,294,298,328,332,340,344,347,356,372,
    416,420,430,431,444,449,451,457,460,463,482,484,508,513,517,528,
    539,540,541,545,550,557,569,572,573,584,593,594,602,607,617,625,
    631,638,662,681,672,724,725,726,733,
}
REVIEW_REJECT = {502:'curved_paved_stub',580:'house_footprint',604:'house_footprint',721:'house_footprint'}
# Intersecting crown outlines merge their white interiors. Each item below is
# a separate visible circular crown, explicitly measured in the supplied plan.
REVIEW_SPLIT = {
    106:[(1334,128,9.8),(1352,128,13.4)],
    192:[(1499,277,10.5),(1518,281,14)],
    663:[(440,831,14),(438,817,8)],
    664:[(513,826,13),(523,817,7.3)],
    668:[(797,830,12),(817,834,13)],
    693:[(599,870,13.5),(606,887,8.8)],
    697:[(620,869,10.8),(625,888,13.8)],
}
REVIEW_CENTER_RADIUS = {
    19:(1265,14,8.5),20:(1416,16,13),61:(855,77,8.5),
    75:(1362,90,8.5),80:(918,95,8.8),89:(902,103,11.5),
    105:(650,120,9),129:(1538,181,9.5),354:(1303,474,12),409:(1354,535,6.8),
}
REVIEW_RECOVERED = {148,154,333,513,580}
# Clearly visible unclosed crowns, measured on the original drawing. These are
# explicit source measurements, not gap filling or a planted population rule.
REVIEW_OPEN_CROWNS = [
    (632,121,12),(704,116,12),(879,112,13),(1239,187,12),
    (1277,35,13),(1283,217,14),(1267,239,11),(1169,217,13),
    (1165,232,8),(1174,253,10),(1149,271,8),(1087,373,6),
    (727,815,13),(571,856,14),(468,814,11),
]


def visual_review(records):
    """Apply explicit source-only review decisions and preserve provenance."""
    extras=[]
    for row in records:
        number=int(row['id'].split('_')[-1])
        row['automatic_classification']=row['classification']
        if number in REVIEW_REJECT:
            row.update(classification='excluded_reviewed_non_tree',review_reason=REVIEW_REJECT[number])
        elif number in REVIEW_SPLIT:
            row.update(classification='excluded_merged_crowns',review_reason='Visible overlapping tree symbols split into measured circles')
            for j,(x,y,r) in enumerate(REVIEW_SPLIT[number],1):
                extras.append(dict(id=f"{row['id']}_split_{j}",classification='tree',center_px=[x,y],radius_px=r,
                    radius_x_px=r,radius_y_px=r,bbox_px=[x-r,y-r,x+r,y+r],source_component=row['id'],
                    review_reason='Manual circle center/radius from visible source crown arcs; overlapping symbols',
                    review_confidence='visual_measured',position_uncertainty_px=2.))
        elif number in REVIEW_ACCEPT:
            row.update(classification='tree',review_reason='Confirmed crown in source crop; conservative shape filter override',review_confidence='visual_confirmed')
        elif row['classification']=='tree':
            row.update(review_reason='Tree symbol visually confirmed in full candidate contact sheet',review_confidence='visual_confirmed')
        if number in REVIEW_CENTER_RADIUS:
            x,y,r=REVIEW_CENTER_RADIUS[number]
            row.update(center_px=[x,y],radius_px=r,radius_x_px=r,radius_y_px=r,
                       review_reason='Partial white component recentered using visible outer crown circle',position_uncertainty_px=2.)
    return records+extras


def recover_open_crowns(gray,records):
    """Close <=4px raster gaps only, retaining measured rather than random points."""
    ink=Image.fromarray(((gray<125)*255).astype(np.uint8))
    closed=np.asarray(ink.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5)))>0
    labels=label_runs(~closed);counts=np.bincount(labels.ravel());recovered=[]
    for label in np.flatnonzero((counts>=35)&(counts<=1600)):
        if not label:continue
        row=measure(labels==label,label,int(label))
        if not row or row['classification'] not in ('tree','suspected_tree'):continue
        m=row['metrics'];x,y=row['center_px'];r=row['radius_px']
        if m['circularity']<.45 or m['aspect']>1.45 or m['oriented_fill']>.85 or m['longest_edge_ratio']>.67:continue
        if any(math.dist([x,y],other['center_px'])<max(r,other['radius_px'])*.90 for other in records+recovered if other['classification']=='tree'):continue
        if int(label) not in REVIEW_RECOVERED:continue
        row.update(id=f'recovered_{int(label):04d}',classification='tree',review_confidence='gap_closed_visually_confirmed',
            review_reason='Closed a maximum 4px gap in original line-art only; candidate inspected against original unmodified image',
            position_uncertainty_px=2.)
        recovered.append(row)
    for index,(x,y,r) in enumerate(REVIEW_OPEN_CROWNS,1):
        if any(math.dist([x,y],other['center_px'])<max(r,other['radius_px'])*.85 for other in records+recovered if other['classification']=='tree'):continue
        recovered.append(dict(id=f'open_crown_{index:03}',classification='tree',center_px=[x,y],radius_px=r,
            radius_x_px=r,radius_y_px=r,bbox_px=[x-r,y-r,x+r,y+r],review_confidence='visual_measured',position_uncertainty_px=2.,
            review_reason='Manually measured visible crown with an unclosed source outline; no inferred/random placement'))
    return records+recovered


def measure(mask, label, region_id):
    yy, xx = np.nonzero(mask)
    area = len(xx)
    if area < 35 or area > 2500:
        return None
    x0, y0, x1, y1 = int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())
    width, height = x1-x0+1, y1-y0+1
    if min(width, height) < 7 or max(width, height) > 65:
        return None
    # The enclosing tree symbol has no interior roof ridges/solar cells.
    rings = boundary_rings(mask)
    if not rings:
        return None
    ring = np.asarray(rings[0], dtype=float)
    center = np.array([xx.mean(), yy.mean()])
    samples = []
    for a, b in zip(ring, np.roll(ring, -1, axis=0)):
        for t in np.linspace(0, 1, max(1, math.ceil(np.linalg.norm(b-a)/.5)), endpoint=False):
            samples.append(a+(b-a)*t)
    samples = np.asarray(samples)
    vectors = samples-center
    angle = np.arctan2(vectors[:, 1], vectors[:, 0])
    radius = np.linalg.norm(vectors, axis=1)
    order = np.argsort(angle)
    # Radius profiles are periodic; harmonics >=5 distinguish scallops from
    # smooth tanks and the strong four-corner harmonic of house rectangles.
    aa, rr = angle[order], radius[order]
    profile = np.interp(np.linspace(-math.pi, math.pi, 128, endpoint=False),
                        np.r_[aa-2*math.pi, aa, aa+2*math.pi], np.tile(rr, 3))
    spectrum = np.abs(np.fft.rfft(profile-profile.mean()))/len(profile)
    high = float(np.sqrt(np.sum(spectrum[5:22]**2))/profile.mean())
    low = float(np.sqrt(np.sum(spectrum[1:5]**2))/profile.mean())
    fill = area/(width*height)
    perimeter = float(np.linalg.norm(ring-np.roll(ring, -1, axis=0), axis=1).sum())
    circularity = 4*math.pi*area/max(perimeter*perimeter, 1)
    coarse = np.asarray(simplify_ring(ring.tolist(),1.15))
    # Rotated bounding rectangles distinguish actual square houses from trees.
    # Axis-aligned box fill alone cannot distinguish a diagonal house diamond.
    min_rect_area = float('inf')
    for a,b in zip(coarse,np.roll(coarse,-1,axis=0)):
        d=b-a; length=np.linalg.norm(d)
        if length < .01:continue
        axis=d/length; perp=np.array([-axis[1],axis[0]])
        p=ring@axis; q=ring@perp
        min_rect_area=min(min_rect_area,float(np.ptp(p)*np.ptp(q)))
    oriented_fill=area/max(min_rect_area,1)
    longest_edge_ratio=float(np.max(np.linalg.norm(coarse-np.roll(coarse,-1,axis=0),axis=1))/math.sqrt(area))
    record = dict(id=f'canopy_{region_id:04d}', component_label=int(label),
                  center_px=center.round(3).tolist(),
                  radius_px=round(float(np.median(profile))+.8, 3),
                  radius_x_px=round(width/2+.8, 3), radius_y_px=round(height/2+.8, 3),
                  bbox_px=[x0, y0, x1, y1], area_px=area,
                  boundary_px=ring.round(2).tolist(),
                  metrics=dict(aspect=round(max(width,height)/min(width,height),4),
                               fill=round(fill,4), vertices=len(ring),
                               circularity=round(circularity,4),
                               coarse_vertices=len(coarse), oriented_fill=round(oriented_fill,4),
                               longest_edge_ratio=round(longest_edge_ratio,4),
                               scallop_energy=round(high,5), low_harmonic_energy=round(low,5)))
    # A convex rectangle remains a rectangle even if its angle is diagonal.
    # Dense roof equipment creates small rectangular enclosed components.
    if oriented_fill>.89 or len(coarse)<7 or longest_edge_ratio>.70:
        record['classification']='excluded_polygon_or_small_rect'
    elif max(width,height)/min(width,height)>1.65 or fill<.40:
        record['classification']='excluded_elongated_or_fragment'
    elif len(ring)<13:
        record['classification']='excluded_polygon_or_small_rect'
    elif high < .016:
        record['classification']='excluded_smooth_or_rectangular'
    elif high >= .025 and low < .15 and circularity > .46:
        record['classification']='tree'
    else:
        record['classification']='suspected_tree'
    return record


def font(size):
    try:
        return ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
    except OSError:
        return ImageFont.load_default()


def diagnostics(im, records):
    overlay=im.convert('RGB').copy()
    draw=ImageDraw.Draw(overlay)
    counts={}
    for row in records:
        cls=row['classification'];counts[cls]=counts.get(cls,0)+1
        if cls not in ('tree','suspected_tree'):
            continue
        x,y=row['center_px'];r=row['radius_px']
        color=(14,153,75) if cls=='tree' else (235,135,0)
        draw.ellipse((x-r,y-r,x+r,y+r),outline=color,width=2)
        draw.line((x-2,y,x+2,y),fill=color,width=1)
        draw.line((x,y-2,x,y+2),fill=color,width=1)
        draw.text((x+2,y-r-5),row['id'].split('_')[-1],fill=color,font=font(9),stroke_width=1,stroke_fill='white')
    label=f"Plan tree crowns: {counts.get('tree',0)} | suspects: {counts.get('suspected_tree',0)} | pixel coordinates only"
    draw.rectangle((0,0,1010,27),fill='white')
    draw.text((8,3),label,font=font(18),fill=(12,60,30))
    overlay.save(DIAG/'vegetation_overlay.png')
    # Large separate contact sheets permit inspection without changing data.
    for cls in ('tree','suspected_tree','excluded_smooth_or_rectangular','excluded_polygon_or_small_rect','excluded_elongated_or_fragment'):
        selected=[r for r in records if r['classification']==cls]
        if not selected:continue
        cols=12;cell_w=140;cell_h=130
        sheet=Image.new('RGB',(cols*cell_w,math.ceil(len(selected)/cols)*cell_h),'#e9ecef');d=ImageDraw.Draw(sheet)
        for i,row in enumerate(selected):
            x0,y0,x1,y1=row['bbox_px'];crop=im.crop((x0-5,y0-5,x1+6,y1+6)).convert('RGB')
            crop.thumbnail((100,100));x=(i%cols)*cell_w;y=(i//cols)*cell_h
            sheet.paste(crop,(x+20,y+20));m=row.get('metrics',{})
            d.text((x+3,y+2),f"{row['id']} {m.get('scallop_energy',0):.3f}",fill='black',font=font(11))
            d.text((x+3,y+109),f"{row['center_px'][0]:.0f},{row['center_px'][1]:.0f} v{m.get('vertices',0)}",fill='black',font=font(11))
        sheet.save(DIAG/f'vegetation_candidates_{cls}.png')
    return counts


def main(source=SOURCE):
    DIAG.mkdir(parents=True,exist_ok=True)
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash!='d4741b2c6790b86e7b6c8f5365e135b44c17a1c3ccb420119ac3e5ad27ecddae':
        raise ValueError('Manual crown review belongs to the supplied 2026-11-03 all-elements drawing; a changed source requires fresh review')
    im=Image.open(source).convert('RGB');gray=np.asarray(im.convert('L'))
    labels=label_runs(gray>=125);counts=np.bincount(labels.ravel());records=[]
    for label in np.flatnonzero((counts>=35)&(counts<=2500)):
        if not label:continue
        record=measure(labels==label,label,len(records)+1)
        if record:records.append(record)
    records=recover_open_crowns(gray,visual_review(records))
    totals=diagnostics(im,records)
    result=dict(schema_version=1,status='review_ready_pixels_only',review_ready=True,
                source_image=str(source.relative_to(ROOT)),source_sha256=source_hash,
                image_size=list(im.size),coordinate_frame='Plan image pixels; origin top-left; x right, y down; no camera or world projection applied',
                method=dict(threshold=125,connectivity=4,random_population=False,
                            detection='Closed white component; polygon/radius shape classification; scalloped crown harmonics distinguish tree symbols',
                            position_uncertainty_px=1.5,review='All automatic candidates contact-sheet reviewed; conservative rejected candidates reviewed for actual small crowns; overlapping symbols manually split where visible',
                            limitations=['Raster line art is schematic, not a vegetation survey.','Some touching or canvas-clipped crowns have 2px center/radius uncertainty.','Faint/open/occluded crown symbols can remain under-detected; this list contains reviewed positions, not a claim of complete surveyed vegetation.','World mapping must use the new independent plan registration, never the old perspective camera.']),
                counts=totals,trees=[r for r in records if r['classification']=='tree'],
                suspected=[r for r in records if r['classification']=='suspected_tree'],
                excluded=[r for r in records if r['classification'].startswith('excluded')])
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(totals))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=SOURCE)
    main(parser.parse_args().source)
