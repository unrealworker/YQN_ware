"""Persistent UE 5.4 HISM groups for the GHS warehouse.

Pass world-space Unreal transforms in centimetres. No unit, axis or origin
conversion is performed. The caller owns level creation and saving. Importing
this module does not create assets; spawn_group lazily creates the template.
"""
import unreal

BLUEPRINT_PATH = '/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup'


def _templates(blueprint):
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = subsystem.k2_gather_subobject_data_for_blueprint(blueprint)
    result = []
    seen_objects = set()
    for handle in handles:
        data = library.get_data(handle)
        obj = library.get_object_for_blueprint(data, blueprint)
        # UE 5.4 appends a child SCS handle in the recursive call and again in
        # its parent loop. Count distinct component templates, not handles.
        if obj is not None:
            key = obj.get_path_name()
            if key in seen_objects:
                continue
            seen_objects.add(key)
        result.append((handle, data, obj))
    return subsystem, library, result


def ensure_hism_blueprint(path: str) -> unreal.Blueprint:
    """Load or create an Actor blueprint with exactly one persistent HISM node."""
    path = path.split('.')[0].rstrip('/')
    if not path.startswith('/Game/GHSDigitalTwin/'):
        raise ValueError('GHS instance blueprints must be inside /Game/GHSDigitalTwin')
    assets = unreal.EditorAssetLibrary
    existing = assets.load_asset(path) if assets.does_asset_exist(path) else None
    if existing is not None:
        if not isinstance(existing, unreal.Blueprint):
            raise TypeError('Existing asset is not a Blueprint: ' + path)
        _, _, objects = _templates(existing)
        hisms = [obj for _, _, obj in objects if isinstance(obj, unreal.HierarchicalInstancedStaticMeshComponent)]
        if len(hisms) != 1:
            raise ValueError('Existing GHS blueprint must contain exactly one HISM: ' + path)
        return existing

    folder, name = path.rsplit('/', 1)
    assets.make_directory(folder)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', unreal.Actor)
    blueprint = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Blueprint, factory)
    if not isinstance(blueprint, unreal.Blueprint):
        raise RuntimeError('Failed to create instance blueprint: ' + path)
    subsystem, library, objects = _templates(blueprint)
    actor_handles = [handle for handle, data, _ in objects if library.is_actor(data)]
    if not actor_handles:
        raise RuntimeError('Blueprint has no Actor subobject context')
    root_handles = [handle for handle, data, _ in objects if library.is_root_component(data)]
    for _, data, obj in objects:
        if library.is_root_component(data) and isinstance(obj, unreal.SceneComponent):
            obj.set_mobility(unreal.ComponentMobility.STATIC)
    params = unreal.AddNewSubobjectParams(
        parent_handle=root_handles[0] if root_handles else actor_handles[0],
        new_class=unreal.HierarchicalInstancedStaticMeshComponent,
        blueprint_context=blueprint,
    )
    handle, reason = subsystem.add_new_subobject(params)
    if not library.is_handle_valid(handle):
        raise RuntimeError('Failed to add HISM node: ' + str(reason))
    component = library.get_object_for_blueprint(library.get_data(handle), blueprint)
    if not isinstance(component, unreal.HierarchicalInstancedStaticMeshComponent):
        raise RuntimeError('Created subobject is not a HISM component')
    component.set_mobility(unreal.ComponentMobility.STATIC)
    component.set_collision_profile_name('NoCollision')
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    if not assets.save_loaded_asset(blueprint, only_if_is_dirty=False):
        raise RuntimeError('Failed to save instance blueprint: ' + path)
    return blueprint


def spawn_group(label: str, folder: str, mesh: unreal.StaticMesh,
                transforms: list[unreal.Transform]) -> unreal.Actor:
    """Spawn one group using world-space UE-cm transforms and batch add_instances.

    This creates a new actor every call and never removes or edits older groups.
    Set materials on its HISM component after this call when an override is
    needed; otherwise the mesh's saved material slots are used.
    """
    if not isinstance(mesh, unreal.StaticMesh):
        raise TypeError('mesh must be a loaded unreal.StaticMesh')
    if not transforms:
        raise ValueError('A HISM group requires at least one transform')
    if not all(isinstance(transform, unreal.Transform) for transform in transforms):
        raise TypeError('transforms must contain unreal.Transform values')
    blueprint = ensure_hism_blueprint(BLUEPRINT_PATH)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_class(blueprint.generated_class(), unreal.Vector(0, 0, 0),
                                         unreal.Rotator(pitch=0, yaw=0, roll=0))
    if actor is None:
        raise RuntimeError('Failed to spawn HISM group: ' + label)
    actor.set_actor_label(label)
    actor.set_folder_path(folder)
    component = actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    if component is None:
        raise RuntimeError('Spawned blueprint has no HISM component: ' + label)
    component.set_static_mesh(mesh)
    if component.get_editor_property('static_mesh') != mesh:
        raise RuntimeError('HISM mesh assignment failed: ' + label)
    component.set_collision_profile_name('NoCollision')
    indices = component.add_instances(transforms, should_return_indices=True,
                                     world_space=True, update_navigation=False)
    if component.get_instance_count() != len(transforms) or len(indices) != len(transforms):
        raise RuntimeError('HISM instance count mismatch: ' + label)
    actor.set_editor_property('tags', ['GHSDigitalTwin', 'HISMGroup', 'InstanceCount=' + str(len(transforms))])
    return actor
