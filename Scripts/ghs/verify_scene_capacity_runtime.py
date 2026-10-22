"""Scene controls acceptance in an owned -game -RenderOffscreen process only.

Requires -TwinDiagnostics -ForceRes -ResX=1920 -ResY=1080. No assets/configs are saved.
Writes Saved/SceneControls/Runtime/<UTC timestamp>/runtime.json, PNGs and CSV
timing summaries. CSV files themselves stay in Saved/Profiling/CSV. The game
quits on completion or failure. See docs/scene-controls-validation-20261023.md.
"""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import struct
import time
import traceback

import unreal

ROOT = Path('D:/UEPro/Test')
CLI = unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-' + f + r'(?=\s|$)', CLI, re.I)
           for f in ('game', 'RenderOffscreen', 'TwinDiagnostics'))
assert not re.search(r'(?:^|\s)-TwinPerf=', CLI, re.I), 'Do not combine with another profiler'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
OUT = ROOT/'Saved/SceneControls/Runtime'/STAMP
OUT.mkdir(parents=True, exist_ok=True)
MAP = ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
META = json.loads((ROOT/'Content/GHSTwinUI/data/storage-capacity.json').read_text(encoding='utf-8'))
MAP_HASH = hashlib.sha256(MAP.read_bytes()).hexdigest()
START = time.monotonic()
world = pc = hud = pawn = roof = traffic = capacity = handle = None
stage = 'discover'
finished = capturing = False
active_sample = None
original_cvars = {}
groups = []
slot_samples = []
shell = []
equipment_actors = []
probe_serial = 0
result = dict(success=False, assets_saved=False, checks=[], captures=[], performance={},
              input_scope='Native HUD commands plus real CEF DOM input/change/click events; no OS input simulation',
              performance_scope='Local editor-game offscreen, one 10s sample per state; not a server or Pixel Streaming benchmark',
              render_visibility_note='CPU visibility is evaluated on actual registered slot centers and checked against shared material parameters; PNGs require visual review for rendered geometry and shadows',
              output=str(OUT), map_sha256_before=MAP_HASH)


def write():
    result['stage'] = stage
    (OUT/'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT/'Saved/SceneControls/runtime-latest.json').write_text(json.dumps(dict(
        success=result['success'], stage=stage, report=str(OUT/'runtime.json'),
        elapsed_seconds=time.monotonic()-START, error=result.get('error')), indent=2), encoding='utf-8')


def record(name, **data):
    result['checks'].append(dict(name=name, passed=True, **data))
    write()
    unreal.log('GHS_SCENE_CAPACITY_CHECK ' + name)


def command(action, **values):
    hud.command(json.dumps(dict(action=action, **values)))


def console(value):
    unreal.SystemLibrary.execute_console_command(world, value, pc)


def controls():
    return json.loads(hud.get_scene_controls_state())


def report():
    return json.loads(capacity.get_report_json())


def poi():
    return json.loads(hud.get_poi_report())


def labels():
    return [v['id'] for v in poi()['labels']]


def browser():
    value = hud.get_editor_property('last_browser_report')
    return json.loads(value) if value else {}


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def near(a, b):
    return abs(float(a)-float(b)) < 1e-5


def wait(name, predicate, seconds=12, stable=1):
    global stage
    stage = name
    deadline = time.monotonic()+seconds
    consecutive = 0
    while True:
        assert time.monotonic() < deadline, 'Timed out: '+name
        consecutive = consecutive+1 if predicate() else 0
        if consecutive >= stable:
            return
        yield


def pause(seconds):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        yield


def discover():
    global world, pc, hud, pawn, roof, traffic, capacity
    for candidate in unreal.ObjectIterator(unreal.World):
        if not candidate.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        widget = getattr(controller, 'twin_hud_widget', None) if controller else None
        if widget and widget.browser_ready:
            world, pc, hud = candidate, controller, widget
            pawn, roof = pc.get_controlled_pawn(), pc.warehouse_roof
            traffic, capacity = pc.campus_traffic, pc.storage_capacity
            return bool(pawn and roof and traffic and capacity)
    return False


def capture(name, **data):
    path = OUT/(name+'.png')
    console('Shot showui filename="'+path.as_posix()+'" -nosuffix')
    yield from wait('capture_'+name, path.exists)
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', raw[16:24]) == (1920, 1080)
    result['captures'].append(dict(name=name, path=str(path), sha256=hashlib.sha256(raw).hexdigest(), **data))
    write()


def eval_js(script):
    assert hasattr(hud, 'evaluate_diagnostics'), 'Compile HUD EvaluateDiagnostics first'
    hud.evaluate_diagnostics(script)


def probe_dom():
    global probe_serial, stage
    probe_serial += 1
    token = probe_serial
    script = """(()=>{const p={action:'report',qaToken:%d,
        page:window.twinState.page==='scene'?'settings':window.twinState.page,
        mainBusy:document.getElementById('main').getAttribute('aria-busy')==='true',
        pageClass:document.getElementById('page').className,domAtMs:performance.now(),
        settings:window.twinState.settings,detail:window.twinState.detail,
        switches:Array.from(document.querySelectorAll('[role=switch]')).map(e=>({key:e.dataset.key,on:e.getAttribute('aria-checked')})),
        sliders:Array.from(document.querySelectorAll('[data-capacity]')).map(e=>({key:e.dataset.capacity,value:e.value,disabled:e.disabled})),
        applyButtons:document.querySelectorAll('[data-action=settings-apply]').length,
        drag:window.__sceneCapacityDrag||null,resetProbe:window.__sceneCapacityResetProbe||null,
        text:document.getElementById('page').innerText};
        window.ue.twin.command(JSON.stringify(p));})()""" % token
    # LastBrowserReport is one shared slot. A normal scheduled report can replace
    # the QA response in the same UE frame before Python polls it. Resend the same
    # token with fresh DOM data until observed; do not treat a lost reply as failure
    # of the controls. No timers/interceptors remain during performance sampling.
    stage = 'browser_dom_probe'
    deadline = time.monotonic()+8
    next_send = 0
    while True:
        current = browser()
        if current.get('qaToken') == token:
            return current
        now = time.monotonic()
        assert now<deadline, 'Timed out: browser_dom_probe token='+str(token)
        if now>=next_send:
            eval_js(script)
            next_send = now+.1
        yield


def settings_ready(name):
    """Fresh DOM handshake: an old page report cannot acknowledge navigation."""
    global stage
    hud.navigate('settings')
    deadline = time.monotonic()+8
    while True:
        dom = yield from probe_dom()
        stage = name
        result.setdefault('diagnostics',{})[name] = dict(native_controls=controls(),capacity=report(),browser=dom)
        write()
        if (dom.get('page')=='settings' and dom.get('mainBusy') is False and dom.get('detail') is None
                and len(dom.get('sliders',[]))==2 and len(dom.get('switches',[]))==4):
            return dom
        assert time.monotonic()<deadline, 'Settings DOM did not become interactive: '+name
        yield from pause(.04)


def set_capacity(rack, floor):
    command('capacity', rack=rack, floor=floor)
    yield from wait('capacity_applied', lambda: near(report()['rack_capacity'], rack) and near(report()['floor_capacity'], floor))


def build_fixtures():
    actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
    meshes = {m['name']: m for m in META['meshes']}
    by_tag = {'GHSStorageGroup:'+g['actor']: g for g in META['groups']}
    definitions_seen = set()
    for actor in actors:
        is_shell = actor.actor_has_tag('GHS_OfficeFacade') or actor.actor_has_tag('ZcoolSequentialDockNumber')
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.static_mesh
            name = mesh.get_name() if mesh else ''
            is_shell |= name.startswith('SM_GHS_V2Exterior') or name == 'SM_GHS_V2DockDoor'
            if not isinstance(component, unreal.InstancedStaticMeshComponent):
                continue
            definition = next((by_tag[str(t)] for t in component.component_tags if str(t) in by_tag), None)
            if not definition:
                continue
            assert definition['actor'] not in definitions_seen, 'Duplicate tagged storage group'
            definitions_seen.add(definition['actor'])
            assert name == definition['mesh'] and component.get_instance_count() == definition['count']
            groups.append((component, definition, meshes[name]))
            for index in range(definition['count']):
                transform = component.get_instance_transform(index, True)
                local_slots = meshes[name]['slots'] if definition['kind'] == 'rack' else [dict(index=0, min_cm=[0,0,40], max_cm=[0,0,60])]
                for slot in local_slots:
                    local = unreal.Vector(*[(a+b)*.5 for a,b in zip(slot['min_cm'],slot['max_cm'])])
                    point = unreal.MathLibrary.transform_location(transform, local)
                    global_slot = definition['base_slot']+index*definition['slots_per_instance']+slot['index']
                    parent = '{}:{}:{}:{}'.format('RACK' if definition['kind']=='rack' else 'PALLET', actor.get_name(), component.get_name(), index)
                    identity = 'MATERIAL:{}:L{}:C{}'.format(parent, slot['level'], slot['column']) if definition['kind']=='rack' else parent
                    slot_samples.append((component,index,point,definition['kind'],global_slot,identity))
        if is_shell and not actor.actor_has_tag('GHS_WarehouseRoof') and not actor.get_editor_property('hidden'):
            shell.append(actor)
    assert len(definitions_seen) == len(META['groups']) and shell
    data = json.loads(hud.get_snapshot())
    actors_by_name = {a.get_name():a for a in actors}
    equipment_actors.extend({actors_by_name[e['actor']] for e in data['equipment']+data['facilities'] if e['actor'] in actors_by_name})
    assert equipment_actors and len(data['equipment']) == 106 and len(data['facilities']) == 56
    result['initial_actor_count'] = len(actors)
    result['business_ids'] = [e['id'] for e in data['equipment']+data['facilities']]


def geometry_signature():
    digest = hashlib.sha256()
    counts = {}
    for component, definition, _ in groups:
        counts[component.get_path_name()] = component.get_instance_count()
        digest.update(component.get_path_name().encode())
        digest.update(component.static_mesh.get_path_name().encode())
        for index in range(component.get_instance_count()):
            transform = component.get_instance_transform(index, True)
            rotation = transform.rotation
            values = xyz(transform.translation)+xyz(transform.scale3d)+[rotation.x,rotation.y,rotation.z,rotation.w]
            digest.update(struct.pack('<10d',*values))
    return dict(instance_counts=counts, transforms_sha256=digest.hexdigest())


def inspect_slots(label, rack, floor, visible=True):
    """Exhaustive actual native hit predicate; yielded outside timing captures."""
    assert hasattr(capacity, 'is_storage_hit_visible'), 'Reflect native visibility predicate first'
    counts = dict(rack=0, floor=0)
    hashes = dict(rack=hashlib.sha256(), floor=hashlib.sha256())
    for ordinal, (component,index,point,kind,slot,identity) in enumerate(slot_samples):
        actual = bool(capacity.is_storage_hit_visible(component,index,point))
        total = META['rack_total_slots' if kind=='rack' else 'floor_total_slots']
        fraction = rack if kind=='rack' else floor
        expected = visible and (slot*97+17)%total < math.floor(fraction*total+.5)
        assert actual == expected, (label,identity,slot,actual,expected)
        if actual:
            counts[kind] += 1
            hashes[kind].update(struct.pack('<I',slot))
        if ordinal%500 == 499:
            yield
    for kind, fraction in (('rack',rack),('floor',floor)):
        total = META['rack_total_slots' if kind=='rack' else 'floor_total_slots']
        assert counts[kind] == (math.floor(fraction*total+.5) if visible else 0)
    # Inspect the real shared MIDs, not only values echoed by the report.
    values = {}
    floor_pair_probes = 0
    for component, definition, mesh in groups:
        for index in range(component.get_num_materials()):
            material = component.get_material(index)
            if isinstance(material, unreal.MaterialInstanceDynamic):
                value = material.get_scalar_parameter_value('StorageCapacity')
                assert near(value,rack if definition['kind']=='rack' else floor), (material.get_path_name(),value)
                values[material.get_path_name()] = value
        if definition['kind']=='floor':
            assert mesh['pallet_count']==2 and len(mesh['pallet_base_z_m'])==2
            for instance in {0,definition['count']-1}:
                transform = component.get_instance_transform(instance,True)
                pair = [bool(capacity.is_storage_hit_visible(component,instance,
                         unreal.MathLibrary.transform_location(transform,unreal.Vector(0,0,z*100+5))))
                        for z in mesh['pallet_base_z_m']]
                assert pair[0]==pair[1], 'Double blue pallets must share one visibility group'
                floor_pair_probes += 1
        if visible:
            assert component.get_editor_property('visible') and not component.get_editor_property('hidden_in_game')
            assert not component.get_owner().get_editor_property('hidden'), 'At zero capacity rack steel must remain'
    assert values, 'No live shared capacity materials'
    data = dict(counts=counts, visible_slots_sha256={k:v.hexdigest() for k,v in hashes.items()},
                native=report(), shared_material_parameters=values, double_pallet_pair_probes=floor_pair_probes)
    record(label, **data)
    return data


def camera_state():
    camera = pc.player_camera_manager
    rotation = camera.get_camera_rotation()
    return dict(position_cm=xyz(camera.get_camera_location()), rotation_deg=[rotation.pitch,rotation.yaw,rotation.roll],
                viewport=list(pc.get_viewport_size()))


def same_camera(a, b):
    return a['viewport']==b['viewport'] and all(abs(x-y)<.02 for key in ('position_cm','rotation_deg') for x,y in zip(a[key],b[key]))


def frame_stats(values):
    ordered = sorted(values)
    assert ordered
    count = len(ordered)
    long = sum(v>50 for v in ordered)
    return dict(count=count, mean_ms=statistics.fmean(ordered), median_ms=statistics.median(ordered),
                p95_ms=ordered[math.ceil(count*.95)-1], p99_ms=ordered[math.ceil(count*.99)-1], max_ms=ordered[-1],
                over_50ms_count=long, over_50ms_percent=long*100/count)


def completed_csv(path):
    try:
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-32768))
            return b'[HasHeaderRowAtEnd],1' in stream.read()
    except OSError:
        return False


def csv_metrics(path):
    raw = path.read_bytes()
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    headers = [i for i,r in enumerate(rows) if r and r[0]=='EVENTS']
    assert headers, 'Missing CSV final header'
    names = rows[headers[-1]]
    first = headers[0]+1 if len(headers)>1 else 0
    rows = [r for r in rows[first:headers[-1]] if r and not r[0].startswith('[')]
    required = ('FrameTime','GameThreadTime','RenderThreadTime','GPUTime','GPU/Total')
    assert all(n in names for n in required), ('Actual CPU/GPU columns missing',names)
    values = {name:[] for name in required}
    for row in rows:
        for name in required:
            value = float(row[names.index(name)])
            assert math.isfinite(value) and value>=0, (name,value)
            values[name].append(value)
    assert len(rows)>=50, 'Too few native frame samples'
    for name in ('GPUTime','GPU/Total'):
        assert sum(v>0 for v in values[name])>=len(rows)*.95, name+' lacks valid GPU timestamps'
    return dict(csv=str(path), csv_sha256=hashlib.sha256(raw).hexdigest(), metrics={k:frame_stats(v) for k,v in values.items()},
                native_frame_time_seconds=sum(values['FrameTime'])/1000,
                sample_window='All CSV frames between start/stop; boundary setup/drain frames are retained equally, no spikes discarded')


def start_drag():
    eval_js("""(()=>{const d=window.__sceneCapacityDrag={started:performance.now(),inputs:0,done:false};
        const send=(key,value,type)=>{const e=document.querySelector('[data-capacity="'+key+'"]');if(!e||e.disabled){d.error='missing or disabled '+key;return;}e.value=String(value);e.dispatchEvent(new Event(type,{bubbles:true}));d.inputs++;};
        const timer=setInterval(()=>{const t=(performance.now()-d.started)/1000;
          if(t>=10){clearInterval(timer);send('rackCapacity',80,'input');send('floorCapacity',100,'change');d.elapsedMs=performance.now()-d.started;d.done=true;return;}
          const x=(t%%2)/2;const v=Math.round((x<.5?2*x:2-2*x)*100);
          send('rackCapacity',v,'input');send('floorCapacity',100-v,'input');},8);})()""".replace('%%','%'))


def sample_performance(name, drag=False):
    global active_sample, capturing
    before = report()
    view = camera_state()
    filename = 'SceneCapacity_'+STAMP+'_'+name+'.csv'
    path = ROOT/'Saved/Profiling/CSV'/filename
    assert not path.exists()
    console('CsvProfile STARTFILE='+filename)
    console('CsvProfile START')
    capturing = True
    active_sample = dict(name=name, delta_ms=[], wall_ms=[], previous=None, camera=view)
    if drag:
        start_drag()
    yield from pause(10.25 if drag else 10.0)
    console('CsvProfile STOP')
    capturing = False
    captured = active_sample
    active_sample = None
    yield from wait('csv_'+name,lambda:completed_csv(path),seconds=15)
    assert same_camera(view,camera_state()), 'Camera or resolution changed during '+name
    data = dict(camera=view, native_before=before,native_after=report(),
                slate_delta=frame_stats(captured['delta_ms']),slate_wall_interval=frame_stats(captured['wall_ms']),
                slate_note='Slate post-tick intervals; not GameThreadTime, RenderThreadTime, or GPUTime')
    try:
        data['native_csv'] = csv_metrics(path)
        data['gpu_verified'] = True
    except Exception:
        data.update(gpu_verified=False,native_csv_error=traceback.format_exc(),csv=str(path))
    if drag:
        dom = yield from probe_dom()
        assert dom['drag']['done'] and not dom['drag'].get('error'),dom
        assert near(report()['rack_capacity'],.8) and near(report()['floor_capacity'],1)
        updates = report()['capacity_updates']-before['capacity_updates']
        assert 5<updates<=10.25*30+6, ('Native material updates exceed 30Hz coalescing budget',updates)
        data.update(browser_drag=dom['drag'],native_capacity_updates=updates)
    result['performance'][name] = data
    write()


def performance_comparison():
    baseline = result['performance']['default_80_100']
    comparisons = {}
    for name,data in result['performance'].items():
        if name=='default_80_100':
            continue
        assert same_camera(baseline['camera'],data['camera'])
        compare = {}
        if baseline['gpu_verified'] and data['gpu_verified']:
            for metric,current in data['native_csv']['metrics'].items():
                base = baseline['native_csv']['metrics'][metric]
                compare[metric] = {key:current[key]-base[key] for key in ('mean_ms','median_ms','p95_ms','max_ms','over_50ms_count','over_50ms_percent')}
                compare[metric]['over_50ms_rate_delta_per_second'] = current['over_50ms_count']/data['native_csv']['native_frame_time_seconds']-base['over_50ms_count']/baseline['native_csv']['native_frame_time_seconds']
        comparisons[name] = compare
    result['performance_vs_default'] = comparisons
    result['performance_note'] = 'Measured differences include scene load at each capacity and traffic animation. A single local run does not establish statistical significance or a performance SLA.'


def run():
    yield from wait('discover',discover,seconds=60)
    assert tuple(pc.get_viewport_size())==(1920,1080), 'Launch with -ResX=1920 -ResY=1080 -windowed'
    console('DisableAllScreenMessages')
    yield from wait('initial_camera',lambda:not pawn.is_pose_transition_active(),stable=4)
    yield from pause(1)
    initial = controls()
    assert all(initial[k] for k in ('building','equipment','racks','pois'))
    assert near(initial['rackCapacity'],.8) and near(initial['floorCapacity'],1) and initial['density']=='auto'
    assert roof.is_roof_closed() and not hud.is_interior_available() and labels()==['WAREHOUSE:GHS']
    assert report()['initialized'] and not report()['error'] and report()['initialization_scans']==1
    build_fixtures()
    signature = geometry_signature()
    initial_traffic = json.loads(traffic.get_traffic_report_json())
    assert initial_traffic['capacity']==32 and initial_traffic['fixed_instances']==32
    assert initial_traffic['component_count']==4 and initial_traffic['route_count']==6
    record('defaults_closed_interior_locked_main_poi_only',controls=initial,capacity=report(),traffic=initial_traffic)
    dom = yield from settings_ready('settings_page')
    assert len(dom['switches'])==4 and len(dom['sliders'])==2 and dom['applyButtons']==0
    assert [int(s['value']) for s in dom['sliders']]==[80,100] and all(not s['disabled'] for s in dom['sliders'])
    record('actual_cef_settings_dom',browser=dom)
    yield from capture('01-settings-closed-default')
    # Closed-roof capacity edits must retain the interaction lock and camera.
    before_view = camera_state()
    yield from set_capacity(.37,.62)
    assert roof.is_roof_closed() and not hud.is_interior_available() and same_camera(before_view,camera_state())
    command('layers',pois=False)
    yield from wait('main_poi_off',lambda:not labels())
    command('overview')
    yield from wait('overview_without_poi',lambda:not pawn.is_pose_transition_active())
    assert not labels() and near(controls()['rackCapacity'],.37)
    command('layers',pois=True)
    yield from wait('main_poi_on',lambda:labels()==['WAREHOUSE:GHS'])
    record('closed_capacity_and_main_poi_follow_controls')
    # A newer top view supersedes the region flight queued behind roof opening.
    command('preset',value='racks')
    assert roof.is_opening() and poi()['pendingNavigation']=='region'
    command('preset',value='top')
    assert not poi()['pendingNavigation']
    yield from wait('latest_top_roof_open',roof.is_interior_available)
    yield from wait('latest_top_camera',lambda:not pawn.is_pose_transition_active(),stable=4)
    assert not pawn.uses_object_pivot(), 'A late region callback replaced the requested top view'
    assert abs(pawn.get_actor_rotation().pitch+78)<.05
    expected_top = xyz(pawn.get_editor_property('overview_center'))
    expected_top[2] = 0
    assert math.dist(xyz(pawn.get_focus_target()),expected_top)<.05
    top_view = camera_state()
    yield from pause(.7)
    assert same_camera(top_view,camera_state()) and not poi()['pendingNavigation']
    record('top_preset_supersedes_pending_rack_flight',camera=top_view,focus_target_cm=expected_top)
    command('overview')
    yield from wait('closed_after_top_regression',lambda:not pawn.is_pose_transition_active())
    assert roof.is_roof_closed()
    # Pending open: reverse shell preference before the 0.5s transition finishes.
    command('layers',building=False)
    assert roof.is_opening() and not hud.is_interior_available()
    assert all(not a.get_editor_property('hidden') for a in shell)
    command('layers',building=True)
    while not roof.is_interior_available():
        assert not labels() and not hud.selected_id
        yield
    assert all(not a.get_editor_property('hidden') for a in shell) and controls()['building']
    record('rapid_shell_reverse_keeps_wall_opens_roof')
    command('layers',building=False,equipment=False)
    yield from pause(.2)
    assert all(a.get_editor_property('hidden') for a in shell)
    assert all(a.get_editor_property('hidden') for a in equipment_actors)
    yield from pause(2.2)
    assert all(a.get_editor_property('hidden') for a in shell+equipment_actors)
    record('actual_shell_equipment_hidden_survive_business_refresh',shell_actor_count=len(shell),equipment_actor_count=len(equipment_actors))
    # Explicit locate auto-enables equipment. Reset invalidates pending focus.
    command('overview')
    yield from wait('closed_before_focus',lambda:not pawn.is_pose_transition_active())
    command('focus',id='AGV-07')
    assert controls()['equipment'] and roof.is_opening()
    command('overview')
    yield from pause(1.0)
    assert roof.is_roof_closed() and not hud.selected_id and not poi()['pendingNavigation']
    assert all(not a.get_editor_property('hidden') for a in shell)
    command('layers',equipment=False)
    command('focus',id='AGV-07')
    yield from wait('locate_opens_roof',roof.is_interior_available)
    yield from wait('locate_camera',lambda:not pawn.is_pose_transition_active(),stable=4)
    assert controls()['equipment'] and all(not a.get_editor_property('hidden') for a in equipment_actors)
    record('locate_auto_enables_equipment_and_overview_cancels_pending')
    assert hud.select_object('AGV-07',False)
    command('layers',equipment=False)
    yield from wait('hidden_equipment_selection_cleared',lambda:not hud.selected_id)
    yield from pause(2.1)
    assert not hud.selected_id and browser().get('detail') is None
    record('hidden_equipment_selection_stays_clear_after_refresh')
    command('overview')
    yield from wait('closed_before_reset',lambda:not pawn.is_pose_transition_active())
    command('layers',building=False)
    command('focus',id='FORK-07')
    command('settingsReset')
    while not roof.is_interior_available():
        assert not hud.selected_id and not poi()['pendingNavigation']
        yield
    yield from pause(.9)
    assert controls()['building'] and all(not a.get_editor_property('hidden') for a in shell)
    assert not hud.selected_id and not poi()['pendingNavigation'] and not pawn.is_pose_transition_active()
    before_view = camera_state()
    command('settingsReset')
    yield from pause(.2)
    assert roof.is_interior_available() and same_camera(before_view,camera_state())
    record('defaults_cancel_pending_actions_preserve_open_state_and_camera')
    before_reset = yield from settings_ready('settings_before_drag_cancel')
    result['diagnostics']['pending_capacity_reset_before'] = dict(native_controls=controls(),capacity=report(),browser=before_reset)
    write()
    eval_js("""(()=>{const snapshot=()=>({settings:JSON.parse(JSON.stringify(window.twinState.settings)),
        busy:document.getElementById('main').getAttribute('aria-busy'),page:window.twinState.page,
        pageClass:document.getElementById('page').className,atMs:performance.now()});
        const p=window.__sceneCapacityResetProbe={before:snapshot()};
        const e=document.querySelector('[data-capacity=rackCapacity]');const reset=document.querySelector('[data-action=settings-reset]');
        if(!e||e.disabled||!reset||reset.disabled){p.error='missing or disabled reset fixture';return;}
        e.value='13';e.dispatchEvent(new Event('input',{bubbles:true}));p.afterInput=snapshot();
        reset.click();p.afterClick=snapshot();})()""")
    yield from pause(.3)
    after_reset = yield from probe_dom()
    result['diagnostics']['pending_capacity_reset_after'] = dict(native_controls=controls(),capacity=report(),browser=after_reset)
    write()
    stimulus = after_reset.get('resetProbe') or {}
    assert not stimulus.get('error') and stimulus.get('afterClick'), stimulus
    assert stimulus['before']['busy']!='true' and near(stimulus['afterInput']['settings']['rackCapacity'],.13), stimulus
    assert near(stimulus['afterClick']['settings']['rackCapacity'],.8) and near(stimulus['afterClick']['settings']['floorCapacity'],1), stimulus
    assert near(report()['rack_capacity'],.8) and near(report()['floor_capacity'],1), result['diagnostics']['pending_capacity_reset_after']
    record('cef_reset_cancels_pending_capacity',before=result['diagnostics']['pending_capacity_reset_before'],after=result['diagnostics']['pending_capacity_reset_after'])
    command('layers',racks=False)
    yield from pause(.2)
    dom = yield from probe_dom()
    assert all(s['disabled'] for s in dom['sliders']) and near(controls()['rackCapacity'],.8)
    yield from inspect_slots('storage_hidden_no_cpu_hits_values_retained',.8,1,False)
    command('layers',racks=True)
    default_slots = yield from inspect_slots('default_native_slot_counts',.8,1)
    # Public selection plus actual scene click path, then capacity-based removal.
    for kind in ('rack','floor'):
        sample = next(s for s in slot_samples if s[3]==kind and capacity.is_storage_hit_visible(s[0],s[1],s[2]))
        component,index,point,_,slot,identity = sample
        assert hud.select_object(identity,False),(kind,identity)
        assert hud.selected_id==identity
        yield from set_capacity(0 if kind=='rack' else .8,0 if kind=='floor' else 1)
        yield from wait('hidden_selection_cleared_'+kind,lambda:not hud.selected_id)
        assert not hud.select_object(identity,False), 'Hidden cargo must not become selected'
        yield from pause(2.1)
        assert not hud.selected_id and browser().get('detail') is None
        record('hidden_'+kind+'_selection_clears_and_stays_clear',identity=identity)
        yield from set_capacity(.8,1)
    # Exercise screen-ray selection using an actual visible highest rack slot.
    command('layers',pois=False)
    yield from set_capacity(1,1)
    rack_samples = [s for s in slot_samples if s[3]=='rack']
    target_sample = max(rack_samples[:80],key=lambda s:s[2].z)
    target = target_sample[2]
    view = hud.get_viewport_pixel_size()
    pawn.focus_on_target(target,3500,unreal.Rotator(pitch=-65,yaw=-90,roll=0),
                         view,unreal.Vector2D(hud.get_panel_position().x*.5,view.y*.55),0)
    yield from pause(.3)
    hit_screen = None
    for sample in sorted(rack_samples[:80],key=lambda s:s[2].z,reverse=True):
        screen = unreal.GameplayStatics.project_world_to_screen(pc,sample[2],False)
        if screen is not None and hud.is_scene_point(screen):
            hud.handle_scene_click(screen)
            if hud.selected_id.startswith('MATERIAL:'):
                hit_screen = screen
                break
    assert hit_screen is not None,'Visible complete rack cargo could not be selected through scene ray'
    picked = hud.selected_id
    # Scene click starts a focus flight; freeze it so the hidden test casts the same ray.
    pawn.freeze_current_pose()
    yield from set_capacity(0,0)
    yield from wait('ray_selection_removed',lambda:not hud.selected_id)
    hud.handle_scene_click(hit_screen)
    assert not hud.selected_id.startswith(('MATERIAL:','PALLET:')),'Zero-capacity scene ray selected hidden cargo'
    hud.clear_selection()
    command('layers',racks=False)
    hud.handle_scene_click(hit_screen)
    assert not hud.selected_id.startswith(('MATERIAL:','PALLET:')),'Storage-disabled scene ray selected cargo'
    record('actual_screen_ray_rejects_zero_and_disabled_storage',visible_picked=picked,screen_pixels=[hit_screen.x,hit_screen.y])
    command('settingsReset')
    yield from wait('defaults_after_ray',lambda:near(report()['rack_capacity'],.8) and near(report()['floor_capacity'],1))
    # Choose a fixed scene view; all 0/80/100 screenshots and timing samples share it.
    command('preset',value='racks')
    yield from wait('fixed_rack_camera',lambda:not pawn.is_pose_transition_active(),stable=4)
    yield from settings_ready('settings_for_capacity_capture')
    eval_js("document.getElementById('main').scrollTop=420;")
    yield from pause(.3)
    fixed_view = camera_state()
    yield from capture('02-capacity-080-100',capacity=report(),camera=fixed_view)
    yield from set_capacity(0,0)
    yield from inspect_slots('zero_native_slot_counts_steel_retained',0,0)
    yield from pause(.5)
    yield from capture('03-capacity-000-000',capacity=report(),camera=camera_state())
    yield from set_capacity(1,1)
    yield from inspect_slots('full_native_slot_counts',1,1)
    yield from pause(.5)
    yield from capture('04-capacity-100-100',capacity=report(),camera=camera_state())
    yield from set_capacity(.8,1)
    restored = yield from inspect_slots('restored_default_stable_slot_order',.8,1)
    assert restored['visible_slots_sha256']==default_slots['visible_slots_sha256']
    assert geometry_signature()==signature
    record('full_zero_default_fixed_instances_stable_positions',signature=signature)
    temporary = {'r.GPUStatsEnabled':1,'r.GPUCsvStatsEnabled':1,'csv.CompressionMode':0,
                 't.MaxFPS':0,'r.VSync':0,'r.VSyncEditor':0,'t.IdleWhenNotForeground':0,
                 'Slate.bAllowThrottling':0,'r.DynamicRes.OperationMode':0,'r.ScreenPercentage':100}
    for key,value in temporary.items():
        original = unreal.SystemLibrary.get_console_variable_string_value(key)
        assert original!='', 'Missing performance cvar '+key
        original_cvars[key] = original
        console(key+' '+str(value))
    result['performance_cvars'] = temporary
    console('stat unit')
    yield from pause(3)
    # stat unit is visible in this capture; CSV supplies machine-readable CPU/GPU evidence.
    yield from capture('05-stat-unit-default',camera=fixed_view)
    yield from pause(.5)
    yield from sample_performance('default_80_100')
    yield from set_capacity(0,0)
    yield from pause(1)
    yield from sample_performance('zero_0_0')
    yield from set_capacity(1,1)
    yield from pause(1)
    yield from sample_performance('full_100_100')
    yield from set_capacity(.8,1)
    yield from pause(1)
    yield from sample_performance('continuous_browser_drag',True)
    console('stat unit')
    performance_comparison()
    assert geometry_signature()==signature and report()['initialization_scans']==1
    assert len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))==result['initial_actor_count']
    record('drag_material_updates_no_rescan_or_instance_growth',capacity=report(),signature=signature)
    # Explicit world-space road mouths, each centered in the actual viewport.
    hud.navigate('overview')
    for name,x,y in (('06-west-road-mouth',-43633.385,-11687.6301),('07-east-road-mouth',45600.7231,-8047.7124)):
        target = unreal.Vector(x,y,0)
        viewport = hud.get_viewport_pixel_size()
        pane = hud.get_panel_position()
        pawn.transition_to_pose(target,11000,unreal.Rotator(pitch=-65,yaw=-90,roll=0),
                                viewport,unreal.Vector2D(pane.x*.5,viewport.y*.54),False,0)
        yield from pause(.6)
        screen = unreal.GameplayStatics.project_world_to_screen(pc,target,False)
        assert screen is not None and hud.is_scene_point(screen)
        yield from capture(name,world_cm=[x,y,0],screen_pixels=[screen.x,screen.y],camera=camera_state())
    final_traffic = json.loads(traffic.get_traffic_report_json())
    assert final_traffic['fixed_instances']==32 and final_traffic['component_count']==4 and final_traffic['peak_active']<=32
    current = json.loads(hud.get_snapshot())
    assert [e['id'] for e in current['equipment']+current['facilities']]==result['business_ids']
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==MAP_HASH
    record('traffic_business_ids_map_preserved',traffic=final_traffic,map_sha256=MAP_HASH)
    assert all(v['gpu_verified'] for v in result['performance'].values()), 'Actual GPU timings missing; inspect native_csv_error, do not substitute Slate timings'


def finish(error=None):
    global finished, handle, active_sample
    if finished:
        return
    finished = True
    active_sample = None
    if capturing and world:
        console('CsvProfile STOP')
    restore_errors = []
    for key,value in original_cvars.items():
        try:
            console(key+' '+value)
        except Exception:
            restore_errors.append(traceback.format_exc())
    if restore_errors and not error:
        error = '\n'.join(restore_errors)
    result.update(success=error is None,elapsed_seconds=time.monotonic()-START,restored_cvars=not restore_errors)
    if error:
        result['error'] = error
        if hud and capacity:
            try:
                result['failure_state'] = dict(native_controls=controls(),capacity=report(),
                                               selected_id=str(hud.selected_id),poi=poi(),browser=browser())
            except Exception:
                result['failure_state_error'] = traceback.format_exc()
    try:
        result['map_sha256_after'] = hashlib.sha256(MAP.read_bytes()).hexdigest()
        assert result['map_sha256_after']==MAP_HASH
    except Exception:
        result.update(success=False,map_verification_error=traceback.format_exc())
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
        handle = None
    (unreal.log_error if not result['success'] else unreal.log)('GHS_SCENE_CAPACITY_RUNTIME '+str(OUT/'runtime.json'))
    if world:
        unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)


steps = run()


def tick(delta):
    if finished:
        return
    now = time.monotonic()
    if active_sample is not None:
        if math.isfinite(delta) and delta>0:
            active_sample['delta_ms'].append(float(delta)*1000)
        previous = active_sample['previous']
        if previous is not None:
            active_sample['wall_ms'].append((now-previous)*1000)
        active_sample['previous'] = now
    try:
        assert now-START<210, 'Acceptance deadline exceeded (210 seconds including startup)'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
