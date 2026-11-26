"""Remove CAD column assemblies whose solid geometry intersects an actual storage mesh."""
from collections import defaultdict
from itertools import product
import hashlib
import json
import math
from pathlib import Path

import unreal

MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
REPORT = ROOT/'Saved/GHS_CAD24/column-clipping.json'
BODY, BASE, EDGE = 'GHS_CAD_Columns', 'GHS_ColumnBases', 'GHS_ColumnEdgeOutlines'
EPS_CM = .01


def xyz(v):
    return (v.x, v.y, v.z)


def sub(a,b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def dot(a,b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def bounds(points):
    axes = list(zip(*points))
    return tuple(map(min, axes)), tuple(map(max, axes))


def overlaps(a,b):
    return all(a[0][k] <= b[1][k] and b[0][k] <= a[1][k] for k in range(3))


def corners(box):
    return product(*zip(*box))


class Pose:
    def __init__(self,t):
        r = t.rotation.rotator()
        assert abs(r.pitch)<.001 and abs(r.roll)<.001, 'Unexpected tilted storage or column'
        self.p, self.s = xyz(t.translation), xyz(t.scale3d)
        assert min(self.s)>0
        self.c, self.d = math.cos(math.radians(r.yaw)), math.sin(math.radians(r.yaw))
        self.signature = tuple(round(n,5) for n in (*self.p,*self.s,self.c,self.d))

    def world(self,p):
        x,y,z = (v*s for v,s in zip(p,self.s))
        return (self.p[0]+self.c*x-self.d*y, self.p[1]+self.d*x+self.c*y, self.p[2]+z)

    def local(self,p):
        x,y,z = sub(p,self.p)
        return ((self.c*x+self.d*y)/self.s[0],(-self.d*x+self.c*y)/self.s[1],z/self.s[2])


def clip_triangle(tri, box):
    """A triangle must have nonzero area inside the six planes of the eroded box."""
    poly = list(tri)
    for k in range(3):
        for sign, bound in ((1,box[0][k]),(-1,box[1][k])):
            clipped = []
            for a,b in zip(poly,poly[1:]+poly[:1]):
                da,db = sign*(a[k]-bound),sign*(b[k]-bound)
                if da >= 0:
                    clipped.append(a)
                if (da>0 and db<0) or (db>0 and da<0):
                    t = da/(da-db)
                    clipped.append(tuple(u+t*(v-u) for u,v in zip(a,b)))
            if len(clipped)<3:
                return False
            poly = clipped
    return any(math.hypot(*cross(sub(poly[i],poly[0]),sub(poly[i+1],poly[0])))>1.e-10
               for i in range(1,len(poly)-1))


def mesh_geometry(mesh):
    triangles = []
    for section in range(mesh.get_num_sections(0)):
        vertices, indices, *_ = unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,section)
        points = [xyz(v) for v in vertices]
        for i in range(0,len(indices),3):
            tri = tuple(points[indices[k]] for k in (i,i+1,i+2))
            triangles.append((bounds(tri),tri,section,i//3))
    assert len(triangles)==mesh.get_num_triangles(0) and triangles, mesh.get_name()
    return triangles


def mesh_contains(triangles, point):
    # Generalized winding number of the actual oriented LOD0 surfaces. This
    # covers a small column base completely enclosed by a closed carton.
    winding = 0.
    for _,tri,_,_ in triangles:
        a,b,c = (sub(v,point) for v in tri)
        la,lb,lc = math.hypot(*a),math.hypot(*b),math.hypot(*c)
        winding += 2*math.atan2(dot(a,cross(b,c)), la*lb*lc+dot(a,b)*lc+dot(b,c)*la+dot(c,a)*lb)
    turns = abs(winding)/(4*math.pi)
    return round(turns)>0 and abs(round(turns)-turns)<.0001


def narrow(column, target, triangles):
    cpose, tpose = column['pose'], target['pose']
    # A 0.1 mm world-space inset excludes coincident faces and numerical noise.
    box = tuple(tuple(v+sign*EPS_CM/s for v,s in zip(side,cpose.s))
                for side,sign in zip(column['local'],(1,-1)))
    near = bounds(tpose.local(cpose.world(p)) for p in corners(box))
    for tb,tri,section,index in triangles:
        if overlaps(near,tb) and clip_triangle([cpose.local(tpose.world(p)) for p in tri],box):
            return dict(test='triangle_inside_column',section=section,triangle=index)
    center = tpose.local(cpose.world(tuple((a+b)/2 for a,b in zip(*box))))
    if mesh_contains(triangles,center):
        return dict(test='column_center_inside_closed_mesh')
    return None


def gather():
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    storage = []
    parts, comps = {},{}
    for actor in subsystem.get_all_level_actors():
        name = actor.get_actor_label()
        for comp in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = comp.static_mesh
            if not mesh:
                continue
            is_part = name in (BODY,BASE,EDGE)
            if not is_part and not mesh.get_name().startswith(('SM_GHS_V2Rack_CAD24_','SM_GHS_Presentation_Cargo')):
                continue
            if is_part:
                assert mesh.get_path_name()=='/Engine/BasicShapes/Cube.Cube' and name not in comps, name
                comps[name] = comp
                parts[name] = []
            b = mesh.get_bounds()
            origin, extent = xyz(b.origin),xyz(b.box_extent)
            local = (sub(origin,extent),tuple(a+b for a,b in zip(origin,extent)))
            for i in range(comp.get_instance_count()):
                pose = Pose(comp.get_instance_transform(i,True))
                data = dict(actor=name,index=i,pose=pose,mesh=mesh,local=local,
                            box=bounds(pose.world(p) for p in corners(local)))
                (parts[name] if is_part else storage).append(data)
    assert set(parts)=={BODY,BASE,EDGE} and storage, (list(parts),len(storage))
    return parts,comps,storage


def owners(parts):
    result = {i['index']:[i] for i in parts[BODY]}
    for item in parts[BASE]+parts[EDGE]:
        # Bases share the CAD centre. Outline strip centres lie in the column
        # footprint, including its boundary. Resolve the parent afresh after HISM swaps.
        matches = []
        for col in parts[BODY]:
            p = col['pose'].local(item['pose'].p)
            if item['actor']==BASE:
                ok = math.dist(col['pose'].p[:2],item['pose'].p[:2])<.1
            else:
                ok = all(col['local'][0][k]-.02 <= p[k] <= col['local'][1][k]+.02 for k in range(3))
            if ok:
                matches.append(col['index'])
        assert len(matches)==1, (item['actor'],item['index'],matches)
        result[matches[0]].append(item)
    return result


def cells(box):
    return product(*(range(math.floor(box[0][i]/500), math.floor(box[1][i]/500)+1) for i in (0,1)))


def audit():
    parts,comps,storage = gather()
    assemblies = owners(parts)
    grid = defaultdict(list)
    for i,obj in enumerate(storage):
        for cell in cells(obj['box']):
            grid[cell].append(i)
    cache, conflicts = {}, []
    for parent,pieces in assemblies.items():
        for part in pieces:
            if part['actor']==EDGE:
                # Geometrically verified below: these strips are inside each
                # body, hence body penetration covers every outline penetration.
                body=pieces[0]
                contained=all(all(body['local'][0][k]-.001 <= p[k] <= body['local'][1][k]+.001 for k in range(3))
                              for p in (body['pose'].local(part['pose'].world(q)) for q in corners(part['local'])))
                if contained:
                    continue
            nearby = sorted({i for cell in cells(part['box']) for i in grid[cell]})
            for i in nearby:
                obj = storage[i]
                if not overlaps(obj['box'],part['box']):
                    continue
                mesh = obj['mesh']
                if mesh not in cache:
                    cache[mesh] = mesh_geometry(mesh)
                hit = narrow(part,obj,cache[mesh])
                if hit:
                    conflicts.append(dict(parent=parent,position_cm=pieces[0]['pose'].p,column_part=part['actor'],
                                          target_actor=obj['actor'],target_index=obj['index'],mesh=mesh.get_name(),**hit))
                    break
            else:
                continue
            break
    return parts,comps,assemblies,conflicts


def inventory(parts):
    return {label:sorted(p['pose'].signature for p in rows) for label,rows in parts.items()}


def write(report):
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


def prune():
    parts,comps,assemblies,conflicts = audit()
    removed = defaultdict(set)
    for hit in conflicts:
        for item in assemblies[hit['parent']]:
            removed[item['actor']].add(item['index'])
    expected = inventory({k:[p for p in v if p['index'] not in removed[k]] for k,v in parts.items()})
    report = dict(map=MAP,tolerance_cm=EPS_CM,stage='before',before={k:len(v) for k,v in parts.items()},
                  removed={k:len(removed[k]) for k in parts},conflicts=conflicts)
    write(report)
    for label, indices in removed.items():
        if indices:
            component = comps[label]
            component.get_owner().modify()
            component.modify()
            for i in sorted(indices,reverse=True):
                assert component.remove_instance(i), (label,i)
    verify(expected)
    report.update(stage='before_save',after={k:len(v) for k,v in expected.items()})
    write(report)
    return report,expected


def verify(expected):
    parts,_,_,conflicts = audit()
    assert not conflicts and inventory(parts)==expected, ('Unexpected surviving geometry',conflicts[:3])


def save_and_reload(levels,report,expected):
    assert levels.save_current_level()
    assert levels.load_level('/Engine/Maps/Entry')
    assert levels.load_level(MAP)
    verify(expected)
    report.update(stage='reload_verified',remaining_conflicts=0,
                  map_sha256=hashlib.sha256((ROOT/'Content'/MAP.removeprefix('/Game/')).with_suffix('.umap').read_bytes()).hexdigest())
    write(report)
    unreal.log('GHS CAD24 column audit: '+str(REPORT))


if __name__=='__main__':
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    assert levels.load_level(MAP)
    report,expected = prune()
    save_and_reload(levels,report,expected)
