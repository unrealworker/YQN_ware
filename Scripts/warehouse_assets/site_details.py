import sys
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *

reset()
steel = material("SiteGalvanized", (0.31, 0.35, 0.37), 0.38, 0.8, texture_role="metal")
black = material("SiteDarkSteel", (0.028, 0.041, 0.05), 0.5, 0.65)
white = material("SiteIvory", (0.65, 0.68, 0.69), 0.6, 0.15)
yellow = material("SafetyYellow", (0.95, 0.57, 0.035), 0.58, 0.05)
red = material("ContainerTerracotta", (0.32, 0.065, 0.035), 0.68, 0.5, texture_role="metal")
glass = material("SiteGlass", (0.055, 0.12, 0.16), 0.15, 0.5, glass=True)
light = material("LampLED", (0.95, 0.85, 0.65), 0.25, 0, emission=3.0)
rubber = material("SiteRubber", (0.013,0.016,0.02), 0.86)
assets=[]

# Six-metre hot-dip galvanized perimeter fence section, origin at its midpoint.
for x in [-3,3]:
    cylinder("Fence post", (x,0,1.25),.055,2.5,steel)
    box("Fence base",(x,0,.09),(.25,.25,.18),black,.02)
for z in [.25,1.2,2.25]:
    box("Fence rail",(0,0,z),(6,.035,.035),steel,.004)
for i in range(49):
    x=-3+i*.125
    beam("Fence wire",(x,0,.28),(x,0,2.25),.008,steel,5)
for z in [.45+i*.18 for i in range(10)]:
    box("Fence horizontal wire",(0,0,z),(6,.012,.012),steel,.001)
assets.append(export_asset("SM_PerimeterFence"))

box("Pole foundation",(0,0,.15),(.65,.65,.3),steel,.03)
cylinder("Lamp pole",(0,0,4.25),.09,8.2,black,20)
beam("Lamp arm",(0,0,8.1),(0,-1.1,8.1),.055,black,12)
box("Lamp housing",(0,-1.1,8.08),(.7,1,.14),black,.045)
box("LED panel",(0,-1.1,7.995),(.54,.79,.025),light,.01)
assets.append(export_asset("SM_YardLightPole"))

# Shipping container with deep ribs, corner castings and doors.
box("Container shell",(0,0,1.3),(6.06,2.44,2.6),red,.025)
for side in [-1,1]:
    for i in range(40):
        box("Container vertical rib",(-2.9+i*.148,side*1.235,1.35),(.055,.055,2.35),red,.008)
    for z in [.12,2.5]:
        box("Container edge rail",(0,side*1.24,z),(6.07,.08,.1),red,.01)
for y in [-.61,.61]:
    box("Container rear door",(3.05,y,1.32),(.04,1.18,2.35),red,.01)
    for yy in [y-.4,y+.4]:
        cylinder("Door lock bar",(3.085,yy,1.3),.025,2.25,steel,10)
for x in [-2.97,2.97]:
    for y in [-1.18,1.18]:
        for z in [.1,2.5]:
            box("Corner casting",(x,y,z),(.18,.18,.16),steel,.01)
assets.append(export_asset("SM_ShippingContainer"))

# Guardhouse and entry canopy, front -Y (becomes +Y in UE).
box("Guardhouse floor",(0,0,.15),(5.2,3.5,.3),steel,.03)
box("Guardhouse body",(0,0,1.55),(4.9,3.2,2.8),white,.04)
for x in [-1.55,0,1.55]:
    box("Front glazing",(x,-1.615,1.8),(1.35,.035,1.3),glass,.01)
for side in [-1,1]:
    box("Side glazing",(side*2.46,0,1.8),(.035,2.3,1.3),glass,.01)
box("Flat roof",(0,0,3.05),(5.5,3.8,.18),black,.035)
box("Canopy",(0,-2.6,3.1),(8,3,.18),black,.035)
for x in [-3.6,3.6]:
    cylinder("Canopy column",(x,-3.8,1.5),.075,3,steel)
assets.append(export_asset("SM_Guardhouse"))

box("Barrier pedestal",(0,0,.55),(.4,.4,1.1),yellow,.05)
box("Barrier arm",(2,0,1.12),(4,.11,.14),white,.015)
for i in range(6):
    box("Barrier red band",(.4+i*.6,-.058,1.12),(.23,.009,.14),red,.001)
assets.append(export_asset("SM_SecurityBarrier"))

# Staff car: separate curved body and glazing, wheel arches, lamps and mirrors.
verts=[]
sections=[(-2.25,.76,.55),(-2.05,.86,.82),(-1.1,.9,1.03),(-.65,.81,1.48),(.5,.78,1.51),(1.15,.85,1.0),(2.15,.83,.83),(2.3,.72,.62)]
for x,w,z in sections:
    verts.extend([(x,-w,.43),(x,w,.43),(x,w,z),(x,-w,z)])
faces=[]
for i in range(len(sections)-1):
    for j in range(4):faces.append((4*i+j,4*i+(j+1)%4,4*(i+1)+(j+1)%4,4*(i+1)+j))
faces.extend([(3,2,1,0),tuple(range(28,32))])
car=mesh("Car body",verts,faces,white)
bev=car.modifiers.new("Soft sheetmetal edges","BEVEL");bev.width=.055;bev.segments=3
car.modifiers.new("Normals","WEIGHTED_NORMAL")
mesh("Windshield",[(.52,-.72,1.50),(.52,.72,1.50),(1.11,.8,1.04),(1.11,-.8,1.04)],[(0,1,2,3)],glass)
for side in [-1,1]:
    mesh("Side windows",[(-.61,side*.82,1.43),(.47,side*.79,1.46),(.96,side*.87,1.06),(-.94,side*.91,1.06)],[(0,1,2,3)],glass)
    box("Door pillar",(-.12,side*.855,1.26),(.06,.04,.4),black,.003)
    box("Mirror",(.75,side*.99,1.02),(.2,.19,.12),white,.025)
    for x in [-1.42,1.47]:
        cylinder("Tire",(x,side*.85,.34),.34,.21,rubber,32,(math.pi/2,0,0))
        cylinder("Alloy rim",(x,side*.969,.34),.22,.018,steel,20,(math.pi/2,0,0))
        cylinder("Hub",(x,side*.983,.34),.07,.026,black,16,(math.pi/2,0,0))
for side in [-1,1]:
    box("Headlight",(2.24,side*.53,.76),(.035,.36,.14),light,.02)
    box("Taillight",(-2.19,side*.55,.73),(.035,.29,.14),red,.01)
box("Grille",(2.28,0,.57),(.025,1.0,.17),black,.015)
assets.append(export_asset("SM_StaffCar"))
save_manifest("site_details.json",assets)
