"""Plan the exact A50 asphalt faces removed with a larger road tile.

This restores one connected road strip only. The C08/DA0 pieces in the same
source mesh remain excluded, preserving the user's other scene deletions.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
from shapely.geometry import Polygon,LineString,box,mapping
from shapely.ops import unary_union
import build_mpr_crossing_surface as base

OUT=ROOT/'SourceAssets/MPR/road_gap_20261106'
NAME='SM_MPR_A50_RoadGap'
ROAD='TPX_ROADS_AXES_A50'
MOTHER='SM_MPRR_Roads_0_-3'
ROLE='MPR4_TerminalAsphalt'
DEST='/Game/MPRWarehouse/RoadGap20261106'
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
SOURCE_SHA='ce27bf4d0943167b62c57ba137a1f020c5b05b86dc6ddab0ab9b0cc5b529d849'

def read(path):return base.transport.revision.read(path)
def write(path,value):base.transport.revision.write(path,value)
def sha(path):return base.transport.revision.sha(path)

def plan():
    row=base.current_rows()[MOTHER]
    assert row['sha256']==SOURCE_SHA and sha(ROOT/row['fbx'])==SOURCE_SHA
    layout_path=base.transport.OUT/'layout.json';layout=base.transport.revision.decode(read(layout_path))
    road=next(r for r in layout['road_centerlines']if r['id']==ROAD)
    assert road['width_m']==9
    axis=LineString(road['points_m']);faces=base.read_faces(row)
    selected=[i for i,(role,p)in enumerate(faces)if Polygon(np.asarray(p)[:,:2]).centroid.distance(axis)<4.501]
    assert len(selected)==181
    polygons=[Polygon(np.asarray(faces[i][1])[:,:2])for i in selected]
    footprint=unary_union(polygons)
    assert footprint.geom_type=='Polygon'and abs(footprint.area-511.78960753284423)<1e-6
    assert footprint.difference(axis.buffer(4.501)).area<1e-7
    assert footprint.difference(layout['roads'].buffer(.0002)).area<1e-8
    for identity in ['TPX_ROADS_AXES_C08','TPX_ROADS_AXES_DA0']:
        other=LineString(next(r['points_m']for r in layout['road_centerlines']if r['id']==identity))
        assert footprint.distance(other)>25,identity
    result=dict(success=True,map=MAP,name=NAME,namespace=DEST,source_mesh=row,
        source_hashes={row['fbx']:SOURCE_SHA,layout_path.relative_to(ROOT).as_posix():sha(layout_path)},
        road_id=ROAD,selected_source_faces=selected,material_roles=[ROLE],footprint=mapping(footprint),
        area_m2=footprint.area,width_m=9,missing_centerline_length_m=axis.intersection(box(0,-450,150,-300)).length,
        diagnosis='The live scene is missing Roads_0_-3. Its A50 strip is restored without the C08/DA0 pieces.',
        expected_missing_source_package='/Game/MPRWarehouse/RebuildB50B57/Site/Meshes/'+MOTHER,
        material_reference_mesh='/Game/MPRWarehouse/TransportCleanup20261105/Meshes/SM_MPRR_Roads_-1_-3',
        expected_effective_material='/Game/MPRWarehouse/SiteComplete/Materials/MI_SC_MPR4_TerminalAsphalt',
        actor_label='MPR_A50_RoadGap_20261106',transform=dict(translation_cm=[0,0,0],rotation_xyzw=[0,0,0,1],scale=[1,1,1]),
        allowed_scene_change='Add only one StaticMeshActor for the 181-face A50 strip; keep all existing actors and absences.')
    return json.loads(json.dumps(result))

def main():
    OUT.mkdir(parents=True,exist_ok=True);p=plan();write(OUT/'plan.json',p)
    print('MPR_ROAD_GAP_PLANNED',len(p['selected_source_faces']),p['area_m2'])

if __name__=='__main__':main()
