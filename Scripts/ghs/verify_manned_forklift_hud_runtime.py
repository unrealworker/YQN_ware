"""Owned -game -RenderOffscreen acceptance for the three warehouse HUD types.

Use -ResX=1920 -ResY=1080 -ForceRes -windowed. Optional -MannedHUDNarrow
uses 360x800. Never saves assets; screenshots include real HUD hit testing.
"""
import hashlib
import json
import math
import re
import struct
import time
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:/UEPro/Test')
COMMAND = unreal.SystemLibrary.get_command_line()
flag = lambda name: bool(re.search(r'(?:^|\s)-' + re.escape(name) + r'(?=\s|$)', COMMAND, re.I))
assert flag('game') and flag('RenderOffscreen'), 'Requires an owned offscreen game; never run in the live editor.'
SUFFIX, RESOLUTION = ('Narrow', (360, 800)) if flag('MannedHUDNarrow') else ('Full', (1920, 1080))
REPORT = ROOT / ('Saved/GHS_MannedForkliftHUD_Runtime_' + SUFFIX + '.json')
MAP_FILE = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap'
MAP_HASH = hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()
STARTED = time.monotonic()
result = dict(success=False, status='running', variant=SUFFIX, tests=[], samples=[], captures=[],
              assets_saved=False, scene_actor_transform_changes=False, visual_review_required=True)
world = pc = pawn = widget = arm = handle = None
actors, kinds, components, original_transforms = {}, {}, {}, {}
initial_data, expected_counts = {}, {}
stage, stage_started, frames = 'discover', STARTED, []
pending = None
captured = set()
status_examples, status_index = [], 0
selected_id = ''
wide_center = None
wide_zoom = 0
live_snapshot = None
group_members = []
regression_ids, regression_index = [], 0


def save():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **data):
    result['tests'].append(dict(name=name, passed=True, **data))
    unreal.log('MANNED_HUD_PASS ' + name)
    save()


def advance(name):
    global stage, stage_started, frames
    stage, stage_started, frames = name, time.monotonic(), []


def vector(v):
    return [float(v.x), float(v.y), float(v.z)]


def transform(actor):
    r = actor.get_actor_rotation()
    return vector(actor.get_actor_location()) + [r.pitch, r.yaw, r.roll] + vector(actor.get_actor_scale3d())


def snapshot(data):
    return dict(id=str(data.get_editor_property('forklift_id')),
                load=float(data.get_editor_property('load_tonnes')),
                speed=float(data.get_editor_property('speed_kmh')),
                driver=str(data.get_editor_property('driver_id')), area=str(data.get_editor_property('area')),
                task=str(data.get_editor_property('task_id')), reason=str(data.get_editor_property('reason')),
                status=str(data.get_editor_property('status')), demo=bool(data.get_editor_property('is_demo_data')),
                updated=float(data.get_editor_property('last_update_seconds')),
                online=float(data.get_editor_property('last_online_seconds')), has_telemetry=bool(data.has_telemetry()))


def set_wide():
    pawn.set_desired_location(wide_center, True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-55, yaw=-90, roll=0), True)
    pawn.set_desired_zoom(wide_zoom, True)
    pawn.set_editor_property('hud_cluster_min_arm_length', 10000.0)


def focus(identifier):
    o, e = actors[identifier].get_actor_bounds(False)
    pawn.set_desired_location(unreal.Vector(o.x, o.y, 0), True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-42, yaw=-135, roll=0), True)
    pawn.set_desired_zoom(2600 if kinds[identifier] == 'truck' else 1300, True)
    pawn.set_editor_property('hud_cluster_min_arm_length', 10000.0)
    widget.clear_selection()


def discover():
    global world, pc, pawn, widget, arm, wide_center, wide_zoom, status_examples, regression_ids
    for candidate in unreal.ObjectIterator(unreal.World):
        if '/Game/Maps/GHS_CAD_NormalWarehouse.' not in candidate.get_path_name():
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller:
            world, pc = candidate, controller
            break
    if not pc:
        return False
    widget = pc.get_editor_property('truck_hud_widget')
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    if not widget or not pawn:
        return False
    assert tuple(pc.get_viewport_size()) == RESOLUTION
    assert widget.is_in_viewport()
    for api in ('get_registered_manned_forklift_count', 'get_manned_forklift_data', 'select_equipment_by_id'):
        assert callable(getattr(widget, api, None)), 'Missing compiled API: ' + api
    arm = pawn.get_component_by_class(unreal.SpringArmComponent)
    assert arm
    categories = (
        ('truck', 'IndependentDockTruck', r'TwinId=GHS_DockTruck_([0-9]+)', 'TRUCK-', 3, widget.get_truck_data, widget.get_registered_truck_count),
        ('stacker', 'NormalWarehouseFloorStacker', r'TwinId=GHN_FloorStacker_([0-9]+)', 'STACKER-', 2, widget.get_stacker_data, widget.get_registered_stacker_count),
        ('manual', 'NormalWarehouseMannedForklift', r'TwinId=GHN_MannedForklift_([0-9]+)', 'FORK-', 2, widget.get_manned_forklift_data, widget.get_registered_manned_forklift_count))
    for kind, tag, pattern, prefix, digits, getter, counter in categories:
        tagged = list(unreal.GameplayStatics.get_all_actors_with_tag(world, tag))
        assert tagged, 'No actual actors for ' + kind
        expected_counts[kind] = len(tagged)
        for actor in tagged:
            numbers = [m.group(1) for t in actor.tags if (m := re.fullmatch(pattern, str(t)))]
            assert len(numbers) == 1, (actor.get_name(), [str(t) for t in actor.tags])
            identifier = prefix + format(int(numbers[0]), '0' + str(digits) + 'd')
            assert identifier not in actors, identifier
            data = getter(identifier)
            assert data and data.get_owner() == actor, ('HUD identity owner mismatch', identifier)
            actors[identifier], kinds[identifier], components[identifier] = actor, kind, data
            original_transforms[identifier] = transform(actor)
        assert counter() == len(tagged), (kind, counter(), len(tagged))
    assert expected_counts['manual'] == 8, 'Approved import must contain eight manual forklifts'
    assert widget.get_registered_equipment_count() == len(actors)
    result.update(counts=expected_counts, ids=sorted(actors), viewport=list(RESOLUTION), map=world.get_path_name())
    record('registered_counts_match_actual_tagged_map_actors', **expected_counts)
    manual_ids = sorted(i for i in actors if kinds[i] == 'manual')
    assert manual_ids == ['FORK-' + format(i, '02d') for i in range(1, 9)]
    for identifier in manual_ids:
        state = snapshot(components[identifier])
        initial_data[identifier] = state
        assert state['demo']
        assert not components[identifier].apply_demo_state(4)
        assert snapshot(components[identifier]) == state
    for name in ('RUNNING', 'IDLE', 'WARNING', 'FAULT', 'OFFLINE'):
        ids = [i for i in manual_ids if components[i].get_editor_property('status') == getattr(unreal.GHSMannedForkliftStatus, name)]
        assert ids, ('Missing manual sample state', name)
        status_examples.append((name, ids[0]))
        state = initial_data[ids[0]]
        if name in ('FAULT', 'OFFLINE'):
            assert state['load'] == state['speed'] == -1 and not state['has_telemetry']
        if name == 'OFFLINE':
            assert state['driver'] == state['area'] == state['task'] == '' and state['online'] == -1
    record('five_demo_states_explicit_and_unknown_data_cleared', data=initial_data)
    assert widget.get_truck_data('FORK-01') is None
    assert widget.get_stacker_data('FORK-01') is None
    assert widget.get_manned_forklift_data('STACKER-01') is None
    assert not widget.select_equipment_by_id('FORK-NOT-REAL')
    record('identity_namespaces_do_not_alias_old_vehicle_types')
    regression_ids = [next(i for i in sorted(actors) if kinds[i] == kind) for kind in ('truck', 'stacker')]
    bounds = [a.get_actor_bounds(False) for a in actors.values()]
    min_x, max_x = min(o.x-e.x for o,e in bounds), max(o.x+e.x for o,e in bounds)
    min_y, max_y = min(o.y-e.y for o,e in bounds), max(o.y+e.y for o,e in bounds)
    wide_center = unreal.Vector((min_x+max_x)/2, (min_y+max_y)/2, 0)
    wide_zoom = min(94000, max(18000, math.hypot(max_x-min_x, max_y-min_y)*1.4))
    widget.clear_selection()
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    set_wide()
    return True


def view_geometry():
    dpi = float(unreal.WidgetLayoutLibrary.get_viewport_scale(world))
    width, height = pc.get_viewport_size()
    f32 = lambda x: struct.unpack('f', struct.pack('f', x))[0]
    scale = min(max(dpi, .75), min(width/640, height/540))/dpi
    return f32(width/dpi), f32(height/dpi), scale


def projected_cells():
    width, height, scale = view_geometry()
    cells = {}
    for identifier, actor in actors.items():
        if actor.get_editor_property('hidden'):
            continue
        o,e = actor.get_actor_bounds(False)
        p = unreal.WidgetLayoutLibrary.project_world_location_to_widget_position(pc, unreal.Vector(o.x,o.y,o.z+e.z+80), True)
        if p is not None and 8*scale <= p.x <= width-8*scale and 8*scale <= p.y <= height-8*scale:
            cell = min(1,max(0,math.floor(p.y/height*2)))*2 + min(1,max(0,math.floor(p.x/width*2)))
            cells.setdefault((kinds[identifier],cell), []).append(identifier)
    return {key:sorted(ids) for key,ids in cells.items()}


def frame(delta):
    labels = []
    for item in widget.get_visible_labels():
        ids = [str(i) for i in item.get_editor_property('equipment_ids')]
        p,s = item.get_editor_property('position'), item.get_editor_property('size')
        assert ids == [str(i) for i in item.get_editor_property('truck_ids')]
        assert ids and set(ids) <= actors.keys()
        assert len({kinds[i] for i in ids}) == 1, ('Cross-type mixed group', ids)
        labels.append(dict(key=str(item.get_editor_property('key')), ids=ids,
                           position=[p.x,p.y], size=[s.x,s.y], opacity=float(item.get_editor_property('opacity'))))
    value = dict(stage=stage, elapsed=time.monotonic()-stage_started, delta=float(delta), labels=labels,
                 selected=str(widget.get_selected_equipment_id()), detail=bool(widget.get_editor_property('detail_visible')),
                 detail_progress=float(widget.get_editor_property('detail_transition_progress')),
                 list_progress=float(widget.get_editor_property('cluster_transition_progress')))
    assert abs(pawn.get_actor_location().z) < .01
    frames.append(value)
    result['samples'].append(value)
    return value


def settled(value):
    return len(frames)>=8 and value['elapsed']>=.8 and all(l['opacity']>=.999 for l in value['labels'])


def conserve(value, aggregate, name):
    cells = projected_cells()
    expected = sorted(i for ids in cells.values() for i in ids)
    actual = [i for label in value['labels'] for i in label['ids']]
    assert expected and sorted(actual)==expected and len(actual)==len(set(actual)), (name,actual,expected)
    assert len(value['labels']) == (len(cells) if aggregate else len(expected)), (name,len(value['labels']),len(cells),len(expected))
    width,height,scale = view_geometry()
    count_by_type = dict(truck=0,stacker=0,manual=0)
    for label in value['labels']:
        x,y = label['position']; w,h = label['size']
        assert x>=-.5 and y>=-.5 and x+w<=width+.5 and y+h<=height+.5
        kind = kinds[label['ids'][0]]
        count_by_type[kind] += 1
        if aggregate:
            expected_group = next(ids for (t,c),ids in cells.items() if t==kind and label['ids'][0] in ids)
            assert sorted(label['ids']) == expected_group
        else:
            assert len(label['ids']) == 1
    if aggregate:
        assert len(value['labels'])<=12 and all(n<=4 for n in count_by_type.values())
    record(name, visible_equipment=len(actual), labels=len(value['labels']), groups_per_type=count_by_type)


def click_label(label):
    x,y = label['position']; w,h = label['size']
    assert widget.handle_pointer_click(unreal.Vector2D(x+w/2,y+h/2))


def popup_bounds(prefix):
    width,height,_ = view_geometry()
    p = widget.get_editor_property(prefix+'_position'); s = widget.get_editor_property(prefix+'_size')
    assert s.x>0 and s.y>0 and p.x>=-.5 and p.y>=-.5 and p.x+s.x<=width+.5 and p.y+s.y<=height+.5


def capture(name, value):
    global pending
    assert pending is None and name not in captured
    path = ROOT / ('Saved/GHS_MannedForkliftHUD_' + name + '_' + SUFFIX + '.png')
    pending = dict(name=name,path=path,requested=time.time(),started=time.monotonic(),frame=value)
    captured.add(name)
    unreal.SystemLibrary.execute_console_command(world,'Shot showui filename="'+path.as_posix()+'" -nosuffix',pc)


def collect_capture():
    global pending
    if pending is None:
        return
    assert time.monotonic()-pending['started']<30, 'Screenshot timeout'
    path=pending['path']
    if not path.is_file() or path.stat().st_mtime<pending['requested'] or path.stat().st_size<10000:
        return
    with path.open('rb') as stream:
        header=stream.read(24)
    assert header[:8]==b'\x89PNG\r\n\x1a\n'
    resolution=list(struct.unpack('>II',header[16:24]))
    assert tuple(resolution)==RESOLUTION
    result['captures'].append(dict(name=pending['name'],path=str(path),resolution=resolution,frame=pending['frame']))
    pending=None


def start_status():
    global selected_id
    selected_id=status_examples[status_index][1]
    focus(selected_id)
    advance('status_label')


def finish(error=None):
    if error is None:
        try:
            assert all(transform(a)==original_transforms[i] for i,a in actors.items()), 'Equipment transform changed'
            assert hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()==MAP_HASH, 'Saved map changed'
            assert len(result['captures'])>=10
            record('saved_map_and_equipment_transforms_unchanged', map_sha256=MAP_HASH)
        except Exception:
            error=traceback.format_exc()
    result.update(success=error is None,status='success' if error is None else 'failed',elapsed_seconds=time.monotonic()-STARTED)
    if error:
        result.update(error=error,failed_stage=stage)
    save()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('MANNED_HUD_'+('FAILED '+error if error else 'SUCCESS '+str(REPORT)))
    unreal.SystemLibrary.execute_console_command(world,'quit',pc)


def tick(delta):
    global selected_id, group_members, status_index, regression_index, live_snapshot
    try:
        assert time.monotonic()-STARTED<240, 'Overall verification timeout'
        assert time.monotonic()-stage_started<45, ('Stage timeout',stage)
        if stage=='discover':
            if time.monotonic()-STARTED>1.5 and discover():
                advance('wide')
            return
        collect_capture()
        value=frame(delta)
        if pending:
            return
        if stage=='wide' and settled(value):
            conserve(value,True,'three_types_aggregate_only_by_own_type_and_screen_cell')
            assert {kinds[i] for l in value['labels'] for i in l['ids']}=={'truck','stacker','manual'}
            capture('WideDistribution',value)
            advance('choose_group')
        elif stage=='choose_group' and settled(value):
            groups=[l for l in value['labels'] if len(l['ids'])>1 and kinds[l['ids'][0]]=='manual']
            assert groups, 'Expected a manual-only aggregate in overview'
            target=max(groups,key=lambda l:len(l['ids']))
            click_label(target)
            group_members=[str(i) for i in widget.get_expanded_cluster_members()]
            assert set(group_members)==set(target['ids']) and not value['selected']
            selected_id=group_members[0]
            advance('group_list')
        elif stage=='group_list' and value['list_progress']>=.999:
            popup_bounds('cluster_list')
            capture('ManualMemberList',value)
            advance('group_choose_member')
        elif stage=='group_choose_member' and settled(value):
            assert widget.set_cluster_page(group_members.index(selected_id)//5)
            row=widget.get_member_row_position(selected_id)
            assert row.x>=0
            _,_,scale=view_geometry()
            assert widget.handle_pointer_click(unreal.Vector2D(row.x+12*scale,row.y+12*scale))
            assert str(widget.get_selected_equipment_id())==selected_id
            record('manual_group_click_lists_own_members_and_real_row_click_selects_detail',members=group_members,selected=selected_id)
            advance('group_detail')
        elif stage=='group_detail' and value['detail_progress']>=.999:
            popup_bounds('detail')
            capture('ManualGroupDetail',value)
            advance('prepare_status')
        elif stage=='prepare_status':
            start_status()
        elif stage=='status_label' and settled(value):
            conserve(value,False,'near_'+status_examples[status_index][0].lower()+'_individual_labels_match_projected_vehicles')
            matching=[l for l in value['labels'] if l['ids']==[selected_id]]
            assert len(matching)==1, (selected_id,value)
            if status_index==0:
                capture('CloseModelProportion',value)
                advance('status_click')
            else:
                click_label(matching[0]); advance('status_detail')
        elif stage=='status_click' and settled(value):
            click_label(next(l for l in value['labels'] if l['ids']==[selected_id]))
            advance('status_detail')
        elif stage=='status_detail' and value['detail_progress']>=.999:
            assert value['selected']==selected_id and value['detail']
            popup_bounds('detail')
            name=status_examples[status_index][0]
            record('manual_'+name.lower()+'_click_detail_and_state',id=selected_id,data=snapshot(components[selected_id]))
            capture('Manual'+name.title(),value)
            advance('next_status')
        elif stage=='next_status':
            status_index+=1
            if status_index<len(status_examples):
                start_status()
            else:
                focus(regression_ids[regression_index]); advance('legacy_label')
        elif stage=='legacy_label' and settled(value):
            identifier=regression_ids[regression_index]
            matching=[l for l in value['labels'] if l['ids']==[identifier]]
            assert len(matching)==1
            click_label(matching[0]); selected_id=identifier
            advance('legacy_detail')
        elif stage=='legacy_detail' and value['detail_progress']>=.999:
            assert value['selected']==selected_id
            popup_bounds('detail')
            if kinds[selected_id]=='truck':
                assert str(widget.get_selected_truck_id())==selected_id
            else:
                assert str(widget.get_selected_truck_id())==''
            record('legacy_'+kinds[selected_id]+'_label_click_detail_remains_compatible',id=selected_id)
            capture('Legacy'+kinds[selected_id].title(),value)
            advance('next_legacy')
        elif stage=='next_legacy':
            regression_index+=1
            if regression_index<len(regression_ids):
                focus(regression_ids[regression_index]); advance('legacy_label')
            else:
                selected_id='FORK-01'; data=components[selected_id]
                assert data.set_telemetry(.65,3.2,unreal.GHSMannedForkliftStatus.RUNNING,'LIVE-OP','LIVE-AREA','LIVE-TASK','Real integration verification',False)
                live_snapshot=snapshot(data)
                assert not live_snapshot['demo'] and live_snapshot['has_telemetry']
                for load,speed in ((-2,3),(.5,-1),(float('inf'),3),(.5,float('inf'))):
                    assert not data.set_telemetry(load,speed,unreal.GHSMannedForkliftStatus.WARNING,'BAD','BAD','BAD','BAD',True)
                    assert snapshot(data)==live_snapshot
                assert not data.apply_demo_state(4) and snapshot(data)==live_snapshot
                focus(selected_id); widget.select_equipment_by_id(selected_id)
                advance('rediscovery')
        elif stage=='rediscovery' and value['elapsed']>=1.6 and value['detail_progress']>=.999:
            assert snapshot(widget.get_manned_forklift_data(selected_id))==live_snapshot
            assert widget.get_registered_equipment_count()==len(actors)
            record('accepted_live_data_survives_periodic_rediscovery_and_invalid_updates',data=live_snapshot)
            capture('LiveTelemetry',value)
            advance('disconnect')
        elif stage=='disconnect':
            data=components[selected_id]
            assert data.set_telemetry(-1,-1,unreal.GHSMannedForkliftStatus.OFFLINE,'STALE','STALE','STALE','Disconnected by integration verification',False)
            offline=snapshot(data)
            assert offline['load']==offline['speed']==-1 and offline['driver']==offline['area']==offline['task']==''
            assert not offline['demo'] and not offline['has_telemetry'] and offline['online']==live_snapshot['online']
            record('real_offline_clears_stale_metrics_person_area_task_and_retains_actual_last_online',data=offline)
            advance('offline_live')
        elif stage=='offline_live' and settled(value):
            capture('LiveOfflineCleared',value)
            advance('prepare_split')
        elif stage=='prepare_split':
            widget.clear_selection(); set_wide()
            pawn.set_editor_property('hud_cluster_min_arm_length',wide_zoom+1000)
            advance('split')
        elif stage=='split' and settled(value):
            conserve(value,False,'below_threshold_all_visible_equipment_split_individually')
            pawn.set_editor_property('hud_cluster_min_arm_length',10000.0)
            advance('merge')
        elif stage=='merge' and settled(value):
            conserve(value,True,'return_to_overview_restores_three_independent_type_groups')
            capture('FinalOverview',value)
            advance('finish')
        elif stage=='finish':
            finish()
    except Exception:
        finish(traceback.format_exc())


save()
handle=unreal.register_slate_post_tick_callback(tick)
unreal.log('MANNED_HUD_VERIFIER_READY '+SUFFIX)
