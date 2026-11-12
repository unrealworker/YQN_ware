"""CAD glazing and local wall aperture delta, built offline after architecture patch.

No earlier source mesh is overwritten. Read current exact actor identities from
the first-apply snapshot. Keep the existing blue glass/aluminium material roles.
"""
from pathlib import Path
import collections
import gzip
import json
import math
import sys
import bpy

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_reference_shell_v4_lib import Geometry
from build_mpr_interior_architecture_patch_20261112 import subtract_box,box_volume
OUT=ROOT/'SourceAssets/MPR/interior_cad_20261112/windows'


def bounds(points):
    return [[min(p[i] for p in points),max(p[i] for p in points)] for i in (0,1)]


def panes_from_cad(rows,footprint):
    frames=[]
    for row in rows:
        if row['type']!='LWPOLYLINE':continue
        bb=bounds(row['points_m']);size=[b-a for a,b in bb]
        if .02<min(size)<.08 and .09<max(size)<.14:
            axis=0 if size[0]<size[1] else 1
            frames.append(dict(axis=axis,fixed=sum(bb[1-axis])/2,bounds=bb,source_handles=row['source_handles']))
    panes=[];used=set()
    for row in rows:
        if row['type']!='LINE':continue
        a,b=row['points_m'];axis=0 if abs(a[1]-b[1])<.001 else 1 if abs(a[0]-b[0])<.001 else None
        if axis is None:continue
        fixed=(a[1-axis]+b[1-axis])/2;lo,hi=sorted([a[axis],b[axis]])
        matching=[f for f in frames if f['axis']==axis and abs(f['fixed']-fixed)<.001]
        if matching and hi-lo>.2:
            panes.append(dict(axis=axis,fixed=fixed,lo=lo,hi=hi,source_handles=row['source_handles'],
                              evidence='glass centre LINE aligned with measured parallel frame cross sections'))
            used.add(row['source_handles'][-1])
    assert len(panes)==92
    # Nine unambiguous short office/sliding-window line segments have no normal
    # three-line extrusion symbol. They are explicit A-WIND geometry, adjoining
    # measured jambs; include them rather than inventing repeated window bays.
    special={'2E1061','2E1062','2E1072','2E107C','2E1108','2E1109','2E110A','2E1475','2E1476'}
    for row in rows:
        if row['source_handles'][-1] in special:
            a,b=row['points_m'];axis=0 if abs(a[1]-b[1])<.001 else 1
            lo,hi=sorted([a[axis],b[axis]])
            panes.append(dict(axis=axis,fixed=(a[1-axis]+b[1-axis])/2,lo=lo,hi=hi,
                source_handles=row['source_handles'],evidence='explicit interior/sliding-window line; frame thickness retained as display detail'))
    rectangle=next(r for r in rows if r['source_handles'][-1]=='2E09AA')
    bb=bounds(rectangle['points_m'])
    panes.append(dict(axis=0,fixed=sum(bb[1])/2,lo=bb[0][0],hi=bb[0][1],source_handles=rectangle['source_handles'],
                      evidence='closed0.9144x0.127m interior window rectangle'))
    assert len(panes)==102
    for pane in panes:
        axis=pane['axis'];center=[0.,0.];center[axis]=(pane['lo']+pane['hi'])/2;center[1-axis]=pane['fixed']
        edge=None
        for i,(a,b) in enumerate(zip(footprint,footprint[1:]+footprint[:1])):
            if abs(a[1-axis]-b[1-axis])>.001:continue
            if min(a[axis],b[axis])<=center[axis]<=max(a[axis],b[axis]) and abs(center[1-axis]-a[1-axis])<.35:
                edge=i;break
        pane['exterior_edge']=edge
        pane['frame_lo']=pane['lo']-.0508;pane['frame_hi']=pane['hi']+.0508
        # Current exterior frame is z1.325..3.875. Indoor office walls are3.3m,
        # so their new frame is capped at3.2m; height remains an explicit estimate.
        pane['z0']=1.325;pane['z1']=3.875 if edge is not None else 3.2
        pane['frame_depth_m']=.1143
        if edge is not None:
            pane['wall_fixed']=footprint[edge][1-axis]
            # Confirm the rough opening ends from actual exterior wall vertices.
            pane['rough_opening_end_verification']='measured U-profile outer edges and adjacent exterior wall jambs'
    assert sum(p['exterior_edge'] is not None for p in panes)==41
    return panes,frames


def template_boxes(obj):
    mesh=obj.data;uv=mesh.uv_layers.active
    assert len(mesh.vertices)%8==0 and len(mesh.polygons)==len(mesh.vertices)//8*6
    for start in range(0,len(mesh.vertices),8):
        vertices=[list(mesh.vertices[i].co) for i in range(start,start+8)]
        faces=list(mesh.polygons[start//8*6:(start//8+1)*6])
        assert all(start<=i<start+8 for f in faces for i in f.vertices)
        roles={mesh.materials[f.material_index].name.split('.')[0] for f in faces};assert len(roles)==1
        bb=[[min(v[i] for v in vertices),max(v[i] for v in vertices)] for i in range(3)]
        yield dict(vertices=vertices,faces=[tuple(i-start for i in f.vertices) for f in faces],
            uvs=[[list(uv.data[i].uv) for i in f.loop_indices] for f in faces] if uv else None,
            role=next(iter(roles)),bounds=bb)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_extracted.json').read_text(encoding='utf8'))
    layout=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
    rows=[r for r in source['architecture'] if r['layer']=='A-WIND']
    panes,frames=panes_from_cad(rows,layout['footprint_outline_m'])
    exterior_lines=[r for r in source['architecture'] if r['layer']=='A-WALL-EXT' and r['type']=='LINE']
    for pane in panes:
        if pane['exterior_edge'] is None:continue
        axis=pane['axis'];normal=1-axis;jamb_handles=[]
        for end in (pane['frame_lo'],pane['frame_hi']):
            jambs=[r for r in exterior_lines if all(abs(p[axis]-end)<.001 and abs(p[normal]-pane['wall_fixed'])<.4 for p in r['points_m'])]
            assert jambs,(pane['source_handles'],end)
            jamb_handles.append([r['source_handles'] for r in jambs])
        pane['measured_jamb_source_handles']=jamb_handles
    baseline=json.load(gzip.open(ROOT/'Saved/MPR/interior_cad_20261112/after.json.gz','rt',encoding='utf8'))
    old_manifest=json.loads((ROOT/'SourceAssets/MPR/reference_v4/architecture/reference_shell_manifest.json').read_text(encoding='utf8'))
    roles=('MPR4_FacadeWhite','MPR4_IndustrialBlue','MPR4_JointSeal','MPR4_GlassBlue','MPR4_Aluminium')
    materials={r:old_manifest['materials'][r] for r in roles};materials['Porcelain']=dict(color=[.83,.85,.88],roughness=.76)
    g=Geometry(materials);name='SM_MPR_CAD_WindowSystem_20261112'
    # Merge touching top/bottom frame rails and deduplicate shared mullions.
    posts={};rails=collections.defaultdict(list)
    for pane in panes:
        axis,fixed,lo,hi=pane['axis'],pane['fixed'],pane['lo'],pane['hi'];z0,z1=pane['z0'],pane['z1']
        def pt(t):return (t,fixed) if axis==0 else (fixed,t)
        g.segment(name,'MPR4_GlassBlue',pt(lo),pt(hi),.022,(z0+z1)/2,z1-z0-.11)
        for t in (lo-.0254,hi+.0254):
            key=(axis,round(fixed,5),round(t,5),z0,z1)
            posts[key]=(pt(t),axis,z0,z1)
        for z in (z0+.0254,z1-.0254):rails[(axis,round(fixed,5),z)].append((lo-.0508,hi+.0508))
        if pane['exterior_edge'] is not None:
            # The current facade is centred on the plan outline; CAD glazing is
            # recessed towards the inner face. Close that real depth with jamb
            # liners instead of leaving the frame floating behind the wall.
            wall=pane['wall_fixed'];normal_axis=1-axis
            d0=min(wall-.17,fixed-.05715);d1=max(wall+.17,fixed+.05715)
            for t in (lo-.0408,hi+.0408):
                center=[0.,0.,(z0+z1)/2];size=[0.,0.,z1-z0]
                center[axis]=t;center[normal_axis]=(d0+d1)/2;size[axis]=.02;size[normal_axis]=d1-d0
                g.box(name,'MPR4_Aluminium',center,size)
            for z in (z0+.01,z1-.01):
                center=[0.,0.,z];size=[0.,0.,.02]
                center[axis]=(lo+hi)/2;center[normal_axis]=(d0+d1)/2;size[axis]=hi-lo+.1016;size[normal_axis]=d1-d0
                g.box(name,'MPR4_Aluminium',center,size)
    for (axis,fixed,t,z0,z1),(p,_,_,_) in posts.items():
        size=(.0508,.1143,z1-z0) if axis==0 else (.1143,.0508,z1-z0)
        g.box(name,'MPR4_Aluminium',(*p,(z0+z1)/2),size)
    for (axis,fixed,z),intervals in rails.items():
        merged=[]
        for lo,hi in sorted(intervals):
            if merged and lo<=merged[-1][1]+.0001:merged[-1][1]=max(merged[-1][1],hi)
            else:merged.append([lo,hi])
        for lo,hi in merged:
            a,b=((lo,fixed),(hi,fixed)) if axis==0 else ((fixed,lo),(fixed,hi))
            g.segment(name,'MPR4_Aluminium',a,b,.1143,z,.0508)
    candidates=[]
    for side in sorted({p['exterior_edge'] for p in panes if p['exterior_edge'] is not None}):
        first_patched=side in (5,15)
        candidates.append(dict(actor_label=f'MPR4_Facade_{side:02}',side=side,
            source_blend='SourceAssets/MPR/interior_cad_20261112/architecture/mpr_reference_shell.blend' if first_patched else 'SourceAssets/MPR/reference_v4/architecture/mpr_reference_shell.blend',
            source_mesh=f'SM_MPR_CAD_Facade_{side:02}_20261112' if first_patched else f'SM_MPR4_Facade_{side:02}',
            new_mesh=f'SM_MPR_CAD_WindowFacade_{side:02}_20261112'))
    candidates.extend([
        dict(actor_label='MPR_OfficePartitions',side=None,source_blend='SourceAssets/MPR/architecture/mpr_architecture.blend',
             source_mesh='SM_MPR_OfficePartitions',new_mesh='SM_MPR_CAD_WindowPartitions_20261112'),
        dict(actor_label='MPR_CAD_PartitionCompletion_20261112',side=None,source_blend='SourceAssets/MPR/interior_cad_20261112/architecture/mpr_reference_shell.blend',
             source_mesh='SM_MPR_CAD_PartitionCompletion_20261112',new_mesh='SM_MPR_CAD_WindowPartitionCompletion_20261112'),
    ])
    replacements=[];cut_checks=[]
    for candidate in candidates:
        with bpy.data.libraries.load(str(ROOT/candidate['source_blend']),link=False) as (available,loaded):
            assert candidate['source_mesh'] in available.objects
            loaded.objects=[candidate['source_mesh']]
        obj=loaded.objects[0];boxes=list(template_boxes(obj))
        relevant=[p for p in panes if p['exterior_edge']==candidate['side']]
        cutters=[]
        for pane in relevant:
            axis=pane['axis'];c=[[-1e4,1e4] for _ in range(3)]
            c[axis]=[pane['frame_lo'],pane['frame_hi']]
            fixed=pane.get('wall_fixed',pane['fixed']);c[1-axis]=[fixed-.4,fixed+.4];c[2]=[pane['z0'],pane['z1']]
            cutters.append(c)
        touched=0;removed=0
        for box in boxes:
            pieces=[box['bounds']]
            for cutter in cutters:pieces=[p for b in pieces for p in subtract_box(b,cutter)]
            removed+=box_volume(box['bounds'])-sum(box_volume(b) for b in pieces)
            if pieces==[box['bounds']]:
                g.mesh(candidate['new_mesh'],box['role'],box['vertices'],box['faces'],box['uvs'])
            else:
                touched+=1
                # Source vertices are float32; exact CAD cutter coordinates can
                # leave micrometre slivers which collapse during FBX roundtrip.
                # Discard only sub0.05mm subtraction remnants, never a source box.
                for b in pieces:
                    if min(hi-lo for lo,hi in b)<.00005:continue
                    g.box(candidate['new_mesh'],box['role'],[(lo+hi)/2 for lo,hi in b],[hi-lo for lo,hi in b])
        if not touched:
            del g.data[candidate['new_mesh']]
            continue
        actor=next(a for a in baseline['actors'] if a['label']==candidate['actor_label'])
        component=next(c for c in actor['components'] if c.get('mesh'))
        replacements.append(dict(actor_guid=actor['guid'],actor_label=actor['label'],old_mesh=component['mesh'],
            new_mesh_name=candidate['new_mesh'],source_mesh=candidate['source_mesh'],source_blend=candidate['source_blend'],
            preserve_material_overrides=component['materials'],side=candidate['side'],windows=relevant))
        cut_checks.append(dict(actor_label=actor['label'],source_boxes=len(boxes),touched_boxes=touched,removed_volume_m3=removed))
    removals=[]
    for label in ('MPR_OfficeGlazing','MPR4_OfficeGlazing_West','MPR4_OfficeGlazing_East'):
        actor=next(a for a in baseline['actors'] if a['label']==label)
        removals.append(dict(actor_guid=actor['guid'],actor_label=label,
            expected_meshes=[c['mesh'] for c in actor['components'] if c.get('mesh')],
            reason='Old schematic glazing band superseded by source-CAD windows; remove duplicate visible layers.'))
    for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    for mat in list(bpy.data.materials):bpy.data.materials.remove(mat,do_unlink=True)
    metadata=dict(scope='CAD windows only; existing architecture/source assets unchanged.',
        source_sha256='c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863',
        baseline='Saved/MPR/interior_cad_20261112/after.json.gz',panes=panes,
        pane_count=102,external_rough_opening_count=41,
        additions=[dict(mesh_name=name,location_cm=[0,0,0])],replacements=replacements,removals=removals,
        cut_checks=cut_checks,height_basis='Display frame1.325..3.875m matches current V4 glazing; indoor3.3m office walls cap frames at3.2m. CAD establishes plan, not sill/window elevations.',
        preservation='Use existing patched facade05/15 as source, retain pedestrian doors and74 large doors. No sorting/worker/cargo/camera/runtime changes.',
        material_bindings={r:'/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+r for r in ('MPR4_GlassBlue','MPR4_Aluminium','MPR4_JointSeal')})
    manifest=g.export(OUT,metadata,{})
    (OUT/'cad_windows_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(manifest=str(OUT/'cad_windows_manifest.json'),mesh_count=len(manifest['meshes']),
                         panes=102,exterior_openings=41,replaced_actors=[r['actor_label'] for r in replacements],removed_glazing_actors=3),ensure_ascii=False))


if __name__=='__main__':main()
