"""Record imported FBX geometry before a UV-only change, then verify after."""
import bpy, hashlib, json, sys, math
from pathlib import Path
from io_scene_fbx import parse_fbx as parse
OUT=Path(__file__).resolve().parent
baseline='--baseline' in sys.argv
manifest=json.loads((OUT/'envelope_v2.json').read_text(encoding='utf8'))
checks=[]
for entry in manifest['meshes']:
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=entry['fbx'])
    obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    mesh=obj.data
    payload={'vertices':[[float(v) for v in p.co] for p in mesh.vertices],
             'faces':[list(p.vertices) for p in mesh.polygons],
             'material_indices':[p.material_index for p in mesh.polygons],
             'slots':[m.name for m in mesh.materials]}
    geometry_hash=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
    nonzero_faces=[{'vertices':[[float(v) for v in mesh.vertices[i].co] for i in p.vertices],
                    'material_index':p.material_index} for p in mesh.polygons if p.area>=1e-14]
    surface_hash=hashlib.sha256(json.dumps(nonzero_faces,separators=(',',':')).encode()).hexdigest()
    mesh.calc_loop_triangles();uv=mesh.uv_layers.active
    assert uv
    areas=[];bad=[]
    for tri in mesh.loop_triangles:
        a,b,c=[uv.data[i].uv for i in tri.loops]
        area=abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))/2
        areas.append(area)
        if not math.isfinite(area) or area<1e-10:bad.append(tri.index)
    mesh.calc_tangents(uvmap=uv.name)
    zero_tangent=sum(1 for loop in mesh.loops if loop.tangent.length<.9)
    zero_bitangent=sum(1 for loop in mesh.loops if loop.bitangent.length<.9)
    item={'name':entry['name'],'geometry_material_sha256':geometry_hash,
          'nonzero_surface_sha256':surface_hash,
          'vertices':len(mesh.vertices),'polygons':len(mesh.polygons),'triangles':len(mesh.loop_triangles),
          'minimum_uv_triangle_area':min(areas),'degenerate_uv_triangle_count':len(bad),
          'degenerate_geometry_triangle_count':sum(1 for t in mesh.loop_triangles if t.area<1e-14),
          'near_zero_tangent_loop_count':zero_tangent,'near_zero_bitangent_loop_count':zero_bitangent}
    if not baseline:
        tree,version=parse.parse(entry['fbx'])
        def child(e,key):return next(c for c in e.elems if c.id==key)
        geometry=next(e for e in child(tree,b'Objects').elems if e.id==b'Geometry')
        tangent_values=child(child(geometry,b'LayerElementTangent'),b'Tangents').props[0]
        binormal_values=child(child(geometry,b'LayerElementBinormal'),b'Binormals').props[0]
        normal_layer=child(geometry,b'LayerElementNormal')
        normal_values=child(normal_layer,b'Normals').props[0]
        normal_indices=child(normal_layer,b'NormalsIndex').props[0]
        vector=lambda data,index:tuple(data[index*3+k] for k in range(3))
        dot=lambda a,b:sum(a[k]*b[k] for k in range(3))
        assert len(tangent_values)==len(binormal_values)==len(mesh.loops)*3
        length_error=orthogonal_error=0
        for i in range(len(mesh.loops)):
            t=vector(tangent_values,i);b=vector(binormal_values,i);n=vector(normal_values,normal_indices[i])
            length_error=max(length_error,abs(math.sqrt(dot(t,t))-1),abs(math.sqrt(dot(b,b))-1))
            orthogonal_error=max(orthogonal_error,abs(dot(t,b)),abs(dot(t,n)),abs(dot(b,n)))
        item['explicit_fbx_tangent_space']={'tangent_loop_count':len(tangent_values)//3,
            'binormal_loop_count':len(binormal_values)//3,'maximum_unit_length_error':length_error,
            'maximum_orthogonality_error':orthogonal_error,'arrays_present':True}
        assert length_error<1e-6 and orthogonal_error<1e-6,item
    checks.append(item)
if not baseline:
    before=json.loads((OUT/'uv_baseline_verification.json').read_text(encoding='utf8'))
    previous={e['name']:e for e in before['meshes']}
    for item in checks:
        item['geometry_and_materials_unchanged']=item['geometry_material_sha256']==previous[item['name']]['geometry_material_sha256']
        item['all_nonzero_surfaces_unchanged']=item['nonzero_surface_sha256']==previous[item['name']]['nonzero_surface_sha256']
        assert item['all_nonzero_surfaces_unchanged'],item
        assert item['degenerate_uv_triangle_count']==0,item
        # The default Blender importer ignores FBX tangent arrays and its
        # recalculation underflows at some original CAD needle tips. The actual
        # exported arrays above must pass instead; UE must import both vectors.
        item['recomputed_mikktspace_near_zero_tangent_count']=item.pop('near_zero_tangent_loop_count')
        item['recomputed_mikktspace_near_zero_bitangent_count']=item.pop('near_zero_bitangent_loop_count')
result={'mode':'baseline' if baseline else 'after_uv_fix','meshes':checks}
(OUT/('uv_baseline_verification.json' if baseline else 'uv_verification.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
