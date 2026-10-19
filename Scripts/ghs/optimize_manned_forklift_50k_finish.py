import bpy, math, json
from pathlib import Path
OUT=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
asset=bpy.data.collections['MannedForklift_Editable'];root=bpy.data.objects['MF_Root']
assert root.get('optimization_50k_stage1') and not root.get('optimization_50k_stage2')

def count(o):
    dg=bpy.context.evaluated_depsgraph_get();e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles()
    n=len(m.loop_triangles);e.to_mesh_clear();return n

def apply(o,m):
    bpy.context.view_layer.objects.active=o;o.select_set(True)
    bpy.ops.object.modifier_apply(modifier=m.name);o.select_set(False)

def dissolve(o,angle):
    m=o.modifiers.new('Remove redundant coplanar edges','DECIMATE');m.decimate_type='DISSOLVE'
    m.angle_limit=math.radians(angle);m.use_dissolve_boundaries=False;m.delimit={'MATERIAL','SHARP','UV'}
    apply(o,m)

def reduce(o,target):
    n=count(o)
    if n<=target:return
    m=o.modifiers.new('Appearance weighted triangle budget','DECIMATE');m.decimate_type='COLLAPSE';m.ratio=target/n
    m.use_collapse_triangulate=True
    if o.name in {'DRV_Head','DRV_V3_ShortHair','DRV_SafetyHelmetShell'}:
        m.use_symmetry=True;m.symmetry_axis='Y'
    apply(o,m)
    o['triangle_budget']=target

for o in list(asset.children['05_Driver'].all_objects):
    if not o or o.type!='MESH':continue
    n=o.name
    targets={'DRV_Head':4200,'DRV_WorkJacket':2600,'DRV_Trousers':2000,'DRV_V3_ShortHair':600,'DRV_SafetyHelmetShell':1400,'DRV_SafetyHelmetBrim':400}
    if n in targets:reduce(o,targets[n])
    elif 'SleeveTape' in n:
        dissolve(o,.3);reduce(o,112)
    elif 'ChestTape' in n:
        dissolve(o,.3);reduce(o,64)
    elif any(s in n for s in ('ChestPocket','JacketPlacket','BadgeMark')):
        dissolve(o,.5);reduce(o,96)
    elif 'Glove' in n:reduce(o,104)
    elif 'HelmetRidge' in n:reduce(o,112)
    elif 'Ear' in n and count(o)>200:reduce(o,200)
    elif 'ZipSeam' in n:reduce(o,100)
    elif 'MouthCrease' in n:reduce(o,120)
    elif 'Lid' in n:reduce(o,100)

for o in list(asset.children['02_Wheels'].all_objects):
    if not o or o.type!='MESH':continue
    n=o.name
    if 'DishedRim' in n:reduce(o,500 if 'Front' in n else 350)
    elif 'RecessedBoltWasher' in n:reduce(o,44)
    elif n.endswith('_Hub'):reduce(o,100)
    elif n.endswith('_AxleCap'):reduce(o,64)

# Surface panels and lettering contain coplanar subdivisions that do not affect silhouettes.
for c in asset.children:
    if c.name in {'05_Driver','02_Wheels'}:continue
    for o in list(c.all_objects):
        if o and o.type=='MESH':dissolve(o,.15)

bpy.context.view_layer.update();root['optimization_50k_stage2']=True
groups={};rows=[]
for c in asset.children:
    for o in c.all_objects:
        if o and o.type=='MESH':
            nt=count(o);groups[c.name]=groups.get(c.name,0)+nt;rows.append({'name':o.name,'collection':c.name,'triangles':nt})
(OUT/'optimization_stage2.json').write_text(json.dumps({'groups':groups,'objects':rows},indent=2),encoding='utf-8')
print('STAGE2',sum(groups.values()),json.dumps(groups))
bpy.context.scene.render.filepath=str(OUT/'manned_forklift_50k_preview.png')
bpy.ops.render.render(write_still=True)
