"""Protect measured rack revisions from legacy rebuild and verification paths.

This module performs no UE imports or writes. Verification imports the new
checker only when called, so its imports of legacy comparison helpers cannot
recursively trigger another verification.
"""
import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'Saved/GHS_CADRackRevision.json'
REGISTRIES = (
    ROOT / 'SourceAssets/GHS/ue_scene_registry.json',
    ROOT / 'SourceAssets/GHS_Normal/ue_scene_registry.json',
    ROOT / 'SourceAssets/GHS/Presentation/visual_layout.json',
)
WORKFLOW = 'docs/superpowers/plans/2026-10-16-cad-rack-correction.md'


def revision_state():
    if REPORT.is_file():
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        return 'complete' if report.get('success') is True else 'incomplete'
    for path in REGISTRIES:
        if path.is_file() and json.loads(path.read_text(encoding='utf-8')).get('cad_rack_revision'):
            return 'missing_report'
    return None


def refuse_legacy_rebuild(entrypoint):
    state = revision_state()
    if state:
        raise RuntimeError(
            f'{entrypoint} is a legacy generic-rack builder and cannot modify '
            f'a CAD rack revision ({state}). Preserve both maps and use the '
            f'checkpointed CAD revision workflow in {WORKFLOW}; inspect '
            'Saved/GHS_CADRackRevision.json before starting a further revision. '
            'Do not remove the revision marker to bypass this guard.'
        )


def dispatch_cad_rack_verification():
    state = revision_state()
    if state is None:
        return False
    if state != 'complete':
        raise RuntimeError(
            f'CAD rack revision is {state}; the legacy verifier cannot certify '
            'or overwrite its historical report. Inspect '
            f'Saved/GHS_CADRackRevision.json and {WORKFLOW}.'
        )
    importlib.import_module('verify_cad_rack_revision').run()
    return True
