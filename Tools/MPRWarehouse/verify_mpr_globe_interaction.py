"""Verify the actual globe -> MPR -> globe lifecycle twice in an owned game."""
from pathlib import Path
import json
import re
import time
import traceback
import unreal as u

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Saved/MPR/roof_interaction_20261106/globe_runtime.json'
CLI=u.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)',CLI,re.I) for flag in ('own','game','RenderOffscreen','TwinDiagnostics'))
expected=json.loads((ROOT/'Saved/MPR/roof_interaction_20261106/runtime/report.json').read_text(encoding='utf8'))
assert expected['success']
fixed=expected['captures'][0]['camera']
report=dict(success=False,cycles=[],stage='discover')
world=pc=handle=None
busy=done=False
started=time.monotonic()

def write():OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def state():return json.loads(pc.get_state())
def command(action,**data):pc.command(json.dumps(dict(action=action,**data)))
def pose():
    m=pc.player_camera_manager;p=m.get_camera_location();r=m.get_camera_rotation()
    return [p.x,p.y,p.z,r.pitch,r.yaw,r.roll]
def same(a,b):return max(abs(x-y) for x,y in zip(a,b)) < .1
def wait(name,predicate,seconds=70):
    report['stage']=name;write();end=time.monotonic()+seconds
    while not predicate():
        assert time.monotonic()<end,(name,state() if pc else None)
        yield
def pause(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:yield
def discover():
    global world,pc
    for w in u.ObjectIterator(u.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_GlobalWarehouse.'):continue
        candidate=u.GameplayStatics.get_player_controller(w,0)
        if candidate and hasattr(candidate,'get_state'):
            world,pc=w,candidate
            return state()['phase']=='idle'
    return False
def run():
    yield from wait('globe_ready',discover)
    yield from pause(5)
    pawn=pc.get_controlled_pawn()
    for index in range(2):
        command('enter',id='mpr-nj')
        yield from wait('mpr_arrival_'+str(index),lambda:state()['phase']=='warehouse')
        yield from pause(.8)
        assert pc.get_controlled_pawn()==pawn
        assert same(pose(),fixed),('Entry pose differs from direct MPR entry',pose(),fixed)
        hud=pc.get_editor_property('twin_hud_widget');roof=pc.warehouse_roof
        assert hud and roof.has_roof() and roof.is_roof_closed()
        assert len(u.GameplayStatics.get_all_actors_with_tag(world,'MPR_Roof'))==30
        labels=json.loads(hud.get_poi_report())['labels']
        assert len(labels)==1 and labels[0]['id']=='WAREHOUSE:MPR'
        assert pc.get_editor_property('campus_traffic') is None and not hud.browser_ready
        label=labels[0];scale=hud.get_hud_scale()
        assert hud.handle_scene_click(u.Vector2D((label['x']+114)*scale,(label['y']+28)*scale))
        yield from wait('mpr_roof_open_'+str(index),roof.is_interior_available)
        assert same(pose(),fixed)
        assert all(a.get_editor_property('hidden') for a in u.GameplayStatics.get_all_actors_with_tag(world,'MPR_Roof'))
        command('back')
        yield from wait('return_to_globe_'+str(index),lambda:state()['phase'] in ('selected','idle'))
        assert pc.get_controlled_pawn()==pawn
        assert pc.get_editor_property('twin_hud_widget') is None
        assert not roof.has_roof() and not roof.is_component_tick_enabled()
        assert not u.GameplayStatics.get_all_actors_with_tag(world,'MPR_Roof')
        assert roof.get_open_progress()==0
        assert abs(pawn.get_editor_property('warehouse_camera').field_of_view-20)<.01
        report['cycles'].append(dict(cycle=index+1,passed=True,roof_parts=30,
            entry_camera=fixed,persistent_camera_preserved=True,roof_actors_unloaded=True))
        write();hud=None
    report.update(success=True,stage='complete');write()
def finish(error=None):
    global done
    done=True
    if error:report.update(success=False,error=error)
    write()
    if handle is not None:u.unregister_slate_post_tick_callback(handle)
    if world:u.SystemLibrary.quit_game(world,pc,u.QuitPreference.QUIT,False)
steps=run()
def tick(delta):
    global busy
    if busy or done:return
    busy=True
    try:
        assert time.monotonic()-started<220,'MPR globe lifecycle timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
    finally:busy=False
handle=u.register_slate_post_tick_callback(tick)
