"""Capture the actual runtime view using calibrated overscan; never save assets."""
from pathlib import Path
import sys,json,time,math,traceback,hashlib,struct
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve();sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as base
OUT=ROOT/'Saved/MPR/reference_v4';CAL=json.loads((ROOT/'SourceAssets/MPR/reference_v3/calibration/camera_calibration.json').read_text(encoding='utf8'))
start=time.monotonic();ready=None;done=False;old=None;handle=None;shot_file=None
report=dict(success=False,renderer='UE game viewport TSR',overscan_size=[2006,1860],crop=[278,949,1728,910],map_sha256=hashlib.sha256(base.MAP_FILE.read_bytes()).hexdigest())
def tick(dt):
 global ready,done,old,handle,shot_file
 if done:return
 try:
  if ready is None:
   if not base.discover():
    assert time.monotonic()-start<30;return
   pc=base.pc;cam=base.camera;old=cam.get_actor_transform();loc=CAL['camera_location_m'];m=CAL['blender_camera']['matrix_world']
   mirror=lambda p:u.Vector(p[0],-p[1],p[2])
   rotation=u.MathLibrary.make_rotation_from_axes(mirror([-m[i][2] for i in range(3)]),mirror([m[i][0] for i in range(3)]),mirror([m[i][1] for i in range(3)]))
   cam.set_actor_location(mirror([v*100 for v in loc]),False,True);cam.set_actor_rotation(rotation,False)
   c=cam.get_component_by_class(u.CameraComponent);c.set_field_of_view(56.830013);c.set_editor_property('constrain_aspect_ratio',False)
   c.set_editor_property('override_aspect_ratio_axis_constraint',True)
   c.set_editor_property('aspect_ratio_axis_constraint',u.AspectRatioAxisConstraint.ASPECT_RATIO_MAINTAIN_XFOV)
   pc.set_view_target_with_blend(cam,0);base.pawn.cancel_pose_transition();base.pawn.freeze_current_pose()
   base.console('r.ScreenPercentage 100');base.console('DisableAllScreenMessages');base.console('r.SetNearClipPlane 100')
   report['render_quality']={key:u.SystemLibrary.get_console_variable_string_value(key) for key in
       ('r.Nanite.MaxPixelsPerEdge','r.Nanite.AllowVoxels','r.Shadow.Virtual.Enable')}
   ready=time.monotonic();return
  if shot_file is not None:
   if shot_file.is_file() and shot_file.stat().st_size>10000:
    data=shot_file.read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
    assert list(struct.unpack('>II',data[16:24]))==report['overscan_size']
    assert data[-12:]==b'\x00\x00\x00\x00IEND\xaeB\x60\x82'
    report.update(success=True,raw_image=str(shot_file),map_unchanged=hashlib.sha256(base.MAP_FILE.read_bytes()).hexdigest()==report['map_sha256'])
    report['raw_image_sha256']=hashlib.sha256(data).hexdigest();assert report['map_unchanged']
    (OUT/'runtime_calibrated_capture.json').write_text(json.dumps(report,indent=2),encoding='utf8');done=True;u.unregister_slate_post_tick_callback(handle);base.console('quit')
   assert time.monotonic()-ready<35,'Screenshot deadline'
  elif time.monotonic()-ready>20:
   report.update(camera_readback=base.view(),field_of_view=float(base.pc.player_camera_manager.get_fov_angle()))
   errors=[];measured=[]
   for row in CAL['correspondences']:
    p=row['world_m'];point=base.pc.project_world_location_to_screen(u.Vector(p[0]*100,-p[1]*100,p[2]*100),False)
    assert point is not None,'Landmark behind camera'
    pixel=[float(point.x)-278,float(point.y)-949]
    errors.append(math.dist(pixel,row['projected_pixel']));measured.append(math.dist(pixel,row['measured_pixel']))
   assert max(errors)<.1,('UE projection differs from calibrated camera',max(errors))
   report.update(projection_landmarks=len(errors),calibration_max_error_px=max(errors),reference_landmark_rms_px=math.sqrt(sum(e*e for e in measured)/len(measured)))
   file=OUT/('runtime_overscan_'+str(time.time_ns())+'.png')
   base.console('Shot filename="'+str(file).replace('\\','/')+'" -nosuffix')
   shot_file=file
 except Exception:
  report.update(success=False,error=traceback.format_exc());(OUT/'runtime_calibrated_capture.json').write_text(json.dumps(report,indent=2),encoding='utf8');done=True;u.unregister_slate_post_tick_callback(handle);base.console('quit')
handle=u.register_slate_post_tick_callback(tick)
