"""Record read-only source provenance without copying the large original CAD."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(r'D:\Data\仓库数据\MPR')
OUT=ROOT/'SourceAssets/MPR/source_provenance.json'
MAIN='平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf'
ENV='仓库周围环境/cadmapper-carteret-new-jersey-us.dxf'
SORTER={
    '96格口木马装配指导书-V1.0(2).docx', '天工96宫格木马.jpg',
    'Snipaste_2026-10-30_16-27-55.png', 'Snipaste_2026-10-30_16-30-02.png',
}
ENV_REFERENCE={
    'Snipaste_2026-10-30_16-02-59.png', 'Snipaste_2026-10-30_16-04-43.png',
    'Snipaste_2026-10-30_16-13-26.png',
}
REPOSITORY_INPUTS=(
    'SourceAssets/GHS/Park/reference_style.json',
    'SourceAssets/GHS/RackSpecs/Models/cad_rack_models.json',
    'Scripts/ghs/park_vegetation.py', 'Scripts/ghs/park_vehicles.py',
    'Scripts/ghs/build_refined_rack_cargo.py', 'Scripts/ghs/build_cad_rack_models.py',
)

def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    assert (SOURCE/MAIN).is_file(), 'Original main CAD is required to record provenance'
    rows=[]
    for path in sorted(SOURCE.rglob('*')):
        # Ignore transient AutoCAD lock files (.dwl/.dwl2) and local backups.
        if not path.is_file() or path.suffix.lower() not in {'.dxf','.png','.jpg','.jpeg','.docx','.pdf'}:continue
        rel=path.relative_to(SOURCE).as_posix()
        role=('authoritative_main_plan' if rel==MAIN else
              'environment_geometry' if rel==ENV else
              'sorter_documented_reference' if path.parent.name=='天工木马播种机设备' and path.name in SORTER else
              'environment_documented_reference' if path.parent.name=='仓库周围环境' and path.name in ENV_REFERENCE else
              'provided_reference_inventory')
        row={'original_path':path.as_posix(),'relative_path':rel,'bytes':path.stat().st_size,
             'sha256':sha256(path),'role':role,'copied_to_repository':False}
        if rel==ENV:
            copied=ROOT/'SourceAssets/MPR/environment/cadmapper-carteret-new-jersey-us.dxf'
            assert sha256(copied)==row['sha256'], 'Environment DXF copy differs from original'
            row.update(copied_to_repository=True,repository_path=copied.relative_to(ROOT).as_posix())
        rows.append(row)
    inherited=[{'path':rel,'bytes':(ROOT/rel).stat().st_size,'sha256':sha256(ROOT/rel)}
               for rel in REPOSITORY_INPUTS]
    manifest={'schema_version':1,'source_root':SOURCE.as_posix(),
              'policy':'Original source files remain untouched. The 256 MB main CAD and reference images/docx are not copied into this change; compact extracted layout, evidence and authored assets are versioned.',
              'files':rows,'existing_repository_inputs':inherited,
              'external_dependencies':[
                  {'name':'ezdxf','path_hint':'Scripts/_vendor/cad','used_by':'main CAD extraction; use Python 3.12 for the existing NumPy binary wheel'},
                  {'name':'NumPy / Pillow','used_by':'CAD alignment and evidence previews'},
                  {'name':'Blender','used_by':'background asset generation and FBX verification'},
                  {'name':'Shapely >=2.1','path_hint':'Saved/ParkRefinement/python_deps','used_by':'environment mesh triangulation; install into Blender Python on another machine, do not commit this local binary cache'},
              ]}
    OUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('MPR_SOURCE_PROVENANCE',len(rows),'original files;',len(inherited),'existing repository inputs')

if __name__=='__main__':main()
