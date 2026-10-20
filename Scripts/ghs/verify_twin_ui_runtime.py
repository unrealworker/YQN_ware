"""Owned offscreen game validation; never save or edit map assets."""
import json, time, traceback, struct, re
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
CLI=unreal.SystemLibrary.get_command_line()
assert re.search(r'(?:^|\s)-game(?:\s|$)',CLI,re.I) and '-RenderOffscreen' in CLI
suffix='Portrait' if '-TwinPortrait' in CLI else 'Small' if '-TwinSmall' in CLI else 'Full'
REPORT=ROOT/f'Saved/GHS_TwinUI_Runtime_{suffix}.json'
START=time.monotonic(); world=pc=pawn=widget=None
step=0; next_at=0; pending=None; handle=None
result=dict(success=False,variant=suffix,checks=[],captures=[],assets_saved=False)

def write(): REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
def record(name,**kw):
    result['checks'].append(dict(name=name,passed=True,**kw)); write()
    unreal.log('GHS_TWIN_CHECK '+name)
def report():
    raw=widget.get_editor_property('last_browser_report')
    return json.loads(raw) if raw else {}
def discover():
    global world,pc,pawn,widget
    for w in unreal.ObjectIterator(unreal.World):
        p=unreal.GameplayStatics.get_player_controller(w,0)
        if p and hasattr(p,'twin_hud_widget') and p.get_editor_property('twin_hud_widget'):
            world,pc,pawn,widget=w,p,p.get_controlled_pawn(),p.get_editor_property('twin_hud_widget'); break
    if not widget or not widget.get_editor_property('browser_ready'): return False
    assert 'ZcoolSmartFactory' in world.get_name()
    data=json.loads(widget.get_snapshot())
    assert len(data['equipment'])==106 and len(data['facilities'])==56,(len(data['equipment']),len(data['facilities']))
    ids={x['id'] for x in data['equipment']}
    assert 'AGV-34' in ids and 'AGV-32' not in ids and 'FORK-01' in ids
    assert not pc.get_editor_property('truck_hud_widget')
    result['initial_snapshot']=data
    record('native_browser_bridge_and_actual_scene_registry',equipment=106,facilities=56)
def assert_page(name):
    r=report()
    assert r.get('page')==name,(name,r)
    assert not r.get('overflow'),r
    assert not r.get('imageFailures'),r
    assert r.get('detailActionsVisible') is not False,r
    assert r.get('equipmentCount')==106 and r.get('facilityCount')==56,r
    record('page_'+name,browser=r)
def capture(name):
    global pending
    p=ROOT/f'Saved/GHS_TwinUI_{suffix}_{name}.png'
    pending=(p,time.time(),time.monotonic())
    unreal.SystemLibrary.execute_console_command(world,f'Shot showui filename="{p.as_posix()}" -nosuffix',pc)
def capture_wait():
    global pending
    p,t,mono=pending
    if not p.exists() or p.stat().st_mtime<t or p.stat().st_size<10000:
        assert time.monotonic()-mono<30,'Screenshot timeout'; return False
    data=p.read_bytes(); assert data[:8]==b'\x89PNG\r\n\x1a\n'
    wh=struct.unpack('>II',data[16:24]); result['captures'].append(dict(path=str(p),size=wh)); pending=None; write(); return True
def select():
    previous=pawn.get_actor_location(); assert widget.select_object('AGV-07',True)
    immediate=pawn.get_actor_location(); assert (immediate-previous).length()<1,'Camera teleported on focus'
    result['camera_before']=[previous.x,previous.y,previous.z]
    record('device_selection_starts_without_camera_jump')
def selected():
    r=report(); data=json.loads(widget.get_snapshot())
    assert data['selection']['id']=='AGV-07'
    assert r.get('detail',{}).get('id')=='AGV-07',r
    assert not r.get('imageFailures'),r
    assert r.get('detailActionsVisible') is not False,r
    record('selected_device_image_detail_and_bridge',browser=r)
def select_invalid():
    assert not widget.select_object('AGV-32',True)
    assert widget.get_editor_property('selected_id')=='AGV-07'
    widget.clear_selection()
    record('missing_scene_identity_rejected')
def layout():
    p,s=widget.get_panel_position(),widget.get_panel_size()
    assert s.x>=360 and s.y>=200,(p,s)
    expected=(600,900) if suffix=='Portrait' else (1366,768) if suffix=='Small' else (1920,1080)
    assert abs(p.x+s.x-expected[0])<1 and abs(p.y+s.y-expected[1])<1,('DPI scaled instead of adapting',p,s,expected)
    if suffix=='Portrait': assert p.x==0 and p.y>200
    else: assert p.x>0 and p.y==64
    assert not widget.is_scene_point(unreal.Vector2D(p.x+s.x/2,p.y+s.y/2))
    assert widget.is_scene_point(unreal.Vector2D(100,160))
    record('responsive_panel_and_input_regions',position=[p.x,p.y],size=[s.x,s.y])
def rack_select():
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor):
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh=component.get_editor_property('static_mesh')
            if mesh and mesh.get_name().startswith('SM_GHS_V2Rack_'):
                index=0
                key=f'RACK:{actor.get_name()}:{component.get_name()}:{index}'
                if widget.select_object(key,True):
                    result['rack_key']=key
                    result['rack_component']=component.get_path_name()
                    return
    raise AssertionError('No actual rack could be resolved')
def rack_click():
    data=json.loads(widget.get_snapshot())['selection']
    assert data['kind']=='rack' and data['cadId'],data
    component=unreal.find_object(None,result['rack_component'])
    transform=component.get_instance_transform(0,world_space=True)
    meta=json.loads((ROOT/'Content/GHSTwinUI/data/rack-slots.json').read_text(encoding='utf-8'))
    model=next(x for x in meta['meshes'] if x['name']==component.get_editor_property('static_mesh').get_name())
    slots=sorted(model['cargo_stacks'],key=lambda x:x['stack_top_z_m'],reverse=True)
    for slot in slots:
        point=unreal.MathLibrary.transform_location(transform,unreal.Vector(slot['pallet_center_x_m']*100,0,(slot['base_z_m']+slot['stack_top_z_m'])*50))
        screen=pc.project_world_location_to_screen(point,False)
        if screen and widget.is_scene_point(screen):
            widget.handle_scene_click(screen)
            chosen=json.loads(widget.get_snapshot()).get('selection',{})
            if chosen.get('kind')=='material':
                assert chosen.get('cadId') and chosen.get('level',0)>0 and not chosen.get('businessBound')
                record('click_actual_rack_cargo_selects_cad_instance_and_slot',selection=chosen)
                return
    raise AssertionError('Visible rack cargo did not select a material slot')
def layers():
    widget.command(json.dumps(dict(action='layers',equipment=False,racks=True,pois=False)))
    devices=json.loads(widget.get_snapshot())['equipment']
    assert devices and all(not a['visible'] for a in devices)
    widget.command(json.dumps(dict(action='layers',equipment=True,racks=True,pois=True)))
    assert any(a['visible'] for a in json.loads(widget.get_snapshot())['equipment'])
    record('runtime_layers_hide_and_restore_equipment')
def toggle_panel():
    width=600 if suffix=='Portrait' else 1366 if suffix=='Small' else 1920
    assert widget.handle_chrome_click(unreal.Vector2D(width-30,25))
def mid_transition():
    p=widget.get_panel_transition_progress()
    assert 0<p<1,('Panel changed abruptly',p)
    record('panel_collapse_has_intermediate_animation',progress=p)
def collapsed():
    assert widget.get_panel_size().x==0
    record('panel_collapses_and_restores_scene_input')
def rapid_pages():
    for p in ['inventory','devices','settings','alerts','overview','orders']: widget.navigate(p)
def reopen_same():
    assert widget.select_object('AGV-07',True)
def navigate_away(): widget.navigate('inventory')
def same_reopened():
    assert report().get('detail',{}).get('id')=='AGV-07',report()
    record('explicit_same_object_reselection_reopens_details')
def resize_portrait(): unreal.SystemLibrary.execute_console_command(world,'r.SetRes 600x900w',pc)
def check_resized():
    p,s=widget.get_panel_position(),widget.get_panel_size()
    assert abs(s.x-600)<1 and p.x==0 and abs(p.y+s.y-900)<1,(p,s)
    position=json.loads(widget.get_snapshot())['selection']['worldPosition']
    screen=pc.project_world_location_to_screen(unreal.Vector(*position),False)
    assert screen and widget.is_scene_point(screen),('Selected object hidden after resize',screen,p,s)
    assert not report().get('overflow')
    record('live_resize_preserves_selected_object_in_scene',screen=[screen.x,screen.y],browser=report())

steps=[('discover',discover,2),('layout',layout,.2),('overview',lambda:assert_page('overview'),.1),('captureOverview',lambda:capture('Overview'),.2)]
for name in ['inventory','orders','devices','alerts','trace','settings']:
    steps.extend([(name+'Navigate',lambda n=name:widget.navigate(n),.65),(name+'Check',lambda n=name:assert_page(n),.1)])
steps.extend([('select',select,3),('selected',selected,.1),('captureDevice',lambda:capture('Device'),.2),('invalid',select_invalid,.3),('layers',layers,.3),('rackSelect',rack_select,3),('rackClick',rack_click,.6),('captureMaterial',lambda:capture('Material'),.2),('overviewFinal',lambda:widget.navigate('overview'),.6)])
steps.extend([('collapse',toggle_panel,.075),('collapseMid',mid_transition,.25),('collapsed',collapsed,.1),('expand',toggle_panel,.3),('expanded',layout,.1),('rapidPages',rapid_pages,.4),('rapidResult',lambda:assert_page('orders'),.1)])
steps.extend([('sameSelect',reopen_same,.5),('navigateAway',navigate_away,.4),('sameAgain',reopen_same,.6),('sameReopened',same_reopened,.1)])
if suffix=='Full': steps.extend([('resizePortrait',resize_portrait,3),('resizeCheck',check_resized,.1),('captureResized',lambda:capture('LiveResize'),.1)])
def finish(error=None):
    result.update(success=not error,error=error,failed_step=steps[step][0] if error and step<len(steps) else None,elapsed=time.monotonic()-START); write()
    if handle: unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_TWIN_RUNTIME_'+('FAILED '+str(error) if error else 'SUCCESS'))
    unreal.SystemLibrary.execute_console_command(world,'quit',pc)
def tick(dt):
    global step,next_at
    try:
        now=time.monotonic(); assert now-START<180,'Runtime timeout'
        if pending and not capture_wait(): return
        if now<next_at:return
        if step>=len(steps):finish();return
        name,fn,delay=steps[step]
        if fn() is False:return
        step+=1;next_at=now+delay
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
