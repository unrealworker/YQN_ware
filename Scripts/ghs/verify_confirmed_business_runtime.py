"""Read actual embedded Chromium output in an owned game; never save scene assets."""
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
OUT = ROOT / 'Saved/AnnotationCleanup'
CLI = unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+f+r'(?=\s|$)', CLI, re.I) for f in ('game','RenderOffscreen','TwinDiagnostics'))
OUT.mkdir(parents=True, exist_ok=True)
MAP = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
map_hash = hashlib.sha256(MAP.read_bytes()).hexdigest()
result = dict(success=False, checks=[], captures=[], assets_saved=False)
world = pc = hud = pawn = handle = None
started = time.monotonic()
stage = 'discover'
probe_serial = 0

def write():
    (OUT/'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

def report():
    raw = hud.get_editor_property('last_browser_report') if hud else ''
    return json.loads(raw) if raw else {}

def record(name, **data):
    result['checks'].append(dict(name=name, passed=True, **data))
    write()

def wait(name, condition, timeout=30):
    global stage
    stage = name
    deadline = time.monotonic()+timeout
    while not condition():
        assert time.monotonic()<deadline, 'Timed out: '+name
        yield

def pause(seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        yield

def discover():
    global world,pc,hud,pawn
    for w in unreal.ObjectIterator(unreal.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):
            continue
        controller=unreal.GameplayStatics.get_player_controller(w,0)
        widget=getattr(controller,'twin_hud_widget',None) if controller else None
        if widget and widget.browser_ready:
            world,pc,hud,pawn=w,controller,widget,controller.get_controlled_pawn()
            return bool(report().get('business'))
    return False

def annotation_probe():
    """Read the current CEF DOM, including accessible collapsed explanations."""
    global probe_serial
    probe_serial += 1
    token = probe_serial
    seed = report()
    script = """(()=>{
const r=%s,page=document.getElementById('page'),main=document.getElementById('main');
const motion=window.TwinMotion,state=window.twinState;
r.action='report';r.businessAnnotationQAToken=%d;
r.page=state.page==='scene'?'settings':state.page;r.detail=state.detail;
r.business=Object.assign({},r.business,{visibleText:String(motion?motion.text(page):(page.innerText||page.textContent||'')).slice(0,6000),
 inventorySampleRows:page.querySelectorAll('[data-inventory-sample]').length,
 ledgerSampleRows:page.querySelectorAll('[data-ledger-sample]').length,
 unverifiedSections:page.querySelectorAll('[data-unverified]').length});
r.businessAnnotations={busy:main.getAttribute('aria-busy')==='true',
 explanations:[...page.querySelectorAll('[data-info]')].map(n=>({label:n.getAttribute('aria-label'),copy:n.dataset.info})),
 numbers:[...page.querySelectorAll('[data-motion-value]')].map(n=>({target:n.dataset.motionValue,actual:n.textContent})),
 unverifiedKeys:[...page.querySelectorAll('[data-unverified]')].map(n=>n.dataset.unverified)};
window.ue.twin.command(JSON.stringify(r));
})()""" % (json.dumps(seed,ensure_ascii=True),token)
    deadline=time.monotonic()+10
    next_send=0
    while True:
        current=report()
        if current.get('businessAnnotationQAToken')==token:
            return current
        now=time.monotonic()
        assert now<deadline,'Fresh CEF business annotation probe timed out'
        if now>=next_send:
            hud.evaluate_diagnostics(script)
            next_send=now+.1
        yield


def settled_business_view(page, detail_id=None):
    """Wait on actual rendered number values, not a guessed animation delay."""
    deadline=time.monotonic()+20
    while True:
        current=report()
        if current.get('page')==page and current.get('business') and current.get('transition',{}).get('phase')=='idle':
            current=yield from annotation_probe()
            dom=current['businessAnnotations']
            detail=current.get('detail') or {}
            if (current['page']==page and (detail.get('id')==detail_id if detail_id else not detail)
                    and not dom['busy'] and all(n['actual']==n['target'] for n in dom['numbers'])):
                return current
        assert time.monotonic()<deadline,'Business view did not settle: '+page
        yield from pause(.05)


def explanation(r, label):
    matches=[item['copy'] for item in r['businessAnnotations']['explanations'] if item['label']==label]
    assert len(matches)==1,(label,matches)
    return matches[0]


def validate(page, r):
    assert r['page']==page, r
    assert not r['overflow'], r
    assert not r['imageFailures'], r
    b=r['business']
    assert b['sourceMode']=='verified-extract' and b['live'] is False
    assert b['warehouseCode']=='GHS_CA_US'
    text=b['visibleText']
    data_help=explanation(r,'数据说明')
    assert '数据非实时刷新' in data_help,data_help
    if page in ('overview','inventory'):
        assert '数量单位待确认' in data_help,data_help
        assert '单位待确认' not in text,text
    if page=='devices':
        assert '管理状态不代表实时在线状态' in data_help,data_help
    assert not re.search(r'GHS_CA_US|仓库\s*108|ETL|UTC\+08|核验日期|静态数据|静态核验|业务快照|查询核验|当前快照',text),text
    assert {'overview':'库存、设备与作业概况','inventory':'库存数量与货位分布','devices':'叉车台账与设备状态'}[page] in text
    if page in ('overview','inventory'):
        for value in ('337,783','336,006','156','14,373'):
            assert value in text, (value,text)
        assert all(value in text for value in ('1,920','416','64')),text
        if page=='overview':
            capacity_help=explanation(r,'库容占用说明')
            assert all(value in capacity_help for value in ('原设计示例','2,400','1,920','数据未核验')),capacity_help
            assert 'capacity' in r['businessAnnotations']['unverifiedKeys']
            assert '80.0%' in text,text
        else:
            assert '2,400' in text,text
            assert 'inventory-design' in r['businessAnnotations']['unverifiedKeys']
        assert '数据未核验' in text and b['unverifiedSections']>0
    if page=='inventory':
        assert b['inventorySampleRows']==5
        for value in ('8551268','7111566','8556512','8703069','10274458','-1','待确认'):
            assert value in text, (value,text)
        assert '数据未核验' in text and b['unverifiedSections']>0
    if page=='devices':
        assert b['deviceView']=='ledger' and b['ledgerSampleRows']==5
        for value in ('82','62','20','0','SITDOWN-GHS-L-IN-S5','暂无'):
            assert value in text,(value,text)
        assert '22:27' not in text
        assert not r['detail']
    record('cef_'+page+'_'+str(pc.get_viewport_size()[0]), browser=r)

def capture(name):
    path=OUT/(name+'.png')
    old=path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot showui filename="'+path.as_posix()+'" -nosuffix',pc)
    yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=old)
    result['captures'].append(str(path))
    write()

def run():
    yield from wait('discover_cef_business',discover,100)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    yield from wait('initial_camera',lambda:not pawn.is_pose_transition_active())
    # CEF's report can precede the first browser texture reaching the GPU viewport.
    yield from pause(2)
    assert pc.warehouse_roof.is_roof_closed()
    scene=json.loads(hud.get_snapshot())
    scene_ids=[x['id'] for x in scene['equipment']]
    assert len(scene_ids)==106 and not any(str(i) in scene_ids for i in range(2574,2579))
    record('scene_registry_kept_separate',equipment=len(scene_ids),facilities=len(scene['facilities']))
    for width,height in ((2560,1600),(390,844)):
        if tuple(pc.get_viewport_size())!=(width,height):
            unreal.SystemLibrary.execute_console_command(world,f'r.SetRes {width}x{height}w',pc)
            yield from wait('resize',lambda:tuple(pc.get_viewport_size())==(width,height))
            yield from pause(1)
        for page in ('overview','inventory','devices'):
            hud.navigate(page)
            yield from wait('navigate_'+page,lambda:report().get('page')==page and report().get('transition',{}).get('phase')=='idle')
            current=yield from settled_business_view(page)
            validate(page,current)
            assert pc.warehouse_roof.is_roof_closed(), 'Business view changed the roof'
            yield from capture(str(width)+'_'+page)
    # Existing scene picking still opens the actual model, independently of ledger IDs.
    assert hud.select_object('FORK-07',False)
    yield from wait('scene_pick',lambda:(report().get('detail') or {}).get('id')=='FORK-07')
    assert hud.is_interior_available()
    yield from wait('scene_detail_ready',lambda:report().get('transition',{}).get('phase')=='idle')
    r=yield from settled_business_view('devices',detail_id='FORK-07')
    text=r['business']['visibleText']
    assert all(value in text for value in ('FORK-07','数据未核验','场景参数 · 尚未核验')),r
    assert 'scene-device' in r['businessAnnotations']['unverifiedKeys'],r
    assert '场景状态及参数尚未与设备平台核验' in explanation(r,'场景参数 · 尚未核验说明'),r
    assert not r['overflow'],r
    record('scene_pick_keeps_identity_and_roof_interaction',browser=report())
    hud.command('{"action":"overview"}')
    yield from wait('roof_restored',lambda:pc.warehouse_roof.is_roof_closed())
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==map_hash
    record('map_preserved',sha256=map_hash)

def finish(error=None):
    result['success']=error is None
    result['elapsed_seconds']=time.monotonic()-started
    if error:result.update(error=error,stage=stage,failure_browser=report())
    write()
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_CONFIRMED_BUSINESS_RUNTIME '+json.dumps(result,ensure_ascii=False))
    if world:unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)

steps=run()
def tick(delta):
    try:
        assert time.monotonic()-started<200,'Acceptance timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
handle=unreal.register_slate_post_tick_callback(tick)
