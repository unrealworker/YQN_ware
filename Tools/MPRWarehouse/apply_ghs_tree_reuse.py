"""Reuse the GHS tree in the existing MPR level; preserve every planting transform.

Owned UE commandlet modes: -TreeAudit, -TreeApply, -TreeVerify.
No original mesh, material, or GHS map is edited.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch
from apply_conveyor_connection_20261113 import signatures

MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
GHS='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
OLD='/Game/MPRWarehouse/SiteComplete/Meshes/SM_MPRSC_Tree_Canopy'
DEST='/Game/MPRWarehouse/GHSTreeReuse'
NAME='SM_MPR_GHS_Tree'
NEW=DEST+'/'+NAME
OUT=ROOT/'Saved/MPR/ghs_tree_reuse'
SRC=ROOT/'SourceAssets/MPR/ghs_tree_reuse'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,data):patch.write(OUT/name,data)

def tree_components(u):
    return [(a,c) for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
            for c in a.get_components_by_class(u.StaticMeshComponent)
            if c.static_mesh and c.static_mesh.get_path_name().split('.')[0] in (OLD,NEW)]

def audit(u):
    assert u.EditorLoadingAndSavingUtils.load_map(GHS)
    trees=[]
    for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors():
        for c in a.get_components_by_class(u.StaticMeshComponent):
            if c.static_mesh and any(t in c.static_mesh.get_name().lower() for t in ('tree','trunk')):
                trees.append(dict(actor=a.get_actor_label(),mesh=c.static_mesh.get_path_name(),
                    materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())]))
    assert trees,'No GHS trees found'
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    before=guard.capture(u,ROOT,MAP);guard.assert_clean(before)
    groups=[]
    for a,c in tree_components(u):
        assert isinstance(c,u.HierarchicalInstancedStaticMeshComponent)
        groups.append(dict(actor=a.get_actor_label(),component=c.get_name(),instances=c.get_instance_count(),
            materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())],
            custom_floats=c.get_editor_property('num_custom_data_floats')))
    assert groups
    write('before.json.gz',before)
    write('audit.json',dict(success=True,ghs_trees=trees,mpr_groups=groups,
        instances=sum(g['instances'] for g in groups),groups=len(groups),map_sha256=before['map_file_sha256']))

def import_tree(u):
    assert not u.EditorAssetLibrary.does_asset_exist(NEW),'Already imported: inspect before retry'
    task=u.AssetImportTask();task.filename=str(SRC/(NAME+'.fbx'))
    task.destination_path=DEST;task.destination_name=NAME;task.automated=True;task.save=False
    opts=u.FbxImportUI();opts.import_mesh=True;opts.import_as_skeletal=False
    opts.import_materials=False;opts.import_textures=False;opts.import_animations=False
    opts.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH;opts.automated_import_should_detect_type=False
    data=opts.static_mesh_import_data;data.combine_meshes=True;data.auto_generate_collision=False
    data.build_nanite=True
    data.generate_lightmap_u_vs=False;data.convert_scene=True;data.convert_scene_unit=True
    data.force_front_x_axis=False;data.vertex_color_import_option=u.VertexColorImportOption.IGNORE
    data.normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    task.options=opts;task.factory=u.FbxFactory()
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh=u.load_asset(NEW);assert mesh
    slots=[str(s.get_editor_property('imported_material_slot_name')) for s in mesh.static_materials]
    # The FBX importer removes unused slots; both used sections must retain
    # their order before restoring the four-slot MPR binding below.
    assert slots in (['Trunk','LeafMid'],['Trunk','LeafMid','LeafLight','LeafShade']),slots
    # Explicitly order existing MPR materials by role; unused leaf slots are
    # retained so existing component overrides and custom tint masks survive.
    original=u.load_asset(OLD)
    mesh.set_editor_property('static_materials',original.get_editor_property('static_materials'))
    bounds=mesh.get_bounds()
    manifest=patch.read(SRC/'manifest.json')
    assert sha(SRC/(NAME+'.fbx'))==manifest['fbx_sha256']
    actual_min=[bounds.origin.x-bounds.box_extent.x,bounds.origin.y-bounds.box_extent.y,bounds.origin.z-bounds.box_extent.z]
    actual_max=[bounds.origin.x+bounds.box_extent.x,bounds.origin.y+bounds.box_extent.y,bounds.origin.z+bounds.box_extent.z]
    assert max(abs(a-b) for a,b in zip(actual_min+actual_max,manifest['bounds_ue_cm']['min']+manifest['bounds_ue_cm']['max']))<.1
    assert abs(bounds.origin.z-bounds.box_extent.z)<.1,'Tree roots must remain at ground origin'
    assert 1100<bounds.box_extent.z*2<1650,'Unexpected tree height/FBX units'
    assert mesh.get_editor_property('nanite_settings').enabled
    return mesh

def apply(u):
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    before=guard.capture(u,ROOT,MAP);guard.assert_clean(before)
    expected=patch.read(OUT/'before.json.gz')
    assert signatures(before)==signatures(expected) and before['map_file_sha256']==expected['map_file_sha256'],'Map changed since audit'
    hashes=guard.content_hashes(ROOT)
    groups=tree_components(u);assert groups
    mesh=import_tree(u)
    for a,c in groups:
        mats=[c.get_material(i) for i in range(c.get_num_materials())]
        assert c.set_static_mesh(mesh)
        for i,m in enumerate(mats):c.set_material(i,m)
    after=guard.capture(u,ROOT,MAP)
    wanted=copy.deepcopy(before)
    changed=[]
    for a in wanted['actors']:
        for c in a['components']:
            if str(c.get('mesh','')).split('.')[0]==OLD:
                c['mesh']=NEW+'.'+NAME;changed.append(a['guid'])
    assert signatures(wanted)==signatures(after),'Unexpected change to actors, planting, materials or custom data'
    assert before['world_settings']==after['world_settings']
    assert u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    after=guard.capture(u,ROOT,MAP)
    existing_changes=[p for p,h in hashes.items() if guard.sha(ROOT/p)!=h]
    assert existing_changes==['Content/Maps/MPR_CAD_Warehouse_B50B57.umap'],existing_changes
    write('contract.json',dict(actors=signatures(after),world_settings=after['world_settings'],map_sha256=after['map_file_sha256']))
    write('apply.json',dict(success=True,groups=len(groups),instances=sum(c.get_instance_count() for a,c in groups),
        untouched_actors=len(before['actors'])-len(set(changed)),mesh=NEW,existing_changes=existing_changes,
        planting_materials_custom_data_preserved=True,map_sha256=after['map_file_sha256']))

def verify(u):
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    state=guard.capture(u,ROOT,MAP);contract=patch.read(OUT/'contract.json')
    assert signatures(state)==contract['actors']
    assert state['world_settings']==contract['world_settings']
    assert state['map_file_sha256']==contract['map_sha256']
    assert all(c.static_mesh.get_path_name().split('.')[0]==NEW for a,c in tree_components(u))
    write('verify.json',dict(success=True,actors_checked=len(state['actors']),map_sha256=state['map_file_sha256']))

if __name__=='__main__':
    import unreal as u
    cmd=u.SystemLibrary.get_command_line().lower();assert '-own' in cmd
    if '-treeaudit' in cmd:audit(u)
    elif '-treeapply' in cmd:apply(u)
    elif '-treeverify' in cmd:verify(u)
    else:raise RuntimeError('Select audit, apply or verify')
