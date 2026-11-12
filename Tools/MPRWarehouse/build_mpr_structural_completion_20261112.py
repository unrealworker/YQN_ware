"""Build missing nested CAD column profiles and external entrance stair plans.

All planar dimensions are source-derived. Column/stair vertical dimensions use
the existing scene interfaces and are declared visualization estimates. No UE
access, no existing FBX overwrite, no scene/map creation.
"""
from pathlib import Path
import json
import gzip
import math
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_reference_shell_v4_lib import Geometry
SRC=ROOT/'Saved/MPR/interior_cad_20261112/architectural_details'
OUT=ROOT/'SourceAssets/MPR/interior_cad_20261112/structure'


def bbox(row):
    return [[row['center_m'][i]-row['size_m'][i]/2,row['center_m'][i]+row['size_m'][i]/2] for i in (0,1)]


def beam(g,name,role,a,b,width):
    a,b=Vector(a),Vector(b);t=(b-a).normalized()
    ref=Vector((0,0,1)) if abs(t.z)<.95 else Vector((0,1,0))
    u=t.cross(ref).normalized()*width/2;v=t.cross(u).normalized()*width/2
    vertices=[tuple(p+sx*u+sy*v) for p in (a,b) for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1))]
    g.mesh(name,role,vertices,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    columns=json.loads((SRC/'column_sections.json').read_text(encoding='utf8'))
    conflicts=json.loads((SRC/'paired_column_conflicts.json').read_text(encoding='utf8'))
    stairs=json.loads((SRC/'stairs.json').read_text(encoding='utf8'))
    original=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_extracted.json').read_text(encoding='utf8'))
    byhandle={tuple(g['source_handles']):g for g in original['architecture']}
    baseline=json.load(gzip.open(ROOT/'Saved/MPR/interior_cad_20261112/preservation/baseline.json.gz','rt',encoding='utf8'))
    materials=dict(Porcelain=dict(color=[.83,.85,.88],roughness=.76),
                   Cobalt=dict(color=[.018,.075,.51],roughness=.76),
                   Metal=dict(color=[.43,.49,.57],roughness=.76))
    geometry=Geometry(materials)
    raw=[c for c in columns if c['nearest_current_center_distance_m']>.01]
    assert len(raw)==148
    # An exact duplicate and five enclosing profiles describe the same solid
    # footprint. Retain source provenance without introducing coincident faces.
    unique={}
    duplicate_count=0
    for column in raw:
        key=tuple(round(v,5) for b in bbox(column) for v in b)
        if key in unique:
            unique[key]['additional_source_handles'].append(column['source_handles']);duplicate_count+=1
        else:
            unique[key]=dict(column,additional_source_handles=[])
    values=list(unique.values());retained=[];contained=[]
    for c in values:
        box=bbox(c)
        enclosing=[]
        for outer in values:
            if outer is c:continue
            big=bbox(outer)
            if all(box[i][0]>=big[i][0]-1e-6 and box[i][1]<=big[i][1]+1e-6 for i in (0,1)):
                enclosing.append(outer)
        if enclosing:
            outer=max(enclosing,key=lambda x:math.prod(x['size_m']))
            outer['additional_source_handles'].append(c['source_handles'])
            outer['additional_source_handles'].extend(c['additional_source_handles'])
            contained.append(dict(inner=c['source_handles'],outer=outer['source_handles']))
        else:retained.append(c)
    assert len(retained)==142 and duplicate_count==1 and len(contained)==5
    for c in retained:
        x,y=c['center_m'];sx,sy=c['size_m']
        geometry.box('SM_MPR_CAD_NestedColumns_20261112','Cobalt',(x,y,.13),(sx,sy,.26))
        geometry.box('SM_MPR_CAD_NestedColumns_20261112','Porcelain',(x,y,6.23),(sx,sy,11.94))
    removals=[]
    for conflict in conflicts:
        p=conflict['current_column']['position_m']
        for prefix,z in [('MPR_Columns_',610.),('MPR_ColumnBases_',13.)]:
            matches=[]
            for actor in baseline['actors']:
                if not actor['label'].startswith(prefix):continue
                for component in actor['components']:
                    for index,transform in enumerate(component.get('instance_transforms',[])):
                        if math.dist(transform['translation_cm'],[p[0]*100,-p[1]*100,z])<.001:
                            matches.append(dict(actor_guid=actor['guid'],actor_label=actor['label'],component_name=component['name'],
                                instance_index=index,expected_transform=transform,source_pillar_handle=conflict['current_column']['source_handles'],
                                replacement_source_sections=[c['source_handles'] for c in conflict['nearest_source_sections']],
                                reason='Misplaced single centre cube/base between two CAD column profiles; replace with the two measured profiles.'))
            assert len(matches)==1,(prefix,p,matches)
            removals.extend(matches)
    assert len(removals)==6
    stair_specs=[]
    for stair in stairs:
        if stair['entity_count']<30:continue
        rows=[byhandle[tuple(h)] for h in stair['source_handles']]
        north=stair['center_m'][1]>0
        wall_y=stair['bounds_m'][1][0] if north else stair['bounds_m'][1][1]
        outward=1 if north else -1
        # The eight LINE tread edges are spaced at 11 inches. LWPOLYLINE
        # offset lines are tread noses, not extra steps.
        tread_lines=[]
        for row in rows:
            if row['type']!='LINE' or len(row['points_m'])!=2:continue
            a,b=row['points_m']
            if abs(a[1]-b[1])<.0001 and 1.50<abs(a[0]-b[0])<1.55:
                tread_lines.append(row)
        tread_lines.sort(key=lambda row:(row['points_m'][0][1]-wall_y)*outward)
        ys=[]
        for row in tread_lines:
            y=row['points_m'][0][1]
            if not ys or abs(y-ys[-1])>.001:ys.append(y)
        assert len(ys)==8,(stair['index'],ys)
        assert all(abs(abs(b-a)-.2794)<.0001 for a,b in zip(ys,ys[1:]))
        tread_x=[min(p[0] for row in tread_lines for p in row['points_m']),
                 max(p[0] for row in tread_lines for p in row['points_m'])]
        touching=[]
        for row in rows:
            for a,b in zip(row['points_m'],row['points_m'][1:]):
                if abs(a[0]-b[0])<.001 and abs(a[1]-b[1])>1 and min(abs(a[1]-wall_y),abs(b[1]-wall_y))<.001:
                    touching.append(a[0])
        assert len(touching)>=2
        platform_x=[min(touching),max(touching)]
        assert abs(abs(ys[0]-wall_y)-1.8288)<.001
        name='SM_MPR_CAD_EntranceStairs_20261112'
        # Raised landing and seven intermediate treads yield eight150mm rises
        # between existing scene ground -1.2m and warehouse floor0m.
        geometry.box(name,'Porcelain',((platform_x[0]+platform_x[1])/2,(wall_y+ys[0])/2,-.06),
                     (platform_x[1]-platform_x[0],abs(ys[0]-wall_y),.12))
        for i,(a,b) in enumerate(zip(ys,ys[1:])):
            top=-(i+1)*1.2/8
            geometry.box(name,'Porcelain',((tread_x[0]+tread_x[1])/2,(a+b)/2,top-.03),
                         (tread_x[1]-tread_x[0],abs(b-a),.06))
        # Source side rails flank the1.524m tread; their vertical profile follows
        # the same declared scene rise. Handrails continue through each landing.
        rail_x=[tread_x[0]-.1016,tread_x[1]+.1016]
        for x in rail_x:
            beam(geometry,name,'Cobalt',(x,ys[0],-.13),(x,ys[-1],-1.2),.09)
            for z in (1.05,.55):
                beam(geometry,name,'Metal',(x,ys[0],z),(x,ys[-1],z-1.2),.035)
            for i in (0,4,7):
                y=ys[i];base=-i*1.2/7
                beam(geometry,name,'Cobalt',(x,y,base),(x,y,base+1.05),.04)
        for x in (platform_x[0],platform_x[1]):
            for z in (.55,1.05):beam(geometry,name,'Metal',(x,wall_y,z),(x,ys[0],z),.035)
            for y in (wall_y,ys[0]):beam(geometry,name,'Cobalt',(x,y,-1.2),(x,y,1.05),.05)
        # Guard the front of an enlarged two-door landing, leaving flight open.
        if platform_x[1]-rail_x[1]>.2:
            for z in (.55,1.05):beam(geometry,name,'Metal',(rail_x[1],ys[0],z),(platform_x[1],ys[0],z),.035)
        if rail_x[0]-platform_x[0]>.2:
            for z in (.55,1.05):beam(geometry,name,'Metal',(platform_x[0],ys[0],z),(rail_x[0],ys[0],z),.035)
        stair_specs.append(dict(source_index=stair['index'],source_handles=stair['source_handles'],
            platform_x_m=platform_x,wall_y_m=wall_y,tread_edge_y_m=ys,tread_x_m=tread_x,
            measured_tread_pitch_m=.2794,measured_platform_depth_m=1.8288,
            tread_edge_handles=[r['source_handles'] for r in tread_lines],nearby_door_handles=stair['nearby_door_handles'],
            ground_m=-1.2,warehouse_floor_m=0.,rises=8,rise_m=.15,
            height_basis='Scene interface estimate; CAD plan proves footprint and tread positions, not rise or floor elevation.'))
    assert len(stair_specs)==18
    manifest=geometry.export(OUT,dict(scope='Independent structural addition. Existing first architecture patch unchanged.',
        source_sha256='c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863',
        additions=[dict(mesh='SM_MPR_CAD_NestedColumns_20261112',location_cm=[0,0,0],instances_in_mesh=len(retained)),
                   dict(mesh='SM_MPR_CAD_EntranceStairs_20261112',location_cm=[0,0,0],stair_groups=len(stair_specs))],
        replacements=[],removals=removals,
        column_height_m=12.2,column_height_basis='Match current retained164-column scene height, not measured from2D column sections.',
        column_sections=retained,covered_inner_sections=contained,duplicate_source_sections=duplicate_count,
        source_column_section_count=309,current_columns_retained=161,final_unique_column_profile_count=303,
        stairs=stair_specs,limitations=['Handrail height1.05m, member widths and tread thickness are visualization dimensions.',
             'One northern stair group has no associated DR1H door insert; retain source stairs without inventing a facade doorway.',
             'No window or masonry wall-height reconstruction is included.']),{})
    (OUT/'structural_completion_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(manifest=str(OUT/'structural_completion_manifest.json'),additions=2,
                         added_column_profiles=len(retained),stair_groups=len(stair_specs),instance_removals=len(removals)),ensure_ascii=False))


if __name__=='__main__':main()
