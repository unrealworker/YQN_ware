"""Snapshot Blender mesh/UV/placement invariants and audit V4 surface spectra.

Blender: --python this.py -- --snapshot Saved/MPR/before.json
Python: this.py --check Saved/MPR/before.json Saved/MPR/after.json
The snapshot reads the source library and never saves any Blender/UE asset.
"""
from pathlib import Path
import argparse,hashlib,json,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];SITE=ROOT/'SourceAssets/MPR/reference_v4/site'

def digest(value):return hashlib.sha256(value).hexdigest()
def read_png(path):
 data=path.read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n';offset=8;compressed=b''
 while offset<len(data):
  length=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8];body=data[offset+8:offset+8+length]
  if kind==b'IHDR':w,h,depth,color,_,_,_=struct.unpack('>IIBBBBB',body);assert depth==8 and color==2
  if kind==b'IDAT':compressed+=body
  offset+=length+12
 raw=np.frombuffer(zlib.decompress(compressed),dtype=np.uint8).reshape(h,w*3+1);assert np.all(raw[:,0]==0)
 return raw[:,1:].reshape(h,w,3).astype(float)

def spectrum(a,frequencies):
 p=np.abs(np.fft.fft2(a-a.mean()))**2;total=float(p.sum())
 coherent=sum(float(p[y%a.shape[0],x%a.shape[1]]) for x,y in frequencies)
 return dict(variance=float(a.var()),old_wave_power_fraction=coherent/total if total else 0.,
             strongest_frequency_fraction=float(p.max())/total if total else 0.)

def texture_stats():
 out={}
 for kind,freq in [('grass',[(9,11),(9,-11),(-9,11),(-9,-11)]),('water',[(3,11),(-3,-11),(7,-4),(-7,4)])]:
  a=read_png(SITE/f'textures/T_MPR3_{kind}_albedo.png')[:,:,0]
  mip=a.reshape(64,16,64,16).mean(axis=(1,3))
  normal=read_png(SITE/f'textures/T_MPR3_{kind}_normal.png')
  out[kind]=dict(mean=float(a.mean()),minimum=float(a.min()),maximum=float(a.max()),full=spectrum(a,freq),mip64=spectrum(mip,freq),
                 normal_x=spectrum(normal[:,:,0],freq),normal_y=spectrum(normal[:,:,1],freq))
 return out

def snapshot(path):
 import bpy
 bpy.ops.wm.open_mainfile(filepath=str(SITE/'MPR_ReferenceSite.blend'));rows={}
 for ob in bpy.data.objects:
  if ob.type!='MESH':continue
  mesh=ob.data;parts=[]
  for collection,prop,size,dt in [(mesh.vertices,'co',3,np.float32),(mesh.loops,'vertex_index',1,np.int32),(mesh.polygons,'loop_start',1,np.int32),(mesh.polygons,'loop_total',1,np.int32),(mesh.polygons,'material_index',1,np.int32)]:
   values=np.empty(len(collection)*size,dtype=dt);collection.foreach_get(prop,values);parts.append(values.tobytes())
  uvs=[]
  for layer in mesh.uv_layers:
   values=np.empty(len(layer.data)*2,dtype=np.float32);layer.data.foreach_get('uv',values);uvs.append(digest(values.tobytes()))
  rows[ob.name]=dict(geometry_digest=digest(b''.join(parts)),uv_digests=uvs,material_roles=[m.name for m in mesh.materials],
                     matrix=[list(row) for row in ob.matrix_world])
 materials={m.name:dict(normal_strength=[float(n.inputs['Strength'].default_value) for n in m.node_tree.nodes if n.type=='NORMAL_MAP']) for m in bpy.data.materials if m.use_nodes}
 manifest=json.loads((SITE/'manifest.json').read_text(encoding='utf8'))
 answer=dict(meshes=rows,materials=materials,manifest=manifest,textures={p.name:digest(p.read_bytes()) for p in (SITE/'textures').glob('*.png')},spectra=texture_stats())
 (ROOT/path).write_text(json.dumps(answer,indent=2),encoding='utf8');print('SURFACE_SNAPSHOT',len(rows),path)

def check(before,after):
 old=json.loads((ROOT/before).read_text());new=json.loads((ROOT/after).read_text());assert old['meshes']==new['meshes'],'Geometry, UV, material assignment or transform changed'
 for key in ('instances','planting','reference_layout','calibration','trailer_layout_audit'):assert old['manifest'][key]==new['manifest'][key],key
 changed={name for name,sha in old['textures'].items() if sha!=new['textures'][name]}
 assert changed=={f'T_MPR3_{kind}_{channel}.png' for kind in ('grass','water') for channel in ('albedo','normal')},changed
 for role,strength in [('MPR3_Grass',.06),('MPR3_GrassFar',.06),('MPR3_PondWater',.08)]:
  assert new['manifest']['materials'][role]['normal_strength']==strength
  assert all(abs(v-strength)<1e-6 for v in new['materials'][role]['normal_strength'])
 expected_materials=json.loads(json.dumps(old['manifest']['materials']))
 for role in ('MPR3_Grass','MPR3_GrassFar'):expected_materials[role]['normal_strength']=.06
 expected_materials['MPR3_PondWater'].update(normal_strength=.08,roughness=.42,metallic=0.)
 assert new['manifest']['materials']==expected_materials,'Unexpected material delta'
 for kind in ('grass','water'):
  stats=new['spectra'][kind]
  assert old['spectra'][kind]['mip64']['old_wave_power_fraction']>.7,'Baseline must reproduce periodic artifact'
  assert stats['mip64']['old_wave_power_fraction']<.01,(kind,stats)
  assert stats['normal_x']['old_wave_power_fraction']<.01 and stats['normal_y']['old_wave_power_fraction']<.01
 assert abs(new['spectra']['grass']['mean']-234)<.02
 assert new['spectra']['grass']['minimum']>=232 and new['spectra']['grass']['maximum']<=236
 assert new['spectra']['water']['minimum']==new['spectra']['water']['maximum']==245
 report=dict(success=True,geometry_uv_transforms_unchanged=True,mesh_count=len(new['meshes']),all_instances_and_tree_positions_unchanged=True,
             changed_textures=sorted(changed),spectra_before=old['spectra'],spectra_after=new['spectra'],
             baseline_sine_counterexample_detected=True,blender_manifest_normal_strengths_equal=True,
             material_delta_limited_to_grass_and_water=True,unchanged_mesh_geometry_uv_signatures=new['meshes'],
             final_manifest_sha256=digest((SITE/'manifest.json').read_bytes()),
             boundary='Offline texture spectra, saved Blender geometry/UVs and manifest invariants only; actual UE appearance remains to be verified')
 path=ROOT/'SourceAssets/MPR/reference_v4/validation/surface_texture_review.json';path.write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))

if __name__=='__main__':
 args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
 parser=argparse.ArgumentParser();parser.add_argument('--snapshot');parser.add_argument('--check',nargs=2);opts=parser.parse_args(args)
 if opts.snapshot:snapshot(Path(opts.snapshot))
 else:check(*map(Path,opts.check))
