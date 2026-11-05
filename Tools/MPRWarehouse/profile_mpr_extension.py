"""Identical before/after native GPU profiling of the enlarged surroundings."""
import sys
from pathlib import Path
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as base
label='before' if '-MPRExtensionBefore' in u.SystemLibrary.get_command_line() else 'after'
base.OUT=base.ROOT/'Saved/MPR/extension_20261104'/('performance_'+label)
original_sample=base.sample
def sample(name,target_m,distance,pitch,yaw,hidden):
    if name=='exterior':
        target_m,distance,pitch,yaw=[0,150,0],165000,-65,-90
    yield from original_sample(name,target_m,distance,pitch,yaw,hidden)
base.sample=sample
base.result['extension_label']=label
base.write()
base.handle=u.register_slate_post_tick_callback(base.tick)
