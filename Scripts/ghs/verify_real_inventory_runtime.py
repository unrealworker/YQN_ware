"""Exercise real snapshot selection and material masks in an owned UE game.

Run with -game -RenderOffscreen -TwinDiagnostics, never in a user's editor.
No asset or map is saved. Reports and actual CEF screenshots stay in output/.
"""
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
CLI = unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)', CLI, re.I)
           for flag in ('game', 'RenderOffscreen', 'TwinDiagnostics'))
REAUDIT = bool(re.search(r'(?:^|\s)-InventoryReaudit(?=\s|$)', CLI, re.I))
OUT = ROOT/('output/ghs-inventory-reaudit-20261125/runtime' if REAUDIT else 'output/ghs-inventory-20261125/runtime')
OUT.mkdir(parents=True, exist_ok=True)
MAP = ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
MAP_HASH = hashlib.sha256(MAP.read_bytes()).hexdigest()
DATA = ROOT/'Content/GHSTwinUI/data'
META = json.loads((DATA/'storage-capacity.json').read_text(encoding='utf8'))
BINDINGS = json.loads((DATA/'inventory-bindings.json').read_text(encoding='utf8'))['bindings']
INDEX = json.loads((DATA/'inventory/index.json').read_text(encoding='utf8'))
LOCATIONS = {x['id']: x for x in INDEX['locations']}
REGISTRY = json.loads((DATA/'scene-bindings.json').read_text(encoding='utf8'))
started = time.monotonic()
world = pc = hud = pawn = capacity = handle = None
finished = False
stage = 'discover'
token = 0
result = dict(success=False, assets_saved=False, checks=[], captures=[], map_sha256_before=MAP_HASH,
              bindings_sha256=hashlib.sha256((DATA/'inventory-bindings.json').read_bytes()).hexdigest())


def write():
    result['stage'] = stage
    (OUT/'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')


def record(name, **values):
    result['checks'].append(dict(name=name, passed=True, **values))
    write()
    unreal.log('GHS_REAL_INVENTORY_CHECK '+name)


def wait(name, condition, timeout=25):
    global stage
    stage = name
    end = time.monotonic()+timeout
    while not condition():
        assert time.monotonic()<end, 'Timed out: '+name
        yield


def pause(seconds):
    end = time.monotonic()+seconds
    while time.monotonic()<end:
        yield


def discover():
    global world, pc, hud, pawn, capacity
    for candidate in unreal.ObjectIterator(unreal.World):
        if not candidate.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        widget = getattr(controller, 'twin_hud_widget', None) if controller else None
        if widget and widget.browser_ready:
            world, pc, hud = candidate, controller, widget
            pawn, capacity = pc.get_controlled_pawn(), pc.storage_capacity
            return bool(pawn and capacity)
    return False


def command(action, **values):
    hud.command(json.dumps(dict(action=action, **values)))


def report():
    raw = hud.get_editor_property('last_browser_report') if hud else ''
    return json.loads(raw) if raw else {}


def probe():
    global token
    token += 1
    script = """(()=>{const p=document.getElementById('page');window.ue.twin.command(JSON.stringify({
      action:'report',inventoryQAToken:%d,page:window.twinState.page,detail:window.twinState.detail,
      busy:document.getElementById('main').getAttribute('aria-busy')==='true',
      text:p.innerText,overflow:document.documentElement.scrollWidth>innerWidth+1,
      errors:window.__inventoryQAErrors||[],settings:window.twinState.settings
    }));})()""" % token
    end, next_send = time.monotonic()+12, 0
    while True:
        current = report()
        if current.get('inventoryQAToken') == token:
            return current
        now = time.monotonic()
        assert now<end, 'CEF inventory probe timed out'
        if now>=next_send:
            hud.evaluate_diagnostics(script)
            next_send = now+.12
        yield


def settle_text(required, timeout=25):
    end = time.monotonic()+timeout
    while True:
        value = yield from probe()
        if not value['busy'] and all(text in value['text'] for text in required):
            assert not value['overflow'], value
            return value
        assert time.monotonic()<end, (required, value)
        yield from pause(.1)


def capture(name):
    path = OUT/(name+'.png')
    old = path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world, 'Shot showui filename="'+path.as_posix()+'" -nosuffix', pc)
    yield from wait('capture_'+name, lambda:path.exists() and path.stat().st_mtime_ns!=old)
    result['captures'].append(str(path))
    write()


def fixture(binding):
    candidates = []
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.static_mesh
            model = next((x for x in META['meshes'] if mesh and x['name']==mesh.get_name()), None)
            if not model:
                continue
            entries = [item for group in REGISTRY['groups'] if group['mesh']==model['source_mesh'] for item in group['instances']]
            if len(entries)!=component.get_instance_count():
                continue
            for index, item in enumerate(entries):
                if item['id']!=binding['cadId']:
                    continue
                slot = next(x for x in model['slots'] if x['level']==binding['level'] and x['column']==binding['column'])
                transform = component.get_instance_transform(index, True)
                local = unreal.Vector(*[(a+b)*.5 for a,b in zip(slot['min_cm'],slot['max_cm'])])
                foot = unreal.Vector(local.x, local.y, slot['min_cm'][2]+2)
                candidates.append(dict(component=component, index=index, slot=slot, transform=transform,
                    center=unreal.MathLibrary.transform_location(transform,local),
                    foot=unreal.MathLibrary.transform_location(transform,foot),
                    id=f"MATERIAL:RACK:{actor.get_name()}:{component.get_name()}:{index}:L{binding['level']}:C{binding['column']}"))
    assert len(candidates)==1, (binding,len(candidates))
    return candidates[0]


def frame_fixture(item):
    viewport = hud.get_viewport_pixel_size()
    pane = hud.get_panel_position()
    pawn.transition_to_pose(item['center'], 1600, unreal.Rotator(pitch=-70,yaw=0,roll=0),
        viewport,unreal.Vector2D(pane.x*.5,viewport.y*.52),False,0)
    yield from pause(1)


def verify_mask(item, location):
    # Raw instance custom data is deliberately not Python-reflected in UE5.8.
    # Native automation verifies its bit words. Here verify actual component
    # material parameters, shared hit visibility, then inspect rendered captures.
    visible = capacity.is_storage_hit_visible(item['component'],item['index'],item['center'])
    assert visible==(location['state']=='occupied'), (location,visible)
    version = item['component'].get_material(4).get_scalar_parameter_value('InventoryMaskVersion')
    assert version==1, version
    return dict(material_version=version,cargo_visible=visible)


def run():
    yield from wait('discover',discover,180)
    yield from wait('initial_camera',lambda:not pawn.is_pose_transition_active())
    yield from pause(2)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    hud.evaluate_diagnostics("window.__inventoryQAErrors=[];window.addEventListener('error',e=>window.__inventoryQAErrors.push(e.message));")
    cap = json.loads(capacity.get_report_json())
    assert cap['inventory_bound_slots']==len(BINDINGS), cap
    assert json.loads(hud.get_scene_controls_state())['inventoryMode']
    assert pc.warehouse_roof.is_roof_closed()
    record('native_binding_coverage',capacity=cap)
    hud.navigate('inventory')
    dom = yield from settle_text(['91,106','23,232','67,874'])
    assert pc.warehouse_roof.is_roof_closed()
    record('cef_real_inventory_list',text=dom['text'][:3500])
    yield from capture('01-inventory-list')

    # Recreate the previously observed noisy SR rack view at exactly the same
    # camera pose, before using an unobstructed top-tier empty slot for picking.
    noisy = fixture(next(x for x in BINDINGS if x['locationCode']=='GHS-SR-02-27-04'))
    assert hud.select_object(noisy['id'],False)
    yield from wait('roof_open_for_material_comparison',hud.is_interior_available)
    viewport=hud.get_viewport_pixel_size()
    pawn.transition_to_pose(noisy['center'],1200,unreal.Rotator(pitch=-20,yaw=0,roll=0),
        viewport,unreal.Vector2D(hud.get_panel_position().x*.5,viewport.y*.52),False,0)
    yield from pause(2)
    yield from capture('00-sr-mask-after-fix')
    pair = tuple(next(x for x in BINDINGS if x['locationCode']==code)
                 for code in ('GHS-R02-43-04','GHS-R02-44-02'))
    for binding in pair:
        item=fixture(binding)
        location=LOCATIONS[binding['locationId']]
        mask=verify_mask(item,location)
        assert hud.select_object(item['id'],False)
        yield from wait('roof_open',hud.is_interior_available)
        yield from frame_fixture(item)
        dom=yield from settle_text([binding['locationCode'],'按编码规则匹配'])
        native=json.loads(hud.get_snapshot())['selection']
        assert native['inventory']['mappingStatus']=='mapped',native
        assert native['inventory']['location']['id']==binding['locationId'],native
        assert native['inventory']['location']['state']==location['state'],native
        assert not dom['errors'], dom['errors']
        record('real_'+location['state']+'_detail',code=binding['locationCode'],mask=mask,selection=native)
        yield from capture('02-'+location['state']+'-location')
        if location['state']=='empty':
            hud.clear_selection()
            screen=unreal.GameplayStatics.project_world_to_screen(pc,item['foot'],False)
            assert screen is not None and hud.is_scene_point(screen)
            assert hud.handle_scene_click(screen), (screen,item['id'])
            assert str(hud.selected_id)==item['id'], (str(hud.selected_id),item['id'])
            record('empty_physical_slot_mouse_pick',id=item['id'],screen=[screen.x,screen.y])
        command('capacity',rack=0,floor=1)
        yield from wait('capacity_zero',lambda:json.loads(capacity.get_report_json())['rack_capacity']==0)
        assert verify_mask(item,location)==mask
        command('capacity',rack=1,floor=1)
        yield from wait('capacity_one',lambda:json.loads(capacity.get_report_json())['rack_capacity']==1)
        assert verify_mask(item,location)==mask
        record('real_occupancy_ignores_preview_slider_'+location['state'])

    if REAUDIT:
        cases = [
            ('special_s06', next(x for x in BINDINGS if x['cadId']=='CAD_369D01_369ADD' and x['level']==6 and x['column']==3)),
            ('corrected_r31_pass', next(x for x in BINDINGS if x.get('cadResolution',{}).get('originalRow')=='R31' and x.get('cadResolution',{}).get('originalBay')=='15' and x.get('cadResolution',{}).get('resolvedBay')=='13')),
            ('leading_zero_code', next(x for x in BINDINGS if x['locationCode']=='GHS-SR-02-073-01')),
        ]
        for name, binding in cases:
            item=fixture(binding)
            location=LOCATIONS[binding['locationId']]
            mask=verify_mask(item,location)
            assert hud.select_object(item['id'],False)
            yield from frame_fixture(item)
            dom=yield from settle_text([binding['locationCode'],'按编码规则匹配'])
            native=json.loads(hud.get_snapshot())['selection']
            assert native['inventory']['mappingStatus']=='mapped',native
            assert native['inventory']['location']['id']==binding['locationId'],native
            assert native['inventory']['location']['state']==location['state'],native
            assert not dom['errors'],dom['errors']
            record(name,code=binding['locationCode'],mask=mask,selection=native)
            if name=='special_s06':
                assert binding['locationCode']=='GHS-SR-06-39-12'
                assert location['state']=='empty'
                hud.clear_selection()
                screen=unreal.GameplayStatics.project_world_to_screen(pc,item['foot'],False)
                assert screen is not None and hud.is_scene_point(screen)
                assert hud.handle_scene_click(screen)
                assert str(hud.selected_id)==item['id'],(str(hud.selected_id),item['id'])
                yield from settle_text([binding['locationCode']])
                record('special_s06_empty_mouse_pick',id=item['id'])
            yield from capture('reaudit-'+name)
        disputed=dict(cadId='CAD_36E079_36E021',level=1,column=1)
        assert not any(x['cadId']==disputed['cadId'] for x in BINDINGS)
        item=fixture(disputed)
        assert hud.select_object(item['id'],False)
        yield from frame_fixture(item)
        yield from settle_text(['库位编码未匹配'])
        native=json.loads(hud.get_snapshot())['selection']
        assert native['inventory']['mappingStatus']=='unmapped',native
        record('conflicting_bay_not_presented_as_verified_inventory',selection=native)
        yield from capture('reaudit-conflicting-bay')

    frozen=next(x for x in BINDINGS if LOCATIONS[x['locationId']]['quantity']>0 and LOCATIONS[x['locationId']]['availableQuantity']==0)
    item=fixture(frozen)
    assert hud.select_object(item['id'],False)
    yield from settle_text([frozen['locationCode']])
    native=json.loads(hud.get_snapshot())['selection']
    assert native['inventory']['location']['state']=='occupied'
    assert native['inventory']['location']['totals']['availableQuantity']==0
    record('zero_available_still_occupied',code=frozen['locationCode'])
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor):
        floor=next((c for c in actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
                    if c.static_mesh and c.static_mesh.get_name().startswith('SM_GHS_Presentation_Cargo')),None)
        if floor and floor.get_instance_count():
            floor_id=f'PALLET:{actor.get_name()}:{floor.get_name()}:0'
            assert hud.select_object(floor_id,False)
            dom=yield from settle_text(['库位编码未匹配'])
            record('unmapped_floor_not_treated_as_empty',id=floor_id)
            break
    else:
        raise AssertionError('Floor fixture not found')
    command('layers',racks=False)
    yield from pause(.3)
    screen=unreal.GameplayStatics.project_world_to_screen(pc,item['foot'],False)
    hud.clear_selection()
    if screen and hud.is_scene_point(screen):
        hud.handle_scene_click(screen)
        assert str(hud.selected_id)!=item['id']
    assert not capacity.is_storage_hit_visible(item['component'],item['index'],item['center'])
    command('layers',racks=True)
    command('settingsReset')
    before_replay=json.loads(capacity.get_report_json())
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-11-25T12:00:00.000Z',endUtc='2026-11-25T13:00:00.000Z')
    yield from wait('replay_active',lambda:json.loads(hud.get_replay_state()).get('active',False))
    command('replaySeek',time=230)
    yield from pause(1)
    command('replayPause')
    command('replayEndRequest')
    command('replayExitConfirm')
    yield from wait('replay_restored',lambda:not json.loads(hud.get_replay_state()).get('active',False))
    after_replay=json.loads(capacity.get_report_json())
    for key in ('inventory_bound_slots','inventory_empty_slots','inventory_occupied_slots'):
        assert before_replay[key]==after_replay[key],(before_replay,after_replay)
    record('replay_restores_real_inventory',counts={k:after_replay[k] for k in ('inventory_bound_slots','inventory_empty_slots','inventory_occupied_slots')})
    command('overview')
    yield from wait('roof_restored',lambda:pc.warehouse_roof.is_roof_closed())
    assert json.loads(capacity.get_report_json())['initialization_scans']==cap['initialization_scans']
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==MAP_HASH
    record('layers_roof_and_scene_preserved')


def finish(error=None):
    global finished,handle
    finished=True
    result.update(success=error is None,elapsed_seconds=time.monotonic()-started,
                  map_sha256_after=hashlib.sha256(MAP.read_bytes()).hexdigest())
    if error:
        result['error']=error
        result['browser']=report()
        if capacity:
            result['capacity']=json.loads(capacity.get_report_json())
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if error is None else unreal.log_error)('GHS_REAL_INVENTORY_RUNTIME '+str(OUT/'runtime.json'))
    if world:
        unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)


steps=run()
def tick(delta):
    if finished:
        return
    try:
        assert time.monotonic()-started<420,'Runtime validation deadline exceeded'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())

write()
handle=unreal.register_slate_post_tick_callback(tick)
