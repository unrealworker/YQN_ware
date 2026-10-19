"""Verify the saved fleet after restart and frame a staffed forklift in editor."""
import sys
sys.path.insert(0,'D:/UEPro/Test/Scripts/ghs')
import import_manned_forklift_fleet as f
import unreal
r=f.util.read(f.REPORT)
assert r['success'] and f.E.get_editor_world().get_path_name().split('.')[0]==f.MAP
by=f.util.labels();saved=f.util.read(f.Path(r['backup_root'])/'final_before_build.json')
now=f.snapshot(by);assert saved==now,'Saved scene changed after build; inspect rather than overwrite'
assert len(by)==260
fleet=[a for a in by.values() if a.actor_has_tag('NormalWarehouseMannedForklift')]
assert len(fleet)==8
mesh=f.LIB.load_asset(f.MESH_PATH)
for a in fleet:
    assert a.static_mesh_component.static_mesh==mesh
    assert f.xyz(a.get_actor_scale3d())==[1.,1.,1.]
    assert a.get_attach_parent_actor() is None
p=by['GHN_MannedForklift_01'].get_actor_location()
eye=unreal.Vector(p.x+800,p.y+650,600)
f.A.set_selected_level_actors([by['GHN_MannedForklift_01']])
f.E.set_level_viewport_camera_info(eye,unreal.MathLibrary.find_look_at_rotation(eye,unreal.Vector(p.x,p.y,125)))
f.util.write(f.ROOT/'Saved/GHS_MannedForkliftFinalEditorVerification.json',dict(success=True,map=f.MAP,
    actor_count=len(by),manual_count=len(fleet),map_sha256=f.util.sha(f.ROOT/f.MAP_FILE),
    all_saved_actor_snapshots_match=True,independent_static_meshes=True,lod_triangles=[mesh.get_num_triangles(i) for i in range(4)],
    native_class_available=hasattr(unreal,'GHSMannedForkliftDataComponent'),editor_view='GHN_MannedForklift_01'))
unreal.log('MANNED_FORKLIFT_FINAL_EDITOR_VERIFIED')
