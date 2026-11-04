"""Prepare an independent, regularized MPR solar layout in ordinary Python.

No bpy/native process. Only solar/ outputs are written; the old V4 sources,
main rebuilt scene, roof and its 195 fixture placements remain immutable.
Run export_mpr_rebuild_solar.py separately in Blender after reviewing the plan.
"""
from collections import defaultdict
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
from shapely.geometry import Polygon, box, mapping
from shapely.ops import unary_union

OUT = ROOT / 'SourceAssets/MPR/rebuild_b50b57/solar'
V4 = ROOT / 'SourceAssets/MPR/reference_v4/architecture'
ROLES = ['MPR4_SolarFrame', 'MPR4_SolarCells', 'MPR4_SolarMid', 'MPR4_SolarFar']
BANKS = ['00_0', '01_0', '01_1', '02_0', '02_1']
PITCH = (1.12, 1.95)
ORIGIN = (-60.56, -79.975)
ROOF = 13.4
TOP = 13.64
DEVICE_CLEARANCE = .85


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def rectangle(key):
    ix, iy = key
    x, y = ORIGIN[0] + ix * PITCH[0], ORIGIN[1] + iy * PITCH[1]
    return box(x, y, x + PITCH[0], y + PITCH[1])


def bank_for(key):
    p = rectangle(key).centroid
    return f'{0 if p.x < 20 else 1 if p.x < 80 else 2:02}_{0 if p.y < 0 else 1}'


def remove_tails(cells):
    """Keep 2x3 groups and discard islands below 24 modules; never grow area."""
    retained = set()
    for ix, iy in sorted(cells):
        group = {(ix + dx, iy + dy) for dx in range(2) for dy in range(3)}
        if group <= cells:
            retained.update(group)
    todo, result = set(retained), set()
    while todo:
        seed = todo.pop()
        queue, component = [seed], {seed}
        while queue:
            x,y = queue.pop()
            for other in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if other in todo:
                    todo.remove(other);component.add(other);queue.append(other)
        if len(component) >= 24:
            result.update(component)
    return result


def rectangular_runs(cells):
    """Tile an orthogonal occupancy mask without overlapping rectangles."""
    by_row = defaultdict(list)
    for x, y in cells:
        by_row[y].append(x)
    runs = defaultdict(list)
    for y, xs in sorted(by_row.items()):
        groups = []
        for x in sorted(xs):
            if not groups or x != groups[-1][-1] + 1:
                groups.append([x])
            else:
                groups[-1].append(x)
        for group in groups:
            runs[(group[0], group[-1] + 1)].append(y)
    result = []
    for (x0, x1), ys in sorted(runs.items()):
        groups = []
        for y in ys:
            if not groups or y != groups[-1][-1] + 1:
                groups.append([y])
            else:
                groups[-1].append(y)
        for group in groups:
            y0, y1 = group[0], group[-1] + 1
            result.append(dict(grid=[x0, y0, x1, y1], bounds_m=[ORIGIN[0] + x0 * PITCH[0], ORIGIN[1] + y0 * PITCH[1],
                ORIGIN[0] + x1 * PITCH[0], ORIGIN[1] + y1 * PITCH[1]], modules=(x1-x0)*(y1-y0)))
    return result


class Meshes:
    def __init__(self):
        self.data = defaultdict(lambda: defaultdict(lambda: [[], [], []]))

    def mesh(self, name, role, vertices, faces, uvs=None):
        vv, ff, uu = self.data[name][role]
        offset = len(vv)
        vv.extend(vertices)
        ff.extend([[i + offset for i in face] for face in faces])
        uu.extend(uvs if uvs is not None else [[(vertices[i][0], vertices[i][1]) for i in face] for face in faces])

    def box(self, name, role, bounds, z0, z1, top=True):
        x0, y0, x1, y1 = bounds
        vertices = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
                    (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
        faces = [(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        if top:
            faces.append((4,5,6,7))
        self.mesh(name, role, vertices, faces)

    def surface(self, name, role, bounds, period):
        x0, y0, x1, y1 = bounds
        vertices = [(x0,y0,TOP),(x1,y0,TOP),(x1,y1,TOP),(x0,y1,TOP)]
        uv = [((x-ORIGIN[0])/period[0], (y-ORIGIN[1])/period[1]) for x,y,z in vertices]
        self.mesh(name, role, vertices, [(0,1,2,3)], [uv])


def build_geometry(blocks):
    geometry = Meshes()
    for bank, rows in blocks.items():
        name = 'SM_MPRR_SolarBank_' + bank
        for lod, role, period in [(0,ROLES[1],PITCH),(1,ROLES[2],PITCH),(2,ROLES[3],(8.,8.))]:
            target = name if lod == 0 else name + f'_LOD{lod}'
            # Stable material order across export, with all four roles listed
            # in the manifest's section remapping contract.
            geometry.data[target][ROLES[0]]
            geometry.data[target][role]
            for row in rows:
                x0,y0,x1,y1 = row['bounds_m']
                bounds = [x0,y0,x1,y1]
                geometry.box(target, ROLES[0], bounds, TOP-.08, TOP, top=False)
                geometry.surface(target, role, bounds, period)
                if lod == 0:
                    # Only the perimeter has raised physical trim. Internal
                    # module divisions live in the UV texture, so there are no
                    # thousands of subpixel reflective seam surfaces.
                    w=.025
                    for edge in [[x0,y0,x1,y0+w],[x0,y1-w,x1,y1],[x0,y0+w,x0+w,y1-w],[x1-w,y0+w,x1,y1-w]]:
                        if edge[2]>edge[0] and edge[3]>edge[1]:
                            geometry.box(target, ROLES[0], edge, TOP+.005, TOP+.02)
                    # Sparse physical mounting rails anchor every array to the
                    # unchanged roof, without individual components/actors.
                    for y in [y0+.15, y1-.15]:
                        geometry.box(target, ROLES[0], [x0+.12,y-.06,x1-.12,y+.06], ROOF+.014, TOP-.08)
    return geometry.data


def svg_geometry(geometry, fill, stroke='none', opacity=1):
    if geometry.is_empty:
        return ''
    polys = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
    commands=[]
    for polygon in polys:
        for ring in [polygon.exterior,*polygon.interiors]:
            coords=list(ring.coords)
            commands.append('M'+' L'.join(f'{x:.5f},{-y:.5f}' for x,y in coords)+' Z')
    return f'<path d="{" ".join(commands)}" fill="{fill}" stroke="{stroke}" stroke-width=".3" fill-rule="evenodd" opacity="{opacity}"/>'


def preview(roof, old_area, new_area, devices, aisles, blocks):
    panel_width, scale = 1160, 2.75
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="2320" height="780" viewBox="0 0 2320 780">',
        '<rect width="2320" height="780" fill="#E7EDF1"/>',
        '<style>text{font-family:"Microsoft YaHei",Arial,sans-serif;fill:#17334B}</style>']
    for index,title in enumerate(['原布局 · 航拍像素轮廓','整理后 · 分区保留 / 连续检修通道 / 设备固定']):
        dx=index*panel_width
        parts.append(f'<text x="{dx+35}" y="42" font-size="24">{title}</text>')
        parts.append(f'<g transform="translate({dx+565},350) scale({scale})">')
        parts.append(svg_geometry(roof,'#E9EDF0','#4F7A96'))
        if index:
            parts.append(svg_geometry(aisles.intersection(roof),'#C9D6E0'))
        parts.append(svg_geometry(new_area if index else old_area,'#153A60'))
        if index:
            # Grid is clipped to the final arrays; no bright noisy cell lines.
            parts.append('<defs><clipPath id="panels">'+svg_geometry(new_area,'white')+'</clipPath></defs>')
            parts.append('<g clip-path="url(#panels)" stroke="#31526C" stroke-width=".10">')
            for i in range(-10,220):
                x=ORIGIN[0]+i*PITCH[0]
                parts.append(f'<path d="M{x},-90 V95"/>')
            for i in range(85):
                y=-(ORIGIN[1]+i*PITCH[1])
                parts.append(f'<path d="M-50,{y} H175"/>')
            parts.append('</g>')
        for device in devices:
            parts.append(svg_geometry(box(*device['bounds_m']),'#F8FAFC','#8196A6'))
        parts.append('</g>')
    parts.extend(['<text x="45" y="700" font-size="20">仅替换五个光伏分区网格；195 处屋顶设备、屋顶和内部保持原位。相同掩码贯穿三个 LOD。</text>',
        '<text x="45" y="739" font-size="17">这是展示场景的布局整理，不代表设备容量、结构验算或施工图。</text>','</svg>'])
    return '\n'.join(parts)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    archive=OUT/'inputs';archive.mkdir(exist_ok=True)
    sources={'previous_plan.json':V4/'plan_solar_v5.json','previous_architecture.json':V4/'reference_shell_manifest.json',
             'cad_layout.json':ROOT/'SourceAssets/MPR/mpr_cad_layout.json'}
    input_hashes={}
    for name,path in sources.items():
        target=archive/name
        if target.exists():
            assert sha(target)==sha(path), ('Source snapshot differs',name)
        else:
            shutil.copy2(path,target)
        input_hashes[name]=sha(target)
    plan,previous,cad=[read(archive/name) for name in sources]
    roof=Polygon(cad['footprint_outline_m'])
    registration=previous['roof_layout']['plan_registration'];sx,sy=registration['scale_m_per_px'];ox,oy=registration['offset_m']
    def convert(points):return [(ox+x*sx,oy+y*sy)for x,y in points]
    fields=[(row['id'],Polygon(convert(row['exterior_px']),[convert(h)for h in row.get('holes_px',[])]))for row in plan['regions']]
    assert len(fields)==16
    devices=[]
    for mesh,rows in previous['instances'].items():
        if mesh not in {'SM_MPR4_RoofLight','SM_MPR4_RoofHVAC'}:continue
        half=(.925,.675)if 'RoofLight'in mesh else (1.15,.925)
        for index,row in enumerate(rows):
            assert row['rotation_deg']==0, 'Review rotated fixture bounds before proceeding'
            x,y,z=row['position_m'];scale=row['scale']
            devices.append(dict(id=f'{mesh}:{index}',position_m=row['position_m'],scale=scale,
                bounds_m=[x-half[0]*scale[0],y-half[1]*scale[1],x+half[0]*scale[0],y+half[1]*scale[1]]))
    assert len(devices)==195
    device_solids=unary_union([box(*row['bounds_m'])for row in devices])
    device_clear=unary_union([box(*row['bounds_m']).buffer(DEVICE_CLEARANCE,join_style=2)for row in devices])
    major_aisles=[box(21.8,-86,26.0,70),box(70.7,-86,73.6,70),box(124.4,-86,127.3,70),
        box(24,3.4,125,5.6),box(24,39.2,125,42.2),box(-45,-41.5,173,-39.0),box(72,-52.6,125,-50.4)]
    fixed_aisles=unary_union(major_aisles)
    services={}
    for identity,original in fields:
        extent=box(*original.bounds).intersection(roof.buffer(-2.,join_style=2))
        # A roof step clips a rectangle rather than filling beyond the roof.
        nearby=[d for d in devices if extent.intersects(box(*d['bounds_m']).buffer(DEVICE_CLEARANCE,join_style=2))]
        clusters=[]
        for device in sorted(nearby,key=lambda r:r['position_m'][1]):
            y=device['position_m'][1]
            if not clusters or y-clusters[-1][0]['position_m'][1]>1.55:
                clusters.append([device])
            else:
                clusters[-1].append(device)
        service=[]
        for cluster in clusters:
            if len(cluster)>=2:
                y0=min(d['bounds_m'][1]for d in cluster)-DEVICE_CLEARANCE
                y1=max(d['bounds_m'][3]for d in cluster)+DEVICE_CLEARANCE
                service.append(box(original.bounds[0],y0,original.bounds[2],y1))
        services[identity]=unary_union(service)
    aisles=unary_union([fixed_aisles,*services.values()])
    bank_cells=defaultdict(set);field_rows=[];global_cells=set()
    for identity,original in fields:
        extent=box(*original.bounds).intersection(roof.buffer(-2.,join_style=2))
        local_aisles=services[identity]
        allowed=extent.difference(device_clear.union(aisles))
        x0,y0,x1,y1=extent.bounds
        cells=set()
        for ix in range(math.floor((x0-ORIGIN[0])/PITCH[0]),math.ceil((x1-ORIGIN[0])/PITCH[0])):
            for iy in range(math.floor((y0-ORIGIN[1])/PITCH[1]),math.ceil((y1-ORIGIN[1])/PITCH[1])):
                key=(ix,iy)
                if key not in global_cells and allowed.covers(rectangle(key)):
                    cells.add(key)
        retained=remove_tails(cells)
        assert len(retained)>=6, ('A major solar region was lost',identity,len(retained))
        global_cells.update(retained)
        area=unary_union([rectangle(k)for k in sorted(retained)])
        for key in retained:
            bank_cells[bank_for(key)].add(key)
        field_rows.append(dict(id=identity,old_geometry=mapping(original),regular_envelope=mapping(extent),
            geometry=mapping(area),original_area_m2=original.area,new_area_m2=area.area,
            module_cells=len(retained),removed_tail_cells=len(cells-retained),service_aisles=mapping(local_aisles.intersection(extent))))
    assert set(bank_cells)==set(BANKS), sorted(bank_cells)
    blocks={bank:rectangular_runs(bank_cells[bank])for bank in BANKS}
    final=unary_union([rectangle(key)for key in sorted(global_cells)])
    assert final.intersection(device_clear).area<1e-7
    assert final.intersection(aisles).area<1e-7
    assert final.difference(roof.buffer(-2.,join_style=2)).area<1e-7
    assert abs(sum(r['new_area_m2']for r in field_rows)-final.area)<1e-6
    geometry=build_geometry(blocks)
    materials={role:copy.deepcopy(previous['materials'][role])for role in ROLES}
    metadata=dict(schema_version=1,units='metres',axis='CAD +Y, UE import reflects Y once',
        namespace='/Game/MPRWarehouse/RebuildB50B57',role_order=ROLES,bank_ids=BANKS,
        roof_z_m=ROOF,top_z_m=TOP,pitch_m=PITCH,uv_origin_m=ORIGIN,
        existing_actor_transforms='Unchanged; replace only the five retained SolarBank mesh references',
        input_hashes=input_hashes,devices_unchanged=devices,fields=field_rows,blocks=blocks,
        geometry=mapping(final),service_aisles=mapping(aisles),module_cells=len(global_cells),
        old_module_cells=previous['roof_layout']['visual_module_count'],area_m2=final.area,
        minimum_device_clearance_m=final.distance(device_solids),required_device_clearance_m=DEVICE_CLEARANCE,
        major_region_count=len(fields),render_bank_count=len(BANKS),
        render_lod_count=3,per_lod_same_top_mask=True,old_assets_modified=False,
        previous_solar_actor_labels=['MPR4_SolarBank_'+bank for bank in BANKS],
        design_policy='Preserve 16 major regions; regular orthogonal panel grid; join same-row device clearances; remove tails smaller than 2 columns by 3 rows and isolated clusters below 24 modules')
    payload=dict(input_hashes=input_hashes,geometry=geometry,materials=materials,layout_sha256=None)
    write(OUT/'layout.json',metadata)
    payload['layout_sha256']=sha(OUT/'layout.json')
    with gzip.GzipFile(filename='',mode='wb',fileobj=(OUT/'geometry_payload.json.gz').open('wb'),mtime=0)as stream:
        stream.write(json.dumps(payload,separators=(',',':')).encode('utf8'))
    (OUT/'plan_comparison.svg').write_text(preview(roof,unary_union([r[1]for r in fields]),final,devices,aisles,blocks),encoding='utf8')
    audit=dict(success=True,layout_sha256=sha(OUT/'layout.json'),payload_sha256=sha(OUT/'geometry_payload.json.gz'),
        regions=16,banks=5,fbx_meshes_planned=len(geometry),devices_fixed=len(devices),
        module_cells=len(global_cells),rectangular_blocks=sum(map(len,blocks.values())),area_m2=final.area,
        minimum_device_clearance_m=final.distance(device_solids),device_clearance_overlap_m2=final.intersection(device_clear).area,
        aisle_overlap_m2=final.intersection(aisles).area,roof_exterior_overlap_m2=final.difference(roof).area,
        triangles_by_mesh={name:sum(len(face)-2 for verts,faces,uv in roles.values()for face in faces)for name,roles in geometry.items()},
        top_mask_identical_across_lods=True,old_assets_modified=False,input_hashes=input_hashes)
    for name,path in sources.items():assert sha(path)==input_hashes[name], ('Source was modified',name)
    write(OUT/'geometry_validation.json',audit)
    print(json.dumps({k:v for k,v in audit.items()if k not in {'triangles_by_mesh','input_hashes'}},indent=2),flush=True)


if __name__=='__main__':
    main()
