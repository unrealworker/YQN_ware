"""Validate exported feed FBX against retained original CAD edges, not pose JSON.

Run inside Blender after build_mpr_operations.py. Z checks enforce the documented
display interpretation; original CAD XY edges independently constrain extents.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import sys
import bpy

ROOT=Path(__file__).resolve().parents[2]


def world_point(point,row):
    angle=math.radians(row['rotation_deg']);c,s=math.cos(angle),math.sin(angle)
    x,y,z=[point[k]*row['scale'][k] for k in range(3)]
    return [row['position_m'][0]+c*x-s*y,
            row['position_m'][1]+s*x+c*y,row['position_m'][2]+z]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--operations',type=Path,default=ROOT/'SourceAssets/MPR/operations')
    parser.add_argument('--output',type=Path,default=ROOT/'Saved/MPR/conveyor_repair_20261106/feed_geometry_verification.json')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    evidence=json.loads((ROOT/'SourceAssets/MPR/operations/cad_loose_feed_geometry.json').read_text(encoding='utf8'))
    operations=json.loads((args.operations/'instances.json').read_text(encoding='utf8'))
    manifest=json.loads((args.operations/'mpr_operations.json').read_text(encoding='utf8'))
    rows={tuple(r['source_handles']):r for r in operations['instances']}
    meshes={r['name']:r for r in manifest['meshes']}
    geometry={};mesh_checks=[]
    curve_handles={f['curve_handle'] for f in evidence['feeds']}
    curve_rows={h:rows[(h,)] for h in curve_handles}
    names={rows[tuple(f['source_handles'])]['mesh'] for f in evidence['feeds']}
    names.update(r['mesh'] for r in curve_rows.values())
    for name in sorted(names):
        path=ROOT/meshes[name]['fbx']
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.fbx(filepath=str(path))
        objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
        assert len(objects)==1,(name,len(objects))
        obj=objects[0];data=obj.data;data.calc_loop_triangles()
        assert all(t.area>1e-10 for t in data.loop_triangles),name
        assert len(data.loop_triangles)<1800,(name,len(data.loop_triangles))
        vertices=[tuple(obj.matrix_world@v.co) for v in data.vertices]
        surfaces=collections.defaultdict(list)
        for face in data.polygons:
            role=data.materials[face.material_index].name.split('.')[0]
            if face.normal.z>.5 and min(vertices[i][2] for i in face.vertices)>.9:
                surfaces[role].extend(vertices[i] for i in face.vertices)
        geometry[name]=(vertices,surfaces)
        mesh_checks.append(dict(mesh=name,triangles=len(data.loop_triangles),
                                fbx_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),zero_degenerate_faces=True))
    checks=[];bounds={};actual_points={}
    for feed in evidence['feeds']:
        row=rows[tuple(feed['source_handles'])]
        vertices,surfaces=geometry[row['mesh']]
        role='Metal' if feed['mesh_key'] in ('transfer','cap','bay') else 'Rubber'
        if feed['mesh_key']=='chevron':
            # Roller axes and diameters have their own paired-edge regression.
            points=[world_point(p,row) for p in vertices if abs(p[2]-1.5)<.00001]
        else:
            assert surfaces[role],(feed['id'],role)
            points=[world_point(p,row) for p in surfaces[role]]
        low=[min(p[k] for p in points) for k in range(3)]
        high=[max(p[k] for p in points) for k in range(3)]
        raw=feed.get('source_edges',[])
        inner=[p for edge in raw if edge.get('role','').startswith('inner_') for p in edge['points_m']]
        if feed['mesh_key'] not in ('chevron','terminal','transfer'):
            expected=inner or feed.get('source_polygon_m') or feed.get('belt_polygon_m')
            assert expected,feed['id']
            expected_low=[min(p[k] for p in expected) for k in range(2)]
            expected_high=[max(p[k] for p in expected) for k in range(2)]
            error=max(abs(low[k]-expected_low[k]) for k in range(2))
            error=max(error,max(abs(high[k]-expected_high[k]) for k in range(2)))
            # Original line ends differ from nominal outer-frame ends by 1.07 mm.
            assert error<.0013,(feed['id'],error,low,high,expected_low,expected_high)
        elif feed['mesh_key']=='terminal':
            source=feed['bounds_m'];expected_low=[min(p[k] for p in source) for k in range(2)]
            expected_high=[max(p[k] for p in source) for k in range(2)]
            error=max(abs(low[0]-expected_low[0]),abs(high[0]-expected_high[0]))
            assert error<.00003,(feed['id'],error)
            expected_width=(expected_high[1]-expected_low[1])*.35/.415
            assert abs(high[1]-low[1]-expected_width)<.00003
        else:
            error=None
        if feed['mesh_key']!='chevron':
            for endpoint,height in zip(feed['render_axis_endpoints_m'],feed['port_heights_m']):
                at_port=[p for p in points if abs(p[0]-endpoint[0])<.00003]
                assert at_port,(feed['id'],endpoint)
                assert max(abs(p[2]-height) for p in at_port)<.00003,(feed['id'],height,at_port)
        bounds[feed['id']]=dict(x=[low[0],high[0]],z=[low[2],high[2]])
        actual_points[feed['id']]=points
        checks.append(dict(id=feed['id'],mesh=row['mesh'],source_edge_error_m=error,
                           actual_surface_bounds_m=[low,high],port_heights_m=feed['port_heights_m']))
    arcs=json.loads((ROOT/'SourceAssets/MPR/conveyor_repair_20261106/u33_actual_cad_arcs.json').read_text(encoding='utf8'))
    curve_checks=[]
    for feed in (f for f in evidence['feeds'] if f['mesh_key']=='rise120'):
        handle=feed['curve_handle'];row=curve_rows[handle]
        source=next(a for a in arcs if a['handle']==handle)
        at=feed['render_axis_endpoints_m'][0]
        source_ends=[]
        for radius in (1.2,2.):
            candidates=[a[k] for a in source['arcs'] if abs(a['radius_m']-radius)<1e-5 for k in ('start_m','end_m')]
            source_ends.append(min(candidates,key=lambda p:math.dist(p,at)))
        new_port=[p for p in actual_points[feed['id']] if abs(p[0]-at[0])<.00003]
        ends=[min(new_port,key=lambda p:p[1]),max(new_port,key=lambda p:p[1])]
        source_ends.sort(key=lambda p:p[1])
        errors=[math.dist(a[:2],b) for a,b in zip(ends,source_ends)]
        assert max(errors)<.0012,(handle,errors)
        curve_surface=[world_point(p,row) for p in geometry[row['mesh']][1]['Rubber']]
        curve_port=[p for p in curve_surface if abs(p[0]-at[0])<.00005]
        assert curve_port,(handle,at)
        # Existing display curve uses frame radii as its carrying width. Require
        # the recovered 0.8m feed to land inside that retained surface, not outside.
        assert min(p[1] for p in curve_port)<=min(p[1] for p in ends)
        assert max(p[1] for p in curve_port)>=max(p[1] for p in ends)
        z_error=max(abs(p[2]-q[2]) for p in curve_port for q in new_port)
        assert z_error<.00003,(handle,z_error)
        curve_checks.append(dict(curve_handle=handle,source_inner_arc_endpoints_m=source_ends,
                                 actual_feed_port_m=ends,edge_errors_m=errors,
                                 actual_retained_curve_port_m=curve_port,height_step_m=z_error))
    joins=[]
    for handle in sorted(curve_handles):
        chain=[f for f in evidence['feeds'] if f['curve_handle']==handle and f['mesh_key'] not in ('terminal','cap','bay')]
        direction=-1 if handle=='2CC6A3' else 1
        chain.sort(key=lambda f:direction*f['position_m'][0])
        for a,b in zip(chain,chain[1:]):
            pa,pb=actual_points[a['id']],actual_points[b['id']]
            xa=max(direction*p[0] for p in pa);xb=min(direction*p[0] for p in pb)
            za=[p[2] for p in pa if abs(direction*p[0]-xa)<.00003]
            zb=[p[2] for p in pb if abs(direction*p[0]-xb)<.00003]
            step=max(abs(x-y) for x in za for y in zb)
            assert step<.00003,(a['id'],b['id'],step)
            gap=xb-xa
            # The V-roller bearing surface has spaces between its end rollers,
            # measured from actual source axes, not a fictitious solid deck.
            if 'chevron' not in (a['mesh_key'],b['mesh_key']):
                source_gap=direction*(b['render_axis_endpoints_m'][0][0]-a['render_axis_endpoints_m'][1][0])
                assert abs(gap-source_gap)<.00003,(a['id'],b['id'],gap,source_gap)
            else:
                source_gap=None
            joins.append(dict(upstream=a['id'],downstream=b['id'],actual_carrying_surface_gap_m=gap,
                              source_frame_gap_m=source_gap,height_step_m=step,
                              note='Source V-roller ends are open between discrete rollers' if source_gap is None else 'Original drafted machine clearance retained'))
    result=dict(source_sha256=evidence['source_sha256'],
                evidence_sha256=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
                arc_evidence_sha256=hashlib.sha256(json.dumps(arcs,sort_keys=True).encode()).hexdigest(),
                new_feed_count=len(checks),mesh_checks=mesh_checks,feed_checks=checks,
                curve_feed_port_checks=curve_checks,adjacent_surface_checks=joins,
                height_note=evidence['height_interpretation'],
                note='FBX vertices checked against original CAD edge records. Z uses explicit H-range endpoint interpretation; tiny drafted machine clearances are retained.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'verified_feeds':len(checks),'verified_meshes':len(mesh_checks),'max_xy_error_m':max(r['source_edge_error_m'] or 0 for r in checks)}))


if __name__=='__main__':main()
