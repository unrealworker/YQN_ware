"""Read-only asset regression: overview must clear an actual device selection."""
import json,time,traceback
from pathlib import Path
import unreal
assert '-RenderOffscreen' in unreal.SystemLibrary.get_command_line()
root=Path(r'D:/UEPro/Test'); started=time.monotonic(); handle=None
def tick(dt):
    for w in unreal.ObjectIterator(unreal.World):
        pc=unreal.GameplayStatics.get_player_controller(w,0)
        if not pc or not hasattr(pc,'twin_hud_widget'): continue
        hud=pc.get_editor_property('twin_hud_widget')
        if not hud or not hud.get_editor_property('browser_ready'): continue
        try:
            assert hud.select_object('AGV-07',False)
            hud.command('{"action":"overview"}')
            assert not hud.get_editor_property('selected_id'), 'Overview retained AGV-07 selection'
            result=dict(success=True)
        except Exception: result=dict(success=False,error=traceback.format_exc())
        (root/'Saved/PanelSlide_ResetBaseline.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.SystemLibrary.execute_console_command(w,'quit',pc)
        return
    if time.monotonic()-started>60:
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.SystemLibrary.quit_editor()
handle=unreal.register_slate_post_tick_callback(tick)
