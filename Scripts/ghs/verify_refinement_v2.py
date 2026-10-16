"""Fresh-process read-only verification of both saved GHS Refinement V2 maps.

This script never saves a level or asset and only writes its new verification
report. Historical verification modules are imported for pure helpers only.
"""
import collections
import copy
import hashlib
import json
import math
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

ROOT=Path(r'D:\UEPro\Test')
SRC=ROOT/'SourceAssets/GHS/RefinementV2'
REPORT=ROOT/'Saved/GHS_RefinementV2Verification.json'
MAPS=['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse']
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot
import verify_ue_scene as common
import verify_clearance_scene as clearance
from verify_normal_scene import check_column_closure


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(actual,expected,label,tolerance=1e-4):
    assert math.isfinite(actual) and abs(actual-expected)<=tolerance,(label,actual,expected)


def angle_close(actual,expected,label,tolerance=.02):
    delta=abs((actual-expected+180)%360-180)
    assert delta<=tolerance,(label,actual,expected,delta)


def normalized_path(path):
    return path.split('.')[0]


def saved_content_state():
    return {p.relative_to(ROOT).as_posix():sha(p)
            for p in (ROOT/'Content').rglob('*') if p.is_file()}


def run():
    report=dict(success=False,created_utc=datetime.now(timezone.utc).isoformat(),
                mode='Fresh UE process; load saved maps; never save levels or assets',
                current_stage='read_application_evidence',maps=[],meshes=[])
    try:
        change=read(ROOT/'Saved/GHS_RefinementV2.json')
        assert change['success'],'V2 apply has not successfully completed'
        checkpoint=read(change['checkpoint']);assert checkpoint['success']
        imported=read(ROOT/'Saved/GHS_RefinementV2Import.json');assert imported['success']
        assert sha(ROOT/'Saved/GHS_RefinementV2Import.json')==change['import_sha256']
        staged=read(SRC/'revised_registry.json')
        registry=read(ROOT/'SourceAssets/GHS/ue_scene_registry.json')
        normal=read(ROOT/'SourceAssets/GHS_Normal/ue_scene_registry.json')
        visual=read(ROOT/'SourceAssets/GHS/Presentation/visual_layout.json')
        revision=change['revision']
        assert revision==staged['refinement_v2']==registry['refinement_v2']==normal['refinement_v2']==visual['refinement_v2']
        assert registry==staged==visual,'Live blue/presentation registry differs from staged V2'
        expected_normal=copy.deepcopy(staged)
        expected_normal['map']=MAPS[1]
        expected_normal['presentation']['expected_actor_count']+=2
        assert normal==expected_normal
        assert registry['map']==MAPS[0] and normal['map']==MAPS[1]
        assert registry['wall_height_profile']==read(ROOT/'SourceAssets/GHS/wall_height_profile.json')
        assert registry['wall_height_profile']['wall_height_m']==registry['wall_height_profile']['column_height_m']==9.6
        assert revision['rack_count']==1629 and revision['cargo_count']==7530
        assert revision['truck_count']==revision['door_count']==87
        assert revision['closed_exterior'] and not revision['roof'] and revision['door_open_fraction']==.5
        assert not registry['blocked_storage']
        assert sum(len(b['slot_ids']) for b in registry['presentation']['cargo_blocks'])==7530
        assert sum(z['active_slots'] for z in registry['presentation']['zone_variant_statistics'])==7530
        groups={g['actor']:g for g in registry['groups']}
        assert len(groups)==len(registry['groups'])==27
        expected_instances=sum(g['count'] for g in groups.values())
        assert expected_instances==registry['presentation']['expected_instance_count']==13849
        assert registry['presentation']['expected_hism_group_count']==27
        changed=set(revision['changed_groups']);retired=set(revision['retired_groups']);allowed=changed|retired
        assert not set(groups)&retired
        assert not ({'GHS_CAD_Columns','GHS_ColumnBases','GHS_ColumnEdgeOutlines'}&allowed)
        old_registry=read(checkpoint['files']['SourceAssets/GHS/ue_scene_registry.json']['backup'])
        old_groups={g['actor']:g for g in old_registry['groups']}
        assert registry['individuals']==old_registry['individuals']
        for label,g in groups.items():
            if label not in changed:assert g==old_groups[label],label+' unrelated registry group'

        report['current_stage']='verify_saved_files_and_source_geometry'
        assert set(change['changed_files'])=={
            'Content/Maps/GHS_CAD_DigitalTwin.umap','Content/Maps/GHS_CAD_NormalWarehouse.umap',
            'SourceAssets/GHS/ue_scene_registry.json','SourceAssets/GHS_Normal/ue_scene_registry.json',
            'SourceAssets/GHS/Presentation/visual_layout.json','SourceAssets/GHS/wall_height_profile.json'}
        for relative,entry in change['changed_files'].items():
            assert sha(entry['backup'])==entry['before_sha256']==checkpoint['files'][relative]['sha256'],relative+' backup changed'
            assert sha(ROOT/relative)==entry['after_sha256'],relative+' saved result changed'
        protected_reports={}
        for relative,entry in checkpoint['files'].items():
            if relative.startswith('Saved/') and relative not in change['changed_files']:
                assert sha(ROOT/relative)==entry['sha256'],'Historical report changed: '+relative
                protected_reports[relative]=entry['sha256']
        disk_before=saved_content_state()
        for relative,digest in checkpoint['content_hashes'].items():
            expected=change['changed_files'].get(relative,{}).get('after_sha256',digest)
            assert disk_before.get(relative)==expected,'Existing Content changed: '+relative
        actual_new={p:h for p,h in disk_before.items() if p not in checkpoint['content_hashes']}
        assert actual_new==change['new_assets'],'Saved V2 Content inventory/hash mismatch'
        assert len(actual_new)==52 and all(p.startswith('Content/GHSRefinementV2/') for p in actual_new)
        for relative,digest in revision['source_sha256'].items():
            assert sha(SRC/relative)==digest,'V2 source changed: '+relative
        for relative,digest in imported['manifests'].items():
            assert sha(SRC/relative)==digest,'Imported manifest changed: '+relative
        geometry=read(SRC/'Envelope/scene_geometry_audit.json')
        assert sha(SRC/'Envelope/scene_geometry_audit.json')==change['geometry_audit_sha256']
        assert geometry['status']=='passed'
        gs=geometry['summary']
        assert gs['final_v2_rack_asset_binding_verified'] and not gs['rack_mesh_manifest_fallback_used']
        for key in ['truck_obb_collision_count','trucks_inside_building_count','truck_wall_collision_count',
                    'rack_wall_component_collision_count','rack_outside_building_count','rack_missing_model_count',
                    'rack_model_fbx_hash_issue_count','groundcargo_wall_collision_count',
                    'groundcargo_outside_building_count','groundcargo_unknown_variant_count']:
            assert gs[key]==0,(key,gs[key])
        assert gs['rack_count']==1629 and gs['groundcargo_count']==7530 and gs['truck_count']==87
        for entry in geometry['source_files'].values():
            assert sha(entry['path'])==entry['sha256'],entry['path']+' geometry source changed'
        envelope=read(SRC/'Envelope/envelope_v2.json')
        ev=envelope['verification']
        for key in ['main_building_outline_closed','main_building_outline_valid','top_perimeter_ring_continuous',
                    'all_87_door_openings_clear','all_87_door_lintels_present','roofless','no_roof_cap_created',
                    'door_both_normals_panel_checked','door_half_open_geometric_check']:
            assert ev[key],key
        assert ev['wall_height_m']==9.6 and ev['preserved_existing_wall_outside_door_openings_area_loss_m2']==0
        assert envelope['door']['opening_fraction']==.5 and envelope['door']['clear_opening_height_m']==2.1
        assert not envelope['door']['full_size_black_backplate']
        layout=read(SRC/'Layout/rack_spacing.json');layout_validation=read(SRC/'Layout/rack_spacing_validation.json')
        assert layout_validation['passed'] and layout_validation['full_envelope_collisions']==0
        assert layout['summary']['restored_ground_slots']==122 and layout['summary']['unresolved_ground_slots']==0
        assert layout['summary']['maximum_row_displacement_m']<1 and layout['summary']['maximum_ground_displacement_m']<1
        mapped={r['instance_id']:r for r in layout['racks']}
        floor_layout={r['id']:r for r in layout['groundcargo']}
        assert len(mapped)==1629 and len(floor_layout)==7530
        rack_manifest=read(SRC/'Racks/refined_rack_cargo.json')
        assert rack_manifest['verification']['all_frames_unchanged'] and rack_manifest['verification']['all_pallets_unchanged']
        assert rack_manifest['verification']['minimum_stack_top_clearance_m']>0
        specs={m['name']:m for relative in imported['manifests'] for m in read(SRC/relative)['meshes']}
        imports={m['name']:m for m in imported['meshes']}
        assert set(specs)==set(imports) and len(specs)==38
        by_key={m['mapping_key']:m for m in rack_manifest['meshes']}
        targets=read(SRC/'Envelope/door_docking_targets.json')['doors']
        dock_targets={d['instance_id']:d for d in targets}
        assert len(targets)==len(dock_targets)==87 and len({d['dock_number'] for d in targets})==87
        truck=read(SRC/'Trucks/dock_truck_v2.json')['meshes'][0]
        assert truck['rear_origin_m']==[0,0,0] and truck['forward_axis']=='+X'
        report.update(source_geometry=gs,spacing_summary=layout['summary'],
                      protected_historical_reports=len(protected_reports),new_asset_count=len(actual_new))

        report['current_stage']='verify_persisted_meshes'
        lib=unreal.EditorAssetLibrary
        unreal.load_module('StaticMeshEditor')
        mesh_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        for name,spec in specs.items():
            entry=imports[name]
            assert sha(spec['fbx'])==entry['fbx_sha256'],name+' imported FBX hash'
            if spec.get('fbx_sha256'):assert entry['fbx_sha256']==spec['fbx_sha256'],name+' source FBX hash'
            asset=lib.load_asset(normalized_path(entry['path']));assert asset,name
            assert normalized_path(asset.get_path_name())=='/Game/GHSRefinementV2/Meshes/'+name
            lod_count=mesh_editor.get_lod_count(asset)
            assert lod_count==(1 if 'Exterior' in name else 4),name+' LOD count'
            triangles=[asset.get_num_triangles(i) for i in range(lod_count)]
            assert triangles==entry['lod_triangles'],name+' persisted LOD triangles'
            if 'triangles' in spec:assert triangles[0]==spec['triangles'],name+' source LOD0 triangle count'
            bounds=asset.get_bounds();expected=spec['bounds_m']
            center=[(a+b)*50 for a,b in expected];center[1]*=-1
            common.compare(common.xyz(bounds.origin),center,.15,name+' local bounds center')
            common.compare(common.xyz(bounds.box_extent),[(b-a)*50 for a,b in expected],.15,name+' local bounds extent')
            slots=asset.get_editor_property('static_materials')
            roles=[str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1] for s in slots]
            roles=[{'WallVolume':'Faces','WallSection':'Sections','WallTrim':'Edges'}.get(role,role) for role in roles]
            assert roles==entry['roles'],name+' persisted material roles'
            expected_roles=spec['slot_roles']
            if spec.get('library_only_narrow_empty_variant'):
                expected_roles=[r for r in expected_roles if r not in {'Pallet','Cargo','CargoEdges'}]
            assert roles==expected_roles,(name,'source material roles',roles,expected_roles)
            blue=[normalized_path(asset.get_material(i).get_path_name()) for i in range(len(slots))]
            assert blue==list(map(normalized_path,entry['palettes']['Blue'])),name+' saved mesh default palette'
            report['meshes'].append(dict(name=name,lods=lod_count,triangles=triangles,roles=roles,bounds_verified=True))

        actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        map_reports={r['map']:r for r in change['maps']}
        assert set(map_reports)==set(MAPS)
        old_floor={r['id']:r for g in old_registry['groups'] if g['actor'].startswith('GHS_CAD_PalletCargo') for r in g['instances']}
        for scene in MAPS:
            report['current_stage']='verify_saved_map '+scene
            assert levels.load_level(scene),scene
            all_actors=actors.get_all_level_actors();by={a.get_actor_label():a for a in all_actors}
            assert len(by)==len(all_actors),scene+' duplicate actor labels'
            before=read(change['preserved_snapshots'][scene]);after=snapshot(by)
            assert len(by)==map_reports[scene]['actor_count']
            assert set(after)==((set(before)-retired)|(changed-set(before))),scene+' actor inventory'
            for label,state in before.items():
                if label not in allowed:assert after.get(label)==state,scene+' non-target actor changed: '+label
            found={label for label,a in by.items() if a.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)}
            assert found==set(groups) and len(found)==27,scene+' HISM group inventory'
            style='Blue' if scene==MAPS[0] else 'Normal'
            components={};boxes={};rack_ids=set();floor_ids=set();door_ids=set();truck_door_ids=set()
            instances=0;restored_floor=0;per_group=[];truck_checks=[]
            for label,g in groups.items():
                actor=by[label];cs=actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                assert len(cs)==1,label+' expected one HISM'
                c=cs[0];components[label]=c
                if label in changed:
                    assert c.get_editor_property('visible') and not c.get_editor_property('hidden_in_game'),label+' hidden component'
                else:
                    # Context grid is intentionally hidden in the normal palette; preserve its prior state.
                    assert after[label]['mesh_properties']==before[label]['mesh_properties']
                assert c.get_instance_count()==g['count']==len(g['instances']),label+' instance count'
                instances+=g['count']
                mesh=c.get_editor_property('static_mesh');assert mesh,label+' null mesh'
                expected_mesh=imports[g['mesh']]['path'] if g['mesh'] in imports else common.expected_mesh_path(g['mesh'])
                assert mesh.get_path_name()==expected_mesh,(label,'mesh',mesh.get_path_name(),expected_mesh)
                materials=common.check_materials(c,label)
                if label=='GHS_V2_WaitingDockTrucks':
                    for i in range(c.get_num_materials()):assert c.get_material(i).get_editor_property('used_with_instanced_static_meshes')
                expected_materials=imports[g['mesh']]['palettes'][style] if g['mesh'] in imports else before[label]['materials']
                assert list(map(normalized_path,materials))==list(map(normalized_path,expected_materials)),label+' material palette'
                largest=dict(position_cm=0.,scale=0.,yaw_deg=0.)
                for i,row in enumerate(g['instances']):
                    t=c.get_instance_transform(i,world_space=True)
                    errors=common.check_transform(t,row,label+' '+str(i)+' '+row['id'])
                    for key,value in errors.items():largest[key]=max(largest[key],value)
                    if label in {'GHS_CAD_Columns','GHS_ColumnBases','GHS_ColumnEdgeOutlines'}:
                        boxes[row['id']]=clearance.actual_box(t,mesh.get_bounds())
                    if label.startswith('GHS_V2_Rack_'):
                        assert row['id'] not in rack_ids;rack_ids.add(row['id']);r=mapped[row['id']]
                        assert row['scale']==[1,1,1]
                        assert row['rack_spec_type']==r['spec_type'] and row['rack_pass_variant']==r['pass_variant']
                        assert row['parent_cad_id']==r['parent_cad_id'] and row['mapping_key']==r['mapping_key']
                        assert by_key[row['mapping_key']]['name']==g['mesh']
                        common.compare(row['position_m'],r['position_m']+[0],1e-6,row['id']+' layout center')
                        angle_close(row['rotation_deg'],r['rotation_deg']+90,row['id']+' CAD rack orientation',1e-5)
                    elif label.startswith('GHS_CAD_PalletCargo'):
                        assert row['id'] not in floor_ids;floor_ids.add(row['id']);f=floor_layout[row['id']]
                        actual=clearance.actual_box(t,mesh.get_bounds())
                        common.compare([actual.x,actual.y],f['position_m'],.0006,row['id']+' floor physical center')
                        # The retained bevelled floor-load meshes are up to 1.61mm inside their nominal CAD envelope.
                        common.compare([actual.hx*2,actual.hy*2],f['size_m'],.002,row['id']+' floor full-size dimensions')
                        assert row['v2_restored']==f['was_blocked'];restored_floor+=int(row['v2_restored'])
                        if row['id'] in old_floor:assert row['scale']==old_floor[row['id']]['scale'],row['id']+' stretched existing cargo'
                    elif label=='GHS_CAD_DockDoors':
                        assert row['id'] not in door_ids;door_ids.add(row['id']);d=dock_targets[row['id']]
                        common.compare(row['position_m'],d['door_center_cad_m'],.00002,row['id']+' dock anchor')
                        angle_close(row['rotation_deg'],d['door_rotation_cad_deg'],row['id']+' dock yaw')
                        assert row['scale']==[1,1,1] and row['open_fraction']==.5
                    elif label=='GHS_V2_WaitingDockTrucks':
                        d=dock_targets[row['door_id']]
                        assert row['door_id'] not in truck_door_ids;truck_door_ids.add(row['door_id'])
                        assert row['dock_number']==d['dock_number'] and row['scale']==[1,1,1]
                        actual_cad=[t.translation.x/100,-t.translation.y/100,t.translation.z/100]
                        expected=d['truck_rear_dock_target_cad_m'][:2]+[-truck['bounds_m'][2][0]]
                        common.compare(actual_cad,expected,.0006,row['id']+' rear dock target')
                        actual_yaw=-float(t.rotation.rotator().yaw)
                        angle_close(actual_yaw,d['truck_forward_cad_yaw_deg'],row['id']+' outward truck yaw')
                        forward=[math.cos(math.radians(actual_yaw)),math.sin(math.radians(actual_yaw))]
                        common.compare(forward,d['outward_unit_normal_cad'][:2],.0004,row['id']+' forward away from building')
                        delta=[actual_cad[k]-d['door_center_cad_m'][k] for k in range(2)]
                        normal=d['outward_unit_normal_cad']
                        close(sum(delta[k]*normal[k] for k in range(2)),d['rear_distance_from_door_m'],row['id']+' rear offset',.0006)
                        close(delta[0]*normal[1]-delta[1]*normal[0],0,row['id']+' rear lateral alignment',.0006)
                        box=clearance.actual_box(t,mesh.get_bounds());close(box.zmin,0,row['id']+' wheels grounded',.0015)
                        truck_checks.append(dict(id=row['id'],door_id=row['door_id'],rear_cad_m=actual_cad,yaw_cad_deg=actual_yaw,ground_z_m=box.zmin))
                per_group.append(dict(actor=label,mesh=mesh.get_path_name(),count=g['count'],materials=materials,maximum_transform_error=largest))
            assert instances==expected_instances
            assert rack_ids==set(mapped) and len(rack_ids)==1629
            assert floor_ids==set(floor_layout) and len(floor_ids)==7530 and restored_floor==122
            assert door_ids==truck_door_ids==set(dock_targets) and len(truck_checks)==87
            assert groups['GHS_CAD_Columns']['count']==groups['GHS_ColumnBases']['count']==170
            assert groups['GHS_ColumnEdgeOutlines']['count']==2040
            check_column_closure(groups,components,boxes)
            for name in ['GHS_CAD_WallFaces','GHS_CAD_WallSections','GHS_CAD_WallEdges']:
                c=components[name];b=c.get_editor_property('static_mesh').get_bounds();t=c.get_instance_transform(0,world_space=True)
                close((t.translation.z+(b.origin.z+b.box_extent.z)*t.scale3d.z)/100,
                      9.6005 if name.endswith('Edges') else 9.6,name+' wall top',.002)
                common.compare(common.xyz(t.scale3d),[1,1,1],.00001,name+' unscaled 9.6m wall')
            for row in groups['GHS_CAD_Columns']['instances']:close(boxes[row['id']].zmax,9.6,row['id']+' preserved column top',.002)
            fx={label for label,a in by.items() if a.get_component_by_class(unreal.DecalComponent)}
            cameras={label for label,a in by.items() if a.get_component_by_class(unreal.CameraComponent)}
            assert len(fx)==40 and cameras==common.CAMERAS and len(cameras)==6
            assert len([a for a in by.values() if isinstance(a,unreal.DirectionalLight)])==1
            assert len([a for a in by.values() if isinstance(a,unreal.SkyLight)])==1
            assert all(after[label]==before[label] for label in fx|cameras)
            for row in registry['individuals']:
                a=by[row['id']];common.check_transform(a.get_actor_transform(),row,row['id'])
                c=a.get_component_by_class(unreal.StaticMeshComponent)
                assert c and c.get_editor_property('static_mesh').get_path_name()==common.expected_mesh_path(row['mesh'])
                assert after[row['id']]==before[row['id']],row['id']+' individual state changed'
            report['maps'].append(dict(map=scene,actors=len(by),hism_groups=27,instances=instances,racks=1629,
                groundcargo=7530,restored_groundcargo=restored_floor,doors=87,trucks=87,
                preserved_columns=170,closed_column_outlines=2040,wall_height_m=9.6,
                preserved_fx=40,preserved_cameras=6,directional_lights=1,skylights=1,
                unchanged_actor_count=len(before)-len(set(before)&allowed),groups=per_group,
                truck_rear_alignment=truck_checks,all_instance_transforms_verified=True,all_palettes_verified=True))

        report['current_stage']='confirm_verification_did_not_write_content_or_history'
        assert saved_content_state()==disk_before,'Verification modified saved Content'
        for relative,digest in protected_reports.items():assert sha(ROOT/relative)==digest,'Verification modified historical report: '+relative
        for relative,entry in change['changed_files'].items():assert sha(ROOT/relative)==entry['after_sha256'],'Verification modified saved result: '+relative
        report.update(success=True,current_stage='complete',completed_utc=datetime.now(timezone.utc).isoformat(),
                      level_saved=False,assets_saved=False,historical_reports_saved=False,
                      unrelated_content_unchanged=True,source_geometry_bound_to_imported_meshes=True)
        unreal.log('GHS_REFINEMENT_V2_VERIFIED '+str(len(report['maps']))+' maps; 1629 racks; 7530 floor loads; 87 trucks per map')
    except Exception:
        report['error']=traceback.format_exc()
        unreal.log_error('GHS_REFINEMENT_V2_VERIFY_FAILED '+report['current_stage']+'\n'+report['error'])
        raise
    finally:
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    from cad_rack_revision_state import dispatch_truck_models_verification
    if not dispatch_truck_models_verification():
        run()
