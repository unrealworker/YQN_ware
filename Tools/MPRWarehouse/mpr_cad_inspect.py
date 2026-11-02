"""Inventory the source DXF without modifying it; uses the existing vendored ezdxf."""
import sys,json,collections,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
import ezdxf
SOURCE=pathlib.Path(r'D:\Data\仓库数据\MPR\平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
OUT=ROOT/'SourceAssets/MPR';OUT.mkdir(parents=True,exist_ok=True)
start=time.time()
doc=ezdxf.read(open(SOURCE,encoding='utf8',errors='replace'))
ms=doc.modelspace()
r={'source':str(SOURCE),'version':doc.dxfversion,'units':doc.units,'extmin':list(doc.header.get('$EXTMIN')),'extmax':list(doc.header.get('$EXTMAX')),'types':dict(collections.Counter(e.dxftype() for e in ms)),'layers':{},'blocks':[],'texts':[],'insert_groups':[]}
groups=collections.defaultdict(list)
for e in ms:
 layer=e.dxf.layer
 r['layers'].setdefault(layer,collections.Counter())[e.dxftype()]+=1
 if e.dxftype() in ('TEXT','MTEXT'):
  r['texts'].append({'text':e.dxf.text if e.dxftype()=='TEXT' else e.plain_text(),'xy':list(e.dxf.insert),'layer':layer,'handle':e.dxf.handle})
 if e.dxftype()=='INSERT':groups[(layer,e.dxf.name)].append(e)
for b in doc.blocks:
 r['blocks'].append({'name':b.name,'count':len(b),'types':dict(collections.Counter(e.dxftype() for e in b)),'layers':dict(collections.Counter(e.dxf.layer for e in b))})
for (layer,name),es in groups.items():
 r['insert_groups'].append({'layer':layer,'name':name,'count':len(es),'position_range':[[min(e.dxf.insert[i] for e in es) for i in range(2)],[max(e.dxf.insert[i] for e in es) for i in range(2)]],'sample':{'handle':es[0].dxf.handle,'xyz':list(es[0].dxf.insert),'scale':[es[0].dxf.xscale,es[0].dxf.yscale,es[0].dxf.zscale],'rot':es[0].dxf.rotation}})
(OUT/'mpr_cad_inventory.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'seconds':round(time.time()-start,1),'version':r['version'],'units':r['units'],'types':r['types'],'layer_count':len(r['layers']),'block_count':len(r['blocks']),'top_insert_groups':sorted(r['insert_groups'],key=lambda x:-x['count'])[:45]},ensure_ascii=False))
