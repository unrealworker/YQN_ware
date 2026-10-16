"""Detailed AGV modeling helpers; dimensions in metres, front=-X, up=Z."""
import bpy
import math
from mathutils import Vector

MATERIALS={}
COLL=None

def collection(name):
    global COLL
    COLL=bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if COLL.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(COLL)
    return COLL

def finish(obj,name,mat=None):
    obj.name=name
    obj["agv_part"]=True
    if COLL:
        for c in list(obj.users_collection): c.objects.unlink(obj)
        COLL.objects.link(obj)
    if mat: obj.data.materials.append(mat)
    return obj

def material(name,color,roughness=.4,metallic=0,**meta):
    name=name if name.startswith("M_AGV_") else "M_AGV_"+name
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color=(*color[:3],1)
    m.use_nodes=True
    bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value=(*color[:3],1)
    bs.inputs['Roughness'].default_value=roughness
    bs.inputs['Metallic'].default_value=metallic
    if meta.get('emission'):
        bs.inputs['Emission Color'].default_value=(*color[:3],1)
        bs.inputs['Emission Strength'].default_value=meta['emission']
    if name not in MATERIALS:
        MATERIALS[name]=dict(name=name,base_color=[*color[:3],1],roughness=roughness,metallic=metallic,**meta)
    return m

def bevel(obj,width=.002,segments=3):
    if width:
        b=obj.modifiers.new('Manufactured edge radii','BEVEL');b.width=width;b.segments=segments
        b.limit_method='ANGLE'
        n=obj.modifiers.new('Weighted surface normals','WEIGHTED_NORMAL');n.keep_sharp=True;n.weight=50
    return obj

def box(name,loc,size,mat,bevel=.002):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    o=finish(bpy.context.object,name,mat);o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    globals()['bevel'](o,min(bevel,min(size)*.38),3)
    return o

def orient(obj,axis):
    direction={'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1),'-X':(-1,0,0),'-Y':(0,-1,0),'-Z':(0,0,-1)}[axis]
    obj.rotation_euler=Vector(direction).to_track_quat('Z','Y').to_euler()

def cylinder(name,loc,radius,depth,mat,vertices=64,axis='Z'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc)
    o=finish(bpy.context.object,name,mat);orient(o,axis)
    for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
    return o

def torus(name,loc,major,minor,mat,axis='Z',segments=64,minor_segments=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=major,minor_radius=minor,major_segments=segments,minor_segments=minor_segments,location=loc)
    o=finish(bpy.context.object,name,mat);orient(o,axis)
    for p in o.data.polygons:p.use_smooth=True
    return o

def mesh(name,verts,faces,mat):
    d=bpy.data.meshes.new(name);d.from_pydata(verts,[],faces);d.update()
    o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o)
    return finish(o,name,mat)

def rounded_points(length,width,radius,segments=12):
    points=[]
    for cx,cy,a in [(length/2-radius,width/2-radius,0),(-length/2+radius,width/2-radius,90),(-length/2+radius,-width/2+radius,180),(length/2-radius,-width/2+radius,270)]:
        for i in range(segments+1):
            angle=math.radians(a+i*90/segments)
            points.append((cx+radius*math.cos(angle),cy+radius*math.sin(angle)))
    return points

def rounded_box(name,loc,size,radius,mat,edge=.0015):
    outline=rounded_points(size[0],size[1],radius)
    n=len(outline)
    vv=[(x+loc[0],y+loc[1],loc[2]+z) for z in [-size[2]/2,size[2]/2] for x,y in outline]
    ff=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    o=mesh(name,vv,ff,mat)
    for p in o.data.polygons:p.use_smooth=p.index>=2
    return bevel(o,edge,3)

def perimeter_ring(name,length,width,radius,z,height,thickness,mat):
    outer=rounded_points(length,width,radius)
    inner=rounded_points(length-2*thickness,width-2*thickness,max(.005,radius-thickness))
    n=len(outer);vv=[]
    for zz in [z-height/2,z+height/2]:
        vv.extend((x,y,zz) for x,y in outer)
        vv.extend((x,y,zz) for x,y in inner)
    ff=[]
    for i in range(n):
        j=(i+1)%n
        ff.extend([(i,j,2*n+j,2*n+i),(n+j,n+i,3*n+i,3*n+j),
                   (2*n+i,2*n+j,3*n+j,3*n+i),(j,i,n+i,n+j)])
    return bevel(mesh(name,vv,ff,mat),.001,2)

def bolt(name,loc,radius=.004,depth=.002,axis='Z'):
    metal=material('Chrome',(.5,.55,.60),.24,.92)
    dark=material('DarkMetal',(.028,.035,.045),.37,.65)
    o=cylinder(name,loc,radius,depth,metal,vertices=32,axis=axis)
    direction=Vector({'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1),'-X':(-1,0,0),'-Y':(0,-1,0),'-Z':(0,0,-1)}[axis])
    cylinder(name+'_HexSocket',Vector(loc)+direction*(depth*.51),radius*.43,depth*.08,dark,vertices=6,axis=axis)
    return o

def line(name,points,radius,mat):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=1
    curve.bevel_depth=radius;curve.bevel_resolution=3
    s=curve.splines.new('POLY');s.points.add(len(points)-1)
    for p,co in zip(s.points,points):p.co=(*co,1)
    o=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(o)
    return finish(o,name,mat)

def text(name,value,loc,size,mat,normal=(-1,0,0),extrude=.0004):
    d=bpy.data.curves.new(name,'FONT');d.body=value;d.size=size;d.align_x='CENTER';d.align_y='CENTER';d.extrude=extrude;d.bevel_depth=.00015
    o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc
    # Local text X follows world -Y on the front face; local Y is world Z.
    o.rotation_euler=Vector(normal).to_track_quat('Z','Y').to_euler()
    return finish(o,name,mat)
