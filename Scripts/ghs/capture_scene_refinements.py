"""Capture occupied/empty storage and blue AGV effects in an owned game."""
import json
import time
import traceback
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test')
assert '-RenderOffscreen' in unreal.SystemLibrary.get_command_line()
start=time.monotonic(); index=0; next_at=0; world=pc=widget=None; handle=None
shots=[('racks',dict(action='preset',value='racks')),('floor',dict(action='preset',value='floor')),
       ('agv34',dict(action='select',id='AGV-34',focus=True))]
report=dict(success=False,captures=[])
def tick(dt):
    global world,pc,widget,index,next_at,handle
    try:
        if not widget:
            for w in unreal.ObjectIterator(unreal.World):
                p=unreal.GameplayStatics.get_player_controller(w,0)
                if p and hasattr(p,'twin_hud_widget') and p.get_editor_property('twin_hud_widget'):
                    world,pc,widget=w,p,p.get_editor_property('twin_hud_widget');break
            if not widget or not widget.get_editor_property('browser_ready'):return
            next_at=time.monotonic()+1
        if time.monotonic()<next_at:return
        if index>=len(shots)*2:
            report['success']=all(Path(p).is_file() and Path(p).stat().st_size>10000 for p in report['captures'])
            assert report['success']
            unreal.unregister_slate_post_tick_callback(handle)
            (ROOT/'Saved/SceneRefinements/views.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            unreal.SystemLibrary.execute_console_command(world,'quit',pc);return
        name,command=shots[index//2]
        if index%2==0:
            if name=='agv34': assert widget.select_object('AGV-34',True)
            else:
                label='GHS_V2_Rack_B_W37619' if name=='racks' else 'GHS_CAD_PalletCargo'
                actor=next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor) if a.get_actor_label()==label)
                c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                transform=c.get_instance_transform(0,world_space=True)
                center=unreal.MathLibrary.transform_location(transform,c.static_mesh.get_bounds().origin)
                pawn=pc.get_controlled_pawn()
                pawn.focus_on_target(center,2200 if name=='racks' else 3500,
                    unreal.Rotator(pitch=-30,yaw=-110,roll=0),unreal.Vector2D(1920,1080),unreal.Vector2D(720,572),.85)
            next_at=time.monotonic()+2.5
        else:
            path=ROOT/('Saved/SceneRefinements/'+name+'.png')
            unreal.SystemLibrary.execute_console_command(world,f'Shot showui filename="{path.as_posix()}" -nosuffix',pc)
            report['captures'].append(str(path));next_at=time.monotonic()+.6
        index+=1
    except Exception:
        report['error']=traceback.format_exc()
        (ROOT/'Saved/SceneRefinements/views.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.SystemLibrary.execute_console_command(world,'quit',pc)
handle=unreal.register_slate_post_tick_callback(tick)
