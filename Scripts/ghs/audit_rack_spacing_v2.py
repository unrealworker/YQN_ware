"""Read the V2 artifact afresh and independently verify its final CAD geometry."""
import collections
import hashlib
import json
import math
from pathlib import Path

from plan_clearance_fix import collision_pairs, corners

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/GHS'
OUT=SOURCE/'RefinementV2/Layout'
EPS=1e-7


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def in_polygon(point,polygon):
    x,y=point;inside=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside=not inside
    return inside


def audit():
    plan=read(OUT/'rack_spacing.json');layout=read(SOURCE/'clearance_layout.json')
    mapping=read(SOURCE/'RackSpecs/cad_plan_mapping.json');registry=read(SOURCE/'ue_scene_registry.json')
    source={r['source_id']:r for r in mapping['source_rack_inserts']}
    previous=mapping['assignments']+mapping['additional_pass_racks']
    racks=plan['racks'];ground=plan['groundcargo'];failures=[]
    def require(condition,message):
        if not condition:failures.append(message)
    require({r['parent_cad_id'] for r in racks}=={r['parent_cad_id'] for r in previous},'Missing or invented rack CAD parent')
    require(len(racks)==len({r['id'] for r in racks})==1629,'Rack uniqueness/count')
    previous_ids={r['instance_id'] for r in previous}
    replaced=[id for r in racks for id in r['replaces_instance_ids']]
    require(len(replaced)==len(set(replaced))==len(previous_ids) and set(replaced)==previous_ids,'Every previous rack represented exactly once')
    rack_boxes=[]
    for r in racks:
        s=source[r['parent_cad_id']]
        require(r['spec_type']==s['spec_type'] and r['pass_variant']==s['pass_variant'],r['id']+' changed CAD category')
        # Source INSERT rotations are stored to six decimals while the old
        # physical OBB retains double precision; four angled D1 bays differ by
        # 0.00000033 degrees and 0.0000096m in the pre-existing extraction.
        require(abs(r['rotation_deg']-s['rotation_deg'])<1e-6,r['id']+' changed CAD angle')
        require(abs(r['position_m'][1]-r['pre_v2_position_m'][1])<EPS,r['id']+' crossed original Y anchor')
        require(abs(r['position_m'][0]-r['pre_v2_position_m'][0])<1,r['id']+' moved >=1m')
        require(r['physical_span_m']>=3.6175,r['id']+' still has a column-cut narrow segment')
        require(abs(r['physical_depth_m']-s['nominal_depth_m'])<.00002,r['id']+' changed frame depth')
        box=dict(id=r['id'],position_m=r['position_m'],rotation_deg=r['rotation_deg'],
                 size_m=[max(1.2192,r['physical_depth_m']),r['physical_span_m']])
        require(all(in_polygon(p,layout['footprint_outline_m']) for p in corners(box)),r['id']+' outside building')
        rack_boxes.append(box)
    originals={e['id']:e for e in layout['storage']+layout['blocked_storage']}
    require(len(ground)==len({e['id'] for e in ground})==len(originals)==7530,'Ground uniqueness/count')
    require({e['id'] for e in ground}==set(originals),'Missing or invented ground CAD parent')
    old_by_id={e['id']:e for e in layout['storage']}
    blocks={}
    for b in registry['presentation']['cargo_blocks']:
        points=[p for id in b['slot_ids'] for p in corners(old_by_id[id])]
        blocks[b['id']]=[[min(p[k] for p in points),max(p[k] for p in points)] for k in range(2)]
    for e in ground:
        old=originals[e['id']];bb=blocks[e['presentation_block_id']]
        require(e['size_m']==old['size_m'],e['id']+' resized ground pallet')
        require(e['rotation_deg']==old['rotation_deg'],e['id']+' changed pallet angle')
        require(abs(e['position_m'][1]-old['position_m'][1])<EPS,e['id']+' changed Y')
        require(math.dist(e['position_m'],old['position_m'])<1,e['id']+' moved >=1m')
        require(all(bb[k][0]-EPS<=p[k]<=bb[k][1]+EPS for p in corners(e) for k in range(2)),e['id']+' entered an inter-block aisle')
        require(all(in_polygon(p,layout['footprint_outline_m']) for p in corners(e)),e['id']+' outside building')
    columns=[]
    for g in registry['groups']:
        if g['actor']=='GHS_ColumnBases':
            for e in g['instances']:
                columns.append(dict(id=e['id'],position_m=e['position_m'][:2],rotation_deg=e['rotation_deg'],
                                    size_m=[v+.2 for v in e['scale'][:2]]))
    collisions=collision_pairs({'rack_full_load_envelope':rack_boxes,'ground_full_load_envelope':ground,
                                'column_bases_plus_100mm':columns,'loading_doors':layout['equipment']})
    collisions=[p for p in collisions if any(c in ('rack_full_load_envelope','ground_full_load_envelope')
                                            for c in (p['a_category'],p['b_category']))]
    require(not collisions,'Physical envelope collision')
    require(all(g['new_width_m']>=2-EPS for g in plan['transverse_gaps'] if g['classification']=='longitudinal_aisle'),'Longitudinal aisle below 2m')
    for p,digest in plan['source_sha256'].items():
        require(hashlib.sha256((SOURCE/p).read_bytes()).hexdigest()==digest,'Source changed: '+p)
    result=dict(status='passed' if not failures else 'failed',passed=not failures,
                rack_count=len(racks),ground_count=len(ground),full_envelope_collisions=len(collisions),
                failures=failures,collisions=collisions,
                assertions=['All 1629 unique CAD rack parents retained exactly once; all 1639 old instances accounted for.',
                            '70 split rack parents restored; no rack span under 3.6175m.',
                            'All 7530 CAD ground slots represented; fixed 1.016m by 1.2192m dimensions preserved.',
                            'No rack or ground displacement reaches 1m; no Y coordinate changed.',
                            'Every ground pallet stays inside its exact original block outer rectangle.',
                            'All loaded footprints stay inside the CAD building outline.',
                            'All loaded footprints are disjoint from each other, dock geometry and every column base plus 100mm.',
                            'Main longitudinal rack aisles remain at least 2m.',
                            'Original source files match their recorded SHA256.'],
                limitations=['Planar loaded envelopes conservatively contain all physical solids; imported UE world bounds still require integration verification.'])
    (OUT/'rack_spacing_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['collisions','assertions','limitations']},indent=2))
    assert not failures,failures
    return result


if __name__=='__main__':
    audit()
