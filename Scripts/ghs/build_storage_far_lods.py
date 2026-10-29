"""Build reviewed far-LOD source files without importing or saving UE assets.

Run with Blender --background --factory-startup --python this_file.py.
LOD2 retains every carton and pallet part, without subpixel bevel rings.
LOD3 retains the entire carton exterior (including the underside), adds a
closed recessed backing behind the 3mm seams, and retains every pallet part.
Both preserve the three source material slots and every visible seam line.
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import math
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'SourceAssets/GHS/DoublePallet'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=SOURCE/'FarLOD',
                    help='Output directory; relative paths are relative to the project root')
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
OUT = (args.output if args.output.is_absolute() else ROOT/args.output).resolve()
assert OUT != SOURCE.resolve(), 'Use the FarLOD subdirectory; preserve the original source library'
OUT.mkdir(parents=True, exist_ok=True)
manifest = json.loads((SOURCE / 'double_pallet_storage.json').read_text())
specs = {row['name']: row for row in manifest['meshes']}
source_files = [SOURCE / 'double_pallet_storage.blend', SOURCE / 'double_pallet_storage.json']
source_files += list(SOURCE.glob('SM_GHS_Presentation_Cargo*.fbx'))
hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 1.0
material_names = specs['SM_GHS_Presentation_CargoMid']['slots']
materials = []
for name, color in zip(material_names, [(.015,.18,.44,1),(.70,.74,.78,1),(.37,.46,.53,1)]):
    m = bpy.data.materials.new(name)
    m.diffuse_color = color
    materials.append(m)


class Geometry:
    # Faces are outward-facing; all bottom faces explicitly retained.
    cube_faces = [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]

    def __init__(self):
        self.vertices = []
        self.faces = []
        self.material_indices = []
        self.roles = Counter()
        self.pallet_boxes = []

    def emit(self, vertices, faces, material, role):
        start = len(self.vertices)
        self.vertices.extend(vertices)
        for face in faces:
            self.faces.append(tuple(start+i for i in face))
            self.material_indices.append(material)
            self.roles[role] += len(face)-2

    def box(self, center, size, material, role, faces=None):
        x,y,z = center
        hx,hy,hz = [d/2 for d in size]
        points = [(x+dx,y+dy,z+dz) for dz in (-hz,hz)
                  for dx,dy in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]]
        face_list = self.cube_faces if faces is None else [self.cube_faces[i] for i in faces]
        self.emit(points, face_list, material, role)
        if material == 0:
            self.pallet_boxes.append(dict(center=center,size=size))

    def wall_line(self, wall, along, z, length, width, horizontal):
        # Place the same flat line just outside the source carton face, avoiding
        # coplanar Z-fighting. Opposite-wall winding is reversed explicitly.
        plane = {'front':-.4803,'back':.4803,'left':-.5803,'right':.5803}[wall]
        half_l, half_w = length/2, width/2
        a,b = (half_l,half_w) if horizontal else (half_w,half_l)
        pairs = [(along-a,z-b),(along+a,z-b),(along+a,z+b),(along-a,z+b)]
        if wall in ('front','back'):
            points = [(u,plane,v) for u,v in pairs]
            if wall == 'back': points.reverse()
        else:
            points = [(plane,u,v) for u,v in pairs]
            if wall == 'left': points.reverse()
        self.emit(points,[(0,1,2,3)],2,'seam_strips')

    def top_line(self, x, y, z, dx, dy):
        self.emit([(x-dx/2,y-dy/2,z),(x+dx/2,y-dy/2,z),
                   (x+dx/2,y+dy/2,z),(x-dx/2,y+dy/2,z)],[(0,1,2,3)],2,'seam_strips')


def build(suffix, layers, lod):
    name = 'SM_GHS_Presentation_Cargo'+suffix
    spec = specs[name]
    height = spec['original_bounds_m'][2][1]
    half = height/2
    g = Geometry()
    for tier, base in enumerate((0.,half)):
        # Same 22 source pallet pieces per tier. No underside, fork opening,
        # edge board or deck spacing is removed, even in the farthest LOD.
        for x in (-.535,0,.535):
            g.box((x,0,base+.018),(.13,1.,.036),0,'pallet_runners')
            for y in (-.40,0,.40):
                g.box((x,y,base+.079),(.13,.16,.086),0,'pallet_blocks')
        for i in range(8):
            g.box((0,-.45+i*.9/7,base+.143),(1.2,.10,.042),0,'pallet_deck')
        for x in (-.585,.585):
            g.box((x,0,base+.145),(.03,1.,.05),0,'pallet_rims')
        start = base+.173
        top = base+half-.0030311603546143
        step = (top-start)/layers
        for ix in range(3):
            for iy in range(3):
                for iz in range(layers):
                    faces = None if lod == 2 else [i for i, visible in enumerate(
                        (iz==0,iz==layers-1,iy==0,ix==2,iy==2,ix==0)) if visible]
                    if faces == []: continue
                    g.box(((ix-1)*1.16/3,(iy-1)*.96/3,start+(iz+.5)*step),
                          (1.16/3-.003,.96/3-.003,step-.003),1,'carton_surfaces',faces)
        if lod == 3:
            # The source 3mm inter-box joints connect to the exterior. Removing
            # inward faces without a backing would expose empty space. A closed
            # backing inset 5mm preserves dark seam depth from every direction.
            g.box((0,0,(start+top)/2),(1.16-.010,.96-.010,top-start-.010),1,'recessed_joint_backing')
        for z in [start+i*step for i in range(layers+1)]:
            for wall in ('front','back','left','right'):
                # Match the original round seam extrema, including top bounds.
                full_width = .0060623207092286
                g.wall_line(wall,0,z,1.16 if wall in ('front','back') else .96,full_width,True)
        for wall in ('front','back','left','right'):
            span = 1.16 if wall in ('front','back') else .96
            for i in range(4):
                g.wall_line(wall,-span/2+i*span/3,(start+top)/2,top-start,.007,False)
        for x in (-.58,-.58+1.16/3,-.58+2*1.16/3,.58):
            g.top_line(x,0,top,.006,.96)
        for y in (-.48,-.16,.16,.48):
            g.top_line(0,y,top,1.16,.006)
    mesh = bpy.data.meshes.new(name+'_LOD'+str(lod))
    mesh.from_pydata(g.vertices,[],g.faces)
    mesh.update()
    for material in materials: mesh.materials.append(material)
    for poly,index in zip(mesh.polygons,g.material_indices): poly.material_index=index
    obj = bpy.data.objects.new(mesh.name,mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1)
    bpy.ops.object.mode_set(mode='OBJECT')
    mesh.calc_loop_triangles()
    actual = len(mesh.loop_triangles)
    assert actual == sum(g.roles.values())
    assert len(g.pallet_boxes) == 44
    bounds = [[min(v.co[i] for v in mesh.vertices),max(v.co[i] for v in mesh.vertices)] for i in range(3)]
    assert max(abs(a-b) for old,new in zip(spec['bounds_m'],bounds) for a,b in zip(old,new)) < 2e-6, bounds
    assert set(g.material_indices) == {0,1,2}
    assert all(math.isfinite(x) for vertex in mesh.vertices for x in vertex.co)
    # Every low-level pallet part has all six sides, so bottom/side views and
    # fork insertion openings remain actual geometry instead of a blue block.
    assert sum(v for k,v in g.roles.items() if k.startswith('pallet_')) == 44*12
    fbx = OUT/(mesh.name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
        mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
    return dict(name=name,lod=lod,triangles=actual,fbx=fbx.name,bounds_m=bounds,
                material_slots=material_names,role_triangles=dict(g.roles),pallet_part_count=44,
                pallet_base_z_m=[0,half],sha256=hashlib.sha256(fbx.read_bytes()).hexdigest())

rows=[]
for suffix,layers in [('Low',2),('Mid',3),('High',4)]:
    for lod in (2,3): rows.append(build(suffix,layers,lod))
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'storage_far_lods.blend'))
result=dict(success=True,status='pending_ue_visual_acceptance_and_import',
            production_assets_modified=False,source_sha256=hashes,meshes=rows,
            editable_source='storage_far_lods.blend',
            editable_source_sha256=hashlib.sha256((OUT/'storage_far_lods.blend').read_bytes()).hexdigest(),
            generator='Scripts/ghs/build_storage_far_lods.py',
            lod0_lod1='unchanged; candidates only replace LOD2 and LOD3 in an isolated UE copy',
            screen_sizes=[1.,.35,.12,.03])
(OUT/'storage_far_lods.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('STORAGE_FAR_LOD_SOURCES '+json.dumps(result))


