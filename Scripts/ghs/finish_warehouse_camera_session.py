"""Remove only this task's temporary runtime observer; do not touch assets."""
import __main__
import json
from pathlib import Path
import unreal

callback = getattr(__main__, 'observe', None)
if callback and callback.__code__.co_filename.replace('\\', '/').endswith('/observe_warehouse_camera_runtime.py'):
    unreal.unregister_slate_post_tick_callback(__main__.handle)
    __main__.data['observer_stopped'] = True
    Path(r'D:\UEPro\Test\Saved\GHS_WarehouseCameraRuntime.json').write_text(
        json.dumps(__main__.data, indent=2), encoding='utf-8')
    unreal.log('WAREHOUSE_CAMERA_TEMPORARY_OBSERVER_REMOVED')
