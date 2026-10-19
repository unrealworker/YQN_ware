"""Import the approved 50k forklift and add eight independently editable vehicles."""
import sys,json,math,shutil,traceback
from datetime import datetime
from pathlib import Path
import unreal
ROOT=Path(r'D:/UEPro/Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import import_manned_forklift as util
from sync_wall_heights import snapshot,transform,xyz
SOURCE=ROOT/'SourceAssets/GHS_Normal/MannedForklift'
PLAN_PATH=ROOT/'Saved/GHS_MannedForkliftFleetPlan.json'
REPORT=ROOT/'Saved/GHS_MannedForkliftFleetImport.json'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse';MAP_FILE='Content/Maps/GHS_CAD_NormalWarehouse.umap'
DEST='/Game/GHSNormalWarehouse/MannedForklift';MESH_NAME='SM_GHN_MannedForklift50k';MESH_PATH=DEST+'/Meshes/'+MESH_NAME
A=util.A;E=util.E;L=util.L;LIB=util.LIB;TOOLS=util.TOOLS;ML=util.ML

def material(spec):
    path=DEST+'/Materials/'+spec['name']
    assert not LIB.does_asset_exist(path),('Existing material',path)
    mat=TOOLS.create_asset(spec['name'],DEST+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    assert mat
    color=ML.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
    color.set_editor_property('constant',unreal.LinearColor(*spec['base_color'][:3],1))
    assert ML.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for prop,val in [(unreal.MaterialProperty.MP_ROUGHNESS,spec['roughness']),
                     (unreal.MaterialProperty.MP_METALLIC,spec['metallic']),
                     (unreal.MaterialProperty.MP_SPECULAR,.3)]:
        v=ML.create_material_expression(mat,unreal.MaterialExpressionConstant);v.set_editor_property('r',float(val))
        assert ML.connect_material_property(v,'',prop)
    emission=spec.get('emission',[0,0,0])
    if max(emission)>0:
        v=ML.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
        v.set_editor_property('constant',unreal.LinearColor(*emission,1))
        assert ML.connect_material_property(v,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    ML.recompile_material(mat);assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat

def check_placements(by,mesh,plan):
    obstacles=util.live_obstacles(by)
    # Cache each merged mesh's actual triangles once, avoiding huge merged bounding boxes.
    floor=[t for t in util.world_triangles(by['GHS_CAD_ExactFootprint']) if all(abs(p[2])<.01 for p in t)]
    assert floor
    walls=[]
    for name in sorted(util.WALLS):
        for tri in util.world_triangles(by[name]):
            walls.append((name,[min(p[i] for p in tri) for i in range(3)]+[max(p[i] for p in tri) for i in range(3)]))
    checked=[]
    for row in plan['placements']:
        t=unreal.Transform(location=unreal.Vector(*row['position_cm']),rotation=unreal.Rotator(yaw=row['yaw_deg']),scale=unreal.Vector(1,1,1))
        box=util.mesh_box(mesh,t)
        assert max(abs(a-b) for a,b in zip(box,row['bounds_cm']))<.3,(row['label'],box,row['bounds_cm'])
        assert abs(box[2]-.5)<.03
        relevant=[o for o in obstacles if util.overlap_z(box,o['bounds_cm'])]
        near=min(relevant,key=lambda o:util.xy_gap(box,o['bounds_cm']))
        gap=util.xy_gap(box,near['bounds_cm']);assert gap>=49.5,(row['label'],near,gap)
        samples=[(x,y) for x in (box[0],(box[0]+box[3])/2,box[3]) for y in (box[1],(box[1]+box[4])/2,box[4])]
        assert all(any(util.contains_xy(p,tri) for tri in floor) for p in samples),('Off floor',row['label'])
        wall_gap=min(util.xy_gap(box,w) for _,w in walls if util.overlap_z(box,w))
        assert wall_gap>=49.5,(row['label'],wall_gap)
        passage=row['clear_passage']['bounds_cm']
        passage_points=[(x,y) for x in (passage[0],(passage[0]+passage[3])/2,passage[3]) for y in (passage[1],(passage[1]+passage[4])/2,passage[4])]
        assert all(any(util.contains_xy(p,tri) for tri in floor) for p in passage_points),('Passage off floor',row['label'])
        assert not any(util.overlap_z(passage,o['bounds_cm']) and util.xy_gap(passage,o['bounds_cm'])<=0 for o in obstacles),('Passage blocked',row['label'])
        passage_wall_gap=min(util.xy_gap(passage,w) for _,w in walls if util.overlap_z(passage,w))
        assert passage_wall_gap>0,('Passage meets wall',row['label'])
        for earlier in checked:assert util.xy_gap(box,earlier['bounds_cm'])>500
        checked.append(dict(label=row['label'],position_cm=row['position_cm'],yaw_deg=row['yaw_deg'],bounds_cm=box,
            nearest_solid=near['label'],nearest_solid_index=near['index'],nearest_solid_cm=gap,wall_clearance_cm=wall_gap,
            floor_sample_count=len(samples),obstacle_count=len(obstacles),wall_triangles=len(walls),
            passage_live_validated=True,passage_wall_clearance_cm=passage_wall_gap))
    return checked

def run():
    assert E.get_editor_world().get_path_name().split('.')[0]==MAP and not E.get_game_world()
    assert not REPORT.exists(),'Import report exists; inspect before retrying'
    plan=util.read(PLAN_PATH);spec=util.read(SOURCE/'manned_forklift_50k_import_manifest.json')
    assert plan['success'] and len(plan['placements'])==8
    assert plan['map']==MAP
    assert plan['source_live_probe_sha256']==util.sha(ROOT/'Saved/GHS_MannedForkliftLiveProbe.json')
    assert plan['source_fbx_sha256']==util.sha(SOURCE/'manned_forklift_50k.fbx')
    assert spec['triangles']==49813
    assert not LIB.does_asset_exist(MESH_PATH)
    by=util.labels();before=snapshot(by)
    assert before==util.read(ROOT/'Saved/GHS_MannedForkliftLiveBaseline.json'),'Live scene changed since planning; refresh probe'
    assert all(r['label'] not in by for r in plan['placements'])
    backup=ROOT/'Saved/Backups'/('GHS_MannedFleet_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True)
    old=util.content_hashes();util.write(backup/'content_before.json',old);util.write(backup/'live_before.json',before)
    shutil.copy2(ROOT/MAP_FILE,backup/'GHS_CAD_NormalWarehouse.disk_before.umap')
    # Preserve the user's live unsaved edits before any additions.
    assert L.save_current_level();shutil.copy2(ROOT/MAP_FILE,backup/'GHS_CAD_NormalWarehouse.live_before.umap')
    report=dict(success=False,backup_root=str(backup),map=MAP,actor_count_before=len(by),plan=str(PLAN_PATH),
                source_fbx=str(SOURCE/'manned_forklift_50k.fbx'),source_sha256=util.sha(SOURCE/'manned_forklift_50k.fbx'),
                current_user_edits_preserved=True,import_stage='materials')
    util.write(REPORT,report);spawned=[];saved=False
    try:
        mats={s['name']:material(s) for s in spec['materials']}
        task=unreal.AssetImportTask();task.filename=report['source_fbx'];task.destination_path=DEST+'/Meshes';task.destination_name=MESH_NAME
        task.automated=True;task.replace_existing=False;task.save=True
        opt=unreal.FbxImportUI();opt.import_mesh=True;opt.import_as_skeletal=False;opt.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        opt.automated_import_should_detect_type=False;opt.import_materials=False;opt.import_textures=False;opt.import_animations=False
        d=opt.static_mesh_import_data;d.combine_meshes=True;d.generate_lightmap_u_vs=False;d.auto_generate_collision=False
        d.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS;d.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
        task.options=opt;TOOLS.import_asset_tasks([task]);mesh=LIB.load_asset(MESH_PATH)
        assert isinstance(mesh,unreal.StaticMesh),task.imported_object_paths
        slots=mesh.get_editor_property('static_materials');used=[]
        for i,s in enumerate(slots):
            name=str(s.get_editor_property('imported_material_slot_name'));assert name in mats,(name,list(mats))
            s.set_editor_property('material_interface',mats[name]);slots[i]=s;used.append(name)
        assert set(used)==set(mats)
        mesh.set_editor_property('static_materials',slots)
        unreal.load_module('StaticMeshEditor');sm=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        reduction=unreal.StaticMeshReductionOptions();reduction.auto_compute_lod_screen_size=False
        reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in [(1.,1.),(.5,.3),(.25,.12),(.12,.04)]]
        assert sm.set_lods(mesh,reduction)==4
        triangles=[mesh.get_num_triangles(i) for i in range(4)]
        assert 49000<=triangles[0]<=50000,triangles
        local=util.mesh_box(mesh,unreal.Transform());b=spec['bounds_m']
        expected=[100*b[0][0],-100*b[1][1],100*b[2][0],100*b[0][1],-100*b[1][0],100*b[2][1]]
        assert max(abs(a-c) for a,c in zip(local,expected))<.1,(local,expected)
        assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
        geometry=check_placements(by,mesh,plan)
        report.update(import_stage='validated_geometry',mesh=MESH_PATH,local_bounds_cm=local,lod_triangles=triangles,material_slots=used,geometry=geometry)
        util.write(REPORT,report)
        with unreal.ScopedEditorTransaction('Place eight staffed forklifts in floor storage'):
            for row in plan['placements']:
                a=A.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*row['position_cm']),unreal.Rotator(yaw=row['yaw_deg']))
                assert a;spawned.append(a);a.set_actor_label(row['label']);a.set_folder_path('GHS_Normal/Vehicles/MannedForklifts')
                a.tags=[unreal.Name('NormalWarehouseMannedForklift'),unreal.Name('TwinId='+row['label']),unreal.Name('FloorStorageWork'),unreal.Name('ModelScale=1to1')]
                c=a.static_mesh_component;c.set_static_mesh(mesh);c.set_mobility(unreal.ComponentMobility.MOVABLE)
                c.set_collision_profile_name('NoCollision');c.set_editor_property('receives_decals',False);c.set_editor_property('cast_shadow',True)
        after=util.labels();after_snap=snapshot(after)
        assert len(after)==len(by)+8
        for name,v in before.items():assert after_snap[name]==v,('Preexisting actor altered',name)
        assert all(a.get_attach_parent_actor() is None for a in spawned)
        assert L.save_current_level();saved=True
        new=util.content_hashes();changed=[p for p,h in old.items() if new[p]!=h]
        assert changed==[MAP_FILE],changed
        newfiles=sorted(set(new)-set(old));assert all(p.startswith('Content/GHSNormalWarehouse/MannedForklift/') for p in newfiles)
        util.write(backup/'live_after.json',after_snap)
        report.update(success=True,import_stage='saved',actor_count_after=len(after),actor_labels=[a.get_actor_label() for a in spawned],
            independent_actors=True,scale=[1,1,1],original_actors_unchanged=True,changed_content=changed,new_content=newfiles,map_sha256=util.sha(ROOT/MAP_FILE))
        A.set_selected_level_actors([])
        a=spawned[1];p=a.get_actor_location()
        E.set_level_viewport_camera_info(unreal.Vector(p.x+650,p.y-800,520),unreal.Rotator(pitch=-22,yaw=126,roll=0))
        unreal.log('MANNED_FORKLIFT_FLEET_IMPORTED '+str(triangles)+' 8 independent vehicles')
    except Exception:
        report['error']=traceback.format_exc()
        if not saved:
            for a in spawned:A.destroy_actor(a)
        raise
    finally:util.write(REPORT,report)

if __name__=='__main__':run()
