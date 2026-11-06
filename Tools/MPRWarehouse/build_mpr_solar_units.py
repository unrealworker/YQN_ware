"""Blender: coarser PV visual units within the existing 59 reviewed regions."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_mpr_hierarchy_solar as geo
import mpr_solar_hierarchy as previous

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/MPR/solar_units_20261106'
DEST = '/Game/MPRWarehouse/SolarUnits20261106'
ROLES = previous.ROLES
GAP = .08
FRAME = .015


def parts(lo, hi, target):
    n = hi-lo
    count = math.ceil(n/target)
    if n > target and n % target == 1:
        count -= 1  # absorb a one-cell remainder, instead of a new thin strip
    size, extra = divmod(n, count)
    cursor = lo
    result = []
    for i in range(count):
        end = cursor+size+(i < extra)
        result.append((cursor, end))
        cursor = end
    assert cursor == hi
    return result


def distance(a, b):
    return math.hypot(max(a[0]-b[2], b[0]-a[2], 0), max(a[1]-b[3], b[1]-a[3], 0))


def top_signature(ob, z):
    values = []
    for poly in ob.data.polygons:
        points = [ob.matrix_world @ ob.data.vertices[i].co for i in poly.vertices]
        if all(abs(p.z-z) < .00002 for p in points):
            values.append(tuple(sorted(tuple(round(v, 4) for v in p) for p in points)))
    return sorted(values)


def main():
    old, old_audit = previous.source_contract()
    layout_path = ROOT / old['layout_source']
    layout = geo.read(layout_path)
    tracked = [layout_path, ROOT/previous.SOURCE/'manifest.json', ROOT/previous.SOURCE/'final_palette.json',
               ROOT/previous.SOURCE/'module_layout.json']
    tracked += [ROOT/r['fbx'] for r in old['export_meshes']]
    hashes = {p.relative_to(ROOT).as_posix(): geo.sha(p) for p in tracked}
    OUT.mkdir(parents=True, exist_ok=True)
    origin, pitch, z = layout['uv_origin_m'], layout['pitch_m'], layout['top_z_m']
    units, bank_audit = {}, []
    cells = set()
    nearest, new_area, blue_area, original_area = 1e9, 0., 0., 0.
    shape_counts = Counter()
    for bank, blocks in layout['blocks'].items():
        rows = []
        for block_id, block in enumerate(blocks):
            ix0, iy0, ix1, iy1 = block['grid']
            bx0, by0, bx1, by1 = block['bounds_m']
            original_area += (bx1-bx0)*(by1-by0)
            for ix, xx in parts(ix0, ix1, 3):
                for iy, yy in parts(iy0, iy1, 2):
                    rect = [origin[0]+ix*pitch[0]+GAP/2, origin[1]+iy*pitch[1]+GAP/2,
                            origin[0]+xx*pitch[0]-GAP/2, origin[1]+yy*pitch[1]-GAP/2]
                    assert bx0 <= rect[0] < rect[2] <= bx1+1e-8 and by0 <= rect[1] < rect[3] <= by1+1e-8
                    keys = {(x,y) for x in range(ix,xx) for y in range(iy,yy)}
                    assert not cells.intersection(keys)
                    cells.update(keys)
                    tone = (ix*17+iy*23)%11
                    role = ROLES[2] if tone<2 else ROLES[3] if tone>8 else ROLES[1]
                    rows.append(dict(block_index=block_id, original_grid=[ix,iy,xx,yy], bounds_m=rect, role=role))
                    shape_counts[(xx-ix,yy-iy)] += 1
                    new_area += (rect[2]-rect[0])*(rect[3]-rect[1])
                    blue_area += (rect[2]-rect[0]-2*FRAME)*(rect[3]-rect[1]-2*FRAME)
                    nearest = min(nearest, *(distance(rect, d['bounds_m']) for d in layout['devices_unchanged']))
        units[bank] = rows
        bank_audit.append(dict(bank=bank, visual_units=len(rows), original_blocks=len(blocks)))
    assert len(cells) == 5636 and nearest >= .85
    original_units = geo.read(ROOT/previous.SOURCE/'module_layout.json')
    old_area = sum((r['bounds_m'][2]-r['bounds_m'][0])*(r['bounds_m'][3]-r['bounds_m'][1])
                   for rows in original_units.values() for r in rows)
    unit_count = sum(map(len,units.values()))
    assert unit_count < 1200
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1
    materials = {}
    for role in ROLES:
        spec = old['materials'][role]
        mat = bpy.data.materials.new(role)
        mat.use_nodes = True
        node = mat.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value = (*spec['base_color'],1)
        node.inputs['Roughness'].default_value = spec['roughness']
        node.inputs['Metallic'].default_value = spec['metallic']
        node.inputs['Specular IOR Level'].default_value = spec['specular']
        materials[role] = mat
    exports = []
    for bank, rows in units.items():
        for lod in range(3):
            name = 'SM_MPRSU_SolarBank_'+bank+('' if lod==0 else '_LOD'+str(lod))
            groups = {role: [[],[],[]] for role in ROLES}
            for row in rows:
                rect = row['bounds_m']
                if lod==0:
                    geo.box(*groups[ROLES[0]],rect,z-.08,z+.014)
                else:
                    geo.rectangle(*groups[ROLES[0]],rect,z+.014)
                x0,y0,x1,y1 = rect
                geo.rectangle(*groups[row['role']],[x0+FRAME,y0+FRAME,x1-FRAME,y1-FRAME],z+.020)
            for block in layout['blocks'][bank]:
                x0,y0,x1,y1 = block['bounds_m']
                for y in (y0+.15,y1-.15):
                    geo.box(*groups[ROLES[0]],[x0+.12,y-.06,x1-.12,y+.06],layout['roof_z_m']+.014,z-.08)
            vv,ff,uvs,indices = [],[],[],[]
            for idx,role in enumerate(ROLES):
                vertices,faces,uv = groups[role]
                offset = len(vv)
                vv.extend(vertices)
                ff.extend([[v+offset for v in face] for face in faces])
                uvs.extend(uv)
                indices.extend([idx]*len(faces))
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(vv,[],ff)
            mesh.update()
            ob = bpy.data.objects.new(name,mesh)
            bpy.context.scene.collection.objects.link(ob)
            for role in ROLES: mesh.materials.append(materials[role])
            uv = mesh.uv_layers.new(name='UVMap')
            for poly,idx,coords in zip(mesh.polygons,indices,uvs):
                poly.material_index = idx
                for loop,coord in zip(poly.loop_indices,coords): uv.data[loop].uv=coord
            bpy.ops.object.select_all(action='DESELECT')
            ob.select_set(True)
            bpy.context.view_layer.objects.active=ob
            path=OUT/(name+'.fbx')
            bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},axis_forward='-Y',
                axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
            mesh.calc_loop_triangles()
            exports.append(dict(name=name,fbx=path.relative_to(ROOT).as_posix(),sha256=geo.sha(path),
                bank=bank,lod=lod,triangles=len(mesh.loop_triangles),bounds_m=geo.bounds(vv),material_roles=ROLES))
            ob.hide_render=lod>0
            ob.hide_viewport=lod>0
    blend = OUT/'MPR_Solar_Units.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    byname={r['name']:r for r in exports}
    meshes=[]
    for bank in units:
        name='SM_MPRSU_SolarBank_'+bank
        levels=[byname[name],byname[name+'_LOD1'],byname[name+'_LOD2']]
        old_row=next(r for r in old['meshes'] if r['bank']==bank)
        row=dict(levels[0])
        row.update(category='Architecture',lod_files=[r['fbx'] for r in levels[1:]],
            lod_sha256=[r['sha256'] for r in levels[1:]],lod_triangles=[r['triangles'] for r in levels],
            lod_material_roles=[ROLES]*3,all_lod_material_roles=ROLES,lod_screen_sizes=old_row['lod_screen_sizes'],
            retained_actor_label=old_row['retained_actor_label'],source_mesh=previous.mesh_path(old_row),
            collision=False,nanite=False,full_precision_uvs=True,instance_only=False)
        meshes.append(row)
    geo.write(OUT/'unit_layout.json',units)
    manifest=dict(success=True,schema_version=1,map=previous.MAP,namespace=DEST,units='metres',
        axis='CAD +Y; UE X=100*x,Y=-100*y,Z=100*z',meshes=meshes,export_meshes=exports,
        material_roles=ROLES,materials=old['materials'],material_paths={r:previous.material_path(r) for r in ROLES},
        source_hashes=hashes,original_layout=old['layout_source'],preserved_blocks=layout['blocks'],
        preserved_device_count=195,original_module_cell_count=5636,visual_unit_count=unit_count,
        standard_merge_cells=[3,2],standard_pitch_m=[3*pitch[0],2*pitch[1]],gap_m=GAP,frame_width_m=FRAME,
        unit_shapes=[dict(cells=list(k),count=v) for k,v in sorted(shape_counts.items())],
        banks=bank_audit,minimum_device_clearance_m=nearest,required_device_clearance_m=.85,
        old_module_coverage_fraction=old_area/original_area,new_unit_coverage_fraction=new_area/original_area,
        new_blue_coverage_fraction=blue_area/original_area,source_assets_unchanged=True,
        unit_layout_sha256=geo.sha(OUT/'unit_layout.json'),previous_source_contract=old_audit,
        blend=blend.relative_to(ROOT).as_posix())
    geo.write(OUT/'manifest.json',manifest)
    # FBX round-trip validates real far/near silhouettes, material roles and axes.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    signatures, audits = {}, []
    for row in exports:
        bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']),use_custom_normals=True,colors_type='LINEAR')
        ob=next(o for o in bpy.context.selected_objects if o.type=='MESH')
        ob.data.calc_loop_triangles()
        actual=geo.bounds([tuple(ob.matrix_world@v.co) for v in ob.data.vertices])
        error=max(abs(a-b) for aa,bb in zip(actual,row['bounds_m']) for a,b in zip(aa,bb))
        assert error<.002 and len(ob.data.loop_triangles)==row['triangles']
        assert [s.material.name for s in ob.material_slots]==ROLES
        frame,blue=top_signature(ob,z+.014),top_signature(ob,z+.020)
        assert len(frame)==len(blue)==len(units[row['bank']])
        mask=hashlib.sha256(json.dumps([frame,blue],sort_keys=True).encode()).hexdigest()
        signatures.setdefault(row['bank'],[]).append(mask)
        for polygon,unit in zip(sorted(frame,key=lambda f:f[0]), sorted(units[row['bank']],key=lambda r:r['bounds_m'][:2])):
            actual_rect=[min(v[0]for v in polygon),min(v[1]for v in polygon),max(v[0]for v in polygon),max(v[1]for v in polygon)]
            assert max(abs(a-b)for a,b in zip(actual_rect,unit['bounds_m']))<.00011
        audits.append(dict(name=row['name'],triangles=row['triangles'],bounds_error_m=error,top_units=len(frame),top_mask=mask))
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        for collection in (bpy.data.meshes,bpy.data.materials):
            for item in list(collection):
                if item.users==0:collection.remove(item)
    assert all(len(set(v))==1 for v in signatures.values())
    assert all(geo.sha(ROOT/path)==sha for path,sha in hashes.items())
    geo.write(OUT/'geometry_validation.json',dict(success=True,manifest_sha256=geo.sha(OUT/'manifest.json'),
        roundtrip=audits,all_lods_identical_top_masks=True,all_original_cells_accounted_for=len(cells),
        original_blocks_preserved=59,roof_devices_preserved=195,minimum_device_clearance_m=nearest,
        triangle_counts=[sum(r['lod_triangles'][i]for r in meshes)for i in range(3)],
        old_assets_unchanged=True,visual_unit_count=unit_count))
    print('SOLAR_UNITS_READY',json.dumps(dict(units=unit_count,coverage=new_area/original_area,
        clearance=nearest,triangles=[sum(r['lod_triangles'][i]for r in meshes)for i in range(3)])),flush=True)


if __name__=='__main__':main()
