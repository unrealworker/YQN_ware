import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import agv_deck_fix as fix
import importlib
importlib.reload(fix)
mesh=fix.lib.load_asset(fix.ASSET)
fix.write(fix.ROOT/'Saved/GHS_AGVDeckFixLiveProbe.json',dict(
    mesh=fix.metadata(mesh), surfaces=fix.corner_surfaces(mesh),
    triangle_audit=fix.triangle_audit(mesh),
    build_settings=str(fix.sm_editor.get_lod_build_settings(mesh,0))))
