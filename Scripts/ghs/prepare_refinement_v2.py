"""Stage the authorized coordinated changes without writing the live registries."""
from pathlib import Path
import json,copy,hashlib,collections
ROOT=Path(__file__).resolve().parents[2];SRC=ROOT/'SourceAssets/GHS/RefinementV2'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    checkpoint=read(ROOT/'Saved/GHS_RefinementV2Checkpoint.json')
    old=read(Path(checkpoint['files']['SourceAssets/GHS/ue_scene_registry.json']['backup']));out=copy.deepcopy(old)
    layout=read(SRC/'Layout/rack_spacing.json');models=read(SRC/'Racks/refined_rack_cargo.json')
    assert read(SRC/'Layout/rack_spacing_validation.json')['passed']
    model_by={m['mapping_key']:m for m in models['meshes']}
    groups={g['actor']:g for g in out['groups']};old_labels=set(groups)
    retired={n for n in groups if n.startswith('GHS_CAD_Rack_')}|{'GHS_ColumnOccupiedStorageOutlines'}
    out['groups']=[g for g in out['groups'] if g['actor'] not in retired]
    changed={'GHS_CAD_WallFaces','GHS_CAD_WallSections','GHS_CAD_WallEdges','GHS_CAD_DockDoors'}
    racks={}
    for row in layout['racks']:
        model=model_by[row['mapping_key']];label='GHS_V2_Rack_'+model['name'].removeprefix('SM_GHS_V2Rack_')
        if label not in racks:racks[label]=dict(actor=label,mesh=model['name'],count=0,material_override=None,instances=[])
        racks[label]['instances'].append(dict(id=row['instance_id'],parent_cad_id=row['parent_cad_id'],source_handles=row['source_handles'],
            position_m=[*row['position_m'],0],rotation_deg=row['rotation_deg']+90,scale=[1,1,1],
            rack_spec_type=row['spec_type'],rack_pass_variant=row['pass_variant'],mapping_key=row['mapping_key'],
            source_center_m=row['source_center_m'],spacing_displacement_m=row['spacing_displacement_m'],
            replaces_instance_ids=row['replaces_instance_ids'],restored_column_split=row['restored_column_split']))
    for g in racks.values():g['count']=len(g['instances'])
    out['groups'].extend(racks[k] for k in sorted(racks));changed.update(racks)
    for role in ['Faces','Sections','Edges']:
        g=groups['GHS_CAD_Wall'+role];g['mesh']='SM_GHS_V2Exterior'+role
        for row in g['instances']:row.update(position_m=[0,0,0],scale=[1,1,1])
    groups['GHS_CAD_DockDoors']['mesh']='SM_GHS_V2DockDoor'
    for row in groups['GHS_CAD_DockDoors']['instances']:row['open_fraction']=.5
    # Keep each floor load's original dimensions and palette, moving its anchor only.
    floor_groups={g['actor']:g for g in out['groups'] if g['actor'].startswith('GHS_CAD_PalletCargo')}
    prior={i['id']:(g['actor'],i) for g in floor_groups.values() for i in g['instances']}
    templates={v:next(i for g in floor_groups.values() for i in g['instances'] if i['presentation_variant']==v) for v in ['Low','Mid','High']}
    for g in floor_groups.values():g['instances']=[]
    for item in layout['groundcargo']:
        if item['id'] in prior:
            label,row=prior[item['id']];row=copy.deepcopy(row)
            position=[row['position_m'][i]+item['displacement_m'][i] for i in range(2)]
        else:
            variant=item['presentation_variant'];row=copy.deepcopy(templates[variant])
            label='GHS_CAD_PalletCargo'+('' if variant=='Mid' else variant)
            assert all(abs(a-b)<1e-5 for a,b in zip(row['physical_cad_size_m'],item['size_m'])),'Restored load must retain full size'
            position=[item['position_m'][i]+row['position_m'][i]-row['physical_cad_center_m'][i] for i in range(2)]
            row.update(id=item['id'],source_handles=item['source_handles'],physical_cad_rotation_deg=item['rotation_deg'],rotation_deg=item['rotation_deg'],presentation_block_id=item['presentation_block_id'])
        row['position_m']=[*position,row['position_m'][2]]
        row['physical_cad_center_m']=item['original_position_m'];row['v2_spacing_displacement_m']=item['displacement_m'];row['v2_restored']=item['was_blocked']
        floor_groups[label]['instances'].append(row)
    for g in floor_groups.values():g['count']=len(g['instances']);changed.add(g['actor'])
    out['historical_blocked_storage_before_v2']=out.get('blocked_storage',[])
    out['blocked_storage']=[]
    block_slots=collections.defaultdict(list)
    for item in layout['groundcargo']:block_slots[item['presentation_block_id']].append(item['id'])
    zone_counts=collections.defaultdict(collections.Counter)
    for block in out['presentation']['cargo_blocks']:
        block['slot_ids']=block_slots[block['id']]
        assert len(block['slot_ids'])==block['all_cad_slot_count']
        zone_counts[block['zone']][block['variant']]+=len(block['slot_ids'])
    out['presentation']['zone_variant_statistics']=[dict(zone=z,active_slots=sum(c.values()),variant_counts=dict(c)) for z,c in sorted(zone_counts.items())]
    doors=read(SRC/'Envelope/door_docking_targets.json')['doors'];truck=read(SRC/'Trucks/dock_truck_v2.json')['meshes'][0]
    vehicles=dict(actor='GHS_V2_WaitingDockTrucks',mesh=truck['name'],count=len(doors),material_override=None,instances=[])
    for door in doors:
        vehicles['instances'].append(dict(id='DockTruck_'+door['dock_number'],dock_number=door['dock_number'],door_id=door['instance_id'],
            position_m=[*door['truck_rear_dock_target_cad_m'][:2],-truck['bounds_m'][2][0]],rotation_deg=door['truck_forward_cad_yaw_deg'],scale=[1,1,1]))
    out['groups'].append(vehicles);changed.add(vehicles['actor'])
    profile=out['wall_height_profile'];profile.update(version=3,source_wall_height_m=9.6,wall_geometry_source='RefinementV2/Envelope',
        wall_height_m=9.6,column_height_m=9.6,policy='Complete CAD outer perimeter with continuous door headers, open top and half-open door apertures')
    counts={k:len([r for r in layout['racks'] if r['spec_type']+('_PASS' if r['pass_variant'] else '')==k]) for k in ['A','B','D1','A_PASS','B_PASS']}
    meta=dict(schema_version=2,source_sha256={p:sha(SRC/p) for p in ['Layout/rack_spacing.json','Layout/rack_spacing_validation.json','Racks/refined_rack_cargo.json','Envelope/envelope_v2.json','Trucks/dock_truck_v2.json']},
        changed_groups=sorted(changed),retired_groups=sorted(retired),rack_count=len(layout['racks']),cargo_count=len(layout['groundcargo']),truck_count=len(doors),door_count=len(doors),
        rack_types=counts,spacing_summary=layout['summary'],closed_exterior=True,roof=False,door_open_fraction=.5,
        scope='Both GHS palettes; authorized small rack and ground-storage spacing changes; existing AGVs and lights preserved')
    out['refinement_v2']=meta
    out['presentation'].update(expected_hism_group_count=len(out['groups']),expected_instance_count=sum(g['count'] for g in out['groups']),
        expected_actor_count=252-len(retired)+len(changed-old_labels),cargo_count=len(layout['groundcargo']))
    out['presentation']['modified_labels']=sorted(set(out['presentation']['modified_labels'])|changed|retired)
    (SRC/'revised_registry.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(groups=len(out['groups']),instances=out['presentation']['expected_instance_count'],racks=meta['rack_count'],cargo=meta['cargo_count'],trucks=len(doors))))
if __name__=='__main__':run()
