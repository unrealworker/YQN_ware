"""Capture the existing MPR map and actual mesh bounds without modifying assets."""
from pathlib import Path
import json,sys,shutil
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch
import refine_mpr_interior_cad_20261112 as prior
OUT=ROOT/'Saved/MPR/optimization_20261112'

def capture(u):
    OUT.mkdir(parents=True,exist_ok=True)
    snapshot=guard.capture(u,ROOT,patch.MAP)
    hashes=guard.content_hashes(ROOT)
    guard.assert_clean(snapshot)
    if (OUT/'baseline.json.gz').exists():
        original=patch.read(OUT/'baseline.json.gz')
        assert original['map_file_sha256']==snapshot['map_file_sha256']
        assert [guard.canonical_actor(a) for a in original['actors']]==[guard.canonical_actor(a) for a in snapshot['actors']]
    else:
        patch.write(OUT/'baseline.json.gz',snapshot)
        patch.write(OUT/'original_package_hashes.json',hashes)
        patch.write(OUT/'preserved_configuration.json',dict(simulation=prior.sim_properties(u),viewport=prior.viewport(u)))
        shutil.copy2(ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap',OUT/'original_map.umap')
    paths=sorted({c['mesh'] for a in snapshot['actors'] for c in a['components'] if c.get('mesh')})
    mesh_editor=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    meshes={}
    for path in paths:
        mesh=u.EditorAssetLibrary.load_asset(path)
        if not isinstance(mesh,u.StaticMesh):continue
        b=mesh.get_bounds()
        row=dict(bounds_cm=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],
                            [b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],
                            [b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]],
                 lod_count=mesh_editor.get_lod_count(mesh),
                 material_paths=[s.material_interface.get_path_name() if s.material_interface else None for s in mesh.static_materials])
        row['lod_vertices']=[mesh_editor.get_number_verts(mesh,i) for i in range(row['lod_count'])]
        row['lod_screen_sizes']=list(mesh_editor.get_lod_screen_sizes(mesh))
        row['nanite_enabled']=mesh.get_editor_property('nanite_settings').enabled
        meshes[path]=row
    patch.write(OUT/'native_mesh_bounds.json',meshes)
    assert guard.content_hashes(ROOT)==hashes
    if not (OUT/'original_package_hashes.json').exists():patch.write(OUT/'original_package_hashes.json',hashes)
    print(json.dumps(dict(success=True,actors=len(snapshot['actors']),meshes=len(meshes),map_sha256=snapshot['map_file_sha256'])))

if __name__=='__main__':
    import unreal
    capture(unreal)
