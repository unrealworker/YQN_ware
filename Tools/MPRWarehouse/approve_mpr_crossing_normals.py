"""CPU-check staged ramp normals, then update only the two new source FBXs."""
import hashlib,json,shutil,sys,struct,zlib
from pathlib import Path
import build_mpr_crossing_surface as build
import numpy as np
ROOT=build.ROOT;SOURCE=build.OUT
STAGE=ROOT/'Saved/MPR/crossing_surface_20261105/ramp_normals'

def native(path,roles):
    obj=next(n for n in build.reader.fbx_nodes(path)if n[0]==b'Objects')
    geo=next(n for n in obj[2]if n[0]==b'Geometry');fields={n[0]:n for n in geo[2]}
    vv=np.asarray(fields[b'Vertices'][1][0],float).reshape(-1,3)
    normals={n[0]:n[1][0]for n in fields[b'LayerElementNormal'][2]}
    assert normals[b'MappingInformationType']==b'ByPolygonVertex'
    nn=np.asarray(normals[b'Normals'],float).reshape(-1,3)
    if normals[b'ReferenceInformationType']==b'IndexToDirect':nn=nn[np.asarray(normals[b'NormalsIndex'],int)]
    material={n[0]:n[1][0]for n in fields[b'LayerElementMaterial'][2]};mi=material[b'Materials']
    result=[];face=[];corners=[]
    for corner,index in enumerate(fields[b'PolygonVertexIndex'][1][0]):
        face.append(int(index)if index>=0 else int(-index-1));corners.append(corner)
        if index<0:
            role=roles[mi[0]if len(mi)==1 else mi[len(result)]]
            result.append((role,vv[face],nn[corners]));face=[];corners=[]
    return result

def geometry_hash(faces):
    values=[(role,points.tolist())for role,points,normals in faces]
    return hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest()

def native_attributes(path):
    nodes=build.reader.fbx_nodes(path);obj=next(n for n in nodes if n[0]==b'Objects')
    connections=next(n for n in nodes if n[0]==b'Connections')
    materials={n[1][0]:n[1][1].split(b'\x00')[0].decode()for n in obj[2]if n[0]==b'Material'}
    model=next(n[1][0]for n in obj[2]if n[0]==b'Model')
    names=[materials[c[1][1]]for c in connections[2]if c[1][0]==b'OO'and c[1][2]==model and c[1][1]in materials]
    geom=next(n for n in obj[2]if n[0]==b'Geometry');layer=next(n for n in geom[2]if n[0]==b'LayerElementUV')
    fields={n[0]:n[1][0]for n in layer[2]};uv=np.asarray(fields[b'UV']).reshape(-1,2)
    if fields[b'ReferenceInformationType']==b'IndexToDirect':uv=uv[np.asarray(fields[b'UVIndex'],int)]
    return names,uv

def prepare_inputs():
    """Run before the exporter's --refine-ramp-normals background pass."""
    STAGE.mkdir(parents=True,exist_ok=True)
    manifest=build.transport.revision.read(SOURCE/'manifest.json');rows=build.current_rows()
    rows.update({r['name']:r for r in manifest['meshes']})
    targets=[rows[f'SM_MPRR_CrossingRamp_{x}_{y}']for x,y in build.TILES]
    references=[rows[f'SM_MPRR_{stem}_{x}_{y}']for stem in ['Roads','CrossingDeck']for x,y in build.TILES]
    for row in targets:shutil.copy2(ROOT/row['fbx'],STAGE/(row['name']+'.before.fbx'))
    build.transport.revision.write(STAGE/'inputs.json',dict(targets=targets,references=references))

def preserve_exact_normals(path,before,after):
    """Write corner vectors directly, avoiding Blender's packed-normal rounding."""
    groups={}
    for role,p,n in after:
        if role=='MPR4_TerminalAsphalt':
            for point,normal in zip(p,n):groups.setdefault(tuple(np.round(point,4)),[]).append(normal)
    averages={key:np.mean(value,axis=0)for key,value in groups.items()}
    averages={key:value/np.linalg.norm(value)for key,value in averages.items()}
    values=[]
    for (role,p,n),(_,q,m)in zip(before,after):
        values.extend([averages[tuple(np.round(point,4))]for point in q]if role=='MPR4_TerminalAsphalt'else n)
    def patch_array(node_name,items,required=True):
        data=bytearray(path.read_bytes());version=struct.unpack_from('<I',data,23)[0]
        wide=version>=7500;fmt='<QQQB'if wide else'<IIIB';size=struct.calcsize(fmt);width=8 if wide else 4
        headers=[];targets=[]
        def visit(pos):
            end,count,propbytes,namesize=struct.unpack_from(fmt,data,pos)
            if not end:return 0
            headers.append((pos,end));name=bytes(data[pos+size:pos+size+namesize]);prop=pos+size+namesize
            if name==node_name:targets.append((pos,prop,propbytes))
            child=prop+propbytes
            while child<end:
                next_child=visit(child)
                if not next_child:break
                child=next_child
            return end
        pos=27
        while True:
            pos=visit(pos)
            if not pos:break
        if not targets and not required:return
        assert len(targets)==1
        node,prop,oldprops=targets[0];kind=chr(data[prop]);assert kind in{'d','f','i'}
        count,encoding,length=struct.unpack_from('<III',data,prop+1)
        raw=np.asarray(items,dtype={'d':'<f8','f':'<f4','i':'<i4'}[kind]).reshape(-1)
        payload=zlib.compress(raw.tobytes())if encoding else raw.tobytes()
        begin=prop+13;end=begin+length;delta=len(payload)-length
        data[begin:end]=payload
        for position,offset in headers:
            new_position=position+(delta if position>=end else 0)
            if offset>=end:struct.pack_into('<Q'if wide else'<I',data,new_position,offset+delta)
        struct.pack_into('<Q'if wide else'<I',data,node+2*width,oldprops+delta)
        struct.pack_into('<I',data,prop+1,len(raw));struct.pack_into('<I',data,prop+9,len(payload))
        path.write_bytes(data)
    patch_array(b'Normals',values)
    patch_array(b'NormalsIndex',list(range(len(values))),required=False)

def main():
    inputs=build.transport.revision.read(STAGE/'inputs.json');manifest=build.transport.revision.read(SOURCE/'manifest.json')
    report=dict(success=False,meshes={})
    for row in inputs['targets']:
        path=SOURCE/(row['name']+'.fbx');staged=STAGE/(row['name']+'.fbx')
        assert build.transport.revision.sha(path)==row['sha256'],'Already-refined/unreviewed source'
        before=native(path,row['material_roles']);after=native(staged,row['material_roles'])
        assert geometry_hash(before)==geometry_hash(after),('FBX positions/topology/material regions changed',row['name'])
        preserve_exact_normals(staged,before,after)
        after=native(staged,row['material_roles'])
        names,uv=native_attributes(staged);old_names,old_uv=native_attributes(path)
        assert names==old_names==row['material_roles']and np.array_equal(uv,old_uv),'FBX slots/UV changed'
        nonlocal_error=0.;changed=0;groups={}
        for (role,p,n),(_,q,m)in zip(before,after):
            if role!='MPR4_TerminalAsphalt':nonlocal_error=max(nonlocal_error,float(np.max(np.abs(n-m))))
            else:
                changed+=int(np.sum(np.linalg.norm(n-m,axis=1)>1e-6))
                for point,normal in zip(q,m):groups.setdefault(tuple(np.round(point,4)),[]).append(normal)
        shared_error=max((float(np.max(np.linalg.norm(np.asarray(normals)-normals[0],axis=1)))for normals in groups.values()),default=0.)
        assert nonlocal_error<1e-6 and shared_error<1e-6 and changed>0,(row['name'],nonlocal_error,shared_error,changed)
        report['meshes'][row['name']]=dict(approved_previous_sha256=row['sha256'],new_sha256=build.transport.revision.sha(staged),
            source_face_vertices_sha256=geometry_hash(before),positions_topology_material_regions_exact=True,
            uv_coordinates_exact=True,native_material_slot_names=names,
            unchanged_nonlocal_normal_max_error=nonlocal_error,shared_vertex_normal_max_error=shared_error,changed_local_corners=changed)
    # Every verification above finishes before either source file is replaced.
    for row in manifest['meshes']:
        if row['name']not in report['meshes']:continue
        result=report['meshes'][row['name']]
        shutil.copy2(STAGE/(row['name']+'.fbx'),ROOT/row['fbx'])
        row.update(approved_previous_sha256=result['approved_previous_sha256'],sha256=result['new_sha256'],local_smooth_normals=True,
            source_face_vertices_sha256=result['source_face_vertices_sha256'])
    manifest['ramp_normals_refinement']=dict(mesh_names=sorted(report['meshes']),vertices_moved=False,material_slots_changed=False)
    report['success']=True
    build.transport.revision.write(SOURCE/'manifest.json',manifest)
    build.transport.revision.write(SOURCE/'ramp_normals_validation.json',report)
    validation=build.transport.revision.read(SOURCE/'geometry_validation.json')
    validation['ramp_normals_refinement']=report
    build.transport.revision.write(SOURCE/'geometry_validation.json',validation)
    print('CROSSING_RAMP_NORMALS_APPROVED',report,flush=True)

if __name__=='__main__':prepare_inputs()if '--prepare' in sys.argv else main()
