"""Native Blender export of the reviewed standalone transport payload only.

Run in a fresh background Blender process. Does not load GEOS/NumPy or rebuild
the whole scene; original source FBXs, full scene manifest and blend are read-only.
"""
import ast,gzip,hashlib,json,math,sys
from pathlib import Path
from types import SimpleNamespace
import bpy

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/rebuild_b50b57'
CACHE=ROOT/'Saved/MPR/cleanup_20261105/transport'
OUT=SOURCE/'transport_revision_20261105'

def main():
    validation=json.loads((CACHE/'geometry_validation.json').read_text(encoding='utf8'))
    assert validation['success'] and validation['payload_sha256']==hashlib.sha256((CACHE/'geometry_payload.json.gz').read_bytes()).hexdigest()
    with gzip.open(CACHE/'geometry_payload.json.gz','rt',encoding='utf8')as f:payload=json.load(f)
    audit=payload['audit'];assert audit['success'] and not payload['instances']
    for name,expected in audit['source_hashes'].items():
        assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==expected,('Base source changed',name)
    assert set(payload['geometry'])==set(audit['mesh_names'])
    assert not any(name.endswith('_RailBed')for name in payload['geometry'])
    OUT.mkdir(parents=True,exist_ok=True)
    used={role for roles in payload['geometry'].values()for role in roles}
    materials={role:payload['materials'][role]for role in used}
    source=ROOT/'Tools/MPRWarehouse/build_mpr_reference_site.py'
    parsed=ast.parse(source.read_text(encoding='utf8'))
    function=next(n for n in parsed.body if isinstance(n,ast.FunctionDef)and n.name=='export')
    namespace=dict(bpy=bpy,ROOT=ROOT,OUT=OUT,G=-1.2,
        GEO=SimpleNamespace(data=payload['geometry']),MATERIALS=materials,
        INSTANCES={},COUNTS={},hashlib=hashlib,json=json)
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
    target=OUT/'MPR_B50B57_TransportRevision.blend'
    for image in bpy.data.images:
        if image.source=='FILE'and image.filepath:
            image.filepath=bpy.path.relpath(bpy.path.abspath(image.filepath),start=str(OUT))
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    (OUT/'MPR_ReferenceSite.blend').unlink()
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    for row in manifest['meshes']:
        row.update(category='Site',full_precision_uvs=True)
    manifest.update(blend=target.relative_to(ROOT).as_posix(),
        source_generated_triangles=sum(r['triangles']for r in manifest['meshes']),
        base_manifest=(SOURCE/'manifest.json').relative_to(ROOT).as_posix(),
        source_hashes=audit['source_hashes'],remove_mesh_names=audit['remove_mesh_names'],
        unchanged_transport_mesh_names=audit['unchanged_transport_mesh_names'],
        import_policy='Replace listed transport meshes only; remove listed live actors if present; reuse existing material assets; retain all other actors and instances.',
        outer_fade_geometry='Same original 24m outer-boundary colour fade; no geometric Z flattening')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (OUT/'layout.json').write_bytes((CACHE/'layout.json').read_bytes())
    (OUT/'geometry_validation.json').write_bytes((CACHE/'geometry_validation.json').read_bytes())
    audit.update(native_export_complete=True,native_export_triangles=manifest['source_generated_triangles'],
        native_export_meshes=len(manifest['meshes']),native_blend=manifest['blend'])
    (OUT/'geometry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    for name,expected in audit['source_hashes'].items():
        assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==expected,('Base source changed',name)
    print('MPR_TRANSPORT_EXPORT_COMPLETE',len(manifest['meshes']),manifest['source_generated_triangles'],flush=True)

if __name__=='__main__':main()
