"""Build editable, correctly scaled GHS rack assets from audited CAD elevations.

Run only in a background Blender process. This never opens or changes the live
Blender session. Metres, Z up, X across the bay, Y through its depth. FBX uses
the established GHS -Y forward conversion and a centred, floor-level origin.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import math
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GHS/RackSpecs/Models'
SLOT_NAMES = ['Upright', 'Beam', 'Braces', 'Pallet', 'Cargo', 'CargoEdges', 'Detail']
PALETTE = {
    'Upright': ((.065, .145, .255), .40, .62),
    'Beam': ((.16, .25, .39), .44, .53),
    'Braces': ((.27, .35, .45), .36, .64),
    'Pallet': ((.055, .19, .37), .58, .15),
    'Cargo': ((.22, .30, .39), .78, .03),
    'CargoEdges': ((.085, .14, .20), .76, .02),
    'Detail': ((.018, .028, .043), .64, .12),
}
MATERIALS = {}
COLLECTION = None


def prepare():
    global MATERIALS
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (color, roughness, metallic) in PALETTE.items():
        material = bpy.data.materials.new('M_GHS_CADRack_' + name)
        material.use_nodes = True
        material.diffuse_color = (*color, 1)
        principled = material.node_tree.nodes.get('Principled BSDF')
        principled.inputs['Base Color'].default_value = (*color, 1)
        principled.inputs['Roughness'].default_value = roughness
        principled.inputs['Metallic'].default_value = metallic
        MATERIALS[name] = material


def mesh(name, vertices, faces, slot):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    COLLECTION.objects.link(obj)
    obj.data.materials.append(MATERIALS[slot])
    obj['physical_material_slot'] = slot
    return obj


def box(name, center, size, slot, bevel=0):
    x, y, z = center
    dx, dy, dz = [value * .5 for value in size]
    points = [(x + sx * dx, y + sy * dy, z + sz * dz)
              for sx, sy, sz in [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                                (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]]
    obj = mesh(name, points, [(0,2,6,4),(1,5,7,3),(0,4,5,1),
                             (2,3,7,6),(0,1,3,2),(4,6,7,5)], slot)
    assert all(face.normal.dot(face.center-Vector(center))>0 for face in obj.data.polygons), (name,'face winding')
    if bevel:
        modifier = obj.modifiers.new('Small manufacturing edge radius', 'BEVEL')
        modifier.width = min(bevel, min(size) * .20)
        modifier.segments = 1
        modifier.affect = 'EDGES'
        normals = obj.modifiers.new('Weighted face normals', 'WEIGHTED_NORMAL')
        normals.keep_sharp = True
    return obj


def bar(name, a, b, width, depth, slot):
    a, b = Vector(a), Vector(b)
    obj = box(name, (0,0,0), (width, depth, (b-a).length), slot)
    obj.location = (a+b)*.5
    obj.rotation_euler = (b-a).to_track_quat('Z', 'Y').to_euler()
    return obj


def build_frame(spec):
    clear = spec['clear_width_m']
    width = spec['frame_width_m']
    depth = spec['frame_depth_m']
    height = spec['upright_height_m']
    post = (width-clear)*.5
    assert .04 <= post <= .15, ('Unexpected CAD post width', spec)
    post_depth = min(post, .0762)
    skin = .008
    for sx in [-1, 1]:
        x = sx * (clear*.5 + post*.5)
        for sy in [-1, 1]:
            y = sy * (depth*.5 - post_depth*.5)
            box('Upright channel web', (x + sx*(post-skin)*.5,y,height*.5),
                (skin,post_depth,height), 'Upright')
            for dy in [-1,1]:
                box('Upright channel flange', (x-sx*skin*.5,y+dy*(post_depth-skin)*.5,height*.5),
                    (post-skin,skin,height), 'Upright')
            box('Anchored upright foot plate', (x,y,.006),
                (post,post_depth,.012), 'Braces')
            # Flat recessed markings add recognisable rack perforations with
            # two triangles each. They do not cut hundreds of holes into LOD0.
            for hole in range(1, int(height/.1524)):
                z = hole*.1524
                yf = y + sy*(post_depth*.5+.0003)
                mesh('Upright adjustment slot',
                     [(x-.006,yf,z-.015),(x+.006,yf,z-.015),
                      (x+.006,yf,z+.015),(x-.006,yf,z+.015)],
                     [(0,1,2,3) if sy<0 else (3,2,1,0)], 'Detail')
        ya, yb = -depth*.5+post_depth, depth*.5-post_depth
        start, end = .13, height-.10
        segments = max(1, round((end-start)/1.3))
        for i in range(segments):
            za = start + (end-start)*i/segments
            zb = start + (end-start)*(i+1)/segments
            bar('Upright side diagonal', (x,ya,za), (x,yb,zb), .022,.012,'Braces')
            if i % 2 == 0:
                bar('Upright side return diagonal', (x,yb,za), (x,ya,zb), .016,.010,'Braces')
        for z in [.12,height-.09]:
            box('Upright transverse tie', (x,0,z), (.032,depth-post_depth*2,.032),'Braces')
    for index, z in enumerate(spec['beam_top_z_m']):
        thickness = spec['beam_heights_m'][index]
        for sy in [-1,1]:
            y = sy*(depth*.5-post_depth*.5)
            box('Load beam %02d' % (index+1), (0,y,z-thickness*.5),
                (clear,.065,thickness), 'Beam', .002)
            for sx in [-1,1]:
                box('Beam end connector', (sx*(clear*.5-.018),y,z-thickness*.5),
                    (.036,.078,thickness), 'Braces')
        for x in spec['cargo_center_x_m']:
            box('Pallet cross support', (x,0,z-.023),
                (.05,depth-post_depth,.046), 'Braces')


def build_load(name, x, base, width, depth, height, pallet_height, deck_thickness, runner_width):
    assert height > pallet_height+.05
    runner_h = deck_thickness
    deck_h = deck_thickness
    spacer_h = pallet_height-runner_h-deck_h
    # Continuous runners and separate deck planks preserve fork openings.
    for sx in [-1,0,1]:
        xx = x + sx * (width*.5-runner_width*.5)
        box(name+' pallet runner', (xx,0,base+runner_h*.5), (runner_width,depth,runner_h),'Pallet')
        for sy in [-1,0,1]:
            box(name+' pallet block', (xx,sy*(depth*.5-.08),base+runner_h+spacer_h*.5),
                (runner_width,.12,spacer_h),'Pallet')
    for i in range(5):
        y = -(depth-.13)*.5+i*(depth-.13)/4
        box(name+' pallet deck', (x,y,base+pallet_height-deck_h*.5),
            (width,.13,deck_h),'Pallet')
    # CAD crosses indicate a load envelope, not literal diagonal strapping.
    # Use a closed shipping crate within that envelope with restrained panel
    # seams, rather than the old open bins or invented diagonal steel members.
    cargo_h = height-pallet_height
    cargo_w, cargo_d = width-.012, depth-.012
    cz = base+pallet_height+cargo_h*.5
    box(name+' enclosed shipping crate', (x,0,cz), (cargo_w,cargo_d,cargo_h),'Cargo',.004)
    seam = .007
    zmid = base+pallet_height+cargo_h*.48
    for sy in [-1,1]:
        y = sy*(cargo_d*.5+.0005)
        box(name+' horizontal package seam', (x,y,zmid), (cargo_w,.001,seam),'CargoEdges')
        box(name+' vertical package seam', (x,y,cz), (seam,.001,cargo_h-.012),'CargoEdges')
    for sx in [-1,1]:
        xx = x+sx*(cargo_w*.5+.0005)
        box(name+' side package seam', (xx,0,zmid), (.001,cargo_d,seam),'CargoEdges')
    box(name+' upper package seam', (x,0,base+height-.0005), (seam,cargo_d,.001),'CargoEdges')


def make_rack(spec):
    global COLLECTION
    COLLECTION = bpy.data.collections.new(spec['name'])
    bpy.context.scene.collection.children.link(COLLECTION)
    COLLECTION['cad_specification'] = spec['code']
    COLLECTION['cad_levels_including_floor'] = len(spec['cargo_base_z_m'])
    build_frame(spec)
    for level, (base, height) in enumerate(zip(spec['cargo_base_z_m'],spec['cargo_envelope_heights_m'])):
        for column, x in enumerate(spec['cargo_center_x_m']):
            build_load('Level %02d load %d' % (level+1,column+1), x,base,
                       spec['cargo_width_m'],spec['cargo_depth_m'],height,spec['pallet_height_m'],
                       spec['pallet_deck_thickness_m'],spec['pallet_runner_width_m'])
    return COLLECTION


def export_asset(spec, collection):
    deps = bpy.context.evaluated_depsgraph_get()
    copies = []
    solid_boxes = []
    for original in collection.objects:
        data = bpy.data.meshes.new_from_object(original.evaluated_get(deps), depsgraph=deps)
        copy = bpy.data.objects.new(original.name+'_Export',data)
        bpy.context.scene.collection.objects.link(copy)
        copy.matrix_world = original.matrix_world.copy()
        copies.append(copy)
        if original.name.startswith('Upright adjustment slot'):
            continue
        points = [original.matrix_world @ vertex.co for vertex in data.vertices]
        low = [min(point[i] for point in points) for i in range(3)]
        high = [max(point[i] for point in points) for i in range(3)]
        solid_boxes.append(dict(name=original.name,
            role=original.get('physical_material_slot','Detail'),
            center_m=[(a+b)*.5 for a,b in zip(low,high)],
            size_m=[b-a for a,b in zip(low,high)]))
    bpy.ops.object.select_all(action='DESELECT')
    for copy in copies:
        copy.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = spec['name']
    bpy.context.scene.cursor.location = (0,0,0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    old_slots = [m.name for m in obj.data.materials]
    material_indices = [SLOT_NAMES.index(old_slots[p.material_index].replace('M_GHS_CADRack_',''))
                        for p in obj.data.polygons]
    obj.data.materials.clear()
    for name in SLOT_NAMES:
        obj.data.materials.append(MATERIALS[name])
    for polygon,index in zip(obj.data.polygons,material_indices):
        polygon.material_index = index
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.calc_loop_triangles()
    bounds = [[min(v.co[i] for v in obj.data.vertices),max(v.co[i] for v in obj.data.vertices)]
              for i in range(3)]
    expected_width = spec['frame_width_m']
    expected_depth = max(spec['frame_depth_m'],spec['cargo_depth_m'] if spec['cargo_center_x_m'] else 0)
    expected_height = max(spec['upright_height_m'],
                          max(z+h for z,h in zip(spec['cargo_base_z_m'],spec['cargo_envelope_heights_m'])))
    assert abs(bounds[0][0]+expected_width*.5)<.001, (spec['name'],'width',bounds)
    assert abs(bounds[0][1]-expected_width*.5)<.001, (spec['name'],'width',bounds)
    assert abs(bounds[1][1]-expected_depth*.5)<.001, (spec['name'],'depth',bounds)
    assert abs(bounds[2][0])<.00001, (spec['name'],'floor',bounds)
    assert abs(bounds[2][1]-expected_height)<.001, (spec['name'],'height',bounds)
    fbx = OUT/(spec['name']+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
        mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
    result = dict(spec, fbx=str(fbx), slots=[MATERIALS[name].name for name in SLOT_NAMES],
                  slot_roles=SLOT_NAMES, origin_m=[0,0,0], bounds_m=bounds,
                  source_parts=len(collection.objects), vertices=len(obj.data.vertices),
                  triangles=len(obj.data.loop_triangles), polygons=len(obj.data.polygons),
                  solid_boxes=solid_boxes,
                  fbx_sha256=hashlib.sha256(fbx.read_bytes()).hexdigest())
    bpy.data.objects.remove(obj,do_unlink=True)
    return result


def preview(collections, specs):
    shown = []
    for collection,spec in zip(collections,specs):
        visible = spec['canonical'] and not spec['pass_variant']
        collection.hide_render = not visible
        if visible:
            shown.append((collection,spec))
    for index,(collection,spec) in enumerate(shown):
        old = Vector(collection['library_board_offset_m'])
        offset = Vector(((index-2)*4.8,0,0))
        for obj in collection.objects:
            obj.location += offset-old
        text = bpy.data.curves.new('Preview specification label','FONT')
        text.body = spec['code']+'  /  '+str(len(spec['cargo_base_z_m']))+' LEVELS'
        text.align_x = 'CENTER'
        text.size = .34
        text.extrude = .002
        label = bpy.data.objects.new('Preview label '+spec['code'],text)
        bpy.context.scene.collection.objects.link(label)
        label.location = (offset.x,-1.10,.15)
        label.rotation_euler = (math.pi*.5,0,0)
        label.data.materials.append(MATERIALS['Braces'])
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 2400
    scene.render.resolution_y = 1400
    scene.render.resolution_percentage = 100
    scene.world.color = (.08,.08,.08)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.02))
    ground = bpy.context.object
    ground.name = 'Preview floor - not exported'
    floor_mat = bpy.data.materials.new('Preview neutral floor')
    floor_mat.diffuse_color = (.11,.14,.19,1)
    ground.data.materials.append(floor_mat)
    for position,power,size in [((0,-10,19),9000,16),((-12,5,13),6000,12),((18,7,12),5000,10)]:
        bpy.ops.object.light_add(type='AREA',location=position)
        lamp = bpy.context.object
        lamp.data.energy = power
        lamp.data.shape = 'DISK'
        lamp.data.size = size
        lamp.rotation_euler = (Vector((0,0,4))-lamp.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(10,-40,20))
    camera = bpy.context.object
    camera.rotation_euler = (Vector((0,0,4.3))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 27
    scene.camera = camera
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(OUT/'cad_rack_models_preview.png')
    bpy.ops.render.render(write_still=True)


def models_from_audited_types(data, mapping):
    result = []
    seen = set()

    def add(code, pass_variant, width, canonical):
        width = round(width,4)
        key = '%s:%d:%.4f' % (code,int(pass_variant),width)
        if key in seen:
            return
        seen.add(key)
        spec = copy.deepcopy(data['types'][code])
        bridge = spec.pop('bridge_variant',None)
        if pass_variant:
            assert bridge, (code,'has no CAD bridge specification')
            spec.update(bridge)
        suffix = '_Pass' if pass_variant else ''
        if not canonical:
            suffix += '_W%05d' % round(width*10000)
        spec.update(name='SM_GHS_CADRack_'+code+suffix,
                    spec_type=code,variant='pass' if pass_variant else 'full',
                    pass_variant=pass_variant,canonical=canonical,
                    mapping_key=key,frame_width_m=width,
                    clear_width_m=round(width-2*spec['upright_front_width_m'],6),
                    beam_heights_m=[beam['height_m'] for beam in spec['source_beams']])
        # Standard loads keep their full real dimensions in reduced bay spans.
        # Divide the remaining clearance equally; no anisotropic rack scaling.
        span = spec['clear_width_m']
        cargo_width = spec['cargo_width_m']
        count = min(3,max(0,int((span-.03)/(cargo_width+.03))))
        gap = (span-count*cargo_width)/(count+1)
        spec['cargo_center_x_m'] = [-span*.5+gap+cargo_width*.5+i*(cargo_width+gap)
                                   for i in range(count)]
        spec['storage_base_z_m'] = list(spec['cargo_base_z_m'])
        spec['cargo_columns'] = count
        spec['cargo_width_preserved'] = True
        result.append(spec)

    for code in ['A','B','C','D1','D2']:
        add(code,False,data['types'][code]['frame_width_m'],True)
    for code in ['A','B','C']:
        add(code,True,data['types'][code]['frame_width_m'],True)
    for row in mapping['assignments']+mapping['additional_pass_racks']:
        add(row['spec_type'],row['pass_variant'],row['physical_span_m'],False)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--specs',required=True)
    parser.add_argument('--mapping')
    parser.add_argument('--preview',action='store_true')
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    args = parser.parse_args(argv)
    source = Path(args.specs)
    data = json.loads(source.read_text(encoding='utf-8'))
    mapping_source = Path(args.mapping) if args.mapping else None
    mapping = json.loads(mapping_source.read_text(encoding='utf-8')) if mapping_source else None
    specs = models_from_audited_types(data,mapping) if mapping else data['models']
    prepare()
    collections, exports = [], []
    for spec in specs:
        collection = make_rack(spec)
        collections.append(collection)
        exports.append(export_asset(spec,collection))
        print('CAD_RACK_EXPORTED',spec['name'],exports[-1]['triangles'],flush=True)
    # Separate editable collections on a comparison board after the centred
    # exports are complete. Equal scaling makes all CAD heights comparable.
    for index,collection in enumerate(collections):
        offset = Vector(((index%8-3.5)*4.8,(index//8)*4,0))
        for obj in collection.objects:
            obj.location += offset
        collection['library_board_offset_m'] = list(offset)
    result = dict(source_spec=str(source),source_spec_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  units='metres',mesh_origin='centred at floor',meshes=exports,
                  blend=str(OUT/'cad_rack_models.blend'),
                  mapping_source=str(mapping_source) if mapping_source else None,
                  mapping_source_sha256=hashlib.sha256(mapping_source.read_bytes()).hexdigest() if mapping_source else None,
                  modeling_assumptions=data.get('modeling_assumptions',[])+[
                      'Pallet height 0.123952 m, deck thickness 0.015875 m and runner width 0.0381 m come from CAD load block geometry.',
                      'Profile wall thickness, perforations, bracing gauge and packaging seams are visual details, not structural engineering specifications.',
                      'Reduced-width clearance variants preserve upright section and cargo dimensions; narrow spans have fewer full-size loads.',
                      'solid_boxes are conservative local-space AABBs of physical parts, including side diagonal bracing.'])
    (OUT/'cad_rack_models.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'cad_rack_models.blend'))
    if args.preview:
        preview(collections,specs)
    print('GHS_CAD_RACK_MODELS_COMPLETE',json.dumps([(e['name'],e['bounds_m'],e['triangles']) for e in exports]))


if __name__ == '__main__':
    main()
