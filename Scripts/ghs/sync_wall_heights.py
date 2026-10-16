"""Synchronize only six wall instances, with backups and fresh-reload proof."""
import copy
import hashlib
import json
import re
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT/'Scripts/ghs'))
from wall_height_profile import PROFILE, WALLS, row_for, synchronize_registry, projected_geometry
import verify_ue_scene as common

REPORT = ROOT/'Saved/GHS_WallHeightSync.json'
REGISTRIES = ['SourceAssets/GHS/ue_scene_registry.json', 'SourceAssets/GHS_Normal/ue_scene_registry.json',
              'SourceAssets/GHS/Presentation/visual_layout.json']
MAP_FILES = ['Content/Maps/'+m.rsplit('/',1)[-1]+'.umap' for m in PROFILE['maps']]
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path, data): Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def xyz(v): return [round(float(v.x),6), round(float(v.y),6), round(float(v.z),6)]
def props(obj, names): return {name:str(obj.get_editor_property(name)) for name in names}


def normalized(value):
    # UE struct repr contains process-local addresses; exclude no field values.
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    if isinstance(value,list):return [normalized(v) for v in value]
    if isinstance(value,str):return re.sub(r'0x[0-9A-Fa-f]+','ADDRESS',value)
    return value


def transform(t):
    r=t.rotation.rotator()
    return dict(position_cm=xyz(t.translation),scale=xyz(t.scale3d),
                rotation_deg=[round(float(x),6) for x in [r.pitch,r.yaw,r.roll]])


def load(path):
    assert LEVELS.load_level(path), path
    return {a.get_actor_label():a for a in ACTORS.get_all_level_actors()}


def snapshot(labels):
    result={}
    for label,a in labels.items():
        item=dict(actor_class=a.get_class().get_path_name(),transform=transform(a.get_actor_transform()),
                  tags=sorted(str(t) for t in a.tags),folder=str(a.get_folder_path()),hidden=a.get_editor_property('hidden'))
        c=a.get_component_by_class(unreal.StaticMeshComponent)
        if c and not a.get_component_by_class(unreal.CameraComponent):
            mesh=c.get_editor_property('static_mesh')
            item['mesh']=mesh.get_path_name() if mesh else None
            item['materials']=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())]
            item['mesh_properties']=props(c,['relative_location','relative_rotation','relative_scale3d','visible','hidden_in_game','cast_shadow','mobility'])
            if isinstance(c,unreal.InstancedStaticMeshComponent):
                item['instances']=[transform(c.get_instance_transform(i,world_space=True)) for i in range(c.get_instance_count())]
        c=a.get_component_by_class(unreal.DecalComponent)
        if c:
            item['decal']=dict(material=c.get_decal_material().get_path_name(),properties=props(c,['decal_size','visible','hidden_in_game','relative_location','relative_rotation','relative_scale3d']))
        c=a.get_component_by_class(unreal.CameraComponent)
        if c:item['camera']=props(c,['field_of_view','projection_mode'])
        c=a.get_component_by_class(unreal.TextRenderComponent)
        if c:item['text']=props(c,['text','text_render_color','world_size'])
        c=a.get_component_by_class(unreal.DirectionalLightComponent)
        if c:item['light']=props(c,['intensity','light_color','cast_shadows','light_source_angle'])
        c=a.get_component_by_class(unreal.SkyLightComponent)
        if c:item['sky']=props(c,['intensity','light_color','cast_shadows','cubemap','real_time_capture','source_type'])
        if isinstance(a,unreal.PostProcessVolume):item['postprocess']=str(a.get_editor_property('settings'))
        result[label]=item
    return normalized(result)


def extents(labels):
    result={}
    for label in WALLS+('GHS_CAD_Columns','GHS_CAD_Racks','GHS_ChargingSupportPanels'):
        c=labels[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        b=c.get_editor_property('static_mesh').get_bounds()
        zs=[]
        for i in range(c.get_instance_count()):
            t=c.get_instance_transform(i,world_space=True)
            zs.append([(t.translation.z+(b.origin.z-b.box_extent.z)*t.scale3d.z)/100,
                       (t.translation.z+(b.origin.z+b.box_extent.z)*t.scale3d.z)/100])
        result[label]=dict(count=len(zs),min_z_m=min(z[0] for z in zs),max_z_m=max(z[1] for z in zs),
                           heights_m=sorted({round(z[1]-z[0],5) for z in zs}))
    return result


def inspect():
    result={m:extents(load(m)) for m in PROFILE['maps']}
    write(ROOT/'Saved/GHS_WallHeightBefore.json',result)
    unreal.log('WALL_HEIGHT_BEFORE '+json.dumps(result))


def apply():
    assert not REPORT.exists(), 'Sync already exists; run verifier or review saved revision before applying again'
    backup=ROOT/'Saved/Backups'/('GHS_WallHeight_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True)
    report=dict(success=False,profile=PROFILE,backup_root=str(backup),file_changes={},maps=[])
    before_content={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}
    write(backup/'content_hashes.json',before_content)
    try:
        for relative in MAP_FILES+REGISTRIES:
            old=ROOT/relative;dest=backup/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,dest)
            report['file_changes'][relative]=dict(before_sha256=sha(old),backup_path=str(dest))
        # Preflight both saved levels and retain full actor/component snapshots.
        for index,m in enumerate(PROFILE['maps']):
            labels=load(m);before=snapshot(labels)
            assert len(labels)==[227,229][index]
            for label in WALLS:
                assert len(before[label]['instances'])==1
                common.check_transform(labels[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_instance_transform(0,world_space=True),dict(position_m=[0,0,0],rotation_deg=0,scale=[1,1,1]),label)
            write(backup/(m.rsplit('/',1)[-1]+'_before.json'),before)
        write(REPORT,report)
        for m in PROFILE['maps']:
            labels=load(m)
            for label in WALLS:
                c=labels[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                row=row_for(label)
                t=unreal.Transform(location=unreal.Vector(*[x*100 for x in row['position_m']]),rotation=unreal.Rotator(),scale=unreal.Vector(*row['scale']))
                assert c.update_instance_transform(0,t,world_space=True,mark_render_state_dirty=True,teleport=True),label
            assert LEVELS.save_current_level(),m
            report['maps'].append(dict(map=m,heights=extents(labels)))
        for relative in REGISTRIES:
            write(ROOT/relative,synchronize_registry(read(ROOT/relative)))
        for relative,item in report['file_changes'].items():item['after_sha256']=sha(ROOT/relative)
        changed=[relative for relative,digest in before_content.items() if sha(ROOT/relative)!=digest]
        assert set(changed)==set(MAP_FILES),changed
        report.update(success=True,changed_content=changed,unchanged_content_count=len(before_content)-len(changed),
                      source_meshes_and_materials_unchanged=True,completed_utc=datetime.now(timezone.utc).isoformat())
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:write(REPORT,report)
    unreal.log('WALL_HEIGHT_SYNC_SAVED '+json.dumps(dict(success=True,maps=PROFILE['maps'],wall_height_m=PROFILE['wall_height_m'])))


def verify():
    import verify_joined_walls as joined
    result=dict(success=False,maps=[],profile=PROFILE)
    try:
        change=read(REPORT);assert change['success'] and change['profile']==PROFILE
        backup=Path(change['backup_root'])
        before_content=read(backup/'content_hashes.json')
        for relative,digest in before_content.items():
            expected=change['file_changes'].get(relative,{}).get('after_sha256',digest)
            assert sha(ROOT/relative)==expected,relative
        assert set(change['file_changes'])==set(MAP_FILES+REGISTRIES)
        for relative,row in change['file_changes'].items():
            assert sha(row['backup_path'])==row['before_sha256'] and sha(ROOT/relative)==row['after_sha256'],relative
        a,b=[read(ROOT/r) for r in REGISTRIES[:2]]
        assert a['groups']==b['groups'] and a['individuals']==b['individuals']
        assert a['groups']==read(ROOT/REGISTRIES[2])['groups']
        for relative in REGISTRIES:
            expected=synchronize_registry(read(change['file_changes'][relative]['backup_path']))
            assert read(ROOT/relative)==expected,relative+' non-wall registry mutation'
        geometry=read(ROOT/'SourceAssets/GHS/joined_walls_geometry.json')
        projected=projected_geometry(geometry)
        cad=read(ROOT/'SourceAssets/GHS/cad_layout.json')
        rect_list=joined.wall_rectangles(cad);rectangles=joined.PolygonGrid(rect_list)
        expanded=joined.PolygonGrid(joined.wall_rectangles(cad,joined.TOLERANCE_M))
        union_area=sum(rectangles.outside_area(poly,{i for i in rectangles.candidates(poly) if i<index}) for index,poly in enumerate(rect_list))
        unreal.load_module('StaticMeshEditor')
        mesh_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        for m in PROFILE['maps']:
            labels=load(m);actual=snapshot(labels);before=normalized(read(backup/(m.rsplit('/',1)[-1]+'_before.json')))
            expected=copy.deepcopy(before)
            for label in WALLS:
                row=row_for(label)
                expected[label]['instances']=[dict(position_cm=[x*100 for x in row['position_m']],scale=row['scale'],rotation_deg=[0,0,0])]
            assert actual==expected,m+' unrelated actor, component, transform or style changed'
            measurements=extents(labels)
            assert abs(measurements['GHS_CAD_WallFaces']['max_z_m']-5.6)<.0001
            assert abs(measurements['GHS_CAD_WallFaces']['min_z_m'])<.0001
            assert abs(measurements['GHS_CAD_WallSections']['max_z_m']-5.6)<.0001
            assert abs(measurements['GHS_CAD_WallEdges']['max_z_m']-5.6005)<.0001
            proof=[]
            for label in WALLS:
                c=labels[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                t=c.get_instance_transform(0,world_space=True);common.check_transform(t,row_for(label),label)
                mesh=c.get_editor_property('static_mesh');triangles,metrics=joined.saved_mesh_triangles(mesh,t,mesh_editor)
                metrics.update(joined.compare_geometry(triangles,projected['meshes'][mesh.get_name()]))
                metrics.update(joined.validate_surfaces(mesh.get_name(),triangles,rectangles,expanded,union_area,projected['verification']))
                proof.append(dict(actor=label,**metrics))
            result['maps'].append(dict(map=m,heights=measurements,wall_geometry=proof,all_non_wall_state_unchanged=True))
        result.update(success=True,shared_geometry_and_layout_equal=True,material_and_lighting_preserved=True,
                      unchanged_content_count=change['unchanged_content_count'],door_gaps_and_wall_thickness_preserved=True,
                      created_utc=datetime.now(timezone.utc).isoformat())
    except Exception:
        result['error']=traceback.format_exc();raise
    finally:write(ROOT/'Saved/GHS_WallHeightVerification.json',result)
    unreal.log('WALL_HEIGHT_SYNC_VERIFIED '+json.dumps(dict(success=True,maps=2,height_m=5.6)))


if __name__=='__main__':apply()
