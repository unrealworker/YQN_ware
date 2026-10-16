"""Build the closed CAD envelope and genuinely two-sided half-open dock shutter.

Run with bundled Python for geometry/docking data, then Blender --background
--python this_file for FBX and editable Blender source. Original assets are read
only. CAD metres are the source frame; Unreal imports reflect Y.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GHS/RefinementV2/Envelope'
OUT.mkdir(parents=True, exist_ok=True)
WIDTH = 119.75 * .0254
LEAF = 110 * .0254
DEPTH = .1876647153
HEIGHT = 4.2
OPEN_HEIGHT = 2.1
WALL_HEIGHT = 9.6
WALL_THICKNESS = .254


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf8')


def build_geometry():
    sys.path.insert(0, str(ROOT / 'Scripts/_vendor/cad'))
    from shapely import constrained_delaunay_triangles
    from shapely.affinity import rotate, translate
    from shapely.geometry import Polygon, Point, box, mapping, shape
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union

    cad = read(ROOT / 'SourceAssets/GHS/cad_layout.json')
    old = read(ROOT / 'SourceAssets/GHS/joined_walls_geometry.json')
    doors = read(ROOT / 'SourceAssets/GHS/RackSpecs/cad_plan_mapping.json')['loading_doors']
    footprint = Polygon(cad['footprint_outline_m'])
    ring = footprint.difference(footprint.buffer(-WALL_THICKNESS, join_style='mitre'))
    previous = shape(old['footprint_geojson'])
    upper = unary_union([previous, ring])
    cuts, docking = [], []
    for door in doors:
        xy = door['physical_center_m']
        angle = door['rotation_deg']
        cut = translate(rotate(box(-WIDTH/2, -.8, WIDTH/2, .8), angle, origin=(0, 0)), *xy)
        cuts.append(cut)
        theta = math.radians(angle)
        tangent = (math.cos(theta), math.sin(theta))
        n = [-tangent[1], tangent[0]]
        # Test the two sides against the source CAD footprint, never door numbering.
        if footprint.contains(Point(xy[0]+n[0], xy[1]+n[1])):
            n = [-n[0], -n[1]]
        n = [round(v, 12) for v in n]
        assert not footprint.contains(Point(xy[0]+n[0], xy[1]+n[1]))
        rear = [xy[i]+n[i]*.65 for i in range(2)]
        center = [xy[i]+n[i]*5.15 for i in range(2)]
        docking.append({
            'instance_id': door['instance_id'], 'dock_number': door['attributes']['DOCK_NO.'],
            'door_center_cad_m': [*xy, 0], 'door_rotation_cad_deg': angle,
            'outward_unit_normal_cad': [*n, 0], 'outward_unit_normal_ue': [n[0], -n[1], 0],
            'truck_rear_dock_target_cad_m': [*rear, 0],
            'truck_rear_dock_target_ue_cm': [rear[0]*100, -rear[1]*100, 0],
            'suggested_9m_truck_center_cad_m': [*center, 0],
            'suggested_9m_truck_center_ue_cm': [center[0]*100, -center[1]*100, 0],
            'truck_forward_cad_yaw_deg': math.degrees(math.atan2(n[1], n[0])),
            'truck_forward_ue_yaw_deg': math.degrees(math.atan2(-n[1], n[0])),
            'rear_distance_from_door_m': .65, 'suggested_truck_length_m': 9,
            'note': 'Truck local +X points away from building; rear bumper is the dock target.'
        })
    all_cuts = unary_union(cuts)
    lower = upper.difference(all_cuts)
    soffits = upper.difference(lower)
    trim = upper.difference(upper.buffer(-.012, join_style='mitre'))
    meshes = {name: {'vertices': [], 'faces': []} for name in (
        'SM_GHS_V2ExteriorFaces', 'SM_GHS_V2ExteriorSections', 'SM_GHS_V2ExteriorEdges')}

    def polygons(geom):
        if geom.geom_type == 'Polygon':
            return [geom]
        return [g for g in geom.geoms if g.geom_type == 'Polygon']

    def sides(geom, z0, z1):
        mesh = meshes['SM_GHS_V2ExteriorFaces']
        for poly in polygons(geom):
            poly = orient(poly, sign=1)
            for loop in [poly.exterior, *poly.interiors]:
                points = list(loop.coords)
                for a, b in zip(points, points[1:]):
                    if math.dist(a, b) < 1e-8:
                        continue
                    k = len(mesh['vertices'])
                    mesh['vertices'] += [[*a,z0], [*b,z0], [*b,z1], [*a,z1]]
                    mesh['faces'].append([k,k+1,k+2,k+3])

    def cap(geom, name, z, upward=True):
        mesh = meshes[name]
        area = 0
        for tri in constrained_delaunay_triangles(geom).geoms:
            if tri.area < 1e-12:
                continue
            assert tri.difference(geom).area < 1e-7
            coords = list(orient(tri, sign=1 if upward else -1).exterior.coords)[:3]
            k = len(mesh['vertices'])
            mesh['vertices'] += [[*p,z] for p in coords]
            mesh['faces'].append([k,k+1,k+2])
            area += tri.area
        assert abs(area-geom.area) < 1e-5
        return area

    sides(lower, 0, HEIGHT)
    sides(upper, HEIGHT, WALL_HEIGHT)
    cap(lower, 'SM_GHS_V2ExteriorSections', 0, False)
    cap(soffits, 'SM_GHS_V2ExteriorSections', HEIGHT, False)
    top_area = cap(upper, 'SM_GHS_V2ExteriorSections', WALL_HEIGHT)
    cap(trim, 'SM_GHS_V2ExteriorEdges', WALL_HEIGHT+.0005)
    openings = []
    for door, cut in zip(doors, cuts):
        entry = {
            'instance_id': door['instance_id'], 'dock_number': door['attributes']['DOCK_NO.'],
            'width_m': WIDTH, 'bottom_m': 0, 'lintel_underside_m': HEIGHT,
            'wall_obstruction_area_below_lintel_m2': lower.intersection(cut).area,
            'lintel_area_above_opening_m2': upper.intersection(cut).area,
            'cut_polygon_cad_m': list(cut.exterior.coords),
        }
        assert entry['wall_obstruction_area_below_lintel_m2'] < 1e-8
        assert entry['lintel_area_above_opening_m2'] > .5
        openings.append(entry)
    assert len(openings) == 87
    # CAD oblique edges can produce sub-nanometre GEOS residue after union.
    assert ring.difference(upper).area < 1e-8
    assert footprint.is_valid and ring.is_valid and lower.is_valid and upper.is_valid
    assert len(ring.interiors) == 1
    retained = previous.difference(all_cuts)
    assert retained.difference(lower).area < 1e-8
    verification = {
        'source_wall_count': 330, 'door_count': 87, 'wall_height_m': WALL_HEIGHT,
        'wall_thickness_m': WALL_THICKNESS, 'lintel_bottom_m': HEIGHT,
        'main_building_outline_closed': cad['footprint_outline_m'][0] == cad['footprint_outline_m'][-1],
        'main_building_outline_valid': footprint.is_valid,
        'top_perimeter_ring_continuous': ring.geom_type == 'Polygon' and len(ring.interiors) == 1,
        'top_perimeter_uncovered_area_m2': ring.difference(upper).area,
        'all_87_door_openings_clear': all(v['wall_obstruction_area_below_lintel_m2'] < 1e-8 for v in openings),
        'all_87_door_lintels_present': all(v['lintel_area_above_opening_m2'] > .5 for v in openings),
        'preserved_existing_wall_outside_door_openings_area_loss_m2': retained.difference(lower).area,
        'building_footprint_area_m2': footprint.area, 'wall_top_cap_area_m2': top_area,
        'roofless': True, 'no_roof_cap_created': top_area < footprint.area * .02,
        'old_wall_footprint_area_m2': previous.area,
        'new_upper_wall_footprint_area_m2': upper.area,
        'new_lower_wall_footprint_area_m2': lower.area,
        'old_wall_missing_perimeter_area_m2': ring.difference(previous).area,
        'interior_layout_policy': 'Union original wall geometry with measured perimeter; remove only 87 loading-door prisms below 4.2m.',
        'door_geometry_policy': 'No backplate. Twelve solid shutter slats from 2.1m to 4.03m; both broad faces use the original Panel role.',
    }
    data = {
        'schema_version': 2, 'coordinate_contract': 'CAD metres; UE=(X,-Y,Z)*100',
        'source_footprint_handles': cad['footprint_source_handles'],
        'main_building_polygon_cad_m': cad['footprint_outline_m'],
        'main_building_polygon_ue_cm': [[x*100,-y*100] for x,y in cad['footprint_outline_m']],
        'perimeter_ring_geojson': mapping(ring), 'upper_walls_geojson': mapping(upper),
        'lower_walls_geojson': mapping(lower), 'meshes': meshes,
        'openings': openings, 'verification': verification,
    }
    write('envelope_geometry.json', data)
    write('door_docking_targets.json', {'coordinate_contract': data['coordinate_contract'], 'doors': docking})
    write('building_footprint.json', {k:v for k,v in data.items() if k.startswith('main_building') or k in ['coordinate_contract','source_footprint_handles']})
    write('geometry_verification.json', verification)
    print(json.dumps(verification, indent=2))


def normalized_face_uv(mesh):
    """A well-conditioned independent UV island on every physical polygon.

    Subtract a local origin before projection (warehouse coordinates approach
    240m). Normalize each axis separately so tiny bevels and 400m wall panels
    both occupy a stable 0..1 UV range. Overlap is deliberate: these assets use
    flat role materials, not a texture atlas or a lightmap.
    """
    def sub(a,b):return tuple(a[k]-b[k] for k in range(3))
    def dot(a,b):return sum(a[k]*b[k] for k in range(3))
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    def unit(v):
        length=math.sqrt(dot(v,v));assert length>0
        return tuple(x/length for x in v)
    uv=mesh.uv_layers.get('UVMap') or mesh.uv_layers.new(name='UVMap')
    mesh.uv_layers.active=uv
    tangents=[None]*len(mesh.loops);bitangents=[None]*len(mesh.loops)
    for poly in mesh.polygons:
        points=[tuple(mesh.vertices[i].co) for i in poly.vertices]
        edges=[sub(b,a) for a,b in zip(points,points[1:]+points[:1])]
        u=unit(max(edges,key=lambda e:dot(e,e)))
        # Canonical sign prevents coincident coplanar corners on adjacent UV
        # islands from receiving opposite MikkTSpace tangents and cancelling.
        if u[max(range(3),key=lambda k:abs(u[k]))]<0:u=tuple(-x for x in u)
        relative=[sub(p,points[0]) for p in points]
        n=unit(tuple(poly.normal))
        v=unit(cross(n,u))
        projected=[(dot(p,u),dot(p,v)) for p in relative]
        limits=[(min(p[k] for p in projected),max(p[k] for p in projected)) for k in range(2)]
        assert all(hi>lo for lo,hi in limits),(mesh.name,poly.index,limits)
        for loop,point in zip(poly.loop_indices,projected):
            uv.data[loop].uv=tuple((point[k]-limits[k][0])/(limits[k][1]-limits[k][0]) for k in range(2))
            # Explicit loop basis avoids the acos-angle underflow of automated
            # tangent weighting at legitimate long, narrow CAD triangle tips.
            corner_n=unit(tuple(mesh.corner_normals[loop].vector))
            corner_u=unit(sub(u,tuple(dot(u,corner_n)*x for x in corner_n)))
            corner_v=unit(cross(corner_n,corner_u))
            tangents[loop]=corner_u;bitangents[loop]=corner_v
    mesh.calc_loop_triangles()
    areas=[]
    for tri in mesh.loop_triangles:
        a,b,c=[uv.data[i].uv for i in tri.loops]
        area=abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))/2
        assert area>1e-10,(mesh.name,tri.index,area)
        areas.append(area)
    return {'method':'Per-face orthogonal projection, origin-relative, independently normalized U/V',
            'uv_layer':uv.name,'minimum_uv_triangle_area':min(areas),
            'degenerate_uv_triangle_count':0,'triangles_checked':len(areas),
            'tangents':tangents,'bitangents':bitangents}


def save_library_with_uv(c,stem):
    """Same evaluated geometry/FBX contract as common.save_library, stable UVs."""
    import bpy
    scene=bpy.context.scene;scene.name='VideoReference_'+stem
    deps=bpy.context.evaluated_depsgraph_get();output=[];exports=[]
    for name,col in c.ASSETS:
        originals=[o for o in col.objects if o.type in {'MESH','FONT','CURVE'}]
        copies=[]
        for obj in originals:
            ev=obj.evaluated_get(deps)
            data=bpy.data.meshes.new_from_object(ev,preserve_all_data_layers=True,depsgraph=deps)
            copy=bpy.data.objects.new(obj.name+'_FBX',data)
            scene.collection.objects.link(copy);copy.matrix_world=obj.matrix_world.copy();copies.append(copy)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in copies:obj.select_set(True)
        bpy.context.view_layer.objects.active=copies[0]
        if len(copies)>1:bpy.ops.object.join()
        obj=bpy.context.object;obj.name=name
        scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
        mesh=obj.data
        empty=[p.index for p in mesh.polygons if p.area<1e-14]
        if empty:
            # GEOS can leave sub-float wall slivers. Drop only polygons that
            # already have zero surface area; keep every vertex coordinate.
            retained=[p for p in mesh.polygons if p.area>=1e-14]
            materials=list(mesh.materials)
            replacement=bpy.data.meshes.new(name+'_UVSafe')
            replacement.from_pydata([tuple(v.co) for v in mesh.vertices],[],[list(p.vertices) for p in retained])
            replacement.update()
            for mat in materials:replacement.materials.append(mat)
            for new,old in zip(replacement.polygons,retained):
                new.material_index=old.material_index;new.use_smooth=old.use_smooth
            obj.data=replacement;mesh=replacement
        uv_check=normalized_face_uv(mesh)
        tangents=uv_check.pop('tangents');bitangents=uv_check.pop('bitangents')
        slots=[m.name for m in mesh.materials]
        assert all(slot in c.MATERIALS for slot in slots)
        fbx=OUT/(name+'.fbx')
        # Inject our already normalized basis into the exporter's tangent arrays
        # only. No Blender installation file, geometry or normal is changed.
        # The -Y forward/+Z up FBX axes are identity in Blender's source frame.
        from io_scene_fbx import export_fbx_bin
        import numpy as np
        original_array_writer=export_fbx_bin.elem_data_single_float64_array
        def explicit_basis_writer(element,key,values):
            if key==b'Tangents':values=np.asarray(tangents,dtype=np.float64).reshape(-1)
            elif key==b'Binormals':values=np.asarray(bitangents,dtype=np.float64).reshape(-1)
            return original_array_writer(element,key,values)
        export_fbx_bin.elem_data_single_float64_array=explicit_basis_writer
        try:
            bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False,use_tspace=True)
        finally:export_fbx_bin.elem_data_single_float64_array=original_array_writer
        uv_check['explicit_tangent_space']='Unit orthogonal loop basis exported; import normals and tangents in UE.'
        bounds=[[min(v.co[i] for v in mesh.vertices),max(v.co[i] for v in mesh.vertices)] for i in range(3)]
        output.append(dict(name=name,fbx=str(fbx),slots=slots,bounds_m=bounds,
                           source_parts=len(originals),vertices=len(mesh.vertices),polygons=len(mesh.polygons),
                           removed_zero_area_polygons=len(empty),uv_verification=uv_check))
        exports.append(obj)
        # Keep the editable primitive collection and the exact UV-safe export in
        # the blend. Exports are hidden to prevent double display in the library.
        obj.hide_set(True);obj.hide_render=True
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(stem+'.blend')))
    used={slot for entry in output for slot in entry['slots']}
    write(stem+'.json',dict(meshes=output,materials=[c.MATERIALS[m] for m in sorted(used)],blend=str(OUT/(stem+'.blend'))))


def export_assets():
    import bpy
    sys.path.insert(0, str(ROOT / 'Scripts/video_reference'))
    import common as c
    c.reset()
    c.OUT = OUT
    geometry = read(OUT/'envelope_geometry.json')
    wall_manifest = read(ROOT/'SourceAssets/GHS/joined_walls.json')
    mats = {}
    for info in wall_manifest['materials']:
        props = {k:v for k,v in info.items() if k not in {'name','base_color','roughness','metallic'}}
        mats[info['name']] = c.material(info['name'],info['base_color'],info['roughness'],info['metallic'],**props)
    names = {'Faces':'M_VR_WallVolume','Sections':'M_VR_WallSection','Edges':'M_VR_WallTrim'}
    for name, mesh in geometry['meshes'].items():
        c.begin_asset(name)
        slot = next(value for suffix,value in names.items() if name.endswith(suffix))
        c.mesh(name,mesh['vertices'],mesh['faces'],mats[slot])
    panel = c.material('M_CADDock_Panel',(.09,.18,.29),.6,.15)
    frame = c.material('M_CADDock_Frame',(.04,.1,.18),.55,.3)
    dark = c.material('M_CADDock_Dark',(.008,.016,.03),.8,0)
    detail = c.material('M_CADDock_Detail',(.08,.3,.43),.6,.1)
    c.begin_asset('SM_GHS_V2DockDoor')
    guide=(WIDTH-LEAF)/2
    for side in [-1,1]:
        c.box('Full-height guide rail',(side*(WIDTH/2-guide/2),0,HEIGHT/2),(guide,DEPTH,HEIGHT),frame,.004)
    c.box('Top roller housing',(0,0,HEIGHT-.085),(WIDTH,DEPTH,.17),frame,.006)
    top=HEIGHT-.17
    pitch=(top-OPEN_HEIGHT)/12
    for i in range(12):
        # Closed, solid boxes have outward normals on both faces. Tiny joints are
        # between slats; no full-width backing sheet can occlude either side.
        c.box('Two-sided Panel slat %02d'%i,(0,0,OPEN_HEIGHT+(i+.5)*pitch),(LEAF,.052,pitch-.004),panel,.002)
    c.box('Lifted bottom rubber seal',(0,0,OPEN_HEIGHT+.014),(LEAF,.057,.028),dark,.002)
    for side in [-1,1]:
        for face in [-1,1]:
            c.box('Narrow guide seal',(side*(LEAF/2-.004),face*.030,(OPEN_HEIGHT+top)/2),(.008,.010,top-OPEN_HEIGHT),dark,.001)
            c.box('Guide accent',(side*(LEAF/2+.006),face*(DEPTH/2-.012),HEIGHT/2),(.008,.015,HEIGHT-.17),detail,.001)
    # Record and assert material assignment on each actual slat before export.
    slats=[o for o in c.ACTIVE.objects if o.name.startswith('Two-sided Panel slat')]
    for obj in slats:
        assert len(obj.data.materials)==1 and obj.data.materials[0] is panel
        normals=[p.normal.y for p in obj.data.polygons]
        assert max(normals) > .99 and min(normals) < -.99
    assert len(slats)==12
    assert not any('gasket' in o.name.lower() or 'backplate' in o.name.lower() for o in c.ACTIVE.objects)
    assert min(o.location.z-o.dimensions.z/2 for o in slats) >= OPEN_HEIGHT
    save_library_with_uv(c,'envelope_v2')
    manifest=read(OUT/'envelope_v2.json')
    for mesh in manifest['meshes']:
        mesh['sha256']=hashlib.sha256(Path(mesh['fbx']).read_bytes()).hexdigest()
        mesh['role']='DockDoor' if mesh['name'].endswith('DockDoor') else next(k for k in names if mesh['name'].endswith(k))
        mesh['slot_roles']=[next((r for r in ['Panel','Frame','Dark','Detail'] if slot.endswith('_'+r)), mesh['role']) for slot in mesh['slots']]
    manifest.update(
        coordinate_contract='CAD metres; Unreal imported axes reflect Y; actor scale exactly [1,1,1]',
        wall_height_m=WALL_HEIGHT, perimeter_wall_thickness_m=WALL_THICKNESS,
        main_building_polygon_cad_m=geometry['main_building_polygon_cad_m'],
        verification=geometry['verification'],
        door={'overall_width_m':WIDTH,'leaf_width_m':LEAF,'depth_m':DEPTH,'height_m':HEIGHT,
              'clear_opening_height_m':OPEN_HEIGHT,'slat_count':12,'panel_on_both_faces':True,
              'full_size_black_backplate':False,'dark_material_only_narrow_seals':True,
              'opening_fraction':.5},
        integration={
            'fbx_normal_import_method':'FBXNIM_IMPORT_NORMALS_AND_TANGENTS',
            'tangent_policy':'Use explicit FBX unit orthogonal tangent/binormal arrays; do not recompute weighted tangents for the long narrow CAD cap triangles.',
            'maps':['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse'],
            'replace_actor_meshes':{'GHS_CAD_WallFaces':'SM_GHS_V2ExteriorFaces','GHS_CAD_WallSections':'SM_GHS_V2ExteriorSections','GHS_CAD_WallEdges':'SM_GHS_V2ExteriorEdges','GHS_CAD_DockDoors':'SM_GHS_V2DockDoor'},
            'wall_instances':'One instance each at CAD (0,0,0), rotation 0, scale (1,1,1). NEW walls are already 9.6m. Do not retain previous Z scale 3.42857. New edges already at 9.6005m; no actor height offset.',
            'door_instances':'All 87 positions and rotations from existing physical_center_m; keep unit scale.',
            'materials':'Reuse per-map original WallVolume/WallSection/WallTrim overrides; map door slot roles to per-map original CAD door Panel/Frame/Dark/Detail materials.',
            'remove_old_geometry':'Replace the three existing joined-wall instances; do not overlay new geometry onto old joined walls.',
            'docking_data':str(OUT/'door_docking_targets.json')})
    manifest['verification']['door_both_normals_panel_checked']=True
    manifest['verification']['door_half_open_geometric_check']=True
    manifest['verification']['all_exported_uv_triangles_non_degenerate']=True
    manifest['verification']['explicit_unit_tangent_space_exported']=True
    write('envelope_v2.json',manifest)
    print('ENVELOPE_V2_EXPORT_VERIFIED',len(manifest['meshes']))


if __name__=='__main__':
    try:
        import bpy
    except ImportError:
        build_geometry()
    else:
        export_assets()
