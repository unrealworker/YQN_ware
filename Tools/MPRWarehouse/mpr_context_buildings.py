"""Quiet GHS-style context buildings on the unmodified CADMapper footprints.

This module emits geometry through the caller's environment API. It has no bpy,
file-write or UE side effects. All heights and facade details are visual
reconstruction, not surveyed dimensions. Building 1583 is always excluded.
"""
import math
from collections import Counter


MATERIALS = {
    'ContextRoof': {'color_linear': [.24, .31, .37], 'roughness': .82},
    'ContextWall': {'color_linear': [.60, .66, .69], 'roughness': .82},
    'ContextTrim': {'color_linear': [.39, .46, .50], 'roughness': .85},
    'ContextGlass': {'color_linear': [.16, .23, .30], 'roughness': .50},
}


def _area(points):
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))*.5


def _inside(point, outline):
    x,y=point; result=False
    for a,b in zip(outline,outline[1:]+outline[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            result=not result
    return result


def _frame(outline):
    a,b=max(zip(outline,outline[1:]+outline[:1]),key=lambda e:math.dist(*e))
    length=math.dist(a,b);u=((b[0]-a[0])/length,(b[1]-a[1])/length);v=(-u[1],u[0])
    projected=[(p[0]*u[0]+p[1]*u[1],p[0]*v[0]+p[1]*v[1]) for p in outline]
    bounds=(min(p[0] for p in projected),max(p[0] for p in projected),min(p[1] for p in projected),max(p[1] for p in projected))
    def world(x,y):return (x*u[0]+y*v[0],x*u[1]+y*v[1])
    return u,v,bounds,world


def _clip_half(points, direction, cut, keep_positive):
    """Clip one convex source roof triangle against its gable ridge plane."""
    result=[]
    for a,b in zip(points,points[1:]+points[:1]):
        da=a[0]*direction[0]+a[1]*direction[1]-cut
        db=b[0]*direction[0]+b[1]*direction[1]-cut
        ai=da>=-1e-8 if keep_positive else da<=1e-8
        bi=db>=-1e-8 if keep_positive else db<=1e-8
        if ai:result.append(a)
        if ai!=bi:
            t=da/(da-db);result.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
    return result


def _cut_line(outline, u, v, along, fixed):
    """Return the inside spans of a roof seam without crossing footprint gaps."""
    hits=[]
    for a,b in zip(outline,outline[1:]+outline[:1]):
        aa=(a[0]*u[0]+a[1]*u[1],a[0]*v[0]+a[1]*v[1])
        bb=(b[0]*u[0]+b[1]*u[1],b[0]*v[0]+b[1]*v[1])
        cross=1-along
        if (aa[cross]>fixed)!=(bb[cross]>fixed):
            t=(fixed-aa[cross])/(bb[cross]-aa[cross])
            hits.append(aa[along]+t*(bb[along]-aa[along]))
    hits.sort()
    return [(a+.4,b-.4) for a,b in zip(hits[::2],hits[1::2]) if b-a>.8]


def build_context_buildings(api, source, ground_z):
    """Emit the 140 source context buildings and return footprints plus audit.

    api may be a dict or namespace, exposing the environment builder's mesh,
    poly, box, strip and zone methods; box yaw is radians. source is the parsed
    environment_local.json. Returned footprints are original XY polygons and
    are suitable for tree exclusion. Up to four roles are used per merged batch.
    """
    get=lambda name:api[name] if isinstance(api,dict) else getattr(api,name)
    mesh,poly,box,strip,zone=[get(key) for key in ('mesh','poly','box','strip','zone')]
    counts=Counter();footprints=[];audit=[]
    for item in source['meshes']:
        if item['layer']!='buildings' or item['id']=='1583':continue
        vertices=item['vertices'];loops=item.get('footprintLoops') or []
        if not loops:continue
        assert len(loops)==1,('Unexpected courtyard: preserve all loops explicitly',item['id'])
        indices=list(loops[0])
        if indices[0]==indices[-1]:indices.pop()
        outline=[tuple(vertices[i][:2]) for i in indices]
        if _area(outline)<0:outline.reverse()
        footprints.append(outline)
        area=abs(_area(outline));cx=sum(p[0] for p in outline)/len(outline);cy=sum(p[1] for p in outline)/len(outline)
        region=zone(cx,cy);name='SM_MPR_Env_'+region+'_Buildings'
        neighbor=item['id']=='1582';industrial=area>1000
        u,v,bounds,world=_frame(outline);xmin,xmax,ymin,ymax=bounds
        width=ymax-ymin;depth=xmax-xmin;ridge=(ymin+ymax)*.5
        rectangularity=area/max(1e-8,width*depth)
        # The supplied aerial shows compact pitched houses west of the campus.
        # Complex/school/industrial outlines retain their exact flat roofs.
        pitched=not industrial and area<450 and len(outline)<=10 and rectangularity>.78
        height=14. if neighbor else 9. if industrial else 5.7 if area>70 else 3.2
        rise=min(1.6,width*.18) if pitched else 0.
        eave=ground_z+height
        def top(point):
            return eave+rise*max(0.,1.-abs(point[0]*v[0]+point[1]*v[1]-ridge)/max(width*.5,1e-8))
        if pitched:
            zmax=max(p[2] for p in vertices)
            faces=[face for face in item['faces'] if all(abs(vertices[i][2]-zmax)<.001 for i in face)]
            assert faces,('Missing source roof triangulation',item['id'])
            for face in faces:
                for side in (False,True):
                    points=_clip_half([vertices[i][:2] for i in face],v,ridge,side)
                    if len(points)<3 or abs(_area(points))<1e-8:continue
                    if _area(points)<0:points.reverse()
                    mesh(name,'ContextRoof',[(p[0],p[1],top(p)) for p in points],[tuple(range(len(points)))])
            counts['pitched_context_roofs']+=1
        else:poly(name,'ContextRoof',outline,eave)
        for a,b in zip(outline,outline[1:]+outline[:1]):
            length=math.dist(a,b)
            if length<1e-6:continue
            tx,ty=(b[0]-a[0])/length,(b[1]-a[1])/length;nx,ny=ty,-tx
            wall=[a,b]
            da=a[0]*v[0]+a[1]*v[1]-ridge;db=b[0]*v[0]+b[1]*v[1]-ridge
            if pitched and da*db<0:
                t=da/(da-db);wall.insert(1,(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
            for p,q in zip(wall,wall[1:]):
                mesh(name,'ContextWall',[(p[0],p[1],ground_z),(q[0],q[1],ground_z),(q[0],q[1],top(q)),(p[0],p[1],top(p))],[(0,1,2,3)])
            if industrial:
                # Low parapet is inset, so the surveyed outer footprint stays put.
                inset=.12;center=((a[0]+b[0])*.5-nx*inset,(a[1]+b[1])*.5-ny*inset,eave+.08)
                box(name,'ContextTrim',center,(length,.18,.16),math.atan2(ty,tx))
                # Flat facade joint strips add rhythm at negligible geometry cost.
                pitch=8.5 if neighbor else 12.
                for k in range(1,math.ceil(length/pitch)):
                    s=length*k/math.ceil(length/pitch);x=a[0]+tx*s+nx*.025;y=a[1]+ty*s+ny*.025
                    mesh(name,'ContextTrim',[(x-tx*.035,y-ty*.035,ground_z+.22),(x+tx*.035,y+ty*.035,ground_z+.22),
                         (x+tx*.035,y+ty*.035,eave-.18),(x-tx*.035,y-ty*.035,eave-.18)],[(0,1,2,3)])
                    counts['facade_joint_strips']+=1
                # Only the immediate neighbor receives loading-bay rhythm. The
                # main-warehouse facing wall is selected from its actual normal.
                toward=(-cx,-cy);facing=nx*toward[0]+ny*toward[1]>0
                if neighbor and length>200 and facing:
                    n=min(26,int(length/14))
                    for k in range(n):
                        s=8+(length-16)*(k+.5)/n;x=a[0]+tx*s+nx*.045;y=a[1]+ty*s+ny*.045
                        half=1.45;z0=ground_z+1.1;z1=z0+3.2
                        mesh(name,'ContextGlass',[(x-tx*half,y-ty*half,z0),(x+tx*half,y+ty*half,z0),
                             (x+tx*half,y+ty*half,z1),(x-tx*half,y-ty*half,z1)],[(0,1,2,3)])
                        counts['neighbor_loading_bay_silhouettes']+=1
            elif area>70 and length>6 and region=='Near':
                # Sparse small window silhouettes; no bright random facade noise.
                x=(a[0]+b[0])*.5+nx*.025;y=(a[1]+b[1])*.5+ny*.025
                mesh(name,'ContextGlass',[(x-tx*.55,y-ty*.55,ground_z+2.8),(x+tx*.55,y+ty*.55,ground_z+2.8),
                     (x+tx*.55,y+ty*.55,ground_z+4.0),(x-tx*.55,y-ty*.55,ground_z+4.0)],[(0,1,2,3)])
                counts['residential_window_silhouettes']+=1
        if neighbor or area>10000:
            # Wide roof fields remain quiet: 12/5 seams and only 4/2 small units.
            seam_count=12 if neighbor else 5
            for k in range(1,seam_count+1):
                x=xmin+depth*k/(seam_count+1)
                for lo,hi in _cut_line(outline,u,v,1,x):
                    strip(name,'ContextTrim',world(x,lo),world(x,hi),.09,eave+.025)
                    counts['roof_seam_spans']+=1
            equipment_count=4 if neighbor else 2
            for k in range(equipment_count):
                x=xmin+depth*(k+1)/(equipment_count+1);y=ymin+width*.73;p=world(x,y)
                corners=[world(x+dx,y+dy) for dx in (-1.2,1.2) for dy in (-.85,.85)]
                if not all(_inside(q,outline) for q in corners):continue
                box(name,'ContextWall',(p[0],p[1],eave+.30),(2.4,1.7,.60),math.atan2(u[1],u[0]))
                box(name,'ContextTrim',(p[0],p[1],eave+.615),(2.20,1.50,.03),math.atan2(u[1],u[0]))
                counts['context_rooftop_units']+=1
        counts['source_context_buildings']+=1
        counts['industrial_context_buildings' if industrial else 'residential_or_small_context_buildings']+=1
        audit.append({'source_id':item['id'],'region':region,'footprint_m2':round(area,3),'height_m':height,
                      'roof_rise_m':round(rise,3),'roof_type':'source-footprint gable' if pitched else 'flat',
                      'outline_preserved':True,'height_and_details':'reference-derived display estimate'})
    return {'footprints':footprints,'counts':dict(counts),'buildings':audit,'material_roles':list(MATERIALS)}
