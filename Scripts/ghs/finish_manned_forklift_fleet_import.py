"""Continue the recorded asset import after adjusting one aisle to the live wall."""
import sys,importlib,traceback,runpy,shutil
sys.path.insert(0,'D:/UEPro/Test/Scripts/ghs')
import import_manned_forklift_fleet as f
importlib.reload(f)
import unreal

def run():
    r=f.util.read(f.REPORT)
    assert not r['success'] and r['import_stage']=='materials'
    assert "Passage meets wall" in r['error'] and 'GHN_MannedForklift_02' in r['error']
    assert f.E.get_editor_world().get_path_name().split('.')[0]==f.MAP and not f.E.get_game_world()
    backup=f.Path(r['backup_root'])
    # The user can continue editing while assets import. Re-probe and plan from
    # the latest live world; never restore actors removed after the first probe.
    for name in ('GHS_MannedForkliftLiveProbe.json','GHS_MannedForkliftLiveBaseline.json','GHS_MannedForkliftFleetPlan.json'):
        shutil.copy2(f.ROOT/'Saved'/name,backup/('initial_'+name))
    runpy.run_path(str(f.ROOT/'Scripts/ghs/probe_manned_forklift_scene.py'),run_name='__main__')
    runpy.run_path(str(f.ROOT/'Scripts/ghs/plan_manned_forklift_fleet.py'),run_name='__main__')
    by=f.util.labels();before=f.snapshot(by)
    assert before==f.util.read(f.ROOT/'Saved/GHS_MannedForkliftLiveBaseline.json')
    f.util.write(backup/'live_before_final.json',before)
    shutil.copy2(f.ROOT/f.MAP_FILE,backup/'GHS_CAD_NormalWarehouse.disk_before_final.umap')
    assert f.L.save_current_level()
    shutil.copy2(f.ROOT/f.MAP_FILE,backup/'GHS_CAD_NormalWarehouse.live_before_final.umap')
    r['initial_actor_count_before']=r['actor_count_before'];r['actor_count_before']=len(by)
    plan=f.util.read(f.PLAN_PATH);spec=f.util.read(f.SOURCE/'manned_forklift_50k_import_manifest.json')
    assert plan['map']==f.MAP and len(plan['placements'])==8
    assert plan['source_fbx_sha256']==f.util.sha(f.SOURCE/'manned_forklift_50k.fbx')==r['source_sha256']
    mesh=f.LIB.load_asset(f.MESH_PATH);assert isinstance(mesh,unreal.StaticMesh)
    local=f.util.mesh_box(mesh,unreal.Transform());b=spec['bounds_m']
    expected=[100*b[0][0],-100*b[1][1],100*b[2][0],100*b[0][1],-100*b[1][0],100*b[2][1]]
    assert max(abs(a-c) for a,c in zip(local,expected))<.1
    triangles=[mesh.get_num_triangles(i) for i in range(4)]
    assert 49000<=triangles[0]<=50000 and all(triangles[i]>triangles[i+1]>0 for i in range(3))
    slots=mesh.get_editor_property('static_materials');used=[]
    for s in slots:
        name=str(s.get_editor_property('imported_material_slot_name'));used.append(name)
        assert s.get_editor_property('material_interface').get_path_name()==f.DEST+'/Materials/'+name+'.'+name
    assert set(used)=={m['name'] for m in spec['materials']}
    checked=f.check_placements(by,mesh,plan)
    assert all(row['label'] not in by for row in plan['placements'])
    spawned=[];saved=False
    r['initial_validation_error']=r.pop('error')
    r.update(import_stage='validated_geometry',mesh=f.MESH_PATH,local_bounds_cm=local,lod_triangles=triangles,material_slots=used,geometry=checked)
    try:
        with unreal.ScopedEditorTransaction('Place eight staffed forklifts in floor storage'):
            for row in plan['placements']:
                a=f.A.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*row['position_cm']),unreal.Rotator(yaw=row['yaw_deg']))
                assert a;spawned.append(a);a.set_actor_label(row['label']);a.set_folder_path('GHS_Normal/Vehicles/MannedForklifts')
                a.tags=[unreal.Name('NormalWarehouseMannedForklift'),unreal.Name('TwinId='+row['label']),unreal.Name('FloorStorageWork'),unreal.Name('ModelScale=1to1')]
                c=a.static_mesh_component;c.set_static_mesh(mesh);c.set_mobility(unreal.ComponentMobility.MOVABLE)
                c.set_collision_profile_name('NoCollision');c.set_editor_property('receives_decals',False);c.set_editor_property('cast_shadow',True)
        after=f.util.labels();snap=f.snapshot(after)
        assert len(after)==len(before)+8
        assert all(snap[n]==s for n,s in before.items())
        assert all(a.get_attach_parent_actor() is None for a in spawned)
        assert f.L.save_current_level();saved=True
        old=f.util.read(backup/'content_before.json');new=f.util.content_hashes()
        changed=[p for p,h in old.items() if new[p]!=h];assert changed==[f.MAP_FILE],changed
        newfiles=sorted(set(new)-set(old));assert all(p.startswith('Content/GHSNormalWarehouse/MannedForklift/') for p in newfiles)
        f.util.write(backup/'live_after.json',snap)
        r.update(success=True,import_stage='saved',actor_count_after=len(after),actor_labels=[a.get_actor_label() for a in spawned],independent_actors=True,
            scale=[1,1,1],original_actors_unchanged=True,changed_content=changed,new_content=newfiles,map_sha256=f.util.sha(f.ROOT/f.MAP_FILE))
        f.A.set_selected_level_actors([])
        p=spawned[1].get_actor_location()
        f.E.set_level_viewport_camera_info(unreal.Vector(p.x+650,p.y-800,520),unreal.Rotator(pitch=-22,yaw=126,roll=0))
        unreal.log('MANNED_FORKLIFT_FLEET_IMPORTED '+str(triangles)+' 8 independent vehicles')
    except Exception:
        r['error']=traceback.format_exc()
        if not saved:
            for a in spawned:f.A.destroy_actor(a)
        raise
    finally:f.util.write(f.REPORT,r)

if __name__=='__main__':run()
