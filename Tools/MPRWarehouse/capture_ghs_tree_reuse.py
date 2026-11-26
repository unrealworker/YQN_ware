"""Two fixed native views; no frame sequences or scene saves."""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import verify_mpr_full_sorter_runtime as v

def run():
    yield from v.wait('discover',v.discover,60)
    v.sim.set_panel_visible(False)
    v.console('DisableAllScreenMessages')
    captures=[]
    for name,target,distance,pitch,yaw in [
        ('overview',(6500,0,0),110000,-52,-90),
        ('detail',(-10356,-9935,150),2800,-25,90)]:
        v.pawn.focus_on_target(v.u.Vector(*target),distance,v.u.Rotator(pitch=pitch,yaw=yaw),v.u.Vector2D(1920,1080),v.u.Vector2D(960,540),0)
        yield from v.pause(6)
        v.pawn.freeze_current_pose()
        p=v.OUT/(name+'.png')
        v.console('Shot filename="'+p.as_posix()+'" -nosuffix')
        yield from v.wait(name,lambda:v.timing.png_ready(p),15)
        captures.append(dict(name=name,path=str(p),camera=v.camera()))
    v.report.update(success=True,stage='complete',captures=captures)
    v.write()

stage='before' if '-TreeBefore' in u.SystemLibrary.get_command_line() else 'after'
v.BASE=v.ROOT/'Saved/MPR/ghs_tree_reuse'/stage
v.run=run
if __name__=='__main__':v.main()
