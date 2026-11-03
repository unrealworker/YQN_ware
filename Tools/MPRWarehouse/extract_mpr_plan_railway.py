"""Trace the latest plan's visible rail corridors in pixel coordinates.

This is an annotated drawing interpretation, not a railway survey. Rail gauge
is intentionally NOT inferred from the exaggerated printed rail-line spacing.
No Blender/Unreal invocation; no scene sources are modified.
"""
from pathlib import Path
import hashlib,json,math
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from extract_mpr_road_outline import label_runs

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/reference_v4/references/all-elements-outline-20261103.png'
OUT=ROOT/'SourceAssets/MPR/reference_v4/site/plan_railway_v5.json'
DIAG=ROOT/'Saved/MPR/road_v5'

# Horizontal scan stations identify paired steel strokes and sleeper hatching.
# Freight roofs are offset from their track by the drawing's pseudo-3D height;
# their centres are retained as separate observations, never treated as rails.
STATIONS=[0,100,200,300,400,500,600,700,800,900,909]
MAIN={
 'MainWest':[1491,1412,1332,1251,1183,1137,1073,995,896,785,775],
 'MainWestInner':[1512,1433,1351,1271,1209,1158,1090,1012,918,809,799],
 'MainEast':[1632,1563,1487,1409,1334,1251,1169,1081,985,876,866],
}
SPURS={
 'WestBranchA':[[1394,0],[1313,100],[1255,200],[1210,300],[1164,400],[1121,500],[1073,600]],
 'WestBranchB':[[1405,0],[1324,100],[1265,200],[1221,300],[1175,400],[1137,500]],
}

def smooth_path(controls,step=5.):
    """Monotone cubic Hermite interpolation: keeps station positions, no loop."""
    p=np.asarray(controls,float);y=p[:,1];x=p[:,0];h=np.diff(y);delta=np.diff(x)/h
    slopes=np.empty(len(x));slopes[0]=delta[0];slopes[-1]=delta[-1]
    for i in range(1,len(x)-1):
        if delta[i-1]*delta[i]<=0:slopes[i]=0
        else:
            a=2*h[i]+h[i-1];b=h[i]+2*h[i-1]
            slopes[i]=(a+b)/(a/delta[i-1]+b/delta[i])
    out=[]
    for i in range(len(x)-1):
        n=max(2,int(math.ceil(h[i]/step)))
        for t in np.linspace(0,1,n,endpoint=False):
            v=(2*t**3-3*t*t+1)*x[i]+(t**3-2*t*t+t)*h[i]*slopes[i]+(-2*t**3+3*t*t)*x[i+1]+(t**3-t*t)*h[i]*slopes[i+1]
            out.append([round(float(v),3),round(float(y[i]+t*h[i]),3)])
    return out+[p[-1].tolist()]

def freight_observations():
    # Visible closed freight-roof white regions: pixel measurements on source.
    # IDs are only diagnostic, not production instance IDs.
    image=np.array(Image.open(SOURCE).convert('L'));labels=label_runs(image>170)
    counts=np.bincount(labels.ravel());observations=[]
    for label in np.flatnonzero((counts>200)&(counts<1800)):
        yy,xx=np.nonzero(labels==label);cx,cy=float(xx.mean()),float(yy.mean())
        if cx<700 or cx<1520-cy*.85-170 or cx>1650-cy*.78:continue
        pts=np.c_[xx,yy];values,vectors=np.linalg.eigh(np.cov(pts.T));ratio=math.sqrt(values[-1]/max(values[0],.01))
        if not 1.65<ratio<6:continue
        vector=vectors[:,-1];length=float(np.ptp(pts@vector));width=float(np.ptp(pts@np.array([-vector[1],vector[0]])))
        if not 12<=width<=15.5:continue
        observations.append(dict(center_px=[round(cx,2),round(cy,2)],length_px=round(length,2),width_px=round(width,2),measurement='closed white roof component; pseudo-3D displacement relative to track'))
    return observations

def main():
    DIAG.mkdir(parents=True,exist_ok=True)
    observations=freight_observations();groups={k:[]for k in ['NorthFreightSiding','MainFreight','MainEastInner']}
    for r in observations:
        x,y=r['center_px']
        track='NorthFreightSiding' if y<400 and x<1560-.8*y else ('MainFreight' if y<550 and x<1620-.85*y else 'MainEastInner')
        groups[track].append(r['center_px']);r['track_id']=track
    for rows in groups.values():rows.sort(key=lambda p:p[1])
    assert [len(groups[k])for k in groups]==[10,11,11]
    tracks=[]
    for name,xs in MAIN.items():
        controls=[[x,y]for x,y in zip(xs,STATIONS)]
        tracks.append(dict(id=name,path_px=smooth_path(controls),control_points_px=controls,kind='through_track',confidence='medium',position_uncertainty_px=4.0))
    for name,controls in SPURS.items():
        target='MainWest'
        tracks.append(dict(id=name,path_px=smooth_path(controls),control_points_px=controls,kind='joining_siding',joins_track=target,join_end_px=controls[-1],confidence='medium',position_uncertainty_px=5.0,
                           inferred_interval_px=controls[-2:],note='Last short turnout connection is inferred through superimposed strokes; do not duplicate track beyond the endpoint'))
    main_inner=next(r for r in tracks if r['id']=='MainWestInner')
    join450=min(main_inner['path_px'],key=lambda p:abs(p[1]-450))
    loaded_controls={
        'NorthFreightSiding':[[1537.0,0]]+groups['NorthFreightSiding']+[join450],
        'MainFreight':[[1534.0,80]]+groups['MainFreight']+[[1090.,600.]],
        'MainEastInner':[[1620.,0],[1547.,100],[1464.,200],[1380.,300],[1294.,400]]+groups['MainEastInner']+[[818.65,909.]],
    }
    for name,controls in loaded_controls.items():
        tracks.append(dict(id=name,path_px=smooth_path(controls),control_points_px=controls,kind='through_track' if name=='MainEastInner' else 'joining_siding',
                           joins_track=None if name=='MainEastInner' else 'MainWestInner',
                           confidence='high_inside_measured_freight_interval_medium_outside',position_uncertainty_px=1.0,
                           measured_freight_interval_y_px=[groups[name][0][1],groups[name][-1][1]],
                           note='Loaded interval passes through measured white roof centres. Use these centres for asset placement; pseudo-3D roof-to-rail offset is intentionally not retained as lateral translation. Tail connection is inferred.'))
    # A separate narrow west branch bed and a main fan bed preserve the planted
    # wedge between them. Global edges are supplied for tree exclusion only.
    west_global=[[x-5,y]for x,y in SPURS['WestBranchA'][:-1]]+[[1066,600],[988,700],[889,800],[778,900],[768,909]]
    east_global=[[x+6,y]for x,y in zip(MAIN['MainEast'],STATIONS)]
    main_west=[[x-6,y]for x,y in zip(MAIN['MainWest'],STATIONS)]
    branch_east=[[x+5,y]for x,y in SPURS['WestBranchB']]
    beds=[dict(id='MainFanBed',west=smooth_path(main_west),east=smooth_path(east_global)),
          dict(id='WestBranchBed',west=smooth_path(SPURS['WestBranchA']),east=smooth_path(branch_east),note='Narrow separate branch bed; planted wedge between branch and main fan must remain vegetated')]
    rolling=dict(track_ids=['NorthFreightSiding','MainFreight','MainEastInner'],spacing_m=24.0,start_offset_m=12.0,scale=[1,1,1],
                 segments=[dict(track_id='NorthFreightSiding',from_y_px=0,to_y_px=400),dict(track_id='MainFreight',from_y_px=80,to_y_px=545),dict(track_id='MainEastInner',from_y_px=410,to_y_px=909)],
                 use_segments=True,roof_observations_px=observations,
                 placements_px=[dict(track_id=r['track_id'],position_px=r['center_px'])for r in observations],prefer_measured_placements=True,
                 note='Use original 20.8m x 3.3m boxcar dimensions. Roof drawings are not scaled-up asset footprints. Do not populate tracks outside listed occupied intervals.')
    result=dict(schema_version=1,status='ready_plan_trace_with_turnout_uncertainty',source_image=SOURCE.relative_to(ROOT).as_posix(),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),image_size=[1728,910],
                coordinate_frame='pixel origin top-left; use mpr_plan_layout.plan_to_world, never legacy perspective CAL',
                tracks=tracks,ballast_edges_px=dict(west=smooth_path(west_global),east=smooth_path(east_global)),ballast_beds_px=beds,
                rolling_stock=rolling,rail_gauge_m=1.435,
                method='Manual cross-section station measurements on paired rail strokes, monotone cubic interpolation; separate identification of freight roofs and switch overlaps.',
                source_reconciliation=[dict(id='EastRoadClearance',reason='Latest road-only building plan and all-elements plan differ locally at northeast canvas edge and lower southeast railway edge. Move the outer empty track west by 9-16px at affected stations; measured freight centres unchanged.',original_control_points_px=[[1645,0],[994,800],[892,900],[882,909]],corrected_control_points_px=[[1632,0],[985,800],[876,900],[866,909]])],
                limitations=['User drawing has schematic line widths and pseudo-3D freight roofs; cannot establish survey-grade track spacing.',
                             'Four continuous tracks, two loaded sidings and two western branches are distinguished; joining turnout tails are explicit semantic inference.',
                             'Global ballast edges bound the entire corridor including the planted wedge. Prefer ballast_beds_px or per-track beds for visible gravel to preserve that wedge.'])
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    im=Image.open(SOURCE).convert('RGBA');layer=Image.new('RGBA',im.size);draw=ImageDraw.Draw(layer)
    colors=[(225,40,50),(30,100,225),(200,35,180),(20,155,135),(230,130,10),(130,50,220),(40,160,50),(170,100,30)]
    for i,row in enumerate(tracks):
        color=colors[i];draw.line([tuple(p)for p in row['path_px']],fill=(*color,210),width=3)
        for p in row['control_points_px']:draw.ellipse((p[0]-2,p[1]-2,p[0]+2,p[1]+2),fill=(*color,255))
        p=row['path_px'][min(20,len(row['path_px'])-1)];draw.text((p[0]+4,p[1]),row['id'],fill=(*color,255),stroke_width=1,stroke_fill=(255,255,255,255))
    for side in ['west','east']:draw.line([tuple(p)for p in result['ballast_edges_px'][side]],fill=(30,100,30,180),width=1)
    Image.alpha_composite(im,layer).convert('RGB').save(DIAG/'railway_trace_overlay.png')
    # Numerical geometric checks in pixel space. Turnout endpoints are shared.
    for row in tracks:
        a=np.asarray(row['path_px']);assert np.isfinite(a).all() and np.all(np.diff(a[:,1])>0)
        assert np.min(a[:,0])>=0 and np.max(a[:,0])<1728
    ordered=[next(t for t in tracks if t['id']==k)for k in ['MainWest','MainWestInner','MainEastInner','MainEast']]
    for a,b in zip(ordered,ordered[1:]):
        assert all(np.interp(y,np.asarray(a['path_px'])[:,1],np.asarray(a['path_px'])[:,0])<np.interp(y,np.asarray(b['path_px'])[:,1],np.asarray(b['path_px'])[:,0])for y in range(910))
    errors=[]
    for r in observations:
        path=np.asarray(next(t for t in tracks if t['id']==r['track_id'])['path_px']);q=np.asarray(r['center_px']);a=path[:-1];d=path[1:]-a;t=np.clip(np.sum((q-a)*d,axis=1)/np.sum(d*d,axis=1),0,1)
        errors.append(float(np.linalg.norm(a+t[:,None]*d-q,axis=1).min()))
    assert max(errors)<.05
    report=dict(status='passed',tracks=len(tracks),main_tracks=4,joining_sidelines=4,roof_observations=len(rolling['roof_observations_px']),loaded_path_roof_center_max_error_px=max(errors),main_track_order_crossing_free=True,
                json_sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(),source_sha256=result['source_sha256'],gauge_m=1.435)
    (DIAG/'railway_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
