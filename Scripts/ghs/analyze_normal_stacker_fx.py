"""Offline PNG differences/GIF; run after the dedicated UE capture has exited."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / 'Saved'


def main():
    capture_path = SAVED / 'GHS_NormalStackerFX_CaptureReport.json'
    capture = json.loads(capture_path.read_text(encoding='utf8'))
    assert capture['success'] and len(capture['screenshots']) == 4, 'Capture did not complete'
    rows = capture['screenshots']
    frames = []
    for row in rows:
        path = Path(row['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'Frame changed after capture'
        assert row['camera'] == capture['camera'], 'Frames do not use the same camera'
        frame = Image.open(path).convert('RGB')
        assert frame.size == (1280, 960)
        frames.append(frame)
    arrays = [np.asarray(frame).astype(np.int16) for frame in frames]
    # Green-dominant pixels isolate the requested green effects from AA noise on
    # the static blue/grey vehicle and tan cargo. This is evidence, not a proof of
    # shader causality: the four images still need visual inspection.
    masks = [(a[:, :, 1] > a[:, :, 0] + 12) & (a[:, :, 1] > a[:, :, 2] + 5)
             & (a[:, :, 1] > 45) for a in arrays]
    union = np.logical_or.reduce(masks)
    comparisons = []
    diff_images = []
    for k in range(3):
        diff = np.abs(arrays[k + 1] - arrays[k])
        magnitude = diff.max(axis=2)
        changed = magnitude > 8
        comparisons.append(dict(pair=[k + 1, k + 2], changed_pixels_gt8=int(changed.sum()),
            changed_fraction_gt8=float(changed.mean()), mean_absolute_rgb_delta=float(diff.mean()),
            green_union_pixels=int(union.sum()), changed_green_pixels_gt8=int((changed & union).sum()),
            green_mask_symmetric_difference_pixels=int((masks[k] ^ masks[k + 1]).sum()),
            request_interval_seconds=rows[k + 1]['requested']['monotonic_seconds'] - rows[k]['requested']['monotonic_seconds'],
            png_write_interval_seconds=(rows[k + 1]['png_mtime_ns'] - rows[k]['png_mtime_ns']) / 1e9))
        diff_images.append(Image.fromarray(np.clip(diff * 4, 0, 255).astype(np.uint8)))
    duration_ms = int(round(capture['requested_interval_seconds'] * 1000))
    frames[0].save(SAVED / 'GHS_NormalStackerFX_Animation.gif', save_all=True, append_images=frames[1:],
                   duration=duration_ms, loop=0, disposal=2)
    sheet = Image.new('RGB', (1280, 1020), '#101c29')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 20)
    for k, frame in enumerate(frames):
        x, y = (k % 2) * 640, (k // 2) * 510
        sheet.paste(frame.resize((640, 480)), (x, y + 30))
        elapsed = rows[k]['requested']['monotonic_seconds'] - rows[0]['requested']['monotonic_seconds']
        draw.text((x + 10, y + 4), 'Frame %02d | request +%.3f s' % (k + 1, elapsed), font=font, fill='white')
    sheet.save(SAVED / 'GHS_NormalStackerFX_ContactSheet.png')
    diff_images[0].save(SAVED / 'GHS_NormalStackerFX_Difference01_02.png')
    result = dict(success=True, capture_report_sha256=hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        fixed_camera_verified=True, green_pixels_per_frame=[int(m.sum()) for m in masks], comparisons=comparisons,
        pixel_changes_observed=all(r['changed_pixels_gt8'] > 0 for r in comparisons),
        green_region_changes_observed=all(r['changed_green_pixels_gt8'] > 30 for r in comparisons),
        interpretation='Pixel changes in green regions support visible animation. Static-frame differences alone cannot prove they arise only from the intended shader or certify smooth realtime playback.',
        gif_note='GIF playback uses the requested interval (%d ms/frame); actual request and PNG write intervals are in comparisons.' % duration_ms,
        outputs=['GHS_NormalStackerFX_Animation.gif', 'GHS_NormalStackerFX_ContactSheet.png', 'GHS_NormalStackerFX_Difference01_02.png'])
    (SAVED / 'GHS_NormalStackerFX_PixelAnalysis.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result, indent=2))
    print('GHS_NORMAL_STACKER_FX_PIXELS_ANALYZED')


if __name__ == '__main__':
    main()
