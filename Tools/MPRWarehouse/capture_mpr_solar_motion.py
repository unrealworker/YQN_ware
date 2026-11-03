"""Deterministic native game camera sampling for solar temporal/LOD review.

No asset saves, no near-clip/AA override. Use -MPRMotionLabel=baseline|final.
Captures settle briefly at each deterministic pose; this is a sampled motion
test, not a claim of real-time video or input-to-photon latency.
"""
from pathlib import Path
import sys,json,time,hashlib,struct,traceback,math,re
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as base
command=u.SystemLibrary.get_command_line();match=re.search(r'-MPRMotionLabel=([a-zA-Z0-9_-]+)',command)
LABEL=match.group(1)if match else 'review'
OUT=ROOT/'Saved/MPR/solar_motion'/LABEL;OUT.mkdir(parents=True,exist_ok=True)
RUN_STAMP=str(time.time_ns())
POSES=[]
for i in range(12):POSES.append(('static',32000.,-66.,-90.))
for i in range(36):POSES.append(('pan',32000.,-66.,-92.+4.*i/35))
for i in range(48):
    t=i/47;distance=70000.-59000.*math.sin(math.pi*t)
    POSES.append(('zoom',distance,-58.,-82.))
ROOF_QUAD=[(-60.,80.,13.64),(-60.,-80.,13.64),(160.,-80.,13.64),(160.,80.,13.64)]
start=time.monotonic();ready=None;index=0;pending=None;done=False;handle=None
report=dict(success=False,label=LABEL,renderer='Native UE game viewport, deterministic sampled movement',captures=[],
    run_id=RUN_STAMP,capture_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    map_sha256=hashlib.sha256(base.MAP_FILE.read_bytes()).hexdigest(),assets_saved=False,
    frame_settle_seconds=.15,first_warmup_seconds=12.,temporal_limit='Each sampled pose settles for 0.15 seconds. Review across native PNGs; encoded playback speed is illustrative, not measured real-time performance.')

def project_roof():
    camera=base.view();p=camera['position_cm'];pitch,yaw,roll=[math.radians(v)for v in camera['rotation_deg']]
    assert abs(roll)<1e-5
    forward=[math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),math.sin(pitch)]
    right=[-math.sin(yaw),math.cos(yaw),0.];up=[-math.sin(pitch)*math.cos(yaw),-math.sin(pitch)*math.sin(yaw),math.cos(pitch)]
    fov=base.camera.get_component_by_class(u.CameraComponent).get_editor_property('field_of_view')
    focal=960/math.tan(math.radians(fov)/2);quad=[]
    for x,y,z in ROOF_QUAD:
        v=[x*100-p[0],-y*100-p[1],z*100-p[2]];d=sum(a*b for a,b in zip(v,forward));assert d>0
        quad.append([960+focal*sum(a*b for a,b in zip(v,right))/d,540-focal*sum(a*b for a,b in zip(v,up))/d])
    return camera,float(fov),quad

def finish(error=None):
    global done
    done=True;u.unregister_slate_post_tick_callback(handle)
    report.update(success=error is None,error=error,map_unchanged=hashlib.sha256(base.MAP_FILE.read_bytes()).hexdigest()==report['map_sha256'])
    if not report['map_unchanged']:report['success']=False
    (OUT/'capture_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    base.console('quit')

def set_view():
    global ready
    group,distance,pitch,yaw=POSES[index];rot=u.Rotator(pitch=pitch,yaw=yaw);target=u.Vector(65*100,0,14*100)
    base.camera.set_actor_location_and_rotation(target-u.MathLibrary.get_forward_vector(rot)*distance,rot,False,True)
    base.pc.set_view_target_with_blend(base.camera,0);ready=time.monotonic()

def tick(dt):
    global ready,index,pending
    if done:return
    try:
        assert time.monotonic()-start<240,'Motion capture deadline'
        if ready is None:
            if not base.discover():return
            assert list(base.pc.get_viewport_size())==[1920,1080]
            c=base.camera.get_component_by_class(u.CameraComponent);c.set_editor_property('constrain_aspect_ratio',False)
            c.set_editor_property('override_aspect_ratio_axis_constraint',True);c.set_editor_property('aspect_ratio_axis_constraint',u.AspectRatioAxisConstraint.ASPECT_RATIO_MAINTAIN_XFOV)
            base.pawn.cancel_pose_transition();base.pawn.freeze_current_pose()
            for a in base.roofs:a.set_actor_hidden_in_game(False)
            base.console('r.ScreenPercentage 100');base.console('DisableAllScreenMessages')
            report['cvars']={name:u.SystemLibrary.get_console_variable_float_value(name)for name in ['r.ScreenPercentage','r.AntiAliasingMethod','r.TemporalAA.Upsampling','r.Nanite.MaxPixelsPerEdge']}
            set_view();return
        if pending:
            if not pending.exists()or pending.stat().st_size<10000:return
            data=pending.read_bytes()
            if data[-12:]!=b'\x00\x00\x00\x00IEND\xaeB\x60\x82':return
            assert struct.unpack('>II',data[16:24])==(1920,1080)
            cam,fov,quad=project_roof()
            report['captures'].append(dict(index=index,group=POSES[index][0],path=str(pending),sha256=hashlib.sha256(data).hexdigest(),camera=cam,fov=fov,roof_quad_px=quad))
            pending=None;index+=1
            if index==len(POSES):finish();return
            set_view()
        elif time.monotonic()-ready>(12 if index==0 else .15):
            # A second validation run must never consume a previous PNG while
            # the asynchronous screenshot command is still being processed.
            pending=OUT/('%03d_%s.png'%(index,RUN_STAMP));assert not pending.exists()
            base.console('Shot filename="'+pending.as_posix()+'" -nosuffix')
    except Exception:finish(traceback.format_exc())

handle=u.register_slate_post_tick_callback(tick)
