import sys,json,collections,os
sys.path.insert(0,r'D:\UEPro\Test\Scripts\_vendor\cad')
import ezdxf
p=r'D:\EdgeDownload\平面布局图_GHS_0.23_20260710现状.dxf'
d=ezdxf.read(open(p,encoding="utf8",errors="replace")); m=d.modelspace()
r={'version':d.dxfversion,'units':d.units,'extmin':list(d.header.get('$EXTMIN')),'extmax':list(d.header.get('$EXTMAX')),'types':dict(collections.Counter(e.dxftype() for e in m)),'layers':{},'blocks':[],'texts':[]}
for e in m:
 l=e.dxf.layer
 if l not in r['layers']:r['layers'][l]=collections.Counter()
 r['layers'][l][e.dxftype()]+=1
 if e.dxftype() in ('TEXT','MTEXT'):r['texts'].append({'text':e.dxf.text if e.dxftype()=='TEXT' else e.plain_text(),'xy':list(e.dxf.insert),'layer':l,'h':e.dxf.handle})
for b in d.blocks:
 r['blocks'].append({'name':b.name,'count':len(b),'types':dict(collections.Counter(e.dxftype() for e in b))})
json.dump(r,open('SourceAssets/GHS/cad_analysis.json','w',encoding='utf8'),ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in r.items() if k not in ('blocks','texts')},ensure_ascii=False,indent=2));print('TEXTS',json.dumps(r['texts'][:180],ensure_ascii=False))


