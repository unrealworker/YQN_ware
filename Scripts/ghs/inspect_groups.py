import sys,json,collections
sys.path.insert(0,r'D:\UEPro\Test\Scripts\_vendor\cad')
import ezdxf
from ezdxf import bbox
p=r'D:\EdgeDownload\平面布局图_GHS_0.23_20260710现状.dxf'
d=ezdxf.read(open(p,encoding="utf8",errors="replace"));m=d.modelspace()
r=json.load(open('SourceAssets/GHS/cad_analysis.json',encoding='utf8'));r['texts']=[];r['insert_groups']=[]
for e in m:
 if e.dxftype() in ('TEXT','MTEXT'):r['texts'].append({'text':e.dxf.text if e.dxftype()=='TEXT' else e.plain_text(),'xy':list(e.dxf.insert),'layer':e.dxf.layer,'h':e.dxf.handle})
groups=collections.defaultdict(list)
for e in m.query('INSERT'):groups[(e.dxf.layer,e.dxf.name)].append(e)
for (l,n),es in groups.items():
 b=d.blocks.get(n);bb=bbox.extents(b,fast=True)
 r['insert_groups'].append({'layer':l,'name':n,'count':len(es),'local_bounds':[list(bb.extmin),list(bb.extmax)] if bb.has_data else None,'position_range':[[min(e.dxf.insert[i] for e in es) for i in range(2)],[max(e.dxf.insert[i] for e in es) for i in range(2)]],'sample':{'h':es[0].dxf.handle,'xy':list(es[0].dxf.insert),'scale':[es[0].dxf.xscale,es[0].dxf.yscale],'rot':es[0].dxf.rotation}})
json.dump(r,open('SourceAssets/GHS/cad_analysis.json','w',encoding='utf8'),ensure_ascii=False,indent=2)
print(json.dumps(r['insert_groups'],ensure_ascii=False));print(json.dumps(r['texts'],ensure_ascii=False))


