"""Check actual replay-bar geometry throughout a native panel slide and reversal."""
from pathlib import Path
exec(Path('D:/UEPro/Test/Scripts/ghs/verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
OUT=ROOT/'Saved/OrderReplay/PanelMotion-20261026/runtime';OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={},motions=[])

CEF_AUDIT=r"""(function(){
 const original=window.twinReplayLayout,root=document.documentElement;
 const card=document.getElementById('replay-transport'),markers=document.getElementById('replay-markers');
 const rows=[];window.__replayPanelAudit={rows};
 window.twinReplayLayout=function(width,moving){
  const before=Array.from(markers.children),stateBefore=window.twinReplayOverlay.getState();
  const signature=s=>JSON.stringify([s.time,s.playing,s.rate,s.followId,s.trailMode,s.startUtc,s.duration]);
  const beforeState=signature(stateBefore);original(width,moving);
  const rect=window.TwinViewport.toLayoutRect(card.getBoundingClientRect());
  const children=Array.from(markers.children);
  rows.push({width,moving,innerWidth:window.innerWidth,rootTransform:root.style.transform,
   cardWidth:rect.width,cardLeft:rect.left,font:getComputedStyle(card).fontSize,
   visible:!card.hidden&&rect.width>0&&getComputedStyle(card).visibility!=='hidden',
   stateSame:beforeState===signature(window.twinReplayOverlay.getState()),
   markersSame:before.length===children.length&&before.every((node,i)=>node===children[i]),
   compact:root.getAttribute('data-replay-compact'),condensed:root.getAttribute('data-replay-condensed'),
   controls:width<=851?Array.from(card.querySelectorAll('.replay-transport-controls button')).map(el=>{
    const b=window.TwinViewport.toLayoutRect(el.getBoundingClientRect());return{label:el.textContent.trim(),left:b.left,right:b.right,top:b.top,bottom:b.bottom};}):[]});
 };
})();"""


def cef_report(token,script=''):
    """Use the real replay CEF bridge, with a token immune to panel reports."""
    result={}
    hud.evaluate_diagnostics(script+";window.ue.twin.command(JSON.stringify({action:'report',replayAuditToken:"
        +json.dumps(token)+",rows:window.__replayPanelAudit.rows}));",True)
    def received():
        try:value=json.loads(hud.last_browser_report)
        except (ValueError,TypeError):return False
        if value.get('replayAuditToken')!=token:return False
        result.update(value);return True
    yield from wait('CEF '+token,received,10)
    return result['rows']


def verify_cef_rows(rows):
    assert rows,'Missing real CEF layout calls'
    first=rows[0]
    assert any(row['moving'] for row in rows),'Missing moving CEF frames'
    assert rows[-1]['moving'] is False,'Missing settled CEF frame'
    for row in rows:
        assert abs(row['cardWidth']-(row['width']-8))<.2,('CEF card width drift',row)
        assert abs(row['cardLeft']-4)<.2,('CEF card left drift',row)
        assert row['innerWidth']==first['innerWidth'],('CEF backing surface resized',row)
        assert row['rootTransform']==first['rootTransform'] and row['font']==first['font'],('Text/root scaled',row)
        assert row['visible'] and row['stateSame'],('CEF blanked or replay state reset',row)
        if row['moving']:assert row['markersSame'],('Markers rebuilt during motion',row)
    return dict(frames=len(rows),moving_frames=sum(row['moving'] for row in rows),
                inner_width=first['innerWidth'],font=first['font'])


def layout():
    overlay=next(w for w in unreal.ObjectIterator(unreal.Widget) if w.get_name()=='ReplayTransport')
    browser=overlay.get_editor_property('slot')
    parent=overlay.get_parent()
    clip=parent.get_editor_property('slot') if parent.get_name()=='ReplayTransportClip' else browser
    return dict(progress=hud.get_panel_transition_progress(),panel_x=hud.get_panel_visual_position().x,
                x=clip.get_position().x,y=clip.get_position().y,width=clip.get_size().x,
                browser_width=browser.get_size().x,visible=overlay.is_visible(),
                time=state()['time'],playing=state()['playing'])


def toggle():
    pixels=hud.get_viewport_pixel_size()
    assert hud.handle_chrome_click(unreal.Vector2D(pixels.x-30,25))


def motion(name,opening,reverse=False):
    before=layout();samples=[before];toggle()
    assert abs(layout()['width']-before['width'])<.01
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        yield
        row=layout();samples.append(row)
        expected=max(320.,row['panel_x']-48)
        assert abs(row['width']-expected)<.1,('Timeline does not follow animated panel edge',row,expected)
        assert row['visible'] and row['time']==before['time'] and row['playing']==before['playing']
        assert abs(row['browser_width']-1872)<.1,('CEF viewport must stay constant',row)
        delta=row['width']-samples[-2]['width']
        assert delta<=.1 if opening else delta>=-.1
        if reverse and .35<row['progress']<.65:break
        if not reverse and abs(row['progress']-(1 if opening else 0))<.0001:break
    assert any(.01<r['progress']<.99 for r in samples),'Missing intermediate animation frames'
    if not reverse:assert abs(samples[-1]['progress']-(1 if opening else 0))<.0001
    report['motions'].append(dict(name=name,samples=samples));record(name,samples=len(samples))


def run():
    yield from wait('discover',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    command('navigate',page='trace');hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    yield from wait('prepared',lambda:not state()['preparing'] and not pawn.is_pose_transition_active())
    command('replayPause');command('replaySeek',time=230);yield from pause(.5)
    yield from cef_report('installed',CEF_AUDIT)
    yield from capture('01-expanded')
    yield from motion('collapse',False)
    yield from pause(.4);yield from capture('02-collapsed')
    rows=yield from cef_report('collapse')
    record('cef-collapse',**verify_cef_rows(rows));report['cef_motions']=dict(collapse=rows)
    yield from cef_report('reset-expand','window.__replayPanelAudit.rows.length=0')
    yield from motion('expand',True)
    yield from pause(.4);yield from capture('03-expanded')
    rows=yield from cef_report('expand')
    record('cef-expand',**verify_cef_rows(rows));report['cef_motions']['expand']=rows
    yield from cef_report('reset-reverse','window.__replayPanelAudit.rows.length=0')
    yield from motion('partial-collapse',False,True)
    yield from motion('reverse-to-expand',True)
    yield from pause(.2)
    rows=yield from cef_report('reverse')
    record('cef-reverse',**verify_cef_rows(rows));report['cef_motions']['reverse']=rows
    # Exercise the real CEF's visible-width breakpoints while its surface stays
    # full size. Native animation geometry is verified separately above.
    rows=yield from cef_report('responsive',"window.__replayPanelAudit.rows.length=0;[851,850,651,650].forEach(w=>window.twinReplayLayout(w,false))")
    assert [row['width'] for row in rows]==[851,850,651,650],rows
    for row in rows:
        assert row['compact']==('true' if row['width']<=650 else 'false'),row
        assert row['condensed']==('true' if row['width']<=850 else 'false'),row
        assert abs(row['cardWidth']-(row['width']-8))<.2 and row['stateSame'],row
        assert len(row['controls'])==7,row
        assert all(b['left']>=4 and b['right']<=row['width']-4+.2 and b['top']>=0 and b['bottom']<=168 for b in row['controls']),('Responsive control clipped',row)
    report['cef_responsive']=rows;record('cef-visible-width-breakpoints',widths=[851,850,651,650])
    yield from capture('04-cef-visible-width-650')
    yield from cef_report('restore-width','window.twinReplayLayout('+str(layout()['width'])+',false)')
    command('replayEndRequest');command('replayExitConfirm')
    assert json.loads(session.get_restoration_report())['verified']
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==map_hash
    record('scene_restored_and_saved_map_unchanged',sha256=map_hash)


steps=run()


def tick(delta):
    try:
        assert time.monotonic()-started<180,'Panel verification timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())


write();handle=unreal.register_slate_post_tick_callback(tick)
