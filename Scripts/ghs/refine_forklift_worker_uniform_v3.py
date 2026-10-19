"""Reference uniform: red cap hardhat, dark work suit, yellow reflective tape.

Edits the seated operator only; uses local materials to preserve the forklift.
"""
import bpy, ast, math, json, bmesh
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(r'D:/UEPro/Test')
scene=bpy.context.scene
assert scene.name=='GHS_MannedForklift_Studio'
collection=bpy.data.collections['05_Driver']
root=bpy.data.objects['MF_Root']
assert not root.get('WorkerUniformV3',False),'Uniform V3 already applied; edit incrementally.'
made=[]
materials={}
spec={
    'Cloth':((.030,.043,.064),.86,0),
    'Navy':((.026,.038,.057),.88,0),
    'Seam':((.022,.031,.047),.83,0),
    'Tape':((.78,.62,.025),.50,0),
    'TapeCore':((.64,.62,.34),.48,.05),
    'Helmet':((.50,.016,.024),.39,.02),
    'Skin':((.47,.285,.20),.68,0),
    'Dark':((.014,.018,.024),.73,0),
    'Rubber':((.020,.024,.029),.88,0),
    'Metal':((.12,.15,.19),.43,.4),
    'BadgeWhite':((.59,.61,.61),.70,0),
    'BadgeRed':((.30,.03,.035),.70,0),
}
for role,(color,rough,metal) in spec.items():
    name='M_MF_WorkerV3_'+role
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes=True;m.diffuse_color=(*color,1)
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
    if role in {'Cloth','Navy','Seam'}:
        tex=m.node_tree.nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=180
        tex.inputs['Detail'].default_value=2
        bump=m.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.13;bump.inputs['Distance'].default_value=.00045
        m.node_tree.links.new(tex.outputs['Fac'],bump.inputs['Height']);m.node_tree.links.new(bump.outputs['Normal'],p.inputs['Normal'])
    materials[role]=m

# Reuse modelling helpers without running the original builder or duplicating the scene.
tree=ast.parse((ROOT/'Scripts/ghs/build_forklift_driver.py').read_text(encoding='utf8'))
builder=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_driver')
exec(compile(ast.Module(body=[n for n in builder.body if isinstance(n,ast.FunctionDef)],type_ignores=[]),'<worker helpers>','exec'))

def assign(obj,role):
    obj.data.materials.clear();obj.data.materials.append(materials[role])

for o in list(collection.objects):
    n=o.name
    # The reference wears a work jacket, not a separate orange high-vis vest.
    if any(w in n for w in ['Vest','ZipperPull','JacketCollar','CollarFold','TrouserReflective','HelmetFrontSafetyMark','GloveBack','ElbowPatch','SleeveSeam','KneeCrease']):
        bpy.data.objects.remove(o,do_unlink=True);continue
    if 'Helmet' in n and not any(w in n for w in ['Strap','Suspension']):assign(o,'Helmet')
    elif any(w in n for w in ['Trouser','CargoPocket','PocketFlap']):assign(o,'Navy')
    elif any(w in n for w in ['WorkJacket','Sleeve','JacketWaist']):assign(o,'Cloth')
    elif 'Glove' in n or n in ['DRV_Neck','DRV_Head','DRV_Nose'] or any(w in n for w in ['Ear','LowerLip']):assign(o,'Skin')
    elif 'Boot' in n or 'Lace' in n:assign(o,'Rubber')

# Small controlled folds in the actual garment surface, strongest at bent joints.
def garment_folds(name,sides,rings,kind):
    o=bpy.data.objects[name]
    assert len(o.data.vertices)==sides*rings+2
    for j in range(rings):
        t=j/(rings-1)
        row=[o.data.vertices[j*sides+i] for i in range(sides)]
        cen=sum((v.co for v in row),Vector())/sides
        for i,v in enumerate(row):
            a=math.tau*i/sides;d=v.co-cen
            if kind=='torso':
                amp=.018*math.exp(-((t-.22)/.24)**2)
                factor=1+amp*math.sin(a*7+t*12)+.012*math.exp(-((t-.72)/.20)**2)*math.cos(a*5-t*5)
            else:
                centre=.52 if kind=='arm' else .48
                envelope=math.exp(-((t-centre)/.21)**2)*math.sin(math.pi*t)**2
                factor=1+envelope*(.033*math.sin(5*a+23*t)+.020*math.sin(3*a-37*t))
            v.co=cen+d*factor
    o.data.update()

garment_folds('DRV_WorkJacket',48,19,'torso')
for side in ['Left','Right']:
    garment_folds('DRV_'+side+'Sleeve',32,22,'arm')
    garment_folds('DRV_'+side+'TrouserLeg',32,22,'leg')

# Surface projection gives pockets, tape and seams the same curvature as the jacket.
jacket=bpy.data.objects['DRV_WorkJacket']
verts=[jacket.matrix_world@v.co for v in jacket.data.vertices]
bvh=BVHTree.FromPolygons(verts,[tuple(p.vertices) for p in jacket.data.polygons])
def front_point(y,z,offset=.002):
    hit=bvh.ray_cast(Vector((.2,y,z)),Vector((-1,0,0)),2.0)[0]
    if hit is None:raise ValueError('Jacket projection missed '+str((y,z)))
    return (hit.x+offset,y,z)

def panel(name,y0,y1,z0,z1,role,bulge=.0008,steps=12):
    vs=[];nz=6
    for j in range(nz+1):
        v=j/nz;z=z0+(z1-z0)*v
        for i in range(steps+1):
            u=i/steps;y=y0+(y1-y0)*u
            lift=.002+bulge*math.sin(math.pi*u)*math.sin(math.pi*v)
            vs.append(front_point(y,z,lift))
    fs=[(j*(steps+1)+i,j*(steps+1)+i+1,(j+1)*(steps+1)+i+1,(j+1)*(steps+1)+i) for j in range(nz) for i in range(steps)]
    o=mesh('V3_'+name,vs,fs,role)
    so=o.modifiers.new('Cloth panel thickness','SOLIDIFY');so.thickness=.0012
    return o

for side,sgn in [('Right',-1),('Left',1)]:
    y0,y1=sorted([sgn*.024,sgn*.152])
    # Two horizontal chest tapes, split at the centre zip.
    for k,z in enumerate([1.494,1.521]):
        panel(side+'ChestTape'+str(k),*sorted([sgn*.011,sgn*.168]),z,z+.014,'Tape',.0001)
        panel(side+'ChestTapeCore'+str(k),*sorted([sgn*.011,sgn*.167]),z+.005,z+.0085,'TapeCore',.0015)
    # Soft shaped patch pockets and modest pointed flaps below the tape.
    panel(side+'ChestPocket',y0,y1,1.356,1.474,'Cloth',.005)
    pp=[front_point(y0,1.478,.006),front_point(y1,1.478,.006),front_point(y1,1.459,.008),
        front_point((y0+y1)/2,1.449,.009),front_point(y0,1.459,.008)]
    patch('V3_'+side+'PocketFlap',pp,'Cloth',.0018)
    tube('V3_'+side+'PocketStitch',[front_point(y0+.004,1.466,.007),front_point(y0+.004,1.36,.0035),
         front_point(y1-.004,1.36,.0035),front_point(y1-.004,1.466,.007)],.0008,'Seam',6)
    p=front_point((y0+y1)/2,1.459,.011)
    ellipsoid('V3_'+side+'PocketSnap',p,(.0015,.0035,.0035),'Dark',12,6)

# Central placket and actual turned-down collar replace the stand-up vest collar.
panel('JacketPlacket',-.010,.010,1.178,1.59,'Seam',.0008)
tube('V3_ZipSeam',[front_point(0,1.18+i*.40/28,.0045) for i in range(29)],.0009,'Metal',6)
loft('V3_CollarStand',[((-.43,0,1.614),.079,.074),((-.425,0,1.65),.067,.066)],'Cloth',32)
for side,sgn in [('Right',-1),('Left',1)]:
    pp=[(-.354,sgn*.007,1.65),(-.365,sgn*.071,1.644),
        front_point(sgn*.100,1.605,.006),front_point(sgn*.052,1.584,.009),
        front_point(sgn*.024,1.622,.006)]
    patch('V3_'+side+'TurnDownCollar',pp,'Cloth',.003)

# Tape wraps the existing bent forearm geometry rather than floating as a rigid ring.
def sleeve_band(side,fraction0,fraction1,role,label,lift=.0018):
    o=bpy.data.objects['DRV_'+side+'Sleeve'];N=32;rows=22
    source=[[o.data.vertices[j*N+i].co.copy() for i in range(N)] for j in range(rows)]
    vs=[];sections=6
    for j in range(sections+1):
        t=(fraction0+(fraction1-fraction0)*j/sections)*(rows-1)
        a=min(int(t),rows-2);f=t-a
        ring=[source[a][i].lerp(source[a+1][i],f) for i in range(N)]
        cen=sum(ring,Vector())/N
        for p in ring:vs.append(p+(p-cen).normalized()*lift)
    fs=[(j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i) for j in range(sections) for i in range(N)]
    ob=mesh('V3_'+side+label,vs,fs,role)
    mod=ob.modifiers.new('Tape backing','SOLIDIFY');mod.thickness=.0008
for side in ['Right','Left']:
    for k,(a,b) in enumerate([(.572,.612),(.643,.683)]):
        sleeve_band(side,a,b,'Tape','SleeveTape'+str(k))
        sleeve_band(side,a+.014,b-.014,'TapeCore','SleeveTapeCore'+str(k),.0028)

# Small generic round uniform badge in the reference position, without inventing a brand.
cy,cz=.103,1.568
for name,r,role,lift in [('BadgeEdge',.018,'BadgeRed',.004),('BadgeFace',.014,'BadgeWhite',.005)]:
    pts=[front_point(cy,cz,lift)]+[front_point(cy+r*math.cos(i*math.tau/48),cz+r*math.sin(i*math.tau/48),lift) for i in range(48)]
    mesh('V3_'+name,pts,[(0,i+1,(i+1)%48+1) for i in range(48)],role)
panel('BadgeMark',cy-.002,cy+.002,cz-.008,cz+.008,'BadgeRed',.004)

# Cap style hardhat: a shorter rear rim and less lateral overhang than the old full brim.
o=bpy.data.objects['DRV_SafetyHelmetBrim']
for v in o.data.vertices:
    v.co.y*=.91
    if v.co.x<-.416:v.co.x=-.416+(v.co.x+.416)*.80
o.data.update()
for o in collection.objects:
    if o.parent is None:o.parent=root
    if o.type=='MESH':
        bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free();o.data.update()
root['WorkerUniformV3']=True
bpy.context.view_layer.update()
print('WORKER_REFERENCE_UNIFORM',len(collection.objects),'parts;',len(made),'new uniform detail pieces')
