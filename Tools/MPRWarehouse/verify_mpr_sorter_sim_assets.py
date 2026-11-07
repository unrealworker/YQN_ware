"""Roundtrip private sorter FBX and check full-loop motion clearances."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'SourceAssets/MPR/sorter_simulation'


def bounds(points):
    return [[min(p[k] for p in points) for k in range(3)],
            [max(p[k] for p in points) for k in range(3)]]


def intersects(a,b,epsilon=.0001):
    return all(a[0][k]<b[1][k]-epsilon and b[0][k]<a[1][k]-epsilon for k in range(3))


def pose(profile,phase):
    h=profile['track_half_straight_cm']/100;r=profile['track_radius_cm']/100
    quarter=math.pi*r/2;distance=(phase%1)*(4*h+2*math.pi*r)
    if distance<quarter:
        a=distance/r;return [h+r*math.cos(a),r*math.sin(a)],a+math.pi/2
    distance-=quarter
    if distance<2*h:return [h-distance,r],math.pi
    distance-=2*h
    if distance<2*quarter:
        a=math.pi/2+distance/r;return [-h+r*math.cos(a),r*math.sin(a)],a+math.pi/2
    distance-=2*quarter
    if distance<2*h:return [-h+distance,-r],0
    distance-=2*h;a=3*math.pi/2+distance/r
    return [h+r*math.cos(a),r*math.sin(a)],a+math.pi/2


def transformed(points,xy,yaw,z=0):
    c,s=math.cos(yaw),math.sin(yaw)
    return [(xy[0]+c*p[0]-s*p[1],xy[1]+s*p[0]+c*p[1],p[2]+z) for p in points]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=SRC/'geometry_validation.json')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    manifest=json.loads((SRC/'manifest.json').read_text(encoding='utf8'))
    layout=json.loads((SRC/'layout.json').read_text(encoding='utf8'))
    mesh_data={};roundtrip=[]
    for record in manifest['meshes']:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        path=ROOT/record['fbx'];bpy.ops.import_scene.fbx(filepath=str(path))
        objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(objects)==1
        obj=objects[0];data=obj.data;data.calc_loop_triangles()
        points=[tuple(obj.matrix_world@v.co) for v in data.vertices]
        assert len(data.materials)==7
        assert [m.name.removeprefix('M_Zcool_').split('.')[0] for m in data.materials]==record['material_roles']
        assert len(data.loop_triangles)==record['triangles']
        assert all(t.area>1e-12 for t in data.loop_triangles)
        bb=bounds(points);error=max(abs(bb[end][k]-record['bounds_m'][k][end]) for k in range(3) for end in range(2));assert error<.00001
        ue=[(p[0],-p[1],p[2]) for p in points]
        mesh_data[record['name']]=ue
        roundtrip.append(dict(mesh=record['name'],triangles=len(data.loop_triangles),material_slots=7,
                              fbx_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bounds_error_m=error,
                              ue_bounds_cm=[[x*100 for x in p] for p in bounds(ue)]))
    tower=mesh_data['SM_MPR_SorterSimTower'];tray=mesh_data['SM_MPR_SorterSimTray']
    assert abs(min(p[1] for p in tower))<1e-6 and abs(max(p[1] for p in tower)-.22)<1e-6
    assert abs(min(p[1] for p in tray)+.125)<1e-6 and abs(max(p[1] for p in tray)-.1675)<1e-6
    # Retained bin corners must be present in the actual imported FBX after the
    # one Y reflection. An asymmetric tower above catches double/no reflection.
    bin_checks=[]
    for key,profile in layout['profiles'].items():
        mesh=profile['static_mesh'].split('/')[-1];points=mesh_data[mesh]
        tree=KDTree(len(points))
        for i,p in enumerate(points):tree.insert(p,i)
        tree.balance();errors=[]
        for slot in profile['bins']:
            lo,hi=slot['bin_bounds_cm']
            for x in (lo[0],hi[0]):
                for y in (lo[1],hi[1]):
                    _,_,error=tree.find((x/100,y/100,hi[2]/100));errors.append(error)
        assert max(errors)<.00001,(key,max(errors))
        bin_checks.append(dict(profile=key,slots=len(profile['bins']),rim_corner_tests=len(errors),max_error_m=max(errors)))
    bpy.ops.wm.open_mainfile(filepath=str(SRC/'MPR_SorterSimulation.blend'))
    collisions=[];motion_checks=[]
    for key,profile in layout['profiles'].items():
        mesh=profile['static_mesh'].split('/')[-1];col=bpy.data.collections[mesh+'_Editable_LOD0']
        fixed=[];guide_count=0
        for obj in col.objects:
            # Drive/guide surfaces are bearing interfaces, not obstacle volumes.
            if obj.name.startswith(('LowerGuide','UpperGuide')):guide_count+=1;continue
            pts=[obj.matrix_world@v.co for v in obj.data.vertices]
            fixed.append((obj.name,bounds([(p.x,-p.y,p.z) for p in pts])))
        heights=[.15+i*.05 for i in range(36)]+[p['tray_carry_z_cm']/100 for p in profile['levels']]+[1.035]
        footprint=[profile['plan_length_cm']/200,profile['plan_width_cm']/200]
        max_extent=[0,0]
        for i in range(512):
            xy,yaw=pose(profile,i/512)
            tower_bounds=bounds(transformed(tower,xy,yaw))
            candidates=[]
            for name,box in fixed:
                if intersects(tower_bounds,box):collisions.append(dict(profile=key,phase=i/512,part='tower',obstacle=name))
                # Filter once in XY; only a handful can intersect moving trays.
                base=bounds(transformed(tray,xy,yaw))
                if all(base[0][k]<box[1][k] and box[0][k]<base[1][k] for k in (0,1)):candidates.append((name,box))
            for z in heights:
                bb=bounds(transformed(tray,xy,yaw,z))
                for name,box in candidates:
                    if intersects(bb,box):collisions.append(dict(profile=key,phase=i/512,part='tray',height_m=z,obstacle=name))
                for k in (0,1):max_extent[k]=max(max_extent[k],abs(bb[0][k]),abs(bb[1][k]))
            assert all(max_extent[k]<=footprint[k]+.0001 for k in (0,1)),(key,max_extent,footprint)
        motion_checks.append(dict(profile=key,loop_samples=512,vertical_samples=len(heights),
                                  evaluated_tray_poses=512*len(heights),fixed_object_obstacles=len(fixed),
                                  bearing_guide_segments_excluded=guide_count,max_swept_half_extent_m=max_extent,
                                  original_half_footprint_m=footprint))
    result=dict(status='passed' if not collisions else 'failed',fbx=roundtrip,bin_alignment=bin_checks,
                motion=motion_checks,collisions=collisions,
                axis_probe='Actual FBX Tower becomes UE local Y[0,22]cm; Tray Y[-12.5,16.75]cm after exactly one reflection.',
                limitation='Conservative whole-part AABB sweep against fixed frame/bin/chute geometry; bearing guide contact interfaces excluded. Runtime trajectory must use this exact profile and tangent orientation.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status=result['status'],fbx=len(roundtrip),motion=motion_checks,collision_count=len(collisions),first_collisions=collisions[:8])))
    assert not collisions,collisions[:8]


if __name__=='__main__':main()
