"""Actual-CEF visual acceptance in an owned offscreen game; never save assets.

Launch the saved Zcool map with -game -RenderOffscreen -TwinDiagnostics
-windowed -ForceRes -ResX=2560 -ResY=1600 -ExecCmds="py <this file>".
The Slate tick generator has a 240-second deadline. It quits only that game.
DOM events exercise production CEF handlers, not OS pointer/keyboard delivery.
Screenshots require human visual review; assertions do not certify aesthetics.
Includes all seven first views, five scrolled page bottoms, a 2560x1600 footer
plate review, and a roof-closed native top-preset scene capture for thumbnails.
Use -VisualPolishScenesOnly for all scene sources, or
-VisualPolishScenesOnlyDetailRefinement to replace only racks/floor/AGV in the
existing manifest while retaining and re-hashing all other source images.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
import traceback

import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/VisualPolish/Runtime'
MAP = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
WORLD_PREFIX = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'
CLI = unreal.SystemLibrary.get_command_line()
DETAIL_REFINEMENT = bool(re.search(r'(?:^|\s)-VisualPolishScenesOnlyDetailRefinement(?=\s|$)', CLI, re.I))
SCENES_ONLY = DETAIL_REFINEMENT or bool(re.search(r'(?:^|\s)-VisualPolishScenesOnly(?=\s|$)', CLI, re.I))
assert all(re.search(r'(?:^|\s)-' + flag + r'(?=\s|$)', CLI, re.I)
           for flag in ('game', 'RenderOffscreen', 'TwinDiagnostics')), 'Owned diagnostic game required'
OUT.mkdir(parents=True, exist_ok=True)
# A focused retry must not erase the earlier all-page acceptance evidence or
# misrepresent those assertions as having run again in this game process.
previous_report = None
if SCENES_ONLY and (OUT / 'runtime.json').exists():
    previous_report = OUT / ('runtime_before_scene_retry_' + str(time.time_ns()) + '.json')
    previous_report.write_bytes((OUT / 'runtime.json').read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset_hashes():
    paths = [MAP, ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap']
    paths += sorted((ROOT / 'Content/GHSZcoolSmartFactory/VisualPolish').rglob('*.uasset'))
    return {str(path.relative_to(ROOT)): sha(path) for path in paths if path.is_file()}


initial_hashes = asset_hashes()
result = dict(success=False, checks=[], captures=[], assets_saved=False,
              run_mode='three_scene_details_only' if DETAIL_REFINEMENT else 'scene_captures_only' if SCENES_ONLY else 'full_acceptance',
              previous_report=str(previous_report) if previous_report else None,
              input_method='Actual embedded CEF production handlers via DOM events',
              visual_review_required=True, asset_hashes_before=initial_hashes)
world = pc = hud = pawn = handle = None
started = time.monotonic()
stage = 'discover'
serial = 0
finished = False

if DETAIL_REFINEMENT:
    assert previous_report, 'Detail refinement requires the previous successful scene manifest'
    previous = json.loads(previous_report.read_text(encoding='utf-8'))
    assert previous.get('assets_unchanged') and previous.get('asset_hashes_after') == initial_hashes, 'Saved assets changed since the scene captures'
    replacement_keys = {'racks', 'floor', 'agv'}
    replacement_names = {'latest_scene_' + key for key in replacement_keys}
    result['design_scene_captures'] = {key: row for key, row in previous['design_scene_captures'].items() if key not in replacement_keys}
    result['captures'] = [row for row in previous['captures'] if row['name'] not in replacement_names]
    for row in result['captures']:
        assert Path(row['path']).is_file() and sha(Path(row['path'])) == row['sha256'], ('Preserved image changed', row['path'])
    result['preserved_capture_count'] = len(result['captures'])


def write():
    (OUT / 'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def record(name, **data):
    result['checks'].append(dict(name=name, passed=True, **data))
    write()


def browser():
    raw = hud.get_editor_property('last_browser_report') if hud else ''
    return json.loads(raw) if raw else {}


def poi():
    return json.loads(hud.get_poi_report())


def controls():
    return json.loads(hud.get_scene_controls_state())


def console(command):
    unreal.SystemLibrary.execute_console_command(world, command, pc)


def command(action, **values):
    hud.command(json.dumps(dict(action=action, **values)))


def pause(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        yield


def wait(name, condition, timeout=20):
    global stage
    stage = name
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'Timed out: ' + name
        yield


def discover():
    global world, pc, hud, pawn
    for candidate in unreal.ObjectIterator(unreal.World):
        if not candidate.get_path_name().startswith(WORLD_PREFIX):
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        widget = getattr(controller, 'twin_hud_widget', None) if controller else None
        if widget and widget.browser_ready:
            world, pc, hud, pawn = candidate, controller, widget, controller.get_controlled_pawn()
            return bool(pawn and browser().get('business'))
    return False


# Keep the report comfortably below Command's 16,384-character input limit.
# A serial handshake cannot mistake an old scheduled browser report for this DOM.
DOM_PROBE = r"""(()=>{
 const q=s=>document.querySelector(s),all=s=>Array.from(document.querySelectorAll(s));
 const rect=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
 const main=q('#main'),page=q('#page'),nav=q('#navigation'),s=window.twinState,b=window.TwinBusinessData.snapshot;
 const tip=q('[role=tooltip]'),trigger=q('[data-info][aria-expanded=true]');
 const vp=window.TwinViewport?window.TwinViewport.getState():{width:innerWidth,height:innerHeight};
 const answer={action:'report',visualPolishToken:TOKEN,
  page:s.page,detail:s.detail?{kind:s.detail.kind,id:s.detail.id}:null,
  busy:main.getAttribute('aria-busy')==='true',viewport:{width:innerWidth,height:innerHeight,design:vp},
  overflow:document.documentElement.scrollWidth>Math.max(vp.width,document.documentElement.clientWidth)+1||main.scrollWidth>main.clientWidth+1||nav.scrollWidth>nav.clientWidth+1,
  extents:{document:document.documentElement.scrollWidth,main:main.scrollWidth,mainClient:main.clientWidth,navigation:nav.scrollWidth,navigationClient:nav.clientWidth},
  scroll:{top:main.scrollTop,height:main.scrollHeight,clientHeight:main.clientHeight,bottomGap:main.scrollHeight-main.clientHeight-main.scrollTop},
  imageFailures:Array.from(document.images).filter(i=>i.complete&&!i.naturalWidth).map(i=>i.getAttribute('src')),
  imagesPending:Array.from(document.images).filter(i=>!i.complete).length,
  text:String(page.innerText||'').slice(0,6000),title:q('h1')?q('h1').innerText:'',
  unverified:all('[data-unverified]').map(e=>e.dataset.unverified),
  inventorySamples:all('[data-inventory-sample]').map(e=>e.dataset.inventorySample),
  ledgerSamples:all('[data-ledger-sample]').map(e=>e.dataset.ledgerSample),
  legends:all('.legend-inline .swatch,.legend .dot').map(e=>({label:e.parentElement.innerText,color:getComputedStyle(e).backgroundColor})),
  tooltip:tip?{text:tip.textContent,bounds:rect(tip),expanded:!!trigger,described:trigger?trigger.getAttribute('aria-describedby'):null,visible:getComputedStyle(tip).display!=='none'&&getComputedStyle(tip).visibility!=='hidden'}:null,
  switches:all('[role=switch]').map(e=>({key:e.dataset.key,on:e.getAttribute('aria-checked')})),
  sliders:all('[data-capacity]').map(e=>({key:e.dataset.capacity,value:e.value,disabled:e.disabled})),
  timeline:all('.timeline li').length,empty:!!q('.empty'),settings:s.settings,
  actionResult:window.__visualPolishAction||null,
  business:{sourceMode:b.source.mode,live:b.source.live,warehouseCode:b.warehouse.code,
   inventory:{onHand:b.inventory.onHand,available:b.inventory.available,frozen:b.inventory.frozen,allocated:b.inventory.allocated,owners:b.inventory.owners,skus:b.inventory.skus,unit:b.inventory.unit,capacity:b.inventory.capacity,sceneMappingConfirmed:b.inventory.sceneMappingConfirmed},
   forklifts:{total:b.forklifts.total,normal:b.forklifts.normal,disabled:b.forklifts.disabled,repair:b.forklifts.repair,telemetryAvailable:b.forklifts.telemetryAvailable,sceneMappingConfirmed:b.forklifts.sceneMappingConfirmed},deviceView:s.filters.devices.view}};
 window.ue.twin.command(JSON.stringify(answer));
})()"""


def probe():
    global serial, stage
    assert hasattr(hud, 'evaluate_diagnostics'), 'Compile EvaluateDiagnostics before running this verifier'
    serial += 1
    token = serial
    script = DOM_PROBE.replace('TOKEN', str(token))
    deadline = time.monotonic() + 8
    next_send = 0
    while True:
        current = browser()
        if current.get('visualPolishToken') == token:
            return current
        assert time.monotonic() < deadline, 'CEF DOM report timed out for token ' + str(token)
        if time.monotonic() >= next_send:
            hud.evaluate_diagnostics(script)
            next_send = time.monotonic() + .1
        yield


def ready(page=None, kind=None):
    deadline = time.monotonic() + 12
    while True:
        dom = yield from probe()
        if (not dom['busy'] and not dom['imagesPending'] and
                (page is None or dom['page'] == page) and
                (kind is None or (dom.get('detail') or {}).get('kind') == kind)):
            return dom
        assert time.monotonic() < deadline, ('CEF view did not settle', page, kind, dom)
        yield


def act(script):
    # Send mutations once; only the read-only probe is retried if reports race.
    hud.evaluate_diagnostics("(()=>{window.__visualPolishAction={ok:false};try{" + script +
                             ";window.__visualPolishAction={ok:true};}catch(e){window.__visualPolishAction={ok:false,error:String(e)};}})()")
    yield from pause(.12)
    dom = yield from probe()
    assert dom['actionResult'] and dom['actionResult']['ok'], dom.get('actionResult')


def click(selector):
    encoded = json.dumps(selector)
    yield from act('const e=document.querySelector(' + encoded + ');if(!e)throw Error("Missing selector: "+' + encoded + ');e.click()')


def navigate(page):
    global stage
    stage = 'page_' + page
    hud.clear_selection()
    hud.navigate('settings' if page == 'scene' else page)
    dom = yield from ready(page)
    assert dom['detail'] is None, dom['detail']
    return dom


def validate(name, dom):
    assert not dom['overflow'], (name, dom['extents'])
    assert not dom['imageFailures'], (name, dom['imageFailures'])
    assert dom['title'], (name, 'Missing page title')
    b = dom['business']
    assert (b['sourceMode'], b['live'], b['warehouseCode']) == ('verified-extract', False, 'GHS_CA_US')
    assert b['inventory'] == dict(onHand=337783, available=336006, frozen=55, allocated=1722,
                                  owners=156, skus=14373, unit=None, capacity=None, sceneMappingConfirmed=False), b
    assert b['forklifts'] == dict(total=82, normal=62, disabled=20, repair=0,
                                  telemetryAvailable=False, sceneMappingConfirmed=False), b
    text = dom['text']
    if not dom['detail'] and dom['page'] in ('overview', 'inventory'):
        assert all(number in text for number in ('337,783', '336,006')), text
        assert dom['unverified'] and '数据未核验' in text, 'Unverified demo capacity lost its notice'
    if not dom['detail'] and dom['page'] == 'inventory':
        assert set(dom['inventorySamples']) == {'8551268', '7111566', '8556512', '8703069', '10274458'}
        assert '-1' in text, 'Negative source sample was silently removed'
    if not dom['detail'] and dom['page'] == 'devices' and b['deviceView'] == 'ledger':
        assert set(dom['ledgerSamples']) == {'2574', '2575', '2576', '2577', '2578'}
        assert 'SITDOWN-GHS-L-IN-S5' in text and '暂无' in text, 'Unconnected ledger telemetry must remain unavailable'
    if dom['page'] in ('orders', 'alerts', 'trace') or (dom['detail'] or {}).get('kind') == 'material-demo':
        assert '数据未核验' in text, (name, 'Demo screen lost its data status')
    record(name, dom=dom)


def capture(name, show_ui=True):
    global stage
    stage = 'capture_' + name
    path = OUT / (name + '.png')
    old = path.stat().st_mtime_ns if path.exists() else 0
    expected_size = tuple(pc.get_viewport_size())
    console('Shot ' + ('showui ' if show_ui else '') + 'filename="' + path.as_posix() + '" -nosuffix')

    def complete():
        if not path.exists() or path.stat().st_mtime_ns == old:
            return False
        try:
            data = path.read_bytes()
            return data[:8] == b'\x89PNG\r\n\x1a\n' and data[-8:-4] == b'IEND'
        except OSError:
            return False

    yield from wait(stage, complete)
    raw = path.read_bytes()
    size = struct.unpack('>II', raw[16:24])
    assert size == expected_size, (name, size, expected_size)
    result['captures'].append(dict(name=name, path=str(path), resolution=list(size),
                                   show_ui=show_ui, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    write()


def capture_page_bottom(page, name):
    """Use the actual page scroll container and prove its bottom was reached."""
    yield from act('const m=document.getElementById("main");m.scrollTop=m.scrollHeight;m.dispatchEvent(new Event("scroll"))')
    yield from pause(.2)
    dom = yield from ready(page)
    assert abs(dom['scroll']['bottomGap']) <= 1, ('Did not reach page bottom', page, dom['scroll'])
    validate('cef_' + page + '_bottom', dom)
    record('actual_cef_scroll_bottom_' + page, scroll=dom['scroll'],
           scroll_required=dom['scroll']['height'] > dom['scroll']['clientHeight'])
    yield from capture(name)
    # Leave saved page scroll bookmarks at zero so subsequent detail captures
    # and another navigation to the same screen retain the original first view.
    yield from act('const m=document.getElementById("main");m.scrollTop=0;m.dispatchEvent(new Event("scroll"))')


def capture_native_top():
    """Run the production top preset with its full scene area, without UI."""
    command('overview')
    yield from wait('closed_roof_before_top', lambda: pc.warehouse_roof.is_roof_closed() and not pawn.is_pose_transition_active())
    assert tuple(pc.get_viewport_size()) == (1920, 1080)
    # GHSTwinHeaderLayout: the desktop panel button occupies [width-112,
    # width-16] x [10,54]. At 1920x1080, native HUD scale is exactly one.
    yield from wait('native_top_viewport_settled', lambda:
                    abs(hud.get_viewport_pixel_size().x - 1920) < .5 and
                    abs(hud.get_viewport_pixel_size().y - 1080) < .5 and
                    abs(hud.get_hud_scale() - 1) < .001)
    if hud.get_panel_transition_progress() > 0:
        assert hud.handle_chrome_click(unreal.Vector2D(1920 - 64, 32))
    # NativeTick deliberately retains the expanded input/camera layout until
    # progress is exactly zero. <.01 is still the 1440px scene, not full width.
    yield from wait('collapse_for_native_top', lambda:
                    hud.get_panel_transition_progress() == 0 and
                    hud.get_panel_size().x == 0 and
                    abs(hud.get_panel_position().x - 1920) < .5)
    yield from pause(.1)
    # GHSTwinHUDWidget::Command("preset","top") uses OverviewCenter,
    # pitch -78, OverviewYaw, and min(95000,OverviewDistance*ViewSize.X /
    # SceneSize.X). The collapsed scene occupies the full width; invoke that
    # handler instead of duplicating/guessing its camera transform here.
    command('preset', value='top')
    yield from wait('native_top_camera', lambda: not pawn.is_pose_transition_active())
    yield from pause(1)
    rotation = pawn.get_actor_rotation()
    pivot = pawn.get_actor_location()
    distance = float(pawn.get_editor_property('spring_arm_component').get_editor_property('target_arm_length'))
    assert abs(rotation.pitch + 78) < .01, ('Native top pitch differs', rotation)
    assert abs((rotation.yaw - pawn.overview_yaw + 180) % 360 - 180) < .01
    assert 900 <= distance <= 95000, distance
    assert pc.warehouse_roof.is_roof_closed() and not hud.is_interior_available()
    record('native_closed_roof_top_preset', command=dict(action='preset', value='top'),
           rotation=[rotation.pitch, rotation.yaw, rotation.roll], pivot=[pivot.x, pivot.y, pivot.z],
           distance=distance, panel_collapsed=True, roof_closed=True,
           settled_full_width_distance=min(95000., float(pawn.overview_distance)),
           panel_size=[hud.get_panel_size().x, hud.get_panel_size().y],
           panel_progress=hud.get_panel_transition_progress(),
           source='GHSTwinHUDWidget.cpp Command preset top; GHSTwinHeaderLayout.h panel button')
    # Preserve the actual production top pivot/rotation/distance, only remove
    # its header's camera-local offset for a centered, UI-free image.
    pawn.transition_to_pose(pivot, distance, rotation, unreal.Vector2D(1920, 1080),
                            unreal.Vector2D(960, 540), True, .7)
    yield from wait('native_top_centered_for_image', lambda: not pawn.is_pose_transition_active())
    yield from pause(.5)
    yield from capture('24_scene_only_top_closed_1920x1080', show_ui=False)
    result['captures'][-1]['camera'] = camera_pose()


def camera_pose():
    location, rotation = pawn.get_actor_location(), pawn.get_actor_rotation()
    camera = pawn.get_editor_property('warehouse_camera')
    arm = pawn.get_editor_property('spring_arm_component')
    offset = arm.get_editor_property('socket_offset')
    return dict(pivot=[location.x, location.y, location.z],
                rotation=[rotation.pitch, rotation.yaw, rotation.roll],
                distance=float(arm.get_editor_property('target_arm_length')),
                socket_offset=[offset.x, offset.y, offset.z],
                field_of_view=float(camera.get_editor_property('field_of_view')))


def design_capture(key, name, **metadata):
    assert hud.is_interior_available(), ('Interior capture requires completely open roof', key)
    assert not str(hud.get_editor_property('selected_id')), 'Clear selection before design backgrounds'
    assert tuple(pc.get_viewport_size()) == (1920, 1080)
    yield from wait('design_camera_' + key, lambda: not pawn.is_pose_transition_active())
    native_pose = camera_pose()
    if any(abs(value) > .01 for value in native_pose['socket_offset']):
        # Native region/top presets frame below the 64px header; image sources
        # have no header. Preserve their measured pose and remove only that offset.
        pawn.focus_on_target(pawn.get_actor_location(), native_pose['distance'], pawn.get_actor_rotation(),
                             unreal.Vector2D(1920, 1080), unreal.Vector2D(960, 540), .7)
        yield from wait('design_centered_' + key, lambda: not pawn.is_pose_transition_active())
        metadata['native_camera_before_centering'] = native_pose
    yield from pause(.75)
    yield from capture(name, show_ui=False)
    result['design_scene_captures'][key] = dict(result['captures'][-1], map=world.get_name(),
                                               roof_open=True, selected_id='', camera=camera_pose(), **metadata)
    write()


def union_bounds(rows):
    assert rows, 'Cannot frame an empty group of actual scene records'
    minimum = [min(row['worldPosition'][axis] - row['extent'][axis] for row in rows) for axis in range(3)]
    maximum = [max(row['worldPosition'][axis] + row['extent'][axis] for row in rows) for axis in range(3)]
    return [(a + b) * .5 for a, b in zip(minimum, maximum)], [(b - a) * .5 for a, b in zip(minimum, maximum)]


def frame_scene_bounds(position, extent, pitch, yaw, fill=.68, closeup=False):
    """Fit actual world-space bounds; narrow the game lens for tiny equipment.

    This changes only the transient game camera. The 60-75 percent request is
    interpreted as the largest projected bounding-box dimension, not a claim
    about the number of visible mesh pixels or foreground occlusion.
    """
    rotation = unreal.Rotator(pitch=pitch, yaw=yaw)
    forward = unreal.MathLibrary.get_forward_vector(rotation)
    right = unreal.MathLibrary.get_right_vector(rotation)
    up = unreal.MathLibrary.get_up_vector(rotation)
    dot = lambda v, axis: v[0] * axis.x + v[1] * axis.y + v[2] * axis.z
    corners = [(extent[0] * x, extent[1] * y, extent[2] * z)
               for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    projected = [(dot(v, forward), dot(v, right), dot(v, up)) for v in corners]
    aspect = 1920 / 1080
    fov = 56.
    if closeup:
        # The production camera has a 900 cm minimum arm length. A narrow lens
        # lets the real small AGV/charger fill the frame without changing meshes.
        required_tan = max(max(abs(x), abs(y) * aspect) / max(1., 900. + depth) / fill
                           for depth, x, y in projected)
        fov = min(56., max(12., math.degrees(2 * math.atan(required_tan))))
    tan_h = math.tan(math.radians(fov * .5))
    distance = max(900., max(max(abs(x), abs(y) * aspect) / (tan_h * fill) - depth
                              for depth, x, y in projected))
    assert distance <= 95000, ('Scene bounds exceed gameplay camera range', position, extent, distance)
    camera = pawn.get_editor_property('warehouse_camera')
    camera.set_editor_property('field_of_view', fov)
    pawn.focus_on_target(unreal.Vector(*position), distance, rotation,
                         unreal.Vector2D(1920, 1080), unreal.Vector2D(960, 540), .8)
    projected_fill = max(max(abs(x), abs(y) * aspect) / ((distance + depth) * tan_h)
                         for depth, x, y in projected)
    return dict(bounds_center=position, bounds_extent=extent, target_max_dimension=fill,
                projected_bbox_max_dimension=projected_fill, field_of_view=fov,
                framing='Actual registry world bounds; visual review must check occlusion and mesh occupancy')


def capture_design_scene_sources():
    """Eleven image categories requested by the complete Pencil image inventory."""
    camera = pawn.get_editor_property('warehouse_camera')
    actors = {actor.get_name(): actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)}
    result['design_scene_captures'] = {}
    for key, name in (('closed_overview', '16_scene_only_overview_1920x1080'),
                      ('top', '24_scene_only_top_closed_1920x1080')):
        item = next(row for row in result['captures'] if row['name'] == name)
        result['design_scene_captures'][key] = dict(item, map=world.get_name(), roof_open=False)
    assert hud.get_panel_transition_progress() == 0 and hud.get_panel_size().x == 0
    command('layers', building=True, racks=True, equipment=True, pois=False)
    hud.clear_selection()
    assert hud.open_warehouse(), 'Current saved scene has no usable warehouse roof'
    yield from wait('design_roof_fully_open', lambda: hud.is_interior_available())
    roof_actor = next((actor for actor in actors.values() if actor.actor_has_tag('GHS_WarehouseRoof')), None)
    assert roof_actor, 'No real warehouse roof actor available to measure the complete warehouse outline'
    origin, extent = roof_actor.get_actor_bounds(False)
    # 1440x1016 design backgrounds crop a 16:9 source horizontally. Keep the
    # complete warehouse inside the middle 68 percent using its actual outline.
    framed = frame_scene_bounds([origin.x, origin.y, origin.z], [extent.x, extent.y, extent.z],
                                pawn.overview_pitch, pawn.overview_yaw, fill=.68)
    yield from design_capture('open_overview', 'latest_scene_open_overview',
                              source='Actual roof actor bounds, saved overview rotation, roof completely open', **framed)
    camera.set_editor_property('field_of_view', 56.)
    command('preset', value='top')
    yield from design_capture('open_top_alternative', 'latest_scene_open_top', source='Production top preset with open roof')

    actual = json.loads(hud.get_snapshot())
    records = actual['equipment'] + actual['facilities']

    def choose(kind, preferred):
        choices = sorted((row for row in records if row['type'] == kind and row.get('visible')),
                         key=lambda row: row['id'])
        assert choices, 'No actual visible scene device of type ' + kind
        return next((row for row in choices if row['id'] == preferred), choices[0])

    selected = {kind: choose(kind, preferred) for kind, preferred in
                (('agv', 'AGV-07'), ('forklift', 'FORK-07'), ('stacker', 'STACKER-04'),
                 ('truck', 'TRUCK-042'), ('charger', 'CH-07'))}
    # Frame a real local charging array and nearby AGVs from runtime positions.
    # Do not fabricate a placement or bind the design's example IDs to telemetry.
    agv = selected['agv']
    squared_distance = lambda a, b: sum((x - y) ** 2 for x, y in zip(a['worldPosition'], b['worldPosition']))
    chargers = sorted((row for row in records if row['type'] == 'charger' and row.get('visible')),
                      key=lambda row: squared_distance(row, agv))
    anchor = chargers[0]
    nearby_chargers = sorted(chargers, key=lambda row: squared_distance(row, anchor))[:12]
    nearby_agvs = sorted((row for row in records if row['type'] == 'agv' and row.get('visible')),
                         key=lambda row: squared_distance(row, anchor))[:4]
    group = nearby_chargers + nearby_agvs
    position, extent = union_bounds(group)
    hud.clear_selection()
    framed = frame_scene_bounds(position, extent, -58, pawn.overview_yaw, fill=.72)
    yield from design_capture('charging_zone', 'latest_scene_charging_zone',
                              subject_ids=[row['id'] for row in group], **framed)

    for kind in ('forklift', 'stacker', 'truck', 'charger'):
        row = selected[kind]
        assert row['actor'] in actors, ('Registry actor is no longer present', row)
        actor = actors[row['actor']]
        hud.clear_selection()
        pitch = -50 if kind == 'agv' else -26 if kind == 'charger' else -30
        # Use the actor's real orientation for a consistent quarter view.
        # Visual QA still needs to confirm which side of each mesh is its front.
        yaw = actor.get_actor_rotation().yaw + 135
        framed = frame_scene_bounds(row['worldPosition'], row['extent'], pitch, yaw, closeup=True)
        yield from design_capture(kind, 'latest_scene_' + kind,
                                  subject_id=row['id'], subject_type=row['type'], actor=row['actor'],
                                  mesh=row['mesh'], location=row['location'], **framed)
        if kind == 'charger':
            framed = frame_scene_bounds(row['worldPosition'], row['extent'], pitch, yaw + 180, closeup=True)
            yield from design_capture('charger_reverse_alternative', 'latest_scene_charger_reverse',
                                      subject_id=row['id'], subject_type=kind, actor=row['actor'],
                                      mesh=row['mesh'], **framed)
    yield from capture_refined_design_details()
    camera.set_editor_property('field_of_view', 56.)
    record('design_sources_from_current_saved_scene', categories=list(result['design_scene_captures']),
           actual_subject_ids={kind: row['id'] for kind, row in selected.items()},
           scope='New game renderings; no UI, no POIs, no selected object; visual QA required before design replacement')


def actual_storage_instances():
    """Measure live ISM instances, never the aggregate bounds of all storage."""
    racks, floor = [], []
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.static_mesh
            if not mesh:
                continue
            path = mesh.get_path_name()
            is_rack = mesh.get_name().startswith('SM_GHS_V2Rack_')
            is_floor = '/DoublePallet/Meshes/' in path and 'CargoHigh' in mesh.get_name()
            if not (is_rack or is_floor):
                continue
            bounds = mesh.get_bounds()
            local_corners = [bounds.origin + unreal.Vector(bounds.box_extent.x * x, bounds.box_extent.y * y, bounds.box_extent.z * z)
                             for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
            for index in range(component.get_instance_count()):
                transform = component.get_instance_transform(index, world_space=True)
                center = unreal.MathLibrary.transform_location(transform, bounds.origin)
                # Keep the transform until the small chosen group needs precise
                # world AABBs; avoid eight UE calls for every unphotographed load.
                row = dict(actor=actor.get_name(), component=component.get_name(), instance_index=index,
                           mesh=mesh.get_name(), mesh_path=path, worldPosition=[center.x, center.y, center.z],
                           transform=transform, corners=local_corners)
                (racks if is_rack else floor).append(row)
    return racks, floor


def measure_chosen_instances(rows):
    for row in rows:
        corners = [unreal.MathLibrary.transform_location(row['transform'], corner) for corner in row['corners']]
        low = [min(getattr(point, axis) for point in corners) for axis in ('x', 'y', 'z')]
        high = [max(getattr(point, axis) for point in corners) for axis in ('x', 'y', 'z')]
        row['worldPosition'] = [(a + b) * .5 for a, b in zip(low, high)]
        row['extent'] = [(b - a) * .5 for a, b in zip(low, high)]
    return union_bounds(rows)


def instance_manifest(rows):
    return [{key: row[key] for key in ('actor', 'component', 'instance_index', 'mesh', 'worldPosition', 'extent')}
            for row in rows]


def capture_refined_design_details():
    racks, floor = actual_storage_instances()
    assert racks and floor, 'Current map must contain real main racks and double-pallet floor meshes'
    # MainRackFieldBounds excludes remote dock/wall racks for the region POI.
    # For this close view, take the densest 40m cell of actual rack centers,
    # then only its eighteen nearest rack modules, not the whole field envelope.
    cells = {}
    for row in racks:
        x, y, _ = row['worldPosition']
        cells.setdefault((math.floor(x / 4000), math.floor(y / 4000)), []).append(row)
    cell = min(cells, key=lambda key: (-len(cells[key]), key))
    dense = cells[cell]
    anchor = [sum(row['worldPosition'][axis] for row in dense) / len(dense) for axis in range(3)]
    square_xy = lambda row, point: sum((row['worldPosition'][axis] - point[axis]) ** 2 for axis in (0, 1))
    chosen_racks = sorted(racks, key=lambda row: square_xy(row, anchor))[:18]
    position, extent = measure_chosen_instances(chosen_racks)
    hud.clear_selection()
    framed = frame_scene_bounds(position, extent, -36, pawn.overview_yaw, fill=.82)
    yield from design_capture('racks', 'latest_scene_racks',
                              source='Local main rack aisles: eighteen live instances nearest the densest rack cell',
                              dense_cell=list(cell), measured_instances=instance_manifest(chosen_racks), **framed)

    # The existing verified DoublePallet runtime photograph uses CargoHigh
    # instance zero. Add its three nearest actual high loads for a small group;
    # the west approach keeps the two blue pallet bands visible at a low angle.
    floor.sort(key=lambda row: (row['actor'], row['component'], row['instance_index']))
    anchor = floor[0]['worldPosition']
    chosen_floor = sorted(floor, key=lambda row: square_xy(row, anchor))[:4]
    position, extent = measure_chosen_instances(chosen_floor)
    framed = frame_scene_bounds(position, extent, -27, 35, fill=.76, closeup=True)
    yield from design_capture('floor', 'latest_scene_floor',
                              source='Four adjacent actual CargoHigh double-pallet instances, both blue pallet bands retained',
                              measured_instances=instance_manifest(chosen_floor), **framed)

    snapshot = json.loads(hud.get_snapshot())
    devices = snapshot['equipment'] + snapshot['facilities']
    charging_manifest = result['design_scene_captures'].get('charging_zone')
    if charging_manifest is not None:
        wanted = set(charging_manifest.get('subject_ids', [])) | {'AGV-07', 'AGV-08', 'AGV-12', 'CH-07', 'CH-12'}
        charging_manifest['subject_world_positions'] = {
            row['id']: row['worldPosition'] for row in devices if row['id'] in wanted}
    agvs = sorted((row for row in devices if row['type'] == 'agv' and row.get('visible')), key=lambda row: row['id'])
    assert agvs, 'No visible real AGV'
    agv = next((row for row in agvs if row['id'] == 'AGV-07'), agvs[0])
    chargers = [row for row in devices if row['type'] == 'charger' and row.get('visible')]
    assert chargers, 'No actual charging bay to ground the unobstructed-side camera'
    nearest = min(chargers, key=lambda row: square_xy(row, agv['worldPosition']))
    delta = [nearest['worldPosition'][axis] - agv['worldPosition'][axis] for axis in (0, 1)]
    yaw = math.degrees(math.atan2(delta[1], delta[0]))
    framed = frame_scene_bounds(agv['worldPosition'], agv['extent'], -58, yaw, closeup=True)
    yield from design_capture('agv', 'latest_scene_agv', subject_id=agv['id'], subject_type='agv',
                              actor=agv['actor'], mesh=agv['mesh'], location=agv['location'],
                              nearest_charger_id=nearest['id'], nearest_charger_position=nearest['worldPosition'],
                              source='Camera faces the nearest actual charging structure from the opposite side of the AGV; visual occlusion review required', **framed)
    record('three_design_details_refined', categories=['racks', 'floor', 'agv'],
           rack_instances=len(chosen_racks), floor_double_pallet_instances=len(chosen_floor), agv_id=agv['id'])


def assert_closed_labels():
    state = poi()
    assert pc.warehouse_roof.is_roof_closed() and not hud.is_interior_available(), state
    assert [label['id'] for label in state['labels']] == ['WAREHOUSE:GHS'], state
    label = state['labels'][0]
    assert (label['width'], label['height']) == (228, 56), label
    assert label['interactive'] and label['opacity'] > .99, label
    return state


def check_tooltip():
    before = (yield from ready('overview'))['detail']
    trigger = 'document.querySelector(".page-head [data-info]")'
    yield from act('const e=' + trigger + ';if(!e)throw Error("Header info trigger missing");e.dispatchEvent(new MouseEvent("mouseover",{bubbles:true}))')
    dom = yield from probe()
    tip = dom['tooltip']
    assert tip and tip['visible'] and tip['expanded'] and tip['described'], dom
    assert '非实时' in tip['text'] and '单位' in tip['text'], tip
    bounds, vp = tip['bounds'], dom['viewport']
    assert bounds['left'] >= -1 and bounds['top'] >= -1 and bounds['right'] <= vp['width'] + 1 and bounds['bottom'] <= vp['height'] + 1, tip
    record('tooltip_hover_actual_cef', tooltip=tip)
    yield from capture('08_overview_info_tooltip')
    yield from act(trigger + '.dispatchEvent(new MouseEvent("mouseout",{bubbles:true,relatedTarget:document.body}))')
    yield from pause(.2)
    assert (yield from probe())['tooltip'] is None, 'Hover explanation did not dismiss'
    yield from act(trigger + '.focus()')
    assert (yield from probe())['tooltip'], 'Keyboard focus did not show explanation'
    yield from act('document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))')
    assert (yield from probe())['tooltip'] is None, 'Escape did not dismiss explanation'
    yield from click('.page-head [data-info]')
    assert (yield from probe())['tooltip'], 'Click did not pin explanation'
    yield from click('.page-head [data-info]')
    dom = yield from probe()
    assert dom['tooltip'] is None and dom['detail'] == before, dom
    yield from act('if(document.activeElement)document.activeElement.blur()')
    record('tooltip_focus_click_escape_keep_selection', tested=['hover', 'mouseleave', 'focus', 'Escape', 'click pin', 'click dismiss'])


def check_alert_legend(dom):
    def rgb(label):
        match = next((row for row in dom['legends'] if label in row['label']), None)
        assert match, ('Missing semantic legend', label, dom['legends'])
        return [int(n) for n in re.findall(r'\d+', match['color'])[:3]]
    fault, warning = rgb('故障'), rgb('预警')
    assert fault[0] > fault[1] * 1.3 and fault[0] > fault[2] * 1.3, fault
    assert warning[0] > warning[1] > warning[2], warning
    assert fault != warning
    record('alert_legend_keeps_fault_red_warning_amber', fault=fault, warning=warning)


def run():
    yield from wait('discover_actual_cef', discover, 90)
    console('DisableAllScreenMessages')
    assert tuple(pc.get_viewport_size()) == (2560, 1600), 'Launch at 2560x1600 with -ForceRes'
    yield from wait('initial_camera', lambda: not pawn.is_pose_transition_active())
    yield from pause(2)
    first_snapshot = json.loads(hud.get_snapshot())
    scene_ids = sorted(row['id'] for row in first_snapshot['equipment'])
    assert scene_ids and not set(scene_ids).intersection({'2574', '2575', '2576', '2577', '2578'})
    record('default_warehouse_poi_228x56_closed_roof', poi=assert_closed_labels())
    for index, page in enumerate(('overview', 'inventory', 'orders', 'devices', 'alerts', 'trace', 'scene'), 1):
        dom = yield from navigate(page)
        validate('cef_' + page, dom)
        assert_closed_labels()
        if page == 'alerts':
            check_alert_legend(dom)
        yield from pause(.2)
        yield from capture('%02d_2560x1600_%s' % (index, page))
        bottom_captures = {'inventory': '18_inventory_bottom', 'devices': '19_device_ledger_bottom',
                           'orders': '20_orders_bottom', 'alerts': '21_alerts_bottom',
                           'scene': '22_scene_settings_bottom'}
        if page in bottom_captures:
            yield from capture_page_bottom(page, bottom_captures[page])

    yield from navigate('overview')
    yield from check_tooltip()
    yield from navigate('inventory')
    yield from click('[data-action="material"]')
    dom = yield from ready('inventory', 'material-demo')
    validate('cef_inventory_demo_detail', dom)
    yield from capture('09_inventory_demo_detail')
    yield from navigate('orders')
    yield from click('[data-action="order"]')
    dom = yield from ready('orders', 'order')
    validate('cef_order_detail', dom)
    yield from capture('10_order_detail')

    yield from navigate('trace')
    yield from act('const q=document.querySelector("[data-search=trace]");q.value="SKU2038";q.dispatchEvent(new Event("input",{bubbles:true}));const d=document.querySelector("[data-filter=\\"trace.date\\"]");d.value="2026-10-20";d.dispatchEvent(new Event("change",{bubbles:true}))')
    yield from click('[data-action="trace-query"]')
    dom = yield from ready('trace')
    validate('cef_trace_search_results', dom)
    assert dom['timeline'] > 0 and not dom['empty'], dom
    yield from capture('11_trace_search_results')
    yield from act('const q=document.querySelector("[data-search=trace]");q.value="VISUAL-POLISH-NO-SUCH-RECORD";q.dispatchEvent(new Event("input",{bubbles:true}))')
    yield from click('[data-action="trace-query"]')
    dom = yield from ready('trace')
    validate('cef_trace_empty', dom)
    assert dom['empty'] and dom['timeline'] == 0, dom
    yield from capture('12_trace_empty')

    yield from navigate('scene')
    original = controls()
    yield from click('[data-action="toggle"][data-key="pois"]')
    yield from wait('poi_off_ack', lambda: controls()['pois'] is False)
    dom = yield from ready('scene')
    assert dom['settings']['pois'] is False and not poi()['labels'], dom
    yield from capture('13_scene_poi_hidden')
    yield from click('[data-action="toggle"][data-key="pois"]')
    yield from wait('poi_on_ack', lambda: controls()['pois'] is True)
    yield from pause(.2)
    assert_closed_labels()
    record('scene_switch_roundtrip', before=original, after=controls())
    yield from click('[data-action="open-warehouse"]')
    yield from wait('roof_open_via_cef', lambda: hud.is_interior_available())
    yield from pause(.3)
    opened = poi()
    assert not any(row['id'] == 'WAREHOUSE:GHS' for row in opened['labels']), opened
    dom = yield from ready('scene')
    assert dom['settings']['roofClosed'] is False, dom
    record('cef_open_roof_exposes_interior', poi=opened, controls=controls())
    yield from capture('14_scene_roof_open')

    yield from navigate('devices')
    assert hud.select_object('FORK-07', False), 'Existing scene device missing'
    dom = yield from ready('devices', 'device')
    assert dom['detail']['id'] == 'FORK-07', dom
    validate('cef_scene_device_detail', dom)
    assert any(label in dom['text'] for label in ('数据未核验', '遥测未接入')), dom
    yield from capture('15_device_detail')
    command('overview')
    yield from wait('roof_restored', lambda: pc.warehouse_roof.is_roof_closed() and not pawn.is_pose_transition_active())
    yield from navigate('overview')
    yield from pause(.3)
    record('roof_restore_hides_all_internal_poi', poi=assert_closed_labels())
    assert sorted(row['id'] for row in json.loads(hud.get_snapshot())['equipment']) == scene_ids
    record('scene_equipment_registry_preserved', count=len(scene_ids))
    assert tuple(pc.get_viewport_size()) == (2560, 1600)
    yield from capture('23_2560x1600_footer_plate')
    record('footer_plate_visual_evidence_captured', capture='23_2560x1600_footer_plate.png',
           open_roof_capture='14_scene_roof_open.png',
           scope='Actual Slate rendering; white backing and legibility require visual inspection')

    yield from capture_clean_scene_sources()
    result['asset_hashes_after'] = asset_hashes()
    assert result['asset_hashes_after'] == initial_hashes, 'Saved scene/material asset changed during gameplay verification'
    record('saved_scene_and_polish_assets_unchanged', hashes=initial_hashes)


def capture_clean_scene_sources():
    command('overview')
    yield from wait('closed_roof_before_scene_sources', lambda:
                    pc.warehouse_roof.is_roof_closed() and not pawn.is_pose_transition_active())
    pawn.get_editor_property('warehouse_camera').set_editor_property('field_of_view', 56.)
    # Shot without showui reads the scene viewport without Slate/CEF chrome.
    # Gameplay pawn changes are transient in this owned process.
    console('r.SetRes 1920x1080w')
    yield from wait('scene_capture_resolution', lambda: tuple(pc.get_viewport_size()) == (1920, 1080))
    yield from pause(.3)
    size = unreal.Vector2D(1920, 1080)
    center = unreal.Vector2D(960, 540)
    pawn.transition_to_pose(pawn.overview_center, pawn.overview_distance,
                            unreal.Rotator(pitch=pawn.overview_pitch, yaw=pawn.overview_yaw), size, center, True, .6)
    yield from wait('clean_overview_camera', lambda: not pawn.is_pose_transition_active())
    yield from pause(1)
    yield from capture('16_scene_only_overview_1920x1080', show_ui=False)
    # Same CAD coordinate registration used by capture_park_details.py.
    target = unreal.Vector((-115 - 239.33385) * 100, (90 - 60.24019) * 100, 0)
    pawn.focus_on_target(target, 26000, unreal.Rotator(pitch=-49, yaw=-110), size, center, .6)
    yield from wait('forest_camera', lambda: not pawn.is_pose_transition_active())
    yield from pause(1)
    yield from capture('17_scene_only_forest_1920x1080', show_ui=False)
    yield from capture_native_top()
    yield from capture_design_scene_sources()


def run_scene_only():
    yield from wait('discover_actual_cef', discover, 90)
    console('DisableAllScreenMessages')
    yield from wait('initial_camera', lambda: not pawn.is_pose_transition_active())
    yield from pause(2)
    record('focused_scene_capture_retry', previous_report=str(previous_report) if previous_report else None,
           scope='Only scene captures run in this process; previous UI checks are not re-certified')
    yield from capture_clean_scene_sources()
    result['asset_hashes_after'] = asset_hashes()
    assert result['asset_hashes_after'] == initial_hashes, 'Saved scene/material asset changed during gameplay verification'
    record('saved_scene_and_polish_assets_unchanged', hashes=initial_hashes)


def run_detail_refinement():
    yield from wait('discover_actual_cef', discover, 90)
    console('DisableAllScreenMessages')
    yield from wait('initial_camera', lambda: not pawn.is_pose_transition_active())
    console('r.SetRes 1920x1080w')
    yield from wait('detail_refinement_resolution', lambda: tuple(pc.get_viewport_size()) == (1920, 1080))
    yield from pause(.5)
    command('layers', building=True, racks=True, equipment=True, pois=False)
    hud.clear_selection()
    assert hud.open_warehouse(), 'Current saved scene has no usable warehouse roof'
    yield from wait('detail_refinement_roof_open', lambda: hud.is_interior_available())
    yield from capture_refined_design_details()
    pawn.get_editor_property('warehouse_camera').set_editor_property('field_of_view', 56.)
    result['asset_hashes_after'] = asset_hashes()
    assert result['asset_hashes_after'] == initial_hashes, 'Saved assets changed during detail capture'
    record('saved_scene_and_polish_assets_unchanged', hashes=initial_hashes)


def finish(error=None):
    global finished
    if finished:
        return
    finished = True
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    result.update(success=error is None, elapsed_seconds=round(time.monotonic() - started, 2), stage=stage)
    if error:
        result['error'] = error
    # Preserve this evidence even when an earlier behavioral assertion failed.
    result['asset_hashes_after'] = asset_hashes()
    result['assets_unchanged'] = result['asset_hashes_after'] == initial_hashes
    if not result['assets_unchanged']:
        result.update(success=False, asset_error='Saved scene/material assets changed')
    write()
    (unreal.log if result['success'] else unreal.log_error)('GHS_VISUAL_POLISH_RUNTIME ' + json.dumps(result, ensure_ascii=False))
    if world:
        unreal.SystemLibrary.quit_game(world, pc, unreal.QuitPreference.QUIT, False)
    else:
        unreal.SystemLibrary.execute_console_command(None, 'quit')


steps = run_detail_refinement() if DETAIL_REFINEMENT else run_scene_only() if SCENES_ONLY else run()


def tick(delta):
    try:
        assert time.monotonic() - started < 240, 'Visual polish acceptance exceeded 240 seconds'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
