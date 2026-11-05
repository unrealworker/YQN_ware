"""Export the validated local transport payload in background Blender only."""
import ast,gzip,hashlib,json,math
from pathlib import Path
from types import SimpleNamespace
import bpy
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/transport_cleanup_20261105'

def main():
    validation=json.loads((OUT/'geometry_validation.json').read_text(encoding='utf8'))
    assert validation['success'] and validation['payload_sha256']==hashlib.sha256((OUT/'geometry_payload.json.gz').read_bytes()).hexdigest()
    with gzip.open(OUT/'geometry_payload.json.gz','rt',encoding='utf8')as f:payload=json.load(f)
    audit=payload['audit'];assert audit['success'] and not payload['instances']
    for name,expected in audit['source_hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    used={role for roles in payload['geometry'].values()for role in roles}
    source=ROOT/'Tools/MPRWarehouse/build_mpr_reference_site.py'
    function=next(n for n in ast.parse(source.read_text(encoding='utf8')).body if isinstance(n,ast.FunctionDef)and n.name=='export')
    namespace=dict(bpy=bpy,ROOT=ROOT,OUT=OUT,G=-1.2,GEO=SimpleNamespace(data=payload['geometry']),
        MATERIALS={role:payload['materials'][role]for role in used},INSTANCES={},COUNTS={},hashlib=hashlib,json=json)
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),namespace)
    frame=payload['frame'];assert frame['type']=='Polygon'
    edges=[(a,b)for ring in frame['coordinates']for a,b in zip(ring,ring[1:])]
    def fade(name,p):
        best=math.inf
        for a,b in edges:
            dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
            t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))if den else 0.
            best=min(best,math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy))
        v=max(0.,min(1.,1-best/24.));return v*v*(3-2*v)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    bpy.context.preferences.filepaths.save_version=0
    namespace['export'](payload['textures'],payload['metadata'],vertex_fade=fade,flatten_fade=False)
    target=OUT/'MPR_B50B57_TransportCleanup.blend'
    for image in bpy.data.images:
        if image.source=='FILE'and image.filepath:image.filepath=bpy.path.relpath(bpy.path.abspath(image.filepath),start=str(OUT))
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    (OUT/'MPR_ReferenceSite.blend').unlink()
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    for row in manifest['meshes']:row.update(category='Site',full_precision_uvs=True)
    manifest.update(blend=target.relative_to(ROOT).as_posix(),
        source_generated_triangles=sum(r['triangles']for r in manifest['meshes']),
        base_manifest='SourceAssets/MPR/rebuild_b50b57/manifest.json',
        previous_transport_manifest='SourceAssets/MPR/rebuild_b50b57/transport_revision_20261105/manifest.json',
        source_hashes=audit['source_hashes'],remove_mesh_names=audit['remove_mesh_names'],
        unchanged_transport_mesh_names=audit['unchanged_transport_mesh_names'],
        import_policy='Replace only listed Site transport assets in the existing MPR map; remove only listed transport actors; reuse current materials; retain warehouse, foliage, site-completion assets and all other actors.',
        outer_fade_geometry='Original 24m outer-boundary color fade, no Z flattening')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    audit.update(native_export_complete=True,native_export_triangles=manifest['source_generated_triangles'],native_export_meshes=len(manifest['meshes']),native_blend=manifest['blend'])
    (OUT/'geometry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    for name,expected in audit['source_hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    print('MPR_TRANSPORT_CLEANUP_EXPORTED',len(manifest['meshes']),manifest['source_generated_triangles'],flush=True)

if __name__=='__main__':main()
