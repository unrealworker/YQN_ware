import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import agv_deck_fix as fix
fix.require_separate_process()
mesh=fix.lib.load_asset(fix.ASSET)
fix.write(fix.ROOT/'Saved/GHS_AGVDeckSavedGeometry.json',fix.triangle_audit(mesh))
