"""Record the appearance references without copying or modifying their sources."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(r'D:\CodexTemp\output\imagegen\industrial-saas\multiview')
OUT=ROOT/'SourceAssets/MPR/reference_v3/reference_provenance.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p),role='site composition' if p.name.startswith('ChatGPT') else 'appearance and visible detail') for p in sorted(SOURCE.glob('*.png'))]
assert len(rows)==7
result=dict(schema_version=1,user_approved_appearance_source=str(SOURCE),references=rows,
 layout_sources=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'SourceAssets/MPR/mpr_cad_layout.json',ROOT/'SourceAssets/MPR/environment/environment_local.json']],
 scope='Replace main-building exterior and all MPR outdoor actors, preserve existing interior actors and dependency bytes. Continue unpictured areas in the same visual language.',
 evidence_limits='Multiview images are appearance concepts. CAD is authoritative for the main footprint/openings and aligned surrounding positions. Landscaping, vehicle occupancy and facade details are visual estimates.')
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('REFERENCE_PROVENANCE',len(rows))
