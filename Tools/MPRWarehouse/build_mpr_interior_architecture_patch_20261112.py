"""Build CAD-verified partition completion and pedestrian doors in Blender.

The existing building, partitions, equipment, workers and map are not opened or
rewritten. Run the audit first. Importing/placing the generated mesh is a
separate, parent-controlled editor action.
"""
import json
import gzip
import hashlib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Tools/MPRWarehouse'))
import bpy
from mpr_reference_shell_v4_lib import Geometry

AUDIT = ROOT/'Saved/MPR/interior_cad_20261112/interior_truth'
OUT = ROOT/'SourceAssets/MPR/interior_cad_20261112/architecture'
SOURCE_BLEND = ROOT/'SourceAssets/MPR/reference_v4/architecture/mpr_reference_shell.blend'
EXPECTED = {
    ('2E093B', '2E0ABA'), ('2E0948', '2E0A33'), ('2E0980', '2E0A73'),
    ('2E098A', '2E0A36'), ('2E0A6E', '2E0A72'), ('2E103E', '2E1040'),
}


def subtract_box(bounds, cutter):
    """Exact disjoint AABB subtraction, retaining source boxes outside the cut."""
    low, high = [v[0] for v in bounds], [v[1] for v in bounds]
    ilow=[max(low[i],cutter[i][0]) for i in range(3)]
    ihigh=[min(high[i],cutter[i][1]) for i in range(3)]
    if any(ihigh[i]-ilow[i]<1e-7 for i in range(3)):
        return [bounds]
    result=[]
    for axis in range(3):
        if ilow[axis]-low[axis]>1e-7:
            result.append([[low[i],ilow[i] if i==axis else high[i]] for i in range(3)])
        if high[axis]-ihigh[axis]>1e-7:
            result.append([[ihigh[i] if i==axis else low[i],high[i]] for i in range(3)])
        low[axis]=ilow[axis]
        high[axis]=ihigh[axis]
    return result


def box_volume(bounds):
    return math.prod(b-a for a,b in bounds)


def source_boxes(obj):
    """The V4 facades are separate eight-vertex box primitives; assert this."""
    mesh=obj.data
    assert len(mesh.vertices)%8==0 and len(mesh.polygons)==len(mesh.vertices)//8*6
    uv=mesh.uv_layers.active
    for start in range(0,len(mesh.vertices),8):
        vertices=[list(mesh.vertices[i].co) for i in range(start,start+8)]
        faces=list(mesh.polygons[(start//8)*6:(start//8+1)*6])
        assert all(start<=i<start+8 for f in faces for i in f.vertices)
        roles={mesh.materials[f.material_index].name.split('.')[0] for f in faces}
        assert len(roles)==1
        bounds=[[min(p[i] for p in vertices),max(p[i] for p in vertices)] for i in range(3)]
        assert all(any(abs(p[i]-v)<.00005 for v in bounds[i]) for p in vertices for i in range(3))
        yield dict(vertices=vertices,faces=[tuple(i-start for i in f.vertices) for f in faces],
                   uvs=[[list(uv.data[i].uv) for i in f.loop_indices] for f in faces],
                   role=next(iter(roles)),bounds=bounds)


def door_groups(doors):
    """Adjacent opposing door leaves share one frame, without a centre post."""
    remaining=list(doors)
    groups=[]
    while remaining:
        first=remaining.pop(0)
        a,b=first['opening_endpoints_m']
        axis=0 if abs(a[1]-b[1])<.001 else 1
        group=dict(axis=axis,fixed=first['opening_center_m'][1-axis],
                   lo=min(a[axis],b[axis]),hi=max(a[axis],b[axis]),leaves=[first])
        again=True
        while again:
            again=False
            for d in list(remaining):
                pa,pb=d['opening_endpoints_m']
                if abs(pa[1-axis]-group['fixed'])>.001 or abs(pb[1-axis]-group['fixed'])>.001:
                    continue
                lo,hi=sorted([pa[axis],pb[axis]])
                if lo<=group['hi']+.001 and hi>=group['lo']-.001:
                    group['lo']=min(lo,group['lo']);group['hi']=max(hi,group['hi'])
                    group['leaves'].append(d);remaining.remove(d);again=True
        groups.append(group)
    return groups


def add_door_group(g,group,name,external):
    axis,fixed=group['axis'],group['fixed']
    # Exterior jamb positions are measured; interior frame depth is a retained
    # presentation detail. Door height is explicitly not a surveyed dimension.
    lo,hi=group['lo'],group['hi']
    if not external:
        lo-=.0508;hi+=.0508
    def pt(t):return (t,fixed) if axis==0 else (fixed,t)
    depth=.23 if external else .16
    for a,b in [(lo,lo+.0508),(hi-.0508,hi)]:
        g.segment(name,'Cobalt',pt(a),pt(b),depth,1.075,2.15)
    g.segment(name,'Cobalt',pt(lo),pt(hi),depth,2.125,.05)
    for leaf in group['leaves']:
        a,b=leaf['opening_endpoints_m'];length=math.dist(a,b);u=[(b[i]-a[i])/length for i in (0,1)]
        aa=[a[i]+u[i]*.006 for i in (0,1)];bb=[b[i]-u[i]*.006 for i in (0,1)]
        g.segment(name,'Porcelain',aa,bb,.038,1.055,2.08)
        p=[b[i]-u[i]*.10 for i in (0,1)]
        # Handles on both faces; no logo, sign or unverified room designation.
        normal=[-u[1],u[0]]
        for side in (-1,1):
            q=[p[i]+normal[i]*side*.04 for i in (0,1)]
            end=[q[i]-u[i]*.10 for i in (0,1)]
            g.segment(name,'Metal',q,end,.018,.98,.018)


def main():
    report = json.loads((AUDIT/'audit_report.json').read_text(encoding='utf8'))
    candidates = json.loads((AUDIT/'partition_missing_candidates.json').read_text(encoding='utf8'))
    assert report['source_sha256']=='c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863'
    actual = {tuple(row['source_face_handles'][i][-1] for i in (0,1)) for row in candidates}
    assert actual == EXPECTED, 'Source wall pairs changed; repeat plan review.'
    assert all(abs(row['length_m']-row['uncovered_length_m'])<.0001 for row in candidates)
    source_manifest=json.loads((SOURCE_BLEND.parent/'reference_shell_manifest.json').read_text(encoding='utf8'))
    materials={k:source_manifest['materials'][k] for k in ('MPR4_IndustrialBlue','MPR4_FacadeWhite','MPR4_JointSeal')}
    materials.update(Porcelain=dict(color=[.83,.85,.88],roughness=.76),
                     Cobalt=dict(color=[.018,.075,.51],roughness=.76),
                     Metal=dict(color=[.43,.49,.57],roughness=.76))
    g = Geometry(materials)
    for row in candidates:
        a, b = row['points_m']
        assert math.dist(a,b)>.5 and .12<row['thickness_m']<.14
        g.segment('SM_MPR_CAD_PartitionCompletion_20261112','Porcelain',a,b,row['thickness_m'],1.65,3.3)
    doors=json.loads((AUDIT/'pedestrian_openings.json').read_text(encoding='utf8'))
    # Derive exterior rough openings from A-WALL-EXT jamb endpoints, NOT the
    # swing-symbol bounding box and NOT the narrower 36-inch door leaf.
    architecture=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_extracted.json').read_text(encoding='utf8'))['architecture']
    external_groups=[]
    for group in door_groups([d for d in doors if d['exterior_edge'] is not None]):
        axis,fixed=group['axis'],group['fixed'];candidates_jamb=[]
        for row in architecture:
            if row['layer']!='A-WALL-EXT':continue
            for point in row['points_m']:
                if abs(point[1-axis]-fixed)>.001:continue
                for side in ('lo','hi'):
                    dist=group[side]-point[axis] if side=='lo' else point[axis]-group[side]
                    if .002<dist<.12:candidates_jamb.append((side,dist,point[axis],row['source_handles']))
        left=min((c for c in candidates_jamb if c[0]=='lo'),key=lambda c:c[1])
        right=min((c for c in candidates_jamb if c[0]=='hi'),key=lambda c:c[1])
        group.update(lo=left[2],hi=right[2],jamb_source_handles=[left[3],right[3]],
                     edge=group['leaves'][0]['exterior_edge'])
        assert abs((group['hi']-group['lo'])-(len(group['leaves'])*.9144+.1016))<.0002
        external_groups.append(group)
    assert len(external_groups)==32 and sum(len(x['leaves']) for x in external_groups)==34
    affected=sorted({d['edge'] for d in external_groups})
    source_names=[f'SM_MPR4_Facade_{side:02}' for side in affected]
    with bpy.data.libraries.load(str(SOURCE_BLEND),link=False) as (available,loaded):
        assert all(name in available.objects for name in source_names)
        loaded.objects=source_names
    originals={obj.name:obj for obj in loaded.objects}
    baseline=json.load(gzip.open(ROOT/'Saved/MPR/interior_cad_20261112/preservation/baseline.json.gz','rt',encoding='utf8'))
    replacements=[]
    subtract_checks=[]
    for side in affected:
        old_name=f'SM_MPR4_Facade_{side:02}';new_name=f'SM_MPR_CAD_Facade_{side:02}_20261112'
        source=originals[old_name];boxes=list(source_boxes(source))
        side_doors=[d for d in external_groups if d['edge']==side]
        cutters=[]
        for d in side_doors:
            c=[[-10000,10000] for _ in range(3)]
            c[d['axis']]=[d['lo'],d['hi']]
            c[1-d['axis']]=[d['fixed']-.6,d['fixed']+.6]
            c[2]=[-.000001,2.15]
            cutters.append(c)
        original_volume=remaining_volume=0
        touched=unchanged=0
        for box in boxes:
            original_volume+=box_volume(box['bounds'])
            pieces=[box['bounds']]
            for cutter in cutters:
                pieces=[p for b in pieces for p in subtract_box(b,cutter)]
            remaining_volume+=sum(box_volume(b) for b in pieces)
            if pieces==[box['bounds']]:
                g.mesh(new_name,box['role'],box['vertices'],box['faces'],box['uvs']);unchanged+=1
            else:
                touched+=1
                for b in pieces:
                    center=[(lo+hi)/2 for lo,hi in b];size=[hi-lo for lo,hi in b]
                    g.box(new_name,box['role'],center,size)
            for p in pieces:
                for cutter in cutters:
                    assert any(min(p[i][1],cutter[i][1])-max(p[i][0],cutter[i][0])<1e-7 for i in range(3))
        expected=sum((d['hi']-d['lo'])*.3048*2.15 for d in side_doors)
        removed=original_volume-remaining_volume
        assert removed>=expected-.001 and removed<expected+.02, (side,removed,expected)
        actor=next(a for a in baseline['actors'] if a['label']==f'MPR4_Facade_{side:02}')
        old_mesh=next(c['mesh'] for c in actor['components'] if c.get('mesh'))
        replacements.append(dict(actor_guid=actor['guid'],actor_label=actor['label'],old_mesh=old_mesh,
                                 new_mesh_name=new_name,new_mesh_package='/Game/MPRWarehouse/InteriorCAD20261112/Architecture/Meshes/'+new_name,
                                 action='replace mesh on this exact existing actor; preserve transform, tags, material overrides, visibility and folder',
                                 exterior_door_groups=side_doors))
        subtract_checks.append(dict(side=side,source_boxes=len(boxes),unchanged_boxes=unchanged,touched_boxes=touched,
                                    original_volume_m3=original_volume,new_volume_m3=remaining_volume,
                                    removed_volume_m3=removed,measured_wall_opening_volume_m3=expected,
                                    all_opening_interiors_empty=True,unaffected_boxes_vertex_and_uv_exact=True))
    for group in external_groups:
        add_door_group(g,group,'SM_MPR_CAD_ExteriorPedestrianDoors_20261112',True)
    internal=door_groups([d for d in doors if d['exterior_edge'] is None])
    # Interior door leaves follow explicit source inserts. The six missing wall
    # segments are additive; arbitrary broad wall reconstruction is not used.
    for group in internal:
        add_door_group(g,group,'SM_MPR_CAD_InteriorPedestrianDoors_20261112',False)
    metadata=dict(
        source_sha256=report['source_sha256'],source_wall_pairs=candidates,
        scope='Six additive partitions, 80 measured pedestrian door leaves, and local subtraction of 32 rough door openings from seven existing V4 facade meshes.',
        coordinate_system='CAD-local metres. Existing import convention mirrors Y once.',
        measured_total_length_m=sum(row['length_m'] for row in candidates),
        height_m=3.3,height_basis='Preserve adjacent existing office-partition height; not measured in plan.',
        verified_by='partition_missing_plan_overlay.png and direct original DXF entity-coordinate validation',
        source_blend_sha256=hashlib.sha256(SOURCE_BLEND.read_bytes()).hexdigest(),
        facade_replacements=replacements,subtraction_verification=subtract_checks,
        exterior_opening_count=len(external_groups),exterior_door_leaf_count=34,interior_door_leaf_count=46,
        exterior_rough_opening_heights_m=2.15,door_leaf_height_m=2.1,
        door_height_basis='Visualization estimate. Source CAD explicitly measures plan leaf width .9144m and rough opening width1.016m/1.9304m, not elevation.',
        preserved='Unchanged source wall primitives including UVs; existing74 dock/drive-in openings; material role slots; facade bounds; roof, floor, site, worker/equipment animation and camera.',
    )
    # Source objects were loaded as read-only templates. Remove their Blender
    # datablocks now so new material slots retain the exact role names, rather
    # than receiving .001 suffixes on FBX round-trip.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material,do_unlink=True)
    manifest = g.export(OUT,metadata,{})
    final=OUT/'mpr_interior_architecture_patch.json'
    final.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    # Compact reproducible evidence, without copying the large extraction.
    (OUT/'cad_architectural_spec.json').write_text(json.dumps(dict(source_sha256=report['source_sha256'],
        missing_partition_segments=candidates,pedestrian_doors=doors,exterior_rough_openings=external_groups),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(manifest=str(final),meshes=len(manifest['meshes']),affected_facades=affected,
        added_partition_count=6,exterior_openings=32,door_leaves=80),ensure_ascii=False))


if __name__ == '__main__':
    main()
