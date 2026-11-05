"""Finish the adjacent C08 ramp fragments without moving any geometry.

Only material indices and approved local normals in CrossingRamp_0_-3 change.
Whole boundary faces are retained to preserve every vertex, face, UV and colour.
"""
import hashlib,json,shutil,struct,zlib
from collections import defaultdict
import numpy as np
import approve_mpr_crossing_normals as base
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import substring,unary_union
ROOT=base.ROOT;SOURCE=base.SOURCE
NAME='SM_MPRR_CrossingRamp_0_-3'
OLD_SHA='2d70584959793e8d4588f63c6bf4cf29932117ee0332c2a85b290045bc84531c'
ROAD='MPR4_TerminalAsphalt'

def face_key(points):
    return hashlib.sha256(json.dumps(sorted(tuple(float(v)for v in p)for p in points),separators=(',',':')).encode()).hexdigest()

def positions_hash(faces):
    return hashlib.sha256(json.dumps([p.tolist()for role,p,n in faces],separators=(',',':')).encode()).hexdigest()

def patch_array(path,node_name,items,required=True):
    data=bytearray(path.read_bytes());wide=struct.unpack_from('<I',data,23)[0]>=7500
    fmt='<QQQB'if wide else'<IIIB';size=struct.calcsize(fmt);width=8 if wide else 4;headers=[];targets=[]
    def visit(pos):
        end,count,propbytes,namesize=struct.unpack_from(fmt,data,pos)
        if not end:return 0
        headers.append((pos,end));prop=pos+size+namesize
        if bytes(data[pos+size:prop])==node_name:targets.append((pos,prop,propbytes))
        child=prop+propbytes
        while child<end:
            nxt=visit(child)
            if not nxt:break
            child=nxt
        return end
    pos=27
    while True:
        pos=visit(pos)
        if not pos:break
    if not targets and not required:return
    assert len(targets)==1,(node_name,len(targets))
    node,prop,oldprops=targets[0];kind=chr(data[prop]);count,encoding,length=struct.unpack_from('<III',data,prop+1)
    raw=np.asarray(items,dtype={'d':'<f8','f':'<f4','i':'<i4'}[kind]).reshape(-1)
    payload=zlib.compress(raw.tobytes())if encoding else raw.tobytes();start=prop+13;end=start+length;delta=len(payload)-length
    data[start:end]=payload
    for position,offset in headers:
        if offset>=end:struct.pack_into('<Q'if wide else'<I',data,position+(delta if position>=end else 0),offset+delta)
    struct.pack_into('<Q'if wide else'<I',data,node+2*width,oldprops+delta)
    struct.pack_into('<I',data,prop+1,len(raw));struct.pack_into('<I',data,prop+9,len(payload));path.write_bytes(data)

def colors(path):
    objects=next(n for n in base.build.reader.fbx_nodes(path)if n[0]==b'Objects')
    geometry=next(n for n in objects[2]if n[0]==b'Geometry')
    layer=next(n for n in geometry[2]if n[0]==b'LayerElementColor')
    fields={n[0]:n[1][0]for n in layer[2]};v=np.asarray(fields[b'Colors']).reshape(-1,4)
    return v[np.asarray(fields[b'ColorIndex'],int)]if fields[b'ReferenceInformationType']==b'IndexToDirect'else v

def main():
    manifest=base.build.transport.revision.read(SOURCE/'manifest.json');row=next(r for r in manifest['meshes']if r['name']==NAME)
    if row.get('residual_material_cleanup'):
        assert base.build.transport.revision.sha(ROOT/row['fbx'])==row['sha256'];print('CROSSING_RESIDUAL_ALREADY_COMPLETE');return
    assert row['sha256']==OLD_SHA and base.build.transport.revision.sha(ROOT/row['fbx'])==OLD_SHA
    path=ROOT/row['fbx'];stage=ROOT/'Saved/MPR/crossing_surface_20261105/residual_material';stage.mkdir(parents=True,exist_ok=True)
    previous=stage/(NAME+'.before.fbx');shutil.copy2(path,previous);target=stage/(NAME+'.fbx');shutil.copy2(path,target)
    before=base.native(path,row['material_roles']);layout,crossing,scope=base.build.plan()
    road=next(r for r in layout['road_centerlines']if r['id']==crossing['road_id']);line=LineString(road['points_m'])
    stations=[line.project(Point(p))for poly in base.build.pieces(scope)for p in poly.exterior.coords]
    window=substring(line,min(stations),max(stations)).buffer(road['width_m']/2+.001,cap_style=2).intersection(layout['roads'])
    selected=[i for i,(role,p,n)in enumerate(before)if role=='MPR3_Asphalt'and Polygon(p[:,:2]).intersection(window).area>1e-6]
    assert len(selected)==115 and 293 in selected
    selected_set=set(selected);polygons=[Polygon(before[i][1][:,:2])for i in selected]
    # The outermost native faces cross the interval boundary by <0.4m. Keep
    # each face whole; all remain on the same C08 road and no other crossing.
    selected_surface=unary_union(polygons)
    assert selected_surface.difference(layout['roads'].buffer(.0002)).area<.001
    for entry in layout['crossings']:
        if entry['id']!='Crossing_04':assert selected_surface.distance(Point(entry['point_m']))>5
    all_rows=base.build.current_rows();all_rows.update({r['name']:r for r in manifest['meshes']})
    normals=defaultdict(lambda:np.zeros(3))
    def key(point):return tuple(np.round(point,4))
    reference_names=[f'SM_MPRR_{stem}_{x}_{y}'for stem in ['Roads','CrossingDeck','CrossingRamp']for x,y in base.build.TILES]
    for name in reference_names:
        item=all_rows[name]
        for role,p,n in base.native(ROOT/item['fbx'],item['material_roles']):
            cross=np.cross(p[1]-p[0],p[2]-p[0])
            for vertex in p:normals[key(vertex)]+=cross/2
    normals={k:v/np.linalg.norm(v)for k,v in normals.items()if np.linalg.norm(v)>1e-15}
    new_roles=[ROAD if i in selected_set else role for i,(role,p,n)in enumerate(before)]
    vectors=[]
    for i,(role,p,n)in enumerate(before):
        vectors.extend([normals[key(v)]for v in p]if new_roles[i]==ROAD else n)
    patch_array(target,b'Materials',[row['material_roles'].index(role)for role in new_roles])
    patch_array(target,b'Normals',vectors);patch_array(target,b'NormalsIndex',list(range(len(vectors))),False)
    after=base.native(target,row['material_roles'])
    assert positions_hash(before)==positions_hash(after)
    old_names,old_uv=base.native_attributes(previous);new_names,new_uv=base.native_attributes(target)
    assert old_names==new_names==row['material_roles']and np.array_equal(old_uv,new_uv)and np.array_equal(colors(previous),colors(target))
    unchanged_normals=0
    for i,((role,p,n),(new_role,q,m))in enumerate(zip(before,after)):
        assert new_role==new_roles[i]
        if new_role!=ROAD:assert np.array_equal(n,m);unchanged_normals+=len(n)
    audit=dict(success=True,phase='Final adjacent C08 ramp material cleanup',crossing_id='Crossing_04',road_id=crossing['road_id'],
        mesh_name=NAME,approved_previous_sha256=OLD_SHA,final_fbx_sha256=base.build.transport.revision.sha(target),
        selected_source_face_indices=selected,approved_material_only_face_geometry_keys=[face_key(before[i][1])for i in selected],
        material_change={'from':'MPR3_Asphalt','to':ROAD},selected_whole_face_area_m2=selected_surface.area,
        selected_area_inside_original_road_interval_m2=selected_surface.intersection(window).area,
        whole_face_boundary_extension_area_m2=selected_surface.difference(window).area,
        selected_bounds_m=list(selected_surface.bounds),road_station_interval_m=[min(stations),max(stations)],
        source_triangles_before=len(before),source_triangles_after=len(after),positions_faces_sha256=positions_hash(after),
        before_material_indices=[row['material_roles'].index(role)for role,p,n in before],
        after_material_indices=[row['material_roles'].index(role)for role,p,n in after],
        uv_sha256=hashlib.sha256(new_uv.tobytes()).hexdigest(),edge_fade_colors_sha256=hashlib.sha256(colors(target).tobytes()).hexdigest(),
        positions_and_faces_exact=True,uv_exact=True,edge_fade_colors_exact=True,native_material_slot_names=new_names,
        unchanged_old_material_corner_normals=unchanged_normals,nonlocal_material_faces_preserved=True,
        vertices_moved=False,other_crossings_changed=False,
        source_before_backup=previous.relative_to(ROOT).as_posix())
    shutil.copy2(target,path);row.update(sha256=audit['final_fbx_sha256'],approved_previous_sha256=OLD_SHA,residual_material_cleanup=True,
        source_face_vertices_sha256=base.geometry_hash(after),positions_faces_sha256=audit['positions_faces_sha256'])
    manifest['residual_material_cleanup']=dict(audit='residual_material_validation.json',mesh_name=NAME,material_only_faces=len(selected),geometry_unchanged=True)
    base.build.transport.revision.write(SOURCE/'manifest.json',manifest)
    base.build.transport.revision.write(SOURCE/'residual_material_validation.json',audit)
    normal=base.build.transport.revision.read(SOURCE/'ramp_normals_validation.json')
    initial=normal['meshes'][NAME];normal.setdefault('initial_phase_meshes',{})[NAME]=initial
    normal['meshes'][NAME]=dict(approved_previous_sha256=OLD_SHA,new_sha256=row['sha256'],positions_topology_exact=True,
        material_regions_change_explicitly_approved=True,approved_material_face_count=len(selected),positions_faces_sha256=audit['positions_faces_sha256'],
        uv_coordinates_exact=True,edge_fade_colors_exact=True,native_material_slot_names=new_names,nonlocal_old_material_normals_exact=True)
    base.build.transport.revision.write(SOURCE/'ramp_normals_validation.json',normal)
    validation=base.build.transport.revision.read(SOURCE/'geometry_validation.json')
    validation['initial_phase_native_fbx_validation']=validation.pop('native_fbx_validation')
    validation['initial_phase_native_fbx_validation']['phase']='Initial F97 scope before approved adjacent C08 material cleanup'
    validation['residual_material_cleanup']=audit;validation['ramp_normals_refinement']=normal
    base.build.transport.revision.write(SOURCE/'geometry_validation.json',validation)
    print('CROSSING_RESIDUAL_MATERIAL_READY',len(selected),selected_surface.area,row['sha256'],flush=True)

if __name__=='__main__':main()
