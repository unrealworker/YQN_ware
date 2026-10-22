"""Generate independent display glazing for the warehouse elevations.

Run with Blender in background. Existing walls, roof, ground, CAD and Unreal
assets are read-only. Editable named parts and the merged export share exactly
the same geometry. Configuration-driven extra groups retain the original office
corner geometry and distinguish high, full-height and split-level glazing.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GHS/OfficeFacade'
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
sys.dont_write_bytecode = True
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

NAME = 'SM_GHS_OfficeGlassFacade'
ORIGIN = (239.33385, 60.24019)
ROLES = ('Glass', 'Frame', 'Panel', 'Pier', 'Sill')
PALETTE = {
    'Glass': ((.027, .085, .155), .18, .18),
    'Frame': ((.50, .59, .68), .45, .35),
    'Panel': ((.78, .82, .87), .8, 0.),
    'Pier': ((.69, .74, .80), .8, 0.),
    'Sill': ((.60, .66, .72), .8, 0.),
}
FACADES = (
    dict(id='West', plane_u_m=0., s_min_m=118.872, s_max_m=137.16,
         bay_count=3, bay_pitch_m=6.096, outward_uv=[-1, 0]),
    dict(id='Front', plane_v_m=137.16, s_min_m=0., s_max_m=45.8724,
         bay_count=5, bay_pitch_m=9.17448, outward_uv=[0, 1]),
)
GLASS_Z = (.24, 6.54)
FRAME_WIDTH = .09
MULLION_WIDTH = .075
PIER_WIDTH = .78
GLASS_DEPTH = (.08, .10)
FRAME_DEPTH = (.10, .18)
TRIANGLE_BUDGET = 30000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def point(u, v, z):
    return (u - ORIGIN[0], -(v - ORIGIN[1]), z)


def bounds_ue(mesh):
    coords = [(v.co.x * 100, -v.co.y * 100, v.co.z * 100) for v in mesh.vertices]
    return dict(min=[min(p[i] for p in coords) for i in range(3)],
                max=[max(p[i] for p in coords) for i in range(3)])


def make_material(name, color, roughness, metallic):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    principled = next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if principled is None:
        principled = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        output = material.node_tree.nodes.new('ShaderNodeOutputMaterial')
        material.node_tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    principled.inputs['Base Color'].default_value = (*color, 1)
    principled.inputs['Roughness'].default_value = roughness
    principled.inputs['Metallic'].default_value = metallic
    return material


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    layout_path = OUT / 'facade_layout.json'
    layout = json.loads(layout_path.read_text(encoding='utf-8-sig'))
    layout_hash = sha(layout_path)
    groups = layout['groups']
    assert groups and len({g['id'] for g in groups}) == len(groups)
    assert not {'West', 'Front'}.intersection(g['id'] for g in groups)
    previous_path = OUT / 'facade_manifest.json'
    previous = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else None
    envelope_path = ROOT / 'SourceAssets/GHS/RefinementV2/Envelope/envelope_geometry.json'
    protected = [envelope_path,
                 ROOT / 'SourceAssets/GHS/RefinementV2/Envelope/building_footprint.json',
                 ROOT / 'SourceAssets/GHS/RackSpecs/cad_plan_mapping.json',
                 ROOT / 'SourceAssets/GHS/MainRoof/roof_manifest.json',layout_path]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    envelope = json.loads(envelope_path.read_text(encoding='utf-8'))
    dock_polygons = [Polygon(p['cut_polygon_cad_m']) for p in envelope['openings']]
    dock_union = unary_union(dock_polygons)
    # Envelope uses CAD (x, y), while the facade helper uses campus (u, v).
    overlay_footprint = unary_union([
        box(-ORIGIN[0] - .18, ORIGIN[1] - 137.16, -ORIGIN[0] + .01, ORIGIN[1] - 118.872),
        box(-ORIGIN[0] - .18, ORIGIN[1] - 137.16 - .18, 45.8724 - ORIGIN[0], ORIGIN[1] - 137.16 + .01),
    ])
    assert dock_union.intersection(overlay_footprint).area < 1e-9, 'Facade covers a CAD loading door'
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.name = 'GHS_OfficeGlassFacade_Source'
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 8
    materials = {r: make_material('M_GHSOfficeFacade_' + r, *PALETTE[r]) for r in ROLES}
    editable = bpy.data.collections.new('Editable_OfficeFacade_Parts')
    scene.collection.children.link(editable)
    preview = bpy.data.collections.new('Preview_Only_Not_Exported')
    scene.collection.children.link(preview)
    objects, records, bays = [], [], []

    def cuboid(name, uv_bounds, z_bounds, role, collection=editable):
        u0, v0, u1, v1 = uv_bounds
        z0, z1 = z_bounds
        assert u1 > u0 and v1 > v0 and z1 > z0, name
        vertices = [point(u, v, z) for z in (z0, z1)
                    for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
        faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
                 (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(materials[role])
        mesh.update()
        assert not mesh.validate(verbose=True), name
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        assert all(e.is_manifold for e in bm.edges), name
        assert all(f.calc_area() > 1e-10 for f in bm.faces), name
        assert bm.calc_volume(signed=True) > 0, name
        bm.to_mesh(mesh)
        bm.free()
        mesh.calc_loop_triangles()
        ob = bpy.data.objects.new(name, mesh)
        collection.objects.link(ob)
        ob['material_role'] = role
        ob['facade_part'] = name
        if collection == editable:
            objects.append(ob)
            records.append(dict(name=name, role=role, bounds_uv_m=list(uv_bounds),
                                z_range_m=list(z_bounds), closed=True, triangles=len(mesh.loop_triangles)))
        return ob

    def piece(facade, name, s0, s1, depth, height, role):
        t0, t1 = depth
        if facade['id'] == 'West':
            uv = (-t1, s0, -t0, s1)
        else:
            uv = (s0, 137.16 + t0, s1, 137.16 + t1)
        return cuboid(facade['id'] + '_' + name, uv, height, role)

    for facade in FACADES:
        start, end = facade['s_min_m'], facade['s_max_m']
        count, pitch = facade['bay_count'], facade['bay_pitch_m']
        assert abs(end - start - count * pitch) < 1e-8
        # Shared vertical piers continue from plinth to the existing roof fascia.
        for i in range(count + 1):
            center = start + i * pitch
            lo, hi = max(start, center - PIER_WIDTH / 2), min(end, center + PIER_WIDTH / 2)
            piece(facade, 'Pier_%02d' % i, lo, hi, (.055, .18), (.04, 9.56), 'Pier')
        for bay in range(count):
            s0 = start + bay * pitch + PIER_WIDTH / 2
            s1 = start + (bay + 1) * pitch - PIER_WIDTH / 2
            z0, z1 = GLASS_Z
            name = 'Bay_%02d_' % (bay + 1)
            # A continuous closed sill and separate opaque header cap the glass.
            piece(facade, name + 'Sill', s0, s1, (.055, .18), (.04, z0), 'Sill')
            piece(facade, name + 'HeadPanel', s0, s1, (.065, .16), (z1, 8.22), 'Panel')
            piece(facade, name + 'FrameLeft', s0, s0 + FRAME_WIDTH, FRAME_DEPTH, (z0, z1), 'Frame')
            piece(facade, name + 'FrameRight', s1 - FRAME_WIDTH, s1, FRAME_DEPTH, (z0, z1), 'Frame')
            piece(facade, name + 'FrameBottom', s0 + FRAME_WIDTH, s1 - FRAME_WIDTH, FRAME_DEPTH,
                  (z0, z0 + FRAME_WIDTH), 'Frame')
            piece(facade, name + 'FrameTop', s0 + FRAME_WIDTH, s1 - FRAME_WIDTH, FRAME_DEPTH,
                  (z1 - FRAME_WIDTH, z1), 'Frame')
            inner0, inner1 = s0 + FRAME_WIDTH, s1 - FRAME_WIDTH
            lower, upper = z0 + FRAME_WIDTH, z1 - FRAME_WIDTH
            sx = [inner0 + (inner1 - inner0) * i / 4 for i in range(5)]
            sz = [lower + (upper - lower) * i / 3 for i in range(4)]
            for i in range(1, 4):
                piece(facade, name + 'VerticalMullion_%02d' % i,
                      sx[i] - MULLION_WIDTH / 2, sx[i] + MULLION_WIDTH / 2,
                      (.10, .17), (lower, upper), 'Frame')
            # Split horizontal mullions between verticals: no coincident surfaces.
            for row in range(1, 3):
                for col in range(4):
                    lo = sx[col] + (MULLION_WIDTH / 2 if col else 0)
                    hi = sx[col + 1] - (MULLION_WIDTH / 2 if col < 3 else 0)
                    piece(facade, name + 'HorizontalMullion_%d_%d' % (row, col), lo, hi,
                          (.10, .17), (sz[row] - MULLION_WIDTH / 2, sz[row] + MULLION_WIDTH / 2), 'Frame')
            for row in range(3):
                for col in range(4):
                    # Glass edges tuck 1cm underneath frames, front faces offset
                    # from the audited 5.3033cm outward legacy-wall protrusion.
                    lo = sx[col] - .01 + (MULLION_WIDTH / 2 if col else 0)
                    hi = sx[col + 1] + .01 - (MULLION_WIDTH / 2 if col < 3 else 0)
                    bottom = sz[row] - .01 + (MULLION_WIDTH / 2 if row else 0)
                    top = sz[row + 1] + .01 - (MULLION_WIDTH / 2 if row < 2 else 0)
                    piece(facade, name + 'Glass_%d_%d' % (row + 1, col + 1), lo, hi,
                          GLASS_DEPTH, (bottom, top), 'Glass')
            bays.append(dict(id=facade['id'] + '_%02d' % (bay + 1), facade=facade['id'],
                             horizontal_range_m=[s0, s1], glass_z_range_m=list(GLASS_Z),
                             columns=4, rows=3, pane_count=12))
    # A single exterior corner post joins both half-piers without seam gaps.
    cuboid('SharedCorner_ContinuousPier', (-.18, 137.16, 0., 137.34), (.04, 9.56), 'Pier')

    original_records = list(records)
    if previous:
        previous_originals = [r for r in previous['parts'] if r['name'].startswith(('West_', 'Front_', 'SharedCorner_'))]
        assert original_records == previous_originals, 'Existing office corner geometry changed'

    def oriented_piece(group, suffix, s0, s1, depth, height, role):
        """Closed prism along an arbitrary wall; works for the diagonal corner."""
        a, b = group['start_uv_m'], group['end_uv_m']
        length = math.dist(a, b)
        direction = ((b[0]-a[0])/length, (b[1]-a[1])/length)
        normal = group['outward_uv']
        assert abs(math.hypot(*normal)-1) < 1e-5, group['id']
        assert abs(direction[0]*normal[0]+direction[1]*normal[1]) < 1e-5, group['id']
        t0, t1 = depth; z0, z1 = height
        assert s1>s0 and t1>t0 and z1>z0, (group['id'],suffix)
        quad = [[a[0]+direction[0]*s+normal[0]*t,a[1]+direction[1]*s+normal[1]*t]
                for s,t in [(s0,t0),(s1,t0),(s1,t1),(s0,t1)]]
        vertices = [point(u,v,z) for z in (z0,z1) for u,v in quad]
        faces = [(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        name = group['id']+'_'+suffix
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces);mesh.materials.append(materials[role]);mesh.update()
        assert not mesh.validate(verbose=True), name
        bm = bmesh.new();bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        assert all(e.is_manifold for e in bm.edges) and all(f.calc_area()>1e-10 for f in bm.faces),name
        assert bm.calc_volume(signed=True)>0,name
        bm.to_mesh(mesh);bm.free();mesh.calc_loop_triangles()
        ob=bpy.data.objects.new(name,mesh);editable.objects.link(ob)
        ob['material_role']=role;ob['facade_part']=name;objects.append(ob)
        records.append(dict(name=name,role=role,
            bounds_uv_m=[min(p[0] for p in quad),min(p[1] for p in quad),max(p[0] for p in quad),max(p[1] for p in quad)],
            footprint_uv_m=quad,z_range_m=[z0,z1],closed=True,triangles=len(mesh.loop_triangles)))
        return ob

    for group in groups:
        group_id=group['id'];length=math.dist(group['start_uv_m'],group['end_uv_m'])
        count=group['bay_count'];pitch=length/count
        dock_numbers=group.get('dock_numbers_by_bay')
        assert dock_numbers is None or (len(dock_numbers)==count and all(isinstance(v,list) and v for v in dock_numbers)),group_id
        edges=group.get('bay_edges_m',[pitch*i for i in range(count+1)])
        assert len(edges)==count+1 and abs(edges[0])<1e-6 and abs(edges[-1]-length)<1e-5,group_id
        assert all(edges[i]<edges[i+1] for i in range(count)),group_id
        pier=group.get('pier_width_m',PIER_WIDTH)
        assert pier>0 and all(edges[i+1]-edges[i]>pier+2*FRAME_WIDTH for i in range(count)),group_id
        columns=group.get('columns',4)
        windows=group['window_z_ranges'];rows=group.get('rows',1)
        row_counts=rows if isinstance(rows,list) else [rows]*len(windows)
        assert len(row_counts)==len(windows) and count>0 and columns>0
        assert all(0<=z0<z1<9.6 for z0,z1 in windows),group_id
        assert all(windows[i][1]<windows[i+1][0] for i in range(len(windows)-1)),group_id
        portal=group.get('kind')=='dock_portal'
        pier_z=group.get('pier_z_range',[.04 if portal else min(z[0] for z in windows)-.18,9.56])
        for i in range(count+1):
            center=edges[i]
            lo,hi=(center-pier/2,center+pier/2) if portal else (max(0,center-pier/2),min(length,center+pier/2))
            oriented_piece(group,'Pier_%02d'%i,lo,hi,(.055,.18),pier_z,'Pier')
        for bay in range(count):
            s0=edges[bay]+pier/2;s1=edges[bay+1]-pier/2
            prefix='Bay_%02d_'%(bay+1)
            head=group.get('head_panel_z_range')
            if head and head[1]>head[0]:
                oriented_piece(group,prefix+'HeadPanel',s0,s1,(.065,.16),head,'Panel')
            if portal:
                # Full dock portal: piers stand in CAD door gaps, while the
                # opaque spandrel starts above the real 4.2 m loading opening.
                lower=group.get('lower_panel_z_range',[4.25,windows[0][0]])
                assert 4.2<lower[0]<lower[1]<=windows[0][0],group_id
                oriented_piece(group,prefix+'DockSpandrel',s0,s1,(.065,.16),lower,'Panel')
            if group.get('spandrel',False):
                for level in range(len(windows)-1):
                    oriented_piece(group,prefix+'Spandrel_%02d'%level,s0,s1,(.065,.16),
                                   (windows[level][1],windows[level+1][0]),'Panel')
            for level,((z0,z1),row_count) in enumerate(zip(windows,row_counts)):
                tag=prefix+'Level_%02d_'%(level+1)
                # Dock number AABBs extend above the door opening. The sill
                # must honor the group's protected lower limit, just as piers.
                sill_bottom=max(.04,z0-.18,pier_z[0])
                if sill_bottom<z0:
                    oriented_piece(group,tag+'Sill',s0,s1,(.055,.18),(sill_bottom,z0),'Sill')
                oriented_piece(group,tag+'FrameLeft',s0,s0+FRAME_WIDTH,FRAME_DEPTH,(z0,z1),'Frame')
                oriented_piece(group,tag+'FrameRight',s1-FRAME_WIDTH,s1,FRAME_DEPTH,(z0,z1),'Frame')
                oriented_piece(group,tag+'FrameBottom',s0+FRAME_WIDTH,s1-FRAME_WIDTH,FRAME_DEPTH,(z0,z0+FRAME_WIDTH),'Frame')
                oriented_piece(group,tag+'FrameTop',s0+FRAME_WIDTH,s1-FRAME_WIDTH,FRAME_DEPTH,(z1-FRAME_WIDTH,z1),'Frame')
                inner0,inner1=s0+FRAME_WIDTH,s1-FRAME_WIDTH;lower,upper=z0+FRAME_WIDTH,z1-FRAME_WIDTH
                sx=[inner0+(inner1-inner0)*i/columns for i in range(columns+1)]
                sz=[lower+(upper-lower)*i/row_count for i in range(row_count+1)]
                for i in range(1,columns):
                    oriented_piece(group,tag+'VerticalMullion_%02d'%i,sx[i]-MULLION_WIDTH/2,sx[i]+MULLION_WIDTH/2,
                                   (.10,.17),(lower,upper),'Frame')
                for row in range(1,row_count):
                    for col in range(columns):
                        lo=sx[col]+(MULLION_WIDTH/2 if col else 0)
                        hi=sx[col+1]-(MULLION_WIDTH/2 if col<columns-1 else 0)
                        oriented_piece(group,tag+'HorizontalMullion_%d_%d'%(row,col),lo,hi,
                                       (.10,.17),(sz[row]-MULLION_WIDTH/2,sz[row]+MULLION_WIDTH/2),'Frame')
                for row in range(row_count):
                    for col in range(columns):
                        lo=sx[col]-.01+(MULLION_WIDTH/2 if col else 0)
                        hi=sx[col+1]+.01-(MULLION_WIDTH/2 if col<columns-1 else 0)
                        bottom=sz[row]-.01+(MULLION_WIDTH/2 if row else 0)
                        top=sz[row+1]+.01-(MULLION_WIDTH/2 if row<row_count-1 else 0)
                        oriented_piece(group,tag+'Glass_%d_%d'%(row+1,col+1),lo,hi,GLASS_DEPTH,(bottom,top),'Glass')
            bay_record=dict(id=group_id+'_%02d'%(bay+1),facade=group_id,kind=group.get('kind','high'),
                horizontal_range_m=[s0,s1],window_z_ranges=windows,columns=columns,rows=row_counts,
                pane_count=sum(row_counts)*columns,structural_bay_edges_m=[edges[bay],edges[bay+1]])
            if dock_numbers is not None:bay_record['dock_numbers']=dock_numbers[bay]
            bays.append(bay_record)

    for corner in layout.get('corner_piers', []):
        cuboid('CornerJoin_'+corner['id'],corner['uv_bounds'],corner['z_range'],'Pier')

    # Check real 3D clearance: clerestories intentionally share loading-door
    # horizontal ranges but stay above the 4.2 m openings and number band.
    door_overlap_volume=0.;high_window_plan_overlap=0.;low_footprints=[]
    for record in records:
        z0,z1=record['z_range_m']
        quad=record.get('footprint_uv_m')
        if quad is None:
            u0,v0,u1,v1=record['bounds_uv_m'];quad=[[u0,v0],[u1,v0],[u1,v1],[u0,v1]]
        footprint=Polygon([(u-ORIGIN[0],ORIGIN[1]-v) for u,v in quad])
        overlap=footprint.intersection(dock_union).area
        vertical=max(0.,min(z1,4.2)-max(z0,0.))
        door_overlap_volume+=overlap*vertical
        if z0>=4.2:high_window_plan_overlap+=overlap
        if z0<4.2:low_footprints.append(footprint)
        assert z1<=9.6,record['name']
    assert door_overlap_volume<1e-8,('Facade geometry intersects a CAD door',door_overlap_volume)
    low_union=unary_union(low_footprints)

    vertices, faces, slots = [], [], []
    for ob in objects:
        offset = len(vertices)
        vertices.extend([tuple(v.co) for v in ob.data.vertices])
        faces.extend([[offset + i for i in p.vertices] for p in ob.data.polygons])
        slots.extend([ROLES.index(ob['material_role'])] * len(ob.data.polygons))
    mesh = bpy.data.meshes.new(NAME)
    mesh.from_pydata(vertices, [], faces)
    for role in ROLES:
        mesh.materials.append(materials[role])
    for p, index in zip(mesh.polygons, slots):
        p.material_index = index
    mesh.update()
    mesh.calc_loop_triangles()
    assert not mesh.validate(verbose=True)
    assert len(mesh.loop_triangles) < TRIANGLE_BUDGET
    export = bpy.data.objects.new(NAME, mesh)
    scene.collection.objects.link(export)
    bpy.ops.object.select_all(action='DESELECT')
    export.select_set(True)
    bpy.context.view_layer.objects.active = export
    fbx = OUT / (NAME + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'MESH'},
        axis_forward='-Y', axis_up='Z', apply_unit_scale=True, bake_anim=False,
        mesh_smooth_type='FACE', use_mesh_modifiers=True, add_leaf_bones=False)
    mesh_row = dict(name=NAME, fbx=str(fbx.relative_to(ROOT)), vertices=len(mesh.vertices),
                    triangles=len(mesh.loop_triangles), bounds_ue_cm=bounds_ue(mesh),
                    material_roles=list(ROLES), slot_names=[materials[r].name for r in ROLES], sha256=sha(fbx))
    export.hide_render = True
    export.hide_set(True)
    export.select_set(False)

    # Preview shell/ground are isolated in an explicit non-exported collection.
    cuboid('PREVIEW_ExistingOfficeMass_NotExported', (0, 110, 45.8724, 137.16), (0, 9.6), 'Panel', preview)
    cuboid('PREVIEW_Roof_NotExported', (-.25, 109.75, 46.1224, 137.41), (9.6, 9.79), 'Panel', preview)
    cuboid('PREVIEW_Ground_NotExported', (-35, 75, 80, 180), (-.16, -.03), 'Sill', preview)
    roof_blue = make_material('PREVIEW_RoofBlue_NotExported', (.035, .13, .48), .8, .05)
    for name, uv in [('PREVIEW_BlueWest_NotExported', (-.25, 109.75, -.12, 137.41)),
                     ('PREVIEW_BlueFront_NotExported', (-.25, 137.28, 46.1224, 137.41))]:
        ob = cuboid(name, uv, (9.79, 9.85), 'Frame', preview)
        ob.data.materials.clear()
        ob.data.materials.append(roof_blue)
    scene.world.use_nodes = True
    world_nodes = scene.world.node_tree.nodes
    background = next((n for n in world_nodes if n.type == 'BACKGROUND'), None)
    if background is None:
        background = world_nodes.new('ShaderNodeBackground')
        output = world_nodes.new('ShaderNodeOutputWorld')
        scene.world.node_tree.links.new(background.outputs['Background'], output.inputs['Surface'])
    background.inputs['Color'].default_value = (.65, .72, .82, 1)
    background.inputs['Strength'].default_value = .65
    target = Vector(point(16, 130, 4.6))
    camera_data = bpy.data.cameras.new('OfficeFacade_PreviewCamera')
    camera = bpy.data.objects.new('OfficeFacade_PreviewCamera', camera_data)
    scene.collection.objects.link(camera)
    camera.location = Vector(point(-30, 181, 32))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = 62
    scene.camera = camera
    for name, uvz, energy, size in [('Key', (-18, 150, 50), 85000, 35), ('Fill', (50, 175, 30), 40000, 28)]:
        light = bpy.data.lights.new(name, 'AREA')
        ob = bpy.data.objects.new(name, light)
        scene.collection.objects.link(ob)
        ob.location = point(*uvz)
        ob.rotation_euler = (target - ob.location).to_track_quat('-Z', 'Y').to_euler()
        light.energy = energy
        light.shape = 'DISK'
        light.size = size
    scene.render.resolution_x = 1536
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    scene.render.filepath = str(OUT / 'office_facade_preview.png')
    # Keep the familiar office-corner preview useful; the full elevations are
    # checked in Unreal, against the actual building shell and dock numbering.
    for ob in objects[len(original_records):]:
        ob.hide_render = True
    bpy.ops.render.render(write_still=True)
    for ob in objects[len(original_records):]:
        ob.hide_render = False
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'OfficeGlassFacade.blend'))
    assert all(sha(ROOT / p) == h for p, h in hashes.items()), 'Shared source changed'
    assert sha(layout_path) == layout_hash, 'Layout changed while generating the asset'
    manifest = dict(version=2, name='GHS warehouse exterior glazing elevations', mesh=mesh_row,
        coordinate_contract='u,v metres; Blender (u-239.33385,-(v-60.24019),z); FBX -Y forward Z up; UE origin scale1 cm',
        materials={r: dict(color_linear=list(PALETTE[r][0]), roughness=PALETTE[r][1], metallic=PALETTE[r][2], opaque=True) for r in ROLES},
        facades=list(FACADES),additional_groups=groups,corner_piers=layout.get('corner_piers',[]),layout_sha256=layout_hash,
        dock_label_placement=layout.get('dock_label_placement',[]),
        bays=bays,bay_count=len(bays),pane_count=sum(b['pane_count'] for b in bays),
        glass_outward_offset_m=list(GLASS_DEPTH), frame_outward_offset_m=list(FRAME_DEPTH),
        pier_width_m=PIER_WIDTH, head_panel_z_m=[6.54, 8.22], existing_wall_top_m=9.6,
        structural_note='Visual reference reconstruction; bay spacing follows the CAD-fitted office wing; glazing is an opaque exterior overlay and does not cut or replace shared walls.',
        parts=records, editable_part_count=len(records),
        checks=dict(all_parts_closed=True, all_faces_valid=True, positive_volume_parts=True,
            cad_loading_door_count=len(dock_polygons), loading_door_overlap_area_m2=dock_union.intersection(low_union).area,
            minimum_door_clearance_m=dock_union.distance(low_union),
            door_overlap_volume_m3=door_overlap_volume,high_window_plan_overlap_area_m2=high_window_plan_overlap,
            original_corner_part_count=len(original_records),original_corner_geometry_preserved=True,
            audited_existing_wall_outward_protrusion_m=.053033, glass_back_clearance_m=.08-.053033,
            all_geometry_below_roof=True, existing_shared_sources_unchanged=True,
            source_hashes=hashes, triangle_budget=TRIANGLE_BUDGET),
        outputs=dict(blend='SourceAssets/GHS/OfficeFacade/OfficeGlassFacade.blend', fbx=mesh_row['fbx'],
                     preview='SourceAssets/GHS/OfficeFacade/office_facade_preview.png'))
    write('facade_manifest.json', manifest)
    print('GHS_OFFICE_FACADE_READY ' + json.dumps(dict(vertices=mesh_row['vertices'], triangles=mesh_row['triangles'],
          bays=len(bays),panes=manifest['pane_count'],parts=len(records),bounds_ue_cm=mesh_row['bounds_ue_cm'])))


if __name__ == '__main__':
    main()
