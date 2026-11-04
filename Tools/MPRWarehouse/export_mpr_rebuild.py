"""Export the prepared geometry in Blender without loading GEOS or NumPy.

Geometry construction runs in a separate Python process. This avoids mixing
external geometry allocators with Blender's native dependency graph updates.
"""
import ast,gzip,hashlib,json,math,sys
from pathlib import Path
from types import SimpleNamespace
import bpy
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/rebuild_b50b57'
CACHE=ROOT/'Saved/MPR/rebuild_20261104'
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_rebuild_style import apply_style

def main():
    with gzip.open(CACHE/'geometry_payload.json.gz','rt',encoding='utf8')as stream:payload=json.load(stream)
    for name,h in payload['input_hashes'].items():
        assert hashlib.sha256((OUT/'inputs'/name).read_bytes()).hexdigest()==h
    # Reuse the reviewed pure Blender exporter, without importing the unrelated
    # CAD generation modules and their native spatial libraries into Blender.
    source=ROOT/'Tools/MPRWarehouse/build_mpr_reference_site.py'
    parsed=ast.parse(source.read_text(encoding='utf8'))
    function=next(n for n in parsed.body if isinstance(n,ast.FunctionDef)and n.name=='export')
    namespace=dict(bpy=bpy,ROOT=ROOT,OUT=OUT,G=-1.2,GEO=SimpleNamespace(data=payload['geometry']),
        MATERIALS=payload['materials'],INSTANCES=payload['instances'],COUNTS=payload['counts'],hashlib=hashlib,json=json)
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
    target=OUT/'MPR_B50B57_Rebuild.blend'
    for image in bpy.data.images:
        if image.source=='FILE'and image.filepath:
            image.filepath=bpy.path.relpath(bpy.path.abspath(image.filepath),start=str(OUT))
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    (OUT/'MPR_ReferenceSite.blend').unlink()
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    for row in manifest['meshes']:
        row['category']='Context'if 'Context'in row['name']else'Site';row['full_precision_uvs']=True
    manifest.update(blend=target.relative_to(ROOT).as_posix(),input_hashes=payload['input_hashes'],
        source_generated_triangles=sum(r['triangles']for r in manifest['meshes']),
        outer_fade_geometry='Colour-only; shared pavement planes retain positive clearance')
    apply_style(manifest)
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    audit=payload['audit'];audit['geometry_triangles']=manifest['source_generated_triangles']
    (OUT/'geometry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    print('MPRR_EXPORT_COMPLETE',len(manifest['meshes']),manifest['source_generated_triangles'],flush=True)

if __name__=='__main__':main()
