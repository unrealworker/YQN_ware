"""Render the GHS plan and export the bay identity and column-contact review lists."""
import csv
import json
import math

from PIL import Image, ImageDraw, ImageFont
from extract_cad24_layout import DEFAULT_OUTPUT, ROOT

OUT = ROOT / 'output/GHS-CAD24'
COLORS = {'A': '#b77538', 'B': '#675598', 'C': '#147d83', 'A1': '#6a8e44',
          'D1': '#4286ba', 'pass': '#2b3441', 'ground': '#c69c36'}


def csv_file(name, headings, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(headings)
        writer.writerows(rows)


def draw_plan(layout, building, audit):
    im = Image.new('RGB', (2400, 1040), '#f8f8f5')
    draw = ImageDraw.Draw(im)
    font_path = 'C:/Windows/Fonts/msyh.ttc'
    def label(x, y, text, size=22, color='#243139'):
        draw.text((x, y), text, font=ImageFont.truetype(font_path, size), fill=color)

    scale = 4.75
    def xy(p):
        return (round(80 + (p[0] + 240) * scale), round(158 + (61 - p[1]) * scale))
    def polygon(row, ground=False):
        angle = math.radians(row['rotation_deg'])
        length, width = row['physical_span_m'], row['physical_depth_m']
        if ground:
            length, width = width, length
        along = (math.cos(angle) * length / 2, math.sin(angle) * length / 2)
        across = (-math.sin(angle) * width / 2, math.cos(angle) * width / 2)
        return [xy([row['position_m'][i] + s * along[i] + t * across[i] for i in (0, 1)])
                for s, t in [(-1, -1), (-1, 1), (1, 1), (1, -1)]]

    label(78, 38, 'GHS   整仓货架与地堆平面图', 47)
    label(80, 105, '2026.10.10  安装复原图    /    3,367 档货架    ·    776 个地堆托盘    ·    168 个柱网对齐点', 22, '#53636a')
    outline = [xy(p) for p in building['footprint_outline_m']]
    draw.polygon(outline, fill='#ffffff', outline='#838b8b', width=3)
    rack_by_id = {r['id']: r for r in layout['racks']}
    for rack in layout['racks']:
        color = COLORS['pass' if rack['pass_variant'] else rack['variant']]
        draw.polygon(polygon(rack), fill=color)
    for ground in layout['ground']:
        draw.polygon(polygon(ground, True), fill=COLORS['ground'])
    # Mark four widely spaced structural registration controls with cross hairs.
    for col in audit['registration_controls']:
        x, y = xy(col['position_m'])
        draw.ellipse((x-7, y-7, x+7, y+7), outline='#122d49', width=2)
        draw.line((x-12, y, x+12, y), fill='#122d49', width=2)
        draw.line((x, y-12, x, y+12), fill='#122d49', width=2)
    for contact in audit['cad_pillar_contacts']:
        if contact['frame_or_beam_overlap']:
            x, y = xy(rack_by_id[contact['rack']]['position_m'])
            draw.ellipse((x-7, y-7, x+7, y+7), outline='#d12e27', width=3)

    legend = [('A', 'A 宽轨'), ('B', 'B 密层'), ('C', 'C 深架'), ('A1', 'A1 裁短柱'),
              ('D1', 'D1 月台架'), ('pass', '跨通道'), ('ground', '地堆托盘')]
    x = 80
    for key, title in legend:
        draw.rectangle((x, 871, x+22, 892), fill=COLORS[key])
        label(x+33, 863, title)
        x += 185
    draw.ellipse((x, 870, x+20, 890), outline='#d12e27', width=3)
    label(x+32, 863, '梁柱投影交叠 14 档')
    label(x+301, 863, '⊕  柱网对齐点')
    x, y = 2054, 890
    draw.line((x, y, x+round(50*scale), y), fill='#243139', width=3)
    for metres in (0, 25, 50):
        tick = x+round(metres*scale)
        draw.line((tick, y-8, tick, y+4), fill='#243139', width=2)
        label(tick-7, y+10, str(metres) + (' m' if metres==50 else ''), 18)
    label(80, 964, '坐标采用建筑局部米制，图右为 +X，图上为 +Y。红圈对应 CAD 梁带与结构柱轮廓在平面上的交叠位置。', 21, '#53636a')
    im.save(OUT / 'GHS整仓货架与地堆平面图.png')


def main():
    layout = json.loads(DEFAULT_OUTPUT.read_text(encoding='utf8'))
    building = json.loads((ROOT / 'SourceAssets/GHS/cad_layout.json').read_text(encoding='utf8'))
    audit = json.loads((OUT / 'geometry_verification.json').read_text(encoding='utf8'))
    blanks = [r for r in layout['racks'] if not r['row_code'] or not r['bay_sequence']]
    csv_file('待确认排档的93个货架.csv', ['CAD句柄','类型','图层','颜色索引','排号原值','档号原值','插入点X英寸','插入点Y英寸','中心X米','中心Y米','跨度轴朝向度'],
             ([r['id'].split('_')[-1], r['variant'], r['source_layer'], r['effective_aci'], r['row_code'], r['bay_sequence'], *r['source_xy'], *r['position_m'], r['rotation_deg']] for r in blanks))
    csv_file('货架与结构柱投影明细.csv', ['货架句柄','排号','档号','柱句柄','交叠范围'],
             ([c['rack'].split('_')[-1],c['row'],c['bay'],c['column_handle'],'边梁或端框' if c['frame_or_beam_overlap'] else '货架包络'] for c in audit['cad_pillar_contacts']))
    draw_plan(layout, building, audit)


if __name__ == '__main__':
    main()
