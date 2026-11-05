"""Independent saved Blender/FBX round-trip and spatial exclusion audit."""
import sys,json,hashlib,math,traceback
from collections import defaultdict
from itertools import product
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Saved/ParkRefinement/python_deps'),str(ROOT/'Tools/MPRWarehouse')]
import bpy,numpy as np,shapely
from shapely.geometry import shape,Point,Polygon,LineString,GeometryCollection
from shapely.ops import unary_union
OUT=ROOT/'SourceAssets/MPR/extension_b50b57'
REPORT=ROOT/'Saved/MPR/extension_20261104/blender_validation.json'
report=dict(success=False,meshes=[],scope='Saved Blender geometry, independent FBX reimport, projected exclusion and tree crown clearance')
POSITION_TOLERANCE_M=.002
COLOR_TOLERANCE=.00002
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def reference_terminal_footprints(rows):
    """Reconstruct only the immutable reference's authored 29 terminal ribbons."""
    assert len(rows)==29 and len({r['id'] for r in rows})==29
    shapes=[]
    for row in rows:
        p=np.asarray(row['origin_m']);d=np.asarray(row['direction']);n=np.array([-d[1],d[0]])
        end=p+d*row['length_m'];half=row['width_m']/2
        ribbon=Polygon([p-n*half,end-n*half,end+n*half,p+n*half])
        shoulder=p+d*min(4.,row['length_m'])
        mouth=Polygon([*row['section_m'],shoulder-n*half,shoulder+n*half]).convex_hull
        shapes.append(ribbon.union(mouth))
    # Old curbs lie 28cm outside the pavement; the original batched support is
    # buffered by 50cm. This explicit 60cm grandfathering band includes both.
    return unary_union(shapes).buffer(.6)

def replacement_spatial_audit(polys,protected,original_terminals):
    """Existing terminal/tree overlaps are grandfathered, new encroachment is not."""
    new_parts=shapely.difference(polys,original_terminals)
    overlaps=shapely.area(shapely.intersection(new_parts,protected.buffer(-.025)))
    overlap=float(np.sum(overlaps))
    assert overlap<.03,('Replacement adds geometry over protected building/tree/rail outside the old frame',overlap)
    return dict(new_projection_m2=float(np.sum(shapely.area(new_parts))),
                protected_new_overlap_m2=overlap,original_terminal_margin_m=.6)

def validated_mouth_stitches(audit,terminal_rows):
    """Allow only individually recorded <=12cm mouth patches, not a frame inset."""
    frame=shape(audit['completed_frame'])
    records=audit['road_audit'].get('mouth_stitches',[])
    encoded=audit.get('mouth_stitches')
    assert encoded is not None or not records,'Missing explicit mouth_stitches geometry'
    total=shape(encoded) if encoded is not None else GeometryCollection()
    assert total.is_valid,'Invalid mouth-stitch union'
    fixed=unary_union([shape(audit['existing_buildings']).buffer(.25),
                      shape(audit['existing_tree_clearance']),shape(audit['existing_rails'])])
    originals={r['id']:r for r in terminal_rows}
    connected={r['id'] for r in audit['connections'] if r['status']=='connected'}
    assert len({r['id'] for r in records})==len(records),'Duplicate mouth-stitch records'
    pieces=[];review=[]
    for row in records:
        identity=row['id']
        assert identity in connected and identity in originals,('Unapproved mouth-stitch identity',identity)
        assert 'geometry' in row,('Mouth stitch lacks independent per-mouth geometry',identity)
        patch=shape(row['geometry'])
        assert not patch.is_empty and patch.is_valid,('Invalid mouth patch',identity)
        assert patch.difference(frame).area<1e-8,('Mouth patch extends outside its documented in-frame band',identity)
        assert abs(patch.area-row['area_m2'])<max(1e-6,patch.area*1e-6),('Mouth patch area changed',identity)
        # Full geometry containment checks depth, not only the supplied number
        # or sampled vertices. The old frame itself is never buffered inward.
        assert patch.intersection(frame.buffer(-.120001)).area<1e-8,('Mouth patch exceeds 12cm',identity)
        reference_section=LineString(originals[identity]['section_m'])
        # The frozen frame uses the raster's half-pixel outside boundary; the
        # original section is on its pixel centre line (75cm apart here). Move
        # only this section's endpoints onto that exact frame edge, preserving
        # its mouth span, rather than globally widening the allowed mask.
        section=LineString([frame.boundary.interpolate(frame.boundary.project(Point(p))).coords[0]
                            for p in originals[identity]['section_m']])
        assert patch.difference(section.buffer(.121,cap_style=3)).area<1e-7,('Patch is not local to the original road mouth',identity)
        depth=max((Point(p).distance(frame.boundary) for p in shapely.get_coordinates(patch)),default=0.)
        assert depth<=.120001 and abs(depth-row['max_in_frame_m'])<1e-6,('Mouth depth audit mismatch',identity,depth)
        protected_overlap=patch.intersection(fixed).area
        assert protected_overlap<1e-7,('Mouth patch overlaps immutable building/tree/rail',identity,protected_overlap)
        pieces.append(patch)
        review.append(dict(id=identity,area_m2=patch.area,max_in_frame_m=depth,
                           reference_section_frame_offset_m=reference_section.hausdorff_distance(section),
                           protected_object_overlap_m2=protected_overlap))
    union=unary_union(pieces) if pieces else GeometryCollection()
    assert total.symmetric_difference(union).area<1e-8,'Mouth-stitch union differs from per-mouth audit'
    return total,fixed,dict(count=len(review),area_m2=total.area,
                            maximum_in_frame_m=max((r['max_in_frame_m'] for r in review),default=0.),
                            mouths=review,frame_wide_tolerance_added=False)

def color_samples(obj):
    """World-coordinate + linear RGBA per surface corner, independent of splits.

    FBX legitimately turns POINT attributes into CORNER attributes and can split
    vertices at UV/normal seams. Polygon corners retain their multiplicity and
    avoid treating those splits as extra/missing authored vertex-color samples.
    """
    mesh=obj.data
    attribute=mesh.color_attributes.get('EdgeFade')
    assert attribute is not None,obj.name+' missing EdgeFade'
    assert attribute.domain in {'POINT','CORNER'},(obj.name,attribute.domain)
    indices=np.empty(len(mesh.loops),dtype=np.int32)
    mesh.loops.foreach_get('vertex_index',indices)
    points=np.asarray([tuple(obj.matrix_world@v.co) for v in mesh.vertices],dtype=np.float64)
    rgba=np.asarray([tuple(c.color) for c in attribute.data],dtype=np.float64)
    values=rgba[indices] if attribute.domain=='POINT' else rgba
    assert len(values)==len(indices) and len(values)>0,obj.name+' empty/incomplete color data'
    assert np.isfinite(values).all() and np.isfinite(points).all()
    assert values.min()>=-COLOR_TOLERANCE and values.max()<=1+COLOR_TOLERANCE
    assert np.max(np.abs(values[:,:3]-values[:,0,None]))<COLOR_TOLERANCE,obj.name+' fade RGB channels disagree'
    assert np.max(np.abs(values[:,3]-1))<COLOR_TOLERANCE,obj.name+' fade must remain opaque'
    return np.column_stack((points[indices],values))

def compare_color_samples(source,current,mesh_name=''):
    """Match exact sample groups with capacities; quantization only finds neighbours.

    A quantized bucket is not an interchangeable sample: nearby curb vertices
    can cross its boundary after FBX float conversion. Keep their actual values
    and use augmenting paths when a greedy match consumes another sample's only
    candidate. Every matched pair still satisfies the original 7-D tolerances.
    """
    assert source.shape==current.shape,('FBX color corner count changed',mesh_name,source.shape,current.shape)
    tolerance=np.asarray([POSITION_TOLERANCE_M]*3+[COLOR_TOLERANCE]*4)
    sv,sc=np.unique(source,axis=0,return_counts=True)
    cv,cc=np.unique(current,axis=0,return_counts=True)
    sk=np.floor(sv[:,:3]/POSITION_TOLERANCE_M).astype(np.int64)
    ck=np.floor(cv[:,:3]/POSITION_TOLERANCE_M).astype(np.int64)
    buckets=defaultdict(list)
    for i,key in enumerate(sk):buckets[tuple(key)].append(i)
    candidates=[]
    for j in range(len(cv)):
        nearby=[]
        for delta in product((-1,0,1),repeat=3):
            key=tuple(ck[j,k]+delta[k] for k in range(3))
            nearby.extend(buckets.get(key,()))
        ids=np.asarray(nearby,dtype=np.int64)
        difference=np.abs(sv[ids]-cv[j])
        ids=ids[np.all(difference<=tolerance,axis=1)]
        distance=np.linalg.norm((sv[ids]-cv[j])/tolerance,axis=1)
        candidates.append([int(i) for i in ids[np.argsort(distance,kind='stable')]])
    free=sc.copy();pending=cc.copy()
    allocations=[{} for _ in cv];clients=[{} for _ in sv]
    def assign(j,i,count):
        value=allocations[j].get(i,0)+count
        if value:
            allocations[j][i]=value;clients[i][j]=value
        else:
            allocations[j].pop(i,None);clients[i].pop(j,None)
        free[i]-=count;pending[j]-=count
    for j in sorted(range(len(cv)),key=lambda j:len(candidates[j])):
        for i in candidates[j]:
            count=min(pending[j],free[i])
            if count:assign(j,i,count)
            if not pending[j]:break
    augmentations=0
    for start in np.flatnonzero(pending):
        while pending[start]:
            parent_current={int(start):None};parent_source={}
            queue=[int(start)];destination=None
            for j in queue:
                for i in candidates[j]:
                    if i in parent_source:continue
                    parent_source[i]=j
                    if free[i]:destination=i;break
                    for other in clients[i]:
                        if other not in parent_current:
                            parent_current[other]=i;queue.append(other)
                if destination is not None:break
            if destination is None:break
            count=min(pending[start],free[destination]);adds=[];removes=[];i=destination
            while True:
                j=parent_source[i];adds.append((j,i))
                if j==start:break
                old=parent_current[j];removes.append((j,old))
                count=min(count,allocations[j][old]);i=old
            for j,i in removes:assign(j,i,-count)
            for j,i in adds:assign(j,i,count)
            augmentations+=1
    if np.any(free) or np.any(pending):
        def residual(values,counts):
            return [dict(position_m=values[i,:3].tolist(),rgba=values[i,3:].tolist(),
                         count=int(counts[i])) for i in np.flatnonzero(counts)[:12]]
        raise AssertionError(('FBX coordinate/color distribution changed',mesh_name,
            dict(source_remaining=int(free.sum()),fbx_remaining=int(pending.sum()),
                 source_samples=residual(sv,free),fbx_samples=residual(cv,pending))))
    adjacent_matches=0;max_position_error=0.;max_color_error=0.
    rounded_source=np.rint(sv/tolerance).astype(np.int64)
    rounded_current=np.rint(cv/tolerance).astype(np.int64)
    for j,matches in enumerate(allocations):
        for i,count in matches.items():
            difference=np.abs(sv[i]-cv[j])
            max_position_error=max(max_position_error,float(difference[:3].max()))
            max_color_error=max(max_color_error,float(difference[3:].max()))
            if np.any(rounded_source[i]!=rounded_current[j]):adjacent_matches+=int(count)
    old_range=np.stack((source[:,3:].min(axis=0),source[:,3:].max(axis=0)))
    new_range=np.stack((current[:,3:].min(axis=0),current[:,3:].max(axis=0)))
    assert np.max(np.abs(old_range-new_range))<=COLOR_TOLERANCE,'FBX color range changed'
    return dict(corner_samples=len(source),coordinate_tolerance_m=POSITION_TOLERANCE_M,
                rgba_tolerance=COLOR_TOLERANCE,neighbor_bucket_samples=adjacent_matches,
                maximum_matched_axis_error_m=max_position_error,maximum_matched_rgba_error=max_color_error,
                capacity_augmentations=augmentations,
                source_rgba_range=old_range.tolist(),fbx_rgba_range=new_range.tolist(),
                coordinate_color_multiset_equal=True)

def connection_supports(audit,terminal_rows):
    connected=[r for r in audit['connections'] if r['status']=='connected']
    outer=[r for r in audit['connections'] if r['status']=='preserved_outer_terminal']
    assert len(connected)==26 and len({r['id'] for r in connected})==26,'Expected 26 explicit connection bands'
    assert {r['id'] for r in outer}=={'SourceTerminal_11','SourceTerminal_12','SourceTerminal_13'}
    assert all(not r['fade_allowed'] for r in connected) and all(r['fade_allowed'] for r in outer)
    original={r['id']:r for r in terminal_rows}
    supports={r['id']:LineString(r['path_m']).buffer(
                  max(r['start_width_m'],r['source_width_m'])/2+.85,cap_style=3)
              for r in connected}
    outer_shapes=[]
    for connection in outer:
        row=original[connection['id']]
        assert np.max(np.abs(np.asarray(row['origin_m'])-connection['origin_m']))<.001
        assert np.max(np.abs(np.asarray(row['end_m'])-connection['end_m']))<.001
        p=np.asarray(row['origin_m']);d=np.asarray(row['direction']);n=np.array([-d[1],d[0]])
        end=p+d*row['length_m'];half=row['width_m']/2
        ribbon=Polygon([p-n*half,end-n*half,end+n*half,p+n*half])
        shoulder=p+d*min(4.,row['length_m'])
        mouth=Polygon([*row['section_m'],shoulder-n*half,shoulder+n*half]).convex_hull
        outer_shapes.append(ribbon.union(mouth).buffer(.85))
    return supports,unary_union(outer_shapes)

def verify_fade_regions(samples,row,frame,outer_frame,supports,outer_tails):
    points=shapely.points(samples[:,:2]);red=samples[:,3]
    outer=shapely.covers(outer_tails,points)
    connected_counts={}
    for identity,support in supports.items():
        mask=shapely.covers(support,points)&~outer
        count=int(mask.sum())
        if row.get('replacement_only') and count:
            assert np.max(red[mask])<.001,(row['name'],identity,'connected band must be opaque')
        connected_counts[identity]=count
    if row.get('replacement_only'):
        assert not np.any((red>.001)&~outer),row['name']+' fades outside the three authorized outer tails'
    else:
        near=(shapely.distance(points,frame.boundary)<3)&~outer
        assert not np.any(red[near]>.001),row['name']+' fades at the old/new boundary'
        fading=red>.001
        assert not np.any(shapely.distance(points[fading],outer_frame.boundary)>30.002),row['name']+' fades away from the outer edge'
    return dict(connected_corner_samples=connected_counts,outer_tail_corner_samples=int(outer.sum()),
                opaque_connected_bands=True)
def run():
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    audit=json.loads((OUT/'geometry_audit.json').read_text(encoding='utf-8'))
    protect=shape(audit['protected_geometry'])
    frame=shape(audit['completed_frame'])
    outer_frame=shape(audit['source_frame'])
    old_site=json.loads((ROOT/'SourceAssets/MPR/reference_v4/site/manifest.json').read_text(encoding='utf-8'))
    mouth_stitches,fixed_objects,mouth_report=validated_mouth_stitches(audit,old_site['outside_plan_continuations'])
    report['authorized_mouth_stitches']=mouth_report
    protected_frame=frame.difference(mouth_stitches)
    replacement_protection=unary_union([protected_frame,fixed_objects])
    supports,outer_tails=connection_supports(audit,old_site['outside_plan_continuations'])
    original_terminals=reference_terminal_footprints(old_site['outside_plan_continuations'])
    source_colors={}
    source=OUT/'inputs/topoexport-B50B57.blend'
    assert sha(source)==manifest['source_blend_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/manifest['blend']),load_ui=False,use_scripts=False)
    for row in manifest['meshes']:
        obj=bpy.data.objects.get(row['name']);assert obj is not None,row['name']
        mesh=obj.data;mesh.calc_loop_triangles()
        assert len(mesh.loop_triangles)==row['triangles'],row['name']
        assert len(mesh.uv_layers)>0,row['name']+' missing UV'
        assert all(math.isfinite(v) for p in mesh.vertices for v in p.co)
        vv=np.array([tuple(obj.matrix_world@v.co) for v in mesh.vertices])
        tris=np.array([list(t.vertices) for t in mesh.loop_triangles])
        xy=vv[tris,:2]
        edge_a,edge_b=xy[:,1]-xy[:,0],xy[:,2]-xy[:,0]
        areas=np.abs(edge_a[:,0]*edge_b[:,1]-edge_a[:,1]*edge_b[:,0])/2
        ids=np.where(areas>1e-7)[0]
        polys=shapely.polygons(xy[ids])
        # Replacements may touch only the authorized old outside-tail area.
        # Only explicit mouth polygons are removed from the replacement frame
        # exclusion. There is no global 12cm (or other) frame shrink.
        exclusion=protected_frame if row.get('replacement_only') else protect.buffer(-.025)
        overlaps=shapely.area(shapely.intersection(polys,exclusion))
        overlap=float(np.sum(overlaps))
        assert overlap<.03,(row['name'],'projects inside preserved area',overlap)
        replacement_audit=replacement_spatial_audit(polys,replacement_protection,original_terminals) if row.get('replacement_only') else None
        color_audit=None
        if row.get('vertex_color_fade'):
            samples=color_samples(obj)
            source_colors[row['name']]=samples
            color_audit=verify_fade_regions(samples,row,frame,outer_frame,supports,outer_tails)
            if row['name']=='SM_MPRE_ReplacementTerminalRoads':
                assert all(color_audit['connected_corner_samples'].values()),'A connected terminal has no replacement road vertices'
        report['meshes'].append(dict(name=row['name'],triangles=row['triangles'],
            protected_overlap_m2=overlap,replacement_spatial_audit=replacement_audit,
            source_fade_audit=color_audit))
    crowns=[]
    for row in audit['context']['trees']:
        crown=Point(row['position_m'][:2]).buffer(row['crown_radius_m'])
        assert not crown.intersects(protect),row['source_id']
        crowns.append(crown)
    report['source_validation']=dict(meshes=len(report['meshes']),triangles=sum(r['triangles'] for r in report['meshes']),
                                    trees=len(crowns),source_sha256=sha(source))
    # Fresh factory scene verifies the FBX files actually carry the validated
    # bounds/UVs/colors; do not trust only the in-memory export success flags.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for row in manifest['meshes']:
        fbx=ROOT/row['fbx'];assert sha(fbx)==row['sha256']
        bpy.ops.import_scene.fbx(filepath=str(fbx),use_custom_normals=True,colors_type='LINEAR')
        meshes=[o for o in bpy.context.selected_objects if o.type=='MESH'];assert len(meshes)==1
        obj=meshes[0];mesh=obj.data;mesh.calc_loop_triangles()
        assert len(mesh.loop_triangles)==row['triangles'],(row['name'],'FBX triangle mismatch')
        vv=[obj.matrix_world@v.co for v in mesh.vertices]
        actual=[[min(p[i] for p in vv),max(p[i] for p in vv)] for i in range(3)]
        error=max(abs(a-b) for aa,bb in zip(actual,row['bounds_m']) for a,b in zip(aa,bb))
        assert error<.02,(row['name'],'FBX metres/axis bounds',error)
        assert mesh.uv_layers
        record=next(r for r in report['meshes'] if r['name']==row['name'])
        record.update(fbx_triangles=len(mesh.loop_triangles),fbx_bounds_error_m=error,
                      fbx_uv_layers=len(mesh.uv_layers))
        if row.get('vertex_color_fade'):
            samples=color_samples(obj)
            record['fbx_color_roundtrip']=compare_color_samples(source_colors[row['name']],samples,row['name'])
            record['fbx_fade_audit']=verify_fade_regions(samples,row,frame,outer_frame,supports,outer_tails)
        bpy.ops.object.delete(use_global=False)
    report.update(success=True,fbx_roundtrip_meshes=len(manifest['meshes']),
                  manifest_sha256=sha(OUT/'manifest.json'),blend_sha256=sha(ROOT/manifest['blend']))
try:run()
except Exception:report['error']=traceback.format_exc();print(report['error'])
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('MPRE_BLENDER_VALIDATION',report['success'])
if not report['success']:raise RuntimeError(report['error'])
