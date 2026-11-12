"""Comparable native scene timing; diagnostic visibility only in an owned game."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re,sys,time,traceback
import unreal as u
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as timing
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
cli=u.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+s+r'(?=\s|$)',cli,re.I) for s in ['own','game','RenderOffscreen','TwinDiagnostics'])
phase='after' if '-mproptafter' in cli.lower() else 'before'
lod_only=bool(re.search(r'(?:^|\s)-MPROptLODOnly(?=\s|$)',cli,re.I))
assert not lod_only or phase=='after','-MPROptLODOnly requires -MPROptAfter'
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT=ROOT/'Saved/MPR/optimization_20261112/runtime'/phase/stamp
OUT.mkdir(parents=True,exist_ok=False)
start=time.monotonic();world=pc=pawn=camera=sim=None;handle=None;finished=False
map_path=ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
original_sha=hashlib.sha256(map_path.read_bytes()).hexdigest()
views=[dict(name='overview',target=[0,0,450],distance=47000,pitch=-62,yaw=-90),
       dict(name='rack-close',target=[-4480,0,500],distance=3000,pitch=-48,yaw=18),
       dict(name='sorter',target=[-10434,1300,130],distance=4300,pitch=-48,yaw=0)]
report=dict(success=False,phase=phase,run_id=stamp,map_sha256=original_sha,resolution=[1920,1080],views=views,
            captures=[],samples=[],lod_only=lod_only,scope='Single native game, original automatic simulation and 100 percent resolution; no Pixel Streaming claim.')
def write():
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
def console(s):u.SystemLibrary.execute_console_command(world,s,pc)
def pause(seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:yield
def wait(test,seconds=30):
    until=time.monotonic()+seconds
    while not test():
        assert time.monotonic()<until,'Timed out'
        yield
def camera_pose():
    c=pc.player_camera_manager;p=c.get_camera_location();r=c.get_camera_rotation()
    return [p.x,p.y,p.z,r.pitch,r.yaw,r.roll]
def workers():
    components=list(sim.get_components_by_class(u.MPRWorkerPoseComponent))
    return dict(total=len(components),visible=sum(c.is_visible() for c in components),
                visible_lods=dict(Counter(c.get_predicted_lod_level() for c in components if c.is_visible())),
                visible_pose_revisions=[c.get_pose_revision() for c in components if c.is_visible()])
def discover():
    global world,pc,pawn,camera,sim
    for w in u.ObjectIterator(u.World):
        if w.get_path_name().startswith(MAP+'.'):
            controller=u.GameplayStatics.get_player_controller(w,0)
            if controller:world=w;pc=controller;break
    if not world:return False
    pawn=pc.get_controlled_pawn()
    if not pawn:return False
    a=u.GameplayStatics.get_all_actors_of_class(world,u.MPRSorterSimulationActor)
    if not a:return False
    sim=a[0]
    return bool(json.loads(sim.get_simulation_report_json())['ready'])
def sample(view,diagnostic=False):
    name=view['name']+('-workers-hidden-diagnostic' if diagnostic else '')
    rot=u.Rotator(pitch=view['pitch'],yaw=view['yaw'])
    camera.set_actor_location_and_rotation(u.Vector(*view['target'])-u.MathLibrary.get_forward_vector(rot)*view['distance'],rot,False,True)
    pc.set_view_target_with_blend(camera,0)
    console('ShowFlag.SkeletalMeshes '+('0' if diagnostic else '1'))
    report['stage']=name+'_warmup';write();yield from pause(10)
    before=workers();pose=camera_pose()
    filename='MPR_OPT_'+phase+'_'+stamp+'_'+name+'.csv'
    csvpath=ROOT/'Saved/Profiling/CSV'/filename
    console('CsvProfile STARTFILE='+filename);console('CsvProfile START')
    report['stage']=name+'_sample';write();yield from pause(15)
    console('CsvProfile STOP');yield from wait(lambda:timing.csv_complete(csvpath),20)
    native=timing.parse_csv(csvpath);native['fps']=native['frame_count']/native['native_frame_time_seconds']
    after=workers();assert before['total']==after['total'] and before['visible']==after['visible']
    assert camera_pose()==pose
    report['samples'].append(dict(name=name,diagnostic_only=diagnostic,camera=pose,workers_before=before,workers_after=after,native_csv=native))
    if not diagnostic:
        png=OUT/(name+'.png');console('Shot showui filename="'+png.as_posix()+'" -nosuffix')
        yield from wait(lambda:timing.png_ready(png),20)
        report['captures'].append(dict(name=name,path=str(png),camera=pose,sha256=hashlib.sha256(png.read_bytes()).hexdigest()))
    console('ShowFlag.SkeletalMeshes 1');write()

def transform_values(transform):
    p,q,s=transform.translation,transform.rotation,transform.scale3d
    return [p.x,p.y,p.z,q.x,q.y,q.z,q.w,s.x,s.y,s.z]

def lod_diagnostics():
    """Real camera feedback, after every timed sample; never force a mesh LOD."""
    sim.set_automatic_advance_for_diagnostics(False)
    sim.set_simulation_playing(False)
    yield from pause(.5)
    state=json.loads(sim.get_simulation_report_json())
    placements=[p for p in state['cad_workers'] if p['source_handle']=='2CCF61']
    assert len(placements)==1 and placements[0]['role']=='sorter_console'
    # The fixed console operator is not resubmitted by paused feed updates.
    placement=placements[0]
    components={int(c.get_name().removeprefix('MannyWorker_')):c
                for c in sim.get_components_by_class(u.MPRWorkerPoseComponent)}
    subject=components[placement['worker_index']]
    feed_indices={w['index'] for w in state['skeletal_workers'] if w['role']=='central_feed'}
    assert len(feed_indices)==6
    baseline_revisions={i:c.get_pose_revision() for i,c in components.items()}
    baseline_bones=[transform_values(subject.get_bone_transform_by_name(
        subject.get_bone_name(i),u.BoneSpaces.WORLD_SPACE)) for i in range(subject.get_num_bones())]
    baseline_world=transform_values(subject.get_world_transform())
    def feed_pose(component):
        left,right=component.get_palm_world(True),component.get_palm_world(False)
        return dict(bones=[transform_values(component.get_bone_transform_by_name(
            component.get_bone_name(i),u.BoneSpaces.WORLD_SPACE)) for i in range(component.get_num_bones())],
            root=transform_values(component.get_world_transform()),
            palms=[left.x,left.y,left.z,right.x,right.y,right.z])
    baseline_feed={i:feed_pose(components[i]) for i in feed_indices}
    assert all(len(pose['bones'])==89 for pose in baseline_feed.values())
    baseline_time=[m['sim_time'] for m in state['machines']]
    assert subject.is_visible() and subject.get_forced_lod()==0
    target=u.Vector(*placement['feet_cm'])+u.Vector(0,0,90)
    yaw=subject.get_world_rotation().yaw+subject.get_reference_facing_yaw_degrees()+180
    diagnostic=dict(success=False,source_handle=placement['source_handle'],worker_index=placement['worker_index'],
        forced_lod=0,pose_revision=subject.get_pose_revision(),bone_count=len(baseline_bones),stages=[],
        scope='Renderer-selected predicted LOD and display uploads with unchanged bones; no GPU triangle readback.')
    report['lod_diagnostics']=diagnostic

    def snapshot(name):
        bones=[transform_values(subject.get_bone_transform_by_name(
            subject.get_bone_name(i),u.BoneSpaces.WORLD_SPACE)) for i in range(subject.get_num_bones())]
        assert len(bones)==len(baseline_bones)
        error=max(abs(a-b) for old,new in zip(baseline_bones,bones) for a,b in zip(old,new))
        assert error<1.e-6,('Camera-only change moved worker bones',name,error)
        assert all(c.get_pose_revision()==baseline_revisions[i] for i,c in components.items()
                   if i not in feed_indices),('Non-feed pose revision changed',name)
        assert baseline_world==transform_values(subject.get_world_transform()),name
        feed_errors={}
        for index,previous in baseline_feed.items():
            current=feed_pose(components[index])
            assert len(current['bones'])==89
            bone_error=max(abs(a-b) for old,new in zip(previous['bones'],current['bones']) for a,b in zip(old,new))
            root_error=max(abs(a-b) for a,b in zip(previous['root'],current['root']))
            palm_error=max(abs(a-b) for a,b in zip(previous['palms'],current['palms']))
            assert max(bone_error,root_error,palm_error)<1.e-6,('Paused feed pose moved',name,index,bone_error,root_error,palm_error)
            feed_errors[index]=dict(bone_transform_error=bone_error,root_transform_error=root_error,
                palm_position_error_cm=palm_error,pose_revision=components[index].get_pose_revision(),
                revision_delta=components[index].get_pose_revision()-baseline_revisions[index])
        value=json.loads(sim.get_simulation_report_json())
        assert [m['sim_time'] for m in value['machines']]==baseline_time
        assert subject.get_forced_lod()==0
        return dict(name=name,camera=camera_pose(),predicted_lod=subject.get_predicted_lod_level(),
            display_lod_changes=subject.get_display_lod_changes(),pose_revision=subject.get_pose_revision(),
            recently_rendered=subject.was_recently_rendered(.5),max_bone_transform_error=error,
            feed_native_pose_checks=feed_errors,
            bone_pose_sha256=hashlib.sha256(json.dumps(bones,separators=(',',':')).encode()).hexdigest())

    for name,distance,offscreen in [('far',18000,False),('near',350,False),
                                  ('far_return',18000,False),('offscreen',18000,True),
                                  ('near_reentry',350,False),('far_final',18000,False)]:
        rot=u.Rotator(pitch=-35,yaw=yaw)
        at=target-u.MathLibrary.get_forward_vector(rot)*distance
        if offscreen:
            # Rotate away at the same position: target is provably behind the
            # view, regardless of shadow passes' WasRecentlyRendered result.
            rot=u.Rotator(pitch=35,yaw=yaw+180)
            forward=u.MathLibrary.get_forward_vector(rot)
            delta=target-at
            assert forward.x*delta.x+forward.y*delta.y+forward.z*delta.z<0
        camera.set_actor_location_and_rotation(at,rot,False,True)
        pc.set_view_target_with_blend(camera,0)
        report['stage']='lod_'+name;write()
        yield from pause(3)
        row=snapshot(name)
        row['target_behind_camera']=offscreen
        row['settled_lods']=[row['predicted_lod']]
        for _ in range(4):
            yield from pause(.15)
            row['settled_lods'].append(subject.get_predicted_lod_level())
        assert len(set(row['settled_lods']))==1,('Automatic LOD oscillates after settle',row)
        diagnostic['stages'].append(row);write()
        if name in ('near','near_reentry'):
            png=OUT/('lod_'+name+'.png')
            console('Shot showui filename="'+png.as_posix()+'" -nosuffix')
            yield from wait(lambda:timing.png_ready(png),20)
            row['capture']=str(png)
    stages={s['name']:s for s in diagnostic['stages']}
    assert stages['near']['predicted_lod']<stages['far']['predicted_lod'],stages
    assert stages['far_return']['predicted_lod']==stages['far']['predicted_lod'],stages
    assert stages['near_reentry']['predicted_lod']==stages['near']['predicted_lod'],stages
    assert stages['far_final']['predicted_lod']==stages['far']['predicted_lod'],stages
    assert stages['near']['display_lod_changes']>stages['far']['display_lod_changes']
    assert stages['far_return']['display_lod_changes']>stages['near']['display_lod_changes']
    assert stages['far_final']['display_lod_changes']>stages['near_reentry']['display_lod_changes']
    diagnostic.update(success=True,simulation_time_unchanged=True,non_feed_pose_revisions_unchanged=True,
                      six_feed_native_bone_root_and_palm_poses_unchanged=True,
                      feed_pose_revision_note='Paused UpdateCentralDistribution resubmits identical feed poses; revision counts are diagnostic submissions, not movement.',
                      tested_far_near_far=True,tested_offscreen_reentry=True)
    write()
def run():
    global camera
    yield from wait(discover,45)
    assert list(pc.get_viewport_size())==[1920,1080]
    pawn.cancel_pose_transition();pawn.freeze_current_pose();pc.cancel_camera_drag()
    actors=list(u.GameplayStatics.get_all_actors_of_class(world,u.Actor))
    camera=next(a for a in actors if isinstance(a,u.CameraActor) and a.get_actor_label()=='MPR_ReviewCamera')
    camera.camera_component.set_editor_property('field_of_view',60.)
    camera.camera_component.set_editor_property('constrain_aspect_ratio',False)
    for a in actors:
        if a.actor_has_tag('MPR_Roof'):a.set_actor_hidden_in_game(True)
    for s in ['r.ScreenPercentage 100','r.VSync 0','t.MaxFPS 0','t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0','csv.CompressionMode 0','r.GPUCsvStatsEnabled 1','DisableAllScreenMessages']:
        console(s)
    sim.set_panel_visible(False)
    if not lod_only:
        for view in views:yield from sample(view)
    if phase=='before':yield from sample(views[0],diagnostic=True)
    else:yield from lod_diagnostics()
    report.update(success=True,stage='complete')
def finish(error=None):
    global finished
    finished=True
    if error:report.update(success=False,error=error)
    report['map_unchanged']=hashlib.sha256(map_path.read_bytes()).hexdigest()==original_sha
    report['success']=report['success'] and report['map_unchanged']
    report['elapsed_seconds']=time.monotonic()-start;write()
    u.unregister_slate_post_tick_callback(handle)
    if world:console('quit')
def tick(dt):
    if finished:return
    try:
        assert time.monotonic()-start<300
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
steps=run();handle=u.register_slate_post_tick_callback(tick)
