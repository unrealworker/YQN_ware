"""Verify the production offline React Bits/ECharts layer in owned UE Chromium.

Run an isolated UnrealEditor -game -RenderOffscreen -TwinDiagnostics process,
with -ExecCmds="py D:/UEPro/Test/Scripts/ghs/verify_ui_motion_runtime.py".
Only Saved/UIMotion is written; no scene or project settings are saved.
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
STAMP = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
OUT = ROOT / 'Saved/UIMotion' / STAMP
OUT.mkdir(parents=True, exist_ok=True)
MAP = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
MAP_HASH = hashlib.sha256(MAP.read_bytes()).hexdigest()
START = time.monotonic()
world = pc = hud = pawn = handle = None
stage = 'discover'
serial = 0
result = dict(success=False, checks=[], captures=[], assets_saved=False,
              scope='Real UE CEF, local offline browser; not a packaged or remote streaming performance benchmark',
              map_sha256_before=MAP_HASH, output=str(OUT),
              ui_sha256={name:hashlib.sha256((ROOT/'Content/GHSTwinUI/web'/name).read_bytes()).hexdigest()
                         for name in ('app.js','motion.js','motion.css','index.html')})


def write():
    result['stage'] = stage
    (OUT / 'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'Saved/UIMotion/runtime-latest.json').write_text(json.dumps(dict(
        success=result['success'], stage=stage, report=str(OUT / 'runtime.json'),
        elapsed_seconds=time.monotonic()-START, error=result.get('error')), ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **data):
    result['checks'].append(dict(name=name, passed=True, **data))
    write()


def wait(name, condition, seconds=20):
    global stage
    stage = name
    deadline = time.monotonic()+seconds
    while not condition():
        assert time.monotonic() < deadline, 'Timed out: ' + name
        yield


def pause(seconds):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        yield


def current_report():
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
            return bool(current_report().get('business'))
    return False


PROBE = r"""(()=>{
const page=document.getElementById('page'), main=document.getElementById('main'), nav=document.getElementById('navigation');
const box=n=>{if(!n)return null;const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};
const motion=window.TwinMotion;
return {
 ua:navigator.userAgent,href:location.href,page:window.twinState.page,detail:window.twinState.detail,
 busy:main.getAttribute('aria-busy')==='true',motion:motion?motion.diagnostics():null,
 performance:window.twinGetPerformance(),viewport:window.TwinViewport.getState(),
 text:motion?motion.text(page):page.textContent,
 overflow:main.scrollWidth>main.clientWidth||nav.scrollWidth>nav.clientWidth,
 charts:[...page.querySelectorAll('[data-motion-chart]')].map(n=>({
   type:JSON.parse(n.dataset.motionChart).type,ready:n.classList.contains('motion-chart-ready'),
   svg:n.querySelectorAll('.motion-chart svg').length,box:box(n),host:box(n.querySelector('.motion-chart')),
   svgTransform:n.querySelector('.motion-chart svg')?getComputedStyle(n.querySelector('.motion-chart svg')).transform:null,
   client:n.querySelector('.motion-chart')?{w:n.querySelector('.motion-chart').clientWidth,h:n.querySelector('.motion-chart').clientHeight}:null,
   svgSize:n.querySelector('.motion-chart svg')?{
    width:n.querySelector('.motion-chart svg').getAttribute('width'),height:n.querySelector('.motion-chart svg').getAttribute('height'),
    viewBox:n.querySelector('.motion-chart svg').getAttribute('viewBox'),box:box(n.querySelector('.motion-chart svg')),
    parentBox:box(n.querySelector('.motion-chart svg').parentElement)}:null
 })),
 numbers:[...page.querySelectorAll('[data-motion-value]')].map(n=>({target:n.dataset.motionValue,actual:n.textContent})),
 pill:box(nav.querySelector('.motion-nav-highlight')),active:box(nav.querySelector('[aria-current="page"]')),
 navButtons:[...nav.querySelectorAll('[data-page]')].map(n=>({page:n.dataset.page,box:box(n)})),
 imageFailures:[...document.images].filter(n=>n.complete&&!n.naturalWidth).map(n=>n.src),
 runtimeErrors:window.__motionRuntimeErrors||[]
};})()"""


def probe():
    global serial, stage
    serial += 1
    token = serial
    script = "window.ue.twin.command(JSON.stringify({action:'report',motionQAToken:%d,dom:%s}));" % (token, PROBE)
    stage = 'probe_cef_' + str(token)
    deadline = time.monotonic()+10
    next_send = 0
    while True:
        r = current_report()
        if r.get('motionQAToken') == token:
            return r['dom']
        now = time.monotonic()
        assert now < deadline, 'Real CEF diagnostic reply missing'
        if now >= next_send:
            hud.evaluate_diagnostics(script)
            next_send = now+.1
        yield


def ready(page):
    deadline = time.monotonic()+15
    while True:
        dom = yield from probe()
        if dom['page'] == page and not dom['busy']:
            return dom
        assert time.monotonic() < deadline, 'Page did not settle: '+page
        yield from pause(.08)


def validate(dom, expected):
    assert dom['page'] == expected and not dom['busy'], dom
    assert dom['motion'] and dom['motion']['engine'] == 'React Bits + ECharts', dom
    assert not dom['motion']['errors'] and not dom['runtimeErrors'], dom
    assert not dom['overflow'] and not dom['imageFailures'], dom
    for chart in dom['charts']:
        assert chart['ready'] and chart['svg'] >= 1, chart
        assert chart['host']['w'] > 0 and chart['host']['h'] > 0, chart
        assert chart['svgTransform'] == 'none', chart
        assert abs(float(chart['svgSize']['width'])-chart['client']['w']) <= 1, ('Chart drawing width does not fill its host', chart)
        assert abs(float(chart['svgSize']['height'])-chart['client']['h']) <= 1, ('Chart drawing height does not fill its host', chart)
    for number in dom['numbers']:
        assert number['actual'] == number['target'], number
    assert dom['motion']['numbers'] == len(dom['numbers']), dom
    assert dom['motion']['charts'] == len(dom['charts']), dom
    assert dom['pill'] and dom['active'], dom
    for key in ('x', 'y', 'w', 'h'):
        assert abs(dom['pill'][key]-dom['active'][key]) < 1, ('Pill drift', dom['pill'], dom['active'])
    if expected in ('overview', 'inventory'):
        for value in ('337,783', '336,006', '156', '14,373'):
            assert value in dom['text'], (value, dom['text'])
        assert '数据未核验' in dom['text'] and '1,920' in dom['text']
    if expected == 'devices':
        assert all(value in dom['text'] for value in ('82','62','20','SITDOWN-GHS-L-IN-S5','暂无'))


def capture(name):
    path = OUT/(name+'.png')
    unreal.SystemLibrary.execute_console_command(world, 'Shot showui filename="'+path.as_posix()+'" -nosuffix', pc)
    yield from wait('capture_'+name, path.exists)
    result['captures'].append(str(path))
    write()


def navigate(page):
    hud.navigate('settings' if page == 'scene' else page)
    yield from ready(page)
    yield from pause(1)
    dom = yield from probe()
    validate(dom, page)
    return dom


def run():
    yield from wait('discover_real_cef', discover, 120)
    yield from wait('initial_camera', lambda: not pawn.is_pose_transition_active())
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    hud.evaluate_diagnostics("window.__motionRuntimeErrors=[];window.addEventListener('error',e=>window.__motionRuntimeErrors.push(String(e.message)));window.addEventListener('unhandledrejection',e=>window.__motionRuntimeErrors.push(String(e.reason)));")
    yield from pause(2)
    assert pc.warehouse_roof.is_roof_closed()
    for page in ('overview','inventory','orders','devices','alerts','trace','scene'):
        dom = yield from navigate(page)
        assert pc.warehouse_roof.is_roof_closed(), 'Page switch unexpectedly changed roof'
        record('cef_'+page, dom=dom)
        yield from capture('1920_'+page)

    yield from navigate('orders')
    hud.evaluate_diagnostics("document.querySelector('[data-key=\"orders.direction\"][data-value=\"inbound\"]').click();")
    yield from pause(1.4)
    before = yield from probe()
    validate(before, 'orders')
    hud.evaluate_diagnostics("document.querySelector('[data-key=\"orders.direction\"][data-value=\"outbound\"]').click();")
    yield from pause(1.4)
    after = yield from probe()
    validate(after, 'orders')
    assert before['motion']['chartCreates'] == after['motion']['chartCreates'], (before, after)
    assert after['motion']['chartUpdates'] > before['motion']['chartUpdates'], (before, after)
    assert any(n['target']=='118' for n in after['numbers']), after
    record('same_view_chart_instance_reused_for_order_updates', before=before['motion'], after=after['motion'])
    yield from capture('1920_orders_outbound')

    hud.evaluate_diagnostics("document.querySelector('#navigation [data-page=\"devices\"]').dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));window.TwinMotion.navigation(document.getElementById('navigation'));")
    yield from pause(.4)
    hovered = yield from probe()
    assert hovered['page']=='orders', hovered
    assert all(abs(hovered['pill'][key]-hovered['active'][key])<1 for key in ('x','y','w','h')), hovered
    hud.evaluate_diagnostics("document.getElementById('navigation').dispatchEvent(new PointerEvent('pointerleave'));")
    yield from pause(.4)
    hover_left = yield from probe()
    validate(hover_left, 'orders')
    record('nav_hover_keeps_highlight_on_selected_page', hovered=hovered['pill'], active=hovered['active'], after_leave=hover_left['pill'])
    hud.evaluate_diagnostics("document.querySelector('#navigation [data-page=\"devices\"]').click();")
    yield from ready('devices')
    yield from pause(1)
    clicked = yield from probe()
    validate(clicked, 'devices')
    record('nav_click_moves_highlight_to_new_selection', pill=clicked['pill'], active=clicked['active'])
    yield from navigate('orders')

    # Native collapse must stop work without resetting the current business view.
    pixels = hud.get_viewport_pixel_size()
    assert hud.handle_chrome_click(unreal.Vector2D(pixels.x-30, 25))
    yield from wait('panel_collapsed', lambda: hud.get_panel_transition_progress() < .001)
    yield from pause(.3)
    hidden = yield from probe()
    assert not hidden['motion']['visible'], hidden
    yield from pause(.6)
    hidden_again = yield from probe()
    assert hidden['performance']['domWrites'] == hidden_again['performance']['domWrites'], (hidden, hidden_again)
    assert hidden['motion']['numberUpdates'] == hidden_again['motion']['numberUpdates'], (hidden, hidden_again)
    assert hud.handle_chrome_click(unreal.Vector2D(pixels.x-30, 25))
    yield from wait('panel_expanded', lambda: hud.get_panel_transition_progress() > .999)
    yield from pause(1)
    restored = yield from probe()
    validate(restored, 'orders')
    assert restored['motion']['visible'], restored
    record('native_panel_hide_pauses_work_and_restores_state', hidden=hidden['motion'], restored=restored['motion'])

    unreal.SystemLibrary.execute_console_command(world, 'r.SetRes 390x844w', pc)
    yield from wait('resize_phone', lambda: tuple(pc.get_viewport_size()) == (390,844))
    yield from pause(1)
    for page in ('overview','orders','devices'):
        dom = yield from navigate(page)
        record('cef_narrow_'+page, dom=dom)
        yield from capture('390_'+page)
    assert hashlib.sha256(MAP.read_bytes()).hexdigest() == MAP_HASH
    record('saved_map_unchanged', sha256=MAP_HASH)
    assert all(hashlib.sha256((ROOT/'Content/GHSTwinUI/web'/name).read_bytes()).hexdigest()==digest
               for name,digest in result['ui_sha256'].items()), 'UI bundle changed during the final acceptance run'
    record('ui_bundle_unchanged_during_acceptance', sha256=result['ui_sha256'])


def finish(error=None):
    result['success'] = error is None
    result['elapsed_seconds'] = time.monotonic()-START
    if error:
        result['error'] = error
    write()
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_UI_MOTION_RUNTIME ' + json.dumps(result, ensure_ascii=False))
    if world:
        unreal.SystemLibrary.quit_game(world, pc, unreal.QuitPreference.QUIT, False)


steps = run()


def tick(delta):
    try:
        assert time.monotonic()-START < 240, 'Owned CEF acceptance timeout'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
