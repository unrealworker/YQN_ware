from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont, ImageSequence


ROOT = Path(__file__).resolve().parent
BG = (237, 242, 245)
INK = '#213F51'
BLUE = '#255E96'
MUTED = '#5A7385'
RULE = '#C9D5DF'
SIZE = (1120, 476)
FONT = 'C:/Windows/Fonts/msyh.ttc'


def font(size):
    return ImageFont.truetype(FONT, size)


def read_state(filename):
    image = Image.open(ROOT / filename).convert('RGB')
    original_background = image.getpixel((0, 0))
    transfer = []
    for pixel in image.get_flattened_data():
        positive = max(0, max(pixel[i] - original_background[i] for i in range(3)))
        negative = max(0, max(original_background[i] - pixel[i] for i in range(3)))
        background_weight = max(0, min(1 - positive / 35, 1 - negative / 60))
        transfer.append(tuple(round(pixel[i] + (BG[i] - original_background[i]) * background_weight) for i in range(3)))
    image.putdata(transfer)
    return image


before = [read_state('pjaZh.png'), read_state('cqbgU.png')]
after = [read_state('rujV6.png'), read_state('QOVOt.png')]
blank = Image.new('RGB', (460, 180), BG)


def scaffold():
    canvas = Image.new('RGB', SIZE, BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((42, 28), 'GHS  /  轻量状态过渡', font=font(30), fill=INK)
    draw.text((43, 80), '保持标签锚点 · 用短促淡入淡出表达信息层级变化', font=font(15), fill=MUTED)
    draw.line((42, 116, 1078, 116), fill=RULE, width=1)
    draw.text((50, 140), '01   同类设备聚合', font=font(22), fill=INK)
    draw.text((610, 140), '02   设备详情展开', font=font(22), fill=INK)
    draw.text((447, 148), '120 ms', font=font(14), fill=BLUE)
    draw.text((1007, 148), '160 ms', font=font(14), fill=BLUE)
    draw.line((560, 140, 560, 392), fill=RULE, width=1)
    draw.text((50, 378), '标签原位收拢，同类型单独成组。', font=font(15), fill=MUTED)
    draw.text((610, 378), '紧凑标签与详情卡快速切换。', font=font(15), fill=MUTED)
    draw.line((42, 422, 1078, 422), fill=RULE, width=1)
    draw.text((43, 441), '状态停留 1.3 秒后循环演示', font=font(13), fill=MUTED)
    draw.text((869, 441), '原位过渡 · 无长距离飞行', font=font(13), fill=MUTED)
    return canvas


def frame(left, right):
    canvas = scaffold()
    canvas.paste(left, (50, 182))
    canvas.paste(right, (610, 182))
    return canvas


def fade_through_background(start, finish, elapsed_ms, duration_ms):
    progress = min(1, max(0, elapsed_ms / duration_ms))
    if progress < 0.5:
        return Image.blend(start, blank, progress * 2)
    return Image.blend(blank, finish, (progress - 0.5) * 2)


frames = [frame(*before)]
durations = [1300]
for time_ms in range(20, 161, 20):
    frames.append(frame(*[
        fade_through_background(before[i], after[i], time_ms, duration)
        for i, duration in enumerate((120, 160))
    ]))
    durations.append(20)
durations[-1] += 1300
for time_ms in range(20, 161, 20):
    frames.append(frame(*[
        fade_through_background(after[i], before[i], time_ms, duration)
        for i, duration in enumerate((120, 160))
    ]))
    durations.append(20)

# One shared palette keeps stationary typography and colors from flickering.
palette_source = Image.new('RGB', (SIZE[0], SIZE[1] * len(frames)), BG)
for index, image in enumerate(frames):
    palette_source.paste(image, (0, SIZE[1] * index))
palette = palette_source.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
palette_values = palette.getpalette()
accent_colors = [(207, 63, 63), (179, 93, 23), (37, 94, 150), BG]
for index, color in enumerate(accent_colors, start=256-len(accent_colors)):
    palette_values[index*3:index*3+3] = color
palette.putpalette(palette_values)
gif_frames = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image in frames]
gif_path = ROOT / 'motion-preview.gif'
gif_frames[0].save(
    gif_path,
    save_all=True,
    append_images=gif_frames[1:],
    duration=durations,
    loop=0,
    optimize=False,
    disposal=1,
)
frame(*after).save(ROOT / 'motion-preview.png')

with Image.open(gif_path) as saved:
    actual_durations = [image.info['duration'] for image in ImageSequence.Iterator(saved)]
    report = {
        'size': list(saved.size),
        'frames': saved.n_frames,
        'duration_ms': sum(actual_durations),
        'frame_durations_ms': actual_durations,
        'loop': saved.info.get('loop'),
        'aggregation_transition_ms': 120,
        'detail_transition_ms': 160,
        'hold_per_state_ms': 1300,
        'background': '#EDF2F5',
        'stationary_frames': True,
        'source_frames': ['pjaZh.png', 'rujV6.png', 'cqbgU.png', 'QOVOt.png'],
    }
    assert saved.size == SIZE
    assert saved.n_frames >= 15
    assert sum(actual_durations) == 2920
(ROOT / 'motion-preview-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
