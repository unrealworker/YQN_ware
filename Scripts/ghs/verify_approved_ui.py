"""Validate the approved HUD in an owned offscreen game; never save assets."""
import json, re, time, traceback
from pathlib import Path
import unreal

ROOT=Path(r'D:/UEPro/Test')
OUT=ROOT/'Saved/PixelStreaming/UIReview'
OUT.mkdir(parents=True,exist_ok=True)
CLI=unreal.SystemLibrary.get_command_line()
assert re.search(r'(?:^|\s)-game(?:\s|$)',CLI,re.I) and '-RenderOffscreen' in CLI
started=time.monotonic(); step=0; next_at=0; handle=None; world=pc=widget=None
result={'success':False,'checks':[],'assets_saved':False}
def write(): (OUT/'native-runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
def record(name,**fields): result['checks'].append(dict(name=name,passed=True,**fields));write()
def discover():
    global world,pc,widget
    for w in unreal.ObjectIterator(unreal.World):
        p=unreal.GameplayStatics.get_player_controller(w,0)
        if p and hasattr(p,'twin_hud_widget') and p.get_editor_property('twin_hud_widget'):
            world,pc,widget=w,p,p.get_editor_property('twin_hud_widget');break
    if not widget or not widget.get_editor_property('browser_ready'):return False
    snap=json.loads(widget.get_snapshot())
    assert len(snap['equipment'])==106 and len(snap['facilities'])==56
    record('real_scene_and_browser_ready',equipment=len(snap['equipment']),facilities=len(snap['facilities']))
def capture(name):
    path=OUT/(name+'.png')
    unreal.SystemLibrary.execute_console_command(world,'Shot showui filename="'+path.as_posix()+'" -nosuffix',pc)
def check_badges():
    report=json.loads(widget.get_poi_report())
    picked=[r for r in report['labels'] if r['selected']]
    assert picked and picked[0]['id']=='FORK-07',report
    assert report['selectionStroke']==6
    for label in report['labels']:
        assert abs(label['badgeInkTop']-(label['badgeHeight']-label['badgeInkBottom']))<.1,label
        assert label['badgeInkTop']>=0 and label['badgeInkBottom']<=24,label
    record('glyph_ink_centered_and_selected_frame_6px',poi=report)
def check_search():
    state=json.loads(widget.get_search_state(False))
    assert state['visible'] and state['rect']['height']==48,state
    assert state['rect']['x']+state['rect']['width']<=state['viewport']['width'],state
    record('search_geometry',state=state)
def reset_check():
    assert widget.get_editor_property('selected_id')==''
    assert not any(r['selected'] for r in json.loads(widget.get_poi_report())['labels'])
    record('overview_clears_selection')
def finish(error=None):
    result.update(success=error is None,error=error,elapsed=time.monotonic()-started)
    write()
    if handle:unreal.unregister_slate_post_tick_callback(handle)
    unreal.log('APPROVED_UI_'+('FAILED' if error else 'PASSED'))
    if world:unreal.SystemLibrary.execute_console_command(world,'quit',pc)
steps=[(discover,2),(lambda:capture('native-overview'),.5),(check_search,.1),
       (lambda:widget.select_object('FORK-07',True),2),(check_badges,.1),
       (lambda:capture('native-forklift-selected'),.5),
       (lambda:widget.command('{"action":"zoomIn"}'),.8),
       (lambda:widget.command('{"action":"overview"}'),1.2),(reset_check,.1)]
def tick(dt):
    global step,next_at
    try:
        assert time.monotonic()-started<180,'Runtime verification timed out'
        if time.monotonic()<next_at:return
        if step==len(steps):finish();return
        action,delay=steps[step]
        if action() is False:return
        step+=1;next_at=time.monotonic()+delay
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
