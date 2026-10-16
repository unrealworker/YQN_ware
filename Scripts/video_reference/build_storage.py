"""Editable storage kit reconstructed from the blue warehouse video reference.

Run with Blender --background --python build_storage.py. Metres, Z up;
front is +Y in Blender (south/-Y after the project's UE import conversion).
"""
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *

reset()

# Distinct storage-prefixed identifiers ensure manifests from separate libraries
# can be combined without silently replacing a material with different values.
steel = material('StorageSteel', (.075, .145, .235), .34, .72)
steel_light = material('StorageSteelLight', (.24, .33, .44), .32, .62)
dark = material('StorageCharcoal', (.018, .035, .065), .62, .15)
blue = material('StoragePalletBlue', (.015, .18, .44), .4, .28)
cargo = material('StorageCargoBlue', (.18, .29, .46), .58, .08)
cyan = material('StorageCargoGrid', (.12, .64, .84), .42, .12, emission=.28)
bin_blue = material('StorageBinBlue', (.12, .22, .37), .58, .12)
bin_inner = material('StorageBinInner', (.035, .07, .13), .72, .08)
ghost = material('StorageGhostEnvelope', (.10, .23, .40), .45, .08, opacity=.075)
pad_base = material('StoragePadBase', (.095, .115, .15), .82)
pad_line = material('StoragePadBorder', (.37, .43, .50), .72)
pad_text = material('StoragePadText', (.46, .51, .57), .76)
green = material('StorageAPGreen', (.12, .63, .28), .65, emission=.22)
roller = material('StorageRoller', (.22, .34, .44), .28, .75)
roller_end = material('StorageRollerEnd', (.045, .085, .13), .42, .6)


def stripe(name, a, b, width, mat):
    """Flat rectangle in XY, useful for floor markings without round tubes."""
    ax, ay, az = a
    bx, by, bz = b
    dx, dy = bx-ax, by-ay
    length = math.hypot(dx, dy)
    nx, ny = -dy/length*width/2, dx/length*width/2
    return mesh(name, [(ax+nx, ay+ny, az), (ax-nx, ay-ny, az),
                       (bx-nx, by-ny, bz), (bx+nx, by+ny, bz)], [(0,1,2,3)], mat)


def pad_base_mesh():
    # Entire pad measures 1.18m square and rests precisely at ground zero.
    box('Recessed location square', (0,0,.003), (1.18,1.18,.006), pad_base, .001)
    for x in [-.582, .582]:
        box('Location vertical border', (x,0,.007), (.016,1.18,.002), pad_line, 0)
    for y in [-.582, .582]:
        box('Location horizontal border', (0,y,.007), (1.18,.016,.002), pad_line, 0)


def floor_label(name, body, x, y, size, mat):
    obj = text(name, body, (x,y,.009), size, mat, rotation=(0,0,math.pi))
    obj.data.align_y = 'CENTER'
    return obj


begin_asset('SM_VR_PalletCargo')
# Three continuous runners, nine blocks and eight deck boards. Spaces between
# runners/blocks are actual fork openings, with no dark solid box filling them.
for x in [-.535,0,.535]:
    box('Pallet bottom runner', (x,0,.018), (.13,1.0,.036), blue, .008)
    for y in [-.40,0,.40]:
        box('Pallet spacer block', (x,y,.079), (.13,.16,.086), blue, .009)
for i in range(8):
    y=-.45+i*.9/7
    box('Pallet upper deck slat', (0,y,.143), (1.2,.10,.042), blue, .006)
for x in [-.585,.585]:
    box('Pallet side rim', (x,0,.145), (.03,1.0,.05), blue, .004)
# A cubic cargo silhouette retains solid faces. Fine cyan exterior joints make
# the characteristic three-by-three-by-three reference grid visible at distance.
base_z=.173
cube=(1.16/3,.96/3,.90/3)
for ix in range(3):
    for iy in range(3):
        for iz in range(3):
            box('Solid cargo cube', ((ix-1)*cube[0],(iy-1)*cube[1],base_z+(iz+.5)*cube[2]),
                (cube[0]-.003,cube[1]-.003,cube[2]-.003),cargo,.004)
for z in [base_z+i*.3 for i in range(4)]:
    curve('Cyan horizontal cargo seam', [(-.58,-.48,z),(.58,-.48,z),(.58,.48,z),(-.58,.48,z)],.0035,cyan,True)
for x in [-.58,-.58+1.16/3,-.58+2*1.16/3,.58]:
    for y in [-.48,.48]:
        beam('Cyan front cargo seam',(x,y,base_z),(x,y,base_z+.9),.0035,cyan,6)
    stripe('Cyan top X grid',(x,-.48,base_z+.9),(x,.48,base_z+.9),.006,cyan)
for y in [-.48,-.16,.16,.48]:
    for x in [-.58,.58]:
        beam('Cyan side cargo seam',(x,y,base_z),(x,y,base_z+.9),.0035,cyan,6)
    stripe('Cyan top Y grid',(-.58,y,base_z+.9),(.58,y,base_z+.9),.006,cyan)


begin_asset('SM_VR_RackBay')
# Four flange-like upright rails, exact nominal 1.50 x .85 x 2.80m envelope.
for x in [-.726,.726]:
    for y in [-.401,.401]:
        box('Rack upright web',(x,y,1.4),(.024,.048,2.8),steel,.003)
        box('Rack upright flange',(x,y,1.4),(.048,.018,2.8),steel_light,.002)
        box('Rack foot plate',(x,y,.012),(.048,.048,.024),steel_light,.002)
        for z in [.2,.5,.8,1.1,1.4,1.7,2.0,2.3,2.6]:
            box('Upright perforation',(x,y+.025,z),(.009,.002,.028),dark,0)
    # Side cross braces remain visible through the blue bin silhouettes.
    for za,zb in [(.10,1.37),(1.39,2.73)]:
        beam('Rack side diagonal',(x,-.375,za),(x,.375,zb),.008,steel_light,6)
        beam('Rack side return diagonal',(x,.375,za),(x,-.375,zb),.006,steel,6)
for level in [.35,.95,1.55,2.15]:
    for y in [-.37,.37]:
        box('Shelf front back channel',(0,y,level-.035),(1.45,.045,.07),steel,.003)
    box('Shelf thin steel deck',(0,0,level-.004),(1.44,.72,.016),steel_light,.002)
    for x in [-.475,0,.475]:
        # The bin consists of a floor, two sides and a back wall; the low front
        # lip exposes a genuinely recessed dark inside rather than a solid cube.
        width=.435
        depth=.65
        z=level+.016
        box('Bin recessed dark floor',(x,0,z+.012),(width,depth,.024),bin_inner,.002)
        for sx in [-1,1]:
            box('Bin tall side wall',(x+sx*(width/2-.012),0,z+.20),(.024,depth,.40),bin_blue,.003)
        box('Bin back wall',(x,-depth/2+.012,z+.20),(width,.024,.40),bin_blue,.003)
        box('Bin low front lip',(x,depth/2-.012,z+.105),(width,.024,.21),bin_blue,.003)
        box('Bin front stiffener',(x,depth/2+.001,z+.07),(width,.014,.025),cargo,.002)
        for sx in [-1,1]:
            box('Bin rim rail',(x+sx*(width/2-.012),0,z+.403),(.033,depth,.016),cargo,.002)
        box('Bin rear rim',(x,-depth/2+.012,z+.403),(width,.032,.016),cargo,.002)
        # Dark inset handle badge on the front reinforces the recessed opening.
        box('Bin inset handle',(x,depth/2+.001,z+.145),(.115,.003,.033),bin_inner,.003)
for y in [-.401,.401]:
    box('Rack crown beam',(0,y,2.771),(1.5,.048,.058),steel_light,.003)
for x in [-.726,.726]:
    box('Rack crown side',(x,0,2.771),(.048,.85,.058),steel_light,.003)
# Two sheets only: low-opacity holographic envelope with exposed front/bottom.
mesh('Rack ghost back plane',[(-.747,-.423,0),(.747,-.423,0),(.747,-.423,2.799),(-.747,-.423,2.799)],[(0,1,2,3)],ghost)
mesh('Rack ghost roof plane',[(-.747,-.423,2.799),(.747,-.423,2.799),(.747,.423,2.799),(-.747,.423,2.799)],[(0,1,2,3)],ghost)


begin_asset('SM_VR_LM_Pad')
pad_base_mesh()
floor_label('LM floor text','LM',0,-.18,.30,pad_text)
floor_label('14 floor number','14',0,.16,.25,pad_text)


begin_asset('SM_VR_AP_Pad')
pad_base_mesh()
floor_label('AP floor text','AP',0,-.30,.25,pad_text)
floor_label('20 floor number','20',0,-.04,.23,pad_text)
# Flat curved arrow below AP20, placed to read from Blender +Y / UE south.
points=[]
for i in range(33):
    a=math.radians(25+250*i/32)
    points.append((.19*math.cos(a),.28+.14*math.sin(a),.011))
for i in range(len(points)-1):
    stripe('AP curved direction arrow',points[i],points[i+1],.045,green)
end=points[-1]
prev=points[-2]
dx,dy=end[0]-prev[0],end[1]-prev[1]
ln=math.hypot(dx,dy);dx/=ln;dy/=ln
mesh('AP arrow head',[(end[0]+dx*.09,end[1]+dy*.09,.012),
                      (end[0]-dx*.055-dy*.075,end[1]-dy*.055+dx*.075,.012),
                      (end[0]-dx*.055+dy*.075,end[1]-dy*.055-dx*.075,.012)],[(0,1,2)],green)


begin_asset('SM_VR_Conveyor')
def bed_height(y):
    return .8-.2*y
for x in [-.465,.465]:
    # Rectangular sloping structural rails, rather than a filled ramp slab.
    z0,z1=bed_height(-1.5),bed_height(1.5)
    beam('Conveyor outer side beam',(x,-1.5,z0-.065),(x,1.5,z1-.065),.035,blue,4)
    beam('Conveyor guide rail',(x,-1.5,z0+.045),(x,1.5,z1+.045),.013,steel_light,8)
for i in range(25):
    y=-1.44+i*.12
    z=bed_height(y)
    cylinder('Exposed conveyor roller',(0,y,z-.032),.037,.858,roller,20,'X')
    for x in [-.444,.444]:
        cylinder('Roller axle end',(x,y,z-.032),.015,.035,roller_end,12,'X')
for y in [-1.30,0,1.30]:
    top=bed_height(y)-.09
    for x in [-.40,.40]:
        box('Conveyor adjustable leg',(x,y,top/2),(.055,.055,top),steel,.005)
        box('Conveyor floor foot',(x,y,.0175),(.13,.13,.035),steel_light,.004)
    box('Conveyor support crossbar',(0,y,.19),(.84,.045,.045),blue,.004)
    beam('Conveyor leg brace',(-.4,y,.20),(.4,y,top-.06),.012,steel_light,8)
for y in [-1.49,1.49]:
    box('Conveyor end crossrail',(0,y,bed_height(y)-.065),(1.0,.022,.07),blue,.003)

save_library('storage')

# Optional asset-board render is deliberately staged only after saving/export:
# the .blend and FBXs keep every individual asset at its own ground origin.
if '--preview' in sys.argv:
    from mathutils import Vector
    offsets=[(-1.5,-1.15,0),(1.2,-1.15,0),(1.0,1.0,0),(2.4,1.0,0),(-1.8,1.45,0)]
    for (_,collection),offset in zip(ASSETS,offsets):
        for obj in collection.objects:
            obj.location += Vector(offset)
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=20
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1200
    scene.render.resolution_y=900
    scene.render.resolution_percentage=100
    scene.world.color=(.04,.05,.07)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.012))
    plane=bpy.context.object
    plane.data.materials.append(dark)
    for loc,power,size in [((1,3,8),1500,7),((-5,-1,5),800,5),((3,-5,4),900,4)]:
        bpy.ops.object.light_add(type='AREA',location=loc)
        light=bpy.context.object
        light.data.energy=power
        light.data.shape='DISK'
        light.data.size=size
        light.rotation_euler=(Vector((0,0,1))-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(6.5,10.5,8.0))
    camera=bpy.context.object
    camera.rotation_euler=(Vector((-.05,.1,1.05))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO'
    camera.data.ortho_scale=8.8
    scene.camera=camera
    scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(OUT/'storage_preview.png')
    bpy.ops.render.render(write_still=True)
