"""Inspect and reimport the shared AGV mesh without changing level placements or materials."""
import hashlib
import json
import re
import sys
import traceback
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot, normalized
MAPS=['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse']
ASSET='/Game/GHSDigitalTwin/Meshes/SM_GHS_KukaLowProfileAGV'
FILE='Content/GHSDigitalTwin/Meshes/SM_GHS_KukaLowProfileAGV.uasset'
BASELINE=ROOT/'Saved/GHS_AGVDeckFixBaseline.json'
REPORT=ROOT/'Saved/GHS_AGVDeckFix.json'
VERIFICATION=ROOT/'Saved/GHS_AGVDeckFixVerification.json'
lib=unreal.EditorAssetLibrary
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
unreal.load_module('StaticMeshEditor')
sm_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,d):Path(p).write_text(json.dumps(d,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def content():return {p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}
def labels():return {a.get_actor_label():a for a in actors.get_all_level_actors()}
def slots(mesh):
    return [dict(name=str(s.get_editor_property('material_slot_name')),imported=str(s.get_editor_property('imported_material_slot_name')),
                 material=s.get_editor_property('material_interface').get_path_name()) for s in mesh.get_editor_property('static_materials')]

def metadata(mesh):
    b=mesh.get_bounds()
    return dict(slots=slots(mesh),bounds=dict(origin=[b.origin.x,b.origin.y,b.origin.z],
        extent=[b.box_extent.x,b.box_extent.y,b.box_extent.z]),lod_count=sm_editor.get_lod_count(mesh),
        lod_screen_sizes=list(sm_editor.get_lod_screen_sizes(mesh)),
        triangles=[mesh.get_num_triangles(i) for i in range(sm_editor.get_lod_count(mesh))])

def corner_surfaces(mesh, screws=False):
    """Read flat intersecting triangles from the saved LOD0 at each plate centre."""
    description=mesh.get_static_mesh_description(0)
    assert description
    samples={(x,y+dy):{} for x in [-28.5,28.5] for y in [-48.,48.] for dy in ([-3.1,3.1] if screws else [0])}
    count=description.get_triangle_count();visited=0
    for index in range(count*4+1024):
        tid=unreal.TriangleID(id_value=index)
        if not description.is_triangle_valid(tid):continue
        visited+=1
        points=[]
        for corner in range(3):
            vi=description.get_triangle_vertex_instance(tid,corner)
            p=description.get_vertex_position(description.get_vertex_instance_vertex(vi))
            points.append((float(p.x),float(p.y),float(p.z)))
        zz=[p[2] for p in points]
        if min(zz)>=31.9 and max(zz)<=32.4 and max(zz)-min(zz)<1e-5:
            a,b,c=points
            den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den)>1e-10:
                slot=description.get_triangle_polygon_group(tid).id_value
                name=str(mesh.get_editor_property('static_materials')[slot].get_editor_property('imported_material_slot_name'))
                for (x,y),heights in samples.items():
                    u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
                    v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
                    if min(u,v,1-u-v)>=-1e-7:
                        heights.setdefault(name,[]).append(round(sum(zz)/3,6))
        if visited==count:break
    assert visited==count
    return [dict(xy_cm=list(xy),heights_cm={n:sorted(set(z)) for n,z in heights.items()}) for xy,heights in samples.items()]

def check_corner_surfaces(surfaces,fixed):
    assert len(surfaces)==4
    for row in surfaces:
        h=row['heights_cm']
        rubber=max(h['M_VR_GHS_AGV_Rubber'])
        panel=max(h['M_VR_GHS_AGV_SideGray'])
        assert abs(rubber-32)<.0001
        assert abs(panel-(32.24 if fixed else 32))<.0001,(row,fixed)
        if fixed:assert panel-rubber>.239
        if fixed:assert min(h['M_VR_GHS_AGV_SideGray'])>32.079

def check_screws(mesh):
    surfaces=corner_surfaces(mesh,screws=True)
    assert len(surfaces)==8
    for row in surfaces:
        h=row['heights_cm'];fasteners=h['M_VR_GHS_AGV_Fasteners']
        assert min(fasteners)>32.259 and abs(max(fasteners)-32.32)<.0001
        assert min(fasteners)-max(h['M_VR_GHS_AGV_SideGray'])>.019
    return surfaces

def triangle_audit(mesh):
    description=mesh.get_static_mesh_description(0);count=description.get_triangle_count()
    unchanged=[];detail=0;visited=0
    for index in range(count*4+1024):
        tid=unreal.TriangleID(id_value=index)
        if not description.is_triangle_valid(tid):continue
        visited+=1;points=[]
        for corner in range(3):
            vi=description.get_triangle_vertex_instance(tid,corner)
            p=description.get_vertex_position(description.get_vertex_instance_vertex(vi))
            points.append(tuple(round(float(v),5) for v in [p.x,p.y,p.z]))
        is_detail=any(all(abs(p[0]-x)<2.801 and abs(p[1]-y)<4.151 and 31.95<p[2]<32.33 for p in points)
                      for x in [-28.5,28.5] for y in [-48.,48.])
        if is_detail:detail+=1
        else:unchanged.append((description.get_triangle_polygon_group(tid).id_value,sorted(points)))
        if visited==count:break
    assert visited==count
    return dict(source_triangles=count,render_triangles=mesh.get_num_triangles(0),corner_triangles=detail,
                other_triangles=len(unchanged),other_geometry_sha256=hashlib.sha256(json.dumps(sorted(unchanged)).encode()).hexdigest())

def source_hashes(source):
    result={p:sha(ROOT/p) for p in source['files'] if not p.startswith('Content/')}
    for p,h in result.items():assert h==source['files'][p]['after_source_sha256'],p
    return result

def require_separate_process():
    assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower(), 'Run saved-map verification in a separate UE commandlet, never the live editor.'

def preflight():
    require_separate_process()
    assert not BASELINE.exists()
    source=read(ROOT/'Saved/GHS_AGVDeckFixSource.json');assert source['success']
    assert sha(ROOT/FILE)==source['files'][FILE]['before_sha256']
    mesh=lib.load_asset(ASSET)
    baseline=dict(success=False,mesh=metadata(mesh),surfaces=corner_surfaces(mesh),maps={})
    check_corner_surfaces(baseline['surfaces'],False)
    for scene in MAPS:
        assert levels.load_level(scene)
        state=snapshot(labels());p=Path(source['backup_root'])/(scene.rsplit('/',1)[-1]+'_actors.json')
        write(p,state);baseline['maps'][scene]=dict(snapshot=str(p),actors=len(state))
    baseline['success']=True
    write(BASELINE,baseline)
    unreal.log('AGV_DECK_BASELINE_CONFIRMED: all four corner caps coplanar with black deck')

def apply():
    assert not REPORT.exists()
    baseline=read(BASELINE);assert baseline['success']
    source=read(ROOT/'Saved/GHS_AGVDeckFixSource.json');assert source['success']
    verified_source_hashes=source_hashes(source)
    assert sha(ROOT/FILE)==source['files'][FILE]['before_sha256']
    before=snapshot(labels())
    dirty_before=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    report=dict(success=False,source_report=str(ROOT/'Saved/GHS_AGVDeckFixSource.json'),maps_edited=False)
    try:
        original=lib.load_asset(ASSET);old_slots=slots(original)
        task=unreal.AssetImportTask();task.filename=str(ROOT/'SourceAssets/GHS/SM_GHS_KukaLowProfileAGV.fbx')
        task.destination_path=ASSET.rsplit('/',1)[0];task.destination_name=ASSET.rsplit('/',1)[1]
        task.automated=True;task.replace_existing=True;task.save=False
        options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        options.automated_import_should_detect_type=False
        options.import_materials=False;options.import_textures=False;options.import_animations=False
        data=options.static_mesh_import_data
        data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
        data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
        task.options=options
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh=lib.load_asset(ASSET);new_slots=mesh.get_editor_property('static_materials')
        assert len(new_slots)==len(old_slots)==10
        for i,slot in enumerate(new_slots):
            assert str(slot.get_editor_property('imported_material_slot_name'))==old_slots[i]['imported']
            slot.set_editor_property('material_interface',lib.load_asset(old_slots[i]['material'].split('.')[0]));new_slots[i]=slot
        mesh.set_editor_property('static_materials',new_slots)
        reduction=unreal.StaticMeshReductionOptions();reduction.auto_compute_lod_screen_size=False
        reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s)
                                      for p,s in zip([1,.5,.18,.05],baseline['mesh']['lod_screen_sizes'])]
        assert sm_editor.set_lods(mesh,reduction)==4
        assert sm_editor.set_lod_screen_sizes(mesh,baseline['mesh']['lod_screen_sizes'])
        check_corner_surfaces(corner_surfaces(mesh),True)
        after=metadata(mesh)
        for key in ('slots','bounds','lod_count','lod_screen_sizes'):
            assert after[key]==baseline['mesh'][key],key
        audit=triangle_audit(mesh);original_audit=read(ROOT/'Saved/GHS_AGVDeckSavedGeometry.json')
        for key in ('other_triangles','other_geometry_sha256'):
            assert audit[key]==original_audit[key],key
        assert audit['source_triangles']-original_audit['source_triangles']==192
        assert audit['corner_triangles']-original_audit['corner_triangles']==192
        assert after['triangles'][0]==audit['source_triangles']
        check_screws(mesh)
        assert snapshot(labels())==before,'Live scene changed during asset reimport'
        assert [p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]==dirty_before
        assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
        baseline_content=read(Path(source['backup_root'])/'content_hashes.json');now=content()
        assert set(now)==set(baseline_content)
        changed=[p for p,h in baseline_content.items() if now[p]!=h]
        assert changed==[FILE],changed
        for p,h in read(Path(source['backup_root'])/'history_hashes.json').items():assert sha(ROOT/p)==h,p
        report.update(success=True,mesh=after,changed_content=changed,mesh_sha256=sha(ROOT/FILE),
                      live_scene_unchanged=True,live_unsaved_edits_preserved=True,materials_unchanged=True,
                      corrected_surfaces=corner_surfaces(mesh),screw_surfaces=check_screws(mesh),
                      source_sha256=verified_source_hashes,geometry_audit=audit)
        unreal.log('AGV_DECK_REIMPORTED: shared mesh fixed, two map files and all materials unchanged')
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:write(REPORT,report)

def verify():
    require_separate_process()
    result=dict(success=False,maps=[])
    try:
        report=read(REPORT);assert report['success']
        baseline=read(BASELINE);source=read(report['source_report'])
        assert source_hashes(source)==report['source_sha256']
        initial=content();assert sha(ROOT/FILE)==report['mesh_sha256']
        old=read(Path(source['backup_root'])/'content_hashes.json')
        assert set(initial)==set(old)
        assert [p for p,h in old.items() if initial[p]!=h]==[FILE]
        for scene,entry in baseline['maps'].items():
            assert levels.load_level(scene)
            by=labels();assert snapshot(by)==normalized(read(entry['snapshot'])),scene
            robots=[a for n,a in by.items() if re.fullmatch(r'GHS_AGV_\d{2}',n)]
            assert len(robots)==34
            assert all(a.get_component_by_class(unreal.StaticMeshComponent).static_mesh.get_path_name()==ASSET+'.'+ASSET.rsplit('/',1)[1] for a in robots)
            result['maps'].append(dict(map=scene,agvs=34,placements_materials_and_effects_unchanged=True))
        mesh=lib.load_asset(ASSET);actual=metadata(mesh)
        assert actual==report['mesh']
        surfaces=corner_surfaces(mesh);check_corner_surfaces(surfaces,True)
        screws=check_screws(mesh);assert triangle_audit(mesh)==report['geometry_audit']
        for p,h in read(Path(source['backup_root'])/'history_hashes.json').items():assert sha(ROOT/p)==h
        assert content()==initial
        result.update(success=True,corner_surfaces=surfaces,plate_top_separation_mm=2.4,
                      screw_surfaces=screws,source_hashes_verified=True,
                      saved_mesh_reloaded=True,only_shared_agv_asset_modified=True,mesh=actual)
        unreal.log('AGV_DECK_FIX_VERIFIED: 4 separated corner plates; both maps/68 AGVs; original materials and LODs preserved')
    except Exception:
        result['error']=traceback.format_exc();raise
    finally:write(VERIFICATION,result)

if __name__=='__main__':
    if '-AGVDeckPreflight' in unreal.SystemLibrary.get_command_line(): preflight()
    else: apply()
