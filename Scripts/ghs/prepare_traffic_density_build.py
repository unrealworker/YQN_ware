"""Record and normally close this session's clean editor for the traffic build."""
import hashlib, json, os
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test')
assert os.getpid()==24396, 'Editor changed; preserve it'
exec(compile((root/'Scripts/ghs/probe_traffic_density_editor.py').read_text(encoding='utf8'),'probe_traffic_density_editor.py','exec'))
assert result['map']=='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
assert not result['in_pie'] and not result['dirty_maps'] and not result['dirty_assets'], 'Preserve unsaved edits or active PIE'
result['map_sha256']={name:hashlib.sha256((root/'Content/Maps'/name).read_bytes()).hexdigest() for name in ('GHS_CAD_NormalWarehouse.umap','GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap')}
(root/'Saved/TrafficDensity/editor-before.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
unreal.SystemLibrary.quit_editor()
