"""Read-only saved-map capture with the exact calibrated off-axis projection.

Run in a dedicated editor via -ExecCmds="py ...". A temporary SceneCapture2D
renders the actual UE scene; no map/asset is saved and no source image is used
as a background. -MPRReferenceCaptureQuit exits after the PNG is exported.
"""
from pathlib import Path
import json,hashlib,sys,time,traceback,math,shutil,struct
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_scene_ownership import verify_owned_scene
from mpr_interior_preservation import capture_editor_snapshot,assert_preserved,MAP
OUT=ROOT/('Saved/MPR/reference_v3_before_capture' if '-MPRReferenceBefore' in u.SystemLibrary.get_command_line() else 'Saved/MPR/reference_v4');OUT.mkdir(parents=True,exist_ok=True)
A=u.get_editor_subsystem(u.EditorActorSubsystem);L=u.get_editor_subsystem(u.LevelEditorSubsystem);E=u.get_editor_subsystem(u.UnrealEditorSubsystem)
report=dict(success=False,map_saved=False,renderer='Unreal SceneCapture2D calibrated off-axis perspective')
actor=None;handle=None;busy=False

def write():
    (OUT/'calibrated_capture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

def finish(error=None):
    global handle
    if handle:u.unregister_slate_post_tick_callback(handle);handle=None
    try:
        if actor:A.destroy_actor(actor)
        assert_preserved(baseline,capture_editor_snapshot(u,project_root=ROOT))
        assert hashlib.sha256(map_file.read_bytes()).hexdigest()==map_sha
    except Exception:error=(error or '')+'\n'+traceback.format_exc()
    report.update(success=error is None,error=error,elapsed_seconds=time.monotonic()-start);write()
    if '-MPRReferenceCaptureQuit' in u.SystemLibrary.get_command_line():u.SystemLibrary.quit_editor()

def tick(dt):
    global busy
    if busy:return
    busy=True
    try:
        if time.monotonic()-start>25:
            capture.capture_scene()
            name='calibrated_overview_'+str(time.time_ns())+'.png'
            file=OUT/name;assert not file.exists()
            u.RenderingLibrary.export_render_target(E.get_editor_world(),target,str(OUT),name)
            assert file.is_file() and file.stat().st_size>10000
            content=file.read_bytes();assert content[:8]==b'\x89PNG\r\n\x1a\n'
            assert list(struct.unpack('>II',content[16:24]))==report['resolution']
            shutil.copy2(file,OUT/'calibrated_overview.png')
            report.update(image=str(file),image_sha256=hashlib.sha256(content).hexdigest(),fresh_export=True);finish()
    except Exception:finish(traceback.format_exc())
    finally:busy=False

def run():
    global actor,capture,target,baseline,map_file,map_sha,start,handle
    assert not L.is_in_play_in_editor()
    assert not u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    verify_owned_scene(ROOT);assert L.load_level(MAP)
    baseline=capture_editor_snapshot(u,project_root=ROOT)
    map_file=ROOT/'Content/Maps/MPR_CAD_Warehouse.umap';map_sha=hashlib.sha256(map_file.read_bytes()).hexdigest()
    cal=json.loads((ROOT/'SourceAssets/MPR/reference_v3/calibration/camera_calibration.json').read_text(encoding='utf8'))
    w,h=cal['image_dimensions_px'];K=cal['intrinsic_matrix'];matrix=cal['blender_camera']['matrix_world'];loc=cal['camera_location_m']
    mirror=lambda p:u.Vector(p[0],-p[1],p[2])
    forward=mirror([-matrix[i][2] for i in range(3)])
    right=mirror([matrix[i][0] for i in range(3)])
    up=mirror([matrix[i][1] for i in range(3)])
    rotation=u.MathLibrary.make_rotation_from_axes(forward,right,up)
    actor=A.spawn_actor_from_class(u.SceneCapture2D,mirror([v*100 for v in loc]),rotation)
    actor.set_actor_label('MPR4_TransientReferenceCapture');capture=actor.get_component_by_class(u.SceneCaptureComponent2D)
    # FinalColorLDR performs the gamma transform using target_gamma. Keep the
    # byte target linear to avoid applying a second hardware sRGB encoding.
    target=u.RenderingLibrary.create_render_target2d(E.get_editor_world(),w,h,u.TextureRenderTargetFormat.RTF_RGBA8)
    target.set_editor_property('target_gamma',2.2)
    capture.texture_target=target;capture.capture_source=u.SceneCaptureSource.SCS_FINAL_COLOR_LDR
    capture.fov_angle=110.;capture.capture_every_frame=True;capture.always_persist_rendering_state=True
    # UE row-vector reversed-Z perspective. X/Y principal point offsets are
    # the same calibrated pinhole projection used for Blender reconstruction.
    projection=u.Matrix(x_plane=u.Plane(2*K[0][0]/w,0,0,0),y_plane=u.Plane(0,2*K[1][1]/h,0,0),
                        z_plane=u.Plane(2*K[0][2]/w-1,1-2*K[1][2]/h,0,1),w_plane=u.Plane(0,0,10,0))
    capture.use_custom_projection_matrix=True;capture.custom_projection_matrix=projection
    report.update(resolution=[w,h],location_cm=[loc[0]*100,-loc[1]*100,loc[2]*100],rotation=str(rotation),
                  calibration_sha256=hashlib.sha256((ROOT/'SourceAssets/MPR/reference_v3/calibration/camera_calibration.json').read_bytes()).hexdigest())
    start=time.monotonic();write();handle=u.register_slate_post_tick_callback(tick)

if __name__=='__main__':
    try:run()
    except Exception:
        report.update(error=traceback.format_exc());write()
        if actor:A.destroy_actor(actor)
        if '-MPRReferenceCaptureQuit' in u.SystemLibrary.get_command_line():u.SystemLibrary.quit_editor()
        raise
