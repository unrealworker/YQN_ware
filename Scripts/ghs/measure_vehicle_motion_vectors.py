"""Measure whether the actual moved mesh differs from the stationary road in UE's velocity buffer."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image

def lit_sedan_edges(root,objects):
    # Align a fixed interior portion of the car to its projected centre in
    # each frame. This keeps the glass/paint edges and excludes road and shadow.
    frames=[]
    for filename,row in objects.items():
        if not filename.startswith('road_sedan-lit-'):
            continue
        cx,cy=row['before']['center']
        x0,y0,x1,y1=row['before']['bounds']
        if not frames:
            hw=int(.32*(x1-x0));hh=int(.34*(y1-y0))
        with Image.open(root/(filename+'.png')) as src:
            sample=src.convert('L').transform((2*hw,2*hh),Image.Transform.AFFINE,
                (1,0,cx-hw,0,1,cy-hh),resample=Image.Resampling.BILINEAR)
            frames.append(np.asarray(sample,dtype=np.float32))
    stack=np.stack(frames)
    gx,gy=np.gradient(np.median(stack,axis=0))
    edges=np.hypot(gx,gy)>12.
    change=np.abs(np.diff(stack,axis=0)[:,edges])
    return dict(frames=len(frames),edge_pixels=int(edges.sum()),mean_frame_luma_difference=float(change.mean()),
                p95_frame_luma_difference=float(np.percentile(change,95)))

def measure(root):
    report=json.loads((root/'verification.json').read_bytes())
    if not report['success']:
        raise ValueError(f'Capture did not finish in {root}')
    groups={}
    for label,row in report['objects'].items():
        if '-velocity-' not in label:
            continue
        group=label.split('-velocity-')[0]
        with Image.open(root/(label+'.png')) as src:
            image=np.asarray(src.convert('RGB'),dtype=np.float32)
        h,w=image.shape[:2]
        point=(np.array(row['before']['center'])+np.array(row['after']['center']))*.5
        bounds=np.array(row['before']['bounds'])
        extent=np.maximum([3,3],(bounds[2:]-bounds[:2])/2)
        size=np.maximum([2,2],np.round(extent*[.35,.30]).astype(int))
        def patch(cx,cy):
            ix,iy=int(round(cx)),int(round(cy))
            assert size[0]<ix<w-size[0] and size[1]<iy<h-size[1],(label,cx,cy)
            return image[iy-size[1]:iy+size[1],ix-size[0]:ix+size[0]]
        body=patch(*point)
        # A static world-space camera has zero motion over the nearby ground.
        # Take road reference on both sides to survive an adjacent passing car.
        side=np.concatenate([patch(point[0],point[1]+s*extent[1]*1.65) for s in (-1,1)])
        background=np.median(side.reshape(-1,3),axis=0)
        delta=np.max(np.abs(body-background),axis=2)
        displacement=float(np.linalg.norm(np.subtract(row['after']['center'],row['before']['center'])))
        groups.setdefault(group,[]).append(dict(image=label,apparent_travel_px=round(displacement,3),
              median_velocity_colour_difference=float(np.median(delta)),moving_core_percent=float(100*np.mean(delta>=1)),
              stationary_colour=background.tolist(),object_colour=np.median(body.reshape(-1,3),axis=0).tolist()))
    summary={k:dict(median_travel_px=float(np.median([f['apparent_travel_px'] for f in frames])),
                    median_colour_difference=float(np.median([f['median_velocity_colour_difference'] for f in frames])),
                    median_moving_core_percent=float(np.median([f['moving_core_percent'] for f in frames])))
             for k,frames in groups.items()}
    lit=lit_sedan_edges(root,report['objects'])
    result=dict(case=root.name,frames=groups,summary=summary,lit_sedan_edges=lit)
    (root/'velocities.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(root.name,summary,lit)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures',type=Path,nargs='+')
    parser.add_argument('--check',action='store_true',help='Require a nonzero velocity buffer on both moving mesh types')
    args=parser.parse_args()
    for root in args.captures:
        summary=measure(root)
        if args.check:
            for vehicle in ('road_sedan','replay_forklift'):
                group=summary[vehicle]
                if group['median_travel_px']<1 or group['median_moving_core_percent']<50:
                    raise SystemExit(f'{vehicle} did not produce motion vectors while moving in {root}')
