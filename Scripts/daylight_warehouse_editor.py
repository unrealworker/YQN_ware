from pathlib import Path
import unreal
script = Path(r"D:\UEPro\Test\Scripts\build_logistics_warehouse.py").read_text(encoding="utf-8")
exec(compile(script.split("\ntry:\n    import_assets()")[0],"build_logistics_warehouse.py","exec"),globals())
setup_daylight_sky()
assert levels.save_current_level()
exec(compile((ROOT/"Scripts/verify_warehouse_editor.py").read_text(encoding="utf-8"),"verify_warehouse_editor.py","exec"),globals())
