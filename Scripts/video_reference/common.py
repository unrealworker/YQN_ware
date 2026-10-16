"""Blender library helpers. Units metres; UE FBX import mirrors the Y axis."""
import bpy
import json
import math
from pathlib import Path
from mathutils import Vector

OUT=Path(r'D:\UEPro\Test\SourceAssets\VideoReference')
OUT.mkdir(parents=True,exist_ok=True)
MATERIALS={}
ASSETS=[]
ACTIVE=None

def reset():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=1.0

def material(name,color,roughness=.5,metallic=.0,**meta):
    name=name if name.startswith('M_VR_') else 'M_VR_'+name
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes=True
    bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value=(*color[:3],1)
    bs.inputs['Roughness'].default_value=roughness
    bs.inputs['Metallic'].default_value=metallic
    if meta.get('emission'):
        bs.inputs['Emission Color'].default_value=(*color[:3],1)
        bs.inputs['Emission Strength'].default_value=meta['emission']
    if 'opacity' in meta:
        bs.inputs['Alpha'].default_value=meta['opacity']
    m.diffuse_color=(*color[:3],meta.get('opacity',1))
    MATERIALS[name]=dict(name=name,base_color=[*color[:3],1],roughness=roughness,metallic=metallic,**meta)
    return m

def begin_asset(name):
    global ACTIVE
    ACTIVE=bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(ACTIVE)
    ASSETS.append((name,ACTIVE))
    return ACTIVE

def finish(o,name,mat):
    o.name=name
    for c in list(o.users_collection):c.objects.unlink(o)
    ACTIVE.objects.link(o)
    o['video_reference_asset']=ACTIVE.name
    if mat is not None:o.data.materials.append(mat)
    return o

def bevel(o,w=.006,segments=2):
    if w:
        b=o.modifiers.new('EdgeRadiuses','BEVEL');b.width=w;b.segments=segments
        n=o.modifiers.new('WeightedNormals','WEIGHTED_NORMAL');n.keep_sharp=True
    return o

def box(name,loc,size,mat,edge=.006):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    o=finish(bpy.context.object,name,mat);o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return bevel(o,min(edge,min(size)*.2))

def mesh(name,verts,faces,mat):
    d=bpy.data.meshes.new(name);d.from_pydata(verts,[],faces);d.update()
    o=bpy.data.objects.new(name,d);bpy.context.scene.collection.objects.link(o)
    return finish(o,name,mat)

def cylinder(name,loc,radius,depth,mat,vertices=32,axis='Z'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc)
    o=finish(bpy.context.object,name,mat)
    v={'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1)}[axis]
    o.rotation_euler=Vector(v).to_track_quat('Z','Y').to_euler()
    for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
    return o

def beam(name,a,b,radius,mat,vertices=8):
    a,b=Vector(a),Vector(b)
    o=cylinder(name,(a+b)/2,radius,(b-a).length,mat,vertices)
    o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
    return o

def curve(name,points,radius,mat,closed=False):
    d=bpy.data.curves.new(name,'CURVE');d.dimensions='3D';d.bevel_depth=radius;d.bevel_resolution=1
    s=d.splines.new('POLY');s.points.add(len(points)-1)
    for p,v in zip(s.points,points):p.co=(*v,1)
    s.use_cyclic_u=closed
    o=bpy.data.objects.new(name,d);bpy.context.scene.collection.objects.link(o)
    return finish(o,name,mat)

def text(name,body,loc,size,mat,rotation=(0,0,0),align='CENTER'):
    d=bpy.data.curves.new(name,'FONT');d.body=body;d.size=size;d.align_x=align;d.extrude=.0005;d.resolution_u=3
    o=bpy.data.objects.new(name,d);bpy.context.scene.collection.objects.link(o)
    o.location=loc;o.rotation_euler=rotation
    return finish(o,name,mat)

def rounded_box(name,loc,size,radius,mat):
    points=[]
    for x,y,a in [(size[0]/2-radius,size[1]/2-radius,0),(-size[0]/2+radius,size[1]/2-radius,90),(-size[0]/2+radius,-size[1]/2+radius,180),(size[0]/2-radius,-size[1]/2+radius,270)]:
        for i in range(7):
            angle=math.radians(a+90*i/6);points.append((x+radius*math.cos(angle),y+radius*math.sin(angle)))
    n=len(points);vs=[(x+loc[0],y+loc[1],z+loc[2]) for z in [-size[2]/2,size[2]/2] for x,y in points]
    fs=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return bevel(mesh(name,vs,fs,mat),.004)

def arc(name,radius,start,end,z,mat,width=.01,segments=48):
    return curve(name,[(radius*math.cos(math.radians(start+(end-start)*i/segments)),radius*math.sin(math.radians(start+(end-start)*i/segments)),z) for i in range(segments+1)],width,mat)

def save_library(stem):
    scene=bpy.context.scene
    scene.name='VideoReference_'+stem
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(stem+'.blend')))
    deps=bpy.context.evaluated_depsgraph_get()
    output=[]
    for name,col in ASSETS:
        originals=[o for o in col.objects if o.type in {'MESH','FONT','CURVE'}]
        copies=[]
        for o in originals:
            ev=o.evaluated_get(deps)
            data=bpy.data.meshes.new_from_object(ev,preserve_all_data_layers=True,depsgraph=deps)
            c=bpy.data.objects.new(o.name+'_FBX',data);scene.collection.objects.link(c);c.matrix_world=o.matrix_world.copy();copies.append(c)
        bpy.ops.object.select_all(action='DESELECT')
        for o in copies:o.select_set(True)
        bpy.context.view_layer.objects.active=copies[0]
        bpy.ops.object.join();obj=bpy.context.object;obj.name=name
        scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.cube_project(cube_size=1);bpy.ops.object.mode_set(mode='OBJECT')
        slots=[m.name for m in obj.data.materials]
        assert all(x in MATERIALS for x in slots)
        fbx=OUT/(name+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
        bounds=[[min(v.co[i] for v in obj.data.vertices),max(v.co[i] for v in obj.data.vertices)] for i in range(3)]
        output.append(dict(name=name,fbx=str(fbx),slots=slots,bounds_m=bounds,source_parts=len(originals),vertices=len(obj.data.vertices),polygons=len(obj.data.polygons)))
        bpy.data.objects.remove(obj,do_unlink=True)
    used={m for a in output for m in a['slots']}
    result=dict(meshes=output,materials=[MATERIALS[m] for m in sorted(used)],blend=str(OUT/(stem+'.blend')))
    (OUT/(stem+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('VIDEO_LIBRARY_COMPLETE',stem,len(output))
