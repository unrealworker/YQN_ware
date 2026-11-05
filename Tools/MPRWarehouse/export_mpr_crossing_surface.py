"""Export the Crossing_04 inlay payload in a separate background Blender."""
import ast,gzip,hashlib,json,math
from pathlib import Path
from types import SimpleNamespace
import bpy
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/crossing_surface_20261105'

def main():
    validation=json.loads((OUT/'geometry_validation.json').read_text())
    assert validation['success']and validation['payload_sha256']==hashlib.sha256((OUT/'geometry_payload.json.gz').read_bytes()).hexdigest()
    with gzip.open(OUT/'geometry_payload.json.gz','rt',encoding='utf8')as f:payload=json.load(f)
    audit=payload['audit']
    for p,digest in audit['source_hashes'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest,p
    roles={r for groups in payload['geometry'].values()for r in groups}
    source=ROOT/'Tools/MPRWarehouse/build_mpr_reference_site.py'
    node=next(n for n in ast.parse(source.read_text(encoding='utf8')).body if isinstance(n,ast.FunctionDef)and n.name=='export')
    scope=dict(bpy=bpy,ROOT=ROOT,OUT=OUT,G=-1.2,GEO=SimpleNamespace(data=payload['geometry']),
        MATERIALS={r:payload['materials'][r]for r in roles},INSTANCES={},COUNTS={},hashlib=hashlib,json=json)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
    edges=[(a,b)for ring in payload['frame']['coordinates']for a,b in zip(ring,ring[1:])]
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
    scope['export'](payload['textures'],payload['metadata'],vertex_fade=fade,flatten_fade=False)
    target=OUT/'MPR_Crossing04_Surface.blend'
    for image in bpy.data.images:
        if image.source=='FILE'and image.filepath:image.filepath=bpy.path.relpath(bpy.path.abspath(image.filepath),start=str(OUT))
    bpy.ops.wm.save_as_mainfile(filepath=str(target));(OUT/'MPR_ReferenceSite.blend').unlink()
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    for row in manifest['meshes']:row.update(category='Site',full_precision_uvs=True)
    manifest.update(blend=target.relative_to(ROOT).as_posix(),mesh_mappings=audit['mesh_mappings'],scope=audit['scope'],
        source_hashes=audit['source_hashes'],remove_mesh_names=[],preserve_steel_rail_meshes=True,
        expected_guard_changes=dict(component_meshes=8,removed_actors=0,added_actors=0,component_material_slot_changes=4),
        source_generated_triangles=sum(r['triangles']for r in manifest['meshes']))
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('CROSSING_SURFACE_EXPORTED',len(manifest['meshes']),manifest['source_generated_triangles'],flush=True)

if __name__=='__main__':
    import sys
    if '--refine-ramp-normals' in sys.argv:
        sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
        from refine_mpr_crossing_normals import main as refine
        refine()
    else:main()
