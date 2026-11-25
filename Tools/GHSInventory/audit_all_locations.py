"""Export a complete scene/WMS reconciliation, never inventing missing links."""
from __future__ import annotations

import argparse
import collections
import csv
import html
import json
from pathlib import Path
import re

import build_bindings as rules


REASONS = {
    'mapped': '已按规则关联，物理对应待现场核验',
    'cad_row_not_business_identifier': '原 CAD 排号为重复占位符，缺少唯一业务排号证据',
    'cad_sequence_geometry_conflict': 'CAD 档号顺序与物理中心顺序冲突，暂停绑定待核验',
    'wms_code_missing': '当前编码族缺少对应完整库位码，不能使用历史编码族替代',
    'floor_business_code_bridge_missing': 'CAD 地堆区号/序号与 WMS 编码之间没有唯一转换关系',
    'ambiguous_cad_targets_for_code': '多个场景目标竞争同一 WMS 编码',
    'ambiguous_wms_location_code': '同族数值编码不能唯一确定 WMS 库位',
}


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def code_key(code):
    match = re.fullmatch(r'(GHS-R)(\d+)-(\d+)-(\d+)', code)
    if not match:
        match = re.fullmatch(r'(GHS-SR-)(\d+)-(\d+)-(\d+)', code)
    return (match[1], *(int(match[i]) for i in (2, 3, 4))) if match else None


def family(code):
    for pattern, label in ((r'^GHS-SR-\d+-', 'GHS-SR- 当前 SR'),
                           (r'^GHS-SR\d+-', 'GHS-SR 旧分隔族'),
                           (r'^GHS-R\d+-', 'GHS-R 普通货架'),
                           (r'^R\d+-', 'R 旧前缀'),
                           (r'^GHS-TS\d+-', 'GHS-TS'),
                           (r'^GHS-TMP-G[A-Z]-', 'GHS-TMP-G'),
                           (r'^GHS-TMP-NEW', 'GHS-TMP-NEW'),
                           (r'^GHS-DG', 'GHS-DG'), (r'^GHS-G\d+', 'GHS-G')):
        if re.search(pattern, code):
            return label
    return '-'.join(code.split('-')[:2])


def audit(root, csv_path, cad_path, output, baseline=None):
    output.mkdir(parents=True, exist_ok=True)
    data = root/'Content/GHSTwinUI/data'
    mapping = rules.read_json(data/'inventory-bindings.json')
    before = rules.read_json(baseline)['bindings'] if baseline else []
    assert mapping['sourceCadSha256'] == rules.sha(cad_path)
    assert mapping['sourceInventorySha256'] == rules.sha(csv_path)
    for name, digest in mapping['sourceHashes'].items():
        assert rules.sha(root/name) == digest, name
    attrs = rules.dxf_insert_attributes(cad_path)
    racks = rules.read_json(root/'SourceAssets/GHS/RefinementV2/Layout/rack_spacing.json')['racks']
    rack_by_id = {r['instance_id']: r for r in racks}
    scene = rules.canonical_scene_groups(rules.read_json(data/'scene-bindings.json'))
    meshes = {m['name']: m['cargo_stacks'] for m in rules.read_json(data/'rack-slots.json')['meshes']}
    models = rules.read_json(root/'SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json')['meshes']
    canonical = {m['spec_type']: m['cargo_stacks'] for m in models if m.get('canonical') and not m.get('pass_variant')}
    floor = {r['id']: r for r in rules.read_json(root/'SourceAssets/GHS/cad_layout.json')['storage']}
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        raw = list(csv.DictReader(stream))
    wms = rules.index_locations(raw)
    numeric = collections.defaultdict(list)
    for code, locations in wms.items():
        if code_key(code):
            numeric[code_key(code)].extend(locations)
    index = rules.read_json(data/'inventory/index.json')
    inventory = {x['id']: x for x in index['locations']}
    bindings = {(x['cadId'], x['level'], x['column']): x for x in mapping['bindings']}
    old = {(x['cadId'], x['level'], x['column']): x for x in before}
    by_location = {x['locationId']: x for x in mapping['bindings']}
    assert len(bindings) == len(by_location) == len(mapping['bindings'])
    resolved = {r['instance_id']: rules.resolve_rack_identity(r, racks, attrs) for r in racks}
    resolved_racks = [x[0] for x in resolved.values() if x[0]]
    # Independently compare modeled centers, including reflected CAD inserts.
    grouped = collections.defaultdict(list)
    for r in resolved_racks:
        grouped[r['row_code']].append(r)
    conflicts = set()
    for group in grouped.values():
        order = sorted(group, key=lambda r: (int(r['bay_sequence']), r['position_m'][1]))
        for left, right in zip(order, order[1:]):
            if int(left['bay_sequence']) != int(right['bay_sequence']) and right['position_m'][1] <= left['position_m'][1] + .001:
                conflicts.update((left['instance_id'], right['instance_id']))
    rows = []
    for group in scene:
        is_rack = group['mesh'].startswith('SM_GHS_V2Rack_')
        is_floor = group['mesh'].startswith('SM_GHS_Presentation_Cargo')
        if not (is_rack or is_floor):
            continue
        for instance in group['instances']:
            cid = instance['id']
            if is_rack:
                rack = rack_by_id[cid]
                resolved_rack, evidence, failure = resolved[cid]
                slots = meshes[group['mesh']]
                original_row, original_bay = rack['row_code'], rack['bay_sequence']
            else:
                source = attrs[floor[cid]['source_handles'][-1]]['attributes']
                slots = [dict(level=1, column=1)]
                original_row, original_bay = source['ZONE_CODE'], source['SEQ']
                resolved_rack, evidence, failure = None, {}, 'floor_business_code_bridge_missing'
            for slot in slots:
                key = (cid, slot['level'], slot['column'])
                bound = bindings.get(key)
                physical = rules.physical_level(slot['base_z_m'], canonical[rack['spec_type']]) if is_rack else 1
                candidate = rules.expected_code(resolved_rack, slot['level'], slot['column'], physical) if resolved_rack else ''
                matches = numeric.get(code_key(candidate), []) if candidate else []
                if bound:
                    assert cid not in conflicts, (cid, 'geometry conflict must not remain bound')
                    assert len(matches) == 1 and matches[0]['location_id'] == bound['locationId'], key
                    assert rules.crosscheck_location(matches[0], resolved_rack, physical) is None, key
                    reason = 'mapped'
                elif not is_rack:
                    reason = failure
                elif not resolved_rack:
                    reason = failure or 'cad_row_not_business_identifier'
                elif cid in conflicts:
                    reason = 'cad_sequence_geometry_conflict'
                elif not matches:
                    reason = 'wms_code_missing'
                elif len(matches) > 1:
                    reason = 'ambiguous_wms_location_code'
                else:
                    raise AssertionError(('Unclassified rejected scene target', key, candidate, matches[0]['location_id']))
                assert reason in REASONS, reason
                state = inventory[bound['locationId']]['state'] if bound else 'unmatched'
                delta = '新增绑定' if bound and key not in old else '暂停绑定' if not bound and key in old else '保持绑定' if bound else '保持未匹配'
                if bound and key in old:
                    assert bound['locationId'] == old[key]['locationId'], ('Unexpected reassignment', key)
                rows.append({'场景目标': f'{cid}:L{slot["level"]}:C{slot["column"]}', '类型': '货架' if is_rack else '地堆',
                    'CAD标识': cid, '原CAD排或区': original_row, '原CAD档或序号': original_bay,
                    '推导排': resolved_rack['row_code'] if resolved_rack else '',
                    '推导档': resolved_rack['bay_sequence'] if resolved_rack else '',
                    '模型局部层': slot['level'], '模型列': slot['column'], '物理层': physical,
                    '候选完整码': candidate, '已绑定WMS编码': bound['locationCode'] if bound else '',
                    'WMS库位ID': bound['locationId'] if bound else '', '库存状态': state,
                    '数量': inventory[bound['locationId']]['quantity'] if bound else '',
                    '分类': reason, '说明': REASONS[reason], '本轮变化': delta,
                    '依据': json.dumps(bound.get('cadResolution', evidence) if bound else evidence, ensure_ascii=False, separators=(',', ':')),
                    '物理位置已现场确认': '否'})
    assert len({r['场景目标'] for r in rows}) == len(rows) == 32586
    assert sum(r['分类'] == 'mapped' for r in rows) == len(bindings)
    wms_rows = []
    for code in sorted(wms):
        for loc in wms[code]:
            bound = by_location.get(loc['location_id'])
            item = inventory[loc['location_id']]
            wms_rows.append({'库位ID': loc['location_id'], '完整库位编码': code, '编码族': family(code),
                '仓库ID': loc['warehouse_id'], '库区ID': loc['warehouse_area_id'], '档号原值': loc['horizontal_num'],
                '层号原值': loc['location_layer'], '状态原值': loc['location_status'], '库存状态': item['state'],
                '数量': item['quantity'], '可用数量': item['availableQuantity'],
                '场景绑定': '规则匹配，待现场核验' if bound else '没有当前场景绑定，不等于无库存',
                'CAD标识': bound['cadId'] if bound else '', '模型局部层': bound['level'] if bound else '',
                '模型列': bound['column'] if bound else ''})
    assert len(wms_rows) == len(inventory) == 91106
    assert len({r['库位ID'] for r in wms_rows}) == len(wms_rows)
    write_csv(output/'全部场景库位核对.csv', rows)
    write_csv(output/'全部WMS库位核对.csv', wms_rows)
    summary = {'sceneTargets': len(rows), 'rackSlots': sum(r['类型'] == '货架' for r in rows),
        'floorSlots': sum(r['类型'] == '地堆' for r in rows), 'wmsLocations': len(wms_rows),
        'mapped': len(bindings), 'states': dict(collections.Counter(r['库存状态'] for r in rows)),
        'reasons': dict(collections.Counter(r['分类'] for r in rows)),
        'changes': dict(collections.Counter(r['本轮变化'] for r in rows)),
        'sourceHashes': mapping['sourceHashes'], 'sourceCadSha256': mapping['sourceCadSha256'],
        'sourceInventorySha256': mapping['sourceInventorySha256'], 'fieldConfirmed': 0}
    (output/'audit-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    reason_html = ''.join(f'<tr><td>{html.escape(REASONS[k])}</td><td>{v:,}</td></tr>' for k, v in summary['reasons'].items())
    changes_html = ''.join(f'<li>{html.escape(k)}：<strong>{summary["changes"].get(k, 0):,}</strong> 个</li>' for k in ('新增绑定','暂停绑定','保持绑定','保持未匹配'))
    cases = [r for r in rows if r['本轮变化'] != '保持绑定' and (r['CAD标识'] == 'CAD_369D01_369ADD' or r['本轮变化'] in ('新增绑定', '暂停绑定'))]
    case_html = ''.join('<tr>'+''.join(f'<td>{html.escape(str(r[k]))}</td>' for k in ('CAD标识','原CAD排或区','原CAD档或序号','模型局部层','模型列','已绑定WMS编码','本轮变化','说明'))+'</tr>' for r in cases[:70])
    document = '''<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GHS 全库位复核报告</title><style>
body{margin:0;background:#f3f6fb;color:#21354d;font:15px/1.65 'Microsoft YaHei',sans-serif}main{max-width:1160px;margin:auto;padding:38px 24px}header{border-bottom:3px solid #3266ff;padding-bottom:20px}h1{font-size:30px;margin:0 0 10px}h2{font-size:20px;margin-top:32px}p{max-width:1000px}a{color:#245bf2}table{border-collapse:collapse;background:white;width:100%;font-size:14px}th,td{padding:11px 14px;border:1px solid #dce4ef;text-align:left}th{background:#eaf0ff;color:#213f7a}.scroll{overflow:auto}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.card{background:white;border:1px solid #dde5f0;padding:18px;border-radius:10px}.card strong{font-size:27px;display:block;color:#245bf2}.note{background:#fff4df;border-left:4px solid #df9a24;padding:15px 20px}code{font-size:13px}small{color:#60748e}li{margin:6px 0}@media(max-width:700px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:22px 14px}}
</style><main><header><h1>GHS 全库位复核报告</h1><p>2026-11-25 · 原始 CAD、库存 CSV、物理场景逐项对照。真实库存快照与物理位置确认分开标记。</p></header>'''
    document += '<div class="cards">'+''.join(f'<div class="card">{label}<strong>{value:,}</strong></div>' for label,value in [('货架托位',summary['rackSlots']),('地堆目标',summary['floorSlots']),('已按规则关联',summary['mapped']),('WMS 库位档案',summary['wmsLocations'])])+'</div>'
    document += '<h2>这次改了什么</h2><ul>'+changes_html+'</ul><p>补充 S01–S09 通道排号、R31/R32 通道档号及同一编码族的前导零差异。推导须有两侧同排同规格邻档和原 CAD 属性证据，不直接替换编号。</p>'
    document += '<p class="note">R40–R47 的第 13、14 档存在物理顺序冲突，且其中通道块反向。相关 144 个托位暂停绑定并保留原始编号，不擅自互换。其余无冲突位置保留。所有规则匹配均未取得现场实扫确认。</p>'
    document += '<h2>全部场景目标的核对结果</h2><table><thead><tr><th>分类与原因</th><th>托位数</th></tr></thead><tbody>'+reason_html+'</tbody></table>'
    document += '<h2>地堆为什么仍未关联</h2><p>全部 7,530 个地堆的 CAD 句柄、54 个区号及序号均已核对，同目录 Excel 也与 CAD 一致，但没有 WMS 业务对应字段。库存坐标中 2,800 条每 10 个库位共点、289 条为递增占位序列，剩余 1 条属于虚拟库位，不能唯一定位地堆。A01-01 的数字尾段可匹配 27 个不同业务编码，不能强行选一个。</p>'
    document += '<p>重复占位排号 A_A_000 的货架同样缺少唯一业务排号；剩余 SR 最高层缺少当前编码族记录，不能用旧分隔编码族替代。这些位置保留未匹配，不能当作空货位。</p>'
    runtime_path = output/'runtime/runtime.json'
    if runtime_path.exists():
        runtime = rules.read_json(runtime_path)
        if (runtime.get('success') and runtime.get('map_sha256_before') == runtime.get('map_sha256_after')
                and runtime.get('bindings_sha256') == rules.sha(data/'inventory-bindings.json')):
            document += f'<h2>本地实际验证</h2><p>UE5.8 实际场景 {len(runtime["checks"])} 项检查通过：新增库位详情、截图 S06 空位鼠标点选、特殊档号、前导零编码、冲突位置不冒充真实库存、追溯结束恢复等。地图文件哈希前后一致。</p><p><a href="runtime/reaudit-special_s06.png">查看用户截图对应托位的实际修复画面</a> · <a href="runtime/runtime.json">运行验证记录</a></p>'
    document += '<h2>完整核对明细</h2><ul><li><a href="全部场景库位核对.csv">全部 32,586 个场景目标：原编号、候选、状态、变化与原因</a></li><li><a href="全部WMS库位核对.csv">全部 91,106 个 WMS 库位：库存与场景绑定情况</a></li><li><a href="floor-review/地堆全量复核报告.md">地堆专项依据</a></li><li><a href="audit-summary.json">统计与输入文件指纹</a></li></ul><p>WMS 档案包含临时、区域型及历史编码，91,106 不能当作三维场景物理容量。库存为空只表示这次快照没有库存记录。</p>'
    document += '<h2>变化样例（完整记录见 CSV）</h2><div class="scroll"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['CAD','原排','原档','局部层','列','WMS编码','本轮变化','原因'])+'</tr></thead><tbody>'+case_html+'</tbody></table></div></main></html>'
    (output/'GHS全库位复核报告.html').write_text(document, encoding='utf8')
    print(json.dumps({k:v for k,v in summary.items() if 'Hash' not in k}, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=rules.ROOT)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--cad', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    options = parser.parse_args()
    audit(options.root, options.csv, options.cad, options.output, options.baseline)
