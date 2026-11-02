"""Fit a pinhole camera to the user's authoritative MPR overview.

NumPy/Pillow only. Pixel measurements are manual image readings, not a survey.
The non-coplanar wall-base checks constrain the roof/ground parallax ambiguity.
Public API: project_world_to_image(world_xyz, calibration=None),
            image_to_ground(px, py, z=-1.2, calibration=None).
"""
from pathlib import Path
import json,math,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/reference_v3/calibration'
REFERENCE=ROOT/'SourceAssets/MPR/reference_v4/references/ChatGPT 图像 2026年11月2日 15_56_24.png'
CALIBRATION=OUT/'camera_calibration.json'

def load_calibration():return json.loads(CALIBRATION.read_text(encoding='utf8'))

def project_world_to_image(world_xyz,calibration=None):
 c=calibration or load_calibration();p=np.asarray(world_xyz,dtype=float)
 if p.shape[-1]!=3:raise ValueError('world_xyz must contain x,y,z in CAD metres')
 R=np.asarray(c['world_to_cv_camera_rotation']);C=np.asarray(c['camera_location_m']);K=np.asarray(c['intrinsic_matrix'])
 q=(R@(p-C).T).T;v=(K@q.T).T
 return (v[...,:2]/v[...,2,None]).tolist()

def image_to_ground(px,py,z=-1.2,calibration=None):
 c=calibration or load_calibration();R=np.asarray(c['world_to_cv_camera_rotation']);C=np.asarray(c['camera_location_m']);K=np.asarray(c['intrinsic_matrix'])
 ray=R.T@np.linalg.solve(K,np.array([px,py,1.],dtype=float))
 if abs(ray[2])<1e-12:raise ValueError('Ray is parallel to requested plane')
 t=(z-C[2])/ray[2]
 if t<=0:raise ValueError('Requested plane lies behind the camera')
 return (C+t*ray).tolist()

def normalize_points(p):
 center=p.mean(axis=0);scale=math.sqrt(2)/np.linalg.norm(p-center,axis=1).mean()
 T=np.array([[scale,0,-center[0]*scale],[0,scale,-center[1]*scale],[0,0,1]])
 return (T@np.c_[p,np.ones(len(p))].T).T[:,:2],T

def homography(source,target):
 a,T=normalize_points(source);b,U=normalize_points(target);rows=[]
 for (x,y),(u,v) in zip(a,b):
  rows.extend([[-x,-y,-1,0,0,0,u*x,u*y,u],[0,0,0,-x,-y,-1,v*x,v*y,v]])
 _,_,V=np.linalg.svd(rows);H=np.linalg.inv(U)@V[-1].reshape(3,3)@T
 return H/H[2,2]

def rodrigues(v):
 angle=np.linalg.norm(v)
 if angle<1e-14:return np.eye(3)
 x,y,z=v/angle;S=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
 return np.eye(3)+math.sin(angle)*S+(1-math.cos(angle))*(S@S)

def initial_pose(H,K,z=13.4):
 B=np.linalg.solve(K,H);scale=(np.linalg.norm(B[:,0])+np.linalg.norm(B[:,1]))/2
 r1=B[:,0]/scale;r2=B[:,1]/scale
 R0=np.column_stack([r1,r2,np.cross(r1,r2)])
 U,_,V=np.linalg.svd(R0);R=U@V
 if np.linalg.det(R)<0:R=-R
 t=B[:,2]/scale-R[:,2]*z;return R,-R.T@t

def fit_camera(world,pixels,H,width,height):
 best=None
 # Joint focal/pose/principal-point solve. Weak principal/focal priors select a
 # stable camera among nearly equivalent single-image planar solutions.
 for focal_start in [900.,1400.,2100.,3000.,4500.]:
  K=np.array([[focal_start,0,width/2],[0,focal_start,height/2],[0,0,1]])
  R0,C0=initial_pose(H,K)
  if C0[2]<0:continue
  start=np.r_[np.zeros(3),C0/1000,math.log(focal_start/2000),0.,0.]
  def decode(p):
   R=rodrigues(p[:3])@R0;C=p[3:6]*1000;f=2000*math.exp(float(np.clip(p[6],-3,3)))
   return R,C,np.array([[f,0,width/2+p[7]*100],[0,f,height/2+p[8]*100],[0,0,1]])
  def residual(p):
   R,C,K=decode(p);q=(R@(world-C).T).T;pred=(K@q.T).T;pred=pred[:,:2]/pred[:,2,None]
   weights=np.r_[np.ones(16),np.full(len(world)-16,.65)]
   return np.r_[((pred-pixels)*weights[:,None]).ravel(),p[7]/2,p[8]/2,p[6]/3]
  p=start;lm=.01;err=residual(p);score=err@err
  for iteration in range(260):
   J=np.column_stack([(residual(p+np.eye(9)[j]*1e-6)-residual(p-np.eye(9)[j]*1e-6))/2e-6 for j in range(9)])
   A=J.T@J;gradient=J.T@err
   try:step=np.linalg.solve(A+lm*np.diag(np.maximum(np.diag(A),1)),gradient)
   except np.linalg.LinAlgError:lm*=10;continue
   candidate=p-step;new=residual(candidate);newscore=new@new
   if newscore<score:
    p=candidate;err=new;delta=score-newscore;score=newscore;lm=max(lm*.35,1e-12)
    if np.linalg.norm(step)<1e-10 or delta<1e-9:break
   else:lm=min(lm*6,1e12)
  R,C,K=decode(p)
  if C[2]<=0:continue
  if best is None or score<best[0]:best=(float(score),R,C,K,iteration+1)
 assert best is not None
 return best

def build():
 from PIL import Image,ImageDraw,ImageFont
 OUT.mkdir(parents=True,exist_ok=True)
 im=Image.open(REFERENCE).convert('RGB');W,H=im.size
 cad=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'));foot=np.array(cad['footprint_outline_m'])
 # Read the top (roof) edge, not the lower blue skirt / wall base. Full image
 # coordinates, 1728x910; west front roof is ~544, its wall base is ~563.
 roof=np.array([[458,329],[488,329],[486,339],[1004,336],[1002,327],[1031,327],
                [1053,444],[1026,444],[1034,484],[1006,484],[1011,506],[983,506],
                [987,531],[458,533],[455,544],[423,544]],dtype=float)
 bases=[(15,[423,563]),(14,[455,562]),(12,[987,549]),(6,[1054,462])]
 roof_world=np.c_[foot,np.full(16,13.4)]
 world=np.r_[roof_world,np.array([[*foot[i],-1.2] for i,p in bases])]
 pixels=np.r_[roof,np.array([p for i,p in bases])]
 Hfit=homography(foot,roof);hp=(Hfit@np.c_[foot,np.ones(16)].T).T;hp=hp[:,:2]/hp[:,2,None]
 score,R,C,K,iterations=fit_camera(world,pixels,Hfit,W,H)
 rotation=(np.diag([1,-1,-1])@R).T
 matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=C
 sy=math.hypot(rotation[0,0],rotation[1,0])
 euler=[math.atan2(rotation[2,1],rotation[2,2]),math.atan2(-rotation[2,0],sy),math.atan2(rotation[1,0],rotation[0,0])]
 result=dict(schema_version=1,reference=str(REFERENCE),reference_sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
  image_dimensions_px=[W,H],coordinate_frame='CAD metres, +X east, +Y north, Z up; pixels origin top-left',
  roof_plane_z_m=13.4,ground_plane_z_m=-1.2,
  intrinsic_matrix=K.tolist(),world_to_cv_camera_rotation=R.tolist(),camera_location_m=C.tolist(),
  blender_camera=dict(location_m=C.tolist(),rotation_euler_xyz_rad=euler,rotation_euler_xyz_deg=np.rad2deg(euler).tolist(),
   matrix_world=matrix.tolist(),type='PERSP',lens_mm=float(K[0,0]*36/W),sensor_width_mm=36,sensor_fit='HORIZONTAL',
   shift_x=float((W/2-K[0,2])/W),shift_y=float((K[1,2]-H/2)/W),pixel_aspect=[1,1],clip_start=.1,clip_end=10000),
  roof_plane_homography_world_to_image=Hfit.tolist(),iterations=iterations,
  fitting_method='Normalized DLT roof homography initialization; multistart finite-difference Levenberg-Marquardt pinhole fit with square pixels; 16 roof corners + 4 visible wall-base checks.',
  limitations=['Manual pixel picks are approximate (typically 1-3px), and AI-generated reference need not obey a single exact perspective camera.',
   'CAD main-building footprint and roof13.4m/ground-1.2m are preserved as the visual scale anchor; other exterior layout is free to follow the reference.',
   'Wall-base points have 0.65 residual weight because lower edges are less certain; principal-point offsets have weak 200px prior, focal has weak log prior to regularize one-view ambiguity.',
   'image_to_ground intersects a ray with a horizontal plane. To place a roof-derived footprint, use z=ground_z+estimated_height; using ground z for roof pixels shifts the building.',
   'This is an art-reference best-fit camera, not photogrammetric survey accuracy. Reprojection residuals remain visible in the diagnostic overlay.'])
 for label,z in [('ground',-1.2),('roof',13.4)]:
  plane=K@np.column_stack([R[:,0],R[:,1],R[:,2]*z-R@C]);plane/=plane[2,2]
  result[label+'_plane_camera_homography_world_to_image']=plane.tolist()
  inverse=np.linalg.inv(plane);inverse/=inverse[2,2]
  result[label+'_plane_camera_homography_image_to_world']=inverse.tolist()
 pred=np.array(project_world_to_image(world,result));errors=np.linalg.norm(pred-pixels,axis=1)
 result['reprojection_error_px']={label:dict(rmse=float(np.sqrt(np.mean(values**2))),mean=float(values.mean()),max=float(values.max())) for label,values in [('roof',errors[:16]),('wall_base',errors[16:]),('all',errors)]}
 herr=np.linalg.norm(hp-roof,axis=1);result['unconstrained_roof_homography_error_px']=dict(rmse=float(np.sqrt(np.mean(herr**2))),max=float(herr.max()))
 result['correspondences']=[dict(id=f'R{i:02}' if i<16 else f'B{bases[i-16][0]:02}',world_m=world[i].tolist(),
  measured_pixel=pixels[i].tolist(),projected_pixel=pred[i].tolist(),error_px=float(errors[i]),kind='roof_corner' if i<16 else 'wall_base') for i in range(len(world))]
 samples=[(400,700,-1.2),(900,800,-1.2),(1100,300,14),(864,455,-1.2)]
 check=[]
 for u,v,z in samples:
  point=image_to_ground(u,v,z,result);back=project_world_to_image(point,result)
  check.append(dict(pixel=[u,v],plane_z_m=z,world_m=point,roundtrip_error_px=float(math.hypot(back[0]-u,back[1]-v))))
 result['mapping_roundtrip_checks']=check
 (OUT/'camera_calibration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 # Scientific diagnostic, not generative editing: original pixels preserved,
 # measured corners yellow, fitted camera corners cyan, residuals magenta.
 annotated=im.copy();d=ImageDraw.Draw(annotated)
 d.line([tuple(p) for p in np.r_[pred[:16],pred[:1]]],fill=(0,225,245),width=2)
 for row in result['correspondences']:
  u,v=row['measured_pixel'];x,y=row['projected_pixel']
  d.line((u,v,x,y),fill=(255,20,180),width=3);d.ellipse((u-3,v-3,u+3,v+3),outline=(255,190,0),width=2)
  d.line((x-3,y,x+3,y),fill=(0,255,255),width=2);d.line((x,y-3,x,y+3),fill=(0,255,255),width=2)
  d.text((u+4,v+4),row['id'],fill=(255,30,30),stroke_width=1,stroke_fill=(255,255,255))
 d.rectangle((12,12,690,87),fill=(13,30,45))
 lines=['MPR reference camera | measured: yellow / fitted: cyan / residual: magenta',
  f'Roof RMS {result["reprojection_error_px"]["roof"]["rmse"]:.2f}px; max {result["reprojection_error_px"]["roof"]["max"]:.2f}px; 16 corners',
  'Main CAD shape retained. AI reference is not guaranteed to be projectively exact.']
 for i,line in enumerate(lines):d.text((22,24+i*20),line,fill='white')
 annotated.save(OUT/'camera_corner_diagnostic.png')
 annotated.crop((390,305,1080,580)).resize((1380,550)).save(OUT/'camera_roof_diagnostic_close.png')
 print(json.dumps({k:result[k] for k in ['blender_camera','reprojection_error_px','unconstrained_roof_homography_error_px']},indent=2))
 return result

if __name__=='__main__':build()
