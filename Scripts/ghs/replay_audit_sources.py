"""Verify the exported trace and obstacle probe refer to the current saved world."""
import hashlib
import json


def verify_sources(root, data):
    path = root/'Saved/OrderReplay/scene_probe.json'
    raw = path.read_bytes()
    probe = json.loads(raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    assert data['provenance']['sceneProbe'] == source_hash, 'Trace was generated from a different scene probe'
    map_path = root/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    scene_path = root/'Content/GHSTwinUI/data/scene-bindings.json'
    assert probe['map'].split('.')[0] == '/Game/Maps/'+map_path.stem
    assert probe['unchanged'] and not probe['dirty_maps'] and not probe['dirty_content'], 'Probe must represent a saved editor world'
    for k,p in [('map_sha256',map_path),('registry_sha256',scene_path)]:
        assert probe.get(k)==hashlib.sha256(p.read_bytes()).hexdigest(), f'Obsolete probe for {p.name}'
    return probe, {key:probe[key] for key in ('map_sha256','registry_sha256')} | {'source_probe_sha256':source_hash}
