"""Stage both scenes' shared geometry using CAD dimensions, never stretched loads."""
import collections,copy,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SOURCE=ROOT/'SourceAssets/GHS/RackSpecs'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key(r):return '%s:%d:%.4f'%(r['spec_type'],bool(r['pass_variant']),r['physical_span_m'])

def run():
    checkpoint=read(ROOT/'Saved/GHS_CADRackCheckpoint.json')
    original=Path(checkpoint['files']['SourceAssets/GHS/ue_scene_registry.json']['backup'])
    old=read(original);out=copy.deepcopy(old)
    mapping=read(SOURCE/'cad_plan_mapping.json');models=read(SOURCE/'Models/cad_rack_models.json')
    model_by={m['mapping_key']:m for m in models['meshes']}
    assert len(model_by)==len(models['meshes'])
    mapped=mapping['assignments']+mapping['additional_pass_racks'];groups={};old_groups={g['actor']:g for g in old['groups']}
    for row in mapped:
        model=model_by[key(row)];label='GHS_CAD_Rack_'+model['name'].removeprefix('SM_GHS_CADRack_')
        if label not in groups:groups[label]=dict(actor=label,mesh=model['name'],count=0,material_override=None,instances=[])
        instance=dict(id=row['instance_id'],parent_cad_id=row['parent_cad_id'],source_handles=row['source_handles'],
            position_m=[*row['position_m'],0.0],rotation_deg=row['rotation_deg']+90,scale=[1.,1.,1.],
            rack_spec_type=row['spec_type'],rack_pass_variant=bool(row['pass_variant']),mapping_key=key(row),
            physical_cad_center_m=row['position_m'],physical_cad_size_m=[row['physical_depth_m'],row['physical_span_m']],
            physical_cad_rotation_deg=row['rotation_deg'],frame_width_m=model['frame_width_m'],
            frame_depth_m=model['frame_depth_m'],upright_height_m=model['upright_height_m'],
            source_row_code=row.get('row_code'),source_bay_sequence=row.get('bay_sequence'),
            clearance_adjustment=row.get('clearance_adjustment',row.get('geometry_policy','')))
        groups[label]['instances'].append(instance);groups[label]['count']+=1
    doors=dict(actor='GHS_CAD_DockDoors',mesh='SM_GHS_CADDockDoor',count=87,material_override=None,instances=[])
    for d in mapping['loading_doors']:
        doors['instances'].append(dict(id=d['instance_id'],source_handles=[d['instance_id'].removeprefix('CAD_')],
            position_m=[*d['physical_center_m'],0],rotation_deg=d['rotation_deg'],scale=[1.,1.,1.],
            classification='loading_dock_door',dock_number=d['attributes']['DOCK_NO.'],height_basis='4.2m visualization estimate'))
    groups[doors['actor']]=doors
    new=[]
    for g in out['groups']:
        if g['actor']=='GHS_CAD_Racks':new.extend(groups[k] for k in sorted(groups) if k!='GHS_CAD_DockDoors')
        elif g['actor']=='GHS_CAD_DockRacks':new.append(doors)
        else:new.append(g)
    out['groups']=new;by={g['actor']:g for g in new};height=9.6
    profile=copy.deepcopy(old['wall_height_profile']);profile.update(version=2,wall_height_m=height,column_height_m=height,
        height_basis='9.6m display envelope selected to clear CAD rack tops 9.144/9.154m; no surveyed building elevation supplied',
        policy='Preserve measured XY and wall thickness; synchronized walls, columns and outlines; equipment and ground-door lines retain scale')
    out['wall_height_profile']=profile
    for label in profile['wall_groups']:
        r=by[label]['instances'][0];edge=label.endswith('Edges')
        r.update(position_m=[0,0,height-profile['source_wall_height_m'] if edge else 0],scale=[1,1,1 if edge else height/profile['source_wall_height_m']])
    for r in by['GHS_CAD_Columns']['instances']:
        bottom=r['position_m'][2]-r['scale'][2]/2;r['position_m'][2]=bottom+height/2;r['scale'][2]=height;r['presentation_height_m']=height
    outlines=[];edge=.012
    for col in by['GHS_CAD_Columns']['instances']:
        w,d,h=col['scale'];x,y,z=col['position_m'];ang=col['rotation_deg'];t=math.radians(ang);parts=[]
        for level,sign in [('Bottom',-1),('Top',1)]:
            cz=sign*(h-edge)/2
            for side in [-1,1]:parts.extend([(level+'_X_'+str(side),(0,side*(d-edge)/2,cz),(w,edge,edge)),(level+'_Y_'+str(side),(side*(w-edge)/2,0,cz),(edge,d-2*edge,edge))])
        for sx in [-1,1]:
            for sy in [-1,1]:parts.append(('Vertical_'+str(sx)+'_'+str(sy),(sx*(w-edge)/2,sy*(d-edge)/2,0),(edge,edge,h-2*edge)))
        for name,(ox,oy,oz),scale in parts:
            outlines.append(dict(id=col['id']+'_Outline_'+name,parent_column_id=col['id'],edge_name=name,
                position_m=[x+ox*math.cos(t)-oy*math.sin(t),y+ox*math.sin(t)+oy*math.cos(t),z+oz],rotation_deg=ang,scale=list(scale),source_handles=col['source_handles']))
    by['GHS_ColumnEdgeOutlines']['instances']=outlines;assert len(outlines)==2040
    changed=set(groups)|set(profile['wall_groups'])|{'GHS_CAD_Columns','GHS_ColumnEdgeOutlines'}
    removed={'GHS_CAD_Racks','GHS_CAD_DockRacks'}
    for g in new:
        if g['actor'] not in changed:assert g==old_groups[g['actor']],g['actor']
    assert out['individuals']==old['individuals']
    assert len(mapped)==1639 and len({r['instance_id'] for r in mapped})==1639
    assert {r['instance_id'] for r in mapping['assignments']}=={r['id'] for r in old_groups['GHS_CAD_Racks']['instances']}
    revision=dict(schema_version=1,specs_sha256=sha(SOURCE/'cad_elevation_specs.json'),mapping_sha256=sha(SOURCE/'cad_plan_mapping.json'),
        models_sha256=sha(SOURCE/'Models/cad_rack_models.json'),changed_groups=sorted(changed),retired_groups=sorted(removed),
        rack_instance_count=1639,loading_door_count=87,added_pass_racks=22,building_display_height_m=height,
        unused_catalogue_specs=mapping['unused_specs'],type_counts=dict(collections.Counter(r['spec_type']+('_PASS' if r['pass_variant'] else '') for r in mapped)),
        palette_policy='Shared geometry with independent existing materials; no world-Z shelf stripe shader on new racks',
        assumptions=[profile['height_basis'],'Dock door height 4.2m is a display estimate; XY comes from the CAD door geometry.','Previously approved column trims and 20mm shared-frame separation are retained; partial bays have fixed-size posts and loads.'])
    out['cad_rack_revision']=revision
    out['presentation'].update(wall_height_m=height,column_height_m=height,
        rack_height_m=None,rack_height_by_type_m={k:v['upright_height_m'] for k,v in read(SOURCE/'cad_elevation_specs.json')['types'].items()},
        assumptions=revision['assumptions'],modified_labels=sorted(set(out['presentation']['modified_labels'])|changed))
    out['presentation']['expected_hism_group_count']=len(new)
    out['presentation']['expected_instance_count']=sum(g['count'] for g in new)
    out['presentation']['expected_actor_count']=227-len(removed)+len(groups)
    write(SOURCE/'revised_registry.json',out);write(SOURCE/'revised_wall_height_profile.json',profile)
    print(json.dumps(dict(groups=len(new),instances=sum(g['count'] for g in new),racks=len(mapped),types=revision['type_counts'])))

if __name__=='__main__':run()
