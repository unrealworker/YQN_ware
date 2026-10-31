"""Full editor runner; -ExecutePythonScript exits the editor after completion."""
from pathlib import Path
import runpy
import unreal

folder = Path(unreal.Paths.project_dir()) / 'Tools/GlobeNavigation'
runpy.run_path(str(folder / 'check_axes.py'), run_name='__main__')
runpy.run_path(str(folder / 'import_globe.py'), run_name='__main__')
