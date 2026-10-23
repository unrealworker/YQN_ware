"""Add modest road-end continuations and sparse distant woodland islands.

Run in background Blender. This never rebuilds existing park meshes or ground.
Traffic routes own the exact original and extended centreline endpoints.
"""
from pathlib import Path
from collections import defaultdict
import hashlib
import json
import math
import random
import sys
import bpy

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/GHS/ContextTransition'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
from park_curves import offset_path,dash_segments
from park_surfaces import emit_surface
from park_forests import _island,_emit_island
from park_vegetation import build_tree,build_shrub
from context_road_ends import classify_context_road_ends
import build_park_geometry as base

DATA=defaultdict(lambda:dict(vertices=[],faces=[],fade=[]))
ORIGIN=(239.33385,60.24019)
FADE=lambda p:0.


def mesh(role,vertices,faces):
    data=DATA[role];start=len(data['vertices'])
    data['vertices'].extend((u-ORIGIN[0],-(v-ORIGIN[1]),z) for u,v,z in vertices)
    data['faces'].extend(tuple(start+i for i in reversed(f)) for f in faces)
    data['fade'].extend(float(FADE(p)) for p in vertices)


def emit_road_end(road, side):
    """Emit one exact source continuation; callers classify its endpoint first."""
    global FADE
    path=road['path_uv_m'];heights=road['heights_m'];width=road['width_m']
    i,j=(0,1) if side=='start' else (-1,-2)
    p=path[i];neighbor=path[j]
    size=math.dist(p,neighbor)
    tangent=((p[0]-neighbor[0])/size,(p[1]-neighbor[1])/size)
    length=float(road.get('extension_m',65.))
    end=(p[0]+tangent[0]*length,p[1]+tangent[1]*length)
    # Start 8 cm inside the original edge; put the overlap 0.3 cm up.
    a=(p[0]-tangent[0]*.08,p[1]-tangent[1]*.08)
    points=[(a[0]+tangent[0]*d,a[1]+tangent[1]*d)
            for d in [k*(length+.08)/32 for k in range(33)]]
    z=heights[i]+.003
    def fade(point,origin=p,direction=tangent,total=length):
        d=(point[0]-origin[0])*direction[0]+(point[1]-origin[1])*direction[1]
        t=max(0.,min(1.,(d-(total-30))/30))
        return t*t*(3-2*t)
    FADE=fade
    base.ribbon('ContextRoads',points,width,z)
    freeway=road['id'].lower().startswith(('i15','freeway','highway'))
    lane_offsets=(-2.3,2.3) if freeway else (-4.6,0,4.6) if width>15 else (0,)
    for offset in lane_offsets:
        for dash in dash_segments(offset_path(points,offset),5.5 if freeway else 3.8,8 if freeway else 6.5):
            base.ribbon('Markings',dash,.12,z+.026)
    for side_sign in (-1,1):
        base.ribbon('Curbs',offset_path(points,side_sign*(width/2+.14)),.26,z+.15)
        base.ribbon('Landscape',offset_path(points,side_sign*(width/2+1.1)),1.5,-.04)
        if freeway:base.ribbon('Markings',offset_path(points,side_sign*(width/2-.25)),.13,z+.026)
    FADE=lambda p:0.
    return dict(road_id=road['id'],side=side,old_end_uv_m=p,new_end_uv_m=end,
                length_m=length,width_m=width,height_m=z,fade_starts_m=length-30,path_uv_m=points)


def road_ends(roads, cad_roads=()):
    """Continue only physical outer road ends, never internal CAD junctions."""
    allowed=classify_context_road_ends(roads,cad_roads)['external']
    by={road['id']:road for road in roads}
    return [emit_road_end(by[row['road_id']],row['side']) for row in allowed]


def distant_islands(site,cad,ends):
    global FADE
    scope=Polygon(site['forests']['forest_scope_polygon_uv_m'])
    campus=Polygon(site['campus_boundary_uv_m'])
    roads=unary_union([LineString(r['points_uv_m']).buffer(12)
        for r in cad['roads'] if len(r['points_uv_m'])>1]+[
        LineString(e['path_uv_m']).buffer(e['width_m']/2+9) for e in ends])
    buildings=unary_union([Polygon(h['footprint_uv_m']).buffer(10) for h in site['residential']['houses']])
    previous=unary_union([Polygon(p['exterior'],p.get('holes',[]))
        for group in site['forests']['groups'] for p in group['ground_polygons_uv_m']])
    water=unary_union([Polygon(r['points_uv_m']).buffer(0) if r.get('closed') else LineString(r['points_uv_m'])
        for r in cad.get('linework',[]) if r['layer']=='water' and len(r['points_uv_m'])>=3])
    available=scope.buffer(-4).difference(unary_union([roads,buildings,previous.buffer(15),campus.buffer(20),water.buffer(18)]))
    targets=[(-270,-310),(-65,-340),(120,-325),(435,-315),(780,-165),
             (785,85),(-285,270),(710,535),(-170,490)]
    rng=random.Random(173352210);selected=[];islands=[];trees=[]
    for target in targets:
        candidates=[]
        for _ in range(1000):
            q=Point(target[0]+rng.uniform(-50,50),target[1]+rng.uniform(-45,45))
            if available.buffer(-17).covers(q) and all(q.distance(p)>48 for p in selected):candidates.append(q)
        if not candidates:continue
        center=min(candidates,key=lambda q:q.distance(Point(target)))
        island=_island(center,rng.uniform(15.5,21),len(islands)*1.6).intersection(available)
        if island.area<500:continue
        selected.append(center)
        # Distant islands share the vegetation language but have less contrast.
        FADE=lambda p:.12
        _emit_island({'mesh':mesh},island)
        placements=[]
        xmin,ymin,xmax,ymax=island.bounds
        for _ in range(1000):
            if len(placements)>=6:break
            x,y=rng.uniform(xmin,xmax),rng.uniform(ymin,ymax)
            if not island.buffer(-3.5).covers(Point(x,y)):continue
            if any(math.dist((x,y),p['position_uv_m'])<9.5 for p in placements):continue
            variant=rng.randrange(3);height=rng.uniform(5.2,7.6)
            size=height/(8.6,10.8,8.7)[variant]
            info=build_tree({'mesh':mesh},x,y,size,variant,base_z=.08)
            placements.append(dict(position_uv_m=[x,y],height_m=height,
                                   radius_m=info['radius_m'],variant=variant))
        assert len(placements)>=3
        islands.append(dict(center_uv_m=[center.x,center.y],trees=placements,
            polygon_uv_m=list(island.exterior.coords),area_m2=island.area))
        trees.extend(placements)
    FADE=lambda p:0.
    assert 5<=len(islands)<=9,(len(islands),'Need sparse distributed edge islands')
    assert len(trees)<=54
    return islands


def export():
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1.
    manifest=[]
    for role,data in sorted(DATA.items()):
        name='SM_GHSContextTransition_'+role
        geo=bpy.data.meshes.new(name);geo.from_pydata(data['vertices'],[],data['faces']);geo.update()
        assert not geo.validate()
        colors=geo.color_attributes.new(name='EdgeFade',type='FLOAT_COLOR',domain='POINT')
        for i,value in enumerate(data['fade']):colors.data[i].color=(value,value,value,1)
        geo.color_attributes.active_color=colors
        if role.startswith('Trees'):
            for poly in geo.polygons:poly.use_smooth=True
        material=bpy.data.materials.new('M_GHSContextTransition_'+role)
        material.diffuse_color=(*base.PALETTE[role],1)
        geo.materials.append(material)
        obj=bpy.data.objects.new(name,geo);bpy.context.collection.objects.link(obj)
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        fbx=OUT/(name+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
            axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
            mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False,colors_type='LINEAR')
        geo.calc_loop_triangles()
        manifest.append(dict(name=name,role=role,fbx=str(fbx.relative_to(ROOT)).replace('\\','/'),
            vertices=len(geo.vertices),triangles=len(geo.loop_triangles),
            bounds_ue_cm=dict(min=[min(v.co.x for v in geo.vertices)*100,-max(v.co.y for v in geo.vertices)*100,min(v.co.z for v in geo.vertices)*100],
                max=[max(v.co.x for v in geo.vertices)*100,-min(v.co.y for v in geo.vertices)*100,max(v.co.z for v in geo.vertices)*100]),
            sha256=hashlib.sha256(fbx.read_bytes()).hexdigest()))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'GHS_ContextTransition.blend'))
    return manifest


def main():
    # Import primitives only; never call the full site's build/export pipeline.
    base.mesh=mesh
    routes=json.loads((ROOT/'SourceAssets/GHS/Traffic/routes.json').read_text(encoding='utf-8'))
    site=json.loads((ROOT/'SourceAssets/GHS/Park/site_geometry_report.json').read_text(encoding='utf-8'))
    cad=json.loads((ROOT/'SourceAssets/GHS/Park/cad_layout.json').read_text(encoding='utf-8'))
    ends=road_ends(routes['roads'],cad['roads'])
    islands=distant_islands(site,cad,ends)
    assets=export()
    # Convex support planes keep all campus props at their original color.
    hull=Polygon(site['campus_boundary_uv_m']).convex_hull.simplify(2,preserve_topology=True)
    assert all(hull.buffer(5).covers(Polygon(h['footprint_uv_m'])) is False for h in site['residential']['houses'])
    result=dict(version=2,roads=ends,islands=islands,meshes=assets,
        excluded_internal_endpoints=classify_context_road_ends(routes['roads'],cad['roads'])['internal'],
        protected_campus_hull_uv_m=list(hull.exterior.coords),
        exterior_building_blend=.18,interior_materials_unchanged=True,
        original_ground_unchanged=True,new_actor_count=len(assets),
        triangles=sum(a['triangles'] for a in assets),trees=sum(len(g['trees']) for g in islands))
    assert result['triangles']<110000
    (OUT/'context_transition.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('GHS_CONTEXT_TRANSITION_READY',json.dumps(dict(roads=len(ends),islands=len(islands),trees=result['trees'],triangles=result['triangles'])))


if __name__=='__main__':main()
