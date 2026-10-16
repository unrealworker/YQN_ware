"""Read saved GHS LOD render geometry without changing or saving assets."""
import json
from pathlib import Path
import unreal

unreal.load_module('StaticMeshEditor')
unreal.load_module('ProceduralMeshComponent')
editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
result = dict(asset_mutations=False, meshes=[])
for name in ['SM_GHS_Shared_PalletCargo', 'SM_GHS_Shared_RackBay']:
    mesh = unreal.EditorAssetLibrary.load_asset('/Game/GHSDigitalTwin/Meshes/' + name)
    entry = dict(name=name, lods=[], materials=[])
    for slot in mesh.get_editor_property('static_materials'):
        material = slot.get_editor_property('material_interface')
        entry['materials'].append(dict(name=material.get_name(), blend_mode=str(material.get_editor_property('blend_mode')),
                                        dithered_lod_transition=bool(material.get_editor_property('dithered_lod_transition'))))
    for lod in range(editor.get_lod_count(mesh)):
        data = dict(index=lod, triangles=mesh.get_num_triangles(lod), sections=[])
        for section in range(mesh.get_num_sections(lod)):
            vertices, indices, normals, uvs, tangents = unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, lod, section)
            material_slot = editor.get_lod_material_slot(mesh, lod, section)
            top_triangles = []
            top_projected_area = 0.0
            if name.endswith('PalletCargo'):
                for offset in range(0, len(indices), 3):
                    a, b, c = [vertices[indices[offset + i]] for i in range(3)]
                    nx = (b.y-a.y)*(c.z-a.z)-(b.z-a.z)*(c.y-a.y)
                    ny = (b.z-a.z)*(c.x-a.x)-(b.x-a.x)*(c.z-a.z)
                    nz = (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)
                    length = (nx*nx+ny*ny+nz*nz)**.5
                    normal_z = sum(normals[indices[offset+i]].z for i in range(3)) / 3
                    if length > 0 and normal_z > .5 and min(a.z,b.z,c.z) > 90:
                        top_projected_area += abs(nz)*.5
                        top_triangles.append([[float(v.x),float(v.y),float(v.z)] for v in [a,b,c]])
            data['sections'].append(dict(index=section, material_slot=material_slot,
                                         material=mesh.get_material(material_slot).get_name(),
                                         z_range_cm=[min(v.z for v in vertices),max(v.z for v in vertices)] if vertices else None,
                                         triangles=len(indices)//3, top_projected_area_cm2=top_projected_area,
                                         top_triangles=top_triangles))
        entry['lods'].append(data)
    result['meshes'].append(entry)
Path(r'D:\UEPro\Test\Saved\GHS_LODDiagnostic.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
unreal.log('GHS_LOD_DIAGNOSTIC_DONE')
