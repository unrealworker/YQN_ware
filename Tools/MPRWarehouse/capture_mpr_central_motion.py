"""Fixed-view native motion capture after functional acceptance; no asset saves."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
import verify_mpr_central_runtime as central
v=central.v

def run():
    v.report.update(scope='Native fixed-view presentation capture of the corrected central equipment.',
                    limitations=['CAD fixes XY; height, speed and dwell are demonstration parameters.'])
    yield from v.wait('discover',v.discover,40)
    for command in ('DisableAllScreenMessages','t.MaxFPS 0','r.VSync 0','t.IdleWhenNotForeground 0'):
        v.console(command)
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.reset_simulation();v.sim.set_simulation_playing(True)
    central.bind(central.verify_state(v.state()))
    yield from central.focus_view('overview',[-10434,1300,130],4300,-48,0,fov=60)
    value=v.step(120)
    yield from central.capture('central_overview',value)
    v.sim.set_panel_visible(False)
    yield from central.feed_sequence('end_a_three_operators',[-10530,-150,120],30)
    yield from central.feed_sequence('end_b_three_operators',[-10330,2770,120],-150)
    assert len(v.report['infeed_sequence'])==256
    v.report.update(success=True,stage='complete')

v.BASE=v.ROOT/'Saved/MPR/central_distribution_20261109/presentation'
v.run=run
if __name__=='__main__':v.main()
