"""Detailed logistics architecture, generated in Blender. Dimensions in metres."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *

reset()
ivory = material('Cladding_Ivory', (.69,.71,.68), .48, .58, texture_role='metal')
steel = material('Structure_Galvanized', (.34,.39,.42), .44, .78, texture_role='metal')
navy = material('Trim_Navy', (.033,.070,.105), .38, .7, texture_role='metal')
roofmat = material('Roof_Zinc', (.40,.46,.49), .47, .75, texture_role='metal')
concrete = material('Concrete_Precast', (.43,.44,.41), .88, texture_role='concrete')
floor = material('Concrete_Polished', (.46,.48,.46), .65, texture_role='concrete')
rubber = material('Dock_Rubber', (.018,.022,.025), .9)
door = material('RollerDoor_Gray', (.40,.44,.46), .48, .65, texture_role='metal')
yellow = material('Safety_Yellow', (.96,.65,.035), .52, .42, texture_role='metal')
black = material('Window_Frames', (.025,.035,.045), .38, .75, texture_role='metal')
glass = material('Office_Glass', (.10,.23,.29), .17, .22, glass=True)
roofglass = material('Rooflight_Glass', (.26,.41,.46), .26, .12, glass=True)
plaster = material('Office_White', (.79,.79,.74), .78, texture_role='concrete')
blue = material('Rack_Blue', (.025,.16,.36), .43, .68, texture_role='metal')
orange = material('Rack_Orange', (.94,.24,.028), .45, .5, texture_role='metal')
wood = material('Rack_Deck', (.46,.32,.16), .8, texture_role='wood')
assets=[]

def corrugated(name, along, fixed, lo, hi, bottom, top, mat):
    # A folded continuous sheet, with narrow raised ribs, rather than painted lines.
    verts=[]; faces=[]
    pos=lo
    coords=[]
    while pos < hi-.001:
        for delta,offset in ((0,0),(.29,0),(.32,.045),(.38,.045),(.41,0)):
            if pos+delta<=hi: coords.append((pos+delta,offset))
        pos += .44
    coords.append((hi,0))
    for p,o in coords:
        xy=(p,fixed-o) if along=='X' else (fixed+o,p)
        verts.extend([(xy[0],xy[1],bottom),(xy[0],xy[1],top)])
    for i in range(len(coords)-1):
        face=(2*i,2*i+2,2*i+3,2*i+1)
        if (along=='X' and fixed>0) or (along=='Y' and fixed<0): face=tuple(reversed(face))
        faces.append(face)
    o=mesh(name,verts,faces,mat)
    mod=o.modifiers.new('Sheet thickness','SOLIDIFY')
    mod.thickness=.055
    mod.offset=0
    return o

def side_door(x,y):
    # Utility doors open at warehouse slab level, with an external stair flight.
    box('PersonnelDoor', (x,y,2.25), (.08,1.16,2.1), navy)
    box('DoorVisionPanel',(x+(.055 if x>0 else -.055),y,2.65),(.03,.43,.48),glass,.006)
    box('DoorHandle',(x+(.08 if x>0 else -.08),y-.40,2.18),(.08,.17,.035),steel,.008)
    s=1 if x>0 else -1
    for j in range(6):
        box('PersonnelStair',(x+s*(.18+.25*j),y,.6-.1*j),(.25,1.6,.2*(6-j)),concrete,.012)
    beam('StairHandrail',(x+s*.2,y+.80,2.25),(x+s*1.5,y+.8,1.25),.025,steel)
    beam('StairHandrail',(x+s*.2,y-.80,2.25),(x+s*1.5,y-.8,1.25),.025,steel)
    for sy in (-.8,.8):
        for j in (0,5):
            xx=x+s*(.2+j*.25); zz=1.2-.2*j
            beam('StairRailPost',(xx,y+sy,zz),(xx,y+sy,zz+1.05),.025,steel)

# WAREHOUSE SHELL: warehouse front is -Y, with ten genuine dock voids.
box('Warehouse_Foundation',(0,0,.50),(96,54,1.0),concrete,.035)
box('Warehouse_Floor',(0,0,1.10),(95.8,53.8,.20),floor,.02)
centres=[-40.5+9*i for i in range(10)]
edges=[-48]+[v for c in centres for v in (c-1.8,c+1.8)]+[48]
for i in range(0,len(edges)-1,2):
    a,b=edges[i:i+2]
    box('DockWall_ConcretePier',((a+b)/2,-26.94,2.0),(b-a,.24,1.6),concrete,.015)
    corrugated('DockWall_CladdingPier','X',-27,a,b,2.8,5.5,ivory)
corrugated('Front_Upper_Cladding','X',-27,-48,48,5.5,11.92,ivory)
box('Front_EaveFascia',(0,-27.12,11.86),(96.4,.23,.32),navy)
box('Back_ConcreteBase',(0,26.94,2),(96,.24,1.6),concrete)
corrugated('Back_Metal_Cladding','X',27,-48,48,2.8,11.92,ivory)
box('Back_EaveFascia',(0,27.12,11.86),(96.4,.23,.32),navy)
for x in (-48,48):
    box('End_ConcreteBase',(x,0,2),(.24,54,1.6),concrete)
    corrugated('End_Cladding','Y',x,-27,27,2.8,11.92,ivory)
    mesh('End_Gable',[(x,-27,11.92),(x,27,11.92),(x,0,14)],[(0,1,2) if x>0 else (2,1,0)],ivory)
    # Gable ribs terminate at the pitched roof.
    for yi in range(-26,27):
        ztop=14-abs(yi)*2/27
        box('Gable_Rib',(x+(.03 if x>0 else -.03),yi,(11.92+ztop)/2),(.045,.045,ztop-11.92),ivory,.005)
    box('Corner_Trim',(x,-27.03,6.6),(.20,.20,10.8),navy)
    box('Corner_Trim',(x,27.03,6.6),(.20,.20,10.8),navy)
    side_door(x+(.17 if x>0 else -.17),16)

open_fractions=[0,.65,0,1,.28,0,.58,1,0,.35]
for i,(x,opening) in enumerate(zip(centres,open_fractions)):
    # Door tracks / recessed loading leveller, outside black seal surround.
    box('DockLeveller',(x,-26.8,1.215),(3.42,2.1,.09),steel,.014)
    box('DockLevellerLip',(x,-27.22,1.17),(3.42,.48,.12),navy,.012)
    for dx in (-1.89,1.89):
        box('RollerGuide',(x+dx,-26.91,3.35),(.14,.14,4.36),steel,.012)
        box('DockShelter_Side',(x+dx*1.15,-27.46,3.45),(.44,.80,4.70),navy,.035)
        box('RubberSeal',(x+dx*1.02,-27.92,3.42),(.28,.075,4.46),rubber,.018)
        box('DockBumper',(x+dx*.88,-27.28,.72),(.30,.38,.76),rubber,.045)
        box('BumperSteelPlate',(x+dx*.88,-27.1,.72),(.38,.08,.87),steel,.015)
    box('DockShelter_Top',(x,-27.46,5.71),(4.78,.80,.42),navy,.025)
    box('DockShelter_Valance',(x,-27.93,5.46),(4.47,.07,.32),rubber,.012)
    # Visible segmented roller doors: some closed, others partly raised / open.
    bottom=1.2+4.3*opening
    if opening<1:
        box('RollerDoor',(x,-26.82,(5.5+bottom)/2),(3.60,.09,5.5-bottom),door,.014)
        z=bottom+.16
        while z<5.5:
            box('RollerDoorSlat',(x,-26.88,z),(3.57,.035,.028),steel,.004)
            z+=.22
        if opening<.5:
            for dx in (-1.0,0,1.0):
                box('RollerDoorVision',(x+dx,-26.89,3.6),(.57,.035,.25),glass,.01)
    else:
        cylinder('RollerDoorDrum',(x,-26.65,5.72),.23,3.75,door,20,(0,math.pi/2,0))
    # Two practical steel guard posts at dock corners.
    for dx in (-2.68,2.68):
        cylinder('DockBollard',(x+dx,-27.93,.57),.075,1.14,yellow,12)
    box('DockNumberPlate',(x,-27.09,6.37),(1.10,.055,.51),navy,.015)
    # Bars mimic high-visibility printed dock identifiers at long viewing distance.
    # No pseudo-letter text or decorative labels.
    for tick in range(i+1):
        box('DockID_Tick',(x-.43+tick*.085,-27.125,6.37),(.035,.015,.22),plaster,.002)

# Interior portal frames support the separate hideable roof.
for x in [-45+9*i for i in range(11)]:
    for y in (-26.4,26.4):
        box('Column_Web',(x,y,6.55),(.22,.44,10.7),steel,.008)
        for dx in (-.17,.17): box('Column_Flange',(x+dx,y,6.55),(.10,.56,10.7),steel,.008)
        box('Column_BasePlate',(x,y,1.27),(.72,.85,.14),steel,.01)
    beam('Truss_BottomChord',(x,-26.4,11.40),(x,26.4,11.40),.105,steel,8)
    points=[(x,-26.4,11.95),(x,-17.6,12.63),(x,-8.8,13.3),(x,0,13.95),(x,8.8,13.3),(x,17.6,12.63),(x,26.4,11.95)]
    for a,b in zip(points,points[1:]): beam('Rafter_TopChord',a,b,.12,steel,8)
    for j,p in enumerate(points[1:-1]):
        beam('Truss_Vertical',(x,p[1],11.4),p,.055,steel,8)
        target=points[j] if j%2==0 else points[j+2]
        beam('Truss_Diagonal',(x,p[1],11.4),target,.06,steel,8)
for y in (-25,-18,-10,0,10,18,25):
    z=14-abs(y)*2/27-.16
    box('Roof_Purlin',(0,y,z),(96,.12,.18),steel,.012)
for x in (-47.6,-27,0,27,47.6):
    for side in (-1,1):
        y=side*27.34
        cylinder('Rainwater_Downpipe',(x,y,6.0),.075,11.7,navy,12)
        for z in (2,6,10): box('Downpipe_Bracket',(x,y-.03*side,z),(.23,.18,.055),steel,.006)
assets.append(export_asset('SM_WarehouseShell'))

# INDEPENDENT ROOF, including real folded sheets and flush rooflight bands.
xcoords={-48.8,48.8}
for j in range(222):
    x=-48.8+j*.44
    for delta in (0,.29,.32,.38,.41):
        if x+delta<48.8: xcoords.add(round(x+delta,4))
for c in (-34,-10,14,38): xcoords.update((c-3,c+3))
xcoords=sorted(xcoords)
for sign in (-1,1):
    ys=[0,8,14,27.8]
    verts=[]; faces=[]; indices=[]
    for xi,x in enumerate(xcoords):
        phase=((x+48.8)%.44)
        corr=.032 if .305<phase<.395 else 0
        for y in ys: verts.append((x,sign*y,14-y*2/27+corr))
    for i in range(len(xcoords)-1):
        xm=(xcoords[i]+xcoords[i+1])/2
        for j in range(3):
            k=i*4+j
            face=(k,k+4,k+5,k+1)
            faces.append(face if sign>0 else tuple(reversed(face)))
            indices.append(1 if j==1 and any(abs(xm-c)<3 for c in (-34,-10,14,38)) else 0)
    o=mesh('Corrugated_Roof',verts,faces,roofmat)
    mod=o.modifiers.new('Roof sheet thickness','SOLIDIFY')
    mod.thickness=.06
    mod.offset=-1
    o.data.materials.append(roofglass)
    for p,idx in zip(o.data.polygons,indices): p.material_index=idx
    for c in (-34,-10,14,38):
        for xx in (c-3,c+3):
            beam('Rooflight_Frame',(xx,sign*8,14-8*2/27+.045),(xx,sign*14,14-14*2/27+.045),.035,steel,8)
        for y in (8,14): box('Rooflight_Frame',(c,sign*y,14-y*2/27+.045),(6,.065,.065),steel,.009)
    # Half-round gutters and end fascia can be understood at aerial scale.
    cylinder('Gutter',(0,sign*27.84,11.91),.15,98,navy,16,(0,math.pi/2,0))
    box('Eave_Apron',(0,sign*27.73,11.91),(97.6,.13,.23),navy)
box('Ridge_Capping',(0,0,14.07),(97.8,.45,.14),navy,.035)
for xx in (-48.78,48.78):
    for sign in (-1,1):
        beam('Roof_Verge',(xx,0,14.07),(xx,sign*27.9,12.0),.115,navy,8)
for x in (-27,0,27):
    for y in (-19,19):
        z=14-abs(y)*2/27
        box('RoofVent_Curb',(x,y,z+.21),(1.65,1.65,.44),navy,.025)
        box('RoofVent_Lid',(x,y,z+.53),(2.03,2.03,.16),roofmat,.04)
        for side in (-1,1):
            for dz in (0,.09,.18): box('Vent_Louvre',(x,y+side*.84,z+.24+dz),(1.55,.10,.035),steel,.005)
assets.append(export_asset('SM_WarehouseRoof'))

# OFFICE ANNEX: actual facade piers, recessed glass, mullions, slabs, canopy.
box('Office_Foundation',(0,0,.25),(24,20,.5),concrete,.035)
for z in (.55,4.20,7.78):
    box('Office_Slab',(0,0,z),(24,20,.25),concrete,.025)
for z in (1.0,4.65):
    for y in (-9.9,9.9): box('Office_Spandrel',(0,y,z),(24,.22,.70),plaster,.015)
    for x in (-11.9,11.9): box('Office_Spandrel',(x,0,z),(.22,20,.70),plaster,.015)
for z in (3.65,7.30):
    for y in (-9.9,9.9): box('Office_Lintel',(0,y,z),(24,.22,.85),plaster,.012)
    for x in (-11.9,11.9): box('Office_Lintel',(x,0,z),(.22,20,.85),plaster,.012)

def window_front(cx,y,z,w=3.3,h=1.9):
    box('Office_Glazing',(cx,y,z),(w,.065,h),glass,.006)
    for xx in (cx-w/2,cx,cx+w/2): box('Window_Mullion',(xx,y-.05,z),(.065,.10,h+.10),black,.006)
    for zz in (z-h/2,z+h/2): box('Window_Rail',(cx,y-.05,zz),(w+.1,.10,.065),black,.006)
    box('Window_Transom',(cx,y-.05,z+.23),(w,.10,.045),black,.004)
    box('Window_Sill',(cx,y-.09,z-h/2-.07),(w+.2,.32,.075),steel,.01)

for z in (2.3,5.95):
    for y in (-9.91,9.91):
        for x in (-9.6,-5.8,-1.9,1.9,5.8,9.6): window_front(x,y,z)
    for x in (-11.9,11.9):
        for y in (-7.2,-2.4,2.4,7.2):
            box('Office_SideGlazing',(x,y,z),(.065,4.0,1.9),glass,.005)
            for yy in (y-2,y,y+2): box('Side_Mullion',(x,yy,z),(.1,.065,2.0),black,.006)
            for zz in (z-.95,z+.95): box('Side_Frame',(x,y,zz),(.1,4.1,.065),black,.006)
for y in (-9.9,9.9):
    for x in (-11.7,-7.7,-3.85,0,3.85,7.7,11.7): box('Office_FacadePier',(x,y,4.1),(.35,.32,7.5),plaster,.02)
for x in (-11.9,11.9):
    for y in (-9.7,-4.8,0,4.8,9.7): box('Office_SidePier',(x,y,4.1),(.32,.36,7.5),plaster,.02)
for y in (-9.9,9.9): box('Office_Parapet',(0,y,8),(24,.23,.40),plaster,.015)
for x in (-11.9,11.9): box('Office_Parapet',(x,0,8),(.23,20,.40),plaster,.015)
box('Office_Roof',(0,0,7.96),(23.6,19.6,.10),navy,.01)
# Entry doors overlay the central ground-floor bay, at realistic scale.
box('Entrance_Recess',(0,-10.10,1.75),(3.5,.16,2.60),black,.01)
for x in (-.80,.80):
    box('Entrance_GlassDoor',(x,-10.21,1.72),(1.49,.055,2.35),glass,.008)
    for dx in (-.75,.75): box('Door_Stile',(x+dx,-10.26,1.72),(.055,.065,2.42),steel,.006)
    beam('Entrance_Pull',(x+(.47 if x<0 else -.47),-10.33,1.42),(x+(.47 if x<0 else -.47),-10.33,2.01),.017,steel)
box('Entrance_Canopy',(0,-11.30,3.28),(7.4,3.4,.22),navy,.045)
for x in (-3.2,3.2): cylinder('Canopy_Column',(x,-12.55,1.78),.075,3.0,steel,16)
box('Entry_Landing',(0,-11.12,.44),(7.4,2.3,.28),concrete,.025)
for j in range(4): box('Entry_Stair',(0,-12.45-j*.30,.075*(4-j)),(7.4,.30,.15*(4-j)),concrete,.015)
for x in (-3.5,3.5):
    beam('Entry_Handrail',(x,-13.3,1.0),(x,-12.0,1.57),.024,steel)
    for y in (-13.3,-12): beam('Entry_Post',(x,y,.2 if y<-13 else .6),(x,y,1.0 if y<-13 else 1.57),.024,steel)
assets.append(export_asset('SM_OfficeAnnex'))

# STANDARD PALLET RACK, 2.8 x 1.2 x 7 m, bolt plates and X bracing.
for x in (-1.32,1.32):
    for y in (-.53,.53):
        box('Rack_Upright',(x,y,3.5),(.13,.13,7.0),blue,.012)
        box('Rack_Baseplate',(x,y,.045),(.16,.14,.09),blue,.012)
        for z in (.6,1.7,2.8,3.9,5.0,6.1):
            box('Rack_UprightHole',(x,y-.064,z),(.035,.012,.09),black,.003)
    for z in (.3,2.5,4.7,6.8):
        beam('Rack_SideRail',(x,-.53,z),(x,.53,z),.035,blue,6)
    for z in (.3,2.5,4.7):
        beam('Rack_SideDiagonal',(x,-.53,z),(x,.53,z+2.2),.027,blue,6)
        beam('Rack_SideDiagonal',(x,.53,z),(x,-.53,z+2.2),.027,blue,6)
for z in (1.90,3.95,6.0):
    for y in (-.54,.54):
        box('Rack_Crossbeam',(0,y,z),(2.8,.12,.18),orange,.015)
        for x in (-1.29,1.29): box('Rack_Connection',(x,y,z),(.13,.12,.28),orange,.012)
    box('Rack_ShelfDeck',(0,0,z+.12),(2.53,1.05,.065),wood,.006)
    for x in (-.8,0,.8): box('Rack_DeckSupport',(x,0,z+.03),(.06,1.08,.10),steel,.006)
assets.append(export_asset('SM_RackUnit'))
save_manifest('architecture.json',assets)
print('ARCHITECTURE_VALIDATION',[(a['name'],a['bounds_m'],a['vertices'],a['polygons']) for a in assets])
