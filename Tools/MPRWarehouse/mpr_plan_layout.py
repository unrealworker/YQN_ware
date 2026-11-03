"""Independent 2D plan registration, deliberately separate from render cameras.

The user drawing has different X/Y scales. Keep CAD warehouse interfaces fixed,
then regularize individual building frames after mapping (never shear meshes).
"""
from pathlib import Path
import json,hashlib
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/reference_v4/references/building-road-outline-20261103.png'
FILE=ROOT/'SourceAssets/MPR/reference_v4/site/plan_registration_v5.json'

def load_registration():return json.loads(FILE.read_text(encoding='utf8'))

def plan_to_world(pixel,z=-1.2,registration=None):
    r=registration or load_registration();p=np.asarray(pixel,float)
    xy=p*np.asarray(r['scale_m_per_px'])+np.asarray(r['offset_m'])
    if xy.ndim==1:return [float(xy[0]),float(xy[1]),float(z)]
    return np.c_[xy,np.full(len(xy),z)].tolist()

def world_to_plan(point,registration=None):
    r=registration or load_registration();p=np.asarray(point,float)[...,:2]
    return ((p-np.asarray(r['offset_m']))/np.asarray(r['scale_m_per_px'])).tolist()

def build_registration():
    # Main wall centers, avoiding dock tabs/roof overhang and the absent NW step.
    # Paired raster measures are explicit and reviewable; no projective warp.
    axes={
        'x':[(444.,-181.93004,'west wall'),(473.,-166.08044,'southwest return'),
             (1022.,182.61076,'east wall'),(998.,166.78656,'east step 1'),
             (976.,150.91156,'east step 2'),(950.,135.36676,'east step 3')],
        'y':[(385.,74.54638,'north long wall'),(375.,83.58878,'northeast return'),
             (523.,-20.50042,'east step 1'),(559.,-50.98042,'east step 2'),
             (581.,-66.22042,'east step 3'),(607.,-83.94962,'south long wall'),
             (618.,-93.09362,'southwest return')]}
    scales=[];offsets=[];readback={}
    for axis,rows in axes.items():
        a=np.array([[p,1.] for p,m,label in rows]);b=np.array([m for p,m,label in rows])
        scale,offset=np.linalg.lstsq(a,b,rcond=None)[0]
        scales.append(float(scale));offsets.append(float(offset))
        readback[axis]=[dict(pixel=p,cad_m=m,label=label,fitted_m=float(p*scale+offset),
                             error_m=float(p*scale+offset-m)) for p,m,label in rows]
    assert scales[0]>0 and scales[1]<0
    result=dict(schema_version=1,reference=SOURCE.relative_to(ROOT).as_posix(),
                reference_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                image_dimensions_px=[1728,910],coordinate_frame='CAD metres; X east, Y north, Z up',
                scale_m_per_px=scales,offset_m=offsets,anchors=readback,
                max_anchor_error_m=max(abs(a['error_m']) for rows in readback.values() for a in rows),
                policy='Separate X/Y scale, zero XY shear. Main CAD shell/interior unchanged. Regularize rotated building footprints; no bilinear mesh warping.',
                source_limitations=['Diagram is not a survey or an isotropic plan.',
                                    'NW CAD return is absent from the diagram and is excluded from fitting.',
                                    'Main CAD doors and shell are authoritative at interior interfaces.'])
    for p in [[0.,0.],[1728.,910.],[444.,385.]]:
        assert np.max(np.abs(np.array(world_to_plan(plan_to_world(p,registration=result),result))-p))<1e-8
    FILE.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':build_registration()
