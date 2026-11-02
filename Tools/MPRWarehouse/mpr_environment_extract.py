"""Extract CADMapper environment without third-party CAD dependencies.

Preserves source triangulation and 3D road/rail geometry; coordinate values are
in metres despite this export's stale INSUNITS=4 metadata. The physical scale
is cross-checked separately against the warehouse footprint and owner plan.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def records(path):
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    pairs = [(int(lines[i]), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]
    result, record, section = [], [], None
    for code, value in pairs:
        if code == 0:
            if record:
                if record[0] == (0, 'SECTION'):
                    section = next((v for c, v in record if c == 2), None)
                elif section == 'ENTITIES':
                    result.append(record)
            record = []
        record.append((code, value))
    return result


def first(record, code, default=None):
    return next((v for c, v in record if c == code), default)


def boundary_loops(vertices, faces):
    # Return mesh boundary edges as ordered loops, retaining source vertex IDs.
    counts = Counter(tuple(sorted((f[i], f[(i + 1) % len(f)])))
                     for f in faces for i in range(len(f)))
    todo = {edge for edge, n in counts.items() if n == 1}
    loops = []
    while todo:
        a, b = min(todo)
        todo.remove((a, b))
        chain = [a, b]
        while chain[-1] != chain[0]:
            edge = next((e for e in sorted(todo) if chain[-1] in e), None)
            if edge is None:
                break
            todo.remove(edge)
            chain.append(edge[1] if edge[0] == chain[-1] else edge[0])
        loops.append(chain)
    return loops


def bounds(vertices):
    return {'min': [min(v[i] for v in vertices) for i in range(3)],
            'max': [max(v[i] for v in vertices) for i in range(3)]}


def parse(path):
    meshes, lines, current = [], [], None
    for rec in records(path):
        kind = rec[0][1]
        if kind == 'MESH':
            verts = []
            for i, (c, v) in enumerate(rec):
                if c == 10:
                    assert rec[i+1][0] == 20 and rec[i+2][0] == 30
                    verts.append([float(v), float(rec[i+1][1]), float(rec[i+2][1])])
            start = next(i for i, pair in enumerate(rec) if pair[0] == 93) + 1
            face_ints = []
            for c, v in rec[start:]:
                if c != 90:
                    break
                face_ints.append(int(v))
            faces, cursor = [], 0
            while cursor < len(face_ints):
                count = face_ints[cursor]
                faces.append(face_ints[cursor+1:cursor+1+count])
                cursor += 1 + count
            assert len(verts) == int(first(rec, 92))
            assert len(face_ints) == int(first(rec, 93))
            assert all(0 <= j < len(verts) for f in faces for j in f)
            xyarea = sum(abs(sum(verts[f[k]][0]*verts[f[(k+1)%len(f)]][1] -
                                     verts[f[(k+1)%len(f)]][0]*verts[f[k]][1]
                                     for k in range(len(f))))/2 for f in faces)
            box = bounds(verts)
            layer = first(rec, 8, '0')
            top_faces = [face for face in faces if all(abs(verts[j][2]-box['max'][2])<0.001 for j in face)]
            footprint_loops = boundary_loops(verts, top_faces) if layer == 'buildings' else []
            meshes.append({'id': first(rec, 5), 'layer': layer,
                           'vertices': verts, 'faces': faces,
                           'boundaryLoops': boundary_loops(verts, faces),
                           'footprintLoops': footprint_loops,
                           'footprintAreaM2': round(xyarea/2,3) if layer == 'buildings' else None,
                           'bounds': box, 'projectedFaceAreaM2': round(xyarea, 3)})
        elif kind == 'POLYLINE':
            current = {'id': first(rec, 5), 'layer': first(rec, 8, '0'),
                       'closed': bool(int(first(rec, 70, '0')) & 1), 'vertices': []}
        elif kind == 'VERTEX' and current is not None:
            current['vertices'].append([float(first(rec, code, '0')) for code in (10,20,30)])
        elif kind == 'SEQEND' and current is not None:
            current['bounds'] = bounds(current['vertices'])
            lines.append(current)
            current = None
    return meshes, lines


def preview(data, output):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1800, 1500), '#e1e7df')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 17)
    titlefont = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 25)
    colors = {'topography':'#e1e7df', 'water':'#98bdcf', 'parks':'#a7bea2',
              'major_roads':'#687783', 'minor_roads':'#75828a',
              'paths':'#adad9c', 'buildings':'#f3f5f6'}
    full_bounds=bounds([v for m in data['meshes'] for v in m['vertices']])
    xmin,ymin,_=full_bounds['min']; xmax,ymax,_=full_bounds['max']
    scale=min(1640/(xmax-xmin), 1210/(ymax-ymin))
    def xy(v): return (80+(v[0]-xmin)*scale, 1360-(v[1]-ymin)*scale)
    for layer in ('topography','water','parks','major_roads','minor_roads','paths','buildings'):
        for mesh in (m for m in data['meshes'] if m['layer'] == layer):
            for face in mesh['faces']:
                draw.polygon([xy(mesh['vertices'][i]) for i in face], fill=colors[layer])
            for loop in mesh['footprintLoops'] if layer == 'buildings' else mesh['boundaryLoops']:
                draw.line([xy(mesh['vertices'][i]) for i in loop], fill='#74817a', width=1)
    for line in data['polylines']:
        pts=[xy(v) for v in line['vertices']]
        if line['layer'] in ('water','parks'):
            draw.polygon(pts,fill=colors[line['layer']],outline='#74817a')
        else:
            draw.line(pts, fill='#474f54', width=2)
    for mesh in data['meshes']:
        if mesh['layer']=='buildings' and mesh['projectedFaceAreaM2'] > 5000:
            b=mesh['bounds']; x,y=xy([(b['min'][0]+b['max'][0])/2,(b['min'][1]+b['max'][1])/2,0])
            draw.text((x,y),mesh['id'],font=titlefont,fill='#203446',anchor='mm')
    draw.text((60,30),'MPR | CADMapper source geometry (metres; X east, Y north provisional)',font=titlefont,fill='#203446')
    draw.text((60,70),'Building IDs identify source meshes. Source z elevations are preserved in JSON.',font=font,fill='#203446')
    draw.line([(80,1410),(80+200*scale,1410)],fill='#203446',width=4)
    draw.text((80,1420),'200 m',font=font,fill='#203446')
    draw.text((1550,1420),'+Y (source)',font=font,fill='#203446')
    draw.line([(1590,1410),(1590,1370)],fill='#203446',width=4)
    image.save(output)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('SourceAssets/MPR/environment/cadmapper-carteret-new-jersey-us.dxf'))
    parser.add_argument('--output',type=Path,default=Path('SourceAssets/MPR/environment'))
    args=parser.parse_args()
    meshes, lines=parse(args.source)
    data={'schemaVersion':1,'sourceFile':args.source.name,
          'sourceSHA256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
          'units':'metres','unitWarning':'DXF INSUNITS=4 (mm) is inconsistent with 1000x1000 site and full warehouse footprint; coordinates are interpreted as metres.',
          'sourceFrame':'Source XY, unshifted and unrotated; no absolute georeference embedded.',
          'heightWarning':'CADMapper buildings all have 3m default extrusion; use separately documented height overrides, never assume these are surveyed heights.',
          'meshes':meshes,'polylines':lines}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'environment_geometry.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    summary={'meshCounts':dict(Counter(m['layer'] for m in meshes)),
             'polylineCounts':dict(Counter(m['layer'] for m in lines)),
             'vertexCount':sum(len(m['vertices']) for m in meshes),
             'faceCount':sum(len(m['faces']) for m in meshes),
             'largeBuildings':[{k:m[k] for k in ('id','bounds','footprintAreaM2')} for m in meshes if m['layer']=='buildings' and m['projectedFaceAreaM2']>5000]}
    (args.output/'environment_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    preview(data,args.output/'environment_plan.png')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
