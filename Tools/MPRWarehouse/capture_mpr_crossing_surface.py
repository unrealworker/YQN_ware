"""Native fixed-camera review and final frame timing after the crossing repair."""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_site_completion as capture
capture.SCRIPT_PATH=Path(__file__).resolve()
capture.OUTPUT_ROOT=capture.ROOT/'Saved/MPR/crossing_surface_20261105/views'
capture.CONFIG_FILE=capture.OUTPUT_ROOT/'run_config.json'
capture.handle=u.register_slate_post_tick_callback(capture.tick)
