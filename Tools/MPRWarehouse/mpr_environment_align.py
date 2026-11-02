"""Rigid fit CADMapper building 1583 to the authoritative main CAD footprint."""
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/environment'
CAD=[[-181.93004,83.69038],[-166.08044,83.69038],[-166.08044,74.54638],[166.78656,74.54638],[166.78656,83.58878],[182.61076,83.58878],[182.61076,-20.50042],[166.78656,-20.50042],[166.78656,-50.98042],[150.91156,-50.98042],[150.91156,-66.22042],[135.36676,-66.22042],[135.36676,-83.94962],[-166.08044,-83.94962],[-166.08044,-93.09362],[-181.93004,-93.09362]]
CORRESPONDENCE=[14,13,12,11,10,9,8,7,6,5,4,3,2,1,0,15]

def main():
    data=json.loads((OUT/'environment_geometry.json').read_text())
    main=next(m for m in data['meshes'] if m['id']=='1583')
    source=np.array([main['vertices'][i][:2] for i in CORRESPONDENCE]);target=np.array(CAD)
    sc=source.mean(axis=0);tc=target.mean(axis=0)
    u,s,vt=np.linalg.svd((source-sc).T@(target-tc))
    rotation=u@vt
    assert np.linalg.det(rotation)>0, 'Fit must not reflect the coordinate frame'
    translation=tc-sc@rotation
    residual=np.linalg.norm(source@rotation+translation-target,axis=1)
    def tx(v):
        a=np.array(v[:2])@rotation+translation
        return [round(float(a[0]),5),round(float(a[1]),5),v[2]]
    alignment={'sourceBuildingId':'1583','targetSource':'main CAD A-WALL-EXT',
        'mainCADOriginInches':[12800,8000],'mainCADInchesToMetres':0.0254,
        'matrixConvention':'row vector [sourceX,sourceY] @ rotation + translation_m',
        'rotation':rotation.tolist(),'translation_m':translation.tolist(),
        'rotation_deg':float(np.degrees(np.arctan2(rotation[0,1],rotation[0,0]))),
        'scale':1,'reflection':False,'rms_error_m':float(np.sqrt(np.mean(residual**2))),
        'max_error_m':float(max(residual)),
        'sourceVertexCorrespondence':CORRESPONDENCE,'targetFootprint_m':CAD,
        'heightPolicy':'Assembly flattens campus to z=-1.2m, with main CAD finished floor z=0. CADMapper elevation retained only as source data; 1.2m dock difference inferred from reference, not surveyed.',
        'referenceEvidence':['Snipaste_2026-10-30_16-02-59.png','Snipaste_2026-10-30_16-04-43.png','Snipaste_2026-10-30_16-13-26.png']}
    assert alignment['max_error_m']<1.8
    (OUT/'alignment.json').write_text(json.dumps(alignment,indent=2),encoding='utf-8')
    for m in data['meshes']:
        m['vertices']=[tx(v) for v in m['vertices']]
        m['bounds']={'min':[min(v[i] for v in m['vertices']) for i in range(3)],'max':[max(v[i] for v in m['vertices']) for i in range(3)]}
    for m in data['polylines']:
        m['vertices']=[tx(v) for v in m['vertices']]
        m['bounds']={'min':[min(v[i] for v in m['vertices']) for i in range(3)],'max':[max(v[i] for v in m['vertices']) for i in range(3)]}
    data['alignment']=alignment
    data['sourceFrame']='Aligned main-CAD metres; +Y preserved, do not mirror before Blender FBX export.'
    (OUT/'environment_local.json').write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print(json.dumps(alignment,indent=2))

if __name__=='__main__':main()
