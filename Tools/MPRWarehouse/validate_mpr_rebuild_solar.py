"""Independent solar geometry validation; ordinary Python, never native Blender.

Default validates the prepared payload. --fbx also reads all fifteen exported
binary FBX meshes and verifies their physical PV masks against the saved plan.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Saved/ParkRefinement/python_deps'),str(ROOT/'Tools/MPRWarehouse')]
from shapely.geometry import Polygon,box,shape
from shapely.ops import unary_union
OUT=ROOT/'SourceAssets/MPR/rebuild_b50b57/solar'
ROLES=['MPR4_SolarFrame','MPR4_SolarCells','MPR4_SolarMid','MPR4_SolarFar']
BANKS=['00_0','01_0','01_1','02_0','02_1']
TOP=13.64
REPORT=dict(success=False,old_assets_modified=False,banks=[],meshes=[])


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fbx_groups(row):
    from validate_mpr_rebuild_surface_clearance import fbx_nodes
    path=(ROOT/row['fbx']).resolve()
    assert path.is_relative_to(OUT.resolve())and sha(path)==row['sha256']
    objects=next(n for n in fbx_nodes(path)if n[0]==b'Objects')
    geometry=[n for n in objects[2]if n[0]==b'Geometry'];assert len(geometry)==1
    fields={n[0]:n for n in geometry[0][2]}
    raw=list(fields[b'Vertices'][1][0]);vertices=list(zip(raw[::3],raw[1::3],raw[2::3]));faces=[];current=[]
    for index in fields[b'PolygonVertexIndex'][1][0]:
        current.append(index if index>=0 else -index-1)
        if index<0:faces.append(current);current=[]
    assert not current
    layer={n[0]:n[1][0]for n in fields[b'LayerElementMaterial'][2]}
    assert layer[b'MappingInformationType']==b'ByPolygon'
    material_indices=list(layer[b'Materials']);assert len(material_indices)==len(faces)
    groups={role:[vertices,[],[]]for role in row['material_roles']}
    for face,index in zip(faces,material_indices):
        assert 0<=index<len(row['material_roles'])
        groups[row['material_roles'][index]][1].append(face)
    return groups


def mesh_mask(groups,role):
    assert set(groups)=={ROLES[0],role}
    faces=[];triangles=0;all_vertices=[]
    for material,(vertices,polygons,uv)in groups.items():
        assert all(math.isfinite(x)for vertex in vertices for x in vertex)
        assert all(13.4139<=v[2]<=13.6601 for v in vertices), 'Solar outside its existing height interval'
        all_vertices.extend(vertices)
        for polygon in polygons:
            assert len(polygon)>=3 and all(0<=i<len(vertices)for i in polygon)
            triangles+=len(polygon)-2
            if material==role:
                assert all(abs(vertices[i][2]-TOP)<.0001 for i in polygon)
                p=Polygon([vertices[i][:2]for i in polygon]);assert p.is_valid and p.area>1e-8
                faces.append(p)
    mask=unary_union(faces)
    assert abs(sum(p.area for p in faces)-mask.area)<1e-5, 'Duplicate/coplanar cell surfaces'
    return mask,triangles


def run(with_fbx):
    layout=read(OUT/'layout.json');previous=read(OUT/'inputs/previous_architecture.json')
    cad=read(OUT/'inputs/cad_layout.json');roof=Polygon(cad['footprint_outline_m'])
    with gzip.open(OUT/'geometry_payload.json.gz','rt',encoding='utf8')as stream:payload=json.load(stream)
    assert payload['layout_sha256']==sha(OUT/'layout.json')
    for name,h in layout['input_hashes'].items():assert sha(OUT/'inputs'/name)==h
    originals={'previous_plan.json':ROOT/'SourceAssets/MPR/reference_v4/architecture/plan_solar_v5.json',
        'previous_architecture.json':ROOT/'SourceAssets/MPR/reference_v4/architecture/reference_shell_manifest.json',
        'cad_layout.json':ROOT/'SourceAssets/MPR/mpr_cad_layout.json'}
    for name,path in originals.items():assert sha(path)==layout['input_hashes'][name], ('Original changed',name)
    devices=[]
    for name,rows in previous['instances'].items():
        if name not in {'SM_MPR4_RoofLight','SM_MPR4_RoofHVAC'}:continue
        hx,hy=(.925,.675)if 'RoofLight'in name else (1.15,.925)
        for index,row in enumerate(rows):
            x,y,z=row['position_m'];sx,sy,sz=row['scale'];devices.append(dict(id=f'{name}:{index}',position_m=row['position_m'],
                scale=row['scale'],bounds_m=[x-hx*sx,y-hy*sy,x+hx*sx,y+hy*sy]))
    assert layout['devices_unchanged']==devices and len(devices)==195
    solid=unary_union([box(*r['bounds_m'])for r in devices]);clear=solid.buffer(.85,join_style=2)
    plan=shape(layout['geometry']);aisles=shape(layout['service_aisles'])
    assert len(layout['fields'])==16 and len({r['id']for r in layout['fields']})==16
    assert set(layout['blocks'])==set(BANKS)
    assert plan.intersection(clear).area<1e-7 and plan.intersection(aisles).area<1e-7
    assert plan.difference(roof.buffer(-2.,join_style=2)).area<1e-7
    mask=unary_union([shape(r['geometry'])for r in layout['fields']])
    assert mask.symmetric_difference(plan).area<1e-6
    assert all(r['module_cells']>=24 for r in layout['fields'])
    expected_names={f'SM_MPRR_SolarBank_{b}'+(f'_LOD{l}'if l else '')for b in BANKS for l in range(3)}
    assert set(payload['geometry'])==expected_names
    all_base=[];payload_triangles={}
    for bank in BANKS:
        expected=unary_union([box(*r['bounds_m'])for r in layout['blocks'][bank]])
        lods=[];counts=[]
        for lod,role in enumerate(ROLES[1:]):
            name='SM_MPRR_SolarBank_'+bank+(f'_LOD{lod}'if lod else '')
            area,triangles=mesh_mask(payload['geometry'][name],role)
            assert area.symmetric_difference(expected).area<1e-7,(name,'Payload footprint mismatch')
            # Physical module UVs share the same phase at every mesh partition.
            vertices,faces,uvs=payload['geometry'][name][role]
            period=layout['pitch_m']if lod<2 else [8.,8.]
            assert len(uvs)==len(faces)
            for face,uv in zip(faces,uvs):
                for vertex,index in zip(uv,face):
                    actual=vertices[index]
                    assert max(abs(vertex[j]-(actual[j]-layout['uv_origin_m'][j])/period[j])for j in (0,1))<1e-8
            lods.append(area);counts.append(triangles);payload_triangles[name]=triangles
            REPORT['meshes'].append(dict(name=name,triangles=triangles,top_area_m2=area.area,uv_phase_valid=True))
        assert all(lods[0].symmetric_difference(g).area<1e-7 for g in lods[1:])
        all_base.append(lods[0]);REPORT['banks'].append(dict(bank=bank,lod_triangles=counts,lod_top_area_m2=[g.area for g in lods],same_mask=True))
    union=unary_union(all_base)
    assert abs(sum(g.area for g in all_base)-union.area)<1e-6, 'Overlapping bank top surfaces'
    assert union.symmetric_difference(plan).area<1e-6
    if with_fbx:
        manifest=read(OUT/'manifest.json');native=read(OUT/'blender_validation.json')
        assert native['success']and native['manifest_sha256']==sha(OUT/'manifest.json')
        assert sha(ROOT/manifest['blend'])==native['blend_sha256']==manifest['blend_sha256']
        assert manifest['layout_sha256']==sha(OUT/'layout.json')and manifest['geometry_payload_sha256']==sha(OUT/'geometry_payload.json.gz')
        assert len(manifest['meshes'])==5 and len(manifest['export_meshes'])==15
        actual_masks={}
        for row in manifest['export_meshes']:
            name=row['name'];lod=1 if name.endswith('_LOD1')else 2 if name.endswith('_LOD2')else 0
            actual,triangles=mesh_mask(fbx_groups(row),ROLES[lod+1])
            expected,_=mesh_mask(payload['geometry'][name],ROLES[lod+1])
            error=actual.hausdorff_distance(expected);delta=actual.symmetric_difference(expected).area
            assert triangles==payload_triangles[name]==row['triangles']
            assert error<.0001 and delta<.15,(name,'Exported mask differs',error,delta)
            actual_masks[name]=actual
        for bank in BANKS:
            name='SM_MPRR_SolarBank_'+bank
            assert all(actual_masks[name].symmetric_difference(actual_masks[name+f'_LOD{lod}']).area<1e-7 for lod in (1,2))
        REPORT['fbx_checks']=dict(meshes=15,all_lod_masks_equal=True,manifest_sha256=sha(OUT/'manifest.json'),
            blend_sha256=manifest['blend_sha256'],native_roundtrip_passed=True)
    REPORT.update(success=True,layout_sha256=sha(OUT/'layout.json'),payload_sha256=sha(OUT/'geometry_payload.json.gz'),
        input_hashes=layout['input_hashes'],devices_fixed=195,minimum_device_clearance_m=plan.distance(solid),
        region_count=16,render_banks=5,geometry_meshes=15,module_cells=layout['module_cells'],
        near_triangles=sum(r['lod_triangles'][0]for r in REPORT['banks']),
        intermediate_triangles=sum(r['lod_triangles'][1]for r in REPORT['banks']),far_triangles=sum(r['lod_triangles'][2]for r in REPORT['banks']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fbx',action='store_true');args=parser.parse_args()
    try:run(args.fbx)
    except Exception:REPORT['error']=traceback.format_exc();print(REPORT['error'])
    name='source_fbx_validation.json'if args.fbx else 'source_geometry_validation.json'
    (OUT/name).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in REPORT.items()if k not in {'meshes','banks','input_hashes'}},indent=2))
    raise SystemExit(0 if REPORT['success']else 1)
