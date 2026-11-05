"""Read-only native saved-blend and FBX check; no NumPy/GEOS imports.

Run a fresh background Blender for each <=30 mesh batch. No asset writes.
"""
import argparse,hashlib,json,math,sys,traceback
from collections import Counter,defaultdict
from itertools import product
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/rebuild_b50b57/transport_revision_20261105'
OUTPUT=ROOT/'Saved/MPR/cleanup_20261105/transport/native_validation'
POS_TOL=.002;COLOR_TOL=.00002

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))
def verify(obj,row):
    mesh=obj.data;mesh.calc_loop_triangles()
    vertices=[tuple(obj.matrix_world@v.co)for v in mesh.vertices]
    assert vertices and all(math.isfinite(x)for p in vertices for x in p)
    assert len(mesh.loop_triangles)==row['triangles']
    error=max(abs(a-b)for i in range(3)for a,b in zip((min(p[i]for p in vertices),max(p[i]for p in vertices)),row['bounds_m'][i]))
    assert error<.02,(row['name'],'Bounds or axes changed',error)
    roles=[s.material.name if s.material else None for s in obj.material_slots]
    roles=[r.rsplit('.',1)[0]if r and r.rsplit('.',1)[-1].isdigit()else r for r in roles]
    assert roles==row['material_roles'],(row['name'],roles,row['material_roles'])
    assert mesh.uv_layers and all(len(layer.data)==len(mesh.loops)and all(math.isfinite(x)for p in layer.data for x in p.uv)for layer in mesh.uv_layers)
    assert all(0<=f.material_index<len(roles)for f in mesh.polygons)
    color=mesh.color_attributes.get('EdgeFade')
    if row.get('vertex_color_fade'):assert color and color.domain in {'POINT','CORNER'}
    samples=[]
    for i,loop in enumerate(mesh.loops):
        rgba=tuple(color.data[loop.vertex_index if color.domain=='POINT'else i].color)if color else (0.,0.,0.,1.)
        assert all(math.isfinite(x)and -COLOR_TOL<=x<=1+COLOR_TOL for x in rgba)
        if color:assert max(abs(rgba[i]-rgba[0])for i in (1,2))<COLOR_TOL and abs(rgba[3]-1)<COLOR_TOL
        samples.append((*vertices[loop.vertex_index],*rgba))
    return dict(name=row['name'],triangles=len(mesh.loop_triangles),bounds_error_m=error,uv_layers=len(mesh.uv_layers),material_roles=roles),samples
def compare(source,actual):
    assert len(source)==len(actual),'FBX corner count differs'
    expected=Counter(source);current=Counter(actual);buckets=defaultdict(list)
    for key in expected:buckets[tuple(math.floor(v/POS_TOL)for v in key[:3])].append(key)
    worst_position=worst_color=0.
    for point,count in sorted(current.items(),key=lambda kv:kv[0]):
        cell=tuple(math.floor(v/POS_TOL)for v in point[:3]);candidates=[]
        for delta in product((-1,0,1),repeat=3):
            for key in buckets.get(tuple(cell[i]+delta[i]for i in range(3)),[]):
                if not expected[key]:continue
                pe=max(abs(key[i]-point[i])for i in range(3));ce=max(abs(key[i]-point[i])for i in range(3,7))
                if pe<=POS_TOL and ce<=COLOR_TOL:candidates.append((pe+ce,key,pe,ce))
        for _,key,pe,ce in sorted(candidates):
            used=min(count,expected[key]);count-=used;expected[key]-=used
            if used:worst_position=max(worst_position,pe);worst_color=max(worst_color,ce)
            if not count:break
        assert not count,('FBX coordinate/colour multiset mismatch',point,count)
    assert not any(expected.values())
    return dict(multiset_equal=True,corner_samples=len(source),maximum_position_error_m=worst_position,maximum_rgba_error=worst_color)
def run(args,report):
    manifest=read(SOURCE/'manifest.json');rows=manifest['meshes'];assert 0<=args.start<args.stop<=len(rows) and args.stop-args.start<=30
    blend=(ROOT/manifest['blend']).resolve();assert blend.is_relative_to(SOURCE.resolve())
    hashes={'manifest_sha256':sha(SOURCE/'manifest.json'),'blend_sha256':sha(blend)}
    report.update(**hashes,batch={'start':args.start,'stop':args.stop,'total_meshes':len(rows)})
    for name,value in manifest['source_hashes'].items():assert sha(SOURCE.parent/name)==value
    bpy.ops.wm.open_mainfile(filepath=str(blend),load_ui=False,use_scripts=False)
    assert {o.name for o in bpy.context.scene.objects if o.type=='MESH'}=={r['name']for r in rows}
    sources={}
    for row in rows[args.start:args.stop]:
        record,samples=verify(bpy.data.objects[row['name']],row);sources[row['name']]=samples;report['meshes'].append(record)
    for image in bpy.data.images:
        if image.source=='FILE'and image.filepath:
            assert image.filepath.startswith('//')and Path(bpy.path.abspath(image.filepath)).is_file()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for row,record in zip(rows[args.start:args.stop],report['meshes']):
        fbx=(ROOT/row['fbx']).resolve();assert fbx.is_relative_to(SOURCE.resolve())and sha(fbx)==row['sha256']
        report['active_mesh']=row['name']
        bpy.ops.import_scene.fbx(filepath=str(fbx),use_custom_normals=True,colors_type='LINEAR')
        objects=[o for o in bpy.context.selected_objects if o.type=='MESH'];assert len(objects)==1
        fbx_record,samples=verify(objects[0],row);record['fbx']=fbx_record
        record['coordinate_color_roundtrip']=compare(sources.pop(row['name']),samples)
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        for collection in (bpy.data.meshes,bpy.data.materials,bpy.data.images):
            for block in list(collection):
                if block.users==0:collection.remove(block)
    assert sha(SOURCE/'manifest.json')==hashes['manifest_sha256']and sha(blend)==hashes['blend_sha256']
    for name,value in manifest['source_hashes'].items():assert sha(SOURCE.parent/name)==value
    report.pop('active_mesh',None);report.update(success=True,fbx_roundtrip_meshes=len(report['meshes']),triangles=sum(r['triangles']for r in rows[args.start:args.stop]),assets_saved=False)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--start',type=int,required=True);parser.add_argument('--stop',type=int,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);assert args.report.resolve().is_relative_to(OUTPUT.resolve())
    report={'success':False,'meshes':[]}
    try:run(args,report)
    except Exception:report['error']=traceback.format_exc()
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('MPR_TRANSPORT_NATIVE_BATCH',report['success'],flush=True)
    if not report['success']:raise RuntimeError(report['error'])
if __name__=='__main__':main()
