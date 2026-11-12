"""Build MPR-private rack families from measured source-CAD elevations.

Run in an isolated background Blender process. The detailed source CAD defines
envelopes and beam levels; steel wall gauge, brace gauge and packaging detail
are explicitly presentation assumptions, not manufacturing certification.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from mpr_blender_common import Geometry,PALETTE
from mpr_ghs_cargo_geometry_20261112 import add_carton,add_pallet_load,PREVIEW_PALETTE,PROVENANCE
PALETTE.update(PREVIEW_PALETTE)
OUT=ROOT/'SourceAssets/MPR/interior_cad_20261112/racks'
ROLES=['Porcelain','Cobalt','Cargo','CargoSeam','Charcoal']


def bar(g,name,role,a,b,width,depth):
    a,b=Vector(a),Vector(b)
    q=(b-a).to_track_quat('Z','Y');mid=(a+b)/2;length=(b-a).length
    vertices=[tuple(mid+q@Vector((x*width/2,y*depth/2,z*length/2)))
              for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    g.mesh(name,role,vertices,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])


def resolved_spec(specs,placement):
    family=placement['family'];wide=placement['width_inches']==192
    if family=='Unresolved':
        s=deepcopy(specs['families']['20'])
        s['beam_top_m']=[];s['beam_bottom_m']=[];s['beam_thickness_m']=[]
        s['cargo']=None;s['portal']=dict(beam_top_m=[],beam_bottom_m=[],beam_thickness_m=[],
            clear_height_m=specs['mixed_portals']['clear_height_m'],inferred=True,
            basis='Two mixed F20/F9 bays have no common measured beam levels. Only shared upright frames are represented pending an elevation.')
        s['id']='Unresolved'
    else:s=deepcopy(specs['families'][family])
    if wide:s.update({k:specs['wide_bay'][k] for k in ['outer_width_m','clear_width_m','depth_m']})
    if placement['passage_variant']:
        p=s['portal']
        s.update({k:p[k] for k in ['beam_top_m','beam_bottom_m','beam_thickness_m']})
        s.pop('ground_cargo',None)
    cargo=s.get('cargo')
    if cargo and wide:
        cargo['columns']=int((s['clear_width_m']-cargo['width_m'])/cargo['pitch_x_m']+1+1e-7)
    s['passage_variant']=placement['passage_variant'];s['width_inches']=placement['width_inches']
    return s


def make(g,name,s,lod):
    for role in (['Porcelain','Charcoal'] if s['id']=='Unresolved' else ROLES):g.data[name][role]
    w,d,h=s['outer_width_m'],s['depth_m'],s['frame_height_m']
    p=s['upright_section_m'];clear=s['clear_width_m'];skin=.005
    # Four open channel uprights: outside dimensions are source-CAD dimensions.
    for sx in (-1,1):
        x=sx*(w/2-p/2)
        for sy in (-1,1):
            y=sy*(d/2-p/2)
            if lod==0:
                g.box(name,'Porcelain',(x+sx*(p-skin)/2,y,(h+.01)/2),(skin,p,h-.01))
                for side in (-1,1):g.box(name,'Porcelain',(x-sx*skin/2,y+side*(p-skin)/2,(h+.01)/2),(p-skin,skin,h-.01))
            else:g.box(name,'Porcelain',(x,y,(h+.01)/2),(p,p,h-.01))
            g.box(name,'Charcoal',(x,y,.005),(p,p,.01))
        # Side-frame bracing never crosses the drive-through bay.
        segments=8 if lod==0 else 4
        for i in range(segments):
            za=.12+(h-.24)*i/segments;zb=.12+(h-.24)*(i+1)/segments
            ys=(-d/2+p,d/2-p) if i%2==0 else (d/2-p,-d/2+p)
            bar(g,name,'Porcelain',(x,ys[0],za),(x,ys[1],zb),.022,.012)
        for z in (.1,h-.08):g.box(name,'Porcelain',(x,0,z),(.025,d-p*2,.025))
    cargo=s.get('cargo');loads=[];fit_adjustments=[]
    for top,bottom,thickness in zip(s['beam_top_m'],s['beam_bottom_m'],s['beam_thickness_m']):
        assert abs(top-bottom-thickness)<.00001
        for sy in (-1,1):g.box(name,'Cobalt',(0,sy*(d/2-.0325),(top+bottom)/2),(clear,.065,thickness))
        # A thin bearing deck stays below the CAD beam-top/cargo datum.
        g.box(name,'Porcelain',(0,0,top-.006),(clear,d-.13,.012))
        if lod==0:
            for x in (-clear/3,0,clear/3):g.box(name,'Porcelain',(x,0,top-.025),(.035,d-.13,.05))
        if cargo:
            nearest=min(range(len(cargo['bottom_m'])),key=lambda i:abs(cargo['bottom_m'][i]-top))
            assert abs(cargo['bottom_m'][nearest]-top)<.001
            height=cargo['height_by_level_m'][nearest]
            above=[b for b in s['beam_bottom_m'] if b>top+.00001]
            if above and top+height>min(above):
                fitted=min(above)-top-.005
                fit_adjustments.append(dict(level_bottom_m=top,source_height_m=height,
                    presentation_height_m=fitted,reason='Source load envelope intersects next measured beam; preserve structural elevations and leave 5 mm clearance.'))
                height=fitted
            loads.append((top,height,cargo))
    if s.get('ground_cargo'):
        ground=s['ground_cargo'];loads.append((ground['bottom_m'],ground['height_m'],ground))
    boxes=0;visual_cartons=0
    for bottom,height,c in loads:
        rows=c.get('depth_rows',1);count=c['columns'];cw=c['width_m'];cd=c['depth_m'];pitch=c['pitch_x_m']
        pallet=s['id'] in ('5','7') or c is s.get('ground_cargo')
        ph=min(.14,height*.2) if pallet else 0
        xs=[(i-(count-1)/2)*pitch for i in range(count)]
        ys=[(i-(rows-1)/2)*cd for i in range(rows)]
        boxes+=count*rows
        if lod==2:
            # Coarse LOD retains each level and its voids; no full-height slab.
            for y in ys:
                if ph:g.box(name,'Cobalt',(0,y,bottom+ph/2),((count-1)*pitch+cw,cd,ph))
                g.box(name,'Cargo',(0,y,bottom+ph+(height-ph)/2),((count-1)*pitch+cw,cd,height-ph))
        else:
            for x in xs:
                for y in ys:
                    if cw>.75:
                        result=add_pallet_load(g,name,(x,y,bottom+height/2),(cw,cd,height),lod,pallet_height=ph)
                        visual_cartons+=result['carton_count']
                    else:
                        add_carton(g,name,(x,y,bottom+height/2),(cw,cd,height),lod)
                        visual_cartons+=1
    # Validate the actual vertices crossing the bay, not just numeric metadata.
    if s['passage_variant']:
        required=s['portal']['clear_height_m']
        crossing=[]
        for role,(vv,ff) in g.data[name].items():
            for face in ff:
                points=[vv[i] for i in face]
                if min(v[0] for v in points)<clear/2-1e-5 and max(v[0] for v in points)>-clear/2+1e-5:
                    crossing.extend(v[2] for v in points)
        if crossing:assert min(crossing)>=required-.00001,(name,min(crossing),required)
    return dict(cargo_envelopes=boxes,visual_cartons=visual_cartons if lod<2 else None,
        beam_levels=len(s['beam_top_m']),frame_dimensions_m=[w,d,h],
        measured_beam_top_m=s['beam_top_m'],measured_beam_bottom_m=s['beam_bottom_m'],
        passage_clear_height_m=s['portal']['clear_height_m'] if s['passage_variant'] else None,
        inferred_passage=s['portal']['inferred'] if s['passage_variant'] else False,
        crossing_beams_present=bool(s['beam_top_m']),presentation_fit_adjustments=fit_adjustments)


def main():
    specs=json.loads((OUT/'rack_specs.json').read_text(encoding='utf8'))
    placement=json.loads((OUT/'placement_manifest.json').read_text(encoding='utf8'))
    unique={r['mesh_name']:r for r in placement['instances']}
    g=Geometry();checks={};resolved={}
    for name,r in sorted(unique.items()):
        spec=resolved_spec(specs,r);resolved[name]=spec
        for lod in range(3):
            checks[name+('_LOD'+str(lod) if lod else '')]=make(g,name+('_LOD'+str(lod) if lod else ''),spec,lod)
    raw=g.export(OUT,'MPR_CAD_Racks',dict(source_sha256=specs['source_sha256']))
    all_meshes={r['name']:r for r in raw['meshes']};records=[]
    for name in sorted(unique):
        row=all_meshes[name];lods=[all_meshes[name+'_LOD'+str(i)] for i in (1,2)]
        row.update(checks[name],sha256=hashlib.sha256((ROOT/row['fbx']).read_bytes()).hexdigest(),
            lod_files=[r['fbx'] for r in lods],lod_triangles=[row['triangles']]+[r['triangles'] for r in lods],
            lod_screen_sizes=[1.,.18,.055],source_family=resolved[name]['id'],
            width_inches=resolved[name]['width_inches'],passage_variant=resolved[name]['passage_variant'])
        assert row['lod_triangles']==sorted(row['lod_triangles'],reverse=True)
        records.append(row)
    # Import every interchange LOD back into Blender, checking dimensions/slots.
    readbacks=[]
    for name,row in all_meshes.items():
        before=set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']))
        objects=[o for o in bpy.data.objects if o not in before and o.type=='MESH']
        assert len(objects)==1
        obj=objects[0];vv=[obj.matrix_world@v.co for v in obj.data.vertices]
        bounds=[[min(v[i] for v in vv),max(v[i] for v in vv)] for i in range(3)]
        error=max(abs(a-b) for aa,bb in zip(bounds,row['bounds_m']) for a,b in zip(aa,bb))
        assert error<.0001 and len(obj.data.materials)==len(row['material_roles'])
        readbacks.append(dict(name=name,maximum_bounds_error_m=error,slots=len(row['material_roles'])))
        bpy.data.objects.remove(obj,do_unlink=True)
    manifest=dict(schema_version=1,source_sha256=specs['source_sha256'],meshes=records,
        material_style='Existing GHS small-carton geometry rules and industrial blue/white material assets; no global material edits.',
        cargo_provenance=PROVENANCE,
        manufacturing_detail_assumptions=['5 mm channel wall, 22x12 mm side braces, 12 mm bearing deck; source only defines frame envelope.',
            'Pallet construction inside CAD load envelope is illustrative; 192-inch load column count repeats original cargo pitch.'],
        validation=dict(success=True,mesh_variants=len(records),fbx_readback=readbacks,checks=checks))
    (OUT/'mesh_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('MPR_CAD_RACKS_COMPLETE '+str(len(records)))


if __name__=='__main__':main()
