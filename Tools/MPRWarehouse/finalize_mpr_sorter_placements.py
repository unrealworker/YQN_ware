"""Build reviewable static instance manifest from measured CAD subassemblies."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/equipment'
groups=json.loads((OUT/'sorter_cad_groups.json').read_text(encoding='utf8'))
children=json.loads((OUT/'sorter_child_bounds.json').read_text(encoding='utf8'))
instances={'SM_MPR_SorterCAD64':[],'SM_MPR_SorterCAD120':[],'SM_MPR_SorterShort10':[]}
def instance(r,source,index):
 return {'position_m':[(r['min'][0]+r['max'][0])/2,(r['min'][1]+r['max'][1])/2,0],
  'rotation_deg':0,'scale':[1,1,1],'source_handle':source,'child_handle':r.get('handle'),
  'id':source+'_BRANCH_'+str(index),'cad_bounds_m':[r['min'],r['max']]}
for assembly in groups:
 if assembly['block']!='14234123':continue
 for side,rows in assembly['side_groups'].items():
  for r in rows:
   width=r['max'][0]-r['min'][0];depth=r['max'][1]-r['min'][1]
   if 6<width<6.5 and 2<depth<2.2:
    instances['SM_MPR_SorterCAD64'].append(instance(r,'2C9A89',len(instances['SM_MPR_SorterCAD64'])+1))
for r in children['2C9AE5']:
 if 7<r['size'][0]<7.5 and 2<r['size'][1]<2.3:
  instances['SM_MPR_SorterCAD120'].append(instance(r,'2C9AE5',len(instances['SM_MPR_SorterCAD120'])+1))
short_groups={'2794A8':7,'2794A9':7,'2794AA':8,'2794AB':8}
pitch=1.9499961  # Repeated CAD row pitch, matches the adjacent three 650mm floor tiles.
short_branches=[]
for r in children['2D41B7']:
 if r['handle'] not in short_groups:continue
 n=short_groups[r['handle']];depth=r['size'][1]-(n-1)*pitch
 for i in range(n):
  row={'min':[r['min'][0],r['min'][1]+i*pitch],
   'max':[r['max'][0],r['min'][1]+i*pitch+depth],
   'size':[r['size'][0],depth],'handle':r['handle']+'_row_'+str(i+1)}
  short_branches.append(row)
  instances['SM_MPR_SorterShort10'].append(instance(row,'2D41B7',len(instances['SM_MPR_SorterShort10'])+1))
children['short_branches']=short_branches
(OUT/'sorter_child_bounds.json').write_text(json.dumps(children,ensure_ascii=False,indent=2),encoding='utf8')
assert len(instances['SM_MPR_SorterCAD64'])==18
assert len(instances['SM_MPR_SorterCAD120'])==4
assert len(instances['SM_MPR_SorterShort10'])==30, len(instances['SM_MPR_SorterShort10'])
result={'schema_version':1,'coordinate_system':'CAD metres: origin [12800,8000], scale 0.0254; X/Y not mirrored. UE importer converts separately.',
 'instances':instances,'counts':{k:len(v) for k,v in instances.items()},
 'placement_evidence':{'2C9A89':'18 branches measured from outside-center CAD linework Y occupancy runs; endpoints recorded in sorter_cad_groups.json.',
  '2C9AE5':'4 exact nested INSERT transformed bounding boxes, handles 115C27 through 115C2A.',
  '2D41B7':'30 branches derived from four exact parent-group bboxes (7/7/8/8 rows) and CAD repeated pitch 1.9499961m; NOT individually extracted child bboxes. Count visually checked against the CAD linework preview.'},
 'capacity_note':'CAD gives horizontal 8/15/5 columns per side. Vertical counts are reconstructed (4/4/1), so 64/120/10 are modeled counts, not confirmed installed capacities.',
 'library_only':['SM_MPR_Tiangong96'],
 'source':'D:/Data/仓库数据/MPR/平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf'}
(OUT/'sorter_instances.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result['counts']))
