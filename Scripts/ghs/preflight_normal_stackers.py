import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import add_normal_stackers as s
assert '-run=pythonscript' in s.unreal.SystemLibrary.get_command_line().lower()
assert s.L.load_level(s.MAP)
plan=s.read(s.ROOT/'Saved/GHS_NormalStackerPlan.json')
probe=s.read(s.ROOT/'Saved/GHS_NormalStackerProbe.json')
assert s.snapshot(s.labels())==s.read(s.ROOT/'Saved/GHS_NormalStackerLiveBaseline.json')
assert all(s.LIB.load_asset(p) for p in s.MATERIALS)
geometry=s.check_geometry(s.labels(),plan['placements'],probe)
s.write(s.ROOT/'Saved/GHS_NormalStackerPreflight.json',dict(success=True,geometry=geometry))
s.unreal.log('GHS_NORMAL_STACKER_PREFLIGHT_PASSED')
