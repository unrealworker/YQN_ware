"""Session-only editor bridge for local, explicitly queued GHS scripts."""
import json
import time
import traceback
from pathlib import Path
import unreal

bridge_root=Path(r'D:\UEPro\Test')
bridge_request=bridge_root/'Saved/GHS_LiveRequest.json'
bridge_status=bridge_root/'Saved/GHS_LiveStatus.json'
if globals().get('bridge_handle') is not None:
    unreal.unregister_slate_post_tick_callback(bridge_handle)
bridge_last=None
bridge_last_poll=0
bridge_busy=False
bridge_namespaces={}

def bridge_tick(delta):
    global bridge_last,bridge_last_poll,bridge_busy
    if bridge_busy or time.monotonic()-bridge_last_poll<1:return
    bridge_last_poll=time.monotonic()
    if not bridge_request.is_file():return
    try:
        request=json.loads(bridge_request.read_text(encoding='utf-8'))
        if request['id']==bridge_last:return
        bridge_last=request['id']
        path=(bridge_root/'Scripts/ghs'/request['script']).resolve()
        assert path.parent==bridge_root/'Scripts/ghs' and path.suffix=='.py'
        bridge_busy=True
        bridge_status.write_text(json.dumps(dict(id=bridge_last,status='running',script=str(path))))
        namespace=bridge_namespaces.setdefault(str(path),dict(__name__='__main__',__file__=str(path)))
        exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),namespace)
        bridge_status.write_text(json.dumps(dict(id=bridge_last,status='executed',script=str(path))))
    except Exception:
        bridge_status.write_text(json.dumps(dict(id=bridge_last,status='failed',error=traceback.format_exc())))
        unreal.log_error('GHS_LIVE_SCRIPT_ERROR '+traceback.format_exc())
    finally:bridge_busy=False

bridge_handle=unreal.register_slate_post_tick_callback(bridge_tick)
unreal.log('GHS_LOCAL_DISPATCHER_READY')
