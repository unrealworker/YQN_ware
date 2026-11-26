"""Prepare or apply road-marking coverage using authored lane triangles in three display meshes.

After importing or rebuilding Park, RoadTerminalFade or replay parking FBX assets,
run road_marking_sources.py in Blender and this UE editor commandlet with -RoadApply.
It also validates an installed mesh in a fresh process; -RoadPrepare only audits.
Original mesh packages are saved under Saved/GHSRenderQuality/RoadAssets/Before.
"""
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
import hashlib
import json
import math
import shutil
import sys
import struct
import unreal

ROOT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
OUT=ROOT/'Saved/GHSRenderQuality/RoadAssets'
PARK='/Game/GHSZcoolSmartFactory/Park/'
END='/Game/GHSZcoolSmartFactory/RoadTerminalFade/'
DEST='/Game/GHSZcoolSmartFactory/VisualPolish/'
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary
unreal.load_module('StaticMeshEditor')
unreal.load_module('ProceduralMeshComponent')
SM=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
TARGETS=[
    (PARK+'Meshes/SM_GHSPark_Markings','park',PARK+'Materials/M_GHSPark_Markings'),
    ('/Game/GHSOrderReplay/Parking/SM_ReplayNoCars_Markings','park',PARK+'Materials/M_GHSPark_Markings'),
    (END+'Meshes/SM_GHSRoadTerminal_Markings','terminal','/Game/GHSZcoolSmartFactory/ContextTransition/Materials/M_GHSContextTransition_Markings')]
OWNER='GHS.RoadCoverage'
VERSION='1'


def package(path):
    return ROOT/'Content'/(path.removeprefix('/Game/')+'.uasset')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(point):
    return tuple(math.floor(x/0.05) for x in point[:3])


def select_faces(mesh,quads):
    spatial=defaultdict(list)
    for i,quad in enumerate(quads):
        for p in quad:
            spatial[key(p)].append((i,p))
    cache={}
    def nearby(point):
        xyz=point.to_tuple()
        if xyz not in cache:
            cell=key(xyz)
            found={}
            for offset in product((-1,0,1), repeat=3):
                for i,p in spatial.get(tuple(a+b for a,b in zip(cell,offset)),()):
                    distance=math.dist(p[:3],xyz)
                    if distance<.025 and (i not in found or distance<found[i][0]):found[i]=(distance,p)
            cache[xyz]=found
        return cache[xyz]
    rows=[]
    coverage=Counter()
    for section in range(mesh.get_num_sections(0)):
        vertices,indices,*_=unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,section)
        attached=[nearby(v) for v in vertices]
        for j in range(0,len(indices),3):
            iv=indices[j:j+3]
            matches=set(attached[iv[0]]).intersection(attached[iv[1]],attached[iv[2]])
            if not matches:continue
            i=min(matches,key=lambda candidate: sum(attached[k][candidate][0] for k in iv))
            rows.append([[*vertices[k].to_tuple(),*attached[k][i][1][3:]] for k in iv])
            coverage[i]+=1
    counts=Counter(coverage.values())
    print(mesh.get_name(),'source quads',len(quads),'matched',len(coverage),'faces per matched quad',counts,flush=True)
    if len(coverage)!=len(quads) or counts!={2:len(quads)}:
        missing=[quads[k] for k in range(len(quads)) if coverage[k]!=2]
        (OUT/(mesh.get_name()+'-exceptions.json')).write_text(json.dumps(missing))
    assert len(coverage)==len(quads) and counts=={2:len(quads)},(mesh.get_name(),counts,len(coverage),len(quads))
    return rows


def prepare(mesh,kind):
    existing=LIB.get_metadata_tag(mesh,OWNER)
    channels=SM.get_num_uv_channels(mesh,0)-(1 if existing else 0)
    q=json.loads((OUT/(kind+'-source-quads.json')).read_bytes())
    rows=select_faces(mesh,q)
    receipt=dict(mesh=mesh.get_name(),triangles=rows,uv_channel=channels,total_triangles=mesh.get_num_triangles(0))
    dest=OUT/(mesh.get_name()+'.json')
    dest.write_text(json.dumps(receipt,separators=(',',':')),encoding='utf8')
    return dest,receipt


def geometry(mesh):
    # Canonical triangles remain comparable after UE splits a material section.
    faces=[]
    for s in range(mesh.get_num_sections(0)):
        vertices,indices,normals,uvs,tangents=unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,s)
        corners=[struct.pack('<8f',*v.to_tuple(),*n.to_tuple(),*uv.to_tuple()) for v,n,uv in zip(vertices,normals,uvs)]
        for j in range(0,len(indices),3):
            tri=[corners[i] for i in indices[j:j+3]]
            faces.append(min(b''.join(tri[k:]+tri[:k]) for k in range(3)))
    body=mesh.get_editor_property('body_setup')
    return dict(triangles=len(faces),geometry_normal_uv0=hashlib.sha256(b''.join(sorted(faces))).hexdigest(),
                collision=body.get_editor_property('agg_geom').export_text() if body else None)


def main():
    command=unreal.SystemLibrary.get_command_line().lower().split()
    sys.path.insert(0,str(ROOT/'Scripts/ghs'))
    import road_marking_material
    results={}
    backup=OUT/'Before'
    backup.mkdir(exist_ok=True)
    apply='-roadapply' in command
    for path,kind,source in TARGETS:
        m=LIB.load_asset(path)
        assert m
        dest,receipt=prepare(m,kind)
        print('ROAD_RECEIPT',m.get_name(),len(receipt['triangles']),receipt['uv_channel'],flush=True)
        assert SM.get_lod_count(m)==1,('Validate the new reduction levels before applying',path)
        state=geometry(m)
        state_path=backup/(m.get_name()+'.json')
        if not state_path.exists():
            assert not LIB.get_metadata_tag(m,OWNER)
            state_path.write_text(json.dumps(state),encoding='utf8')
            shutil.copy2(package(path),backup/package(path).name)
        original=json.loads(state_path.read_bytes())
        assert state==original,m.get_name()
        if apply or '-roadmaterial' in command:
            target=DEST+'M_RoadCoverage_'+kind.title()
            mat=road_marking_material.build(source,target,receipt['uv_channel'],VERSION,OWNER)
            if not apply:continue
            installed=LIB.get_metadata_tag(m,OWNER)
            assert unreal.GHSRoadMarkingEditorLibrary.apply_road_ribbon_uv(m,str(dest),mat,receipt['uv_channel'])
            if not installed:
                LIB.set_metadata_tag(m,OWNER,VERSION)
                assert geometry(m)==original,m.get_name()
                assert LIB.save_loaded_asset(m,only_if_is_dirty=False)
            sections=Counter()
            for sec in range(m.get_num_sections(0)):
                slot=SM.get_lod_material_slot(m,0,sec)
                _,indices,*_=unreal.ProceduralMeshLibrary.get_section_from_static_mesh(m,0,sec)
                sections[slot]+=len(indices)//3
            assert sections[1]==len(receipt['triangles']) and sections[0]==state['triangles']-sections[1],sections
            results[m.get_name()]=dict(lods=SM.get_lod_count(m),sections=dict(sections),triangles=state['triangles'],matched=len(receipt['triangles']),
                before_sha256=sha(backup/package(path).name),asset_sha256=sha(package(path)),
                material=target,geometry_normal_uv0=state['geometry_normal_uv0'])
    if apply:(OUT/'installed.json').write_text(json.dumps(results,indent=2),encoding='utf8')


if __name__=='__main__':main()
