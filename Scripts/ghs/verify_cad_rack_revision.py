"""Fresh-process verification of CAD rack geometry and both saved scene styles."""
import hashlib,json,sys,traceback
from datetime import datetime,timezone
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot
import verify_ue_scene as common
import verify_clearance_scene as clearance
from verify_normal_scene import check_column_closure
MAPS=['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse']
REPORT=ROOT/'Saved/GHS_CADRackVerification.json'
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
lib=unreal.EditorAssetLibrary
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def close(a,b,label,tol=1e-4):assert abs(a-b)<tol,(label,a,b)

def run():
    report=dict(success=False,created_utc=datetime.now(timezone.utc).isoformat(),maps=[],meshes=[],mode='Fresh saved-map reload; immutable checkpoint and exact CAD dimensions')
    try:
        change=read(ROOT/'Saved/GHS_CADRackRevision.json');assert change['success']
        checkpoint=read(change['checkpoint']);revision=change['revision']
        registry=read(ROOT/'SourceAssets/GHS/ue_scene_registry.json')
        other=read(ROOT/'SourceAssets/GHS_Normal/ue_scene_registry.json')
        assert registry['groups']==other['groups']==read(ROOT/'SourceAssets/GHS/Presentation/visual_layout.json')['groups']
        assert registry['individuals']==other['individuals'] and registry['cad_rack_revision']==revision
        assert registry['wall_height_profile']==read(ROOT/'SourceAssets/GHS/wall_height_profile.json')
        assert revision['building_display_height_m']==9.6
        for relative,entry in change['changed_files'].items():
            assert sha(entry['backup'])==entry['before_sha256'] and sha(ROOT/relative)==entry['after_sha256'],relative
        for relative,digest in checkpoint['content_hashes'].items():
            expected=change['changed_files'].get(relative,{}).get('after_sha256',digest)
            assert sha(ROOT/relative)==expected,'Unrelated asset changed: '+relative
        for relative,digest in change['new_assets'].items():assert sha(ROOT/relative)==digest,relative
        actual_new={p.relative_to(ROOT).as_posix() for p in (ROOT/'Content').rglob('*.uasset') if p.relative_to(ROOT).as_posix() not in checkpoint['content_hashes']}
        assert actual_new==set(change['new_assets'])
        for relative,entry in checkpoint['files'].items():
            if relative.startswith('Saved/') and relative not in change['changed_files']:
                assert sha(ROOT/relative)==entry['sha256'],'Historical report changed: '+relative
        source=ROOT/'SourceAssets/GHS/RackSpecs'
        assert sha(source/'cad_elevation_specs.json')==revision['specs_sha256']
        assert sha(source/'cad_plan_mapping.json')==revision['mapping_sha256']
        assert sha(source/'Models/cad_rack_models.json')==revision['models_sha256']
        mapping=read(source/'cad_plan_mapping.json');specs=read(source/'cad_elevation_specs.json')
        assert sha(specs['source'])==specs['source_sha256'],'CAD source changed'
        solid=read(ROOT/'Saved/GHS_CADRackSolidAudit.json');assert solid['success'],solid
        assert solid['input_sha256']['mapping']==revision['mapping_sha256']
        assert solid['input_sha256']['models']==revision['models_sha256']
        assert solid['column_height_m']==revision['building_display_height_m'] and solid['rack_floor_offset_m']==0
        report['solid_audit']=solid.get('summary',{'status':solid.get('status')})
        models=read(source/'Models/cad_rack_models.json')['meshes']
        model_by={m['name']:m for m in models};model_keys={m['mapping_key']:m for m in models}
        imported=read(ROOT/'Saved/GHS_CADRackImport.json');assert imported['success']
        assert imported['model_manifest_sha256']==revision['models_sha256']
        import_by={m['name']:m for m in imported['meshes']}
        unreal.load_module('StaticMeshEditor');mesh_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        for model in models:
            assert sha(model['fbx'])==model['fbx_sha256']
            asset=lib.load_asset('/Game/GHSDigitalTwin/Meshes/'+model['name']);assert asset
            assert mesh_editor.get_lod_count(asset)==4
            assert asset.get_num_triangles(0)==model['triangles'],model['name']+' LOD0 triangle mismatch'
            bounds=asset.get_bounds();expected=model['bounds_m']
            center=[(a+b)*50 for a,b in expected];center[1]*=-1;extent=[(b-a)*50 for a,b in expected]
            common.compare(common.xyz(bounds.origin),center,.15,model['name']+' center')
            common.compare(common.xyz(bounds.box_extent),extent,.15,model['name']+' extent')
            code=model.get('spec_type',model.get('code'));spec=specs['types'][code]
            layout=spec['bridge_variant'] if model['pass_variant'] else spec
            common.compare(model['beam_top_z_m'],layout['beam_top_z_m'],1e-5,model['name']+' CAD beams')
            common.compare(model['cargo_base_z_m'],layout['cargo_base_z_m'],1e-5,model['name']+' CAD storage levels')
            close(model['upright_height_m'],layout.get('upright_height_m',spec['upright_height_m']),model['name']+' CAD height')
            # Narrow column-clearance segments intentionally contain no pallet or cargo;
            # FBX omits their unused material slots rather than adding empty sections.
            expected_roles=model['slot_roles'] if model['cargo_center_x_m'] else ['Upright','Beam','Braces','Detail']
            actual_roles=[str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1] for s in asset.get_editor_property('static_materials')]
            assert actual_roles==expected_roles==import_by[model['name']]['roles'],model['name']+' material roles'
            report['meshes'].append(dict(name=model['name'],beam_top_z_m=model['beam_top_z_m'],storage_levels=len(model['cargo_base_z_m']),
                upright_height_m=model['upright_height_m'],frame_width_m=model['frame_width_m'],loaded_width_fixed=True,lods=4))
        groups={g['actor']:g for g in registry['groups']};scope=set(revision['changed_groups'])|set(revision['retired_groups'])|{'CAM_GHS_RackAisles'}
        mapped={r['instance_id']:r for r in mapping['assignments']+mapping['additional_pass_racks']}
        for scene in MAPS:
            assert levels.load_level(scene);by={a.get_actor_label():a for a in actors.get_all_level_actors()}
            before=read(change['preserved_snapshots'][scene]);after=snapshot(by)
            for name,state in before.items():
                if name not in scope:assert after.get(name)==state,scene+' unrelated actor: '+name
            assert set(after)==(set(before)-set(revision['retired_groups']))|(set(revision['changed_groups'])-set(before))
            found={n for n,a in by.items() if a.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)}
            assert found==set(groups)
            components={};boxes={};rack_ids=set();instances=0;material_readback={}
            for name,g in groups.items():
                c=by[name].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent);components[name]=c
                assert c.get_instance_count()==g['count']==len(g['instances']);instances+=g['count']
                mesh=c.get_editor_property('static_mesh');assert mesh.get_path_name()==common.expected_mesh_path(g['mesh'])
                for i,row in enumerate(g['instances']):
                    t=c.get_instance_transform(i,world_space=True);common.check_transform(t,row,name+' '+str(i))
                    if name in {'GHS_CAD_Columns','GHS_ColumnBases','GHS_ColumnEdgeOutlines'}:boxes[row['id']]=clearance.actual_box(t,mesh.get_bounds())
                    if name.startswith('GHS_CAD_Rack_'):
                        assert row['id'] not in rack_ids;rack_ids.add(row['id']);m=mapped[row['id']]
                        assert row['scale']==[1.,1.,1.] and row['rack_spec_type']==m['spec_type'] and row['rack_pass_variant']==m['pass_variant']
                        common.compare(row['position_m'],[*m['position_m'],0.0],1e-5,row['id']+' CAD center')
                        close(row['rotation_deg'],m['rotation_deg']+90,row['id']+' orientation')
                        assert model_keys[row['mapping_key']]['name']==g['mesh']
                        close(mesh.get_bounds().box_extent.z*.02,model_by[g['mesh']]['upright_height_m'],row['id']+' world height',.003)
                if g['mesh'] in import_by:
                    expected=import_by[g['mesh']]['normal_materials' if scene==MAPS[1] else 'blue_materials']
                    actual=[c.get_material(i).get_path_name().split('.')[0] for i in range(c.get_num_materials())]
                    assert actual==[p.split('.')[0] for p in expected],name+' palette mismatch';material_readback[name]=actual
            assert rack_ids==set(mapped) and len(rack_ids)==1639
            assert groups['GHS_CAD_DockDoors']['count']==87
            check_column_closure(groups,components,boxes)
            for name in ['GHS_CAD_WallFaces','GHS_CAD_WallSections','GHS_CAD_WallEdges']:
                c=components[name];b=c.get_editor_property('static_mesh').get_bounds();t=c.get_instance_transform(0,world_space=True)
                top=(t.translation.z+(b.origin.z+b.box_extent.z)*t.scale3d.z)/100
                close(top,9.6005 if name.endswith('Edges') else 9.6,name+' wall top',.002)
            for row in groups['GHS_CAD_Columns']['instances']:close(boxes[row['id']].zmax,9.6,row['id']+' column top',.002)
            assert len([a for a in by.values() if a.get_component_by_class(unreal.DecalComponent)])==40
            assert len([a for a in by.values() if isinstance(a,unreal.DirectionalLight)])==1
            assert len([a for a in by.values() if isinstance(a,unreal.SkyLight)])==1
            report['maps'].append(dict(map=scene,actors=len(by),hism_groups=len(groups),instances=instances,racks=1639,loading_doors=87,
                type_counts=revision['type_counts'],wall_and_column_height_m=9.6,unchanged_actor_count=len(before)-len(scope&set(before)),
                materials=material_readback,all_cad_centers_and_layer_heights_verified=True,all_column_outlines_closed=True,
                agv_fx_unchanged=40,unrelated_actor_state_unchanged=True))
        for relative,entry in change['changed_files'].items():assert sha(ROOT/relative)==entry['after_sha256'],relative+' verification wrote file'
        report.update(success=True,source_cad_sha256=specs['source_sha256'],type_catalogue=list(specs['types']),
            unused_catalogue_specs=mapping['unused_specs'],level_saved=False,assets_saved=False,assumptions=revision['assumptions'])
        unreal.log('GHS_CAD_RACK_VERIFIED '+str(len(report['maps']))+' maps')
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':run()
