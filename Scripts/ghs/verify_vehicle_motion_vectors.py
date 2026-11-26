"""Compare actual campus sedan instances and rigid replay forklifts in the velocity buffer."""
import re
from pathlib import Path
import unreal

project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
exec((project/'Scripts/ghs/verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
RENDER_VARS=[
    'r.AntiAliasingMethod','sg.AntiAliasingQuality','r.ScreenPercentage','sg.ResolutionQuality',
    'r.DynamicRes.OperationMode','r.SecondaryScreenPercentage.GameViewport','r.TemporalAA.Upsampling',
    'r.ScreenPercentage.Default.Desktop.Mode','r.ScreenPercentage.Auto.PixelCountMultiplier',
    'r.Editor.Viewport.OverridePIEScreenPercentage',
    'r.TSR.History.ScreenPercentage','r.TSR.History.SampleCount','r.TSR.History.UpdateQuality',
    'r.TSR.ShadingRejection.Flickering','r.TSR.ShadingRejection.Flickering.Period',
    'r.TSR.ShadingRejection.Flickering.AdjustToFrameRate','r.Tonemapper.Sharpen',
    'r.VelocityOutputPass','r.Velocity.EnableVertexDeformation','r.DefaultFeature.MotionBlur',
    'sg.PostProcessQuality','r.MotionBlurQuality','r.MotionBlur.Amount','r.MotionBlur.Scale',
    'r.MotionBlur.Max','r.MaxAnisotropy'
]

def blur_settings(settings):
    return {k:settings.get_editor_property(k) for k in
            ('override_motion_blur_amount','motion_blur_amount','override_motion_blur_max','motion_blur_max',
             'override_motion_blur_target_fps','motion_blur_target_fps')}

def collect(world,pc):
    vars={k:unreal.SystemLibrary.get_console_variable_string_value(k) for k in RENDER_VARS}
    target=pc.get_view_target()
    camera=target.get_component_by_class(unreal.CameraComponent)
    volumes=[]
    for pp in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.PostProcessVolume):
        volumes.append(dict(actor=pp.get_name(),enabled=pp.enabled,unbound=pp.unbound,priority=pp.priority,
                            blend_weight=pp.blend_weight,blur=blur_settings(pp.settings)))
    traffic=pc.campus_traffic
    instances=[]
    for mesh in traffic.get_components_by_class(unreal.InstancedStaticMeshComponent) if traffic else ():
        visible=next((i for i in range(mesh.get_instance_count())
                      if mesh.get_instance_transform(i,True).scale3d.x>.1),None)
        if visible is not None:
            p=mesh.get_instance_transform(visible,True).translation
            instances.append(dict(mesh=mesh.get_name(),slot=visible,position=[p.x,p.y,p.z],
                                  movable=str(mesh.mobility),count=mesh.get_instance_count()))
    return dict(world=world.get_path_name(),viewport=pc.get_viewport_size(),controls=vars,
                camera=dict(target=target.get_name(),fov=camera.field_of_view,weight=camera.post_process_blend_weight,
                            blur=blur_settings(camera.post_process_settings)) if camera else dict(target=target.get_name()),
                volumes=volumes,traffic=instances)
variant=re.search(r'-GHSRenderCase=([a-z0-9_-]+)',CLI,re.I)
assert variant and '-usefixedtimestep' in CLI.lower(), 'Use a labelled disposable game with fixed frame rate'
OUT=ROOT/'Saved/GHSRenderQuality'/variant.group(1)
OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={},objects={})

def xy(p):
    point=pc.project_world_location_to_screen(p,False)
    assert point is not None
    return [point.x,point.y]

def vec(values):
    return unreal.Vector(*values)

def commands(command_text):
    unreal.SystemLibrary.execute_console_command(world,command_text,pc)

def frame(name):
    path=OUT/(name+'.png'); stamp=path.stat().st_mtime_ns if path.exists() else 0
    commands('Shot filename="'+path.as_posix()+'" -nosuffix')
    yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=stamp)
    report['captures'].append(name)

def center(component,transform):
    return unreal.MathLibrary.transform_location(transform,component.static_mesh.get_bounds().origin)

def samples(name,art_camera,component,read_transform):
    # Fix the camera on the world, broadside to motion. A stationary road then has
    # zero velocity while the real vehicle should show a different velocity colour.
    bounds=component.static_mesh.get_bounds()
    def witness():
        transform=read_transform()
        p=center(component,transform)
        scr=[xy(unreal.MathLibrary.transform_location(transform,bounds.origin+
                vec([sx*bounds.box_extent.x,sy*bounds.box_extent.y,sz*bounds.box_extent.z])))
             for sx in (-1,1) for sy in (-1,1) for sz in (-1,1)]
        return dict(center=xy(p),position=[p.x,p.y,p.z],
                    bounds=[min(v[0] for v in scr),min(v[1] for v in scr),
                            max(v[0] for v in scr),max(v[1] for v in scr)])
    for mode in ('lit','velocity'):
        if mode=='velocity':
            commands('viewmode VisualizeBuffer')
            commands('r.BufferVisualizationTarget Velocity')
        else:
            commands('viewmode lit')
        prev=center(component,read_transform())
        for _ in range(2):yield
        transform=read_transform()
        current=center(component,transform)
        dist=math.hypot(current.x-prev.x,current.y-prev.y)
        assert dist>.1,(name,mode,dist)
        travel=vec([(current.x-prev.x)/dist,(current.y-prev.y)/dist,0])
        rot=unreal.Rotator(pitch=-78,yaw=math.degrees(math.atan2(travel.y,travel.x))-90)
        focus=current+travel*(dist*10)
        eye=focus-unreal.MathLibrary.get_forward_vector(rot)*2250
        art_camera.set_actor_location_and_rotation(eye,rot,False,True)
        for _ in range(12):yield
        for i in range(6):
            filename=f'{name}-{mode}-{i}'
            before=witness()
            yield from frame(filename)
            report['objects'][filename]=dict(before=before,after=witness())
    commands('viewmode lit')

def run():
    yield from wait('game',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    report['render_state']=collect(world,pc)
    commands('DisableAllScreenMessages')
    art_camera=next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.CameraActor)
                    if a.get_actor_label()=='CAM_GHS_Overview')
    art_camera.camera_component.set_editor_property('field_of_view',60.)
    art_camera.camera_component.set_editor_property('post_process_blend_weight',0.)
    target=pc.get_view_target()
    traffic=pc.campus_traffic
    mesh=next(c for c in traffic.get_components_by_class(unreal.InstancedStaticMeshComponent)
              if c.static_mesh.get_name()=='SM_GHSTraffic_Sedan')
    slot=next(i for i in range(mesh.get_instance_count()) if mesh.get_instance_transform(i,True).scale3d.x>.1)
    pc.set_view_target_with_blend(art_camera,0.)
    yield from samples('road_sedan',art_camera,mesh,lambda:mesh.get_instance_transform(slot,True))
    pc.set_view_target_with_blend(target,0.)
    command('navigate',page='trace');hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    yield from wait('prepared',lambda:state()['active'] and not state()['preparing'] and not pawn.is_pose_transition_active())
    command('replayPause')
    track=json.loads((ROOT/'Content/GHSTwinUI/data/order-replay.json').read_bytes())['tracks'][0]
    a,b=max(((x,y) for x,y in zip(track['keys'],track['keys'][1:]) if x[7]=='运送托盘' and y[7]==x[7]),
            key=lambda p:math.dist(p[0][1][:2],p[1][1][:2]))
    command('replaySeek',time=a[0]+.10*(b[0]-a[0]));command('replayTrails',mode='off')
    actor=next(x for x in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
               if x.get_class().get_name()=='GHSOrderReplayActor')
    component=next(x for x in actor.get_components_by_class(unreal.StaticMeshComponent)
                   if x.get_name()=='Body_'+track['id'])
    pc.set_view_target_with_blend(art_camera,0.);command('replayPlay')
    yield from samples('replay_forklift',art_camera,component,component.get_world_transform)
    pc.set_view_target_with_blend(target,0.)
    command('replayEndRequest');command('replayExitConfirm')
    yield from wait('replay restored',lambda:not state()['active'])
    record('lit_and_velocity_captures_of_two_production_motion_paths',frames=len(report['objects']))

steps=run()
def tick(_):
    try:
        assert time.monotonic()-started<240
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
