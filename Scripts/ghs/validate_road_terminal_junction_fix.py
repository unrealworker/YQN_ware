"""Read-only source receipt validation; does not prove the UE map was imported."""
from pathlib import Path
import hashlib
import json

from context_road_ends import classify_context_road_ends

ROOT=Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scoped_repair(root=ROOT):
    path=root/'SourceAssets/GHS/RoadTerminalFade/road_terminal_junction_fix.json'
    assert path.is_file(),'Legacy context includes internal junction tails; scoped repair receipt is missing'
    patch=read(path)
    assert patch['success'] and patch['original_assets_unchanged']
    assert patch['islands_preserved'] and patch['traffic_routes_unchanged']
    assert patch['existing_retained_face_coordinates_and_vertex_colors_exact']
    routes=read(root/'SourceAssets/GHS/Traffic/routes.json')
    cad=read(root/'SourceAssets/GHS/Park/cad_layout.json')
    classification=classify_context_road_ends(routes['roads'],cad['roads'])
    identity=lambda rows:{(r['road_id'],r['side']) for r in rows}
    assert identity(patch['remaining_external_endpoints'])==identity(classification['external'])
    assert identity(patch['removed_internal_endpoints'])==identity(classification['internal'])
    assert len(classification['external'])==6 and len(classification['internal'])==2
    assert {row['role'] for row in patch['meshes']}=={'ContextRoads','Curbs','Markings','Landscape'}
    for row in patch['meshes']:
        asset=(root/row['fbx']).resolve()
        assert asset.is_relative_to((root/'SourceAssets/GHS/RoadTerminalFade').resolve())
        assert sha(asset)==row['sha256'],row['fbx']
        assert row['source_faces']==row['retained_faces']+row['removed_faces']
        assert row['removed_faces']==len(row['removed_source_face_indices'])>0
        assert row['retained_face_coordinates_and_vertex_colors_exact']
        assert row['edge_fade_range']==[0.,1.]
    assert sha(root/patch['blend'])==patch['blend_sha256']
    protected=patch['protected_source_sha256']
    required={'SourceAssets/GHS/ContextTransition/GHS_ContextTransition.blend',
              'SourceAssets/GHS/ContextTransition/context_transition.json',
              'SourceAssets/GHS/Park/site_geometry_report.json',
              'SourceAssets/GHS/Traffic/routes.json','Content/GHSTwinUI/data/campus-traffic-routes.json'}
    assert required<=set(protected)
    for name,value in protected.items():
        assert sha(root/name)==value,('Protected source changed',name)
    return dict(success=True,source_only=True,ue_import_not_verified=True,
                active_endpoints=classification['external'],
                removed_internal_endpoints=classification['internal'],
                legacy_context_manifest='preserved source only; use scoped repaired meshes',
                protected_sources=len(protected),mesh_count=len(patch['meshes']),
                islands_and_routes_unchanged=True)


if __name__=='__main__':
    print(json.dumps(validate_scoped_repair(),indent=2))
