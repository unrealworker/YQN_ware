"""Derive a static closed-door park truck from the existing dock truck.

Run only in isolated background Blender.  The source library and existing UE
assets are read-only; the derived source, FBX, report and previews are written
under SourceAssets/GHS/Park/Trucks. Metres, rear origin, local +X forward.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'SourceAssets/GHS/Park/Trucks'
SOURCE = ROOT/'SourceAssets/GHS_Normal/TrucksLong'
SOURCE_BLEND = SOURCE/'dock_truck_long.blend'
SOURCE_FBX = SOURCE/'SM_GHN_LongDockTruck.fbx'
SOURCE_ASSET = ROOT/'Content/GHSNormalWarehouse/TrucksLong/SM_GHN_LongDockTruck.uasset'
NAME = 'SM_GHSPark_ClosedTruck'
PALETTE = {
    'TruckBody': ((.87,.90,.93),.64,.03),
    'TruckBlue': ((.018,.075,.51),.57,.04),
    'TruckTrim': ((.63,.68,.73),.55,.18),
    'TruckGlass': ((.055,.14,.22),.25,.12),
    'TruckRubber': ((.018,.024,.028),.84,.0),
    'TruckHeadlight': ((.66,.87,.96),.38,.03),
    'TruckTailLight': ((.46,.035,.025),.42,.03),
}
ROLE_MAP = {'Body':'TruckBody','Trim':'TruckTrim','Accent':'TruckBlue',
            'Glass':'TruckGlass','Rubber':'TruckRubber',
            'Headlight':'TruckHeadlight','TailLight':'TruckTailLight'}
REMOVE_PREFIXES = ('Folded rear cargo door','Rear door hinge','Cargo hinge')
SHAPE_CHANGE_PREFIXES = ('Side blue belt',)
BLUE_CAB_PREFIXES = ('Sculpted cab','Cab roof lip')
sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluated_vertices(obj, deps):
    evaluated = obj.evaluated_get(deps)
    mesh = evaluated.to_mesh()
    points = [tuple(obj.matrix_world @ vertex.co) for vertex in mesh.vertices]
    evaluated.to_mesh_clear()
    return points


def bounds(points):
    return {'min':[min(p[i] for p in points) for i in range(3)],
            'max':[max(p[i] for p in points) for i in range(3)]}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source_paths = (SOURCE_BLEND,SOURCE_FBX,SOURCE_ASSET)
    before_hashes = {str(path):sha(path) for path in source_paths}
    spec = json.loads((SOURCE/'dock_truck_long.json').read_text(encoding='utf8'))['meshes'][0]
    assert before_hashes[str(SOURCE_FBX)] == spec['fbx_sha256']
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.name = 'GHS_Park_ClosedTruck'
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    collection = bpy.data.collections.new(NAME)
    scene.collection.children.link(collection)
    with bpy.data.libraries.load(str(SOURCE_BLEND),link=False) as (source,loaded):
        loaded.objects = list(source.objects)
    originals = {obj.name:obj for obj in loaded.objects if obj is not None}
    assert len(originals) == spec['source_parts'], (len(originals),spec['source_parts'])
    assert all(obj.type=='MESH' for obj in originals.values())
    for obj in originals.values():
        collection.objects.link(obj)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    source_vertices = {name:evaluated_vertices(obj,deps) for name,obj in originals.items()}
    source_roles = {name:obj.data.materials[0].name.rsplit('_',1)[-1]
                    for name,obj in originals.items()}
    source_bounds = bounds([p for points in source_vertices.values() for p in points])

    materials = {}
    for role,(color,roughness,metallic) in PALETTE.items():
        mat = bpy.data.materials.new('M_GHSPark_'+role)
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if bsdf is None:
            bsdf = mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            output = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
            mat.node_tree.links.new(bsdf.outputs['BSDF'],output.inputs['Surface'])
        bsdf.inputs['Base Color'].default_value = (*color,1)
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = metallic
        mat.diffuse_color = (*color,1)
        materials[role] = mat

    removed = []
    changed = []
    reused = {}
    for name,obj in originals.items():
        if name.startswith(REMOVE_PREFIXES):
            removed.append({'name':name,'source_bounds_m':bounds(source_vertices[name])})
            bpy.data.objects.remove(obj,do_unlink=True)
            continue
        role = ROLE_MAP[source_roles[name]]
        if name.startswith(BLUE_CAB_PREFIXES):
            role = 'TruckBlue'
        obj.data.materials.clear()
        obj.data.materials.append(materials[role])
        for polygon in obj.data.polygons:
            polygon.material_index = 0
        obj['ghs_park_derived_from'] = str(SOURCE_BLEND)
        obj['ghs_source_part_name'] = name
        obj['ghs_park_material_role'] = role
        if name.startswith(SHAPE_CHANGE_PREFIXES):
            obj.dimensions.z = .62
            obj.location.z = 1.55
            changed.append({'name':name,'change':'Side blue belt height 0.22 to 0.62 m; centre z 1.55 m',
                            'source_bounds_m':bounds(source_vertices[name])})
        else:
            reused[name] = obj

    new_parts = []

    def finish(obj,name,role,edge=0):
        obj.name = name
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)
        obj.data.materials.append(materials[role])
        obj['ghs_park_material_role'] = role
        obj['ghs_closed_rear_component'] = True
        if edge:
            bevel = obj.modifiers.new('Small edge radii','BEVEL')
            bevel.width = edge
            bevel.segments = 2
            normals = obj.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
            normals.keep_sharp = True
        new_parts.append(obj)
        return obj

    def box(name,center,size,role,edge=.004):
        bpy.ops.mesh.primitive_cube_add(size=1,location=center)
        obj = bpy.context.object
        obj.dimensions = size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        return finish(obj,name,role,min(edge,min(size)*.20))

    def cylinder(name,center,radius,height,role,sides=12):
        bpy.ops.mesh.primitive_cylinder_add(vertices=sides,radius=radius,depth=height,location=center)
        obj = bpy.context.object
        for face in obj.data.polygons:
            face.use_smooth = len(face.vertices)==4
        return finish(obj,name,role)

    # Door leaves are transverse across the rear aperture, not the original
    # folded panels lying longitudinally against the side of the cargo box.
    for sign in (-1,1):
        side = 'Left' if sign < 0 else 'Right'
        box('Closed cargo door '+side,(.005,sign*.583,2.375),(.055,1.154,2.47),'TruckBody',.007)
        box('Closed door blue lower band '+side,(-.0275,sign*.583,1.52),(.010,1.125,.46),'TruckBlue',.002)
        for z in (1.5,2.30,3.2):
            cylinder('Closed door hinge barrel '+side,(-.045,sign*1.174,z),.026,.14,'TruckTrim')
            box('Closed door hinge strap '+side,(-.046,sign*1.10,z),(.025,.17,.052),'TruckTrim',.003)
        cylinder('Closed door locking rod '+side,(-.067,sign*.39,2.375),.018,2.26,'TruckTrim')
        for z in (1.32,2.18,3.43):
            box('Closed door rod collar '+side,(-.067,sign*.39,z),(.055,.065,.065),'TruckTrim',.004)
        box('Closed door lock handle '+side,(-.096,sign*.47,1.92),(.026,.22,.034),'TruckTrim',.004)
        box('Closed door lower reflector '+side,(-.037,sign*.80,1.285),(.012,.18,.042),'TruckTailLight',.002)
    # Black overlap gasket closes the fine centre seam behind the white leaves.
    box('Closed door centre overlap gasket',(.012,0,2.375),(.030,.015,2.47),'TruckRubber',.001)
    box('Closed door top identity plate',(-.031,0,3.40),(.012,.42,.095),'TruckBlue',.002)

    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    reuse_checks = []
    for name,obj in reused.items():
        current = evaluated_vertices(obj,deps)
        original = source_vertices[name]
        assert len(current)==len(original),(name,len(current),len(original))
        error = max((Vector(a)-Vector(b)).length for a,b in zip(current,original))
        assert error < 1e-6,(name,error)
        reuse_checks.append({'name':name,'vertices':len(current),'maximum_vertex_error_m':error})
    for item in changed:
        item['derived_bounds_m'] = bounds(evaluated_vertices(originals[item['name']],deps))
    assert len(removed)==16,(len(removed),[item['name'] for item in removed])
    assert len(changed)==2
    assert not any(obj.name.startswith(REMOVE_PREFIXES) for obj in collection.objects)
    assert all(any(row['name'].startswith(prefix) for row in reuse_checks)
               for prefix in ('Sculpted cab','Road tire','Wheel hub','Cargo side skin','Cargo roof'))

    # Sample the rear aperture against only the newly built door assembly.
    # This prevents the front cargo bulkhead from hiding an accidentally open
    # rear and tests the centre seam as well as both separate door leaves.
    door_vertices,door_faces = [],[]
    for obj in new_parts:
        evaluated = obj.evaluated_get(deps)
        data = evaluated.to_mesh()
        offset = len(door_vertices)
        door_vertices.extend(tuple(obj.matrix_world @ vertex.co) for vertex in data.vertices)
        door_faces.extend(tuple(offset+i for i in polygon.vertices) for polygon in data.polygons)
        evaluated.to_mesh_clear()
    tree = BVHTree.FromPolygons(door_vertices,door_faces,all_triangles=False)
    hits = []
    for yi in range(47):
        y = -1.14+2.28*yi/46
        for zi in range(50):
            z = 1.16+2.43*zi/49
            point,normal,index,distance = tree.ray_cast(Vector((-1,y,z)),Vector((1,0,0)),1.10)
            assert point is not None,(y,z,'Open rear aperture')
            assert -.15 < point.x < .05,(y,z,tuple(point),'Rear door hit outside door plane')
            hits.append(tuple(point))

    # Save the complete editable collection before any joined export object,
    # ground plane, lighting or presentation camera is added.
    source_file = OUT/'closed_truck.blend'
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.wm.save_as_mainfile(filepath=str(source_file))

    copies = []
    for obj in collection.objects:
        evaluated = obj.evaluated_get(deps)
        data = bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=deps)
        copy = bpy.data.objects.new(obj.name+'_Export',data)
        scene.collection.objects.link(copy)
        copy.matrix_world = obj.matrix_world.copy()
        copies.append(copy)
    for obj in copies:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.object.join()
    export = bpy.context.object
    export.name = NAME
    scene.cursor.location = (0,0,0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    assert not export.data.validate(verbose=True), 'Export mesh needed geometry repair'
    export.data.update()
    export.data.calc_loop_triangles()
    triangle_count = len(export.data.loop_triangles)
    assert triangle_count > 20000
    degenerate_faces = sum(polygon.area < 1e-14 for polygon in export.data.polygons)
    assert degenerate_faces == 0,degenerate_faces
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1)
    bpy.ops.object.mode_set(mode='OBJECT')
    slots = [material.name for material in export.data.materials]
    roles = [slot.removeprefix('M_GHSPark_') for slot in slots]
    assert set(roles)==set(PALETTE),(roles,list(PALETTE))
    blender_bounds = bounds([tuple(vertex.co) for vertex in export.data.vertices])
    assert all(abs(blender_bounds[k][i]-source_bounds[k][i])<1e-5
               for k in ('min','max') for i in range(3)),(blender_bounds,source_bounds)
    lo,hi = blender_bounds['min'],blender_bounds['max']
    ue_bounds = {'min':[lo[0]*100,-hi[1]*100,lo[2]*100],
                 'max':[hi[0]*100,-lo[1]*100,hi[2]*100]}
    fbx = OUT/(NAME+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
        mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
    after_hashes = {str(path):sha(path) for path in source_paths}
    assert after_hashes==before_hashes
    report = {
        'success':True,'version':1,'generator':str(Path(__file__).resolve()),
        'name':NAME,'fbx':str(fbx),'blend':str(source_file),
        'fbx_sha256':sha(fbx),'source_sha256':before_hashes,'source_assets_preserved':True,
        'origin_m':[0,0,0],'forward_axis':'+X',
        'coordinate_contract':'Blender metres; rear origin; FBX -Y forward Z up; UE import at origin scale 1 mirrors Y and converts to centimetres.',
        'material_roles':roles,'slot_names':slots,
        'materials':{role:list(color) for role,(color,roughness,metallic) in PALETTE.items()},
        'material_specs':{role:{'name':'M_GHSPark_'+role,'color_linear':list(color),
                           'roughness':roughness,'metallic':metallic}
                     for role,(color,roughness,metallic) in PALETTE.items()},
        'triangles':triangle_count,'vertices':len(export.data.vertices),'polygons':len(export.data.polygons),
        'bounds_blender_m':blender_bounds,'bounds_ue_cm':ue_bounds,
        'dimensions_m':[hi[i]-lo[i] for i in range(3)],
        'geometry_center_offset_m':[(hi[i]+lo[i])*.5 for i in range(3)],
        'source_parts':len(originals),'derived_editable_parts':len(collection.objects),
        'removed_source_parts':removed,'modified_source_parts':changed,
        'added_parts':[obj.name for obj in new_parts],
        'reuse_validation':{'preserved_parts':len(reuse_checks),
                            'maximum_vertex_error_m':max(row['maximum_vertex_error_m'] for row in reuse_checks),
                            'source_bounds_m':source_bounds,'checks':reuse_checks},
        'door_validation':{'rear_aperture_closed':True,'sample_count':len(hits),
            'sample_region_yz_m':{'y':[-1.14,1.14],'z':[1.16,3.59]},
            'raycast_only_new_door_assembly':True,
            'center_seam_backed_by_overlap_gasket':True,'folded_doors_and_hinges_removed':True},
        'geometry_validation':{'mesh_validate_needed_repairs':False,'degenerate_faces':degenerate_faces},
        'interaction_policy':'Static background only: no business actor clone, no identity/POI/data components. Root importer applies instance collision/tick/identity restrictions.',
    }
    report['mesh'] = {'name':NAME,'fbx':str(fbx),'material_roles':roles,'slot_names':slots,
        'vertices':len(export.data.vertices),'polygons':len(export.data.polygons),
        'triangles':triangle_count,'bounds_ue_cm':ue_bounds,
        'blender_bounds_m':blender_bounds,'sha256':report['fbx_sha256']}
    report['source_assets'] = [{'path':path,'sha256':digest} for path,digest in before_hashes.items()]
    report['validation'] = {'success':True,'source_assets_preserved':True,
        'preserved_source_parts':len(reuse_checks),
        'maximum_reused_vertex_error_m':report['reuse_validation']['maximum_vertex_error_m'],
        'removed_folded_door_parts':len(removed),'modified_belt_parts':len(changed),
        'added_closed_door_parts':len(new_parts),
        'door_aperture_rays_passed':len(hits),'rear_aperture_closed':True,
        'mesh_validate_needed_repairs':False,'degenerate_faces':degenerate_faces,
        'full_source_bounds_preserved':True}
    (OUT/'closed_truck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    bpy.data.objects.remove(export,do_unlink=True)

    # Actual rendered review images; these presentation objects are never saved
    # into the editable source or included in the exported FBX.
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.world.color = (.25,.25,.25)
    scene.view_settings.view_transform = 'AgX'
    ground = bpy.data.materials.new('Preview ground')
    ground.diffuse_color = (.45,.49,.53,1)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(7,0,-.015))
    bpy.context.object.data.materials.append(ground)
    bpy.ops.object.light_add(type='AREA',location=(7,-7,14))
    bpy.context.object.data.energy = 3000
    bpy.context.object.data.shape = 'DISK'
    bpy.context.object.data.size = 9
    bpy.ops.object.light_add(type='SUN')
    bpy.context.object.rotation_euler = (math.radians(25),math.radians(-20),math.radians(-25))
    bpy.context.object.data.energy = 2.0
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'ORTHO'
    scene.camera = camera
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    for name,eye,target,scale in [
        ('closed_truck_front.png',(22,-17,11),(7,0,1.7),18.5),
        ('closed_truck_rear.png',(-10,-17,10),(6.3,0,1.7),18.5),
        ('closed_truck_doors.png',(-7,-3.5,4.6),(.2,0,2.0),5.6),
    ]:
        camera.location = eye
        camera.data.ortho_scale = scale
        camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath = str(OUT/name)
        bpy.ops.render.render(write_still=True)
    assert {str(path):sha(path) for path in source_paths}==before_hashes
    print('GHS_PARK_CLOSED_TRUCK_READY',triangle_count,blender_bounds)


if __name__=='__main__':
    main()
