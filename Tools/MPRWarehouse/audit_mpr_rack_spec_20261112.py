"""Read original MPR DXF and preserve rack specification evidence, without scene edits."""
from __future__ import annotations
import collections
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Matrix44, Vec3

SOURCE = Path(r'D:\Data\仓库数据\MPR\平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
OUT = ROOT / 'Saved/MPR/interior_cad_20261112/rack_truth'
SPEC_OUT = ROOT / 'SourceAssets/MPR/interior_cad_20261112/racks'


class MixedDxfStream:
    def __init__(self, path):
        self.file = open(path, 'rb')

    def readline(self):
        value = self.file.readline().replace(b'\r\n', b'\n')
        try:
            return value.decode('utf8')
        except UnicodeDecodeError:
            return value.decode('gb18030', errors='replace')


def basic(e):
    return {'type': e.dxftype(), 'handle': e.dxf.handle,
            'layer': e.dxf.layer, 'color': e.dxf.get('color', 256),
            'true_color': e.dxf.get('true_color', None)}


def text_of(e):
    return e.dxf.text if e.dxftype() == 'TEXT' else e.plain_text()


def primitive_points(e):
    kind = e.dxftype()
    if kind == 'LINE':
        return [Vec3(e.dxf.start), Vec3(e.dxf.end)]
    if kind == 'LWPOLYLINE':
        p = [Vec3(x, y, e.dxf.get('elevation', 0)) for x, y in e.get_points('xy')]
        return p + p[:1] if e.closed else p
    if kind == 'POLYLINE':
        p = [v.dxf.location for v in e.vertices]
        return p + p[:1] if e.is_closed else p
    if kind in ('CIRCLE', 'ARC'):
        lo = 0 if kind == 'CIRCLE' else e.dxf.start_angle
        hi = 360 if kind == 'CIRCLE' else e.dxf.end_angle
        if hi <= lo:
            hi += 360
        c = e.dxf.center
        return [Vec3(c.x + e.dxf.radius * math.cos(math.radians(lo + (hi-lo)*i/24)),
                     c.y + e.dxf.radius * math.sin(math.radians(lo + (hi-lo)*i/24)), c.z)
                for i in range(25)]
    return []


def dump_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')


def derive_specs():
    """Derive beam elevations from flattened original CAD, not from nominal labels."""
    geometry = json.loads((OUT / 'rack_three_views_local_geometry.json').read_text('utf8'))
    dimensions = {d['handle']: d for d in json.loads((OUT / 'rack_three_views_local_dimensions.json').read_text('utf8'))}
    labels = {d['handle']: d for d in json.loads((OUT / 'rack_texts.json').read_text('utf8'))}
    # Local three-view block coordinates are real inch geometry; block instance scale=3 is sheet display scale.
    definitions = {
        '16': dict(aci=3, label='26621C', floor=-2032.612616484845, front=(305,-2020,453,-1670), thickness=[3]*16,
                   dims=['265F30','265F31','265F20','265F32','265F1D','265F1C'], portal=None,
                   cargo=(8,15.5,21,14.5), cargo_depth_rows=2, cargo_pitch=18),
        '17+1': dict(aci=6, label='26621D', floor=-2016.136267758475, front=(1251,-2000,1394,-1640), thickness=[3]*17,
                     dims=['265D64','265D53','265D54','265D50','265E54','265EFD'], portal=(1569,-1900,1713,-1640),
                     cargo=(9,14,21,13.5), cargo_depth_rows=2, cargo_pitch=16),
        '20': dict(aci=4, label='26621E', floor=-2026.663945751939, front=(2495,-2030,2639,-1650), thickness=[3]*20,
                   dims=['265F50','265F3C','265F3D','265F39','266045','2660DE'], portal=(2769,-1900,2913,-1650),
                   cargo=(9,14,21,13.5), cargo_depth_rows=2, cargo_pitch=16),
        '9': dict(aci=2, label='26621F', floor=-2029.638281118392, front=(3587,-2035,3734,-1630), thickness=[4]*9,
                  dims=['2660E5','2660E8','2660F8','2660E9','2660F7'], portal=(3897,-1900,4045,-1620),
                  cargo=(3,42,42,38), cargo_depth_rows=1, cargo_pitch=48),
        '5': dict(aci=90, label='266112', floor=-2029.638281118402, front=(4578,-2040,4722,-1600), thickness=[6]*4,
                  dims=['2661D9','2661DB','2661A4','266117','2661B9','26621A'], portal=(4913,-1800,5059,-1600),
                  cargo=(3,40,48,76), cargo_depth_rows=1, cargo_pitch=46),
        '7': dict(aci=40, label='267784', floor=-2941.047760439174, front=(243,-2950,387,-2500), thickness=[4,4,6,6,6,6],
                  dims=['26784B','26784D','267C1C','267C3A','267C58','267789','26782B','26788C'], portal=(577,-2700,723,-2500),
                  cargo=(3,40,48,76), cargo_depth_rows=1, cargo_pitch=46),
    }
    families = {}
    evidence = {}

    def beam_lines(rect, thicknesses=None):
        ys = {}
        for e in geometry:
            pp = e.get('points', [])
            for a,b in zip(pp, pp[1:]):
                if abs(a[1]-b[1]) < .0001 and 143.5 < abs(a[0]-b[0]) < 143.8:
                    if rect[0]-4 <= min(a[0],b[0]) and max(a[0],b[0]) <= rect[2]+4 and rect[1] < a[1] < rect[3]:
                        ys.setdefault(round(a[1],4), []).append({'handle': e['handle'], 'source_chain': e.get('source_chain',[])})
        values = sorted(ys)
        pairs = []
        for lo,hi in zip(values,values[1:]):
            thickness = round(hi-lo,4)
            if thickness in (3,4,6):
                pairs.append({'bottom_y':lo, 'top_y':hi, 'thickness_in':thickness,
                              'bottom_sources':ys[lo][:2], 'top_sources':ys[hi][:2]})
        if thicknesses is not None:
            assert [p['thickness_in'] for p in pairs] == thicknesses, (rect, pairs)
        return pairs

    for key,d in definitions.items():
        pairs = beam_lines(d['front'], d['thickness'])
        floor = d['floor']
        # Frame height includes the explicitly drawn 10 mm baseplate under the 360-inch upright.
        f = {'id': key, 'label':labels[d['label']]['text'], 'plan_aci':d['aci'],
             'plan_aci_basis':'同色平面与规格文字' if key != '16' else '六种类型排除和布局分区推断，16层标题为白色无绿色图例',
             'plan_aci_inferred':key=='16', 'frame_height_m':9.154, 'upright_height_m':9.144,
             'baseplate_thickness_m':.01, 'outer_width_m':3.81, 'clear_width_m':3.6576,
             'depth_m':1.0668, 'upright_section_m':.0762,
             'beam_top_m':[round((p['top_y']-floor)*.0254,6) for p in pairs],
             'beam_bottom_m':[round((p['bottom_y']-floor)*.0254,6) for p in pairs],
             'beam_thickness_m':[round(p['thickness_in']*.0254,6) for p in pairs],
             'beam_count':len(pairs), 'standard_inferred':False,
             'cargo':{'columns':d['cargo'][0], 'width_m':round(d['cargo'][1]*.0254,6),
                      'depth_m':round(d['cargo'][2]*.0254,6), 'height_m':round(d['cargo'][3]*.0254,6),
                      'pitch_x_m':round(d['cargo_pitch']*.0254,6), 'depth_rows':d['cargo_depth_rows'],
                      'bottom_m':[round((p['top_y']-floor)*.0254,6) for p in pairs],
                      'height_by_level_m':[round(d['cargo'][3]*.0254,6)]*len(pairs),
                      'depth_inferred':key=='9',
                      'basis':'封闭矩形/托盘正视外包络；16/17/20侧视21英寸深，5/7侧视48英寸深；9深度无侧视明示，以42英寸架深表达'},
             'source_label_handle':d['label'], 'source_dimension_handles':d['dims'],
             'notes':[]}
        if key=='17+1':
            f['ground_cargo']={'columns':3,'width_m':1.016,'depth_m':1.2192,'height_m':1.397,'bottom_m':0,
                               'pitch_x_m':1.143, 'source_handles':['265ED1','265EDA','265EE3'],
                               'depth_inferred':False,'basis':'正视地面3个40×55英寸托盘包络，侧视48英寸深'}
        if key in ('5','7'):
            f['ground_cargo']={'columns':3,'width_m':1.016,'depth_m':1.2192,'height_m':1.9304 if key=='5' else .7112,
                               'bottom_m':0,'pitch_x_m':1.1684,'source_handles':['26611D'] if key=='5' else ['26778F'],
                               'basis':'5层=地面1层+4梁，7层=地面1层+6梁；侧视沿用48英寸托盘深'}
        if key=='7':
            f['cargo']['height_by_level_m'][:2]=[.5588,.5588]
            f['notes'].append('7层底部两个新增层的货物包络22英寸高；地面包络28英寸；上部4层76英寸，不可均分层高。英文4beam标签未更新。')
        if key=='9':
            f['notes'].append('中文9层、英文8beam互相矛盾，原始几何明确9根4英寸梁和9层38英寸货物；按几何还原。')
        if key in ('17+1','20'):
            f['notes'].append('箱子顶面高于360英寸立柱；保留原图13.5英寸高箱体。')
        if d['portal']:
            portal_pairs=beam_lines(d['portal'])
            f['portal']={'inferred':False,'beam_top_m':[round((p['top_y']-floor)*.0254,6) for p in portal_pairs],
                         'beam_bottom_m':[round((p['bottom_y']-floor)*.0254,6) for p in portal_pairs],
                         'beam_thickness_m':[round(p['thickness_in']*.0254,6) for p in portal_pairs],
                         'clear_height_m':round((portal_pairs[0]['bottom_y']-floor)*.0254,6),
                         'basis':'三视图通道架正视实际横梁线；同层与邻架对齐',
                         'source_dimension_handle':d['dims'][-1]}
            if key in ('17+1','20'):
                f['portal']['dimension_clear_height_m']=round(dimensions[d['dims'][-1]]['actual_measurement']*.0254,6)
                f['portal']['dimension_geometry_offset_m']=round(f['portal']['dimension_clear_height_m']-f['portal']['clear_height_m'],6)
                f['notes'].append('通道净空标注的基准地面与立柱底板地面约差22毫米；模型按实际横梁几何对齐，同时保留标注值供审阅。')
            else:
                f['portal']['dimension_value_m']=round(dimensions[d['dims'][-1]]['actual_measurement']*.0254,6)
        families[key]=f
        evidence[key]={'label':labels[d['label']], 'floor_y_in_local_threeview':floor,
                       'standard_beam_lines':pairs,
                       'portal_beam_lines':beam_lines(d['portal']) if d['portal'] else None,
                       'dimensions':[dimensions[h] for h in d['dims']]}
    max_clear=max(f['portal']['clear_height_m'] for f in families.values() if 'portal' in f)
    f=families['16']
    indices=[i for i,z in enumerate(f['beam_bottom_m']) if z>=max_clear]
    f['portal']={'inferred':True,'beam_top_m':[f['beam_top_m'][i] for i in indices],
                 'beam_bottom_m':[f['beam_bottom_m'][i] for i in indices],
                 'beam_thickness_m':[f['beam_thickness_m'][i] for i in indices],
                 'clear_height_m':f['beam_bottom_m'][indices[0]], 'source_dimension_handle':None,
                 'basis':'原图16层只有标准正视和双排侧视，未画通道正视；暂保留对齐20英寸层距的上部梁，下方净空至少覆盖已明确通道的最大6.4144米；须补通道详图确认。',
                 'reference_clear_height_m':max_clear}
    report={'schema_version':1,'source':str(SOURCE), 'source_sha256':json.loads((OUT/'source_audit.json').read_text('utf8'))['sha256'],
            'threeview_insert_handle':'2DA39F','threeview_block':'三视图','threeview_sheet_scale':3,
            'units_note':'三视图块内几何为英寸；顶层3倍仅排版显示比例，不乘入设备物理尺寸。',
            'families':families,
            'wide_bay':{'clear_width_m':4.8768,'outer_width_m':5.0292,'depth_m':1.0668,
                        'source_block':'RACK_42D_192B','elevation_inferred':True,
                        'basis':'平面192英寸清宽明确，立面按同排相邻类型的通道层高延伸；本图三视只画144英寸清宽。'},
            'mixed_portals':{'source_handles':['2CFE06','2CFECC'],'candidate_families':['20','9'],
                             'family':'Unresolved','resolved':False,'inferred':True,
                             'clear_height_m':max(families['20']['portal']['clear_height_m'],families['9']['portal']['clear_height_m']),
                             'beam_top_m':[], 'beam_bottom_m':[], 'beam_thickness_m':[],
                             'basis':'平面两端20与9层类型相接，二者通道横梁标高无共同值；暂只保留共同立柱/深向支撑，不虚构跨通道梁和货物。须补详图确认。'},
            'unresolved':['16层ACI3关联来自排除法，非同色图例','16层通道架正视缺失','两处20/9通道归属冲突','192英寸通道立面未单列','9层货物深度无侧视明示']}
    SPEC_OUT.mkdir(parents=True,exist_ok=True)
    (SPEC_OUT/'rack_specs.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    (SPEC_OUT/'cad_elevation_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),'utf8')
    dump_json('rack_specs.json',report)
    print(json.dumps({'spec':str(SPEC_OUT/'rack_specs.json'), 'families':{k:{'beams':f['beam_count'],'first_top_m':f['beam_top_m'][0],
          'portal_beams':len(f['portal']['beam_top_m']),'portal_clear_m':f['portal']['clear_height_m']} for k,f in families.items()}},ensure_ascii=True))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    doc = ezdxf.read(MixedDxfStream(SOURCE))
    ms = doc.modelspace()
    texts = []
    inserts = []
    dimensions = []
    primitives = []
    for e in ms:
        kind = e.dxftype()
        if kind in ('TEXT', 'MTEXT'):
            d = basic(e)
            d.update(text=text_of(e), position=list(e.dxf.insert))
            texts.append(d)
        elif kind == 'INSERT':
            d = basic(e)
            d.update(block=e.dxf.name, position=list(e.dxf.insert), rotation=e.dxf.rotation,
                     scale=[e.dxf.xscale, e.dxf.yscale, e.dxf.zscale])
            inserts.append(d)
        elif kind == 'DIMENSION':
            d = basic(e)
            d.update({k: list(v) if isinstance(v, Vec3) else v
                      for k, v in e.dxf.all_existing_dxf_attribs().items()
                      if k not in ('owner', 'handle')})
            try:
                measurement = e.get_measurement()
                d['actual_measurement'] = list(measurement) if isinstance(measurement, Vec3) else measurement
            except Exception:
                pass
            dimensions.append(d)
        else:
            p = primitive_points(e)
            if p and any(0 <= v.y <= 2700 and 10000 <= v.x <= 23000 for v in p):
                d = basic(e)
                d['points'] = [list(v) for v in p]
                primitives.append(d)
    dump_json('modelspace_texts.json', texts)
    dump_json('modelspace_inserts.json', inserts)
    dump_json('modelspace_dimensions.json', dimensions)
    dump_json('detail_primitives.json', primitives)

    block_records = []
    block_texts = []
    for block in doc.blocks:
        bt = []
        for e in block:
            if e.dxftype() in ('TEXT', 'MTEXT'):
                d = basic(e)
                d.update(block=block.name, text=text_of(e), position=list(e.dxf.insert))
                bt.append(d)
        if bt:
            block_texts.extend(bt)
        block_records.append({'name': block.name, 'size': len(block),
                              'types': dict(collections.Counter(e.dxftype() for e in block)),
                              'layers': dict(collections.Counter(e.dxf.layer for e in block))})
    dump_json('block_texts.json', block_texts)
    dump_json('block_inventory.json', block_records)
    rack_texts = [t for t in texts + block_texts
                  if any(s in t['text'].lower() for s in ['货架', 'beam level', 'pallet position'])]
    dump_json('rack_texts.json', rack_texts)
    detail_block_names = {d['block'] for d in block_texts if '144"' in d['text'] and 'beam level' in d['text']}

    # Flatten only the drawing detail strip and rack source blocks. Never flatten the warehouse.
    def flatten(e, mat=Matrix44(), chain=(), depth=0):
        if depth > 14:
            return []
        kind = e.dxftype()
        if kind == 'INSERT':
            tr = e.matrix44() @ mat
            return [d for child in doc.blocks.get(e.dxf.name)
                    for d in flatten(child, tr, chain+(e.dxf.handle,), depth+1)]
        d = basic(e)
        d['source_chain'] = list(chain)
        if kind in ('TEXT', 'MTEXT'):
            d.update(text=text_of(e), position=list(mat.transform(e.dxf.insert)))
            return [d]
        p = primitive_points(e)
        if p:
            d['points'] = [list(mat.transform(v)) for v in p]
            return [d]
        if kind == 'DIMENSION':
            try:
                return [v for child in e.virtual_entities()
                        for v in flatten(child, mat, chain+(e.dxf.handle,), depth+1)]
            except Exception:
                return []
        return []

    detail = []
    for e in ms:
        if e.dxftype() == 'INSERT':
            p = e.dxf.insert
            if (-1500 < p.y < 2800 and 10000 < p.x < 24000) or e.dxf.name in detail_block_names:
                flat = flatten(e)
                detail.extend(flat)
    dump_json('detail_insert_geometry.json', detail)
    for name in detail_block_names:
        local = [d for e in doc.blocks[name] for d in flatten(e)]
        dump_json('rack_three_views_local_geometry.json', local)
        local_dims = []
        local_inserts = []
        for e in doc.blocks[name]:
            if e.dxftype() in ('DIMENSION', 'INSERT'):
                d = basic(e)
                d.update({k: list(v) if isinstance(v, Vec3) else v
                          for k, v in e.dxf.all_existing_dxf_attribs().items()
                          if k not in ('owner', 'handle')})
                if e.dxftype() == 'DIMENSION':
                    try:
                        d['actual_measurement'] = e.get_measurement()
                    except Exception:
                        pass
                    local_dims.append(d)
                else:
                    local_inserts.append(d)
        dump_json('rack_three_views_local_dimensions.json', local_dims)
        dump_json('rack_three_views_local_inserts.json', local_inserts)
    rack_blocks = {}
    for name in ('RACK_42D_144B', 'RACK_42D_192B'):
        if name in doc.blocks:
            rack_blocks[name] = [d for e in doc.blocks[name] for d in flatten(e)]
    dump_json('rack_plan_block_geometry.json', rack_blocks)
    report = {'source': str(SOURCE), 'bytes': SOURCE.stat().st_size,
              'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'units_header': doc.units, 'meters_per_drawing_unit': .0254,
              'elapsed_seconds': round(time.time()-started, 1),
              'text_count': len(texts), 'dimension_count': len(dimensions),
              'detail_primitive_count': len(primitives), 'detail_insert_primitive_count': len(detail),
              'rack_texts': rack_texts,
              'plan_rack_insert_count': sum(d['layer'] == 'W_RACK' for d in inserts)}
    dump_json('source_audit.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if '--derive-only' not in sys.argv:
        main()
    derive_specs()
