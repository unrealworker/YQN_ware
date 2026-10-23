"""Remove exactly two erroneous internal-junction tails from saved source.

Background Blender only. This never calls the full context/island builder,
imports Unreal, edits the original blend, or changes traffic routes. Every
retained face and its EdgeFade values must match the source exactly.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import struct
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'Scripts/ghs'))
from context_road_ends import classify_context_road_ends
import build_context_transition as context

SOURCE = ROOT/'SourceAssets/GHS/ContextTransition'
OUT = ROOT/'SourceAssets/GHS/RoadTerminalFade'
ROLES = ('ContextRoads', 'Curbs', 'Markings', 'Landscape')
EXPECTED_REMOVALS = {('sycamore_south','end'), ('sycamore_north','start')}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path):
    return str(path.relative_to(ROOT)).replace('\\','/')


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def face_key(vertices, indices):
    # Source Blender meshes store float32. No broad spatial tolerance or
    # bounding-box clipping is allowed to remove real roads or green islands.
    return tuple(sorted(tuple(f32(v) for v in vertices[index]) for index in indices))


def face_record(mesh, polygon):
    colors = mesh.color_attributes['EdgeFade']
    return (tuple((tuple(mesh.vertices[i].co), tuple(colors.data[i].color))
                  for i in polygon.vertices), polygon.material_index, polygon.use_smooth)


def main():
    original_blend = SOURCE/'GHS_ContextTransition.blend'
    protected = [original_blend, SOURCE/'context_transition.json',
                 ROOT/'SourceAssets/GHS/Traffic/routes.json',
                 ROOT/'Content/GHSTwinUI/data/campus-traffic-routes.json',
                 ROOT/'SourceAssets/GHS/Park/cad_layout.json',
                 ROOT/'SourceAssets/GHS/Park/site_geometry_report.json']
    protected += sorted(SOURCE.glob('*.fbx'))
    hashes = {rel(path): sha(path) for path in protected}
    routes = read(ROOT/'SourceAssets/GHS/Traffic/routes.json')
    cad = read(ROOT/'SourceAssets/GHS/Park/cad_layout.json')
    manifest = read(SOURCE/'context_transition.json')
    classification = classify_context_road_ends(routes['roads'],cad['roads'])
    removed_ends = classification['internal']
    assert {(r['road_id'],r['side']) for r in removed_ends} == EXPECTED_REMOVALS
    assert len(classification['external']) == 6
    assert {(r['road_id'],r['side']) for r in manifest['roads']} == (
        EXPECTED_REMOVALS | {(r['road_id'],r['side']) for r in classification['external']})

    # Reproduce only the two historic tails as an exact face deletion receipt.
    context.DATA.clear()
    context.base.mesh = context.mesh
    by = {r['id']:r for r in routes['roads']}
    for row in removed_ends:
        context.emit_road_end(by[row['road_id']],row['side'])
    assert set(context.DATA) == set(ROLES)
    targets = {role:Counter(face_key(data['vertices'],face) for face in data['faces'])
               for role,data in context.DATA.items()}
    context.DATA.clear()
    future_ends=context.road_ends(routes['roads'],cad['roads'])
    assert {(r['road_id'],r['side']) for r in future_ends} == {
        (r['road_id'],r['side']) for r in classification['external']}
    external_faces={role:Counter(face_key(data['vertices'],face) for face in data['faces'])
                    for role,data in context.DATA.items()}

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    names = ['SM_GHSContextTransition_'+role for role in ROLES]
    with bpy.data.libraries.load(str(original_blend),link=False) as (_, destination):
        destination.objects = names
    originals = dict(zip(ROLES,destination.objects))
    assert all(originals.values())
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=1.
    assets=[]
    for role in ROLES:
        original = originals[role]
        assert all(abs(original.matrix_world[r][c]-(1 if r==c else 0))<1e-8
                   for r in range(4) for c in range(4))
        source = original.data
        assert len(source.color_attributes)==1
        edge = source.color_attributes['EdgeFade']
        assert edge.domain=='POINT' and edge.data_type=='FLOAT_COLOR'
        vertices=[tuple(v.co) for v in source.vertices]
        expected_remove=targets[role]
        pending=expected_remove.copy()
        kept=[];removed=[]
        for face in source.polygons:
            key=face_key(vertices,face.vertices)
            if pending[key]:
                pending[key]-=1
                removed.append(face.index)
            else:
                kept.append(face)
        assert not +pending, (role,'Expected exact source faces missing',sum((+pending).values()))
        assert len(removed)==sum(expected_remove.values()) and removed
        used=sorted({i for face in kept for i in face.vertices})
        indices={old:new for new,old in enumerate(used)}
        name='SM_GHSRoadTerminal_'+role
        mesh=bpy.data.meshes.new(name)
        mesh.from_pydata([vertices[i] for i in used],[],
                         [tuple(indices[i] for i in face.vertices) for face in kept])
        mesh.update()
        assert not mesh.validate(),(role,'Unexpected geometry repair')
        for mat in source.materials:
            mesh.materials.append(mat)
        color=mesh.color_attributes.new(name='EdgeFade',type='FLOAT_COLOR',domain='POINT')
        mesh.color_attributes.active_color=color
        for new,old in enumerate(used):
            color.data[new].color=edge.data[old].color
        for face,old in zip(mesh.polygons,kept):
            face.material_index=old.material_index
            face.use_smooth=old.use_smooth
        expected_records=Counter(face_record(source,face) for face in kept)
        actual_records=Counter(face_record(mesh,face) for face in mesh.polygons)
        assert expected_records==actual_records,(role,'Retained geometry or color changed')
        original_faces=Counter(face_key(vertices,f.vertices) for f in source.polygons)
        current_vertices=[tuple(v.co) for v in mesh.vertices]
        current_faces=Counter(face_key(current_vertices,f.vertices) for f in mesh.polygons)
        assert original_faces-expected_remove==current_faces
        if role=='Landscape':
            assert not (external_faces[role]-current_faces),'An external green shoulder was removed'
        else:
            assert external_faces[role]==current_faces,(role,'Future builder differs from repaired mesh')

        obj=bpy.data.objects.new(name,mesh)
        bpy.context.collection.objects.link(obj)
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True);bpy.context.view_layer.objects.active=obj
        fbx=OUT/(name+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
            axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
            mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False,colors_type='LINEAR')
        mesh.calc_loop_triangles()
        low=[min(v.co[i] for v in mesh.vertices) for i in range(3)]
        high=[max(v.co[i] for v in mesh.vertices) for i in range(3)]
        assets.append(dict(name=name,role=role,fbx=rel(fbx),sha256=sha(fbx),
            source_mesh=original.name,vertices=len(mesh.vertices),triangles=len(mesh.loop_triangles),
            source_faces=len(source.polygons),removed_faces=len(removed),retained_faces=len(kept),
            removed_source_face_indices=removed,
            bounds_ue_cm=dict(min=[low[0]*100,-high[1]*100,low[2]*100],
                              max=[high[0]*100,-low[1]*100,high[2]*100]),
            edge_fade_range=[min(c.color[0] for c in color.data),max(c.color[0] for c in color.data)],
            material_slots=[m.name for m in mesh.materials],
            retained_face_coordinates_and_vertex_colors_exact=True))
    output_blend=OUT/'GHS_RoadTerminal_JunctionFix.blend'
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    assert hashes=={path:sha(ROOT/path) for path in hashes},'Protected source changed'
    report=dict(version=1,success=True,scope='Remove only two internal Sycamore continuation tails',
        meshes=assets,removed_internal_endpoints=removed_ends,
        remaining_external_endpoints=classification['external'],
        source_manifest=rel(SOURCE/'context_transition.json'),
        blend=rel(output_blend),blend_sha256=sha(output_blend),
        protected_source_sha256=hashes,original_assets_unchanged=True,
        islands_preserved=True,traffic_routes_unchanged=True,
        existing_retained_face_coordinates_and_vertex_colors_exact=True)
    (OUT/'road_terminal_junction_fix.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('GHS_ROAD_TERMINAL_JUNCTION_FIXED '+json.dumps({
        'meshes':[{k:r[k] for k in ('role','triangles','removed_faces','retained_faces')} for r in assets],
        'remaining_endpoints':len(classification['external']),'protected_sources':len(hashes)}))


if __name__=='__main__':
    main()
