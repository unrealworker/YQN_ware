"""Native CSV performance in the separate map, with the existing camera behavior."""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as base
base.MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
base.MAP_FILE=base.ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
base.OUT=base.ROOT/'Saved/MPR/rebuild_20261104/performance'
base.result['map']=base.MAP
original=base.sample
def sample(name,target_m,distance,pitch,yaw,hidden):
    if name=='exterior':target_m,distance,pitch,yaw=[0,150,0],165000,-65,-90
    yield from original(name,target_m,distance,pitch,yaw,hidden)
base.sample=sample
base.write()
base.handle=u.register_slate_post_tick_callback(base.tick)
