"""Build reference-led Tiangong 96-bin sorter in an isolated background Blender.

Run: blender --background --factory-startup --python Tools/MPRWarehouse/build_mpr_sorter.py
One UE mesh per complete machine, 7 shared GHS material roles, explicit LOD0/1/2.
Assembly manual fig.8 supplies cart dimensions; full-machine envelope is estimated.
No user scene or source document is modified.
"""
import bpy, json, math, hashlib
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'SourceAssets/MPR/equipment'
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = Path(r'D:\Data\仓库数据\MPR\天工木马播种机设备')
ROLES = ['Porcelain','Cobalt','SoftBlue','Metal','Charcoal','Rubber','Glass']
COLORS = [(0.83,.85,.88),(.018,.075,.51),(.24,.39,.68),(.43,.49,.57),(.055,.075,.11),(.025,.035,.055),(.055,.14,.22)]
MATS = {}
PARTS=[]

def material(role,color):
    mat=bpy.data.materials.new('M_Zcool_'+role)
    mat.diffuse_color=(*color,1);mat.use_nodes=True
    p=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=.57 if role=='Metal' else .74
    p.inputs['Metallic'].default_value=.2 if role=='Metal' else 0
    return mat

def mesh(name,verts,faces,role,collection):
    data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);collection.objects.link(obj)
    data.materials.append(MATS[role]);PARTS.append(obj)
    return obj

def box(name,center,size,role,collection,rx=0):
    x,y,z=center;a,b,c=[q*.5 for q in size]
    verts=[(-a,-b,-c),(a,-b,-c),(a,b,-c),(-a,b,-c),(-a,-b,c),(a,-b,c),(a,b,c),(-a,b,c)]
    cr,sr=math.cos(rx),math.sin(rx)
    verts=[(x+vx,y+vy*cr-vz*sr,z+vy*sr+vz*cr) for vx,vy,vz in verts]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    return mesh(name,verts,faces,role,collection)

def rod(name,start,end,radius,role,collection,sides=8):
    a,b=Vector(start),Vector(end);axis=(b-a).normalized()
    tangent=axis.cross(Vector((0,0,1)))
    if tangent.length<.01:tangent=axis.cross(Vector((0,1,0)))
    tangent.normalize();bitangent=axis.cross(tangent).normalized()
    verts=[tuple(p+radius*(tangent*math.cos(2*math.pi*i/sides)+bitangent*math.sin(2*math.pi*i/sides))) for p in (a,b) for i in range(sides)]
    faces=[tuple(reversed(range(sides))),tuple(range(sides,sides*2))]+[(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
    return mesh(name,verts,faces,role,collection)

def bin_object(name,x,y,z,collection,simple=False):
    # 395 x 505 mm is read as the nominal outer bin family from manual fig.8.
    # Exact shell thickness/height taper not dimensioned: simplified visually.
    w,d,h=.395,.505,.180;t=.006
    rings=[]
    for rw,rd,rz in [(w*.85,d*.85,0),(w,d,h),(w-2*t,d-2*t,h),(w*.85-2*t,d*.85-2*t,t)]:
        rings += [(x-rw/2,y-rd/2,z+rz),(x+rw/2,y-rd/2,z+rz),(x+rw/2,y+rd/2,z+rz),(x-rw/2,y+rd/2,z+rz)]
    faces=[(0,3,2,1),(12,13,14,15)]
    for j,k in [(0,4),(4,8),(8,12)]:
        faces += [(j+i,j+(i+1)%4,k+(i+1)%4,k+i) for i in range(4)]
    o=mesh(name,rings,faces,'SoftBlue',collection)
    if not simple:
        for sy in (-1,1):box(name+'_Rim'+str(sy),(x,y+sy*(d/2),z+h),(.411,.012,.012),'SoftBlue',collection)
        for sx in (-1,1):box(name+'_Handle'+str(sx),(x+sx*w*.495,y,z+h-.045),(.008,.11,.018),'Cobalt',collection)
    return o

def generate(lod=0):
    global PARTS
    PARTS=[]
    col=bpy.data.collections.new('Tiangong96_Editable_LOD'+str(lod));bpy.context.scene.collection.children.link(col)
    xs=[-.5,0,.5];module_centers=[-2.34,-.78,.78,2.34]
    # Eight wheeled carts: 3 bins x 4 levels each; independent objects in .blend.
    bins=[]
    for side in (-1,1):
        for cart,cx in enumerate(module_centers):
            cy=side*1.10
            prefix=f'Cart_{side}_{cart+1}'
            for px in (-.72,.72):
                for py in (-.2525,.2525):
                    if lod<2:
                        rod(prefix+'_D28',(cx+px,cy+py,.105),(cx+px,cy+py,1.674),.014,'Metal',col,sides=6)
                        rod(prefix+'_Caster',(cx+px-.012,cy+py,.0315),(cx+px+.012,cy+py,.0315),.0315,'Rubber',col,sides=8)
                        box(prefix+'_WheelBracket',(cx+px,cy+py,.087),(.042,.042,.055),'Metal',col)
            for level in range(4):
                z=.16+level*.445
                for yoff in (-.2385,.2385):
                    box(prefix+f'_Rail_{level}_{yoff}',(cx,cy+yoff,z-.022),(1.44,.028,.028),'Metal',col)
                for j,xoff in enumerate(xs):
                    name=f'Bin_{"L" if side<0 else "R"}_{cart*3+j+1:02d}_{level+1}'
                    bin_object(name,cx+xoff,cy,z,col,simple=lod>0);bins.append(name)
    assert len(bins)==96
    # Main sorter backbone and 4 x 12 discharge chutes on both sides.
    for side in (-1,1):
        for ix,x in enumerate([-3.12,-1.56,0,1.56,3.12]):
            box(f'ChuteFrame_{side}_{ix}',(x,side*.76,1.17),(.04,.04,2.24),'Metal',col)
            if lod<2:rod('Foot',(x,side*.76,.01),(x,side*.76,.05),.045,'Charcoal',col)
        box(f'SideHeader_{side}',(0,side*.76,2.19),(6.27,.04,.24),'Porcelain',col)
        for level in range(4):
            base=.16+level*.445
            box(f'ChuteRail_{side}_{level}',(0,side*.77,base+.205),(6.24,.028,.035),'Metal',col)
            box(f'ConveyorRail_{side}_{level}',(0,side*.35,base+.30),(6.70,.055,.08),'Metal',col)
            if lod<2:box(f'Belt_{side}_{level}',(0,side*.20,base+.335),(6.60,.26,.018),'Cobalt',col)
            for cart,cx in enumerate(module_centers):
                for j,xoff in enumerate(xs):
                    x=cx+xoff;z=base+.30
                    # Four-tier tilted sheet-metal chutes; manual specifies 20 degrees.
                    box(f'Chute_{side}_{cart}_{j}_{level}',(x,side*.625,z),(.430,.62,.012),'Porcelain',col,rx=-side*math.radians(20))
                    if lod<2:
                        for sx in (-1,1):
                            box('ChuteSide',(x+sx*.213,side*.625,z+.065),(.009,.62,.13),'Porcelain',col,rx=-side*math.radians(20))
                        box('StatusStrip',(x,side*.927,base+.205),(.39,.008,.018),'Cobalt',col)
                    if level==3:
                        for light in range(4):box('StatusIndicator',(x,side*.784,2.13+light*.040),(.095,.007,.015),'Cobalt',col)
    for x in [-3.12,-1.56,0,1.56,3.12]:
        box('OverheadCrossBeam',(x,0,2.30),(.05,1.56,.05),'Metal',col)
    for y in (-.36,.36):
        box('MainTopRail',(0,y,2.32),(7.8,.055,.06),'Charcoal',col)
        box('MainFloorRail',(0,y,.20),(7.8,.055,.06),'Metal',col)
    # End turn/lift machinery and two ergonomic infeed stations.
    for side in (-1,1):
        x=side*3.69
        for xx in (x-.55,x+.55):
            for y in (-.73,.73):
                box('EndFrame',(xx,y,1.17),(.055,.055,2.24),'Metal',col)
                if lod<2:rod('EndLevelFoot',(xx,y,0),(xx,y,.061),.045,'Charcoal',col)
        box('EndCanopy',(x,0,2.31),(1.16,1.52,.07),'Porcelain',col)
        for y in (-.755,.755):
            box('EndPanel',(x,y,1.35),(1.10,.035,1.9),'Porcelain',col)
            box('EndServiceRecess',(x,y+(.020 if y>0 else -.020),.93),(.38,.012,.22),'Charcoal',col)
            box('BrandAccent',(x,y+(.026 if y>0 else -.026),1.94),(.39,.009,.07),'Cobalt',col)
            if lod==0:
                for stripe in range(3):box('BrandBars',(x,y+(.026 if y>0 else -.026),1.82-stripe*.045),(.39,.009,.016),'Cobalt',col)
        box('EndDoor',(x+side*.57,.39,1.16),(.035,.60,2.12),'Porcelain',col)
        for hz in (.6,1.37):box('EndWindow',(x+side*.592,.39,hz),(.008,.46,.58),'Glass',col)
        box('InfeedDeck',(x+side*.86,-.31,1.02),(.70,.90,.065),'Porcelain',col)
        box('InfeedBelt',(x+side*.79,-.31,1.056),(.48,.72,.014),'Cobalt',col)
        box('InfeedScreenSupport',(x+side*.55,-.74,1.34),(.035,.035,.68),'Metal',col)
        box('MonitorBody',(x+side*.58,-.72,1.66),(.065,.46,.30),'Charcoal',col)
        box('MonitorGlass',(x+side*.618,-.72,1.66),(.011,.41,.25),'Glass',col)
        if lod<2:
            rod('MotorHousing',(x-.17,0,2.36),(x+.17,0,2.36),.105,'Cobalt',col,sides=12)
            box('MotorGearbox',(x+.23,0,2.36),(.16,.20,.18),'Metal',col)
            for y in (-.36,.36):box('LiftBelt',(x,y,1.20),(.035,.022,1.94),'Rubber',col)
            box('LiftShuttle',(x,0,.90),(.74,.62,.06),'Cobalt',col)
        if lod==0:
            for xoff in (-.42,.42):
                box('ServiceFrame',(x+xoff,-.73,1.15),(.026,.030,2.10),'Charcoal',col)
    return col,bins

def bounds(objects):
    pts=[o.matrix_world@Vector(p) for o in objects for p in o.bound_box]
    return [[min(v[i] for v in pts),max(v[i] for v in pts)] for i in range(3)]

def export(col,name):
    originals=list(col.objects)
    # Joined duplicate retains semantic editable objects in source collection.
    bpy.ops.object.select_all(action='DESELECT')
    duplicates=[]
    for o in originals:
        n=o.copy();n.data=o.data.copy();bpy.context.scene.collection.objects.link(n);n.select_set(True);duplicates.append(n)
    bpy.context.view_layer.objects.active=duplicates[0];bpy.ops.object.join()
    joined=bpy.context.object;joined.name=name
    # Stable material slot contract independent of generation order.
    polys=[joined.data.materials[p.material_index].name.removeprefix('M_Zcool_') for p in joined.data.polygons]
    joined.data.materials.clear()
    for role in ROLES:joined.data.materials.append(MATS[role])
    for p,role in zip(joined.data.polygons,polys):p.material_index=ROLES.index(role)
    bpy.context.scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    joined.data.calc_loop_triangles();triangles=len(joined.data.loop_triangles)
    b=bounds([joined]);path=OUT/(name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,global_scale=1,
        bake_anim=False,add_leaf_bones=False,use_mesh_modifiers=True)
    bpy.data.objects.remove(joined,do_unlink=True)
    return {'name':name,'fbx':str(path),'material_roles':ROLES,'bounds_m':b,
        'triangles':triangles,'material_slots':len(ROLES),'editable_parts':len(originals),
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def preview(objects):
    for obj in bpy.context.scene.objects:obj.hide_render=obj not in objects
    scene=bpy.context.scene
    try:scene.render.engine='CYCLES'
    except TypeError as exc:raise RuntimeError(str(exc))
    scene.cycles.samples=24
    scene.render.resolution_x=1700;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    groundmat=material('GroundPreview',(.52,.58,.66));MATS['GroundPreview']=groundmat
    ground=box('PreviewGround',(0,0,-.08),(200,200,.10),'GroundPreview',scene.collection)
    ground.hide_render=False
    world=bpy.data.worlds.new('MPR Equipment Preview World');world.use_nodes=True
    world.node_tree.nodes.get('Background').inputs[0].default_value=(.70,.75,.82,1)
    world.node_tree.nodes.get('Background').inputs[1].default_value=.7;scene.world=world
    for i,(loc,power,size) in enumerate([((0,-4,9),1800,7),((3,5,7),1300,6)]):
        data=bpy.data.lights.new('PreviewArea'+str(i),'AREA');data.energy=power;data.shape='DISK';data.size=size
        o=bpy.data.objects.new(data.name,data);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('CAM_MPR_Sorter');camera=bpy.data.objects.new('CAM_MPR_Sorter',data);scene.collection.objects.link(camera)
    camera.location=(8.5,-11,8);camera.rotation_euler=(Vector((0,0,1))-camera.location).to_track_quat('-Z','Y').to_euler()
    data.type='ORTHO';data.ortho_scale=12.2;scene.camera=camera
    scene.render.filepath=str(OUT/'mpr_sorter_preview.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_Tiangong96.blend'))
    bpy.ops.render.render(write_still=True)

def main():
    assert bpy.data.filepath=='', 'Use --factory-startup; never overwrite a live Blender scene'
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    for role,color in zip(ROLES,COLORS):MATS[role]=material(role,color)
    specs=[];full=None
    for lod in range(3):
        col,bins=generate(lod)
        if lod==0:full=list(col.objects)
        row=export(col,'SM_MPR_Tiangong96'+('' if lod==0 else '_LOD'+str(lod)))
        row.update(lod=lod,bin_count=len(bins));specs.append(row)
        for obj in col.objects:obj.hide_render=lod!=0;obj.hide_set(lod!=0)
    assert all(s['bin_count']==96 and s['material_slots']==7 for s in specs)
    assert specs[2]['triangles']<specs[1]['triangles']<specs[0]['triangles']<50000
    sources=[SOURCE/'96格口木马装配指导书-V1.0(2).docx',SOURCE/'天工96宫格木马.jpg',SOURCE/'Snipaste_2026-10-30_16-27-55.png',SOURCE/'Snipaste_2026-10-30_16-30-02.png']
    manifest={'schema_version':1,'source_files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
      'units':'metres','origin':'center of machine plan at floor','axis':'X along length, Y across two sides, Z up; FBX -Y forward Z up',
      'confirmed':{'bins':96,'columns_per_side':12,'levels':4,'sides':2,'carts':8,
        'cart_frame_width_m':1.44,'cart_frame_depth_m':.505,'cart_height_m':1.687,'vertical_pitch_m':.445,
        'tube_diameter_m':.028,'caster_diameter_m':.063,'chute_slope_deg':20},
      'estimates':['Full machine envelope, end cabin dimensions, tray taper/thickness, slide width, screen and motor dimensions are visual reconstructions because no full machine dimensioned drawing is supplied.',
        'Light blue bins, white structure and cobalt belts use shared GHS presentation palette; no live telemetry or movement is implied.',
        'Placed count and machine alignment must be taken from CAD separately; PW_TG_96C_IN is not a complete 96-bin machine footprint.'],
      'material_paths':{r:'/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+r for r in ROLES},
      'meshes':specs,'recommended_lod_screen_sizes':[1,.22,.065],
      'blender':str(OUT/'MPR_Tiangong96.blend'),'preview':str(OUT/'mpr_sorter_preview.png'),
      'runtime_policy':'Static single mesh per machine with HISM for repeated machines; 7 slots, no Tick, no collision on decorative machine.'}
    (OUT/'sorter_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    preview(full)
    print('MPR_SORTER_CREATED '+json.dumps([{'name':s['name'],'triangles':s['triangles'],'bounds_m':s['bounds_m']} for s in specs]))

if __name__=='__main__':main()
