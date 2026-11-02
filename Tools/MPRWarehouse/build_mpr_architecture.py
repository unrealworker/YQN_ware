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

# Roof layout is traced from the supplied oblique roof photograph. The image is
# sampled for geometry only; it is never imported as a UE texture/material.
# CAD +X is the stepped east end, CAD -Y is the southern loading court. Four
# identifiable roof corners provide a planar homography; readback is estimated,
# not a surveyed as-built PV installation or a count of electrical modules.
import bpy, numpy as np, hashlib
OUT=ROOT/'SourceAssets/MPR/architecture'
REFERENCE=Path(r'D:\Data\仓库数据\MPR\仓库周围环境\Snipaste_2026-10-30_16-02-59.png')
roof_points=[[-181.93004,83.69038],[182.61076,83.58878],
             [135.36676,-83.94962],[-181.93004,-93.09362]]
photo_points=[[378,69],[1512,100],[1470,480],[167,474]]
equations=[];values=[]
for (x,y),(u,v) in zip(roof_points,photo_points):
    equations.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]])
    values.extend([u,v])
homography=np.r_[np.linalg.solve(equations,values),1].reshape(3,3)
inverse=np.linalg.inv(homography)
image=bpy.data.images.load(str(REFERENCE),check_existing=False);iw,ih=image.size
pixels=np.empty(iw*ih*4,dtype=np.float32);image.pixels.foreach_get(pixels)
pixels=pixels.reshape(ih,iw,4)[::-1,:,:3]*255

def photo_xy(x,y):
    q=homography@np.array([x,y,1.]);return q[:2]/q[2]

def blue_panel(x,y):
    u,v=photo_xy(x,y);u,v=int(round(u)),int(round(v))
    if u<2 or v<2 or u>=iw-2 or v>=ih-2:return False
    # A 3x3 median is stable across thin white module seams and photo texture.
    r,gg,b=np.median(pixels[v-1:v+2,u-1:u+2,:],axis=(0,1))
    return b-r>10 and b-gg>3 and 42<(r+gg+b)/3<173

def roof_clearance(x,y,dx,dy):
    return all(inside(x+sx*dx,y+sy*dy) for sx in (-1,1) for sy in (-1,1))

# Repeated low strips follow the true high-density fields. Large white patches
# and the central north/south service corridor survive the source sampling.
# Tiny isolated blue objects (vents, image labels) are removed as components.
pitch_x=1.12;pitch_y=1.95;origin_x=-47.6;origin_y=-80.9
grid={};photograph_restored=[]
for ix in range(193):
    x=origin_x+ix*pitch_x
    for iy in range(79):
        y=origin_y+iy*pitch_y
        if not roof_clearance(x,y,3.0,3.0):continue
        if x<17.6 and not ((x>-46 and y<-34) or (x>-23 and y<1)):continue
        if 17.6<x<22.8:continue  # continuous principal service corridor
        samples=sum(blue_panel(x+dx,y+dy) for dx,dy in [(0,0),(-.25,-.45),(.25,-.45),(-.25,.45),(.25,.45)])
        occupied=samples>=3
        # A Google Maps red place-pin obscures this connected existing bank;
        # adjacent-angle 16-04-43 and 16-03-26 confirm the occupied strip below.
        if 5.0<x<11.8 and -32<y<-18:
            occupied=True;photograph_restored.append([x,y])
        if occupied:grid[(ix,iy)]=(x,y)
remaining=set(grid);keep=set()
while remaining:
    first=remaining.pop();stack=[first];component=[]
    while stack:
        ix,iy=stack.pop();component.append((ix,iy))
        for q in [(ix-1,iy),(ix+1,iy),(ix,iy-1),(ix,iy+1)]:
            if q in remaining:remaining.remove(q);stack.append(q)
    if len(component)>=6:keep.update(component)
grid={key:grid[key] for key in sorted(keep)}
strips=[];solar_panels=len(grid)
for ix in range(193):
    rows=sorted(iy for gx,iy in grid if gx==ix);runs=[]
    for iy in rows:
        if not runs or iy>runs[-1][-1]+1:runs.append([iy])
        else:runs[-1].append(iy)
    for run in runs:
        x=origin_x+ix*pitch_x;y0=origin_y+run[0]*pitch_y-pitch_y*.48
        y1=origin_y+run[-1]*pitch_y+pitch_y*.48;w=pitch_x*.94
        g.box('SM_MPR_RoofSolar','Solar',(x,(y0+y1)/2,ROOF+.16),(w,y1-y0,.08))
        # Only two edge rails per continuous bank, plus inexpensive surface
        # module joints. No per-panel Actor, duplicate support grids or tick.
        for side in (-1,1):
            xx=x+side*w/2
            g.mesh('SM_MPR_RoofSolar','Metal',[(xx-.006,y0,ROOF+.205),(xx+.006,y0,ROOF+.205),
                   (xx+.006,y1,ROOF+.205),(xx-.006,y1,ROOF+.205)],[(0,1,2,3)])
        for iy in run[:-1]:
            y=origin_y+(iy+.5)*pitch_y
            g.mesh('SM_MPR_RoofSolar','Metal',[(x-w/2,y-.006,ROOF+.206),(x+w/2,y-.006,ROOF+.206),
                   (x+w/2,y+.006,ROOF+.206),(x-w/2,y+.006,ROOF+.206)],[(0,1,2,3)])
        strips.append(dict(x=x,y0=y0,y1=y1,width=w,modules=len(run)))

# Read the small isolated blue/gray roof lights from the same calibrated image.
# Large connected solar fields are filtered by projected pixel area. Candidate
# centers are merged within 1.5m, then rejected if they land on an occupied bank.
average=pixels.mean(axis=2)
mask=(pixels[:,:,2]-pixels[:,:,0]>6)&(average>65)&(average<211)
mask[:90,:]=False;mask[460:,:]=False;mask[:,:170]=False;mask[:,1580:]=False
remaining=set((int(x),int(y)) for y,x in zip(*np.where(mask)))
lights=[]
while remaining:
    first=remaining.pop();stack=[first];component=[]
    while stack:
        u,v=stack.pop();component.append((u,v))
        for q in [(u-1,v),(u+1,v),(u,v-1),(u,v+1),(u-1,v-1),(u+1,v-1),(u-1,v+1),(u+1,v+1)]:
            if q in remaining:remaining.remove(q);stack.append(q)
    if not 3<=len(component)<=65:continue
    p=np.array(component);u,v=p.mean(axis=0);q=inverse@np.array([u,v,1.]);x,y=q[:2]/q[2]
    if not roof_clearance(x,y,4,4):continue
    if np.ptp(p[:,0])>14 or np.ptp(p[:,1])>10:continue
    if any(abs(x-t['x'])<t['width']/2+1.1 and t['y0']-1<y<t['y1']+1 for t in strips):continue
    if any(math.hypot(x-a,y-b)<1.5 for a,b in lights):continue
    lights.append((float(x),float(y)))
lights.sort()
for x,y in lights:
    g.box('SM_MPR_RoofPlant','Detail',(x,y,ROOF+.07),(1.55,1.05,.14))
    g.box('SM_MPR_RoofPlant','Skylight',(x,y,ROOF+.16),(1.37,.87,.06))
skylights=len(lights)

layout=dict(schema_version=2,coordinate_system='CAD metres, +X stepped east end, -Y south loading court; no UE Y mirror applied',
    reference=REFERENCE.name,reference_sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
    cross_checks=['Snipaste_2026-10-30_16-03-26.png','Snipaste_2026-10-30_16-03-46.png','Snipaste_2026-10-30_16-04-17.png','Snipaste_2026-10-30_16-04-43.png','Snipaste_2026-10-30_16-13-26.png'],
    cad_control_points_m=roof_points,image_control_points_px=photo_points,homography=homography.tolist(),
    panel_pitch_m=[pitch_x,pitch_y],principal_corridor_x_m=[17.6,22.8],
    solar_module_cells=solar_panels,continuous_strips=strips,skylight_centers_m=lights,
    photo_pin_restored_cells=photograph_restored,
    assumptions=['Planar photo-to-CAD alignment and small array boundaries are image readings, estimated within roughly 2-5m; not an as-built survey.',
    'Grid pitch, individual module dimensions and low mounting heights are visualization estimates. Cell count is not verified electrical module capacity.',
    'Only isolated visible roof-light centers are reconstructed; photograph labels, shadows and resolution can hide small fixtures.',
    'Dense east banks, southwest separate banks, central service corridor and staggered white clearances follow the supplied photos; no checkerboard rule.'])
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'roof_layout_reference.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf8')

# Geometry-only vector plan for review, with explicit CAD coordinates and scale.
def sx(x):return 75+(x+190)*3.7
def sy(y):return 105+(95-y)*3.7
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1560" height="900" viewBox="0 0 1560 900">',
 '<rect width="1560" height="900" fill="#e8eef3"/>',
 '<text x="75" y="40" font-family="Arial,Microsoft YaHei" font-size="25" fill="#19354b">MPR 屋顶光伏 / 天窗 — 照片标定平面预览</text>',
 '<text x="75" y="72" font-family="Arial,Microsoft YaHei" font-size="17" fill="#43596a">照片读数估计（约 2–5 m）；CAD 轮廓固定。+X：阶梯端；−Y：南侧装卸场。非光伏施工图。</text>',
 '<polygon points="'+' '.join(f'{sx(x):.2f},{sy(y):.2f}' for x,y in fp)+'" fill="#fbfcfd" stroke="#42596c" stroke-width="2"/>']
for t in strips:svg.append(f'<rect x="{sx(t["x"]-t["width"]/2):.2f}" y="{sy(t["y1"]):.2f}" width="{t["width"]*3.7:.2f}" height="{(t["y1"]-t["y0"])*3.7:.2f}" fill="#24465d"/>')
for x,y in lights:svg.append(f'<rect x="{sx(x)-2.5:.2f}" y="{sy(y)-1.7:.2f}" width="5" height="3.4" fill="#95b3cb" stroke="#49657c" stroke-width=".5"/>')
for x in range(-150,181,50):svg.append(f'<text x="{sx(x):.2f}" y="814" font-family="Arial" font-size="15" text-anchor="middle" fill="#43596a">X {x} m</text>')
svg.extend([f'<line x1="75" y1="853" x2="260" y2="853" stroke="#19354b" stroke-width="3"/>',
 '<text x="167" y="877" text-anchor="middle" font-family="Arial" font-size="16" fill="#19354b">50 m</text>',
 f'<text x="325" y="858" font-family="Arial,Microsoft YaHei" font-size="17" fill="#43596a">{len(strips)} 条合并板带 · {solar_panels} 个视觉模块 · {skylights} 处可识别天窗 · 中央通道 X=17.6–22.8 m</text>', '</svg>'])
(OUT/'roof_layout_preview.svg').write_text('\n'.join(svg),encoding='utf8')
bpy.data.images.remove(image)

g.export(ROOT/'SourceAssets/MPR/architecture','mpr_architecture',dict(
    footprint_area_m2=CAD['footprint_area_m2'],apertures=apertures,
    roof_mesh_prefixes=['SM_MPR_Roof'],skylight_count=skylights,solar_cluster_count=len(strips),solar_module_cells=solar_panels,
    roof_layout_reference='SourceAssets/MPR/architecture/roof_layout_reference.json',
    height_basis={'clear_height_m':12.192,'source':'Prologis property brochure 40ft clear',
                  'roof_surface_m':ROOF,'facade_m':HEIGHT,'office_partition_m':3.3,
                  'external_ground_m':-1.2,'display_estimates':['roof structure depth','office height','dock height','solar layout']}))
