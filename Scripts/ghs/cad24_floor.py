"""Rebuild the GHS ground pallet groups from model-space CAD inserts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Content/GHSTwinUI/data'
SOURCE = ROOT / 'SourceAssets/GHS/CAD24/racks.json'
PREFIX = 'SM_GHS_Presentation_Cargo'
MID_ACTOR = 'GHS_CAD_PalletCargo'
MID_MESH = PREFIX + 'Mid'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, data):
    path.write_bytes(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf8'))


def prepare_ground():
    cad = read(SOURCE)
    scene = read(DATA / 'scene-bindings.json')
    capacity = read(DATA / 'storage-capacity.json')
    instances = []
    for ground in cad['ground']:
        attrs = ground['attrs']
        x,y = ground['position_m'][:2]
        instances.append(dict(id=ground['id'], position_m=[x,y,.012],
            rotation_deg=(ground['rotation_deg']+90)%360, scale=[float(attrs['WIDTH_IN'])*.0254/1.2,
            float(attrs['DEPTH_IN'])*.0254,1], zone_code=attrs['ZONE_CODE'], sequence=attrs['SEQ']))
    assert len({r['id'] for r in instances}) == len(cad['ground']) > 0
    scene['groups'] = [g for g in scene['groups'] if not g['mesh'].startswith(PREFIX)]
    capacity['groups'] = [g for g in capacity['groups'] if g['kind']!='floor']
    count = len(instances)
    scene['groups'].append(dict(actor=MID_ACTOR,mesh=MID_MESH,count=count,instances=instances))
    capacity['groups'].append(dict(actor=MID_ACTOR,mesh=MID_MESH,source_mesh=MID_MESH,kind='floor',
        count=count,slots_per_instance=1,base_slot=0))
    capacity['floor_total_slots'] = count
    capacity['floor_multiplier'] = 101 if count%97==0 else 97
    write(DATA / 'scene-bindings.json', scene)
    write(DATA / 'storage-capacity.json', capacity)


def apply_ground():
    import unreal
    from apply_cad24_racks import make_capacity_materials
    from storage_capacity_import_validation import configure_capacity_component
    scene = read(DATA / 'scene-bindings.json')
    capacity = read(DATA / 'storage-capacity.json')
    materials = make_capacity_materials('floor',capacity['floor_total_slots'])
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    by_label = {a.get_actor_label():a for a in actors.get_all_level_actors()}
    retired = []
    for variant in ('Low', 'High'):
        label = MID_ACTOR + variant
        if label in by_label:
            component = by_label[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            assert component and component.static_mesh.get_name() == PREFIX + variant
            assert 'GHSStorageGroup:'+label in map(str, component.component_tags)
            retired.append(by_label[label])
    for group in scene['groups']:
        if group['actor'] != MID_ACTOR:
            continue
        actor = by_label[group['actor']]
        comp = actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert comp.static_mesh.get_name()==group['mesh']
        transforms = []
        for item in group['instances']:
            x,y,z = item['position_m']
            transforms.append(unreal.Transform(location=unreal.Vector(100*x,-100*y,100*z),
                rotation=unreal.Rotator(yaw=-item['rotation_deg']),scale=unreal.Vector(*item['scale'])))
        actor.modify()
        comp.modify()
        comp.clear_instances()
        comp.add_instances(transforms,False,True,False)
        targets = [materials[comp.get_material(i).get_path_name()] for i in range(comp.get_num_materials())]
        base = next(g['base_slot'] for g in capacity['groups'] if g['actor']==group['actor'])
        bases = list(map(float,range(base,base+len(transforms))))
        comp = configure_capacity_component(lambda:actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent),
            comp.static_mesh,targets,{},bases)
        for i,transform in enumerate(transforms):
            actual = comp.get_instance_transform(i,True)
            assert (actual.translation-transform.translation).length()<.1
        assert comp.get_instance_count()==group['count']
    assert MID_ACTOR in by_label and any(g['actor']==MID_ACTOR for g in scene['groups'])
    for actor in retired:
        assert actors.destroy_actor(actor)


if __name__=='__main__':
    prepare_ground()
