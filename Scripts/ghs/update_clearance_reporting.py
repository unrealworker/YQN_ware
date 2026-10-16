from pathlib import Path
p=Path('Scripts/ghs/plan_clearance_fix.py');s=p.read_text();s=s.replace("shared_changes,unresolved_shared=trim_shared_end_frames", "original_before=collision_pairs({'columns_with_base_clearance':obstacles,'storage':physical['storage'],'racks':physical['racks'],'equipment':equipment})\n shared_changes,unresolved_shared=trim_shared_end_frames")
s=s.replace("before=collision_pairs({'columns_with_base_clearance':obstacles,'storage':physical['storage'],'racks':physical['racks'],'equipment':cad['equipment']})", "before=original_before")
s=s.replace("'after_collision_counts':counts(after)","'after_collision_counts':counts(after),'checked_pair_categories':['storage_storage','racks_racks','equipment_equipment','racks_storage','equipment_storage','equipment_racks','columns_with_base_clearance_storage','columns_with_base_clearance_racks','columns_with_base_clearance_equipment','columns_with_base_clearance_columns_with_base_clearance']")
p.write_text(s,encoding='utf8')
