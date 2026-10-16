"""Create an immutable checkpoint before the CAD rack correction."""
import hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'Saved/GHS_CADRackCheckpoint.json'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run():
    assert not REPORT.exists(),'Checkpoint already exists; preserve it for the complete revision'
    backup=ROOT/'Saved/Backups'/('GHS_CADRacks_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True)
    files=['Content/Maps/GHS_CAD_DigitalTwin.umap','Content/Maps/GHS_CAD_NormalWarehouse.umap',
        'SourceAssets/GHS/ue_scene_registry.json','SourceAssets/GHS_Normal/ue_scene_registry.json',
        'SourceAssets/GHS/Presentation/visual_layout.json','SourceAssets/GHS/wall_height_profile.json']
    files += [p.relative_to(ROOT).as_posix() for p in (ROOT/'Saved').glob('GHS_*.json')]
    files += [p.relative_to(ROOT).as_posix() for p in (ROOT/'Scripts/ghs').glob('*.py')]
    copies={}
    for relative in dict.fromkeys(files):
        src=ROOT/relative;dst=backup/relative;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        copies[relative]=dict(sha256=sha(src),backup=str(dst))
    content={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}
    data=dict(success=True,backup_root=str(backup),files=copies,content_hashes=content,
              created_utc=datetime.now(timezone.utc).isoformat())
    REPORT.write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps(dict(backup=str(backup),backed_up_files=len(copies),content_files=len(content))))

if __name__=='__main__':run()
