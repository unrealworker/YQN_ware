"""192-inch MPR rack: widen only the GHS frame; cargo remains rigid-sized.

Run in isolated background Blender. Uses the existing GHS frame, pallet and
carton generators without invoking their mains or touching source assets.
"""
from pathlib import Path
import copy,hashlib,importlib.util,json,math,sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/storage'
SLOTS=['Upright','Beam','Braces','Pallet','Cargo','CargoEdges','Detail']
ROLES=['Porcelain','Cobalt','Porcelain','Cobalt','Cargo','CargoSeam','Charcoal']
PALETTE=[(.83,.85,.88),(.018,.075,.51),(.83,.85,.88),(.018,.075,.51),(.53,.35,.20),(.36,.24,.14),(.055,.075,.11)]


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def merge_collection(collection,name,materials):
    verts=[];faces=[];slotids=[]
    for obj in collection.objects:
        off=len(verts);verts.extend(tuple(obj.matrix_world@v.co) for v in obj.data.vertices)
        role=obj.get('physical_material_slot','Detail');slot=SLOTS.index(role)
        for p in obj.data.polygons:faces.append(tuple(i+off for i in p.vertices));slotids.append(slot)
    data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
    for m in materials:obj.data.materials.append(m)
    for p,idx in zip(obj.data.polygons,slotids):p.material_index=idx
    data.calc_loop_triangles()
    return obj,[[min(v[i] for v in verts),max(v[i] for v in verts)] for i in range(3)]


def export(obj,path):
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    refined=load_module('ghs_refined_source',ROOT/'Scripts/ghs/build_refined_rack_cargo.py');cad=refined.cad
    # Same generator geometry, no bevel subdivision needed for a repeated rack.
    refined.RULES['edge_radius_m']=0
    original=json.loads((ROOT/'SourceAssets/GHS/RackSpecs/Models/cad_rack_models.json').read_text())
    spec=copy.deepcopy(next(m for m in original['meshes'] if m['name']=='SM_GHS_CADRack_A'))
    spec.update(name='SM_MPR_Rack_42D_192',code='MPR_42D_192',frame_width_m=5.0292,clear_width_m=4.8768,
        cargo_center_x_m=[-1.7526,-.5842,.5842,1.7526],cargo_x_centers_m=[-1.7526,-.5842,.5842,1.7526],cargo_columns=4)
    materials=[]
    for slot,role,color in zip(SLOTS,ROLES,PALETTE):
        mat=bpy.data.materials.new('M_MPR_Rack192_'+slot);mat.diffuse_color=(*color,1);mat.use_nodes=True
        bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Roughness'].default_value=.72
        materials.append(mat)
    cad.MATERIALS=dict(zip(SLOTS,materials))
    # Disable manufacturing edge modifiers on the source frame beams too.
    old_box=cad.box
    def simple_box(name,center,size,slot,bevel=0):return old_box(name,center,size,slot,0)
    cad.box=simple_box
    collection,stacks=refined.build(spec)
    bpy.context.view_layer.update()
    cargo=[o for o in collection.objects if o.get('unscaled_rigid_carton')]
    assert len(cargo)==sum(s['carton_count'] for s in stacks)
    assert all(tuple(o.scale)==(1.,1.,1.) for o in cargo)
    assert all(abs(o['carton_dimensions_m'][0]-.45)<1e-8 and abs(o['carton_dimensions_m'][1]-.55)<1e-8 for o in cargo)
    assert min(s['top_clearance_m'] for s in stacks)>.1
    meshes=[];objects=[]
    for lod in range(3):
        selected=bpy.data.collections.new('Rack192_LOD'+str(lod));bpy.context.scene.collection.children.link(selected)
        for obj in collection.objects:
            role=obj.get('physical_material_slot','Detail');name=obj.name
            if lod>0 and role in ('CargoEdges','Detail'):continue
            if lod>0 and name.startswith('Upright side return diagonal'):continue
            if lod==1 and role=='Pallet':continue
            if lod==2 and role in ('Cargo','Pallet'):continue
            if lod==2 and name.startswith('Upright side diagonal'):
                # Preserve a sparse structural X-brace silhouette.
                if int(name.rsplit('.',1)[-1])%2 if name.rsplit('.',1)[-1].isdigit() else False:continue
            selected.objects.link(obj)
        if lod==1:
            cad.COLLECTION=selected
            for stack in stacks:
                x=stack['pallet_center_x_m'];base=stack['base_z_m'];w=spec['cargo_width_m'];d=spec['cargo_depth_m'];ph=spec['pallet_height_m'];deck=spec['pallet_deck_thickness_m'];rw=spec['pallet_runner_width_m']
                cad.box('LOD1 pallet top deck',(x,0,base+ph-deck/2),(w,d,deck),'Pallet')
                for sx in (-1,0,1):
                    xx=x+sx*(w/2-rw/2)
                    cad.box('LOD1 pallet runner',(xx,0,base+deck/2),(rw,d,deck),'Pallet')
                    cad.box('LOD1 pallet support',(xx,0,base+ph/2),(rw,.24,ph-2*deck),'Pallet')
            bpy.context.view_layer.update()
        if lod==2:
            cad.COLLECTION=selected
            for stack in stacks:
                x=stack['pallet_center_x_m'];base=stack['base_z_m'];height=stack['stack_top_z_m']-base-spec['pallet_height_m']
                cad.box('LOD2 pallet envelope',(x,0,base+spec['pallet_height_m']/2),(spec['cargo_width_m'],spec['cargo_depth_m'],spec['pallet_height_m']),'Pallet')
                cad.box('LOD2 rigid cargo silhouette',(x,0,base+spec['pallet_height_m']+height/2),(.944,1.136,height),'Cargo')
            bpy.context.view_layer.update()
        name=spec['name']+('_LOD'+str(lod) if lod else '')
        obj,bounds=merge_collection(selected,name,materials);objects.append(obj)
        fbx=OUT/(name+'.fbx');export(obj,fbx)
        assert abs(bounds[0][1]-bounds[0][0]-5.0292)<1e-5
        assert abs(bounds[2][1]-9.154)<1e-5 and abs(bounds[2][0])<1e-5
        meshes.append({'name':name,'fbx':fbx.relative_to(ROOT).as_posix(),'material_roles':ROLES,
            'material_slot_names':[m.name for m in materials],'bounds_m':bounds,
            'triangles':len(obj.data.loop_triangles),'vertices':len(obj.data.vertices),
            'sha256':hashlib.sha256(fbx.read_bytes()).hexdigest()})
        selected.hide_render=True;selected.hide_viewport=True
    collection.hide_render=True;collection.hide_viewport=True
    # Keep source components editable, show just LOD0 in the source artifact.
    for obj in objects[1:]:obj.hide_render=True;obj.hide_set(True)
    row=meshes[0];row.update(instance_only=True,lod_files=[m['fbx'] for m in meshes[1:]],lod_triangles=[m['triangles'] for m in meshes],
        frame_dimensions_m=[5.0292,1.0668,9.154],mesh_long_x=True,origin_m=[0,0,0])
    manifest={'schema_version':1,'units':'metres','axis':'CAD +Y; FBX -Y forward / Z up; UE reflects Y',
        'meshes':[row],'lod_details':meshes,'source_frame':'Scripts/ghs/build_cad_rack_models.py',
        'source_cargo':'Scripts/ghs/build_refined_rack_cargo.py',
        'assumptions':['MPR CAD specifies 42-inch-deep / 192-inch clear bay; 198-inch outer frame includes 3-inch uprights each side.',
        '9.154m height, 4 storage levels and shelf elevations reused from GHS A for visualization; no MPR elevation supplied.',
        'Original 1.016m x 1.2192m pallets retain normal front/rear overhang beyond the 1.0668m frame depth.'],
        'validation':{'cargo_not_scaled':True,'carton_count':len(cargo),'pallet_count':len(stacks),
        'pallet_dimensions_m':[spec['cargo_width_m'],spec['cargo_depth_m'],spec['pallet_height_m']],
        'carton_width_depth_m':[.45,.55],'minimum_stack_clearance_m':min(s['top_clearance_m'] for s in stacks),
        'seven_slots_all_lods':True,'triangles_decrease':meshes[0]['triangles']>meshes[1]['triangles']>meshes[2]['triangles']},
        'cargo_stacks':stacks}
    assert manifest['validation']['triangles_decrease']
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_Rack192.blend'))
    # Export readback verifies the actual interchange products, not just source.
    checks=[]
    for m in meshes:
        before=set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(ROOT/m['fbx']))
        imported=[o for o in bpy.data.objects if o not in before and o.type=='MESH'];assert len(imported)==1
        obj=imported[0];vv=[obj.matrix_world@v.co for v in obj.data.vertices]
        bounds=[[min(v[i] for v in vv),max(v[i] for v in vv)] for i in range(3)]
        error=max(abs(bounds[i][j]-m['bounds_m'][i][j]) for i in range(3) for j in range(2))
        assert error<.001 and len(obj.data.materials)==7
        checks.append({'name':m['name'],'max_bounds_error_m':error,'material_slots':7})
        for o in imported:bpy.data.objects.remove(o,do_unlink=True)
    (OUT/'validation.json').write_text(json.dumps({'success':True,'checks':checks,**manifest['validation']},indent=2),encoding='utf-8')
    # Separate visible near-view review; this is not included in the FBX.
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24
    scene.world.color=(.45,.45,.45)
    for loc in [(3,-7,12),(-6,-2,9),(5,5,11)]:
        light=bpy.data.lights.new('ReviewLight','AREA');light.energy=1800;light.size=7
        o=bpy.data.objects.new('ReviewLight',light);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,4))-o.location).to_track_quat('-Z','Y').to_euler()
    camera=bpy.data.cameras.new('ReviewCamera');o=bpy.data.objects.new('ReviewCamera',camera);scene.collection.objects.link(o);o.location=(8,-15,10)
    o.rotation_euler=(Vector((0,0,4.4))-o.location).to_track_quat('-Z','Y').to_euler();camera.type='ORTHO';camera.ortho_scale=11.8;scene.camera=o
    scene.render.resolution_x=1000;scene.render.resolution_y=1200;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/'rack192_preview.png');bpy.ops.render.render(write_still=True)
    print('MPR_RACK192_COMPLETE '+json.dumps({'lod_triangles':row['lod_triangles'],'cargo_count':len(cargo),'pallet_count':len(stacks),'bounds':row['bounds_m']}))

if __name__=='__main__':main()
