from pathlib import Path
import sys,json
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import verify_mpr_full_sorter_runtime as v

def run():
    yield from v.wait('discover',v.discover,60)
    v.sim.set_panel_visible(False);v.sim.set_simulation_playing(False)
    v.roof.open_roof(True)
    yield from v.wait('open',lambda:v.roof.is_interior_available(),20)
    v.pawn.focus_on_target(v.u.Vector(-1747.744,5937.314,103.5),2656,v.u.Rotator(pitch=-48.72,yaw=0),v.u.Vector2D(1920,1080),v.u.Vector2D(960,540),0)
    yield from v.pause(5);v.pawn.freeze_current_pose()
    p=v.OUT/'connection.png';v.console('Shot filename="'+p.as_posix()+'" -nosuffix')
    yield from v.wait('capture',lambda:v.timing.png_ready(p),15)
    v.report.update(success=True,stage='complete',captures=[dict(path=str(p),camera=v.camera())]);v.write()

stage='before' if '-MPRConnectionBefore' in u.SystemLibrary.get_command_line() else 'after'
v.BASE=v.ROOT/'Saved/MPR/conveyor_connection_20261113'/stage
v.run=run
if __name__=='__main__':v.main()
