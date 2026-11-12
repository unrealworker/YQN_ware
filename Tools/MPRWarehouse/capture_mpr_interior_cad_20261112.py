"""Fixed native game captures and CSV timing before/after the CAD correction."""
from pathlib import Path
import json,math,sys,time,traceback,hashlib
import unreal as u
ROOT=Path('D:/UEPro/Test');sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as timing
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
stage='before' if '-mprinteriorbefore' in u.SystemLibrary.get_command_line().lower() else 'after'
detail='-mprinteriordetail' in u.SystemLibrary.get_command_line().lower()
if detail:stage='details'
OUT=ROOT/'Saved/MPR/interior_cad_20261112/runtime'/stage;OUT.mkdir(parents=True,exist_ok=True)
placement=json.loads((ROOT/'SourceAssets/MPR/interior_cad_20261112/racks/placement_manifest.json').read_text(encoding='utf8'))
views=[dict(name='01-interior-overview',target=[0,0,450],distance=47000,pitch=-62,yaw=-90)]
for family in ('16','17+1','20','9','5','7'):
    items=[r for r in placement['instances'] if r['family']==family and not r['passage_variant']]
    r=min(items,key=lambda r:sum(v*v for v in r['original_transform']['translation_cm'][:2]))
    target=r['original_transform']['translation_cm'][:];target[2]=470
    views.append(dict(name='rack-'+family.replace('+','P'),target=target,distance=2600,pitch=-42,yaw=18))
r=next(r for r in placement['instances'] if r['family']=='20' and r['passage_variant'])
target=r['original_transform']['translation_cm'][:];target[2]=240
views.append(dict(name='08-drive-through',target=target,distance=1400,pitch=-5,yaw=0))
views.append(dict(name='09-office-doors',target=[17200,6500,180],distance=5200,pitch=-48,yaw=155))
if detail:
    views=[dict(name='east-office-windows',target=[18250,-4850,170],distance=1500,pitch=-12,yaw=170),
           dict(name='south-personnel-entrance',target=[1620,8500,70],distance=1000,pitch=-20,yaw=-70),
           dict(name='northwest-window-openings',target=[-16806,-8344,240],distance=1000,pitch=-15,yaw=80)]
report=dict(success=False,stage=stage,views=views,captures=[],resolution=[1920,1080],
            map_sha256=hashlib.sha256((ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap').read_bytes()).hexdigest(),
            conditions='Native -game, automatic sorter simulation, 100 percent screen resolution, other project editor closed during performance measurement.')
started=time.monotonic();world=pc=pawn=camera=None;handle=None;done=False;index=0;phase='discover';ready=0;pending=None


def console(s):u.SystemLibrary.execute_console_command(world,s,pc)
def pose():
    c=pc.player_camera_manager;p=c.get_camera_location();r=c.get_camera_rotation()
    return [p.x,p.y,p.z,r.pitch,r.yaw,r.roll]
def set_view():
    global ready
    v=views[index];rot=u.Rotator(pitch=v['pitch'],yaw=v['yaw'])
    target=u.Vector(*v['target'])
    camera.set_actor_location_and_rotation(target-u.MathLibrary.get_forward_vector(rot)*v['distance'],rot,False,True)
    pc.set_view_target_with_blend(camera,0);ready=time.monotonic()
def finish(error=None):
    global done
    done=True
    if handle:u.unregister_slate_post_tick_callback(handle)
    report.update(success=error is None,error=error,elapsed_seconds=time.monotonic()-started)
    assert report['map_sha256']==hashlib.sha256((ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap').read_bytes()).hexdigest()
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    console('quit')
def tick(dt):
    global world,pc,pawn,camera,index,phase,ready,pending
    if done:return
    try:
        assert time.monotonic()-started<240
        if phase=='discover':
            for w in u.ObjectIterator(u.World):
                if not w.get_path_name().startswith(MAP+'.'):continue
                controller=u.GameplayStatics.get_player_controller(w,0)
                if controller:world=w;pc=controller;break
            if not world:return
            pawn=pc.get_controlled_pawn()
            if not pawn:return
            assert list(pc.get_viewport_size())==[1920,1080]
            pawn.cancel_pose_transition();pawn.freeze_current_pose();pc.cancel_camera_drag()
            actors=list(u.GameplayStatics.get_all_actors_of_class(world,u.Actor))
            camera=next(a for a in actors if isinstance(a,u.CameraActor) and a.get_actor_label()=='MPR_ReviewCamera')
            for actor in actors:
                if actor.actor_has_tag('MPR_Roof'):actor.set_actor_hidden_in_game(True)
            component=camera.get_component_by_class(u.CameraComponent)
            component.set_editor_property('constrain_aspect_ratio',False)
            component.set_editor_property('field_of_view',60.)
            console('r.ScreenPercentage 100');console('r.VSync 0');console('t.MaxFPS 0')
            console('r.SetNearClipPlane 10');console('DisableAllScreenMessages')
            console('t.IdleWhenNotForeground 0');console('Slate.bAllowThrottling 0')
            console('csv.CompressionMode 0');console('r.GPUCsvStatsEnabled 1')
            report['runtime_actor_count']=len(actors)
            report['simulation_actor_count']=sum(a.get_class().get_name()=='MPRSorterSimulationActor' for a in actors)
            set_view();phase='capture';return
        if phase=='capture':
            if pending:
                if not timing.png_ready(pending):return
                report['captures'].append(dict(name=views[index]['name'],file=str(pending),camera=pose()))
                pending=None;index+=1
                if index==len(views):
                    if detail:finish();return
                    index=0;set_view();phase='warm';return
                set_view()
            elif time.monotonic()-ready>(12 if index==0 else 3):
                pending=OUT/(views[index]['name']+'.png')
                assert not pending.exists()
                console('Shot filename="'+pending.as_posix()+'" -nosuffix')
        elif phase=='warm' and time.monotonic()-ready>8:
            report['performance_camera']=pose()
            report['csv_filename']='MPR_INTERIOR_CAD_'+stage+'_'+str(time.time_ns())+'.csv'
            console('CsvProfile STARTFILE='+report['csv_filename']);console('CsvProfile START')
            ready=time.monotonic();phase='sample'
        elif phase=='sample' and time.monotonic()-ready>15:
            console('CsvProfile STOP');ready=time.monotonic();phase='flush'
        elif phase=='flush':
            path=ROOT/'Saved/Profiling/CSV'/report['csv_filename']
            if not timing.csv_complete(path):
                assert time.monotonic()-ready<20;return
            native=timing.parse_csv(path)
            native['fps']=native['frame_count']/native['native_frame_time_seconds']
            report['performance']=native;finish()
    except Exception:finish(traceback.format_exc())
handle=u.register_slate_post_tick_callback(tick)
