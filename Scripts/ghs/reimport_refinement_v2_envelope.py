"""Refresh only the four new V2 envelope meshes after UV-only source repair."""
from pathlib import Path
import sys,json,hashlib,traceback
import unreal
ROOT=Path(r'D:\UEPro\Test');SRC=ROOT/'SourceAssets/GHS/RefinementV2'
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from import_refinement_v2 import BLUE,NORMAL
lib=unreal.EditorAssetLibrary;assets=unreal.AssetToolsHelpers.get_asset_tools()
unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run():
    report_path=ROOT/'Saved/GHS_RefinementV2Import.json'
    report=json.loads(report_path.read_text());assert report['success']
    assert not (ROOT/'Saved/GHS_RefinementV2.json').exists(),'Only before applying the revision'
    initial=SRC/'Envelope/ue_initial_import.json'
    if not initial.exists():initial.write_text(report_path.read_text())
    manifest_path=SRC/'Envelope/envelope_v2.json';manifest=json.loads(manifest_path.read_text())
    by={m['name']:m for m in report['meshes']}
    repair=dict(success=False,meshes=[])
    try:
        for spec in manifest['meshes']:
            name=spec['name'];entry=by[name];path=entry['path'].split('.')[0]
            assert path=='/Game/GHSRefinementV2/Meshes/'+name
            assert spec['bounds_m']==entry['bounds_m'],'UV repair changed geometry bounds'
            existing=lib.load_asset(path)
            existing.get_editor_property('asset_import_data').set_editor_property('normal_import_method',unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
            build=editor.get_lod_build_settings(existing,0)
            build.set_editor_property('recompute_tangents',False)
            build.set_editor_property('recompute_normals',False)
            editor.set_lod_build_settings(existing,0,build)
            task=unreal.AssetImportTask();task.filename=spec['fbx'];task.destination_path=path.rsplit('/',1)[0]
            task.destination_name=name;task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=True
            opt=unreal.FbxImportUI();opt.import_mesh=True;opt.import_as_skeletal=False
            opt.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;opt.automated_import_should_detect_type=False
            opt.import_materials=False;opt.import_textures=False;opt.import_animations=False
            data=opt.static_mesh_import_data;data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
            data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS;data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
            task.options=opt;assets.import_asset_tasks([task]);mesh=lib.load_asset(path);assert mesh
            unreal.log('V2_ENVELOPE_IMPORT_SETTINGS '+name+' '+str(mesh.get_editor_property('asset_import_data').get_editor_property('normal_import_method'))+' '+str(editor.get_lod_build_settings(mesh,0)))
            assert mesh.get_editor_property('asset_import_data').get_editor_property('normal_import_method')==unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS
            assert not editor.get_lod_build_settings(mesh,0).get_editor_property('recompute_tangents')
            slots=mesh.get_editor_property('static_materials');roles=[]
            for i,s in enumerate(slots):
                role=str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1]
                role={'WallVolume':'Faces','WallSection':'Sections','WallTrim':'Edges'}.get(role,role)
                roles.append(role);s.set_editor_property('material_interface',lib.load_asset(entry['palettes']['Blue'][i]));slots[i]=s
            assert roles==entry['roles'];mesh.set_editor_property('static_materials',slots)
            if name.endswith('DockDoor'):
                reduction=unreal.StaticMeshReductionOptions();reduction.auto_compute_lod_screen_size=False
                reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in [(1.,1.),(.55,.25),(.30,.08),(.18,.025)]]
                assert editor.set_lods(mesh,reduction)==4
            b=mesh.get_bounds();center=[(a+b)*50 for a,b in spec['bounds_m']];center[1]*=-1
            extent=[(b-a)*50 for a,b in spec['bounds_m']]
            assert max(abs(getattr(b.origin,k)-v) for k,v in zip('xyz',center))<.15
            assert max(abs(getattr(b.box_extent,k)-v) for k,v in zip('xyz',extent))<.15
            assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
            entry.update(fbx_sha256=sha(spec['fbx']),lod_triangles=[mesh.get_num_triangles(i) for i in range(editor.get_lod_count(mesh))])
            repair['meshes'].append(name)
        report['manifests']['Envelope/envelope_v2.json']=sha(manifest_path)
        report['envelope_uv_repair']=True
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        repair['success']=True;unreal.log('GHS_V2_UV_REIMPORT_SUCCESS')
    except Exception:repair['error']=traceback.format_exc();raise
    finally:(ROOT/'Saved/GHS_RefinementV2UVImport.json').write_text(json.dumps(repair,indent=2))
if __name__=='__main__':run()
