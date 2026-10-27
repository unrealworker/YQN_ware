"""Build the GHS blue cart from the placed STEP triangulation in Blender.

Run extract_cart_shell_step.py first; then Blender --background --python thisfile.
Run retopologize_cart_shell_1026.py after extraction.
Pass -- --reference for an unsimplified comparison render in Saved/CartShell1026.
"""
import bpy
import bmesh
import json
import math
import sys
import hashlib
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ROOT = Path(__file__).resolve().parents[2]
TEMP = ROOT / 'Saved/CartShell1026'
OUT = ROOT / 'SourceAssets/CartShell_1026'
DETAIL_20K='--20k' in sys.argv
if DETAIL_20K:OUT=OUT/'20k'
BUDGET=20000 if DETAIL_20K else 10000
OUT.mkdir(parents=True, exist_ok=True)
REFERENCE = '--reference' in sys.argv
data = json.loads((TEMP / 'assembly_mesh.json').read_text(encoding='utf8'))
optimized_file='optimized_parts_20k.json' if DETAIL_20K else 'optimized_shells.json'
optimized = {p['index']:p for p in json.loads((TEMP/optimized_file).read_text(encoding='utf8'))} if not REFERENCE else {}
all_vertices=[]
all_triangles=[]
for part in data['parts']:
    offset=len(all_vertices)
    all_vertices.extend([tuple(v/1000 for v in p) for p in part['vertices_mm']])
    all_triangles.extend([tuple(v+offset for v in f) for f in part['triangles']])
occluder=BVHTree.FromPolygons(all_vertices,all_triangles,all_triangles=True)
lo, hi = data['bounds_mm']
origin = [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version=0
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1
asset = bpy.data.collections.new('GHS_CART | CAD assembly')
scene.collection.children.link(asset)
studio = bpy.data.collections.new('STUDIO | excluded from exports')
scene.collection.children.link(studio)

def material(name, color, roughness, metallic):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat

materials = [
    material('GHS | Industrial blue', (.015, .06, .42), .34, .15),
    material('GHS | Deep blue lower shell', (.012, .045, .35), .38, .12),
    material('GHS | Silver hardware', (.64, .68, .73), .31, .65),
    material('GHS | Rubber charcoal', (.018, .023, .030), .76, 0),
    material('GHS | Motor graphite', (.035, .043, .052), .43, .35),
]

root = bpy.data.objects.new('GHS_CartShell_1026', None)
asset.objects.link(root)
root.empty_display_size=.04
root['source_units'] = 'millimeter'
root['source_origin_mm'] = origin
root['source_file'] = Path(data['source']).name
root['triangle_budget'] = BUDGET

def triangle_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)

def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def simplify(obj, target):
    activate(obj)
    before = triangle_count(obj)
    if before <= target:
        return
    mod = obj.modifiers.new('CAD silhouette budget', 'DECIMATE')
    mod.ratio = target / before
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)

parts_report = []
rejected_interior_bridges=0
for part in data['parts']:
    i = part['index']
    input_triangles=len(part['triangles'])
    if i in optimized:
        original=part
        part=dict(part,vertices_mm=optimized[i]['vertices_mm'],triangles=optimized[i]['triangles'],
                  colors=[(0,0,0)]*len(optimized[i]['triangles']))
        if DETAIL_20K and i>1 and part['triangles']:
            tree=KDTree(len(original['triangles']))
            old_vertices=[Vector(v) for v in original['vertices_mm']]
            for j,f in enumerate(original['triangles']):
                tree.insert(sum((old_vertices[v] for v in f),Vector())/3,j)
            tree.balance()
            new_vertices=[Vector(v) for v in part['vertices_mm']]
            part['colors']=[original['colors'][tree.find(sum((new_vertices[v] for v in f),Vector())/3)[1]] for f in part['triangles']]
    name = ('LowerShell' if i == 0 else 'UpperShell' if i == 1 else
            'DriveWheel' if i in (2, 4) else 'Caster' if i in (6,17,28,39) else 'Hardware')
    mesh = bpy.data.meshes.new(f'CAD_{i:02d}_{name}')
    vertices = [[(p[0]-origin[0])/1000,(p[1]-origin[1])/1000,max(0.0,(p[2]-origin[2])/1000)] for p in part['vertices_mm']]
    faces=part['triangles']
    colors=part['colors']
    if DETAIL_20K and i in optimized and i<6 and faces:
        source_vertices=[Vector(tuple((p[k]-origin[k])/1000 for k in range(3))) for p in original['vertices_mm']]
        source_tree=BVHTree.FromPolygons(source_vertices,original['triangles'],all_triangles=True)
        current_vertices=[Vector(v) for v in vertices]
        keep=[]
        for j,face in enumerate(faces):
            a,b,c=(current_vertices[v] for v in face)
            samples=((a+b+c)/3,(a+b)/2,(b+c)/2,(c+a)/2)
            # Collapse is allowed inside, but may never create a new sheet
            # spanning an original opening or fold a panel away from the CAD.
            if max(source_tree.find_nearest(p)[3] for p in samples)<.0005:
                keep.append(j)
        rejected_interior_bridges+=len(faces)-len(keep)
        colors=[colors[j] for j in keep]
        faces=[faces[j] for j in keep]
    if not REFERENCE and i not in optimized:
        keep=[]
        directions=[Vector((x,y,z)).normalized() for x,y,z in
                    [(x,y,z) for x in (-1,0,1) for y in (-1,0,1) for z in (-1,0,1) if x or y or z]]
        worldverts=[Vector(tuple(v/1000 for v in p)) for p in part['vertices_mm']]
        for fi, face in enumerate(faces):
            a,b,c=(worldverts[v] for v in face)
            normal=(b-a).cross(c-a).normalized()
            center=(a+b+c)/3
            # Remove fully occluded CAD internals before spending the game-mesh budget.
            probes=[normal]+[d for d in directions if d.dot(normal)>.12]
            for direction in probes:
                hit=occluder.ray_cast(center+direction*.00001,direction,2)[0]
                if hit is None:
                    keep.append(fi)
                    break
        visible_patches={part['face_ids'][k] for k in keep}
        keep=[k for k in range(len(faces)) if part['face_ids'][k] in visible_patches]
        faces=[faces[k] for k in keep]
        colors=[colors[k] for k in keep]
    if not faces:
        bpy.data.meshes.remove(mesh)
        parts_report.append(dict(index=i,name=f'{i:02d}_{name}',cad_name=part['name'],input_triangles=input_triangles,triangles=0))
        continue
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f'{i:02d}_{name}', mesh)
    asset.objects.link(obj)
    obj.parent = root
    obj['cad_part_name'] = part['name']
    obj['source_index'] = i
    for mat in materials:
        mesh.materials.append(mat)
    for poly, rgb in zip(mesh.polygons, colors):
        if i == 0:
            mat_index = 1
        elif i == 1:
            mat_index = 0
        elif i in (2,4):
            center = sum((Vector(vertices[v]) for v in poly.vertices), Vector()) / len(poly.vertices)
            radius = math.hypot(center.y, center.z-.0795)
            mat_index = 3 if abs(center.x) > .157 else 4 if max(rgb)<.12 else 2
        elif i in (6,17,28,39):
            mat_index = 3 if rgb[0]>.8 and rgb[1]<.2 else 2
        else:
            mat_index = 2
        poly.material_index = mat_index
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000001)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=.0000001)
    if not REFERENCE:
        bmesh.ops.dissolve_limit(bm,angle_limit=math.radians(.005 if DETAIL_20K else .05),verts=list(bm.verts),edges=list(bm.edges),delimit={'MATERIAL'})
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(clean_customdata=False)
    mesh.update()
    normal_source = None
    if not REFERENCE and i not in optimized and len(mesh.polygons) and i not in (2,4):
        normal_source = obj.copy()
        normal_source.data = obj.data.copy()
        scene.collection.objects.link(normal_source)
        for poly in normal_source.data.polygons:
            poly.use_smooth=True
        normal_source.data.set_sharp_from_angle(angle=math.radians(35))
        activate(normal_source)
        norm=normal_source.modifiers.new('Source CAD normals','WEIGHTED_NORMAL')
        norm.keep_sharp=True
        bpy.ops.object.modifier_apply(modifier=norm.name)
    if not REFERENCE and i not in optimized:
        budget = 3000 if i in (0,1) else 950 if i in (2,4) else 60 if i in (3,5) else 220 if i in (6,17,28,39) else 30
        simplify(obj, budget)
    for poly in obj.data.polygons:
        poly.use_smooth = not ((i in (0,1) and abs(poly.normal.z)>.98) or (i in (2,4) and abs(poly.normal.x)>.98))
        if DETAIL_20K and max(abs(n) for n in poly.normal)>.999:
            poly.use_smooth=False
    obj.data.set_sharp_from_angle(angle=math.radians(35))
    activate(obj)
    norm = obj.modifiers.new('CAD weighted normals', 'WEIGHTED_NORMAL')
    norm.keep_sharp = True
    norm.weight = 50
    bpy.ops.object.modifier_apply(modifier=norm.name)
    if normal_source:
        transfer=obj.modifiers.new('Preserve CAD surface normals','DATA_TRANSFER')
        transfer.object=normal_source
        transfer.use_loop_data=True
        transfer.data_types_loops={'CUSTOM_NORMAL'}
        transfer.loop_mapping='POLYINTERP_NEAREST'
        bpy.ops.object.modifier_apply(modifier=transfer.name)
        source_mesh=normal_source.data
        bpy.data.objects.remove(normal_source,do_unlink=True)
        bpy.data.meshes.remove(source_mesh)
    parts_report.append(dict(index=i, name=obj.name, cad_name=part['name'],
                             input_triangles=input_triangles, triangles=triangle_count(obj)))
    print('MESH', i, triangle_count(obj), flush=True)

if not REFERENCE:
    total = sum(p['triangles'] for p in parts_report)
    if total > BUDGET and not DETAIL_20K:
        drive = bpy.data.objects['02_DriveWheel']
        simplify(drive, triangle_count(drive)-(total-10000)-4)
        activate(drive)
        drive.data.set_sharp_from_angle(angle=math.radians(35))
        norm=drive.modifiers.new('Final weighted normals','WEIGHTED_NORMAL')
        norm.keep_sharp=True
        bpy.ops.object.modifier_apply(modifier=norm.name)
        parts_report[2]['triangles']=triangle_count(drive)

# Orthographic studio, physically sized lighting. Studio geometry is never exported.
floor_mat = material('STUDIO | soft blue gray', (.40,.45,.51), .86, 0)
floor_mesh = bpy.data.meshes.new('StudioFloor')
floor_mesh.from_pydata([(-200,-200,-.001),(200,-200,-.001),(200,200,-.001),(-200,200,-.001)],[],[(0,1,2,3)])
floor = bpy.data.objects.new('Studio ground',floor_mesh)
studio.objects.link(floor)
floor.data.materials.append(floor_mat)

def aim(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()

for name, location, energy, size in [
    ('Key softbox',(.4,-.6,1.2),24,1.0),
    ('Fill softbox',(-.6,-.1,.6),9,.8),
    ('Rim softbox',(.1,.7,1),30,.7),
]:
    light = bpy.data.lights.new(name,'AREA')
    light.energy, light.shape, light.size = energy,'DISK',size
    obj = bpy.data.objects.new(name,light)
    studio.objects.link(obj)
    obj.location = location
    aim(obj,(0,0,.08))
world = bpy.data.worlds.new('GHS soft studio')
world.use_nodes = True
next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND').inputs[0].default_value=(.55,.64,.78,1)
next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND').inputs[1].default_value=.35
scene.world = world
camera_data = bpy.data.cameras.new('Camera')
camera = bpy.data.objects.new('Camera',camera_data)
studio.objects.link(camera)
camera_data.type='ORTHO'
camera_data.ortho_scale=.79
camera.location=(.68,-.85,.68)
aim(camera,(0,0,.09))
scene.camera=camera
scene.render.engine='CYCLES'
scene.cycles.samples=48
scene.cycles.use_denoising=True
scene.render.resolution_x=1400
scene.render.resolution_y=1100
scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'
scene.view_settings.look='AgX - Medium High Contrast'
scene.view_settings.exposure=-.3
scene.render.image_settings.file_format='PNG'

activate(root)
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        space=area.spaces.active
        space.shading.type='MATERIAL'
        space.overlay.show_overlays=False
        space.region_3d.view_distance=.9
        space.region_3d.view_location=(0,0,.09)
        space.region_3d.view_rotation=camera.rotation_euler.to_quaternion()
        space.clip_start=.001
        space.clip_end=100

if REFERENCE:
    scene.render.filepath=str(TEMP/'reference.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(TEMP/'reference.blend'))
    bpy.ops.render.render(write_still=True)
else:
    total=sum(p['triangles'] for p in parts_report)
    assert BUDGET*.9 <= total <= BUDGET, total
    manifest=dict(source=data['source'], source_sha256=hashlib.sha256(Path(data['source']).read_bytes()).hexdigest(),
                  source_size_mm=data['size_mm'], triangle_count=total, triangle_budget=BUDGET,source_part_count=len(parts_report),
                  mesh_part_count=sum(p['triangles']>0 for p in parts_report),
                  units='meters', up_axis='Z', origin='floor center', cad_origin_mm=origin,
                  input_triangles=sum(p['input_triangles'] for p in parts_report), parts=parts_report,
                  rejected_interior_bridge_triangles=rejected_interior_bridges,
                  palette_source='SourceAssets/GHS_Normal/material_style.json',
                  optimization=('Original visible CAD patches, including hole walls and window-visible internals; visibility culling and weighted simplification' if DETAIL_20K else 'CAD exterior patches and original top plate; simplified rim strips; hidden mechanical faces culled; minor hardware decimated'),
                  materials=[dict(name=m.name,linear_rgba=list(m.diffuse_color)) for m in materials])
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in asset.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=root
    bpy.ops.export_scene.fbx(filepath=str(OUT/'SM_CartShell_1026.fbx'),use_selection=True,
        object_types={'MESH','EMPTY'},apply_unit_scale=True,axis_forward='-Y',axis_up='Z',
        bake_anim=False,add_leaf_bones=False,mesh_smooth_type='FACE')
    bpy.ops.export_scene.gltf(filepath=str(OUT/'CartShell_1026.glb'),export_format='GLB',use_selection=True)
    activate(root)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'CartShell_1026.blend'))
    scene.render.filepath=str(OUT/'preview_front.png')
    bpy.ops.render.render(write_still=True)
    camera.location=(-.65,.85,.6)
    aim(camera,(0,0,.09))
    scene.render.filepath=str(OUT/'preview_rear.png')
    bpy.ops.render.render(write_still=True)
    print('COMPLETE',total,'triangles',flush=True)
