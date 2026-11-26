"""Export original CAD identifiers joined to the user's real location records.

CAD labels, derived identities and literal CSV identifiers are separate columns.
No scene mapping is added by this report. Unresolved targets retain blank WMS
fields instead of pretending their lack of a mapping means empty stock.
"""
import argparse
import collections
import csv
import html
import json
from pathlib import Path

import build_bindings as rules


def export(root, csv_path, cad_path, output, workbook=None):
    output.mkdir(parents=True, exist_ok=True)
    mapping = rules.read_json(root/'Content/GHSTwinUI/data/inventory-bindings.json')
    assert mapping['sourceInventorySha256'] == rules.sha(csv_path)
    assert mapping['sourceCadSha256'] == rules.sha(cad_path)
    for name, digest in mapping['sourceHashes'].items():
        assert rules.sha(root/name) == digest, name
    if mapping.get('rule', {}).get('id') == 'cad24-beam-position':
        return export_cad24(root, csv_path, mapping, output, workbook)
    attrs = rules.dxf_insert_attributes(cad_path)
    racks = {r['instance_id']: r for r in rules.read_json(root/'SourceAssets/GHS/RefinementV2/Layout/rack_spacing.json')['racks']}
    floor = {r['id']: r for r in rules.read_json(root/'SourceAssets/GHS/cad_layout.json')['storage']}
    meshes = {m['name']: m['cargo_stacks'] for m in rules.read_json(root/'Content/GHSTwinUI/data/rack-slots.json')['meshes']}
    bindings = {(b['cadId'], b['level'], b['column']): b for b in mapping['bindings']}
    by_id = collections.defaultdict(list)
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        for row in reader:
            by_id[row['location_id']].append(row)
    inventory_fields = {'inventory_item_id', 'sku', 'quantity', 'available_quantity', 'allocation_quantity',
                        'freeze_quantity', 'wait_move_in_quantity', 'wait_move_out_quantity', 'inventory_updated_at_utc8'}
    metadata_fields = [h for h in headers if h not in inventory_fields]
    scene = rules.canonical_scene_groups(rules.read_json(root/'Content/GHSTwinUI/data/scene-bindings.json'))
    out_rows, joined_rows = [], []
    examples = {}
    for group in scene:
        is_rack = group['mesh'].startswith('SM_GHS_V2Rack_')
        if not is_rack and not group['mesh'].startswith('SM_GHS_Presentation_Cargo'):
            continue
        for instance in group['instances']:
            cid = instance['id']
            source = racks[cid] if is_rack else floor[cid]
            handles = source['source_handles']
            original = attrs[handles[-1]]['attributes']
            label = original.get('BLOCK_CODE') if is_rack else original.get('ZONE_CODE')
            sequence = original.get('SEQ', '')
            for slot in meshes[group['mesh']] if is_rack else [dict(level=1, column=1)]:
                binding = bindings.get((cid, slot['level'], slot['column']))
                prefix = {'CAD实例': cid, 'CAD句柄路径': '/'.join(handles), '类型': '货架' if is_rack else '地堆',
                    'CAD原文编号': label, 'CAD原文序号': sequence,
                    '模型局部层': slot['level'], '模型档内列': slot['column'],
                    '关联方式': '编码与结构规则关联，非现场确认' if binding else '尚无唯一对应，不等于空货位',
                    '推导排': binding.get('cadResolution', {}).get('resolvedRow', '') if binding else '',
                    '推导档': binding.get('cadResolution', {}).get('resolvedBay', '') if binding else '',
                    '关联依据': json.dumps(binding.get('cadResolution', {}), ensure_ascii=False, separators=(',', ':')) if binding else '',
                    'CSV原始库位编码': binding['locationCode'] if binding else '',
                    'CSV原始库位ID': binding['locationId'] if binding else ''}
                source_rows = by_id[binding['locationId']] if binding else []
                if source_rows:
                    assert all(r['warehouse_id']=='108' and r['location_code']==binding['locationCode'] for r in source_rows)
                    assert all(all(r[k]==source_rows[0][k] for k in metadata_fields) for r in source_rows)
                items = [r for r in source_rows if r['inventory_item_id']]
                row = {**prefix, **{k: source_rows[0][k] if source_rows else '' for k in metadata_fields},
                    '库存记录条数': len(items) if binding else '',
                    '库存总量_件': sum(int(r['quantity'] or 0) for r in items) if binding else '',
                    '可用总量_件': sum(int(r['available_quantity'] or 0) for r in items) if binding else '',
                    'SKU明细': json.dumps([{k:r[k] for k in headers if k in inventory_fields} for r in items], ensure_ascii=False, separators=(',', ':')) if binding else ''}
                out_rows.append(row)
                for item in source_rows:
                    joined_rows.append({**prefix, **item})
                if (cid=='CAD_33D7FD' and slot['column']==2 and slot['level']==2
                        or cid=='CAD_369D01_369ADD' and slot['column']==3 and slot['level']==6
                        or cid=='CAD_30F339'
                        or cid=='CAD_35ED2D_36CA19' and slot['level']==1 and slot['column']==1):
                    examples[cid]=row
    assert len(out_rows)==32586
    assert sum(bool(r['CSV原始库位ID']) for r in out_rows)==len(bindings)
    assert len({(r['CAD实例'],r['模型局部层'],r['模型档内列']) for r in out_rows})==len(out_rows)
    assert len({r['CSV原始库位ID'] for r in out_rows if r['CSV原始库位ID']})==len(bindings)
    for name, rows in [('全部CAD托位与真实库位信息.csv', out_rows),('已关联CAD托位的原始库存明细.csv', joined_rows)]:
        with (output/name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer=csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
    summary={'date':'2026-11-26','allSceneTargets':len(out_rows),'matchedLocations':len(bindings),
        'unresolvedTargets':len(out_rows)-len(bindings),'joinedSourceRows':len(joined_rows),
        'sourceCadSha256':rules.sha(cad_path),'sourceCsvSha256':rules.sha(csv_path),
        'bindingSha256':rules.sha(root/'Content/GHSTwinUI/data/inventory-bindings.json'),
        'fieldConfirmed':0,'examples':examples}
    (output/'lookup-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    panels=[]
    for cid in ('CAD_35ED2D_36CA19','CAD_33D7FD','CAD_369D01_369ADD','CAD_30F339'):
        row=examples[cid]
        evidence=json.loads(row['关联依据'] or '{}')
        fields=[('CAD 原文编号',row['CAD原文编号']),('CAD 原文序号',row['CAD原文序号']),
                ('独立文字轴号',evidence.get('axisText',{}).get('text','—')),
                ('模型局部层 / 列',f'{row["模型局部层"]} / {row["模型档内列"]}'),
                ('CSV 库位编码',row['location_code'] or '没有唯一对应记录'),
                ('CSV 库位 ID',row['location_id'] or '—'),('库存总量 / 件',row['库存总量_件'] if row['库存总量_件']!='' else '未知，不能当作 0'),
                ('可用数量 / 件',row['可用总量_件'] if row['可用总量_件']!='' else '—'),
                ('WMS 库区 / 层 / 横向序号',' / '.join(row[k] or '—' for k in ('warehouse_area_id','location_layer','horizontal_num')))]
        panels.append('<article><h3>'+html.escape(cid)+'</h3><dl>'+''.join('<dt>'+html.escape(k)+'</dt><dd>'+html.escape(str(v))+'</dd>' for k,v in fields)+'</dl></article>')
    visuals=[]
    for filename,label in [('axis-unnamed-1.svg','原 CAD：左端 R1 独立文字标注'),('R17-16-original-cad.svg','原 CAD：R17 第16档'),('A01-01-original-cad.svg','原 CAD：A01 第01位'),('axis-R17-SR01.svg','原 CAD：SR01–SR03 与底边 R19–R21 是不同编号体系')]:
        if (output/'cad-review'/filename).exists():
            visuals.append(f'<figure><img src="cad-review/{filename}" alt="{label}"><figcaption>{label}，直接从原 DXF 渲染，不是场景截图或重绘。</figcaption></figure>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CAD编码与真实库位查询结果</title><style>
body{background:#f3f6fb;color:#21354d;font:15px/1.7 'Microsoft YaHei',sans-serif;margin:0}main{max-width:1180px;margin:auto;padding:36px 22px}header{border-bottom:3px solid #3266ff;padding-bottom:20px}h1{font-size:28px;margin:0}h2{font-size:21px;margin-top:28px}h3{font-size:16px;margin:0 0 16px}.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin:24px 0}article{background:white;border:1px solid #dde5f0;border-radius:10px;padding:20px}dl{margin:0}dt{font-size:13px;color:#61738c;margin-top:12px}dd{margin:0;font-weight:600;overflow-wrap:anywhere}a{color:#245bf2}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:12px;border:1px solid #dce4ef}th{background:#eaf0ff}.note{background:#fff4df;padding:16px;border-left:4px solid #d99d2e}figure{margin:16px 0}img{width:100%;border:1px solid #dce4ef;background:#fff}figcaption,small{color:#61738c;font-size:13px}@media(max-width:850px){.cards{grid-template-columns:1fr}}
</style><main><header><h1>通过 CAD 编码读取 CSV 真实库位信息</h1><p>全量核对：2026-11-26 · 仓库 GHS_CA_US / 108 · 库存源文件为用户提供的 2026-11-25 导出。</p></header>'''
    page+=f'<p><strong>{len(out_rows):,} 个场景目标已逐项核对，其中 {len(bindings):,} 个托位已关联并提取真实库位信息。</strong>本轮重新读取原始 DXF 独立文字、块属性、内嵌表格、两个 Excel 工作表及 CSV 全部库位字段。</p>'
    page+='<p><strong>补上之前漏读的 R1 独立文字轴号。</strong>左端 14 档与 R02、R03 两排的档位、规格、朝向一致，新增 168 个规则关联；原有 21,291 条库位 ID 不变。另 8 档与参考排偏移 0.3048 m，继续不绑定。原块属性 A_A_000 / 1 保留在导出中，独立轴号 R1 与推导 R01 另行记录，不伪造原始编码。</p>'
    page+='<div class="note">CAD 上确实有编号。货架提供排号、档号等信息；它们与 CSV 完整库位编码需要按结构关联，不能把“第 16 档”直接当作“第 16 个托位”。所有推导保留 CAD 原值，并继续注明待现场核验。</div>'
    page+='<h2>实际查到的库位信息</h2><div class="cards">'+''.join(panels)+'</div><p>左端 R1 首档第 1 层首位对应 GHS-R01-01-01；块属性仍保留原来的 A_A_000 / 1。R17 第 16 档包含第 46、47、48 个托位，因此第 2 层中间托位关联 GHS-R17-47-02。S06 通道根据相邻 SR06 排恢复业务排号，局部第 6 层对应物理第 12 层。地堆 A01 / 01 的原始编码已读出，但 CSV 的编码和名称中没有唯一对应。</p>'
    stock_rows=sum(bool(r['inventory_item_id']) for r in joined_rows)
    page+=f'<h2>完整提取结果</h2><ul><li><a href="全部CAD托位与真实库位信息.csv">全部 {len(out_rows):,} 个 CAD 托位及真实库位字段</a>：含原编号、句柄、推导编号、库位尺寸、状态、数量和 SKU 明细。未关联项保留空白。</li><li><a href="已关联CAD托位的原始库存明细.csv">已关联托位对应的 {len(joined_rows):,} 行 CSV 原始数据</a>：39 个源字段保持原值，其中 {stock_rows:,} 行是库存记录，{len(joined_rows)-stock_rows:,} 行是无库存记录的库位占位行。</li><li><a href="lookup-summary.json">统计与源文件指纹</a></li><li><a href="independent-review/csv-acceptance.json">独立逐字段校验结果</a></li></ul>'
    page+='<h2>未关联项仍需保留的原因</h2><table><tr><th>类别</th><th>数量</th><th>核对结果</th></tr><tr><td>地堆 A01–A54</td><td>7,530</td><td>图纸与 Excel 有区号/序号，但 CSV 没有同名记录或唯一转换关系。</td></tr><tr><td>其余 A_A_000 特殊货架</td><td>3,426</td><td>剩余占位编号无法唯一确定业务排/档。底边 R19–R21 对应上方 SR01–SR03，不能一律拿底边文字当业务排。</td></tr><tr><td>R40–R47 第13/14档</td><td>144</td><td>编号与物理方向存在冲突，保留原值，暂停关联。</td></tr><tr><td>SR 顶层</td><td>27</td><td>当前编码族缺少库位；旧编码族未具备相同档号元数据，不能直接替代。</td></tr></table>'
    page+='<p>R01 新增记录中有 9 条尺寸在米字段内填写 48×40×85，疑似未换算的英寸；另 42 条第 4 层限高为 1.016 m。导出保留原数值，不将这些值用于缩放模型。<a href="table-review/R01轴线候选WMS复核.md">查看逐项尺寸及编码复核说明</a>。</p>'
    page+='<p>库位名称中的额外别名仅补充了普通货架去掉 GHS 前缀的写法，没有发现地堆桥接。部分 R01 库位及 SR 顶层的行/列字段写法与其它层相反，查询保留 CSV 原值，不以字段中文名重新排列场景。</p><p>导出中的 scene_mapping_status 等原字段仍保留 CSV 的 unmapped/空值；本项目实际关联情况看新增的“关联方式”“CSV原始库位ID”列，避免改写业务源数据。CAD 内嵌 Excel 表格也已解包核对，为建筑、停车和绿地面积统计，不是库位对照。</p>'+''.join(visuals)
    runtime_path=output/'runtime/runtime.json'
    if runtime_path.exists():
        runtime=rules.read_json(runtime_path)
        if (runtime.get('success') and runtime.get('bindings_sha256')==summary['bindingSha256']
                and runtime.get('map_sha256_before')==runtime.get('map_sha256_after')):
            page+=f'<h2>UE5.8 本地验收</h2><p>当前关联数据通过 {len(runtime["checks"])} 项实际场景检查，包括新增 R1 有货/空位、详情、未匹配保护及追溯恢复；场景地图文件未改变。<a href="runtime/runtime.json">查看验收记录</a>。</p>'
            for state,label in [('occupied','R1 有货库位'),('empty','R1 空库位')]:
                page+=f'<figure><img src="runtime/reaudit-cad_r1_axis_{state}.png" alt="{label}"><figcaption>{label}：本机实际运行截图，尺寸显示保持原 CSV 值，上述异常单位仍待业务数据修正。</figcaption></figure>'
    page+=f'<p><small>本轮更新库位关联数据，不修改场景几何、原始 CAD 或 CSV，不部署服务器。已关联的 {len(bindings):,} 个位置可在项目中点击查看真实快照；本报告提供完整来源与逐项数据。</small></p></main></html>'
    (output/'CAD编码与真实库位查询结果.html').write_text(page,encoding='utf8')
    print(json.dumps({k:v for k,v in summary.items() if k!='examples'},ensure_ascii=False))
    return summary


def export_cad24(root, csv_path, mapping, output, workbook):
    from bind_cad24 import read_workbook
    if not workbook or rules.sha(workbook) != mapping['sourceWorkbookSha256']:
        raise ValueError('请指定与当前场景绑定一致的 --workbook 库位明细')
    beams, _floor = read_workbook(workbook)
    layout = rules.read_json(root/'SourceAssets/GHS/CAD24/racks.json')
    racks = {r['id']: r for r in layout['racks']}
    ground = {p['id']: p for p in layout['ground']}
    data = root/'Content/GHSTwinUI/data'
    groups = rules.canonical_scene_groups(rules.read_json(data/'scene-bindings.json'))
    models = {m['source_mesh']: m['cargo_stacks'] for m in rules.read_json(data/'storage-capacity.json')['meshes']
              if m['kind'] == 'rack'}
    bindings = {(b['cadId'],b['level'],b['column']):b for b in mapping['bindings']}
    records = collections.defaultdict(list)
    codes = set()
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        source_fields = reader.fieldnames
        for r in reader:
            records[r['location_id']].append(r)
            codes.add(r['location_code'])
    columns = ['CAD实例','排号或地堆区号','档号或地堆序号','货架规格','模型局部层','档内模型列','物理层',
               '梁号','梁层规格','净高_英寸','深度_英寸','跨宽_英寸','该梁层库位数','该梁层可用库容_立方米',
               '关联情况','库位ID','WMS原始库位码','库存条数','库存总件数','可用件数','SKU']
    summary_file = output/'全部CAD托位与真实库位信息.csv'
    detail_file = output/'已关联CAD托位的原始库存明细.csv'
    counted = matched = raw_count = 0
    with summary_file.open('w', encoding='utf-8-sig', newline='') as summary, detail_file.open('w', encoding='utf-8-sig', newline='') as details:
        targets = csv.writer(summary)
        raw = csv.writer(details)
        targets.writerow(columns)
        raw.writerow(['CAD实例','模型局部层','档内模型列',*source_fields])
        for g in groups:
            for inst in g['instances']:
                cid = inst['id']
                if cid in racks:
                    r = racks[cid]
                    row = r['row_code']
                    bay = int(r['bay_sequence']) if row else ''
                    slots = models[g['mesh']]
                    variant = r['variant']
                elif cid in ground:
                    attrs = ground[cid]['attrs']
                    row, bay = attrs['ZONE_CODE'], attrs['SEQ']
                    slots = [dict(level=0,column=0,physical_level=0)]
                    variant = '地堆'
                else:
                    continue
                for s in slots:
                    level, col, phys = s['level'], s['column'], s['physical_level']
                    b = bindings.get((cid,level,col))
                    beam = beams.get((row,bay),{}).get(phys,{})
                    source_rows = records[b['locationId']] if b else []
                    items = [item for item in source_rows if item['inventory_item_id']]
                    if b:
                        status = '按 CAD、库位表及 WMS 规则关联'
                    elif cid in ground:
                        status = '整区编码对应多个托盘' if row in codes else 'WMS 缺少对应地堆编码'
                    else:
                        status = '无唯一 WMS 对应' if beam else 'CAD 未给该托位业务编码'
                    totals = [sum(int(i[field]) for i in items) if b and all(i[field] for i in items) else ''
                              for field in ('quantity','available_quantity')]
                    targets.writerow([cid,row,bay,variant,level,col,phys,beam.get('beam_code',''),
                        beam.get('beam_key_code',''),beam.get('size_height',''),beam.get('size_deep',''),
                        beam.get('size_width',''),beam.get('库位数量',''),beam.get('库容-最终可用',''),status,
                        b['locationId'] if b else '',b['locationCode'] if b else '',len(items) if b else '',
                        *totals,','.join(sorted({i['sku'] for i in items}))])
                    counted += 1
                    matched += bool(b)
                    for item in source_rows:
                        raw.writerow([cid,level,col,*(item[k] for k in source_fields)])
                        raw_count += 1
    if matched != len(bindings) or counted != mapping['issues']['sceneRackSlots'] + mapping['issues']['sceneFloorSlots']:
        raise ValueError('导出的 CAD 托位数或关联数与场景不一致')
    print(json.dumps(dict(sceneTargets=counted,mapped=matched,rawRows=raw_count), ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=rules.ROOT)
    p.add_argument('--csv',type=Path,required=True)
    p.add_argument('--cad',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workbook',type=Path,help='CAD 2.4 库位明细')
    args=p.parse_args()
    export(args.root,args.csv,args.cad,args.output,args.workbook)
