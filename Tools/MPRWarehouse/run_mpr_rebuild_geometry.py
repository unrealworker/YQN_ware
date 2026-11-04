"""Run MPR GEOS geometry in standalone CPython, never inside Blender.

Use Blender's bundled python.exe (not blender.exe). Only the small, inspected
geometry primitives are loaded from Blender-oriented shared modules. The build
entry's --geometry-only branch must serialize plain data and return before any
editor API or exporter call; forbidden API shims fail closed if that changes.
"""
import ast
import importlib
import math
import sys
import types
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT/'Tools/MPRWarehouse'


def _forbidden(*args, **kwargs):
    raise RuntimeError('Blender geometry API/export is unavailable in standalone geometry stage')


class _UnavailableEditor(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        raise RuntimeError('Unexpected Blender API in standalone geometry stage: bpy.'+name)


def _source_nodes(filename, names, node_type):
    path = TOOLS/filename
    module = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    selected = [node for node in module.body if isinstance(node, node_type) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise RuntimeError('Shared geometry helper contract changed: '+filename)
    return compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec')


def load_geometry_builder():
    """Install narrow shims and import the existing builder without editor code."""
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError('Use standalone Python 3.13 matching Saved/ParkRefinement/python_deps')
    if 'bpy' in sys.modules:
        raise RuntimeError('Run once in a fresh standalone Python process, not Blender')
    sys.path[:0] = [str(TOOLS), str(ROOT/'Saved/ParkRefinement/python_deps'), str(ROOT/'Scripts/ghs')]
    unavailable = _UnavailableEditor('bpy')
    sys.modules['bpy'] = unavailable

    common = types.ModuleType('mpr_blender_common')
    common.__file__ = str(TOOLS/'mpr_blender_common.py')
    common.__dict__.update(defaultdict=defaultdict, math=math, bpy=unavailable,
                           Vector=_forbidden, tessellate_polygon=_forbidden)
    exec(_source_nodes('mpr_blender_common.py', {'Geometry'}, ast.ClassDef), common.__dict__)
    # These two shared methods are not needed by the current rebuild. Failing
    # explicitly is safer than pretending a polygon tessellator or exporter ran.
    common.Geometry.prism = _forbidden
    common.Geometry.export = _forbidden
    sys.modules[common.__name__] = common

    style = types.ModuleType('build_mpr_reference_context_v4')
    style.__file__ = str(TOOLS/'build_mpr_reference_context_v4.py')
    style.G = common.Geometry()
    for name, role in dict(W='Wall', R='Roof', T='Trim', V='Glass', P='Paving').items():
        setattr(style, name, 'MPR4_Context'+role)
    exec(_source_nodes('build_mpr_reference_context_v4.py', {'box', 'roof', 'house'}, ast.FunctionDef), style.__dict__)
    sys.modules[style.__name__] = style

    exporter = types.ModuleType('build_mpr_reference_site')
    exporter.__file__ = str(TOOLS/'build_mpr_reference_site.py')
    exporter.export = _forbidden
    sys.modules[exporter.__name__] = exporter
    return importlib.import_module('build_mpr_rebuild')


def main():
    source = (TOOLS/'build_mpr_rebuild.py').read_text(encoding='utf-8')
    syntax = ast.parse(source)
    if not any(isinstance(node, ast.Constant) and node.value == '--geometry-only' for node in ast.walk(syntax)):
        raise RuntimeError('Builder must implement its serializing --geometry-only branch before this entry is run')
    if '--geometry-only' not in sys.argv:
        sys.argv.append('--geometry-only')
    builder = load_geometry_builder()
    print('MPRR_STANDALONE_GEOMETRY', sys.executable, sys.version.split()[0], flush=True)
    builder.main()


if __name__ == '__main__':
    main()
