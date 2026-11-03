"""Fit real orthogonal buildings to uncertain single-image roof evidence.

Only center, size and a Z rotation are inferred. Image quadrilaterals never
deform the physical model. This module has no Blender/UE or filesystem writes.
"""
import math
import numpy as np
from calibrate_mpr_reference_camera import image_to_ground

HOUSE_SPECS={'Cottage':(10,8,3.8,5.9,0),'Garage':(11.2,8.8,4.,6.3,1),'LongGable':(14,8.2,4.2,6.4,2)}


def signed_area(points):
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))/2


def rectangle(center,size,yaw):
    c,s=math.cos(yaw),math.sin(yaw);w,d=size
    return [[center[0]+c*x-s*y,center[1]+s*x+c*y]
            for x,y in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]]


def axis_difference(a,b):
    return abs((a-b+math.pi/2)%math.pi-math.pi/2)


def fit_rectangle(points,street_segments=(),residential=False):
    points=[list(p) for p in points]
    if len(points)!=4:raise ValueError('Rectification only supports four-corner evidence; preserve/decompose genuine L footprints explicitly.')
    if signed_area(points)<0:points=[points[0],points[3],points[2],points[1]]
    q=np.asarray(points);center=q.mean(axis=0)
    u=(q[1]+q[2]-q[0]-q[3])/4;v=(q[2]+q[3]-q[0]-q[1])/4
    # Best orthogonal axes in least-squares sense; unlike a bounding box this
    # does not enclose the entire sheared silhouette and inflate it into strips.
    _,vectors=np.linalg.eigh(np.outer(u,u)-np.outer(v,v));axis=vectors[:,-1]
    if axis@u<0:axis=-axis
    perpendicular=np.array([-axis[1],axis[0]])
    dimensions=2*np.abs([u@axis,v@perpendicular]);yaw=math.atan2(axis[1],axis[0])
    if dimensions[1]>dimensions[0]:dimensions=dimensions[::-1];yaw+=math.pi/2
    original_yaw=yaw;alignment=None
    if residential and street_segments:
        candidates=[]
        for name,a,b in street_segments:
            a,b=np.asarray(a),np.asarray(b);ab=b-a;length=float(np.linalg.norm(ab))
            if length<1:continue
            t=float(np.clip((center-a)@ab/(length*length),0,1));distance=float(np.linalg.norm(center-(a+t*ab)))
            theta=math.atan2(ab[1],ab[0]);choice=min((theta,theta+math.pi/2),key=lambda z:axis_difference(z,yaw))
            candidates.append((distance+.1*math.degrees(axis_difference(choice,yaw)),distance,name,choice))
        _,distance,name,yaw=min(candidates)
        alignment=dict(street=name,distance_m=distance,rotation_from_rectangular_fit_deg=math.degrees(axis_difference(yaw,original_yaw)),source='Existing traced street direction only; no position relocation to road V5.')
    source_area=abs(signed_area(points));ratio=float(dimensions[0]/max(dimensions[1],1e-8))
    # A handful of tiny segmented fragments cannot define viable dwellings.
    # Keep sane proportions rather than preserving their accidental thinness.
    ratio=max(1.05,min(2.6,ratio)) if residential else max(1.,min(5.,ratio))
    size=[math.sqrt(source_area*ratio),math.sqrt(source_area/ratio)]
    if residential:size=[max(7.,min(34.,size[0])),max(5.5,min(25.,size[1]))]
    return dict(center_m=center.tolist(),size_m=size,yaw_deg=math.degrees(yaw)%180,
                footprint_m=rectangle(center.tolist(),size,yaw),source_area_m2=source_area,
                area_m2=size[0]*size[1],source_footprint_m=points,street_alignment=alignment,
                center_shift_m=0.,area_ratio=size[0]*size[1]/source_area)


def infer_layout(layout,calibration):
    ground=calibration['ground_plane_z_m'];segments=[];placements={}
    for street in layout.get('residential_streets',[]):
        pts=[image_to_ground(*p,z=ground,calibration=calibration)[:2] for p in street['points']]
        segments.extend((street['name'],a,b) for a,b in zip(pts,pts[1:]))
    for index,row in enumerate(layout['buildings']):
        if row['id'].startswith('rail_service_shed_'):continue
        height=row['estimated_height_m'];points=[image_to_ground(*p,z=ground+height,calibration=calibration)[:2] for p in row['pixel_outline']]
        style=None
        if row['type']=='house_gable':
            pixels=list(row['pixel_outline'])
            if math.dist(pixels[0],pixels[1])<math.dist(pixels[1],pixels[2]):pixels=pixels[1:]+pixels[:1]
            short_world=min(math.dist(points[i],points[(i+1)%4]) for i in range(4));height=max(5.6,min(13.,short_world*.50))
            style='LongGable' if math.dist(pixels[0],pixels[1])/max(math.dist(pixels[1],pixels[2]),1)>1.65 else ('Garage' if index%3==1 else 'Cottage')
            w,d,e,r,v=HOUSE_SPECS[style]
            points=[image_to_ground(*p,z=ground+height*e/r,calibration=calibration)[:2] for p in pixels]
        frame=fit_rectangle(points,segments,row['type']=='house_gable')
        frame.update(id=row['id'],type=row['type'],height_m=height,style=style)
        placements[row['id']]=frame
    return placements


def transform_vertex(vertex,frame,prototype_width,prototype_depth,prototype_height,ground):
    x,y,z=vertex;w,d=frame['size_m'];angle=math.radians(frame['yaw_deg']);c,s=math.cos(angle),math.sin(angle)
    px=x*w/prototype_width;py=y*d/prototype_depth;cx,cy=frame['center_m']
    return (cx+c*px-s*py,cy+s*px+c*py,ground+z*frame['height_m']/prototype_height)


def hull(points):
    points=sorted(set(map(tuple,points)))
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];hi=[]
    for p in points:
        while len(lo)>1 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(points):
        while len(hi)>1 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return lo[:-1]+hi[:-1]


def outline_rectangle(points,residential=False,center=None):
    """Regularize a traced plan contour; preserve area without affine shear."""
    q=np.array(points,float);convex=hull(points);best=None
    for a,b in zip(convex,convex[1:]+convex[:1]):
        angle=math.atan2(b[1]-a[1],b[0]-a[0]);c,s=math.cos(angle),math.sin(angle)
        rotation=np.array([[c,-s],[s,c]]);local=q@rotation
        lo=local.min(axis=0);hi=local.max(axis=0);size=hi-lo;area=float(np.prod(size))
        if best is None or area<best[0]:best=area,(lo+hi)/2@rotation.T,size,angle
    _,fitted_center,size,angle=best
    if size[1]>size[0]:size=size[::-1];angle+=math.pi/2
    actual_area=abs(signed_area([list(p)for p in points]));size=size*math.sqrt(actual_area/max(float(np.prod(size)),1e-9))
    fitted_center=list(center) if center is not None else fitted_center.tolist()
    ratio=float(size[0]/size[1]);ratio=max(1.05,min(2.6,ratio)) if residential else max(1.,min(8.,ratio))
    size=[math.sqrt(actual_area*ratio),math.sqrt(actual_area/ratio)]
    if residential:size=[max(6.,min(32.,size[0])),max(5.,min(24.,size[1]))]
    return dict(center_m=fitted_center,size_m=size,yaw_deg=math.degrees(angle)%180,
                footprint_m=rectangle(fitted_center,size,angle),area_m2=size[0]*size[1],source_area_m2=actual_area,
                area_ratio=size[0]*size[1]/actual_area,source_footprint_m=[list(p)for p in points])


def infer_plan_layout(layout):
    from mpr_plan_layout import plan_to_world
    placements={}
    for i,row in enumerate(layout['houses']+layout['industrial']):
        world=[p[:2]for p in plan_to_world(row['pixel_outline'])]
        if row['type'] in ('orthogonal_l_industrial','warehouse_deep_docks'):
            # Plan registration is axis-aligned; real re-entrant corners stay.
            frame=dict(footprint_m=world,center_m=np.mean(world,axis=0).tolist(),size_m=None,yaw_deg=0.,
                       area_m2=abs(signed_area(world)),source_area_m2=abs(signed_area(world)),area_ratio=1.,source_footprint_m=world)
        else:
            center=plan_to_world(row.get('pixel_center',np.mean(row['pixel_outline'],axis=0).tolist()))[:2]
            frame=outline_rectangle(world,row['type']=='house_gable',center)
        frame.update(id=row['id'],type=row['type'],height_m=row.get('estimated_height_m',6.3 if i%3==1 else 5.9),
                     style=('Garage' if i%3==1 else 'Cottage') if row['type']=='house_gable' else None,
                     placement_method='Registered orthographic plan; orthogonal physical axes only, no perspective inverse or quad warp')
        placements[row['id']]=frame
    # Keep distinct neighbouring dwellings separated after regularizing raster
    # corners. Preserve centers; only shrink the two affected local rectangles.
    houses=[f for f in placements.values() if f['type']=='house_gable']
    for _ in range(8):
        changed=False
        for i,a in enumerate(houses):
            for b in houses[i+1:]:
                delta=np.array(b['center_m'])-a['center_m'];axes=[]
                for frame in (a,b):
                    yaw=math.radians(frame['yaw_deg']);axes.extend([np.array([math.cos(yaw),math.sin(yaw)]),np.array([-math.sin(yaw),math.cos(yaw)])])
                ratios=[]
                for axis in axes:
                    support=0.
                    for frame in (a,b):
                        yaw=math.radians(frame['yaw_deg']);u=np.array([math.cos(yaw),math.sin(yaw)]);v=np.array([-u[1],u[0]])
                        support+=(abs(axis@u)*frame['size_m'][0]+abs(axis@v)*frame['size_m'][1])/2
                    ratios.append((abs(delta@axis)-3.0)/max(support,1e-8))
                factor=max(ratios)
                if factor<1:
                    factor=max(.5,factor)
                    for frame in (a,b):
                        frame['size_m']=[v*factor for v in frame['size_m']];frame['footprint_m']=rectangle(frame['center_m'],frame['size_m'],math.radians(frame['yaw_deg']))
                        frame['area_m2']=math.prod(frame['size_m']);frame['area_ratio']=frame['area_m2']/frame['source_area_m2'];frame['separation_scale']=frame.get('separation_scale',1.)*factor
                    changed=True
        if not changed:break
    return placements
