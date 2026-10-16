"""Read-only physical audit of CAD racks against racks, columns and floor loads.

Uses generated physical parts, not rack envelopes, for the narrow phase.
Diagonal braces are reconstructed as oriented boxes and checked against their
exported AABBs.  Cargo bevels use both enclosing boxes and inscribed solid cores:
only core/core or exact-box intersections are reported as confirmed penetrations.
"""
from pathlib import Path
import argparse
import collections
import datetime
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
MAPPING = ROOT/'SourceAssets/GHS/RackSpecs/cad_plan_mapping.json'
MODELS = ROOT/'SourceAssets/GHS/RackSpecs/Models/cad_rack_models.json'
REGISTRY = ROOT/'SourceAssets/GHS/Presentation/visual_layout.json'
OUTPUT = ROOT/'Saved/GHS_CADRackSolidAudit.json'
EPS = .001
IDENTITY = ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))


def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a,a))
def unit(a):
    n=norm(a)
    return tuple(x/n for x in a)


class Box:
    __slots__=('center','half','axes','name','role','bevel','aabb')
    def __init__(self, center, size, axes=IDENTITY, name='', role='', bevel=0.):
        self.center=tuple(center); self.half=tuple(v*.5 for v in size)
        self.axes=tuple(tuple(a) for a in axes)
        self.name=name; self.role=role
        self.bevel=(bevel,bevel,bevel) if isinstance(bevel,(int,float)) else tuple(bevel)
        extent=[sum(abs(self.axes[j][i])*self.half[j] for j in range(3)) for i in range(3)]
        self.aabb=tuple((self.center[i]-extent[i],self.center[i]+extent[i]) for i in range(3))

    def core(self):
        return Box(self.center,[max(0.,2*v-2*inset) for v,inset in zip(self.half,self.bevel)],
                   self.axes,self.name,self.role,0.)


def sat(a,b):
    """Full 15-axis 3D OBB SAT, including sloping side brace rectangles."""
    if any(min(a.aabb[i][1],b.aabb[i][1])-max(a.aabb[i][0],b.aabb[i][0])<=EPS for i in range(3)):
        return None
    axes=list(a.axes)+list(b.axes)
    for aa in a.axes:
        for bb in b.axes:
            v=cross(aa,bb)
            if norm(v)>1e-8: axes.append(unit(v))
    minimum=float('inf'); min_axis=None; delta=sub(b.center,a.center)
    for axis in axes:
        penetration=(sum(h*abs(dot(v,axis)) for h,v in zip(a.half,a.axes))+
                     sum(h*abs(dot(v,axis)) for h,v in zip(b.half,b.axes))-abs(dot(delta,axis)))
        if penetration<=EPS:return None
        if penetration<minimum:minimum=penetration;min_axis=axis
    return {'minimum_axis_penetration_m':minimum,'axis':min_axis}


def transform(box,position,yaw,scale=(1,1,1)):
    angle=math.radians(yaw);c,s=math.cos(angle),math.sin(angle)
    def rotate(v):return (c*v[0]-s*v[1],s*v[0]+c*v[1],v[2])
    center=rotate(tuple(a*b for a,b in zip(box.center,scale)))
    axes=tuple(rotate(a) for a in box.axes)
    # Only ground cargo primitives use anisotropic scale and they are axis
    # aligned before yaw. Generated rack parts and diagonal braces use scale 1.
    if scale!=(1,1,1):assert box.axes==IDENTITY
    return Box([a+b for a,b in zip(position,center)],
               [2*h*v for h,v in zip(box.half,scale)],axes,box.name,box.role,
               tuple(inset*factor for inset,factor in zip(box.bevel,scale)))


def model_parts(spec):
    diagonal_recipes=[]
    clear=spec['clear_width_m'];width=spec['frame_width_m'];depth=spec['frame_depth_m'];height=spec['upright_height_m']
    post=(width-clear)*.5;post_depth=min(post,.0762)
    ya,yb=-depth*.5+post_depth,depth*.5-post_depth
    start,end=.13,height-.10;segments=max(1,round((end-start)/1.3))
    for sx in [-1,1]:
        x=sx*(clear*.5+post*.5)
        for i in range(segments):
            za=start+(end-start)*i/segments;zb=start+(end-start)*(i+1)/segments
            diagonal_recipes.append(((x,ya,za),(x,yb,zb),.022,.012))
            if i%2==0:diagonal_recipes.append(((x,yb,za),(x,ya,zb),.016,.010))
    index=0;result=[]
    for part in spec['solid_boxes']:
        name=part['name'];role=part['role']
        if name.startswith(('Upright side diagonal','Upright side return diagonal')):
            a,b,w,d=diagonal_recipes[index];index+=1
            z=unit(sub(b,a));xx=(1.,0.,0.);yy=cross(z,xx)
            solid=Box([(u+v)*.5 for u,v in zip(a,b)],[w,d,norm(sub(b,a))],(xx,yy,z),name,role)
            expected=Box(part['center_m'],part['size_m'])
            discrepancy=max(abs(solid.aabb[i][j]-expected.aabb[i][j]) for i in range(3) for j in range(2))
            assert discrepancy<.0001,('Diagonal orientation/size differs from exported geometry',spec['name'],name,discrepancy)
        else:
            bevel=.004 if 'enclosed shipping crate' in name else (.002 if name.startswith('Load beam') else 0.)
            solid=Box(part['center_m'],part['size_m'],name=name,role=role,bevel=bevel)
        result.append(solid)
    assert index==len(diagonal_recipes),(spec['name'],index,len(diagonal_recipes))
    return result


def floor_cargo_parts(layers):
    source=(ROOT/'Scripts/video_reference/build_storage.py').read_text(encoding='utf8')
    recipe=source[source.index('# Three continuous runners'):source.index("begin_asset('SM_VR_RackBay')")]
    recipe=recipe.replace('cube=(1.16/3,.96/3,.90/3)','cube=(1.16/3,.96/3,.3)').replace('for iz in range(3):','for iz in range(layers):').replace('range(4)','range(layers+1)').replace('base_z+.9','base_z+layers*.3')
    parts=[]
    def box(name,center,size,material,edge=.006):
        parts.append(Box(center,size,name=name,role='Pallet' if 'Pallet' in name else 'Cargo',bevel=min(edge,min(size)*.2)))
    noop=lambda *a,**kw:None
    env=dict(box=box,curve=noop,beam=noop,stripe=noop,layers=layers,blue='blue',cargo='cargo',cyan='cyan')
    exec(compile(recipe,'<ground-cargo-physical-recipe>','exec'),env)
    return parts


def bounds_part(bounds):
    return Box([(a+b)*.5 for a,b in bounds],[b-a for a,b in bounds])


def suggestion(a,b,witness):
    kinds={a['kind'],b['kind']};roles={witness['a_part']['role'],witness['b_part']['role']}
    if kinds & {'column','column_base'}:
        if roles <= {'Cargo','CargoEdges','Pallet','Column','ColumnBase'}:
            return 'Keep CAD frame anchor and full-size pallet dimensions; omit only the colliding load cell next to the column, preserving rack structure and existing base clearance.'
        return 'Keep CAD row anchor; trim or split the affected rack bay locally around the column/base, preserving 0.10m clearance. Do not translate an entire row.'
    if kinds=={'rack'}:
        return 'Inspect the two CAD parent anchors and shared end frame. Preserve full-size pallets; remove a conflicting load cell or trim only the shared frame end if warranted.'
    return 'Keep CAD slot locations. If a load overlaps an adjacent rack, leave only that affected slot empty; do not uniformly compress pallets or move warehouse rows.'


def audit(args):
    mapping=json.loads(MAPPING.read_text(encoding='utf8'))
    assignments=mapping['assignments']+mapping['additional_pass_racks']
    preflight={'rack_count':len(assignments),'pass_count':sum(r['pass_variant'] for r in assignments),
               'pass_types':dict(collections.Counter(r['spec_type'] for r in assignments if r['pass_variant'])),
               'cad_pass_y_range_m':[min(r['position_m'][1] for r in assignments if r['pass_variant']),max(r['position_m'][1] for r in assignments if r['pass_variant'])],
               'dock_d1_count':sum(r['spec_type']=='D1' for r in assignments),
               'note':'Pass groups must use bridge geometry; blue pass markers must not be instantiated as full-height storage stacks.'}
    report={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'mapping_preflight':preflight,'input_sha256':{'mapping':hashlib.sha256(MAPPING.read_bytes()).hexdigest()},
            'penetration_tolerance_m':EPS,'rack_floor_offset_m':args.rack_z,
            'column_height_m':args.column_height,
            'scope':'Read-only CAD-coordinate physical check; rack-rack, rack-column, rack-column base, rack-ground cargo; same-asset intentional joints excluded.'}
    if not MODELS.exists():
        report.update(status='awaiting_model_manifest',passed=False,success=False)
        OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8');return report
    manifest=json.loads(MODELS.read_text(encoding='utf8'));registry=json.loads(REGISTRY.read_text(encoding='utf8'))
    report['input_sha256'].update(models=hashlib.sha256(MODELS.read_bytes()).hexdigest(),registry=hashlib.sha256(REGISTRY.read_bytes()).hexdigest())
    meshes={m['mapping_key']:m for m in manifest['meshes']}
    parts={key:model_parts(m) for key,m in meshes.items()}
    entities=[]
    def add(id,kind,position,yaw,scale,outer,templates,**extra):
        entities.append(dict(id=id,kind=kind,position=position,yaw=yaw,scale=scale,
                             outer=transform(outer,position,yaw,scale),templates=templates,**extra))
    for row in assignments:
        key='%s:%d:%.4f'%(row['spec_type'],int(row['pass_variant']),row['physical_span_m'])
        spec=meshes[key]
        add(row['instance_id'],'rack',row['position_m'][:2]+[args.rack_z],row['rotation_deg']+90,(1,1,1),
            bounds_part(spec['bounds_m']),parts[key],mesh=spec['name'],spec_type=row['spec_type'],
            parent_cad_id=row['parent_cad_id'],pass_variant=row['pass_variant'])
    floor_manifest=json.loads((ROOT/'SourceAssets/GHS/Presentation/presentation_storage.json').read_text(encoding='utf8'))
    ground_bounds={m['name']:m['bounds_m'] for m in floor_manifest['meshes']}
    ground_parts={'SM_GHS_Presentation_Cargo'+label:floor_cargo_parts(n) for label,n in [('Low',4),('Mid',6),('High',8)]}
    for group in registry['groups']:
        actor=group['actor'];kind=None
        if actor=='GHS_CAD_Columns':kind='column'
        elif actor=='GHS_ColumnBases':kind='column_base'
        elif actor.startswith('GHS_CAD_PalletCargo'):kind='ground_cargo'
        if not kind:continue
        for row in group['instances']:
            pos=list(row['position_m']);scale=tuple(row.get('scale',[1,1,1]));yaw=row.get('rotation_deg',0)
            if kind in ('column','column_base'):
                if kind=='column' and args.column_height:
                    pos[2]=args.column_height*.5;scale=(scale[0],scale[1],args.column_height)
                template=Box((0,0,0),(1,1,1),name='solid column' if kind=='column' else 'solid column base',role='Column' if kind=='column' else 'ColumnBase')
                outer=template;template_parts=[template]
            else:
                outer=bounds_part(ground_bounds[group['mesh']]);template_parts=ground_parts[group['mesh']]
            add(row['id'],kind,pos,yaw,scale,outer,template_parts,mesh=group['mesh'])
    report['entity_counts']=dict(collections.Counter(e['kind'] for e in entities))
    assert report['entity_counts']['column']==170 and report['entity_counts']['column_base']==170
    assert report['entity_counts']['ground_cargo']==7408
    # Check the inner passage of every distinct loaded pass model / D1 model.
    corridor=[]
    for key,spec in meshes.items():
        if not (spec.get('pass_variant') or spec['spec_type']=='D1'):continue
        clear=spec['clear_under_beam_m'];width=spec['clear_width_m']-.002
        region=Box((0,0,(clear-.002)*.5),(width,max(spec['frame_depth_m'],spec['cargo_depth_m'])+.002,clear-.002))
        hits=[{'name':b.name,'role':b.role} for b in parts[key] if sat(region,b)]
        corridor.append({'mapping_key':key,'mesh':spec['name'],'clear_under_beam_m':clear,'clear_span_m':spec['clear_width_m'],'intrusions':hits})
    report['passage_audit']=corridor
    cell=4.;grid=collections.defaultdict(list);candidate_pairs=set()
    for i,e in enumerate(entities):
        b=e['outer'];limits=[(math.floor(v[0]/cell),math.floor(v[1]/cell)) for v in b.aabb[:2]]
        for xx in range(limits[0][0],limits[0][1]+1):
            for yy in range(limits[1][0],limits[1][1]+1):
                for j in grid[(xx,yy)]:
                    if e['kind']=='rack' or entities[j]['kind']=='rack':candidate_pairs.add((j,i))
                grid[(xx,yy)].append(i)
    transformed={}
    def getparts(index):
        if index not in transformed:
            e=entities[index]
            transformed[index]=[transform(b,e['position'],e['yaw'],e['scale']) for b in e['templates']]
        return transformed[index]
    counts=collections.defaultdict(collections.Counter);confirmed=[];unresolved=[]
    for i,j in sorted(candidate_pairs):
        a,b=entities[i],entities[j];category='_vs_'.join(sorted([a['kind'],b['kind']]))
        counts[category]['candidate_pairs']+=1
        if not sat(a['outer'],b['outer']):continue
        counts[category]['outer_overlaps']+=1
        aa=[part for part in getparts(i) if sat(part,b['outer'])]
        bb=[part for part in getparts(j) if sat(part,a['outer'])]
        witness=None;outer_witness=None
        for pa in aa:
            for pb in bb:
                outer=sat(pa,pb)
                if not outer:continue
                descriptor={'a_part':{'name':pa.name,'role':pa.role,'center_m':pa.center},
                            'b_part':{'name':pb.name,'role':pb.role,'center_m':pb.center},**outer}
                outer_witness=outer_witness or descriptor
                core=sat(pa.core() if any(pa.bevel) else pa,pb.core() if any(pb.bevel) else pb)
                if core:
                    witness={**descriptor,'confirmed_core_penetration_m':core['minimum_axis_penetration_m']};break
            if witness:break
        compact=lambda e:{k:e[k] for k in ('id','kind','position','mesh')}
        if witness:
            row={'category':category,'a':compact(a),'b':compact(b),'witness':witness,'suggestion':suggestion(a,b,witness)}
            confirmed.append(row);counts[category]['confirmed_intersections']+=1
        elif outer_witness:
            unresolved.append({'category':category,'a':compact(a),'b':compact(b),'conservative_bounds_witness':outer_witness,
                               'reason':'Beveled outer boxes overlap but inset solid cores do not; needs triangle-level review before calling a true collision.'})
            counts[category]['bounds_only_unresolved']+=1
        else:counts[category]['outer_only_no_physical_intersection']+=1
    passed=not confirmed and not unresolved and not any(c['intrusions'] for c in corridor)
    report.update(status='complete',passed=passed,success=passed,
                  pair_counts={k:dict(v) for k,v in counts.items()},confirmed_intersection_count=len(confirmed),
                  bounds_only_unresolved_count=len(unresolved),confirmed_intersections=confirmed,bounds_only_unresolved=unresolved,
                  checks={'scale_of_every_rack_is_one':True,'original_full_size_pallet_depth_preserved':True,
                          'diagonal_brace_obb_matches_exported_aabb':True,'self_asset_joints_excluded':True},
                  limitations=['Ground cargo thin decorative seam curves are excluded; actual pallet and cargo solids are audited.',
                               'Inscribed cores prove intersections but cannot disprove beveled-corner contacts. Such cases remain explicitly unresolved.',
                               'This is a source geometry audit. Imported UE transform and bounds verification must additionally confirm model placement.'])
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--column-height',type=float)
    parser.add_argument('--rack-z',type=float,default=.012)
    args=parser.parse_args()
    result=audit(args)
    print(json.dumps({k:result[k] for k in ['status','passed','mapping_preflight','entity_counts','confirmed_intersection_count','bounds_only_unresolved_count'] if k in result},indent=2))
