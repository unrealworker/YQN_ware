"""Check physical building geometry independently from image projection fit.

Python checks delivered footprints; Blender additionally reopens the source
and checks saved roof-face planarity and wall-face verticality. All context
buildings use the newly registered plan; tanks are checked as true circles.
"""
from pathlib import Path
import argparse, hashlib, json, math, sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT/'SourceAssets/MPR/reference_v4/context'
sys.path[:0]=[str(ROOT/'Saved/ParkRefinement/python_deps'),str(ROOT/'Tools/MPRWarehouse')]
from shapely.geometry import MultiPoint,Polygon


def polygon_angles(points):
    q=np.asarray(points,dtype=float);edges=np.roll(q,-1,axis=0)-q
    return [math.degrees(math.acos(float(np.clip((-edges[i-1])@edges[i]/
            np.linalg.norm(edges[i-1])/np.linalg.norm(edges[i]),-1,1)))) for i in range(len(q))]


def main():
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='Saved/MPR/road_v5/context_geometry_validation.json')
    parser.add_argument('--blender',action='store_true');opts=parser.parse_args(args)
    manifest=json.loads((CONTEXT/'manifest.json').read_text(encoding='utf8'))
    errors=[];buildings=[];tank_checks=[]
    for row in manifest['context_buildings']:
        if row['type']=='cylindrical_tank':
            center=np.asarray(row['center_m'][:2]);radii=np.linalg.norm(np.asarray(row['footprint_m'])-center,axis=1)
            error=float(np.max(np.abs(radii-row['radius_m'])))
            tank_checks.append(dict(id=row['id'],radius_m=row['radius_m'],metadata_circle_max_radius_error_m=error))
            if error>1e-8:errors.append(f"{row['id']}: footprint not circular")
            continue
        angles=polygon_angles(row['footprint_m']);error=max(abs(v-90) for v in angles)
        buildings.append(dict(id=row['id'],type=row['type'],angles_deg=angles,max_right_angle_error_deg=error))
        if error>1e-5:errors.append(f"{row['id']}: rectangle corner error {error:.6f} degrees")
    mesh_checks=[];house_envelopes=[];house_clearance=[]
    if opts.blender:
        import bpy
        bpy.ops.wm.open_mainfile(filepath=str(CONTEXT/'mpr4_reference_context.blend'))
        for ob in bpy.data.objects:
            if ob.type!='MESH' or any(word in ob.name for word in ('Tank','Pipes','Pads')):continue
            roof_error=wall_error=0.;roof_faces=wall_faces=0
            for face in ob.data.polygons:
                role=ob.data.materials[face.material_index].name
                points=np.array([tuple(ob.data.vertices[i].co) for i in face.vertices])
                if role=='MPR4_ContextRoof':
                    roof_faces+=1
                    _,_,v=np.linalg.svd(points-points.mean(axis=0),full_matrices=False)
                    roof_error=max(roof_error,float(np.max(np.abs((points-points.mean(axis=0))@v[-1]))))
                if role=='MPR4_ContextWall':
                    wall_faces+=1
                    normal=np.array(face.normal)
                    wall_error=max(wall_error,min(abs(float(normal[2])),abs(1-abs(float(normal[2])))))
            mesh_checks.append(dict(name=ob.name,roof_faces=roof_faces,roof_max_plane_error_m=roof_error,wall_faces=wall_faces,wall_normal_axis_error=wall_error))
            # Single precision Blender vertices at 600m coordinates have ~0.06mm ULP.
            if roof_error>.00015:errors.append(f'{ob.name}: saved roof face plane error {roof_error:.8f} m')
            # Gable triangles at large world coordinates acquire <0.006 degree
            # normal noise from float32 midpoint rounding; no visible slant.
            if wall_error>1e-4:errors.append(f'{ob.name}: saved wall not vertical/horizontal {wall_error:.8f}')
        for row in manifest['context_buildings']:
            if row['type']!='house_gable':continue
            frame=row['physical_frame'];ranges=frame.get('mesh_vertex_ranges')
            if not ranges:
                errors.append(row['id']+': missing delivered-mesh vertex provenance');continue
            ob=bpy.data.objects[row['mesh']];points=[]
            for role,span in ranges.items():
                start=span['saved_vertex_start'];count=span['vertex_count']
                points.extend(tuple(ob.data.vertices[i].co)[:2]for i in range(start,start+count))
            actual=MultiPoint(points).convex_hull;expected=Polygon(frame['complete_geometry_footprint_m'])
            delta=actual.hausdorff_distance(expected);outside=actual.difference(Polygon(row['footprint_m']).buffer(.0002)).area
            if delta>.00015:errors.append(row['id']+': saved geometry differs from complete source envelope')
            if outside>.0001:errors.append(row['id']+': roof or porch extends outside cleared footprint')
            house_envelopes.append(dict(id=row['id'],checked_vertices=len(points),footprint_m=list(actual.exterior.coords)[:-1],
                                        source_to_saved_hull_error_m=delta,outside_cleared_footprint_m2=outside))
        from mpr_plan_site import road_geometry
        roads=road_geometry()
        for i,a in enumerate(house_envelopes):
            pa=Polygon(a['footprint_m'])
            if pa.intersection(roads).area>.001:errors.append(a['id']+': complete mesh envelope intersects road')
            for b in house_envelopes[i+1:]:
                pb=Polygon(b['footprint_m']);distance=pa.distance(pb)
                if distance<5:
                    house_clearance.append(dict(a=a['id'],b=b['id'],clearance_m=distance,xy_overlap_m2=pa.intersection(pb).area))
                if distance<2.999:errors.append(a['id']+' / '+b['id']+': complete mesh clearance below 3m')
        tank=bpy.data.objects['SM_MPR4_Context_TankField'];vertices=np.array([tuple(v.co)for v in tank.data.vertices])
        for check in tank_checks:
            row=next(r for r in manifest['context_buildings']if r['id']==check['id']);center=np.asarray(row['center_m'][:2]);radius=row['radius_m']
            distances=np.linalg.norm(vertices[:,:2]-center,axis=1);points=vertices[(np.abs(vertices[:,2]+1.2)<.0001)&(np.abs(distances-radius)<.002)]
            points=np.unique(points,axis=0);assert len(points)==48,(row['id'],len(points))
            error=float(np.max(np.abs(np.linalg.norm(points[:,:2]-center,axis=1)-radius)))
            check.update(saved_circle_vertices=len(points),saved_circle_max_radius_error_m=error,
                         saved_circle_xy_diameters_m=np.ptp(points[:,:2],axis=0).tolist())
            if error>.00015:errors.append(f"{row['id']}: saved geometry is not a true circle")
    report=dict(success=not errors,checked_buildings=len(buildings),max_right_angle_error_deg=max(x['max_right_angle_error_deg'] for x in buildings),
                source_manifest_sha256=hashlib.sha256((CONTEXT/'manifest.json').read_bytes()).hexdigest(),buildings=buildings,
                true_circle_tanks=tank_checks,saved_blender_checked=opts.blender,mesh_checks=mesh_checks,errors=errors,
                saved_house_envelopes=house_envelopes,nearby_house_clearances=house_clearance,
                minimum_complete_house_clearance_m=min((r['clearance_m']for r in house_clearance),default=None),
                boundary='Geometric invariants only; source inspection does not replace actual UE visual acceptance or new-road setback review.')
    output=ROOT/opts.output;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('buildings','mesh_checks','errors','true_circle_tanks','saved_house_envelopes','nearby_house_clearances')},ensure_ascii=False));print('errors',len(errors))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
