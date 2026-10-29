"""Measure production UI motion in an owned UE CEF process, without saving assets.

Launch UnrealEditor Test.uproject /Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory
  -game -RenderOffscreen -TwinDiagnostics -ForceRes -ResX=1920 -ResY=1080
  -UIMotionRun=baseline -ExecCmds="t.MaxFPS 60,r.VSync 0,py D:/UEPro/Test/Scripts/ghs/verify_ui_motion_performance.py"
All output is under Saved/UIMotion. No fixed timestep: RAF and bridge timings use
wall time. Reported RAF intervals measure the CEF renderer, not streamed video.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
import unreal

ROOT = Path('D:/UEPro/Test')
CLI = unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-' + flag + r'(?=\s|$)', CLI, re.I)
           for flag in ('game', 'RenderOffscreen', 'TwinDiagnostics'))
assert not re.search(r'-UseFixedTimeStep\b', CLI, re.I), 'Performance requires wall time'
LABEL_MATCH = re.search(r'-UIMotionRun=([A-Za-z0-9_-]+)', CLI, re.I)
LABEL = LABEL_MATCH.group(1) if LABEL_MATCH else 'measurement'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
OUT = ROOT / 'Saved/UIMotion' / ('performance_' + LABEL + '_' + STAMP)
OUT.mkdir(parents=True, exist_ok=True)
MAP = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
FILES = ('app.js', 'motion.js', 'motion.css', 'index.html')
START = time.monotonic()
stage = 'discover'
world = pc = hud = pawn = handle = None
serial = 0
result = dict(success=False, run=LABEL, samples=[], checks=[], output=str(OUT),
              assets_saved=False, scope='Owned local UE CEF; no remote/video/network FPS claim',
              instrumentation='RAF, PerformanceObserver longtask, synchronous TwinMotion hooks; diagnostic reports disabled while sampling',
              timing_notes='JS click dispatch excludes OS pointer latency. roundtripOverSampleMs includes native-to-CEF injection plus CEF-to-native report delivery; it is not network latency. RAF callbacks can miss compositor-only frames. navigation220 includes frame intervals beginning within 220ms of the latest action, including intervals crossing its boundary; after220 includes later intervals. callback intervals use actual performance.now wall times.',
              map_sha256_before=hashlib.sha256(MAP.read_bytes()).hexdigest(),
              ui_sha256={name: hashlib.sha256((ROOT/'Content/GHSTwinUI/web'/name).read_bytes()).hexdigest() for name in FILES})


def write():
    result.update(stage=stage, elapsed_seconds=time.monotonic()-START)
    (OUT/'performance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT/'Saved/UIMotion'/('performance-'+LABEL+'-latest.json')).write_text(json.dumps(dict(
        success=result['success'], stage=stage, report=str(OUT/'performance.json'),
        elapsed_seconds=result['elapsed_seconds'], error=result.get('error')), ensure_ascii=False, indent=2), encoding='utf-8')


def wait(name, predicate, seconds=20):
    global stage
    stage = name
    deadline = time.monotonic()+seconds
    while not predicate():
        assert time.monotonic() < deadline, 'Timed out: '+name
        yield


def pause(seconds):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        yield


def report():
    raw = hud.get_editor_property('last_browser_report') if hud else ''
    return json.loads(raw) if raw else {}


def discover():
    global world, pc, hud, pawn
    for candidate in unreal.ObjectIterator(unreal.World):
        if not candidate.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        widget = getattr(controller, 'twin_hud_widget', None) if controller else None
        if widget and widget.browser_ready:
            world, pc, hud, pawn = candidate, controller, widget, controller.get_controlled_pawn()
            return bool(report().get('business'))
    return False


INSTALL = r"""(()=>{
if(window.__motionPerf)return;
const motion=window.TwinMotion, main=document.getElementById('main'), nav=document.getElementById('navigation');
const P=window.__motionPerf={active:null,errors:[],snapshot:null};
const round=n=>Math.round(n*1000)/1000;
const summary=values=>{const a=values.slice().sort((a,b)=>a-b),n=a.length;
 return {count:n,mean:n?round(a.reduce((x,y)=>x+y,0)/n):0,p50:n?round(a[Math.floor((n-1)*.5)]):0,
 p95:n?round(a[Math.floor((n-1)*.95)]):0,max:n?round(a[n-1]):0,over25:a.filter(v=>v>25).length,over50:a.filter(v=>v>50).length};};
const current=()=>({page:window.twinState.page,detail:window.twinState.detail,
 busy:main.getAttribute('aria-busy')==='true',active:nav.querySelector('[aria-current="page"]')?.dataset.page,
 motion:motion.diagnostics(),performance:window.twinGetPerformance()});
const alignment=()=>{const a=nav.querySelector('[aria-current="page"]'),p=nav.querySelector('.motion-nav-highlight');
 if(!a||!p)return null;const ar=a.getBoundingClientRect(),pr=p.getBoundingClientRect();
 return {x:round(pr.x),y:round(pr.y),targetX:round(ar.x),targetY:round(ar.y),distance:round(Math.hypot(pr.x-ar.x,pr.y-ar.y))};};
for(const name of ['beforePaint','afterPaint','navigation']){
 const original=motion[name];motion[name]=function(...args){const s=P.active,t=performance.now();
  try{return original.apply(this,args);}finally{if(s)s.hooks[name].push(performance.now()-t);}};
}
window.addEventListener('error',e=>P.errors.push(String(e.message)));
window.addEventListener('unhandledrejection',e=>P.errors.push(String(e.reason)));
P.longtaskSupported=typeof PerformanceObserver==='function'&&PerformanceObserver.supportedEntryTypes.includes('longtask');
if(P.longtaskSupported)new PerformanceObserver(list=>{const s=P.active;if(s)for(const e of list.getEntries())
 if(e.startTime>=s.start)s.longTasks.push({atMs:round(e.startTime-s.start),durationMs:round(e.duration)});
}).observe({entryTypes:['longtask']});
function frame(t,token){const s=P.active;if(!s||s.token!==token)return;
 const elapsed=performance.now()-s.start;
 if(s.last!==null){const interval=t-s.last,callback=elapsed-s.lastElapsed;
  const phase=s.lastElapsed<s.lastActionMs+220?'navigation220':'after220';
  s.frames.push(interval);s.framePhases[phase].push(interval);s.callbackPhases[phase].push(callback);
  if(callback>25)s.gaps.push({atMs:round(s.lastElapsed),phase,rafMs:round(interval),callbackMs:round(callback)});
 }s.last=t;s.lastElapsed=elapsed;
 if(s.firstFrameMs===null)s.firstFrameMs=elapsed;
 if(s.firstIdleMs===null&&elapsed>=s.lastActionMs&&main.getAttribute('aria-busy')!=='true')s.firstIdleMs=elapsed;
 const diagnostics=motion.diagnostics();
 if(diagnostics.chartCreates!==s.lastChartCreates){s.chartCreationEvents.push({atMs:round(elapsed),count:diagnostics.chartCreates-s.lastChartCreates});s.lastChartCreates=diagnostics.chartCreates;}
 if(s.chartsReadyMs===null&&main.getAttribute('aria-busy')!=='true'&&!(diagnostics.pendingCharts||0)){
  const nodes=[...document.querySelectorAll('#page [data-motion-chart]')];
  if(nodes.every(n=>n.classList.contains('motion-chart-ready')&&n.querySelector('.motion-chart svg')))s.chartsReadyMs=elapsed;
 }
 if(s.positions.length<24&&elapsed>=s.positions.length*25&&elapsed<600)s.positions.push({atMs:round(elapsed),...alignment()});
 requestAnimationFrame(t=>frame(t,token));
}
P.run=function(token,name,action,duration){
 if(P.active)throw new Error('Overlapping performance sample');
 const s=P.active={token,name,start:performance.now(),frames:[],last:null,lastElapsed:null,firstFrameMs:null,firstIdleMs:null,lastActionMs:0,
 framePhases:{navigation220:[],after220:[]},callbackPhases:{navigation220:[],after220:[]},gaps:[],
 chartsReadyMs:null,chartCreationEvents:[],lastChartCreates:motion.diagnostics().chartCreates,
 hooks:{beforePaint:[],afterPaint:[],navigation:[]},longTasks:[],positions:[],actions:[],before:current()};
 P.action=function(label,fn){s.lastActionMs=performance.now()-s.start;s.firstIdleMs=null;s.chartsReadyMs=null;const t=performance.now();fn();
  s.actions.push({label,atMs:round(t-s.start),handlerMs:round(performance.now()-t),page:window.twinState.page,
   active:nav.querySelector('[aria-current="page"]')?.dataset.page});};
 requestAnimationFrame(t=>frame(t,token));action();
 setTimeout(()=>{if(P.active!==s)return;P.active=null;
  const after=current(),delta={};for(const k of ['chartCreates','chartUpdates','chartDisposes','numberUpdates'])delta[k]=(after.motion[k]||0)-(s.before.motion[k]||0);
  const out={name,elapsedMs:round(performance.now()-s.start),firstFrameMs:round(s.firstFrameMs||0),
   firstIdleMs:s.firstIdleMs===null?null:round(s.firstIdleMs),raf:summary(s.frames),
   rafPhases:Object.fromEntries(Object.entries(s.framePhases).map(([k,v])=>[k,summary(v)])),
   callbackPhases:Object.fromEntries(Object.entries(s.callbackPhases).map(([k,v])=>[k,summary(v)])),
   frameGaps:s.gaps.sort((a,b)=>b.callbackMs-a.callbackMs).slice(0,12),
   chartsReadyMs:s.chartsReadyMs===null?null:round(s.chartsReadyMs),lastActionMs:round(s.lastActionMs),chartCreationEvents:s.chartCreationEvents.slice(0,16),
   largestGapsMs:s.frames.slice().sort((a,b)=>b-a).slice(0,8).map(round),
   hooks:Object.fromEntries(Object.entries(s.hooks).map(([k,v])=>[k,summary(v)])),
   longTasks:s.longTasks.slice(0,12),longtaskSupported:P.longtaskSupported,positions:s.positions,
   actions:s.actions,before:s.before,after,lifecycleDelta:delta,alignment:alignment(),errors:P.errors.slice(-5)};
  window.ue.twin.command(JSON.stringify({action:'report',motionPerfToken:token,sample:out}));
 },duration);
};
P.click=page=>P.action(page,()=>document.querySelector('#navigation [data-page="'+page+'"]').click());
window.twinSetDiagnostics(false);
})()"""


def sample(name, action, duration=1300, expected=None, native_actions=()):
    global serial, stage
    serial += 1
    token = serial
    stage = name
    write()
    start = time.monotonic()
    hud.evaluate_diagnostics('window.__motionPerf.run(%d,%s,()=>{%s},%d);' % (token, json.dumps(name), action, duration))
    pending = list(native_actions)
    performed = []
    while report().get('motionPerfToken') != token:
        elapsed = time.monotonic()-start
        assert elapsed < 12, 'Timed out: '+name
        while pending and elapsed >= pending[0][0]:
            _, label, callback = pending.pop(0)
            assert callback(), 'Native action failed: '+label
            performed.append(dict(label=label, atMs=round(elapsed*1000,3)))
        yield
    data = report()['sample']
    data['nativeActions'] = performed
    data['nativeRoundtripMs'] = round((time.monotonic()-start)*1000, 3)
    data['roundtripOverSampleMs'] = round(data['nativeRoundtripMs']-data['elapsedMs'], 3)
    result['samples'].append(data)
    write()
    assert not data['errors'] and not data['after']['motion']['errors'], data
    assert data['raf']['count'] >= 5, 'Insufficient real CEF RAF samples'
    assert not data['after']['busy'], 'Transition did not settle: '+name
    assert data['chartsReadyMs'] is not None and data['chartsReadyMs']-data['lastActionMs'] < 1000, 'Charts were not complete within 1 second: '+name
    assert data['alignment'] and data['alignment']['distance'] < 1.5, 'Navigation highlight drift: '+name
    if expected:
        assert data['after']['page'] == expected and data['after']['active'] == expected, data
    for action in data['actions']:
        if action['label'] in ('overview','inventory','orders','devices','alerts','trace','scene'):
            assert action['page']==action['label'] and action['active']==action['label'], 'Navigation selection was not immediate'
    return data


def run():
    yield from wait('discover_real_cef', discover, 120)
    yield from wait('initial_camera', lambda: not pawn.is_pose_transition_active())
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    hud.evaluate_diagnostics(INSTALL)
    yield from pause(2)
    assert tuple(pc.get_viewport_size()) == (1920,1080), pc.get_viewport_size()
    result['viewport'] = list(pc.get_viewport_size())
    result['roof_closed_before'] = pc.warehouse_roof.is_roof_closed()
    yield from sample('idle_overview', '', 1500, 'overview')
    for cycle in range(2):
        for page in ('inventory','orders','devices','alerts','trace','scene','overview'):
            yield from sample('nav_%d_%s' % (cycle+1,page), 'window.__motionPerf.click(%s);'%json.dumps(page), expected=page)
    rapid = "['inventory','orders','devices','alerts','scene','trace','orders'].forEach((p,i)=>setTimeout(()=>window.__motionPerf.click(p),i*45));"
    data = yield from sample('rapid_navigation_45ms', rapid, 1500, 'orders')
    assert all(a['page']==a['label'] and a['active']==a['label'] for a in data['actions']), 'Accepted click did not immediately select target'
    yield from sample('same_view_orders_outbound', "window.__motionPerf.action('outbound',()=>document.querySelector('[data-key=\"orders.direction\"][data-value=\"outbound\"]').click());", expected='orders')
    yield from sample('same_view_orders_inbound', "window.__motionPerf.action('inbound',()=>document.querySelector('[data-key=\"orders.direction\"][data-value=\"inbound\"]').click());", expected='orders')
    yield from sample('setup_scene_devices', "window.__motionPerf.action('scene-devices',()=>window.twinFilterType('all'));", expected='devices')
    # Copy the real native snapshot only inside this disposable browser context.
    payload = hud.get_snapshot()
    hud.evaluate_diagnostics('window.__motionPerf.snapshotText="";')
    for offset in range(0,len(payload),7000):
        hud.evaluate_diagnostics('window.__motionPerf.snapshotText+='+json.dumps(payload[offset:offset+7000])+';')
    hud.evaluate_diagnostics('window.__motionPerf.snapshot=JSON.parse(window.__motionPerf.snapshotText);')
    yield from pause(.2)
    same = yield from sample('same_view_identical_snapshots', "for(let i=0;i<8;i++)setTimeout(()=>window.__motionPerf.action('snapshot',()=>window.twinReceive(window.__motionPerf.snapshot)),i*90);", 1600, 'devices')
    assert same['lifecycleDelta']['chartCreates']==0 and same['lifecycleDelta']['chartDisposes']==0, same
    assert same['after']['performance']['domWrites']==same['before']['performance']['domWrites'], same
    changed = yield from sample('same_view_changed_snapshots', "for(let i=0;i<8;i++)setTimeout(()=>window.__motionPerf.action('telemetry',()=>{const d=JSON.parse(JSON.stringify(window.__motionPerf.snapshot));if(d.equipment&&d.equipment[0]){d.equipment[0].status=i%2?'running':'idle';d.equipment[0].value=30+i;}window.twinReceive(d);}),i*90);", 1600, 'devices')
    assert changed['lifecycleDelta']['chartCreates']==0 and changed['lifecycleDelta']['chartDisposes']==0, changed
    assert changed['lifecycleDelta']['chartUpdates']>0, 'Changed snapshot did not exercise chart update path'
    # Start a cold device-detail transition 300ms into the native 420ms close.
    # The native visibility notification then cancels it mid-entry; reopening
    # must release the transition gate and finish its queued ring chart.
    pixels = hud.get_viewport_pixel_size()
    toggle = lambda: hud.handle_chrome_click(unreal.Vector2D(pixels.x-30,25))
    assert toggle(), 'Could not start native close'
    hidden = yield from sample('native_hide_during_transition',
        "setTimeout(()=>window.__motionPerf.action('cold-device-detail',()=>{const d=JSON.parse(JSON.stringify(window.__motionPerf.snapshot));d.selection={kind:'device',id:d.equipment[0].id};window.twinSelect(d);}),300);",
        1800, 'devices', native_actions=((.65,'reopen-panel',toggle),))
    assert hidden['after']['detail'] and hidden['after']['detail']['kind']=='device', hidden
    assert hidden['after']['motion']['visible'] and hidden['lifecycleDelta']['chartCreates']>0, hidden
    assert hud.get_panel_transition_progress() > .999, 'Native panel did not reopen'
    assert pc.warehouse_roof.is_roof_closed() == result['roof_closed_before']
    assert hashlib.sha256(MAP.read_bytes()).hexdigest() == result['map_sha256_before']
    result['ui_sha256_after'] = {name:hashlib.sha256((ROOT/'Content/GHSTwinUI/web'/name).read_bytes()).hexdigest() for name in FILES}
    assert result['ui_sha256_after']==result['ui_sha256'], 'UI files changed while measured process was running'
    result['checks'] += ['immediate_navigation_selection','rapid_latest_target_wins','same_view_chart_lifecycle_preserved','native_hide_during_transition_recovers_cold_chart','map_unchanged','ui_bundle_unchanged']


def finish(error=None):
    result['success'] = error is None
    if error:
        result['error'] = error
    write()
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_UI_MOTION_PERFORMANCE '+json.dumps(dict(success=result['success'],report=str(OUT/'performance.json'),error=error)))
    if world:
        unreal.SystemLibrary.quit_game(world, pc, unreal.QuitPreference.QUIT, False)
    else:
        unreal.SystemLibrary.execute_console_command(None, 'quit')


steps = run()


def tick(delta):
    try:
        assert time.monotonic()-START < 220, 'Owned performance QA timeout'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
