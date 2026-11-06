"""Scoped edits to the current MPR map, preserving the user's live baseline."""
from copy import deepcopy
import importlib,json,shutil,traceback
from pathlib import Path
import mpr_scene_patch_guard as g
from apply_mpr_site_round2 import legacy_fbx,package

ROOT=g.ROOT
FOLDERS={'remove':'city_road_removal_20261106','gap':'road_gap_20261106','solar':'solar_units_20261106'}

def manifest(mode):
    p=ROOT/'SourceAssets/MPR'/FOLDERS[mode]/'manifest.json'
    m=g.read(p);g.require(m['map']==g.MAP,'Wrong map')
    if mode=='solar':
        import mpr_solar_units as solar
        solar.source_contract()
    else:
        for row in m['meshes']:
            path=(ROOT/row['fbx']).resolve()
            g.require(path.is_relative_to(p.parent)and g.guard.sha(path)==row['sha256'],'Source mesh changed')
        for path,digest in m.get('source_hashes',{}).items():g.require(g.guard.sha(ROOT/path)==digest,'Old source changed')
        validation=g.read(p.parent/'validation.json');g.require(validation['success'],'Geometry validation failed')
        if mode=='remove':g.require(validation['manifest_sha256']==g.guard.sha(p),'Road deletion validation stale')
    return m

def meshes(snapshot):
    return {c['mesh'].split('.')[0]:(a,c)for a in snapshot['actors']for c in a['components']if c.get('mesh')}

def validate(before,after,mode,cmd=False):
    m=manifest(mode)
    a={r['guid']:g.normalize(r,commandlet_compat=cmd)for r in before['actors']}
    b={r['guid']:g.normalize(r,commandlet_compat=cmd)for r in after['actors']}
    expected=deepcopy(a);changed=[];deleted=[]
    if mode in ('remove','solar'):
        specs=m['mesh_mappings']if mode=='remove'else[dict(old_mesh=r['source_mesh'],new_mesh=m['namespace']+'/Meshes/'+r['name'])for r in m['meshes']]
        for spec in specs:
            pairs=[(r,c)for r in expected.values()for c in r['components']if c.get('mesh')==g.obj(spec['old_mesh'])]
            g.require(len(pairs)==1,'Expected unique original component')
            row,c=pairs[0];c['mesh']=g.obj(spec['new_mesh']);changed.append(row['guid'])
        if mode=='remove':
            for name in m['remove_mesh_names']:
                pairs=[r for r in expected.values()if any((c.get('mesh')or'').split('.')[-1]==name for c in r['components'])]
                g.require(len(pairs)==1 and len(pairs[0]['components'])==1,'Unsafe actor deletion')
                row=pairs[0];deleted.append(row['guid']);del expected[row['guid']]
        g.require(set(b)==set(expected),'Unexpected actor additions/deletions')
    else:
        new=set(b)-set(a);g.require(len(new)==1 and set(a)<=set(b),'Expected one road infill actor')
        row=b[next(iter(new))];cs=row['components'];spec=m['meshes'][0]
        g.require(row['label']==m['actor_label']and row['class']=='/Script/Engine.StaticMeshActor','Unexpected infill actor')
        g.require(not g.differences(row['transform'],m['transform'])and len(cs)==1,'Unexpected infill transform/components')
        g.require(cs[0]['mesh']==g.obj(m['namespace']+'/Meshes/'+spec['name'])and cs[0]['materials']==[g.obj(m['expected_effective_material'])], 'Infill mesh/material differs')
        g.require(not row['tick_enabled']and not row['collision_enabled'],'Infill behavior changed')
        g.require(not row['hidden']and cs[0]['visible']and not cs[0]['hidden_in_game'],'Infill visibility changed')
        g.require(cs[0]['class']=='/Script/Engine.StaticMeshComponent'and not g.differences(cs[0]['transform'],m['transform']), 'Infill local transform changed')
        g.require(cs[0]['collision_profile']=='NoCollision'and not cs[0]['cast_shadow'],'Infill render/collision policy changed')
        expected[row['guid']]=row;changed.append(row['guid'])
    errors=g.differences(expected,b)+g.differences(before['world_settings'],after['world_settings'])
    errors+=g.differences(g.normalized_coverage(before['world_actor_coverage'],commandlet_compat=cmd),g.normalized_coverage(after['world_actor_coverage'],commandlet_compat=cmd))
    g.require(not errors,'Out-of-scope changes: '+json.dumps(errors[:20]))
    return dict(success=True,before_actors=len(a),after_actors=len(b),changed=changed,deleted=deleted,
                unchanged_actors=len(a)-len(set(changed)&set(a))-len(deleted))

def content_check(before,mode):
    now=g.guard.content_hashes(ROOT);map_rel=g.MAP_FILE.relative_to(ROOT).as_posix()
    g.require(not [p for p,h in before.items()if p!=map_rel and now.get(p)!=h],'Existing shared asset modified')
    prefix='Content/'+manifest(mode)['namespace'].removeprefix('/Game/')+'/'
    additions={p:h for p,h in now.items()if p not in before}
    g.require(all(p.startswith(prefix)for p in additions),'New asset outside owned namespace')
    return dict(success=True,new_packages=additions,protected_packages=len(before)-1)

def apply_geometry(u,mode,before):
    m=manifest(mode);lookup=meshes(before);live={a.get_path_name():a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    import mpr_transport_cleanup as importer
    importer=importlib.reload(importer);importer.DEST=m['namespace'];importer.OWNER='mpr-'+FOLDERS[mode]
    created=[];targets=[]
    for row in m['meshes']:
        if mode=='remove':
            spec=next(s for s in m['mesh_mappings']if s['name']==row['name'])
            a,c=lookup[spec['old_mesh']]
        else:
            reference=m['material_reference_mesh']
            if reference not in lookup:
                aliases=[s['new_mesh']for s in manifest('remove')['mesh_mappings']if s['old_mesh']==reference]
                g.require(len(aliases)==1 and aliases[0]in lookup,'Missing verified neighboring road')
                reference=aliases[0]
            a,c=lookup[reference]
        actor=live[a['path']];comp=next(cmp for cmp in actor.get_components_by_class(u.StaticMeshComponent)if cmp.get_name()==c['name'])
        roles=[str(s.get_editor_property('imported_material_slot_name'))for s in comp.static_mesh.static_materials]
        g.require(roles==row['material_roles'],'Material roles differ')
        mats=[s.material_interface for s in comp.static_mesh.static_materials]if mode=='remove'else[comp.get_material(0)]
        if mode=='gap':g.require(package(mats[0])==m['expected_effective_material'],'Road material changed')
        with legacy_fbx(u):mesh,report=importer.import_mesh(u,row,mats)
        created.append(report);targets.append((comp,mesh))
    if mode=='remove':
        for comp,mesh in targets:g.require(comp.set_static_mesh(mesh),'Mesh swap failed')
        for name in m['remove_mesh_names']:
            pairs=[a for a in before['actors']if any((c.get('mesh')or'').split('.')[-1]==name for c in a['components'])]
            g.require(len(pairs)==1 and len(pairs[0]['components'])==1,'Unsafe deletion')
            g.require(u.get_editor_subsystem(u.EditorActorSubsystem).destroy_actor(live[pairs[0]['path']]),'Delete failed')
    else:
        mesh=targets[0][1]
        actor=u.get_editor_subsystem(u.EditorActorSubsystem).spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0),u.Rotator(0,0,0))
        actor.set_actor_label(m['actor_label']);actor.set_folder_path('MPR/RoadGap20261106');actor.tags=['mpr-road-gap-20261106']
        actor.set_actor_enable_collision(False);actor.set_actor_tick_enabled(False)
        comp=actor.get_component_by_class(u.StaticMeshComponent);g.require(comp.set_static_mesh(mesh),'Infill mesh failed')
        comp.set_collision_profile_name('NoCollision');comp.set_editor_property('cast_shadow',False)
    return dict(success=True,assets=created)

def run(u,mode):
    out=ROOT/'Saved/MPR/road_solar_20261106'/mode;out.mkdir(parents=True,exist_ok=True)
    g.require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(),'Exit PIE first')
    g.require(not(out/'before.json.gz').exists(),'This apply already started; inspect previous report')
    before=g.guard.capture(u,ROOT,g.MAP);hashes=g.guard.content_hashes(ROOT)
    g.write(out/'before.json.gz',before);g.write(out/'content_before.json.gz',hashes)
    shutil.copy2(g.MAP_FILE,out/'map_before.umap')
    report=dict(success=False,mode=mode)
    try:
        if mode=='solar':
            import mpr_solar_units as solar
            report['apply']=importlib.reload(solar).apply(u)
        else:report['apply']=apply_geometry(u,mode,before)
        after=g.guard.capture(u,ROOT,g.MAP)
        report['preservation']=validate(before,after,mode);report['content']=content_check(hashes,mode)
        g.require(u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level(),'Cannot save current map')
        after=g.guard.capture(u,ROOT,g.MAP);report['preservation']=validate(before,after,mode)
        g.write(out/'after.json.gz',after);shutil.copy2(g.MAP_FILE,out/'map_after.umap')
        report['success']=True
    except Exception:report['error']=traceback.format_exc();raise
    finally:g.write(out/'report.json',report)
    print('MPR_ROAD_SOLAR_APPLY_OK',mode,report['preservation'])

def reload_verify(u,modes):
    g.require('-run=pythonscript'in u.SystemLibrary.get_command_line().lower(),'Owned commandlet only')
    g.require(u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(g.MAP),'Cannot reload current saved map')
    current=g.guard.capture(u,ROOT,g.MAP)
    mode=modes[-1];out=ROOT/'Saved/MPR/road_solar_20261106'/mode
    expected=g.read(out/'after.json.gz')
    result=validate(g.read(out/'before.json.gz'),current,mode,cmd=True)
    g.require(not g.differences({r['guid']:g.normalize(r,commandlet_compat=True)for r in expected['actors']},{r['guid']:g.normalize(r,commandlet_compat=True)for r in current['actors']}),'Reloaded scene differs')
    native=[]
    for name in modes:
        m=manifest(name)
        for row in m['meshes']:
            mesh=u.EditorAssetLibrary.load_asset(m['namespace']+'/Meshes/'+row['name'])
            roles=[str(s.get_editor_property('imported_material_slot_name'))for s in mesh.static_materials]
            g.require(roles==row['material_roles'],'Reloaded material slots differ')
            triangles=[mesh.get_num_triangles(i)for i in range(mesh.get_num_lods())]
            if name=='solar':g.require(triangles==row['lod_triangles'],'Solar LOD differs')
            native.append(dict(name=row['name'],triangles=triangles,material_roles=roles))
    g.write(out/'reload_report.json',dict(success=True,preservation=result,native=native))
    print('MPR_ROAD_SOLAR_RELOAD_OK',mode)
