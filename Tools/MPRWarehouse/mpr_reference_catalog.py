"""One source catalog for Blender composition, UE import and saved-map audit."""
from pathlib import Path
from collections import defaultdict
import json

VERSION=4
DEST='/Game/MPRWarehouse/ReferenceV4'
TAG='mpr-reference-exterior-v4'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def material_name(role):
    return 'MI_'+role if role.startswith(('MPR3_','MPR4_')) else 'MI_MPR4_Prop_'+role

def load_catalog(root, *, require_final=True):
    root=Path(root)
    src=root/'SourceAssets/MPR/reference_v4'
    architecture=src/'architecture/reference_shell_manifest.json'
    if not architecture.exists() and not require_final:
        architecture=root/'SourceAssets/MPR/reference_v3/architecture/reference_shell_manifest.json'
    paths=[('Architecture',architecture),('Props',src/'props/manifest.json'),
           ('Site',src/'site/manifest.json'),('Context',src/'context/manifest.json')]
    manifests=[(category,read(path)) for category,path in paths]
    specs={};rows=[];instances=defaultdict(list)
    for category,manifest in manifests:
        for role,spec in manifest['materials'].items():
            spec=dict(spec)
            if category=='Architecture':spec.setdefault('normal_convention','OpenGL')
            if role in specs and specs[role]!=spec:raise ValueError('Conflicting material '+role)
            specs[role]=spec
        rows.extend((category,dict(r,skip_auto_lods=True) if 'Tree' in r['name'] else dict(r)) for r in manifest['meshes'] if r.get('lod',0)==0)
        for name,items in manifest.get('instances',{}).items():instances[name].extend(items)
    named={row['name']:row for _,row in rows}
    props=dict(manifests)['Props']
    tree_rows=[r for _,r in rows if 'Tree' in r['name'] and r.get('instance_only')]
    if require_final:
        assert tree_rows and all(not r.get('metadata',{}).get('prototype',False) for r in tree_rows), 'Final foliage required'
    for i,placement in enumerate(dict(manifests)['Site'].get('planting',{}).get('tree_positions',[])):
        row=tree_rows[i%len(tree_rows)];bounds=row['bounds_m']
        radius=float(row.get('metadata',{}).get('crown_radius_m',max(bounds[0][1]-bounds[0][0],bounds[1][1]-bounds[1][0])/2))
        scale=float(placement['crown_radius_m'])/radius
        instances[row['name']].append(dict(position_m=placement['position_m'],rotation_deg=placement.get('rotation_deg',0),scale=[scale]*3))
    missing=set(instances)-set(named)
    if missing:raise ValueError('Unknown instance meshes: '+', '.join(sorted(missing)))
    return dict(manifests=manifests,paths=paths,materials=specs,rows=rows,instances=dict(instances))
