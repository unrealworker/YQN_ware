"""Build an exact, source-checked delta for the existing MPR operation HISM groups."""
import argparse
import collections
import gzip
import hashlib
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(path):
    with (gzip.open(path, 'rt', encoding='utf-8') if str(path).endswith('.gz') else open(path, encoding='utf-8')) as stream:
        return json.load(stream)


def build(before, after, snapshot, mesh_manifest):
    old_rows, new_rows = before['instances'], after['instances']
    targets = []
    for actor in snapshot['actors']:
        for component in actor.get('components', []):
            for index, transform in enumerate(component.get('instance_transforms', [])):
                targets.append((actor, component, index, transform))

    def old_record(index):
        row = old_rows[index]
        point = [row['position_m'][0]*100, -row['position_m'][1]*100, row['position_m'][2]*100]
        matches = []
        for actor, component, instance_index, transform in targets:
            if str(component.get('mesh', '')).split('.')[-1] != row['mesh'].split('/')[-1]:
                continue
            if math.dist(point, transform['translation_cm']) > .001:
                continue
            if max(abs(a-b) for a,b in zip(row['scale'],transform['scale'])) > .00001:
                continue
            matches.append(dict(old_ops_index=index,source_handles=row['source_handles'],old_pose=row,
                                actor_guid=actor['guid'],actor_label=actor['label'],component_name=component['name'],
                                instance_index=instance_index,original_transform=transform))
        assert len(matches)==1,(index,row,matches)
        return matches[0]

    def exact(row):
        return json.dumps(row, sort_keys=True, separators=(',', ':'))

    new_exact = collections.Counter(exact(r) for r in new_rows)
    old_exact = collections.Counter(exact(r) for r in old_rows)
    unchanged = [r for r in old_rows if new_exact[exact(r)]]
    changed_old = [i for i,r in enumerate(old_rows) if not new_exact[exact(r)]]
    changed_new = [i for i,r in enumerate(new_rows) if not old_exact[exact(r)]]
    symbol_handles = {h for r in after['drafting_symbols'] for h in r['source_handles']}
    drive_handles = {h for r in after['merged_drive_units'] for h in r['source_handles']}
    removals=[];old_groups=collections.defaultdict(list);new_groups=collections.defaultdict(list)
    for i in changed_old:
        row=old_rows[i]
        if set(row['source_handles']).issubset(symbol_handles|drive_handles):
            removals.append(dict(old_record(i),reason='merged_drive_detail' if set(row['source_handles']).issubset(drive_handles) else 'nonphysical_drafting_symbol'))
        else:
            old_groups[tuple(row['source_handles'])].append(old_record(i))
    for i in changed_new:
        row=new_rows[i];new_groups[tuple(row['source_handles'])].append(dict(row,new_ops_index=i))
    assert set(old_groups).issubset(new_groups),set(old_groups)-set(new_groups)
    added_keys=set(new_groups)-set(old_groups)
    permitted_added_keys={tuple(r['source_handles']) for r in after.get('recovered_loose_feeds',[])}
    assert added_keys==permitted_added_keys,(added_keys,permitted_added_keys)
    replacements=[dict(source_handles=list(key),old_instances=value,new_instances=new_groups[key]) for key,value in old_groups.items()]
    additions=[dict(source_handles=list(key),new_instances=new_groups[key]) for key in new_groups if key in added_keys]
    allowed_replaced={'SM_MPR_SorterOutput','SM_MPR_Turn__U33','SM_MPR_Conveyor2m'}
    assert all(r['old_pose']['mesh'] in allowed_replaced for group in replacements for r in group['old_instances'])
    assert len(removals)==182,len(removals)
    original_meshes={r['mesh'] for r in old_rows}
    names={r['mesh'] for r in new_rows}-original_meshes
    meshes=[r for r in mesh_manifest['meshes'] if r['name'] in names]
    assert len(meshes)==len(names),(names,meshes)
    return dict(schema_version=1,map=snapshot['map'],removals=removals,replacements=replacements,additions=additions,new_meshes=meshes,
                counts=dict(old=len(old_rows),new=len(new_rows),removed=len(removals),replaced_old=sum(len(v) for v in old_groups.values()),
                            replaced_new=sum(len(new_groups[key]) for key in old_groups),added=sum(len(new_groups[key]) for key in added_keys),unchanged=len(unchanged)),
                unchanged_digest=hashlib.sha256(json.dumps(unchanged,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                scope='Verified CAD drafting-symbol and duplicate-drive removals; four-cell and Y-merge detail; two U33 handedness repairs; three source-proven feed lines and 14 adjoining terminal height corrections')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',type=pathlib.Path,required=True)
    parser.add_argument('--after',type=pathlib.Path,default=ROOT/'SourceAssets/MPR/operations/instances.json')
    parser.add_argument('--snapshot',type=pathlib.Path,default=ROOT/'SourceAssets/MPR/exposure_20261106/after.json.gz')
    parser.add_argument('--mesh-manifest',type=pathlib.Path,default=ROOT/'SourceAssets/MPR/operations/mpr_operations.json')
    parser.add_argument('--output',type=pathlib.Path,default=ROOT/'SourceAssets/MPR/conveyor_repair_20261106/repair_manifest.json')
    args=parser.parse_args()
    manifest=build(read(args.before),read(args.after),read(args.snapshot),read(args.mesh_manifest))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest['counts']))
