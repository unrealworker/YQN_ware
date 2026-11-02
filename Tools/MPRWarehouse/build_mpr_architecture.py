"""MPR CAD footprint and apertures, GHS palette. Run in background Blender."""
import sys, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_blender_common import Geometry

CAD=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf-8'))
g=Geometry();fp=CAD['footprint_outline_m'];HEIGHT=13.6;ROOF=13.4
g.prism('SM_MPR_Floor','Floor',fp,-.22,0)
g.prism('SM_MPR_Roof','Roofs',fp,13.12,ROOF)
openings=CAD['dock_doors']+CAD['drive_in_doors']

def inside(x,y):
    result=False
    for a,b in zip(fp,fp[1:]+fp[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:result=not result
    return result

def wall_piece(name,a,b,z0,z1,role='Porcelain',thickness=.3048):
    if math.dist(a,b)>.003:g.segment(name,role,a,b,thickness,(z0+z1)/2,z1-z0)

apertures=[]
for side,(a,b) in enumerate(zip(fp,fp[1:]+fp[:1])):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
    name='SM_MPR_Exterior_%02d'%side;cuts=[]
    def pt(t):return (a[0]+ux*t,a[1]+uy*t)
    for door in openings:
        p=door['position_m'];t=(p[0]-a[0])*ux+(p[1]-a[1])*uy
        perpendicular=abs((p[0]-a[0])*uy-(p[1]-a[1])*ux)
        if 0<t<length and perpendicular<.4:
            half=door['opening_width_m']/2;cuts.append((max(0,t-half),min(length,t+half),door))
    cuts.sort(key=lambda r:r[0]);cursor=0
    for left,right,door in cuts:
        wall_piece(name,pt(cursor),pt(left),-1.2,HEIGHT)
        h=4.2 if door in CAD['dock_doors'] else 4.5
        wall_piece(name,pt(left),pt(right),h,HEIGHT)
        if door in CAD['dock_doors']:wall_piece(name,pt(left),pt(right),-1.2,-.04,role='PaleGray')
        # Real thick jambs at both ends of the opening.
        for edge in (left,right):wall_piece(name,pt(edge-.045),pt(edge+.045),0,h,role='Cobalt',thickness=.42)
        apertures.append(dict(id=door['id'],side=side,opening_width_m=right-left,height_m=h))
        cursor=max(cursor,right)
    wall_piece(name,pt(cursor),pt(length),-1.2,HEIGHT)
    # Architectural fascia and separated roof parapet remain removable with roof.
    wall_piece(name,pt(0),pt(length),11.65,11.84,role='Cobalt',thickness=.34)
    wall_piece('SM_MPR_RoofEdge',pt(0),pt(length),13.4,13.82,role='Porcelain',thickness=.38)
    # Fine precast vertical joints, only outside wall planes.
    nx,ny=-uy,ux
    if inside((a[0]+b[0])/2+nx,(a[1]+b[1])/2+ny):nx,ny=-nx,-ny
    for i in range(1,int(length/6.1)):
        x,y=pt(i*6.1)
        g.box(name,'PaleGray',(x+nx*.157,y+ny*.157,8.2),(.018,.018,6.5))

assert len(apertures)==74,('All doors must be assigned exactly once',len(apertures))
for w in CAD['office_walls']:
    wall_piece('SM_MPR_OfficePartitions',*w['points_m'],0,3.3,thickness=w['thickness_m'])

# Glazing bands at the two end office faces follow photographed precast styling.
for x,y0,y1 in [(-182.10,50,80),(182.78,62,80)]:
    for y in range(int(y0),int(y1),3):
        g.box('SM_MPR_OfficeGlazing','Glass',(x,y,2.4),(.055,2.4,2.4))
        g.box('SM_MPR_OfficeGlazing','Porcelain',(x,y,3.65),(.09,2.55,.12))
        for off in (-1.25,0,1.25):g.box('SM_MPR_OfficeGlazing','Porcelain',(x,y+off,2.4),(.09,.07,2.5))

# Roof details are low-poly geometry; no tick or translucent material.
skylights=0;solar_panels=0
for x in range(-169,174,15):
    for y in range(-73,74,15):
        if not all(inside(x+dx,y+dy) for dx,dy in [(-2,-2),(2,-2),(2,2),(-2,2)]):continue
        g.box('SM_MPR_RoofPlant','Detail',(x,y,ROOF+.14),(1.8,1.25,.28))
        g.box('SM_MPR_RoofPlant','Skylight',(x,y,ROOF+.32),(1.62,1.08,.12));skylights+=1
for x in range(-12,170,4):
    for y in range(-76,68,4):
        # Reference density: solar mostly over east half; leave service aisles.
        if x%24<5 or y%24<5:continue
        if not all(inside(x+dx,y+dy) for dx,dy in [(-2,-2),(2,-2),(2,2),(-2,2)]):continue
        if any(abs(x-a)<3 and abs(y-b)<2.5 for a in range(-169,174,15) for b in range(-73,74,15)):continue
        g.box('SM_MPR_RoofSolar','Solar',(x,y,ROOF+.25),(3.5,3.45,.1))
        g.segment('SM_MPR_RoofSolar','Metal',(x,y-1.7),(x,y+1.7),.018,ROOF+.31,.012)
        solar_panels+=1

g.export(ROOT/'SourceAssets/MPR/architecture','mpr_architecture',dict(
    footprint_area_m2=CAD['footprint_area_m2'],apertures=apertures,
    roof_mesh_prefixes=['SM_MPR_Roof'],skylight_count=skylights,solar_cluster_count=solar_panels,
    height_basis={'clear_height_m':12.192,'source':'Prologis property brochure 40ft clear',
                  'roof_surface_m':ROOF,'facade_m':HEIGHT,'office_partition_m':3.3,
                  'external_ground_m':-1.2,'display_estimates':['roof structure depth','office height','dock height','solar layout']}))
