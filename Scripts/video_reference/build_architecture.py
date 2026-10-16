"""Editable blue warehouse architecture and floor graphics from video frames.

Coordinates are metres, ground Z=0 and equipment fronts +Y.  The shared FBX
export mirrors Y for the UE warehouse, where equipment faces -Y.
"""
import sys
from pathlib import Path
import math

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *

reset()
blue = material('ArchitecturalBlue', (.015, .18, .45), roughness=.36, metallic=.28)
dark_blue = material('ArchitecturalBlueShadow', (.008, .065, .16), roughness=.44, metallic=.22)
roof_blue = material('ElevatorRoofBlue', (.015, .23, .58), roughness=.42, metallic=.18)
cyan_inner = material('ElevatorInterior', (.025, .54, .73), roughness=.48, emission=.35)
cyan_edge = material('ArchitecturalEdge', (.08, .68, .90), emission=.8, unlit=True)
black = material('ArchitecturalRail', (.008, .014, .023), roughness=.32, metallic=.5)
gray = material('CabinetGray', (.29, .34, .36), roughness=.47, metallic=.3)
screen = material('CabinetDisplay', (.015, .06, .072), roughness=.2)
white = material('HologramWhite', (.78, .94, 1), emission=1.5, unlit=True)
amber = material('GateAmber', (1, .48, .075), emission=1.6, unlit=True)
green = material('HologramGreen', (.18, .95, .05), emission=1.0, unlit=True)
cyan = material('HologramCyan', (.07, .77, .74), emission=.8, unlit=True)
orange = material('AlarmOrange', (1, .16, .008), emission=1.6, unlit=True)
red = material('AlarmRedPulse', (1, .025, .005), emission=1.3, unlit=True, pulse=True, pulse_speed=2.0)
fan_mat = material('ScanFanTranslucent', (.15, .75, .22), emission=.3, opacity=.11, unlit=True)
fan_line = material('ScanFanGrid', (.12, .72, .25), emission=.4, opacity=.30, unlit=True)


def planar_strip(name, a, b, width, z, mat):
    """A flat ribbon with constant width, preserving clean floor projections."""
    dx,dy = b[0]-a[0], b[1]-a[1]
    length = math.hypot(dx,dy)
    nx,ny = -dy/length*width/2, dx/length*width/2
    return mesh(name, [(a[0]+nx,a[1]+ny,z),(a[0]-nx,a[1]-ny,z),
                       (b[0]-nx,b[1]-ny,z),(b[0]+nx,b[1]+ny,z)], [(0,1,2,3)], mat)


def ring_section(name, radius, width, start, end, z, mat, steps=None):
    steps = steps or max(2, int(abs(end-start)/3))
    vs=[]
    for i in range(steps+1):
        a=math.radians(start+(end-start)*i/steps)
        for r in (radius-width/2,radius+width/2):
            vs.append((r*math.cos(a),r*math.sin(a),z))
    return mesh(name,vs,[(2*i,2*i+1,2*i+3,2*i+2) for i in range(steps)],mat)


def radial_tick(name, angle, r0, r1, width, z, mat):
    a=math.radians(angle)
    return planar_strip(name,(r0*math.cos(a),r0*math.sin(a)),
                        (r1*math.cos(a),r1*math.sin(a)),width,z,mat)


def front_triangle(name,cx,y,z,w,h,mat,up=True):
    sign=1 if up else -1
    return mesh(name,[(cx-w/2,y,z-sign*h/2),(cx+w/2,y,z-sign*h/2),
                      (cx,y,z+sign*h/2)],[(0,1,2),(2,1,0)],mat)


begin_asset('SM_VR_Elevator')
box('LiftFloor',(0,0,.04),(3.2,3,.08),cyan_inner)
box('LiftBack',(0,-1.42,1.735),(3.2,.16,3.47),dark_blue)
box('LiftLeftWall',(-1.52,-.11,1.735),(.16,2.46,3.47),blue)
box('LiftRightWall',(1.52,-.11,1.735),(.16,2.46,3.47),blue)
box('LiftInteriorBack',(0,-1.329,1.48),(2.82,.018,2.77),cyan_inner)
box('LiftInteriorLeft',(-1.429,-.08,1.48),(.018,2.45,2.77),cyan_inner)
box('LiftInteriorRight',(1.429,-.08,1.48),(.018,2.45,2.77),cyan_inner)
for side in (-1,1):
    box('LiftFrontJamb', (side*1.30,1.31,1.735),(.60,.38,3.47),blue)
    box('LiftJambShadow', (side*1.53,1.511,1.69),(.08,.022,3.20),dark_blue)
    box('LiftDoorBlackRail', (side*1.018,1.507,1.40),(.036,.026,2.8),black,edge=.001)
    box('LiftInnerLightStrip',(side*.984,1.283,1.40),(.022,.025,2.76),cyan_edge,edge=.001)
box('LiftFrontHeader',(0,1.31,3.135),(2,.38,.67),blue)
box('LiftDoorUpperRail',(0,1.507,2.81),(2.02,.026,.035),black,edge=.001)
box('LiftRoof',(0,-.11,3.385),(2.88,2.46,.17),roof_blue)
for side in (-1,1):
    box('LiftRoofSideRim',(side*1.575,-.005,3.485),(.05,2.89,.03),blue,edge=.003)
box('LiftRoofRearRim',(0,-1.475,3.485),(3.1,.05,.03),blue,edge=.003)
box('LiftRoofFrontLip',(0,1.47,3.485),(3.1,.06,.03),roof_blue)
box('LiftCeilingLuminaire',(0,.60,3.31),(1.76,.48,.015),cyan_edge,edge=.001)
# Seven-segment white 2; visible geometry stays editable and independent of fonts.
cx,y,cz=1.29,1.516,1.69
w,h,stroke=.42,.67,.075
for label,z in [('Top',cz+h/2),('Middle',cz),('Bottom',cz-h/2)]:
    box('Floor2'+label,(cx,y,z),(w,.012,stroke),white,edge=.012)
box('Floor2UpperRight',(cx-w/2+stroke/2,y,cz+h/4),(stroke,.012,h/2),white,edge=.012)
box('Floor2LowerLeft',(cx+w/2-stroke/2,y,cz-h/4),(stroke,.012,h/2),white,edge=.012)
front_triangle('LiftUpArrow',cx-.12,1.525,1.14,.16,.15,white)
front_triangle('LiftDownArrow',cx+.12,1.525,1.14,.16,.15,white,False)

begin_asset('SM_VR_Gate')
for side in (-1,1):
    box('GateUpright',(side*1.41,0,1.28),(.18,.27,2.56),blue)
    box('GateInnerRail',(side*1.306,.145,1.26),(.026,.026,2.52),dark_blue,edge=.001)
box('GateHeader',(0,0,2.68),(3,.34,.24),roof_blue)
box('GateAmberBase',(0,.008,2.813),(.35,.18,.026),gray)
box('GateAmberIndicator',(0,.008,2.844),(.28,.13,.045),amber)

begin_asset('SM_VR_ControlCabinet')
box('CabinetEnclosure',(0,-.0225,.575),(.45,.155,1.15),gray,edge=.015)
box('CabinetDoor',(0,.058,.59),(.405,.018,1.065),gray,edge=.009)
box('CabinetDisplayFrame',(-.045,.072,.89),(.218,.015,.165),black,edge=.003)
box('CabinetDisplayGlass',(-.045,.083,.89),(.184,.005,.13),screen,edge=.001)
box('CabinetDisplayStatus',(-.07,.088,.91),(.102,.003,.013),cyan,edge=0)
box('CabinetHandle',(.145,.0775,.56),(.025,.045,.17),black,edge=.003)
for x in (-.12,-.04,.04):
    cylinder('CabinetButton',(x,.081,.71),.017,.018,green if x<0 else amber,vertices=16,axis='Y')
for z in (.16,.20,.24):
    box('CabinetVent',(0,.070,z),(.27,.006,.007),black,edge=0)

begin_asset('SM_VR_StatusRing')
for i in range(10):
    start=i*36+2
    ring_section('StatusInnerSegment',.82,.058,start,start+25,.041,green)
for start,end in [(12,112),(145,224),(263,332)]:
    ring_section('StatusCyanArc',.985,.018,start,end,.040,cyan)
for start,end in [(34,67),(164,196),(277,303)]:
    ring_section('StatusWhiteOuterArc',1.09,.014,start,end,.042,white)
for a in (0,90,180,270):
    radial_tick('StatusRadialTick',a,.98,1.16,.015,.043,white)

begin_asset('SM_VR_AlarmRing')
for i in range(12):
    ring_section('AlarmInnerSegment',.76,.10,i*30+3,i*30+25,.041,orange)
    ring_section('AlarmOuterSegment',1.03,.035,i*30+1,i*30+28,.042,orange)
for i in range(8):
    ring_section('AlarmPulseSegment',.61,.028,i*45+4,i*45+37,.043,red)
for a in (15,105,195,285):
    ring_section('AlarmWhiteCurvedTick',1.19,.014,a,a+23,.044,white)
    radial_tick('AlarmWhiteRadialTick',a+23,1.14,1.29,.014,.044,white)
for a in (0,90,180,270):
    for r in (1.12,1.32,1.52):
        radial_tick('AlarmAxisDash',a,r,r+.13,.013,.040,orange)

begin_asset('SM_VR_TargetMarker')
for sx in (-1,1):
    for sy in (-1,1):
        corner=(sx*.5,sy*.5)
        planar_strip('TargetCornerX',corner,(sx*.29,sy*.5),.035,.04,green)
        planar_strip('TargetCornerY',corner,(sx*.5,sy*.29),.035,.04,green)
for r in range(5):
    box('TargetVerticalDash',(0,0,.13+r*.16),(.025,.025,.075),green,edge=0)
# Four triangular facets make the hovering pointer visible from every camera.
mesh('TargetDownPointer',[(-.12,-.10,1.30),(.12,-.10,1.30),(.12,.10,1.30),(-.12,.10,1.30),(0,0,1.04)],
     [(0,1,4),(1,2,4),(2,3,4),(3,0,4),(3,2,1,0)],green)

begin_asset('SM_VR_ScanFan')
vs=[(0,0,.05)]
for i in range(61):
    a=math.radians(67.5+45*i/60)
    vs.append((3*math.cos(a),3*math.sin(a),.05))
mesh('ScanFanSurface',vs,[(0,i,i+1) for i in range(1,61)],fan_mat)
for i in range(1,19):
    ring_section('ScanFanSubArc',i/6,.004,67.5,112.5,.052,fan_line,steps=45)
for i in range(19):
    a=67.5+45*i/18
    radial_tick('ScanFanRadialLine',a,.03,3,.003,.053,fan_line)
ring_section('ScanFanOuterBoundary',3,.014,67.5,112.5,.054,fan_line,steps=60)

save_library('architecture')
