"""Read-only source-CAD audit of MPR architectural/interior omissions.

No scene import, assets, source layout, or live editor state is changed. The
report distinguishes measured plan evidence from unverified elevations.
"""
from pathlib import Path
import collections
import hashlib
import io
import json
import math
import os
import sys
import gzip

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/_vendor/cad'))
os.environ['EZDXF_DISABLE_C_EXT'] = '1'
import ezdxf
from ezdxf.math import Matrix44
from PIL import Image, ImageDraw, ImageFont

SOURCE = Path('D:/Data/仓库数据/MPR/平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
OUT = ROOT / 'Saved/MPR/interior_cad_20261112/interior_truth'
SCALE = .0254
ORIGIN = (12800., 8000.)
WALL_LAYERS = {'A-WALL-GPE', 'A-WALL-NDE', 'A-WALL-DE', 'A-WALL-MAS', 'A-WALL-NDN', 'A-WALL-GPN'}


def read_architecture_document(handles):
    selected = []
    section = block = ''

    def keep(record):
        nonlocal section, block
        if not record:
            return
        kind = record[0][1].strip()
        values = {c: v.strip() for c, v in record}
        if kind == 'SECTION':
            section = values.get(2, '')
        if kind == 'BLOCK':
            block = values.get(2, '')
        retain = section in ('HEADER', 'TABLES') or kind in ('SECTION', 'ENDSEC', 'EOF')
        if section == 'BLOCKS':
            retain |= (kind in ('BLOCK', 'ENDBLK', 'INSERT', 'ATTRIB', 'SEQEND')
                       or block in ('ue5u56u56', 'PILLAR', 'DR1H45', 'DR1H90')
                       or values.get(5) in handles)
        if section == 'ENTITIES':
            retain |= kind in ('INSERT', 'ATTRIB', 'SEQEND')
        if retain:
            selected.extend(f'{c}\n{v}\n' for c, v in record)
        if kind == 'ENDBLK':
            block = ''

    def decode(value):
        try:
            return value.decode('utf8').rstrip('\r\n')
        except UnicodeDecodeError:
            return value.decode('gb18030', errors='replace').rstrip('\r\n')
    with SOURCE.open('rb') as stream:
        record = []
        while True:
            code_line, value_line = stream.readline(), stream.readline()
            if not code_line:
                break
            code = int(code_line)
            if code == 0:
                keep(record)
                record = []
            record.append((code, decode(value_line)))
        keep(record)
    return ezdxf.read(io.StringIO(''.join(selected)))


def xy(point):
    return [(point[i]-ORIGIN[i])*SCALE for i in (0, 1)]


def entity_points(e):
    kind = e.dxftype()
    if kind == 'LINE':
        return [e.dxf.start, e.dxf.end]
    if kind == 'LWPOLYLINE':
        points = list(e.vertices_in_wcs())
        return points + points[:1] if e.closed else points
    if kind == 'POLYLINE':
        return list(e.points())
    return []


def chain_matrix(doc, handles):
    matrix = Matrix44()
    for handle in handles:
        matrix = Matrix44.chain(doc.entitydb[handle].matrix44(), matrix)
    return matrix


def segment_distance(p, a, b):
    d = [b[i]-a[i] for i in (0, 1)]
    length2 = sum(v*v for v in d)
    t = max(0, min(1, sum((p[i]-a[i])*d[i] for i in (0, 1))/length2))
    return math.dist(p, [a[i]+d[i]*t for i in (0, 1)])


def interval_union(intervals):
    result = []
    for lo, hi in sorted(intervals):
        if result and lo <= result[-1][1] + 1e-6:
            result[-1][1] = max(result[-1][1], hi)
        else:
            result.append([lo, hi])
    return result


def partition_overlay(extracted, layout, missing):
    image=Image.new('RGB',(1500,1000),'#ffffff')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',13)
    for i,item in enumerate(missing):
        column,row=i%3,i//3
        left,top=column*500,row*500
        a,b=item['points_m'];center=[(a[j]+b[j])/2 for j in (0,1)]
        radius=max(3.0,item['length_m']/2+1.5)
        scale=440/(radius*2)
        def project(p):return (left+250+(p[0]-center[0])*scale,top+255-(p[1]-center[1])*scale)
        def inside(p):return abs(p[0]-center[0])<radius and abs(p[1]-center[1])<radius
        for w in layout['office_walls']:
            wa,wb=w['points_m']
            if inside(wa) and inside(wb):
                draw.line([project(wa),project(wb)],fill='#b4c4cb',width=max(3,int(w['thickness_m']*scale)))
        for g in extracted['architecture']:
            if not(g['layer'].startswith('A-WALL') or 'DOOR' in g['layer']):continue
            for pa,pb in zip(g['points_m'],g['points_m'][1:]):
                if inside(pa) and inside(pb):draw.line([project(pa),project(pb)],fill='#132e4a' if 'DOOR' in g['layer'] else '#666666',width=1)
        draw.line([project(a),project(b)],fill='#e02d3d',width=4)
        draw.text((left+14,top+12),f"{i+1}. {item['length_m']:.3f} m missing / {item['thickness_m']:.3f} m thick",font=font,fill='black')
        draw.text((left+14,top+35),' + '.join(h[-1] for h in item['source_face_handles']),font=small,fill='black')
        draw.text((left+14,top+474),'gray=CAD faces  blue-gray=built walls  red=missing',font=small,fill='black')
        draw.rectangle((left+1,top+1,left+498,top+498),outline='#dddddd')
    image.save(OUT/'partition_missing_plan_overlay.png')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    layout = json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
    extracted = json.loads((ROOT/'SourceAssets/MPR/mpr_cad_extracted.json').read_text(encoding='utf8'))
    handles = {h for row in extracted['architecture'] for h in row['source_handles']}
    with SOURCE.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    doc = read_architecture_document(handles)
    source_checks = []
    for row in extracted['architecture']:
        entity = doc.entitydb.get(row['source_handles'][-1])
        if entity is None:
            raise AssertionError(row['source_handles'])
        points = entity_points(entity)
        if not points:
            continue
        matrix = chain_matrix(doc, row['source_handles'][:-1])
        actual = [xy(p) for p in matrix.transform_vertices(points)]
        if len(actual) != len(row['points_m']):
            raise AssertionError(('point count', row['source_handles']))
        error = max(math.dist(a, b) for a, b in zip(actual, row['points_m']))
        if error > .00001:
            raise AssertionError(('source coordinate mismatch', row['source_handles'], error))
        source_checks.append(error)

    columns = []
    for row in layout['columns']:
        e = doc.entitydb[row['source_handles'][0]]
        p = xy(e.matrix44().transform((0, 0, 0)))
        columns.append(dict(source_handles=row['source_handles'], center_m=p,
                            layout_center_m=row['position_m'], size_m=row['size_m']))

    footprint = layout['footprint_outline_m']
    edges = list(zip(footprint, footprint[1:]+footprint[:1]))
    doors = []
    door_block_shapes = {}
    for row in layout['pedestrian_doors']:
        matrix = chain_matrix(doc, row['source_handles'])
        # Source DR1H45/90 unit block: leaf hinge at (-.5,0), closed latch at (.5,0).
        # This is the wall opening. The stored bbox midpoint includes swing arc.
        endpoints = [xy(p) for p in matrix.transform_vertices([(-.5, 0, 0), (.5, 0, 0)])]
        center = [(a+b)/2 for a, b in zip(*endpoints)]
        nearest = min((segment_distance(center, a, b), i) for i, (a, b) in enumerate(edges))
        width = math.dist(*endpoints)
        wallhits = []
        for wall in layout['office_walls']:
            if segment_distance(center, *wall['points_m']) < wall['thickness_m']/2 + .03:
                wallhits.append(wall['id'])
        doors.append(dict(id=row['id'], source_handles=row['source_handles'], block=row['block'],
                          opening_endpoints_m=endpoints, opening_center_m=center, opening_width_m=width,
                          swing_bbox_center_m=row['position_m'],
                          exterior_edge=nearest[1] if nearest[0] < .35 else None,
                          nearest_exterior_edge_distance_m=nearest[0],
                          current_office_wall_overlap_ids=wallhits,
                          existing_3d_model='not consumed by architecture or reference-shell generators',
                          door_height_m=None))
        if row['block'] not in door_block_shapes:
            door_block_shapes[row['block']] = [dict(type=e.dxftype(),handle=e.dxf.handle,
                points=[list(p) for p in entity_points(e)],
                arc=(dict(center=list(e.dxf.center),radius=e.dxf.radius,start=e.dxf.start_angle,end=e.dxf.end_angle)
                     if e.dxftype()=='ARC' else None)) for e in doc.blocks[row['block']]]

    # Compare every measured axis-aligned parallel pair with the currently built
    # 110 centerlines. These are candidates: nearby unrelated walls must not be
    # automatically converted into geometry without the plan overlay.
    faces = []
    for g in extracted['architecture']:
        if g['layer'] not in WALL_LAYERS:
            continue
        for a, b in zip(g['points_m'], g['points_m'][1:]):
            if math.dist(a, b) < .5:
                continue
            axis = 0 if abs(a[1]-b[1]) < .001 else 1 if abs(a[0]-b[0]) < .001 else None
            if axis is None:
                continue
            faces.append(dict(axis=axis,fixed=(a[1-axis]+b[1-axis])/2,
                              lo=min(a[axis],b[axis]),hi=max(a[axis],b[axis]),
                              layer=g['layer'],source_handles=g['source_handles']))
    missing = []
    seen = set()
    for i, a in enumerate(faces):
        for b in faces[i+1:]:
            if a['axis'] != b['axis'] or a['layer'] != b['layer']:
                continue
            thick = abs(a['fixed']-b['fixed'])
            lo, hi = max(a['lo'],b['lo']),min(a['hi'],b['hi'])
            if not (.075 <= thick <= .36 and hi-lo > .5):
                continue
            fixed = (a['fixed']+b['fixed'])/2
            key = (a['axis'],round(fixed,4),round(lo,4),round(hi,4))
            if key in seen:
                continue
            seen.add(key)
            axis = a['axis']
            coverage = []
            for w in layout['office_walls']:
                wa, wb = w['points_m']
                if abs(wa[1-axis]-fixed)>.02 or abs(wb[1-axis]-fixed)>.02:
                    continue
                l,h=max(lo,min(wa[axis],wb[axis])),min(hi,max(wa[axis],wb[axis]))
                if h>l:
                    coverage.append((l,h))
            covered = sum(h-l for l,h in interval_union(coverage))
            if hi-lo-covered > .5:
                points = [[lo,fixed],[hi,fixed]] if axis==0 else [[fixed,lo],[fixed,hi]]
                missing.append(dict(points_m=points,thickness_m=thick,length_m=hi-lo,
                    uncovered_length_m=hi-lo-covered,layer=a['layer'],
                    source_face_handles=[a['source_handles'],b['source_handles']],
                    disposition='plan review required; existing nearest-pair algorithm only keeps one overlap per face'))

    # Include evidence for architectural categories absent from the mesh set.
    missing_categories = {}
    for layer in ('A-STAIRS','A-WIND','A-COL-ENCL','A-SPRINKLER-RISER'):
        rows=[g for g in extracted['architecture'] if g['layer']==layer]
        missing_categories[layer]=dict(entity_count=len(rows),source_examples=rows[:8],
            conclusion='No dedicated source-geometry consumer in current architecture generator; source must be classified before repair')
    findings = [
        dict(id='pedestrian_doors_omitted',severity='high',measured_count=len(doors),
             exterior_count=sum(d['exterior_edge'] is not None for d in doors),
             internal_count=sum(d['exterior_edge'] is None for d in doors),
             evidence='80 explicit DR1H45/DR1H90 INSERTs inside architecture source 2C93B4. Builders cut only 72 dock and 2 drive-in doors.',
             repair='Use source opening endpoints, not swing bbox centers. Cut only mapped exterior/internal wall intersections; add frames/door leaves in current blue-white roles. Opening height remains unmeasured.'),
        dict(id='partition_nearest_pair_truncation',severity='high',candidate_count=len(missing),
             evidence='mpr_cad_refine.py chooses min(matches) once per wall face; disjoint collinear overlaps can be dropped.',
             repair='Review candidates in plan; interval-split faces and retain all validated opposing overlaps. Do not rebuild unrelated facade/roof/camera.'),
        dict(id='unmeasured_elevations',severity='limitation',
             evidence='Office height 3.3m, dock height 4.2m/4.5m, roof13.4m and all current simplified device heights are generator assumptions. CAD plan positions alone do not prove vertical fidelity.',
             repair='Bind available source elevations and dimensions before claiming exact construction.'),
    ]
    report=dict(schema_version=1,source=str(SOURCE),source_sha256=digest,
        coordinate_system='CAD-local metres. UE X=100*x, Y=-100*y, Z=100*z.',
        source_geometry_verified=dict(line_polyline_count=len(source_checks),max_error_m=max(source_checks)),
        counts=dict(columns=len(columns),pedestrian_doors=len(doors),current_office_walls=len(layout['office_walls']),
                    omitted_partition_candidates=len(missing)),
        findings=findings,important_preservation=['existing runtime central distributor','CAD worker placements and console/table clearance','motion interpolation','current exterior site/camera and dirty map'],
        scope='Offline source and construction-script audit; not a live-map validation.')
    baseline_path=ROOT/'Saved/MPR/interior_cad_20261112/preservation/baseline.json.gz'
    if baseline_path.exists():
        baseline=json.load(gzip.open(baseline_path,'rt',encoding='utf8'))
        current_columns=[]
        for actor in baseline['actors']:
            if actor['label'].startswith('MPR_Columns_'):
                for component in actor['components']:
                    current_columns.extend(component.get('instance_transforms',[]))
        errors=[]
        for column in layout['columns']:
            target=[column['position_m'][0]*100,-column['position_m'][1]*100]
            match=min(current_columns,key=lambda t:math.dist(t['translation_cm'][:2],target))
            errors.append(math.dist(match['translation_cm'][:2],target))
        selected=[dict(label=a['label'],guid=a['guid'],hidden=a['hidden'],meshes=[c.get('mesh') for c in a['components'] if c.get('mesh')])
            for a in baseline['actors'] if a['label']=='MPR_OfficePartitions' or a['label'].startswith('MPR4_Facade_')]
        report['current_map_evidence']=dict(path=str(baseline_path),map=baseline['map'],
            column_instances=len(current_columns),max_column_xy_error_cm=max(errors),architectural_actors=selected,
            facade_generator='build_mpr_reference_shell_v4.py also includes only dock_doors + drive_in_doors')
    partition_overlay(extracted,layout,missing)
    for name, data in [('audit_report',report),('pedestrian_openings',doors),('door_block_evidence',door_block_shapes),
                       ('partition_missing_candidates',missing),('architectural_columns',columns),('unmodeled_architecture_categories',missing_categories)]:
        (OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
