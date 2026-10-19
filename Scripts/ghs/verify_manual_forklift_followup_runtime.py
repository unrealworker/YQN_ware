"""Owned offscreen acceptance for the manual-forklift identity follow-up.

Run in GHS_CAD_NormalWarehouse with -game -RenderOffscreen -ResX=1920
-ResY=1080 -ForceRes -windowed. Temporary actors/data exist only in this
process. No editor subsystem, asset save, native input or desktop operation.
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
assert flag('game') and flag('RenderOffscreen'), 'Run only in an owned offscreen game.'
REPORT = ROOT / 'Saved/GHS_ManualForkliftFollowup_Runtime.json'
CHANGE_REPORT = ROOT / 'Saved/GHS_ManualForkliftFollowup.json'
PROBE = ROOT / 'Saved/GHS_ManualFollowupProbe.json'
MAP_FILE = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap'
MESH = '/Game/GHSNormalWarehouse/MannedForklift/Meshes/SM_GHN_MannedForklift50k.SM_GHN_MannedForklift50k'
TYPE_TAG = 'NormalWarehouseMannedForklift'
MANUAL_RE = re.compile(r'TwinId=GHN_MannedForklift_([0-9]+)')
MAP_HASH = hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()
STARTED = time.monotonic()
result = dict(success=False, status='running', tests=[], captures=[], samples=[],
              assets_saved=False, temporary_runtime_actors_only=True, visual_review_required=True)
world = pc = pawn = widget = handle = None
stage, stage_started, stage_frames = 'discover', STARTED, 0
actors, kinds, data_by_id, original_transforms = {}, {}, {}, {}
manual, initial_states, legacy_counts = {}, {}, {}
spawned, issued_ids, original_tags = [], [], {}
selected_id, close_id, live_id = '', '', 'FORK-01'
live_state = None
pending = None
wide_center, wide_zoom = None, 0.0
resolution = None


def save():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **values):
    result['tests'].append(dict(name=name, passed=True, **values))
    unreal.log('MANUAL_FOLLOWUP_PASS ' + name)
    save()


def advance(name):
    global stage, stage_started, stage_frames
    stage, stage_started, stage_frames = name, time.monotonic(), 0


def xyz(v):
    return [float(v.x), float(v.y), float(v.z)]


def transform(actor):
    r = actor.get_actor_rotation()
    return dict(position_cm=xyz(actor.get_actor_location()), scale=xyz(actor.get_actor_scale3d()),
                rotation_deg=[float(r.pitch), float(r.yaw), float(r.roll)])


def same_transform(actual, expected):
    assert all(abs(a-b) <= .02 for a,b in zip(actual['position_cm'], expected['position_cm'])), (actual, expected)
    assert all(abs(a-b) <= .0001 for a,b in zip(actual['scale'], expected['scale'])), (actual, expected)
    assert all(abs((a-b+180)%360-180) <= .01 for a,b in zip(actual['rotation_deg'], expected['rotation_deg'])), (actual, expected)


def snapshot(data):
    names = ('forklift_id', 'load_tonnes', 'speed_kmh', 'driver_id', 'area', 'task_id', 'reason',
             'is_demo_data', 'last_update_seconds', 'last_online_seconds')
    out = {name: data.get_editor_property(name) for name in names}
    out['status'] = str(data.get_editor_property('status'))
    out['has_telemetry'] = bool(data.has_telemetry())
    return out


def identifier(actor, pattern=MANUAL_RE, prefix='FORK-', digits=2):
    tags = [str(t) for t in actor.tags]
    twins = [t for t in tags if t.startswith('TwinId=')]
    if len(twins) != 1:
        return None
    match = pattern.fullmatch(twins[0])
    return prefix + format(int(match[1]), '0' + str(digits) + 'd') if match and int(match[1]) > 0 else None


def is_manual_mesh(actor):
    if not isinstance(actor, unreal.StaticMeshActor):
        return False
    c = actor.get_component_by_class(unreal.StaticMeshComponent)
    return bool(c and c.static_mesh and c.static_mesh.get_path_name() == MESH)


def actual_manual():
    return [a for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor) if is_manual_mesh(a)]


def verify_count(expected):
    fleet = actual_manual()
    ids = [identifier(a) for a in fleet]
    assert len(fleet) == expected and None not in ids and len(set(ids)) == expected, (expected, ids)
    assert all(a.actor_has_tag(TYPE_TAG) for a in fleet)
    assert widget.get_registered_manned_forklift_count() == expected
    for a,i in zip(fleet, ids):
        data = widget.get_manned_forklift_data(i)
        assert data and data.get_owner() == a, ('HUD owner', i)
    assert widget.get_registered_truck_count() == legacy_counts['truck']
    assert widget.get_registered_stacker_count() == legacy_counts['stacker']
    assert widget.get_registered_equipment_count() == expected + sum(legacy_counts.values())
    return dict(zip(ids, fleet))


def original_stable():
    for i,a in manual.items():
        assert identifier(a) == i, ('Original ID changed', i)
        assert [str(t) for t in a.tags] == original_tags[i], ('Original identity tags changed', i)
        same_transform(transform(a), original_transforms[i])
        data = widget.get_manned_forklift_data(i)
        assert data and data == data_by_id[i] and data.get_owner() == a
        assert snapshot(data) == (live_state if i == live_id and live_state else initial_states[i]), ('Telemetry changed', i)


def set_wide():
    widget.clear_selection()
    pawn.set_desired_location(wide_center, True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-55, yaw=-90, roll=0), True)
    pawn.set_desired_zoom(wide_zoom, True)
    pawn.set_editor_property('hud_cluster_min_arm_length', 10000.0)


def focus(i):
    o,e = actors[i].get_actor_bounds(False)
    widget.clear_selection()
    pawn.set_desired_location(unreal.Vector(o.x, o.y, 0), True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-42, yaw=-135, roll=0), True)
    pawn.set_desired_zoom(1300, True)


def discover():
    global world, pc, pawn, widget, resolution, close_id, wide_center, wide_zoom
    for candidate in unreal.ObjectIterator(unreal.World):
        if '/Game/Maps/GHS_CAD_NormalWarehouse.' in candidate.get_path_name():
            candidate_pc = unreal.GameplayStatics.get_player_controller(candidate, 0)
            if candidate_pc:
                world, pc = candidate, candidate_pc
                break
    if not pc:
        return False
    widget = pc.get_editor_property('truck_hud_widget')
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    if not widget or not pawn or widget.get_registered_manned_forklift_count() < 16:
        return False
    resolution = tuple(pc.get_viewport_size())
    assert resolution == (1920, 1080), resolution
    assert widget.is_in_viewport()
    changes = json.loads(CHANGE_REPORT.read_text(encoding='utf-8-sig'))
    assert changes['success'] and changes['manual_count'] == 16
    assert len(changes['added']) == 4 and len(changes['repaired']) == 4
    baseline = json.loads(Path(changes['baseline_path']).read_text(encoding='utf-8-sig'))
    probe = json.loads(PROBE.read_text(encoding='utf-8-sig'))
    fleet = actual_manual()
    assert len(fleet) == 16
    for a in fleet:
        i = identifier(a)
        assert i and i not in manual and a.actor_has_tag(TYPE_TAG), (a.get_name(), i)
        manual[i] = actors[i] = a
        kinds[i] = 'manual'
        data_by_id[i] = widget.get_manned_forklift_data(i)
        assert data_by_id[i] and data_by_id[i].get_owner() == a
        original_transforms[i] = transform(a)
        original_tags[i] = [str(t) for t in a.tags]
        initial_states[i] = snapshot(data_by_id[i])
    assert sorted(manual) == ['FORK-%02d' % n for n in range(1, 17)]
    by_object_name = {a.get_name(): a for a in fleet}
    by_label = {}
    for row in probe['forklifts']:
        assert row['mesh'] == MESH
        a = by_object_name.get(row['path'].rsplit('.', 1)[-1])
        assert a, ('Missing original object', row['path'])
        same_transform(transform(a), baseline[row['label']]['transform'])
        by_label[row['label']] = a
    assert len(by_label) == 12, 'Expected original 8 and four user copies'
    repaired = []
    for row in changes['repaired']:
        a = by_label[row['label']]
        # The saved report describes editor repair. Runtime discovery also adds
        # its explicit ownership marker, which is expected and not a scene edit.
        runtime_tags = set(str(t) for t in a.tags)
        assert set(row['new_tags']) <= runtime_tags
        assert runtime_tags-set(row['new_tags']) <= {'GHSManualIdentityOwner='+a.get_name()}
        assert all(abs(v-w) <= .02 for v,w in zip(xyz(a.get_actor_location()), row['position_cm']))
        repaired.append(dict(label=row['label'], id=identifier(a), position_cm=xyz(a.get_actor_location())))
    assert {r['label'] for r in repaired} == {'GHN_MannedForklift_9', 'GHN_MannedForklift_8', 'GHN_MannedForklift_10', 'GHN_MannedForklift_11'}
    assert {r['id'] for r in repaired} == {'FORK-09', 'FORK-10', 'FORK-11', 'FORK-12'}
    for row in changes['added']:
        n = int(row['label'].rsplit('_', 1)[-1])
        assert 13 <= n <= 16
        a = manual['FORK-%02d' % n]
        assert all(abs(v-w) <= .02 for v,w in zip(xyz(a.get_actor_location()), row['position_cm']))
        assert abs((a.get_actor_rotation().yaw-row['yaw_deg']+180)%360-180) <= .01
    close_id = repaired[0]['id']
    record('all_12_existing_transforms_preserved_and_four_user_copies_repaired', repaired=repaired)
    record('four_additions_match_saved_change_report', additions=changes['added'])
    # The user's old stacker copies may already share IDs. This follow-up does
    # not repair that fleet: compare HUD counts with unique valid legacy IDs.
    legacy_detail = {}
    for kind,tag,pattern,prefix,digits,getter in (
        ('truck', 'IndependentDockTruck', r'TwinId=GHS_DockTruck_([0-9]+)', 'TRUCK-', 3, widget.get_truck_data),
        ('stacker', 'NormalWarehouseFloorStacker', r'TwinId=GHN_FloorStacker_([0-9]+)', 'STACKER-', 2, widget.get_stacker_data)):
        tagged = list(unreal.GameplayStatics.get_all_actors_with_tag(world, tag))
        ids = [identifier(a, re.compile(pattern), prefix, digits) for a in tagged]
        unique = sorted(set(ids) - {None})
        legacy_counts[kind] = len(unique)
        legacy_detail[kind] = dict(actual_tagged_actors=len(tagged), unique_valid_ids=len(unique),
                                   duplicate_ids=sorted(i for i in unique if ids.count(i)>1))
        for i in unique:
            data = getter(i)
            assert data and data.get_owner() in tagged
            actors[i], kinds[i] = data.get_owner(), kind
            original_transforms[i] = transform(actors[i])
    verify_count(16)
    record('16_unique_manual_forklifts_registered_and_legacy_unique_counts_preserved', legacy=legacy_detail)
    result.update(initial_ids=sorted(manual), viewport=list(resolution), map=world.get_path_name(),
                  legacy=legacy_detail, change_report=str(CHANGE_REPORT), baseline_path=changes['baseline_path'])
    bounds = [a.get_actor_bounds(False) for a in actors.values()]
    lo_x,hi_x = min(o.x-e.x for o,e in bounds), max(o.x+e.x for o,e in bounds)
    lo_y,hi_y = min(o.y-e.y for o,e in bounds), max(o.y+e.y for o,e in bounds)
    wide_center = unreal.Vector((lo_x+hi_x)/2, (lo_y+hi_y)/2, 0)
    wide_zoom = min(94000, max(18000, math.hypot(hi_x-lo_x, hi_y-lo_y)*1.4))
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    set_wide()
    return True


def geometry():
    dpi = float(unreal.WidgetLayoutLibrary.get_viewport_scale(world))
    w,h = pc.get_viewport_size()
    return w/dpi, h/dpi, min(max(dpi,.75), min(w/640,h/540))/dpi


def frame():
    global stage_frames
    stage_frames += 1
    labels = []
    for label in widget.get_visible_labels():
        ids = [str(i) for i in label.get_editor_property('equipment_ids')]
        p,s = label.get_editor_property('position'), label.get_editor_property('size')
        labels.append(dict(key=str(label.get_editor_property('key')), ids=ids, position=[p.x,p.y],
                           size=[s.x,s.y], opacity=float(label.get_editor_property('opacity'))))
    value = dict(stage=stage, elapsed=time.monotonic()-stage_started, labels=labels,
                 selected=str(widget.get_selected_equipment_id()),
                 detail=bool(widget.get_editor_property('detail_visible')),
                 detail_progress=float(widget.get_editor_property('detail_transition_progress')),
                 list_progress=float(widget.get_editor_property('cluster_transition_progress')))
    assert abs(pawn.get_actor_location().z) < .01
    if stage_frames == 1 or stage_frames % 30 == 0:
        result['samples'].append(value)
    return value


def settled(v):
    return stage_frames >= 8 and v['elapsed'] >= 1.0 and all(l['opacity'] >= .999 for l in v['labels'])


def check_labels(v, aggregate):
    w,h,scale = geometry()
    expected = set()
    for i,a in actors.items():
        if a.get_editor_property('hidden'):
            continue
        o,e = a.get_actor_bounds(False)
        p = unreal.WidgetLayoutLibrary.project_world_location_to_widget_position(pc, unreal.Vector(o.x,o.y,o.z+e.z+80), True)
        if p is not None and 8*scale <= p.x <= w-8*scale and 8*scale <= p.y <= h-8*scale:
            expected.add(i)
    actual = [i for label in v['labels'] for i in label['ids']]
    assert expected and set(actual) == expected and len(actual) == len(set(actual)), (actual, sorted(expected))
    for label in v['labels']:
        assert len({kinds[i] for i in label['ids']}) == 1, ('Mixed vehicle types', label)
        x,y = label['position']; lw,lh = label['size']
        assert x >= -.5 and y >= -.5 and x+lw <= w+.5 and y+lh <= h+.5
        if not aggregate:
            assert len(label['ids']) == 1
    return expected


def click_label(label):
    x,y = label['position']; w,h = label['size']
    assert widget.handle_pointer_click(unreal.Vector2D(x+w/2,y+h/2))


def check_panel(prefix):
    w,h,_ = geometry()
    p,s = widget.get_editor_property(prefix+'_position'), widget.get_editor_property(prefix+'_size')
    assert s.x>0 and s.y>0 and p.x>=-.5 and p.y>=-.5 and p.x+s.x<=w+.5 and p.y+s.y<=h+.5


def capture(name, value):
    global pending
    assert pending is None
    path = ROOT / ('Saved/GHS_ManualForkliftFollowup_' + name + '.png')
    pending = dict(name=name, path=path, started=time.monotonic(), requested=time.time(), frame=value)
    unreal.SystemLibrary.execute_console_command(world, 'Shot showui filename="'+path.as_posix()+'" -nosuffix', pc)


def collect_capture():
    global pending
    if not pending:
        return
    assert time.monotonic()-pending['started'] < 30, 'Screenshot timeout'
    path = pending['path']
    if not path.is_file() or path.stat().st_mtime < pending['requested'] or path.stat().st_size < 10000:
        return
    with path.open('rb') as stream:
        header = stream.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n' and tuple(struct.unpack('>II', header[16:24])) == resolution
    result['captures'].append(dict(name=pending['name'], path=str(path), frame=pending['frame'], resolution=list(resolution)))
    pending = None
    save()


def spawn_temporary(copy_tags, number):
    source = manual[live_id]
    p = source.get_actor_location()
    spawn_transform = unreal.Transform(location=unreal.Vector(p.x+600*number,p.y,p.z),
        rotation=source.get_actor_rotation(), scale=source.get_actor_scale3d())
    # UE 5.4 marks these runtime UFunctions BlueprintInternalUseOnly, so they
    # have no generated Python methods. call_method is the supported reflection
    # bridge for precisely this case; no editor spawn subsystem is involved.
    gameplay = unreal.get_default_object(unreal.GameplayStatics)
    actor = gameplay.call_method('BeginDeferredActorSpawnFromClass', args=(
        world, unreal.StaticMeshActor.static_class(), spawn_transform,
        unreal.SpawnActorCollisionHandlingMethod.ALWAYS_SPAWN, None,
        unreal.SpawnActorScaleMethod.MULTIPLY_WITH_ROOT))
    assert actor, 'Could not spawn runtime test actor'
    spawned.append(actor)
    c = actor.get_component_by_class(unreal.StaticMeshComponent)
    source_c = source.get_component_by_class(unreal.StaticMeshComponent)
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    assert c.set_static_mesh(source_c.static_mesh)
    for index in range(source_c.get_num_materials()):
        c.set_material(index, source_c.get_material(index))
    actor.tags = list(source.tags) if copy_tags else []
    actor.set_actor_enable_collision(False)
    gameplay.call_method('FinishSpawningActor', args=(actor, spawn_transform,
        unreal.SpawnActorScaleMethod.MULTIPLY_WITH_ROOT))
    assert is_manual_mesh(actor)
    assert identifier(actor) == (live_id if copy_tags else None)
    return actor


def finish(error=None):
    if error is None:
        try:
            original_stable()
            for i,a in actors.items():
                same_transform(transform(a), original_transforms[i])
            assert hashlib.sha256(MAP_FILE.read_bytes()).hexdigest() == MAP_HASH, 'Saved map was modified'
            assert len(result['captures']) >= 4
            record('saved_map_hash_and_original_vehicle_transforms_unchanged', map_sha256=MAP_HASH)
        except Exception:
            error = traceback.format_exc()
    result.update(success=error is None, status='success' if error is None else 'failed',
                  elapsed_seconds=time.monotonic()-STARTED, issued_runtime_ids=issued_ids)
    if error:
        result.update(error=error, failed_stage=stage)
    save()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('MANUAL_FOLLOWUP_' + ('FAILED '+error if error else 'SUCCESS '+str(REPORT)))
    unreal.SystemLibrary.execute_console_command(world, 'quit', pc)


def tick(delta):
    global selected_id, live_state
    try:
        assert time.monotonic()-STARTED < 180, 'Overall verification timeout'
        assert time.monotonic()-stage_started < 40, ('Stage timeout', stage)
        if stage == 'discover':
            if time.monotonic()-STARTED > 1.8 and discover():
                advance('wide')
            return
        collect_capture()
        v = frame()
        if pending:
            return
        if stage == 'wide' and settled(v):
            visible = check_labels(v, True)
            assert set(manual) <= visible, ('Manual vehicles missing in overview', sorted(set(manual)-visible))
            groups = [l for l in v['labels'] if len(l['ids'])>1 and all(i in manual for i in l['ids'])]
            assert groups, 'Expected an independent manual-forklift group'
            record('all_16_manual_vehicles_visible_in_separate_type_groups', groups=groups)
            capture('Overview', v)
            advance('choose_group')
        elif stage == 'choose_group' and settled(v):
            group = max((l for l in v['labels'] if len(l['ids'])>1 and all(i in manual for i in l['ids'])), key=lambda l:len(l['ids']))
            click_label(group)
            assert set(str(i) for i in widget.get_expanded_cluster_members()) == set(group['ids'])
            selected_id = group['ids'][0]
            advance('group_list')
        elif stage == 'group_list' and settled(v) and v['list_progress'] >= .999:
            check_panel('cluster_list')
            capture('ManualGroupList', v)
            advance('group_row')
        elif stage == 'group_row' and settled(v):
            members = [str(i) for i in widget.get_expanded_cluster_members()]
            assert widget.set_cluster_page(members.index(selected_id)//5)
            row = widget.get_member_row_position(selected_id)
            _,_,scale = geometry()
            assert row.x>=0 and widget.handle_pointer_click(unreal.Vector2D(row.x+12*scale,row.y+12*scale))
            assert str(widget.get_selected_equipment_id()) == selected_id
            advance('group_detail')
        elif stage == 'group_detail' and settled(v) and v['detail_progress'] >= .999:
            assert v['detail'] and v['selected'] == selected_id
            check_panel('detail')
            record('manual_group_real_row_click_opens_detail', selected=selected_id)
            capture('ManualGroupDetail', v)
            advance('prepare_close')
        elif stage == 'prepare_close':
            focus(close_id)
            advance('close_label')
        elif stage == 'close_label' and settled(v):
            check_labels(v, False)
            match = [l for l in v['labels'] if l['ids'] == [close_id]]
            assert len(match) == 1, ('Repaired user copy missing individual label', close_id)
            click_label(match[0])
            advance('close_detail')
        elif stage == 'close_detail' and settled(v) and v['detail_progress'] >= .999:
            assert v['detail'] and v['selected'] == close_id
            check_panel('detail')
            record('repaired_user_copy_close_label_click_opens_correct_detail', selected=close_id)
            capture('UserCopyCloseDetail', v)
            advance('spawn')
        elif stage == 'spawn':
            original_stable()
            data = data_by_id[live_id]
            assert data.set_telemetry(.65,3.2,unreal.GHSMannedForkliftStatus.RUNNING,
                'LIVE-OP','LIVE-AREA','LIVE-TASK','Runtime identity preservation check',False)
            live_state = snapshot(data)
            assert not live_state['is_demo_data'] and live_state['has_telemetry']
            spawn_temporary(False,1)
            spawn_temporary(True,2)
            advance('auto_discovery')
        elif stage == 'auto_discovery' and v['elapsed'] >= 2.2 and widget.get_registered_manned_forklift_count() == 18:
            verify_count(18)
            ids = [identifier(a) for a in spawned]
            assert len(set(ids)) == 2 and all(int(i[5:])>16 for i in ids), ids
            issued_ids.extend(ids)
            original_stable()
            record('HUD_automatically_discovers_untagged_exact_mesh_and_repairs_copied_identity', ids=ids,
                   tags=[[str(t) for t in a.tags] for a in spawned], live_telemetry=live_state)
            for a in spawned:
                a.destroy_actor()
            spawned.clear()
            advance('deleted')
        elif stage == 'deleted' and v['elapsed'] >= 2.2 and widget.get_registered_manned_forklift_count() == 16:
            verify_count(16)
            assert all(widget.get_manned_forklift_data(i) is None for i in issued_ids)
            original_stable()
            spawn_temporary(False,3)
            advance('high_water')
        elif stage == 'high_water' and v['elapsed'] >= 2.2 and widget.get_registered_manned_forklift_count() == 17:
            verify_count(17)
            new_id = identifier(spawned[0])
            assert int(new_id[5:]) > max(int(i[5:]) for i in issued_ids), (new_id,issued_ids)
            issued_ids.append(new_id)
            original_stable()
            record('deleted_ids_are_not_reused_and_original_live_data_stays_bound', ids=issued_ids)
            spawned[0].destroy_actor()
            spawned.clear()
            advance('cleanup')
        elif stage == 'cleanup' and v['elapsed'] >= 2.2 and widget.get_registered_manned_forklift_count() == 16:
            verify_count(16)
            original_stable()
            focus(live_id)
            assert widget.select_equipment_by_id(live_id)
            advance('live_detail')
        elif stage == 'live_detail' and settled(v) and v['detail_progress'] >= .999:
            assert v['selected'] == live_id and v['detail']
            check_panel('detail')
            capture('PreservedLiveTelemetry', v)
            advance('finish')
        elif stage == 'finish':
            finish()
    except Exception:
        finish(traceback.format_exc())


save()
handle = unreal.register_slate_post_tick_callback(tick)
unreal.log('MANUAL_FOLLOWUP_VERIFIER_READY ' + str(REPORT))
