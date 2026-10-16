"""One height contract for both CAD warehouse styles; meshes stay immutable."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / 'SourceAssets/GHS/wall_height_profile.json'
PROFILE = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
WALLS = tuple(PROFILE['wall_groups'])


def row_for(label):
    assert label in WALLS, label
    source, target = PROFILE['source_wall_height_m'], PROFILE['wall_height_m']
    return dict(position_m=[0, 0, target-source if label.endswith('Edges') else 0],
                rotation_deg=0, scale=[1, 1, 1 if label.endswith('Edges') else target/source])


def synchronize_registry(registry):
    groups = {g['actor']: g for g in registry['groups']}
    for label in WALLS:
        group = groups[label]
        assert group['count'] == len(group['instances']) == 1, label
        group['instances'][0].update(row_for(label))
    registry['wall_height_profile'] = copy.deepcopy(PROFILE)
    if 'presentation' in registry:
        presentation = registry['presentation']
        presentation['wall_height_m'] = PROFILE['wall_height_m']
        for label in WALLS:
            if label not in presentation['modified_labels']:
                presentation['modified_labels'].append(label)
    return registry


def projected_geometry(geometry):
    """Project the immutable Blender local geometry into the current scene."""
    result = copy.deepcopy(geometry)
    for label in WALLS:
        name = {'GHS_CAD_WallFaces':'SM_GHS_JoinedWallFaces',
                'GHS_CAD_WallSections':'SM_GHS_JoinedWallSections',
                'GHS_CAD_WallEdges':'SM_GHS_JoinedWallEdges'}[label]
        row = row_for(label)
        mesh = result['meshes'][name]
        for field in ('vertices', 'verts'):
            if field in mesh:
                mesh[field] = [[x, y, z*row['scale'][2]+row['position_m'][2]] for x,y,z in mesh[field]]
    result['verification']['wall_height_m'] = PROFILE['wall_height_m']
    result['verification']['edge_z_m'] = PROFILE['wall_height_m']+PROFILE['edge_offset_m']
    return result
