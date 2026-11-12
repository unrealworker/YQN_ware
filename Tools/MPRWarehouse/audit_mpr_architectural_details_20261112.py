"""Audit nested architectural stairs, windows and column sections against UE baseline.

Uses source geometry already checked by audit_mpr_interior_spec_20261112.py.
Creates evidence only; it does not generate or edit scene geometry.
"""
from pathlib import Path
import collections
import gzip
import json
import math
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Saved/MPR/interior_cad_20261112/architectural_details'
OUT.mkdir(parents=True,exist_ok=True)
layout=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
extracted=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_extracted.json').read_text(encoding='utf8'))
baseline=json.load(gzip.open(ROOT/'Saved/MPR/interior_cad_20261112/preservation/baseline.json.gz','rt',encoding='utf8'))
architecture=extracted['architecture']
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
colors={'A-STAIRS':'#bd1d2d','A-WIND':'#008b65','A-COL-ENCL':'#cc7314'}


def bounds(rows):
    points=[p for row in rows for p in row['points_m']]
    return [[min(p[i] for p in points),max(p[i] for p in points)] for i in (0,1)]


def clusters(rows,tolerance=.2):
    bb=[bounds([row]) for row in rows];parent=list(range(len(rows)))
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i in range(len(rows)):
        for k in range(i):
            if all(max(bb[i][a][0]-bb[k][a][1],bb[k][a][0]-bb[i][a][1])<tolerance for a in (0,1)):
                parent[root(i)]=root(k)
    result=collections.defaultdict(list)
    for i,row in enumerate(rows):result[root(i)].append(row)
    return sorted(result.values(),key=lambda group:(bounds(group)[1][0],bounds(group)[0][0]))


def panel(center,span,title,subtitle='',width=700,height=640,current_columns=True):
    image=Image.new('RGB',(width,height),'#ffffff');d=ImageDraw.Draw(image)
    scale=min((width-60)/span[0],(height-105)/span[1])
    def project(p):return (width/2+(p[0]-center[0])*scale,(height+40)/2-(p[1]-center[1])*scale)
    for row in architecture:
        color=colors.get(row['layer'],'#a4a4a4')
        for a,b in zip(row['points_m'],row['points_m'][1:]):
            if max(a[0],b[0])<center[0]-span[0]/2 or min(a[0],b[0])>center[0]+span[0]/2:continue
            if max(a[1],b[1])<center[1]-span[1]/2 or min(a[1],b[1])>center[1]+span[1]/2:continue
            d.line([project(a),project(b)],fill=color,width=2 if row['layer'] in colors else 1)
    if current_columns:
        for col in layout['columns']:
            x,y=col['position_m'];sx,sy=col['size_m']
            if abs(x-center[0])<span[0]/2 and abs(y-center[1])<span[1]/2:
                d.rectangle([project((x-sx/2,y+sy/2)),project((x+sx/2,y-sy/2))],outline='#145bd0',width=3)
    d.rectangle((0,0,width,62),fill='white')
    d.text((12,10),title,font=font,fill='black');d.text((12,36),subtitle,font=small,fill='black')
    d.rectangle((0,height-30,width,height),fill='white')
    d.text((12,height-25),'Red stairs / green windows / orange CAD columns / blue existing columns',font=small,fill='black')
    return image


def main():
    stairs=[]
    stair_rows=[g for g in architecture if g['layer']=='A-STAIRS']
    for i,group in enumerate(clusters(stair_rows)):
        bb=bounds(group);center=[(a+b)/2 for a,b in bb];size=[b-a for a,b in bb]
        real=len(group)>30 and min(size)>1.
        doors=[]
        for door in layout['pedestrian_doors']:
            x,y=door['position_m']
            if bb[0][0]-.5<x<bb[0][1]+.5 and bb[1][0]-.8<y<bb[1][1]+.8:
                doors.append(door['source_handles'])
        stairs.append(dict(index=i,entity_count=len(group),bounds_m=bb,size_m=size,center_m=center,
            source_handles=[g['source_handles'] for g in group],nearby_door_handles=doors,
            classification='external entrance stair and landing; repeated treads and handrail plan, physically adjoining facade' if real else 'isolated small square; not sufficient evidence for a staircase',
            height_m=None,scene_coverage='No dedicated stairs asset/actor or stair generator found in baseline' if real else 'do not model as stair'))
    source_columns=[]
    for row in architecture:
        if row['layer']!='A-COL-ENCL':continue
        bb=bounds([row]);center=[(a+b)/2 for a,b in bb];size=[b-a for a,b in bb]
        nearest=min((math.dist(center,c['position_m']),c['id']) for c in layout['columns'])
        source_columns.append(dict(source_handles=row['source_handles'],points_m=row['points_m'],center_m=center,size_m=size,
            nearest_current_column_id=nearest[1],nearest_current_center_distance_m=nearest[0],
            classification='matching selected structural column' if nearest[0]<.01 else 'unmodeled closed architectural column section; inspect profile and shared/paired position',height_m=None))
    displaced=[]
    for col in layout['columns']:
        nearest=sorted(source_columns,key=lambda c:math.dist(c['center_m'],col['position_m']))[:2]
        if math.dist(nearest[0]['center_m'],col['position_m'])>.01:
            displaced.append(dict(current_column=col,nearest_source_sections=nearest,
                issue='Single current square is centered between two source sections; must not count as exact source-section reproduction'))
    windows=[]
    for i,group in enumerate(clusters([g for g in architecture if g['layer']=='A-WIND'])):
        bb=bounds(group);size=[b-a for a,b in bb]
        windows.append(dict(index=i,bounds_m=bb,size_m=size,entity_count=len(group),
                            source_handles=[g['source_handles'] for g in group],height_m=None))
    report=dict(source=layout['source'],verified_source_sha256='c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863',
        stair_groups=len(stairs),complete_external_stair_groups=sum(s['entity_count']>30 for s in stairs),
        internal_stair_groups=0,isolated_stair_layer_square_count=sum(s['entity_count']==1 for s in stairs),
        nested_closed_column_sections=len(source_columns),matched_existing_centers=sum(c['nearest_current_center_distance_m']<.01 for c in source_columns),
        unmodeled_sections_farther_than_half_m=sum(c['nearest_current_center_distance_m']>.5 for c in source_columns),
        single_current_columns_between_source_pairs=len(displaced),window_groups=len(windows),
        current_glazing_actors=[dict(label=a['label'],guid=a['guid'],hidden=a['hidden'],meshes=[c.get('mesh') for c in a['components'] if c.get('mesh')])
             for a in baseline['actors'] if 'Glazing' in a['label']],
        findings=[
            dict(priority='high',id='nested_columns_missing',conclusion='164 selected PILLAR inserts are correctly placed but do not cover the nested architectural base column sections.',
                 safe_repair='Combine the nested source sections with selected PILLAR using geometric matching. Preserve 161 matches; explicitly resolve the 3 paired-column conflicts. Match current height only as declared visualization estimate; do not duplicate coincident structural cores.'),
            dict(priority='high',id='external_stairs_missing',conclusion='18 full stair-and-landing plan assemblies physically adjoin pedestrian doors on the north/south facade; no stair geometry in baseline.',
                 safe_repair='Follow measured tread/landing/rail footprints. Height remains unknown in CAD; current exterior-to-floor delta1.2m is a scene assumption, not surveyed stair rise. Exclude the isolated square.'),
            dict(priority='medium',id='window_layout_not_cad',conclusion='Source window groups extend along the west and east walls and three entry vestibules; current three glazing actors derive from two regular display bands, including an older overlapping band.',
                 safe_repair='Map actual window faces and vestibule plan first. Do not turn horizontal plan frames into arbitrary solid cuboids; heights and mullion vertical divisions require declared assumptions or elevations.'),
        ],scope='Read-only source and saved baseline audit; no new geometry generated; source layers are corroborated by repeated geometry and current overlaps, not names alone.')
    for name,data in [('detail_audit',report),('stairs',stairs),('column_sections',source_columns),('paired_column_conflicts',displaced),('windows',windows)]:
        (OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    overview=panel((0,-4),(378,190),'MPR nested architectural features','Plan positions; figures and elevations outside the building excluded',1600,900)
    overview.save(OUT/'architectural_features_plan.png')
    examples=[
        ((-123.84,-86.4),(5.5,6.5),'Repeated entrance stair','2C93B4 / 2E0BF6 etc; 1.8796m x 4.6736m'),
        ((16.2,-86.4),(6.8,6.5),'Two-door entrance stair','2C93B4 / 2E0F03 etc; common landing and treads'),
        ((-86.83244,41.01838),(1.7,1.5),'Two source columns, one model column','Source 2E0F65 / companion; CAD pair vs centre cube'),
        ((23.96,-50.42162),(2.,1.5),'Nested structural sections missing','Source 2E0B69 + 2E145B; 254mm square pair'),
        ((-181.1,25),(3.5,12),'Measured window spacing','West wall windows also exist outside display y50..80 band'),
        ((-176.7,80),(11.,8.),'Entry vestibule construction','A-WIND wall/entry assembly: plan detail is physical'),
    ]
    sheet=Image.new('RGB',(2100,1280),'white')
    for i,(center,span,title,subtitle) in enumerate(examples):sheet.paste(panel(center,span,title,subtitle),(i%3*700,i//3*640))
    sheet.save(OUT/'architectural_details_evidence.png')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
