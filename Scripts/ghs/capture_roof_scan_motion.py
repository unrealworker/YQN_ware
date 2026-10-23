"""Capture actual UE frames on a fixed 60 Hz simulation clock, not a performance test."""
import hashlib,json,re,time,traceback
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/RoofScan/MotionFrames';OUT.mkdir(parents=True,exist_ok=True)
CLI=unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)',CLI,re.I) for flag in ('game','RenderOffscreen','TwinDiagnostics','UseFixedTimeStep'))
assert '-FPS=60' in CLI
world=pc=hud=roof=pawn=None;handle=None;done=False;warm=0;frame=0;start=time.monotonic();trace=[]
MAP=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap';MAP_HASH=hashlib.sha256(MAP.read_bytes()).hexdigest()
def console(cmd):unreal.SystemLibrary.execute_console_command(world,cmd,pc)
def discover():
    global world,pc,hud,roof,pawn
    for w in unreal.ObjectIterator(unreal.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):continue
        c=unreal.GameplayStatics.get_player_controller(w,0);h=getattr(c,'twin_hud_widget',None) if c else None
        if not h or not h.browser_ready:continue
        world,pc,hud=w,c,h;roof=pc.warehouse_roof;pawn=pc.get_controlled_pawn();return True
    return False
def finish(error=None):
    global done
    done=True
    data=dict(success=error is None,error=error,fps=60,frames=frame,trace=trace,
              scope='Actual UE rendered frames, fixed 1/60 simulation timestep; playback is not a wall-time performance measurement',
              map_preserved=hashlib.sha256(MAP.read_bytes()).hexdigest()==MAP_HASH)
    (OUT/'capture.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    if handle is not None:unreal.unregister_slate_post_tick_callback(handle)
    if world:unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)
def tick(delta):
    global warm,frame
    if done:return
    try:
        assert time.monotonic()-start<180,'Capture timeout'
        if not hud and not discover():return
        if pawn.is_pose_transition_active():return
        if warm<90:
            warm+=1
            if warm==1:console('DisableAllScreenMessages')
            return
        if frame>=126:
            paths=list(OUT.glob('frame-*.png'))
            if len(paths)==126 and all(p.stat().st_size>10000 for p in paths):finish()
            return
        if frame==18:assert hud.open_warehouse()
        if frame==78:roof.restore_roof(True)
        trace.append(dict(frame=frame,phase=roof.get_transition_phase(),progress=roof.get_open_progress(),
                          opening=roof.is_opening(),closing=roof.is_closing(),closed=roof.is_roof_closed()))
        console('Shot showui filename="'+(OUT/f'frame-{frame:04d}.png').as_posix()+'" -nosuffix')
        frame+=1
    except Exception:finish(traceback.format_exc())
handle=unreal.register_slate_post_tick_callback(tick)
