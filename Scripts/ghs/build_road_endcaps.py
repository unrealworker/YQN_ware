"""Export a scoped replacement of the existing Curbs source mesh.

No full park rebuild: every untouched face is copied exactly. Only the .10m
sidewalk and .19m curb triangles inside the two Glen opening masks are cut.
The original blend/FBX files and all material assignments remain untouched.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'Scripts/ghs'))
sys.path.insert(0, str(ROOT/'Saved/ParkRefinement/python_deps'))
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union
from road_endcaps import glen_endcap_masks

SOURCE = ROOT/'SourceAssets/GHS/Park/GHS_Park_Source.blend'
OUT = ROOT/'SourceAssets/GHS/RoadEndcaps'
ORIGIN = (239.33385,60.24019)
NAME = 'SM_GHSRoadEndcaps_Curbs'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    return [part for child in geometry.geoms for part in parts(child)]


def face_key(vertices, face):
    return tuple(sorted(tuple(vertices[index]) for index in face))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protected = sorted((ROOT/'SourceAssets/GHS/Park').glob('*.fbx'))
    protected += sorted((ROOT/'SourceAssets/GHS/ContextTransition').glob('*.fbx'))
    protected += [SOURCE, ROOT/'SourceAssets/GHS/Traffic/routes.json',
                  ROOT/'SourceAssets/GHS/ContextTransition/context_transition.json']
    hashes = {str(path.relative_to(ROOT)).replace('\\','/'):sha(path) for path in protected}
    routes = json.loads((ROOT/'SourceAssets/GHS/Traffic/routes.json').read_text(encoding='utf-8'))
    openings = glen_endcap_masks(routes['roads'])
    cut = unary_union([row['polygon'] for row in openings])
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    with bpy.data.libraries.load(str(SOURCE),link=False) as (_,target):
        target.objects=['SM_GHSPark_Curbs']
    original = target.objects[0]
    assert all(abs(original.matrix_world[row][col]-(1 if row==col else 0))<1e-8
               for row in range(4) for col in range(4))
    vertices = [tuple(v.co) for v in original.data.vertices]
    old_faces = [tuple(p.vertices) for p in original.data.polygons]
    faces, face_settings, untouched, removed = [], [], Counter(), []
    for index, face in enumerate(old_faces):
        coords = [vertices[i] for i in face]
        level = coords[0][2]
        eligible = min(abs(level-.10),abs(level-.19))<1e-6 and all(abs(v[2]-level)<1e-7 for v in coords)
        polygon = None
        if eligible:
            xy = [(v[0]+ORIGIN[0],-v[1]+ORIGIN[1]) for v in coords]
            # Avoid creating Shapely objects for the rest of the 110k faces.
            eligible = any(not (max(x for x,y in xy)<r['polygon'].bounds[0] or
                                min(x for x,y in xy)>r['polygon'].bounds[2] or
                                max(y for x,y in xy)<r['polygon'].bounds[1] or
                                min(y for x,y in xy)>r['polygon'].bounds[3]) for r in openings)
            if eligible:
                polygon=Polygon(xy)
                eligible=polygon.intersection(cut).area>1e-10
        source_face=original.data.polygons[index]
        settings=(source_face.material_index,source_face.use_smooth)
        if not eligible:
            faces.append(face);face_settings.append(settings)
            untouched[face_key(vertices,face)]+=1
            continue
        kept=polygon.difference(cut)
        removed.append(dict(source_face=index,elevation_m=level,removed_area_m2=polygon.area-kept.area))
        for part in parts(kept):
            for triangle in parts(shapely.constrained_delaunay_triangles(part)):
                if triangle.area<1e-10:
                    continue
                xy=list(triangle.exterior.coords)[:-1]
                # Preserve the original face orientation after the Y mirror.
                sign=lambda points:sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))
                if sign(xy)*sign([(v[0]+ORIGIN[0],-v[1]+ORIGIN[1]) for v in coords])<0:
                    xy.reverse()
                start=len(vertices)
                vertices.extend((x-ORIGIN[0],-(y-ORIGIN[1]),level) for x,y in xy)
                faces.append(tuple(range(start,start+len(xy))));face_settings.append(settings)
    assert removed, 'Expected source endcaps were not found'
    mesh=bpy.data.meshes.new(NAME)
    mesh.from_pydata(vertices,[],faces);mesh.update()
    assert not mesh.validate(), 'Clipped mesh required repairs'
    for material in original.data.materials:
        mesh.materials.append(material)
    for face,settings in zip(mesh.polygons,face_settings):
        face.material_index,face.use_smooth=settings
    obj=bpy.data.objects.new(NAME,mesh);bpy.context.collection.objects.link(obj)
    # Compare exact float32 face coordinates after Blender stores the mesh.
    new_vertices=[tuple(v.co) for v in mesh.vertices]
    actual=Counter(face_key(new_vertices,tuple(p.vertices)) for p in mesh.polygons)
    assert not (untouched-actual), 'An out-of-scope source face changed'
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=1.
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    fbx=OUT/(NAME+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
        mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'GHS_RoadEndcaps.blend'))
    mesh.calc_loop_triangles()
    bounds=[[min(v.co[i] for v in mesh.vertices),max(v.co[i] for v in mesh.vertices)] for i in range(3)]
    assert all(sha(ROOT/path)==value for path,value in hashes.items()), 'Protected source file changed'
    report=dict(version=1,success=True,scope='glen:start and glen:end only',
        name=NAME,fbx=str(fbx.relative_to(ROOT)).replace('\\','/'),sha256=sha(fbx),
        vertices=len(mesh.vertices),triangles=len(mesh.loop_triangles),
        source_faces=len(old_faces),untouched_faces=sum(untouched.values()),changed_source_faces=len(removed),
        removed_area_m2=sum(row['removed_area_m2'] for row in removed),removed_faces=removed,
        material_slots=[m.name for m in mesh.materials],
        bounds_ue_cm=dict(min=[bounds[0][0]*100,-bounds[1][1]*100,bounds[2][0]*100],
                          max=[bounds[0][1]*100,-bounds[1][0]*100,bounds[2][1]*100]),
        openings=[{**{k:v for k,v in row.items() if k!='polygon'},
                   'mask_uv_m':list(row['polygon'].exterior.coords)} for row in openings],
        protected_source_sha256=hashes,
        original_assets_unchanged=True,untouched_face_coordinates_exact=True,
        overlay_geometry_added=False)
    (OUT/'road_endcaps.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('GHS_ROAD_ENDCAPS_READY',json.dumps({k:report[k] for k in ('triangles','untouched_faces','changed_source_faces','removed_area_m2')}))


if __name__=='__main__':
    main()
