"""Fresh-UE validation of 170 closed, contained, twelve-edge column outlines."""
from collections import defaultdict
from datetime import datetime, timezone
import itertools
import json
import math
from pathlib import Path
import sys
import traceback

import unreal

ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import verify_ue_scene as common
import verify_clearance_scene as clearance
import verify_joined_walls as joined

REPORT_PATH=ROOT/'Saved/GHS_ColumnOutlinesVerification.json'
GROUP='GHS_ColumnEdgeOutlines'
EDGE_WIDTH_M=.012
TOLERANCE_M=.0002


def expected_edges(width,depth,height,edge=EDGE_WIDTH_M):
    """Construct disjoint boxes that partition the twelve original cube edges."""
    assert min(width,depth,height)>2*edge
    result=[]
    for sign_z in [-1,1]:
        z=sign_z*(height-edge)/2
        for sign in [-1,1]:
            result.append(((0,sign*(depth-edge)/2,z),(width/2,edge/2,edge/2),'horizontal_x'))
            result.append(((sign*(width-edge)/2,0,z),(edge/2,(depth-2*edge)/2,edge/2),'horizontal_y'))
    for sign_x,sign_y in itertools.product([-1,1],repeat=2):
        result.append(((sign_x*(width-edge)/2,sign_y*(depth-edge)/2,0),
                       (edge/2,edge/2,(height-2*edge)/2),'vertical'))
    return result


def box_in_column_frame(outline,column):
    """Inverse translation/yaw only, retaining physical metre dimensions."""
    column_z=(column.zmin+column.zmax)/2
    points=[]
    for x,y in outline.corners:
        dx,dy=x-column.x,y-column.y
        px=dx*column.co+dy*column.si
        py=-dx*column.si+dy*column.co
        for z in [outline.zmin,outline.zmax]:
            points.append((px,py,z-column_z))
    lo=[min(p[i] for p in points) for i in range(3)]
    hi=[max(p[i] for p in points) for i in range(3)]
    # All corners must be corners of the local axis-aligned box; this rejects
    # a rotated diagonal sliver whose AABB might accidentally match an edge.
    assert all(min(abs(p[i]-lo[i]),abs(p[i]-hi[i]))<=TOLERANCE_M
               for p in points for i in range(3)), 'Outline rotated away from column axes'
    return tuple((a+b)/2 for a,b in zip(lo,hi)),tuple((b-a)/2 for a,b in zip(lo,hi)),points


def local_positive_overlap(a,b):
    center_a,half_a=a
    center_b,half_b=b
    overlap=[min(center_a[i]+half_a[i],center_b[i]+half_b[i])-
             max(center_a[i]-half_a[i],center_b[i]-half_b[i]) for i in range(3)]
    return all(value>TOLERANCE_M for value in overlap)


def world_positive_overlap(a,b):
    if min(a.zmax,b.zmax)-max(a.zmin,b.zmin)<=TOLERANCE_M:
        return False
    for x,y in a.axes+b.axes:
        ra=a.hx*abs(x*a.co+y*a.si)+a.hy*abs(-x*a.si+y*a.co)
        rb=b.hx*abs(x*b.co+y*b.si)+b.hy*abs(-x*b.si+y*b.co)
        if ra+rb-abs((b.x-a.x)*x+(b.y-a.y)*y)<=TOLERANCE_M:
            return False
    return True


def outline_cross_column_intersections(outlines):
    grid=defaultdict(list)
    for index,row in enumerate(outlines):
        x0,y0,x1,y1=row['box'].aabb
        for x in range(math.floor(x0),math.floor(x1)+1):
            for y in range(math.floor(y0),math.floor(y1)+1):
                grid[x,y].append(index)
    seen,overlaps=set(),[]
    for entries in grid.values():
        for offset,i in enumerate(entries):
            for j in entries[offset+1:]:
                key=min(i,j),max(i,j)
                if key in seen or outlines[i]['parent']==outlines[j]['parent']:
                    continue
                seen.add(key)
                if world_positive_overlap(outlines[i]['box'],outlines[j]['box']):
                    overlaps.append([outlines[i]['id'],outlines[j]['id']])
    return overlaps


def main(report):
    build=common.read_json(ROOT/'Saved/GHS_BuildReport.json')
    assert build.get('column_outlines_added') and build.get('wall_joined_corrected')
    applied=common.read_json(ROOT/'Saved/GHS_ColumnOutlinesApplied.json')
    assert applied['success']
    assert abs(applied['edge_width_m']-EDGE_WIDTH_M)<1e-9
    registry=common.read_json(ROOT/'SourceAssets/GHS/ue_scene_registry.json')
    previous=common.read_json(Path(applied['backup'])/'ue_scene_registry.json')
    histories={name:clearance.sha(ROOT/'Saved'/name) for name in
               ['GHS_Verification.json','GHS_ClearanceVerification.json','GHS_JoinedWallsVerification.json']}
    groups={group['actor']:group for group in registry['groups']}
    old_groups={group['actor']:group for group in previous['groups']}
    assert set(groups)==set(old_groups)|{GROUP} and GROUP not in old_groups
    assert len(old_groups)==15 and all(groups[label]==old_groups[label] for label in old_groups)
    assert registry['individuals']==previous['individuals']
    for key in previous:
        if key not in {'groups','individuals'}:
            assert registry[key]==previous[key], 'Pre-existing registry metadata changed: '+key
    # These functions preserve their historical reports and run every earlier
    # saved-state, mesh, material, FX, camera, LOD and clearance regression.
    joined.main(report)
    report['success']=False
    assert (report['actor_count'],report['hism_group_count'],report['instanced_count'])==((225 if build.get('lighting_optimized') else 248),16,14116)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    labels={actor.get_actor_label():actor for actor in actors}
    component=lambda label:labels[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    edges,bodies=component(GROUP),component('GHS_CAD_Columns')
    assert edges.get_instance_count()==2040 and bodies.get_instance_count()==170
    assert edges.get_editor_property('visible') and not edges.get_editor_property('hidden_in_game')
    assert edges.get_editor_property('static_mesh').get_path_name()=='/Engine/BasicShapes/Cube.Cube'
    assert edges.get_num_materials()==1
    trim=component('GHS_CAD_WallEdges').get_material(0)
    assert edges.get_material(0)==trim
    assert trim.get_path_name()=='/Game/GHSDigitalTwin/Materials/Instanced/M_GHS_WallTrim.M_GHS_WallTrim'
    assert bodies.get_material(0)==component('GHS_CAD_WallFaces').get_material(0)
    edge_bounds=edges.get_editor_property('static_mesh').get_bounds()
    body_bounds=bodies.get_editor_property('static_mesh').get_bounds()
    columns={row['id']:clearance.actual_box(bodies.get_instance_transform(index,world_space=True),body_bounds)
             for index,row in enumerate(groups['GHS_CAD_Columns']['instances'])}
    assert len(applied['source_column_ids'])==170 and set(applied['source_column_ids'])==set(columns)
    assert applied['source_level_sha256']==clearance.SOURCE_SHA
    prior_build=common.read_json(Path(applied['backup'])/'GHS_BuildReport.json')
    # The outline operation adds exactly one group; unrelated lighting may
    # already be optimized when a new level is built from the same source.
    assert applied['actor_count']==prior_build['actor_count']+1
    assert (applied['hism_group_count'],applied['instanced_count'])==(16,14116)
    source_handles={row['id']:row['source_handles'] for row in groups['GHS_CAD_Columns']['instances']}
    per_column=defaultdict(list)
    outlines=[]
    for index,row in enumerate(groups[GROUP]['instances']):
        parent=row.get('parent_column_id',row.get('parent_cad_id'))
        assert parent in columns, 'Outline lacks unique column source: '+str(row)
        assert row['source_handles']==source_handles[parent]
        box=clearance.actual_box(edges.get_instance_transform(index,world_space=True),edge_bounds)
        data=dict(id=row['id'],parent=parent,box=box)
        outlines.append(data)
        per_column[parent].append(data)
    assert set(per_column)==set(columns)
    report['column_outlines']=[]
    maximum_error,maximum_protrusion,overlap_count=0.0,0.0,0
    for parent,column in columns.items():
        rows=per_column[parent]
        assert len(rows)==12,parent+' must have twelve edges'
        size=(column.hx*2,column.hy*2,column.zmax-column.zmin)
        expected=expected_edges(*size)
        unmatched=set(range(12))
        local=[]
        total_volume=0.0
        for row in rows:
            center,half,points=box_in_column_frame(row['box'],column)
            protrusion=max(abs(p[i])-size[i]/2 for p in points for i in range(3))
            assert protrusion<=TOLERANCE_M,(parent,'outside column',row['id'],protrusion)
            maximum_protrusion=max(maximum_protrusion,protrusion)
            best=min(((max(abs(center[i]-expected[index][0][i]) for i in range(3)),
                       max(abs(half[i]-expected[index][1][i]) for i in range(3)),index)
                      for index in unmatched),key=lambda item:max(item[:2]))
            error=max(best[:2])
            assert error<=TOLERANCE_M,(parent,row['id'],'edge geometry mismatch',error)
            maximum_error=max(maximum_error,error)
            unmatched.remove(best[2])
            local.append((center,half))
            total_volume+=8*math.prod(half)
        assert not unmatched
        for index,a in enumerate(local):
            for b in local[index+1:]:
                overlap_count+=local_positive_overlap(a,b)
        expected_volume=4*EDGE_WIDTH_M**2*(sum(size)-4*EDGE_WIDTH_M)
        assert abs(total_volume-expected_volume)<1e-7,(parent,'outline volume mismatch')
        report['column_outlines'].append(dict(column_id=parent,edge_count=12,
            all_expected_edges_present=True,closed_top_bottom_and_vertical_connections=True,
            original_bounds_containment_verified=True,actual_volume_m3=total_volume))
    assert overlap_count==0,'Outline bars overlap inside a column'
    cross_overlaps=outline_cross_column_intersections(outlines)
    assert not cross_overlaps,cross_overlaps[:10]
    for name,digest in histories.items():
        assert clearance.sha(ROOT/'Saved'/name)==digest,'Historical report changed: '+name
    assert clearance.sha(ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap')==report['saved_map_sha256']
    assert clearance.sha(ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap')==clearance.SOURCE_SHA
    report.update(success=True,column_outlines_added=True,outlined_column_count=170,
        column_outline_instance_count=2040,column_outline_edge_width_m=EDGE_WIDTH_M,
        outline_wall_edge_material_identical=True,column_body_wall_material_identical=True,
        all_twelve_edge_frames_closed=True,all_outlines_inside_original_columns=True,
        outline_geometry_tolerance_m=TOLERANCE_M,maximum_outline_geometry_error_m=maximum_error,
        maximum_outline_protrusion_m=maximum_protrusion,outline_bar_overlap_count=0,
        cross_column_outline_overlap_count=0,all_original_groups_unchanged=15,
        all_individual_records_unchanged=True,historical_reports_preserved=histories)


def run():
    report=dict(success=False,map=common.MAP,created_utc=datetime.now(timezone.utc).isoformat(),
                verification_mode='Fresh UE saved HISM geometry in each column frame; no asset/level save',
                groups=[],individuals=[],effects=[],meshes=[])
    try:
        main(report)
    except Exception:
        report['success']=False
        report['error']=traceback.format_exc()
        raise
    finally:
        REPORT_PATH.write_text(json.dumps(report,indent=2),encoding='utf-8')
    unreal.log('GHS_COLUMN_OUTLINES_VERIFIED '+json.dumps({key:report[key] for key in
               ['success','actor_count','instanced_count','outlined_column_count','column_outline_instance_count']}))


if __name__=='__main__':
    run()
