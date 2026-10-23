"""Isolated commandlet import; no live editor or map save."""
import runpy
import unreal
assert unreal.EditorLoadingAndSavingUtils.load_map('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory')
runpy.run_path('D:/UEPro/Test/Scripts/ghs/replay_import_assets.py',run_name='__main__')
