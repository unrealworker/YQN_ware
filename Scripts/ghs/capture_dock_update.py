"""Capture both numbered facades and full floor cargo in an owned game."""
import json
import time
import traceback
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/DockNumbers'
assert '-RenderOffscreen' in unreal.SystemLibrary.get_command_line()
rows=json.loads((ROOT/'SourceAssets/GHS/ZcoolDockNumbers.json').read_text(encoding='utf-8'))['rows']
start=time.monotonic();index=0;next_at=0;world=pc=widget=None;handle=None
shots=[('doors_1_3',2),('doors_57_61',59),('doors_85_87',86),('floor_full',0),('rack_gaps',-1)]
result=dict(success=False,captures=[])
def finish(error=None):
    result.update(success=error is None,error=error)
    (OUT/'views.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    unreal.unregister_slate_post_tick_callback(handle)
    if world:unreal.SystemLibrary.execute_console_command(world,'quit',pc)
def tick(dt):
    global world,pc,widget,index,next_at,handle
    try:
        assert time.monotonic()-start<100,'Capture timeout'
        if not widget:
            for w in unreal.ObjectIterator(unreal.World):
                p=unreal.GameplayStatics.get_player_controller(w,0)
                if p and hasattr(p,'twin_hud_widget') and p.get_editor_property('twin_hud_widget'):
                    world,pc,widget=w,p,p.get_editor_property('twin_hud_widget');break
            if not widget or not widget.get_editor_property('browser_ready'):return
            next_at=time.monotonic()+1
        if time.monotonic()<next_at:return
        if index>=len(shots)*2:
            assert all(Path(p).is_file() and Path(p).stat().st_size>10000 for p in result['captures'])
            finish();return
        name,number=shots[index//2]
        if index%2==0:
            pawn=pc.get_controlled_pawn()
            if number>0:
                row=rows[number-1]
                pawn.focus_on_target(unreal.Vector(*row['location']),1900,
                    unreal.Rotator(pitch=-12,yaw=row['yaw']+180),unreal.Vector2D(1920,1080),unreal.Vector2D(720,572),.8)
            else:
                label='GHS_CAD_PalletCargo' if number==0 else 'GHS_V2_Rack_B_W37619'
                actor=next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor) if a.get_actor_label()==label)
                c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                t=c.get_instance_transform(0,world_space=True)
                center=unreal.MathLibrary.transform_location(t,c.static_mesh.get_bounds().origin)
                pawn.focus_on_target(center,3500 if number==0 else 2200,
                    unreal.Rotator(pitch=-30,yaw=-110),unreal.Vector2D(1920,1080),unreal.Vector2D(720,572),.8)
            next_at=time.monotonic()+2.5
        else:
            path=OUT/(name+'.png')
            unreal.SystemLibrary.execute_console_command(world,f'Shot showui filename="{path.as_posix()}" -nosuffix',pc)
            result['captures'].append(str(path));next_at=time.monotonic()+1
        index+=1
    except Exception:finish(traceback.format_exc())
handle=unreal.register_slate_post_tick_callback(tick)
