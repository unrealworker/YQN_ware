"""Audit MPR's central distribution plan without editing any UE asset or map.

CAD supplies XY, personnel symbols, interfaces and machine footprints. Height,
transfer speed and the kinematics between drawn poses remain simulation choices.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
from PIL import Image, ImageDraw, ImageFont

SOURCE = Path('D:/Data/仓库数据/MPR/平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
OUT = ROOT / 'SourceAssets/MPR/sorter_simulation/central_distribution'
ORIGIN = (12800., 8000.)


def cad(p):
    return [(float(p[i])-ORIGIN[i])*.0254 for i in range(2)]


def ue(p):
    return [round(p[0]*100, 6), round(-p[1]*100, 6), 0.]


def rounded(v):
    if isinstance(v, float):
        return round(v, 8)
    if isinstance(v, list):
        return [rounded(x) for x in v]
    if isinstance(v, dict):
        return {k: rounded(x) for k, x in v.items()}
    return v


def source_hash():
    with SOURCE.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def refresh_source_edges(snapshot):
    """Re-read the recorded handles directly; avoid flattening half a million entities."""
    sys.path.insert(0, str(ROOT/'Scripts/_vendor/cad'))
    import ezdxf
    from ezdxf import bbox
    doc = ezdxf.readfile(SOURCE)
    root = doc.entitydb['2C9A89']
    assert root.dxf.name == '14234123'
    matrix = root.matrix44()
    for row in snapshot['segments']:
        e = doc.entitydb[row['handle']]
        assert e.dxftype() == 'LINE'
        row['points_cad_m'] = [cad(v) for v in matrix.transform_vertices([e.dxf.start, e.dxf.end])]
    other = doc.entitydb['2C9AE5']
    cache = bbox.Cache()
    for row in snapshot['central120_children']:
        e = doc.entitydb[row['handle']]
        assert e.dxf.name == row['block']
        bb = bbox.extents([e], cache=cache)
        p = [cad(v) for v in other.matrix44().transform_vertices(bb.rect_vertices())]
        row['bounds_cad_m'] = [[min(v[k] for v in p) for k in range(2)],
                               [max(v[k] for v in p) for k in range(2)]]
    snapshot['source_sha256'] = source_hash()
    (OUT/'source_edges.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_edges = json.loads((OUT/'source_edges.json').read_text(encoding='utf8'))
    assert source_hash() == source_edges['source_sha256'], 'Original CAD changed; repeat full placement audit before using cached personnel and sorter metadata.'
    if '--refresh-source' in sys.argv:
        refresh_source_edges(source_edges)
    extracted = json.loads((ROOT/'SourceAssets/MPR/mpr_cad_extracted.json').read_text(encoding='utf8'))
    metadata = {r['source_handles'][0]: r for r in extracted['all_insert_groups']}
    machines = json.loads((ROOT/'SourceAssets/MPR/equipment/sorter_instances.json').read_text(encoding='utf8'))['instances']
    segments = source_edges['segments']
    by_handle = {r['handle']: r for r in segments}
    # Explicit source edges, rather than the rounded legacy straight-roller centre.
    x0 = by_handle['EB739']['points_cad_m'][0][0]
    x1 = by_handle['EB75B']['points_cad_m'][0][0]
    y0 = min(v[1] for v in by_handle['E1D14']['points_cad_m'])
    y1 = max(v[1] for v in by_handle['EB84D']['points_cad_m'])
    cx = (x0+x1)/2
    straight = [[x0,y0],[x1,y1]]
    personnel = []
    # These are separate people INSERTs. The six mechanical loading tables are
    # flattened inside 2C9A89 and are not themselves people.
    table_y = [2.82198585299,1.22198585299,-.37801414701,-25.62801414701,-27.22801414701,-28.82801414701]
    worker_handles = ['2CCF63','2CCF64','2CCF65','2CCF69','2CCF67','2CCF68']
    source_pairs = [('920CF','9213C'),('920CF','9213C'),('920CF','9213C'),('92032','921DE'),('92032','921DE'),('92032','921DE')]
    for i,h in enumerate(worker_handles):
        assert metadata[h]['block'] == 'terwrq434'
        # Exact original personnel INSERT identity and world bounds from the
        # existing source extraction; parent source hash is checked above.
        lo=cad(metadata[h]['bounds_dxf'][0]); hi=cad(metadata[h]['bounds_dxf'][1])
        p=[(lo[k]+hi[k])/2 for k in range(2)]
        assert math.dist(p,metadata[h]['position_m']) < .01
        north=i<3; tx0,tx1=(-106.158235362645,-105.184235362645) if north else (-103.495735362645,-102.521735362645)
        cy=table_y[i]
        personnel.append({'id':'feed_operator_'+str(i+1),'source_handle':h,'source_block':metadata[h]['block'],
            'classification':'personnel_symbol_not_equipment','position_cad_m':p,'position_ue_cm':ue(p),
            'symbol_bounds_cad_m':[lo,hi], 'cad_insert_rotation_deg':metadata[h]['rotation_deg'],
            'facing_ue_yaw_deg':0 if north else 180,
            'facing_basis':'Face the adjacent loading console toward central distributor; raw CAD person symbol has a bent working pose.',
            'feed_table':{'source_parent_handle':'2C9A89','reference_surface_line_handles':list(source_pairs[i]),
                'reference_surface_repetition_offset_cad_m':[0,0 if i in (0,3) else (-1.6*(i%3))],
                'plan_bounds_cad_m':[[tx0,cy-.292],[tx1,cy+.292]],
                'bounds_basis':'Simplified working envelope from measured surface and frame edges; not a new vendor dimensional drawing.',
                'surface_center_cad_m':[(tx0+tx1)/2,cy],
                'entry_to_central_cad_m':[x0 if north else x1,cy],
                'surface_height_cm':100,'height_basis':'display assumption; original is a 2D plan'}})
    # Receiver mouths have a real transverse CAD edge about 523 mm wide. Keep
    # both parallel mouths in evidence. The primary is nearest the existing
    # machine centreline; a new short linking surface fills the CAD separation.
    links=[]
    for m in machines['SM_MPR_SorterCAD64']:
        mx,my=m['position_m'][:2]; west=mx<cx
        inner=m['cad_bounds_m'][1 if west else 0][0]
        candidates=[]
        for r in segments:
            a,b=r['points_cad_m']; dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1])
            if dx<1e-6 and abs(a[0]-inner)<.004 and .52<dy<.53 and abs((a[1]+b[1])/2-my)<1.:
                candidates.append(r)
        assert len(candidates)==2,(m['id'],len(candidates))
        candidates.sort(key=lambda r:abs(sum(p[1] for p in r['points_cad_m'])/2-my))
        mouth=candidates[0]; a,b=mouth['points_cad_m']; yy=(a[1]+b[1])/2
        start=[x0 if west else x1,yy];end=[a[0],yy]
        links.append({'machine_id':m['id'],'source_parent_handle':'2C9A89',
            'machine_center_cad_m':[mx,my],'machine_bounds_cad_m':m['cad_bounds_m'],
            'receiver_mouth_source_handle':mouth['handle'],'receiver_mouth_segment_cad_m':mouth['points_cad_m'],
            'receiver_mouth_width_m':abs(a[1]-b[1]),
            'second_receiver_mouth':candidates[1],
            'central_edge_cad_m':start,'machine_edge_cad_m':end,
            'central_edge_ue_cm':ue(start),'machine_edge_ue_cm':ue(end),
            'gap_length_m':math.dist(start,end),'recommended_link_width_m':abs(a[1]-b[1]),
            'link_evidence':'Endpoints and mouth width measured from CAD. The continuous fixed bridging surface is a simulation completion requested by user, not an independently drawn original fixed belt.',
            'height_basis':'Interface height follows existing machine conveyor; 2D CAD does not certify Z.'})
    print('WORKERS_LINKS',len(personnel),len(links),flush=True)
    four_children=source_edges['central120_children']
    four_mid = next(r['bounds_cad_m'] for r in four_children if r['handle']=='115C22')
    four_cx = (four_mid[0][0]+four_mid[1][0])/2
    four_hardware = [r['bounds_cad_m'] for r in four_children if r['classification']=='central_distribution_hardware']
    four_bounds = [[min(b[0][k] for b in four_hardware) for k in range(2)],
                   [max(b[1][k] for b in four_hardware) for k in range(2)]]
    data={'schema_version':1,'source':str(SOURCE),'source_sha256':source_edges['source_sha256'],
        'coordinate_system':{'cad_origin_dxf':list(ORIGIN),'dxf_to_m':.0254,'ue_cm':'[cad_x*100, -cad_y*100, z]; XY only, z is an explicit display assumption'},
        'correction':'Six manual feeding stations at the two ends feed a common central distribution assembly serving eighteen sorters. Do not spawn one feeding person per sorter.',
        'central64':{'source_handle':'2C9A89','source_block':'14234123','total_flat_entities':source_edges['source_flat_entity_count'],
            'center_x_cad_m':cx,'straight_frame_bounds_cad_m':straight,
            'straight_frame_bounds_ue_cm':[ue(straight[0]),ue(straight[1])],
            'frame_width_m':x1-x0,'straight_length_m':y1-y0,
            'source_edge_handles':['EB739','EB75B','E1D14','EB84D'],
            'guide_inner_edges_x_cad_m':[-104.872985362645,-103.806985362645],
            'kinematic_evidence':'Plan shows parallel guide/return paths, curved return ends and transverse distributor assemblies at drawn poses. Static CAD alone does not establish carriage speed, height or routing firmware.',
            'workers':personnel,'machine_links':links},
        'central120':{'source_handle':'2C9AE5','source_block':'480','children':four_children,
            'guide_center_x_cad_m':four_cx,'guide_center_x_ue_cm':four_cx*100,
            'middle_module_width_m':four_mid[1][0]-four_mid[0][0],
            'whole_distribution_hardware_bounds_cad_m':four_bounds,
            'machine_count':4,'visible_personnel_symbols_in_block':0,
            'mechanism':'Independent central closed-return distributor with four lateral sorter interfaces.',
            'personnel_policy':'No per-machine workers. Upstream system entry may supply simulated parcels, explicitly labeled as an assumption.'},
        'legacy_straight_roller_replacement':{
            'mesh_asset':'/Game/MPRWarehouse/Operations/Meshes/SM_MPR_Conveyor2m',
            'candidate_actor_labels':['MPR_SM_MPR_Conveyor2m_-2_-1','MPR_SM_MPR_Conveyor2m_-2_0'],
            'matching_instances_ue_cm':[[-10430.,-(-30.10301+1.9*i)*100,0] for i in range(19)]+[[-11152.,-(13.12737+1.62*i)*100,0] for i in range(5)],
            'count':24,'policy':'Match mesh and world instance XY (1 cm tolerance), cache original transforms, transiently hide only these 24 instances. Never hide their entire HISM actor or overwrite a user-edited map.'},
        'validation':{'six_personnel_symbols':len(personnel)==6,'eighteen_receiver_mouths':len(links)==18,'four_secondary_sorters':sum(c['classification']=='sorter' for c in four_children)==4}}
    assert all(data['validation'].values())
    (OUT/'cad_layout.json').write_text(json.dumps(rounded(data),ensure_ascii=False,indent=2),encoding='utf8')
    # Review figure: actual source LINE vectors for the central system plus the
    # measured source symbol positions. Blue = original CAD; orange = new links.
    im=Image.new('RGB',(1500,2450),'#f7fafc');d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    box=[-113.,-33.,-95.5,7.];s=55
    def q(p):return (150+(p[0]-box[0])*s,2300-(p[1]-box[1])*s)
    d.rectangle([q([x0,y1]),q([x1,y0])],fill='#e1eaf0',outline='#3e698a',width=3)
    for gx in data['central64']['guide_inner_edges_x_cad_m']:
        d.line([q([gx,y0]),q([gx,y1])],fill='#3e698a',width=2)
    d.text(q([x1+.15,y1+.5]),'2C9A89',font=small,fill='#173247')
    for m in machines['SM_MPR_SorterCAD64']:
        lo,hi=m['cad_bounds_m']; a=q([lo[0],hi[1]]);b=q([hi[0],lo[1]]);d.rectangle([a,b],outline='#7b93a6',width=2)
    for r in segments:
        a,b=r['points_cad_m'];d.line([q(a),q(b)],fill='#7b93a6',width=1)
    for link in links:d.line([q(link['central_edge_cad_m']),q(link['machine_edge_cad_m'])],fill='#f07826',width=5)
    for i,w in enumerate(personnel):
        lo,hi=w['feed_table']['plan_bounds_cad_m']
        d.rectangle([q([lo[0],hi[1]]),q([hi[0],lo[1]])],fill='#a6dacb',outline='#058866',width=2)
        p=q(w['position_cad_m']);d.ellipse((p[0]-8,p[1]-8,p[0]+8,p[1]+8),fill='#058866')
        off=-105 if i<3 else 18;d.text((p[0]+off,p[1]-9),w['source_handle'],font=small,fill='#075943')
    d.text((70,25),'MPR 中央传送投放装置：原 CAD 坐标审计',font=font,fill='#173247')
    d.text((70,65),'绿色：6 个独立人员块（两端各 3 人）   橙色：按接口补全的连接面',font=font,fill='#173247')
    d.text((70,105),'中央装置与 18 台播种机保留 CAD 原位置；高度与运动节拍属于仿真参数。',font=font,fill='#173247')
    im.save(OUT/'cad_layout_review.png')
    print(json.dumps({'output':str(OUT),'workers':len(personnel),'links':len(links),'center_x_m':cx,'validation':data['validation']},ensure_ascii=False))

if __name__=='__main__':
    main()
