"""Rebuild only the replay forklift diffusion decal; protect all other assets."""
import hashlib
import json
import shutil
import sys
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from replay_repair_trail_material import build_ripple_material, RIPPLE_PATH


def repair():
    target=ROOT/'Content/GHSOrderReplay/Materials/M_ReplayGroundRipple.uasset'
    out=ROOT/'Saved/OrderReplay/RippleVisibility-20261026';out.mkdir(parents=True,exist_ok=True)
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    protected=[ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap',
               ROOT/'Content/GHSTwinUI/data/order-replay.json',
               ROOT/'Scripts/video_reference/agv_fx_shader.py']
    protected.extend(p for p in (ROOT/'Content/GHSOrderReplay').rglob('*.uasset') if p!=target)
    before={str(p.relative_to(ROOT)):sha(p) for p in protected}
    backup=out/'M_ReplayGroundRipple.before.uasset'
    if target.exists() and not backup.exists():shutil.copy2(target,backup)
    statistics=build_ripple_material()
    assert all(sha(ROOT/name)==value for name,value in before.items()),'A protected source changed'
    material=unreal.EditorAssetLibrary.load_asset(RIPPLE_PATH)
    ml=unreal.MaterialEditingLibrary
    properties=[unreal.MaterialProperty.MP_BASE_COLOR,unreal.MaterialProperty.MP_EMISSIVE_COLOR,unreal.MaterialProperty.MP_OPACITY]
    pending=[ml.get_material_property_input_node(material,p) for p in properties]
    assert all(pending),'The ring requires blue coverage and emissive output'
    seen=set();parameters=set()
    while pending:
        node=pending.pop()
        if not node or node.get_path_name() in seen:continue
        seen.add(node.get_path_name())
        assert not isinstance(node,unreal.MaterialExpressionTime),'Use the replay clock so pause/seek stay exact'
        if isinstance(node,unreal.MaterialExpressionScalarParameter):parameters.add(str(node.get_editor_property('parameter_name')))
        pending.extend(x for x in ml.get_inputs_for_material_expression(material,node) if x)
    assert {'ReplayTime','Phase','RippleEmission'}<=parameters,parameters
    report=dict(success=True,material=RIPPLE_PATH,version=unreal.EditorAssetLibrary.get_metadata_tag(material,'GHS.Replay.FXVersion'),
                gradient_srgb=['#8BB9FF','#356BFA'],radius_cm=165,main_wave_core_width_cm=5.28,
                emission=.55,peak_wave_opacity=.96,period_seconds=2.,clock='ReplayTime',
                outputs=['BaseColor','Emissive','Opacity'],statistics=statistics,
                material_sha256=sha(target),protected_hashes=before,protected_sources_unchanged=True)
    (out/'material-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    unreal.log('REPLAY_RIPPLE_VISIBILITY_BUILT '+json.dumps(report,ensure_ascii=False))


if __name__=='__main__':repair()
