"""Rebuild the GHS ground pallet groups from model-space CAD inserts."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Content/GHSTwinUI/data'
SOURCE = ROOT / 'SourceAssets/GHS/CAD24/racks.json'
GROUPS = {'Low':'GHS_CAD_PalletCargoLow', 'Mid':'GHS_CAD_PalletCargo', 'High':'GHS_CAD_PalletCargoHigh'}
PREFIX = 'SM_GHS_Presentation_Cargo'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, data):
    path.write_bytes(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf8'))


def prepare_ground():
    cad = read(SOURCE)
    scene = read(DATA / 'scene-bindings.json')
    capacity = read(DATA / 'storage-capacity.json')
    variants = defaultdict(list)
    for ground in cad['ground']:
        attrs = ground['attrs']
        # Retain the three existing presentation heights. CAD HEIGHT_IN is a limit.
        variant = ('Low','Mid','High','Mid')[int(attrs['SEQ']) % 4]
        x,y = ground['position_m'][:2]
        variants[variant].append(dict(id=ground['id'], position_m=[x,y,.012],
            rotation_deg=(ground['rotation_deg']+90)%360, scale=[float(attrs['WIDTH_IN'])*.0254/1.2,
            float(attrs['DEPTH_IN'])*.0254,1], zone_code=attrs['ZONE_CODE'], sequence=attrs['SEQ']))
    assert len({r['id'] for rows in variants.values() for r in rows}) == len(cad['ground'])
    scene['groups'] = [g for g in scene['groups'] if not g['mesh'].startswith(PREFIX)]
    capacity['groups'] = [g for g in capacity['groups'] if g['kind']!='floor']
    base = 0
    for variant,actor in GROUPS.items():
        mesh = PREFIX+variant
        instances = variants[variant]
        assert instances, variant
        scene['groups'].append(dict(actor=actor,mesh=mesh,count=len(instances),instances=instances))
        capacity['groups'].append(dict(actor=actor,mesh=mesh,source_mesh=mesh,kind='floor',
            count=len(instances),slots_per_instance=1,base_slot=base))
        base += len(instances)
    capacity['floor_total_slots'] = base
    capacity['floor_multiplier'] = 101 if base%97==0 else 97
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
    for group in scene['groups']:
        if group['actor'] not in GROUPS.values():
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


if __name__=='__main__':
    prepare_ground()
