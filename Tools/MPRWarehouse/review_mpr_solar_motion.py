"""CPU-only paired review of native MPR roof motion samples (Pillow/NumPy).

This is not real-time video: capture_mpr_solar_motion.py settles each pose for
0.15 s. Success means that this audit completed on compatible, hash-checked
inputs, never that a scene is flicker-free. Different baseline/final map hashes
are expected and recorded. No UE/Blender import, asset save, or source mutation.

Example:
  python Tools/MPRWarehouse/review_mpr_solar_motion.py
  python Tools/MPRWarehouse/review_mpr_solar_motion.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
WORLD = np.array([[-60., 80.], [-60., -80.], [160., -80.], [160., 80.]])
# The capture calibration quad remains identical to the historic baseline.
# A larger analysis canvas includes the east edge measured in the new aerial.
ANALYSIS_BOUNDS = (-65., 175., -85., 85.)
ANALYSIS_QUAD = np.array([[-65., 85.], [-65., -85.], [175., -85.], [175., 85.]])
LUMA = np.array([.2126, .7152, .0722], dtype=np.float32)
LIMITATIONS = [
    'Each native camera pose settles for 0.15 s; preview playback is illustrative, not real-time capture, frame-rate, latency, or continuous-motion evidence.',
    'Homography uses z=13.64 m from the capture roof quad. Raised panel hardware, perspective parallax, resampling, temporal history and LOD changes can still contribute to residual differences.',
    'Metrics are restricted to final-plan panel interiors visible and blue in BOTH runs and BOTH adjacent frames. Bright flashes may leave that intersection; blue-coverage and classification-change metrics are reported separately to expose this selection effect.',
    'Camera-aligned high-pass differences are auxiliary observations, not proof of no flicker. View-dependent reflection and changing source pixels per metre are not fully separable from temporal aliasing.',
    'Lower high-frequency energy can mean lost panel detail. Spatial high-pass contrast and blue-plane colour/coverage are reported alongside temporal residuals; a darker or blurred result is not automatically better.',
    'The final plan is authoritative for comparison masks, including equipment and access holes. Baseline geometry may differ there; excluded boundaries are not evaluated as temporal quality.',
]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def homography(src, dst):
    """Return H mapping the four source coordinates to destination coordinates."""
    a, b = [], []
    for (x, y), (u, v) in zip(np.asarray(src, float), np.asarray(dst, float)):
        a += [[x, y, 1, 0, 0, 0, -u*x, -u*y], [0, 0, 0, x, y, 1, -v*x, -v*y]]
        b += [u, v]
    h = np.r_[np.linalg.solve(np.asarray(a), np.asarray(b)), 1.].reshape(3, 3)
    return h


def transform_points(h, points):
    p = np.c_[np.asarray(points, float), np.ones(len(points))] @ h.T
    return p[:, :2] / p[:, 2:3]


def plane_pixels(world, size):
    w, h = size
    p = np.asarray(world, float)
    xmin,xmax,ymin,ymax=ANALYSIS_BOUNDS
    return np.stack([(p[..., 0]-xmin)/(xmax-xmin)*(w-1), (ymax-p[..., 1])/(ymax-ymin)*(h-1)], -1)


def plan_to_world(points, registration):
    return np.asarray(points, float)*registration['scale_m_per_px'] + registration['offset_m']


def erode(mask, radius):
    if radius <= 0:
        return np.asarray(mask, bool)
    im = Image.fromarray(np.asarray(mask, np.uint8)*255)
    return np.asarray(im.filter(ImageFilter.MinFilter(2*radius+1))) > 0


def build_panel_mask(plan, registration, architecture, size, edge_m, strip_inset_m):
    macro = Image.new('L', size)
    draw = ImageDraw.Draw(macro)
    for region in plan['regions']:
        pts = plane_pixels(plan_to_world(region['exterior_px'], registration), size)
        draw.polygon([tuple(p) for p in pts], fill=255)
        for hole in region.get('holes_px', []):
            pts = plane_pixels(plan_to_world(hole, registration), size)
            draw.polygon([tuple(p) for p in pts], fill=0)
    strips = Image.new('L', size)
    sd = ImageDraw.Draw(strips)
    for strip in architecture['roof_layout']['strips']:
        x, width = strip['x'], strip['width']
        inset = min(strip_inset_m, width*.3, (strip['y1']-strip['y0'])*.3)
        box = [[x-width/2+inset, strip['y0']+inset], [x+width/2-inset, strip['y1']-inset]]
        p = plane_pixels(box, size)
        sd.rectangle((min(p[:, 0]), min(p[:, 1]), max(p[:, 0]), max(p[:, 1])), fill=255)
    radius = max(1, math.ceil(edge_m*max((size[0]-1)/(ANALYSIS_BOUNDS[1]-ANALYSIS_BOUNDS[0]), (size[1]-1)/(ANALYSIS_BOUNDS[3]-ANALYSIS_BOUNDS[2]))))
    mask = erode(np.asarray(macro) > 0, radius) & (np.asarray(strips) > 0)
    if int(mask.sum()) < 1000:
        raise ValueError('Final plan/strip panel mask has insufficient area; verify registration and source files')
    return mask


def check_reports(baseline, final, expected_frames):
    for name, report in [('baseline', baseline), ('final', final)]:
        if report.get('success') is not True or report.get('map_unchanged') is not True:
            raise ValueError(f'{name}: capture unsuccessful or map changed during capture')
        if report.get('assets_saved') is not False:
            raise ValueError(f'{name}: expected non-mutating capture report')
        if not report.get('map_sha256'):
            raise ValueError(f'{name}: missing map SHA256')
        if len(report.get('captures', [])) != expected_frames:
            raise ValueError(f'{name}: expected {expected_frames} complete captures')
    for key in ['frame_settle_seconds', 'first_warmup_seconds']:
        if baseline.get(key) != final.get(key):
            raise ValueError(f'Capture sampling timing differs: {key}')
    for i, (a, b) in enumerate(zip(baseline['captures'], final['captures'])):
        if a['index'] != i or b['index'] != i or a['group'] != b['group']:
            raise ValueError(f'Frame {i}: sequence/group mismatch')
        ca, cb = a['camera'], b['camera']
        if ca['viewport'] != cb['viewport']:
            raise ValueError(f'Frame {i}: viewport mismatch')
        for key, atol in [('position_cm', .001), ('rotation_deg', .000001)]:
            if not np.allclose(ca[key], cb[key], rtol=0, atol=atol):
                raise ValueError(f'Frame {i}: camera {key} mismatch')
        if not math.isclose(a['fov'], b['fov'], rel_tol=0, abs_tol=.000001):
            raise ValueError(f'Frame {i}: FOV mismatch')
        if not np.allclose(a['roof_quad_px'], b['roof_quad_px'], rtol=0, atol=.001):
            raise ValueError(f'Frame {i}: projected roof quad mismatch')


def load_native(row):
    path = Path(row['path'])
    if sha(path) != row['sha256']:
        raise ValueError(f'Native PNG hash mismatch: {path}')
    with Image.open(path) as im:
        if list(im.size) != row['camera']['viewport']:
            raise ValueError(f'Native PNG viewport mismatch: {path}')
        return im.convert('RGB')


def rectify(native, row, size, xx, yy):
    # Pillow expects output -> input coefficients, not the opposite matrix.
    dest = plane_pixels(WORLD, size)
    h = homography(dest, row['roof_quad_px'])
    check = transform_points(h, dest)
    if np.max(np.abs(check-np.asarray(row['roof_quad_px']))) > 1e-5:
        raise ValueError(f'Frame {row["index"]}: invalid homography')
    out = native.transform(size, Image.Transform.PERSPECTIVE, tuple((h/h[2, 2]).ravel()[:8]), Image.Resampling.BILINEAR)
    denom = h[2, 0]*xx+h[2, 1]*yy+h[2, 2]
    sx = (h[0, 0]*xx+h[0, 1]*yy+h[0, 2])/denom
    sy = (h[1, 0]*xx+h[1, 1]*yy+h[1, 2])/denom
    valid = (denom > 0) & (sx >= 2) & (sy >= 2) & (sx < native.width-3) & (sy < native.height-3)
    return np.asarray(out).astype(np.float32), valid, h


def highpass(luma, radius):
    # A quantized blur component is an analysis transform only; native images
    # are untouched. Keep the same transform for both paired captures.
    low = np.asarray(Image.fromarray(np.clip(luma, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius)), np.float32)
    return luma-low


def blue_mask(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r < 155) & (b-r > 12) & (g-r > 3) & (b > 30)


def median(values):
    return round(float(np.median(values)), 6)


def difference_stats(a, b, mask):
    diff = (b-a)[mask]
    offset = np.median(diff)
    residual = diff-offset
    return dict(unadjusted_absolute_mean=float(np.abs(diff).mean()),
                signed_global_shift_median=float(offset),
                centered_absolute_mean=float(np.abs(residual).mean()),
                centered_absolute_p95=float(np.percentile(np.abs(residual), 95)))


def create_preview(caps_a, caps_b, target, ffmpeg, fps):
    """Resize/present original frames, never re-render or synthesize scene pixels."""
    target.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1920, 580
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{width}x{height}', '-framerate', str(fps), '-i', '-', '-an', '-c:v', 'libx264',
               '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for a, b in zip(caps_a, caps_b):
            frame = Image.new('RGB', (width, height), '#162735')
            for x, row in [(0, a), (960, b)]:
                frame.paste(load_native(row).resize((960, 540), Image.Resampling.LANCZOS), (x, 40))
            draw = ImageDraw.Draw(frame)
            draw.text((12, 5), f'BASELINE | {a["index"]:03d} {a["group"]}', fill='white')
            draw.text((972, 5), f'FINAL | {b["index"]:03d} {b["group"]}', fill='white')
            draw.text((12, 22), f'Native PNG samples; 0.15 s pose settling; {fps:g} fps illustration, NOT real-time footage. Original PNGs retained.', fill='#ccdbe7')
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        process.stdin = None
        _, stderr = process.communicate(timeout=180)
        if process.returncode != 0:
            raise RuntimeError('ffmpeg preview failed: '+stderr.decode('utf8', 'replace')[-4000:])
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    return dict(path=str(target), sha256=sha(target), resolution=[width, height], presentation_fps=fps,
                actual_capture_fps=None, frames=len(caps_a), method='Unchanged native PNG content downscaled 50 percent and placed side by side below labels; no interpolation or synthetic in-between frames')


def summarize_pairs(pairs):
    result = {}
    for group in ['static', 'pan', 'zoom']:
        rows = [p for p in pairs if p['group'] == group and p['sufficient_support']]
        item = dict(total_pairs=sum(p['group'] == group for p in pairs), analyzed_pairs=len(rows))
        for run in ['baseline', 'final']:
            vals = [p[run]['highpass']['centered_absolute_mean'] for p in rows]
            item[run] = dict(highpass_centered_mae_pair_mean=float(np.mean(vals)) if vals else None,
                             highpass_centered_mae_pair_p95=float(np.percentile(vals, 95)) if vals else None,
                             blue_classification_change_fraction_mean=float(np.mean([p[run]['blue_classification_change_fraction'] for p in rows])) if rows else None)
        before = item['baseline']['highpass_centered_mae_pair_mean']
        after = item['final']['highpass_centered_mae_pair_mean']
        item['final_to_baseline_highpass_ratio'] = after/before if before and before > 1e-8 else None
        item['interpretation'] = 'Auxiliary registered panel-interior change only; inspect preserved spatial detail, blue-mask retention, native playback and near/mid/far captures before a visual verdict.'
        result[group] = item
    return result


def run(args, result):
    base_path, final_path = args.baseline/'capture_report.json', args.final/'capture_report.json'
    before, after = read_json(base_path), read_json(final_path)
    check_reports(before, after, args.expected_frames)
    plan, reg, architecture = read_json(args.plan), read_json(args.registration), read_json(args.architecture)
    if architecture['roof_layout']['source_sha256'] != sha(args.plan):
        raise ValueError('Final architecture solar-plan SHA is stale; rebuild before this audit')
    if args.final_map and sha(args.final_map) != after['map_sha256']:
        raise ValueError('Final capture does not match the supplied current map')
    result.update(map_sha256={'baseline': before['map_sha256'], 'final': after['map_sha256']},
                  map_hashes_differ=before['map_sha256'] != after['map_sha256'],
                  captures={'baseline': dict(path=str(base_path), sha256=sha(base_path)), 'final': dict(path=str(final_path), sha256=sha(final_path))},
                  sources={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p) for p in [args.plan, args.registration, args.architecture]},
                  cvars={'baseline': before.get('cvars', {}), 'final': after.get('cvars', {})},
                  render_settings_differ=before.get('cvars') != after.get('cvars'),
                  camera_pairing_verified=True, frame_settle_seconds=before['frame_settle_seconds'])
    if result['render_settings_differ']:
        result.setdefault('warnings', []).append('Render cvars differ; comparison measures the complete final rendering change, not an isolated geometry/material effect. Both settings are recorded.')
        if args.require_same_cvars:
            raise ValueError('Render cvars differ and --require-same-cvars was requested')
    xmin,xmax,ymin,ymax=ANALYSIS_BOUNDS
    size = (args.width, round(args.width*(ymax-ymin)/(xmax-xmin)))
    full_area=covered_area=0.
    for strip in architecture['roof_layout']['strips']:
        left,right=strip['x']-strip['width']/2,strip['x']+strip['width']/2
        full_area+=(right-left)*(strip['y1']-strip['y0'])
        covered_area+=max(0,min(right,xmax)-max(left,xmin))*max(0,min(strip['y1'],ymax)-max(strip['y0'],ymin))
    result['analysis_plane'] = dict(world_quad_m=ANALYSIS_QUAD.tolist(), capture_calibration_quad_m=WORLD.tolist(), strip_area_coverage_fraction=covered_area/full_area, z_m=13.64, resolution=list(size), edge_exclusion_m=args.edge_m,
                                    strip_inset_m=args.strip_inset_m, blue_mask_erode_px=args.blue_erode_px,
                                    highpass_blur_radius_px=args.highpass_radius, interpolation='Bilinear homography, identical fixed world-plane scale')
    mask = build_panel_mask(plan, reg, architecture, size, args.edge_m, args.strip_inset_m)
    Image.fromarray(mask.astype(np.uint8)*255).save(args.out/'final_panel_interior_mask.png')
    yy, xx = np.mgrid[:size[1], :size[0]].astype(float)
    result['panel_mask_pixels'] = int(mask.sum())
    frame_rows, pair_rows, previous = [], [], None
    for a, b in zip(before['captures'], after['captures']):
        current = {}
        for name, capture in [('baseline', a), ('final', b)]:
            rgb, valid, h = rectify(load_native(capture), capture, size, xx, yy)
            luma = rgb @ LUMA
            blue = blue_mask(rgb)
            current[name] = dict(rgb=rgb, valid=valid, luma=luma, highpass=highpass(luma, args.highpass_radius), blue=blue)
        visible = mask & current['baseline']['valid'] & current['final']['valid']
        common = visible & erode(current['baseline']['blue'] & current['final']['blue'], args.blue_erode_px)
        frame = dict(index=a['index'], group=a['group'], source_images={'baseline': a['sha256'], 'final': b['sha256']},
                     visible_panel_pixels=int(visible.sum()), shared_blue_pixels=int(common.sum()),
                     shared_blue_fraction=float(common.sum()/max(1, visible.sum())))
        for name, data in current.items():
            frame[name] = dict(blue_coverage_fraction=float((data['blue'] & visible).sum()/max(1, visible.sum())),
                               median_luma=median(data['luma'][common]) if common.any() else None,
                               spatial_highpass_rms=float(np.sqrt(np.mean(data['highpass'][common]**2))) if common.any() else None)
        frame_rows.append(frame)
        if previous is not None and previous['group'] == a['group']:
            pair_visible = visible & previous['visible']
            support = common & previous['common']
            enough = int(support.sum()) >= args.min_pixels and support.sum()/max(1, pair_visible.sum()) >= .02
            pair = dict(previous_index=previous['index'], index=a['index'], group=a['group'],
                        common_visible_pixels=int(pair_visible.sum()), shared_interior_pixels=int(support.sum()),
                        support_fraction=float(support.sum()/max(1, pair_visible.sum())), sufficient_support=bool(enough))
            for name, data in current.items():
                prev = previous['data'][name]
                pair[name] = dict(blue_classification_change_fraction=float(((data['blue'] ^ prev['blue']) & pair_visible).sum()/max(1, pair_visible.sum())))
                if enough:
                    pair[name].update(luma=difference_stats(prev['luma'], data['luma'], support),
                                      highpass=difference_stats(prev['highpass'], data['highpass'], support))
            pair_rows.append(pair)
        if a['index'] in [0, 12, 48, 71, 95]:
            # Diagnostic rectification is clearly distinct from raw/native preview.
            canvas = Image.new('RGB', (size[0]*2, size[1]+24), '#192a39')
            draw = ImageDraw.Draw(canvas)
            for i, name in enumerate(['baseline', 'final']):
                diagnostic = np.clip(current[name]['rgb'], 0, 255).astype(np.uint8)
                canvas.paste(Image.fromarray(diagnostic), (i*size[0], 24))
                draw.text((i*size[0]+5, 5), f'{name.upper()} RECTIFIED ANALYSIS, frame {a["index"]} (not native perspective)', fill='white')
            canvas.save(args.out/f'analysis_rectified_{a["index"]:03d}.png')
            Image.fromarray(common.astype(np.uint8)*255).save(args.out/f'shared_support_{a["index"]:03d}.png')
        previous = dict(index=a['index'], group=a['group'], visible=visible, common=common, data=current)
    result.update(frames=frame_rows, pairs=pair_rows, groups=summarize_pairs(pair_rows),
                  source_png_count=2*len(frame_rows), insufficient_support_pairs=sum(not p['sufficient_support'] for p in pair_rows),
                  input_hashes_verified=True, visual_verdict='REQUIRES_NATIVE_VISUAL_REVIEW', flicker_free_claim=False)
    missing = [group for group, stats in result['groups'].items() if stats['analyzed_pairs'] == 0]
    if missing:
        raise ValueError('No valid shared panel support for groups: '+', '.join(missing))
    if not args.no_preview:
        if not args.ffmpeg.is_file():
            raise FileNotFoundError(f'ffmpeg unavailable: {args.ffmpeg}; use --no-preview for metrics only')
        result['preview'] = create_preview(before['captures'], after['captures'], args.out/'native_sampled_comparison.mp4', args.ffmpeg, args.preview_fps)
    else:
        result['preview'] = dict(status='explicitly_skipped', playback_is_real_time=False)
    result['success'] = True
    result['audit_complete'] = True


def self_test():
    src = np.array([[0, 0], [0, 79], [109, 79], [109, 0]], float)
    dst = np.array([[10, 8], [-2, 95], [160, 86], [145, 3]], float)
    h = homography(src, dst)
    assert np.max(np.abs(transform_points(h, src)-dst)) < 1e-8
    assert np.max(np.abs(transform_points(np.linalg.inv(h), dst)-src)) < 1e-8
    # A uniform brightness change must be reported as brightness, not as a
    # centered temporal pattern change. This guards the metric's basic claim.
    a = np.arange(400, dtype=np.float32).reshape(20, 20)/4
    d = difference_stats(a, a+17, np.ones_like(a, bool))
    assert d['unadjusted_absolute_mean'] == 17 and d['centered_absolute_mean'] == 0
    mask = np.zeros((15, 15), bool)
    mask[2:13, 2:13] = True
    assert erode(mask, 1).sum() == 81
    assert np.allclose(plane_pixels(ANALYSIS_QUAD, (1100, 800)), [[0, 0], [0, 799], [1099, 799], [1099, 0]])
    # Original calibration corners map inside the expanded canvas; they must
    # still project to the recorded native pixels without changing the camera.
    expanded=plane_pixels(WORLD,(1100,800));calibrated=homography(expanded,dst)
    assert np.max(np.abs(transform_points(calibrated,expanded)-dst))<1e-8
    # Identity registration must preserve native pixels; validates Pillow's
    # destination-to-source coefficient convention, not just matrix algebra.
    im = Image.fromarray(np.stack([a, a*1.1, a*.8], -1).astype(np.uint8))
    q = np.array([[0, 0], [0, 19], [19, 19], [19, 0]], float)
    ident = homography(q, q)
    got = im.transform(im.size, Image.Transform.PERSPECTIVE, tuple(ident.ravel()[:8]), Image.Resampling.BILINEAR)
    assert np.max(np.abs(np.asarray(got).astype(int)-np.asarray(im).astype(int))) <= 1
    # A real geometry change is allowed; a camera mismatch is not.
    sample = dict(success=True, map_unchanged=True, assets_saved=False, map_sha256='baseline',
                  frame_settle_seconds=.15, first_warmup_seconds=12., captures=[dict(index=0, group='static',
                  camera=dict(position_cm=[0, 0, 10], rotation_deg=[-45, 0, 0], viewport=[1920, 1080]),
                  fov=56, roof_quad_px=dst.tolist())])
    other = json.loads(json.dumps(sample));other['map_sha256'] = 'final'
    check_reports(sample, other, 1)
    other['captures'][0]['fov'] = 57
    try:
        check_reports(sample, other, 1)
    except ValueError:
        pass
    else:
        raise AssertionError('Camera FOV mismatch was not rejected')
    print(json.dumps(dict(success=True, checks=['projective_roundtrip', 'brightness_shift_separation', 'mask_erosion', 'world_plane_orientation', 'pillow_inverse_mapping', 'different_map_allowed', 'camera_mismatch_rejected'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT/'Saved/MPR/solar_motion/baseline')
    parser.add_argument('--final', type=Path, default=ROOT/'Saved/MPR/solar_motion/final')
    parser.add_argument('--out', type=Path, default=ROOT/'Saved/MPR/solar_motion/review')
    parser.add_argument('--plan', type=Path, default=ROOT/'SourceAssets/MPR/reference_v4/architecture/plan_solar_v5.json')
    parser.add_argument('--registration', type=Path, default=ROOT/'SourceAssets/MPR/reference_v4/site/plan_registration_v5.json')
    parser.add_argument('--architecture', type=Path, default=ROOT/'SourceAssets/MPR/reference_v4/architecture/reference_shell_manifest.json')
    parser.add_argument('--final-map', type=Path, help='Optional final map file; its hash must match final capture. Baseline map is allowed to differ.')
    parser.add_argument('--ffmpeg', type=Path, default=Path('D:/CodexTemp/hyperframes-tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe'))
    parser.add_argument('--width', type=int, default=1100)
    parser.add_argument('--edge-m', type=float, default=.4)
    parser.add_argument('--strip-inset-m', type=float, default=.10)
    parser.add_argument('--blue-erode-px', type=int, default=1)
    parser.add_argument('--highpass-radius', type=float, default=1.5)
    parser.add_argument('--min-pixels', type=int, default=500)
    parser.add_argument('--expected-frames', type=int, default=96)
    parser.add_argument('--preview-fps', type=float, default=8)
    parser.add_argument('--no-preview', action='store_true')
    parser.add_argument('--require-same-cvars', action='store_true', help='Optional isolated-change audit; by default changed render cvars are recorded and disclosed, not rejected')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    result = dict(schema_version=1, success=False, audit_complete=False, tool=Path(__file__).name,
                  tool_sha256=sha(__file__), limitations=LIMITATIONS, renderer='CPU analysis of actual native UE PNG captures')
    try:
        if args.width < 100 or args.preview_fps <= 0 or args.edge_m < 0 or args.blue_erode_px < 0:
            raise ValueError('Invalid analysis parameters')
        run(args, result)
    except Exception as error:
        result.update(error=str(error), traceback=traceback.format_exc())
    report_path = args.out/'solar_motion_review.json'
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    note = ('审计完成，仍需检查原生画面；不代表没有闪烁。' if result['success'] else '审计未完成：'+result.get('error', 'unknown'))
    (args.out/'README.md').write_text('# MPR 光伏逐姿态采样审查\n\n'+note+'\n\n'
        '每个姿态停留 0.15 秒后采集 PNG，并排 MP4 只是演示播放，不能作为实时流畅度或帧率证据。'
        '原始 PNG 未修改；analysis_rectified 图仅用于平面对齐诊断。\n\n'
        'solar_motion_review.json 记录两版地图哈希、逐帧 PNG 哈希、匹配姿态和视场角、最终面板/留空 mask、'
        '有效共同蓝面、亮度漂移、局部高通变化及空间细节强度。颜色变暗或高频细节被抹平不等于动态改善。\n', encoding='utf8')
    print(json.dumps(dict(success=result['success'], report=str(report_path), error=result.get('error'),
                          groups=result.get('groups'), insufficient_support_pairs=result.get('insufficient_support_pairs')), ensure_ascii=False))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
