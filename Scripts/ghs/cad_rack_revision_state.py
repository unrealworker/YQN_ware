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
REFINEMENT_V2_REPORT = ROOT / 'Saved/GHS_RefinementV2.json'
TRUCK_MODELS_REPORT = ROOT / 'Saved/GHS_TruckModelsSplit.json'
REGISTRIES = (
    ROOT / 'SourceAssets/GHS/ue_scene_registry.json',
    ROOT / 'SourceAssets/GHS_Normal/ue_scene_registry.json',
    ROOT / 'SourceAssets/GHS/Presentation/visual_layout.json',
)
WORKFLOW = 'docs/superpowers/plans/2026-10-16-cad-rack-correction.md'
REFINEMENT_V2_WORKFLOW = 'SourceAssets/GHS/RefinementV2/README.md'


def refinement_v2_state():
    """Prefer the applied V2 report, then its persisted registry marker."""
    if REFINEMENT_V2_REPORT.is_file():
        report = json.loads(REFINEMENT_V2_REPORT.read_text(encoding='utf-8'))
        return 'complete' if report.get('success') is True else 'incomplete'
    for path in REGISTRIES:
        if path.is_file() and 'refinement_v2' in json.loads(path.read_text(encoding='utf-8')):
            return 'missing_report'
    return None


def revision_state():
    v2_state = refinement_v2_state()
    if v2_state is not None:
        return v2_state
    if REPORT.is_file():
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        return 'complete' if report.get('success') is True else 'incomplete'
    for path in REGISTRIES:
        if path.is_file() and json.loads(path.read_text(encoding='utf-8')).get('cad_rack_revision'):
            return 'missing_report'
    return None


def refuse_legacy_rebuild(entrypoint):
    v2_state = refinement_v2_state()
    if v2_state is not None:
        raise RuntimeError(
            f'{entrypoint} is a legacy builder and cannot modify GHS Refinement '
            f'V2 ({v2_state}). Preserve both maps and the historical reports; '
            f'inspect Saved/GHS_RefinementV2.json and {REFINEMENT_V2_WORKFLOW}. '
            'Do not remove the V2 report or registry marker to bypass this guard.'
        )
    state = revision_state()
    if state:
        raise RuntimeError(
            f'{entrypoint} is a legacy generic-rack builder and cannot modify '
            f'a CAD rack revision ({state}). Preserve both maps and use the '
            f'checkpointed CAD revision workflow in {WORKFLOW}; inspect '
            'Saved/GHS_CADRackRevision.json before starting a further revision. '
            'Do not remove the revision marker to bypass this guard.'
        )


def dispatch_refinement_v2_verification():
    """Dispatch only from explicit verifier entry points, never on import."""
    if dispatch_truck_models_verification():
        return True
    state = refinement_v2_state()
    if state is None:
        return False
    if state != 'complete':
        raise RuntimeError(
            f'GHS Refinement V2 is {state}; legacy verification cannot certify '
            'it or overwrite historical reports. Inspect '
            f'Saved/GHS_RefinementV2.json and {REFINEMENT_V2_WORKFLOW}.'
        )
    importlib.import_module('verify_refinement_v2').run()
    return True


def dispatch_truck_models_verification():
    """Keep V2's historical report intact after unpacking the truck instances."""
    if dispatch_agv_deck_verification():
        return True
    if TRUCK_MODELS_REPORT.is_file():
        state = 'complete' if json.loads(TRUCK_MODELS_REPORT.read_text(encoding='utf-8')).get('success') is True else 'incomplete'
    else:
        state = 'missing_report' if any(p.is_file() and 'truck_models_split' in json.loads(p.read_text(encoding='utf-8')) for p in REGISTRIES) else None
    if state is None:
        return False
    if state != 'complete':
        raise RuntimeError(f'Independent truck model conversion is {state}; inspect {TRUCK_MODELS_REPORT} before verification.')
    importlib.import_module('split_dock_truck_models').verify()
    return True


def dispatch_agv_deck_verification():
    if dispatch_normal_stacker_verification():
        return True
    report = ROOT / 'Saved/GHS_AGVDeckFix.json'
    if not report.is_file():
        return False
    if json.loads(report.read_text(encoding='utf-8')).get('success') is not True:
        raise RuntimeError(f'AGV deck repair is incomplete; inspect {report} before verification.')
    importlib.import_module('agv_deck_fix').verify()
    return True


def dispatch_normal_stacker_verification():
    if dispatch_normal_stacker_fx_verification():
        return True
    report = ROOT / 'Saved/GHS_NormalStackers.json'
    if not report.is_file():
        return False
    if json.loads(report.read_text(encoding='utf-8')).get('success') is not True:
        raise RuntimeError(f'Normal warehouse stacker placement is incomplete; inspect {report}.')
    importlib.import_module('add_normal_stackers').verify()
    return True


def dispatch_normal_stacker_fx_verification():
    report = ROOT / 'Saved/GHS_NormalStackerFX.json'
    if not report.is_file():
        return False
    if json.loads(report.read_text(encoding='utf-8')).get('success') is not True:
        raise RuntimeError(f'Normal stacker effects are incomplete; inspect {report}.')
    importlib.import_module('add_normal_stacker_fx').verify()
    return True


def dispatch_cad_rack_verification():
    if dispatch_refinement_v2_verification():
        return True
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
