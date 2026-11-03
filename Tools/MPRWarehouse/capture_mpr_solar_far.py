"""24 native far-distance samples; run with -MPRMotionLabel=far.

Reuses the original capture callbacks, PNG checks and saved-map guard. Each
pose settles for 0.15s; this is deterministic sampling, not real-time video.
"""
from pathlib import Path
import sys,re,hashlib
import unreal as u

match=re.search(r'-MPRMotionLabel=([a-zA-Z0-9_-]+)',u.SystemLibrary.get_command_line())
assert match and match.group(1)=='far','Use -MPRMotionLabel=far to keep baseline/final evidence separate'
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_solar_motion as motion

# 12 outward poses including both endpoints, then 12 returning poses. The
# apex is sampled once; all adjacent positions stay on the same camera ray.
motion.POSES=[('far_zoom',70000.+55000.*(i/11 if i<=11 else (23-i)/12),-58.,-82.)for i in range(24)]
motion.report.update(
    capture_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    base_capture_tool_sha256=hashlib.sha256(Path(motion.__file__).read_bytes()).hexdigest(),
    purpose='Sample the PV LOD1-to-LOD2 transitions in both directions beyond the normal overview range.',
    pose_count=len(motion.POSES),
    distance_units='Unreal centimetres; camera-to-target distance along the inherited camera ray.',
    distance_path_cm=[70000.,125000.,70000.],
    orientation_deg=dict(pitch=-58.,yaw=-82.),
    approximate_bank_lod1_to_lod2_distances_m=[765.8,779.0,793.4,929.2,1020.6],
    threshold_estimate_scope='Source bank bounds at 1920x1080 and horizontal FOV56; estimates, not measured active LOD readback.',
    sampling_boundary='Native PNG at each deterministic pose after the inherited 0.15s settle (first pose 12s warmup); no real-time frame pacing or input-latency claim.')
