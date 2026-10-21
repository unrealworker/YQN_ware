"""Verify cache work budgets and hidden-panel synchronization in an owned UE game."""
import json
import re
import time
import traceback
from pathlib import Path
import unreal

ROOT = Path(r'D:/UEPro/Test')
CLI = unreal.SystemLibrary.get_command_line()
assert re.search(r'(?:^|\s)-game(?:\s|$)', CLI, re.I)
assert '-RenderOffscreen' in CLI and '-TwinDiagnostics' in CLI
REPORT = ROOT/'Saved/PerformanceP0P1/runtime_cache_acceptance.json'
START = time.monotonic()
step = 0
next_at = 0
handle = None
world = widget = None
before = None
result = dict(success=False, checks=[], assets_saved=False)


def write():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **values):
    result['checks'].append(dict(name=name, passed=True, **values))
    write()


def perf():
    return json.loads(widget.get_poi_report())['performance']


def browser():
    return json.loads(widget.get_editor_property('last_browser_report'))


def finish(error=None):
    result.update(success=error is None, error=error, elapsed_seconds=time.monotonic()-START)
    write()
    unreal.unregister_slate_post_tick_callback(handle)
    if world:
        unreal.SystemLibrary.execute_console_command(world, 'quit')


def tick(delta):
    global step, next_at, world, widget, before
    try:
        now = time.monotonic()
        assert now-START < 80, 'Runtime cache acceptance timed out'
        if now < next_at:
            return
        if step == 0:
            for candidate in unreal.ObjectIterator(unreal.World):
                pc = unreal.GameplayStatics.get_player_controller(candidate, 0)
                if pc and hasattr(pc, 'twin_hud_widget') and pc.get_editor_property('twin_hud_widget'):
                    world = candidate
                    widget = pc.get_editor_property('twin_hud_widget')
                    break
            if not widget or not widget.get_editor_property('browser_ready') or not widget.get_editor_property('last_browser_report'):
                return
            assert 'ZcoolSmartFactory' in world.get_name()
            next_at = now+4
        elif step == 1:
            before = perf()
            next_at = now+4
        elif step == 2:
            after = perf()
            frames = after['projectionFrames']-before['projectionFrames']
            candidates = after['candidateBuilds']-before['candidateBuilds']
            assert frames > 0 and candidates <= 42, (before, after)
            assert frames > candidates*2, (before, after)
            assert after['worldScans'] == before['worldScans'], (before, after)
            assert after['snapshotSerializations'] == before['snapshotSerializations'], (before, after)
            record('steady_scene_avoids_world_rescan_and_snapshot_serialization', before=before, after=after)
            assert widget.select_object('AGV-07', False)
            next_at = now+1
        elif step == 3:
            assert browser()['detail']['id'] == 'AGV-07'
            assert widget.handle_chrome_click(unreal.Vector2D(1890,25))
            next_at = now+1
        elif step == 4:
            before = perf()
            assert not before['browserActive']
            widget.clear_selection()
            next_at = now+3
        elif step == 5:
            after = perf()
            assert not after['browserActive']
            assert after['snapshotSerializations'] == before['snapshotSerializations'], (before, after)
            record('fully_hidden_panel_does_not_serialize_even_when_selection_clears', before=before, after=after)
            assert widget.select_object('AGV-08', False)
            next_at = now+1
        elif step == 6:
            after = perf()
            assert after['browserActive']
            assert browser()['detail']['id'] == 'AGV-08', browser()
            assert after['snapshotSerializations'] == before['snapshotSerializations']+1, (before, after)
            record('hidden_new_selection_resumes_with_one_fresh_snapshot', report=browser(), performance=after)
            widget.command('{"action":"overview"}')
            next_at = now+1.5
        elif step == 7:
            assert not widget.get_editor_property('selected_id')
            assert browser()['detail'] is None, browser()
            record('overview_clears_native_and_browser_selection')
            finish()
            return
        step += 1
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
