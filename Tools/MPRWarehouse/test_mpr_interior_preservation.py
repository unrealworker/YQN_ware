"""Protection regressions; no Unreal runtime or project asset writes."""
from copy import deepcopy
import unittest
from mpr_interior_preservation import (
    MAP, SCHEMA, NEW_OWNER, PreservationError, classify_actor,
    canonical_digest, assert_preserved, replacement_guids)


def actor(guid, label, folder, components=None, tags=None):
    row = {'guid': guid, 'label': label, 'path': MAP + ':' + label,
           'name': label, 'class': '/Script/Engine.StaticMeshActor',
           'folder': folder, 'tags': tags or ['MPRWarehouse', 'mpr-cad-scene-v1'],
           'transform': [0, 0, 0], 'components': components or []}
    row['classification'] = classify_actor(row)
    return row


def baseline():
    actors = [actor('a', 'MPR_Floor', 'MPR/Architecture'),
              actor('b', 'MPR_Racks_0_0', 'MPR/Storage/Racks',
                    [{'name': 'HISM', 'mesh': '/Game/Shared/Rack.Rack',
                      'materials': ['/Game/Shared/M.M'], 'instance_count': 2,
                      'instance_transforms': [[0, 0, 0], [100, 0, 0]], 'custom_data': []}]),
              actor('c', 'MPR_Exterior_00', 'MPR/Architecture'),
              actor('d', 'UserLight', 'User', tags=['Manual']),
              actor('e', 'MPR_WarehouseCamera', 'MPR/Cameras')]
    return {'schema_version': SCHEMA, 'map': MAP, 'actors': actors,
            'asset_hashes': {'/Game/Shared/M': {'Content/Shared/M.uasset': 'oldhash'}},
            'protected_digest': canonical_digest(actors[:2] + actors[3:4])}


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.before = baseline()
        self.after = deepcopy(self.before)

    def test_identical_snapshot_passes(self):
        self.assertEqual(assert_preserved(self.before, self.after)['protected_actors'], 3)

    def test_recreated_actor_fails_despite_same_visible_state(self):
        self.after['actors'][1]['guid'] = 'replacement'
        with self.assertRaisesRegex(PreservationError, 'disappeared/recreated'):
            assert_preserved(self.before, self.after)

    def test_changed_instance_order_fails_without_count_change(self):
        self.after['actors'][1]['components'][0]['instance_transforms'].reverse()
        with self.assertRaisesRegex(PreservationError, 'components'):
            assert_preserved(self.before, self.after)

    def test_changed_material_fails(self):
        self.after['actors'][1]['components'][0]['materials'] = ['/Game/Other.M']
        with self.assertRaisesRegex(PreservationError, 'components'):
            assert_preserved(self.before, self.after)

    def test_reimport_same_path_fails(self):
        self.after['asset_hashes']['/Game/Shared/M']['Content/Shared/M.uasset'] = 'newhash'
        with self.assertRaisesRegex(PreservationError, 'dependency package'):
            assert_preserved(self.before, self.after)

    def test_exterior_replacement_passes(self):
        self.after['actors'].pop(2)
        self.after['actors'].append(actor('new', 'NewShell', 'MPR/ReferenceV3/Architecture', tags=[NEW_OWNER]))
        self.assertEqual(assert_preserved(self.before, self.after, require_old_exterior_removed=True)['new_exterior_actors'], 1)

    def test_old_exterior_remaining_fails_acceptance(self):
        with self.assertRaisesRegex(PreservationError, 'Old exterior actor remains'):
            assert_preserved(self.before, self.after, require_old_exterior_removed=True)

    def test_unknown_user_actor_is_protected(self):
        self.after['actors'].pop(3)
        with self.assertRaisesRegex(PreservationError, 'UserLight'):
            assert_preserved(self.before, self.after)

    def test_unknown_mesh_in_environment_folder_is_protected(self):
        row = actor('x', 'MPR_UserDecoration', 'MPR/Environment', [{'mesh': '/Game/User/M.M'}])
        self.assertEqual(row['classification'], 'protected_other')

    def test_interior_precedes_exterior_tag(self):
        row = actor('x', 'MPR_Floor', 'MPR/ReferenceV3/Architecture', tags=[NEW_OWNER])
        self.assertEqual(row['classification'], 'interior')

    def test_camera_framing_can_change_but_identity_cannot(self):
        self.after['actors'][4]['transform'] = [100, 50, 20]
        assert_preserved(self.before, self.after)
        self.after['actors'][4]['guid'] = 'newcamera'
        with self.assertRaisesRegex(PreservationError, 'camera identity'):
            assert_preserved(self.before, self.after)

    def test_extra_non_exterior_fails(self):
        self.after['actors'].append(actor('new', 'NewRack', 'MPR/Storage/Racks'))
        with self.assertRaisesRegex(PreservationError, 'Unexpected new'):
            assert_preserved(self.before, self.after)

    def test_replacement_list_has_only_baseline_exterior(self):
        self.assertEqual(replacement_guids(self.before), ['c'])

    def test_mutated_transform_and_custom_data_fail(self):
        self.after['actors'][1]['components'][0]['custom_data'] = [1.0]
        self.after['actors'][0]['transform'][0] = .0001
        with self.assertRaisesRegex(PreservationError, 'Protected actor changed'):
            assert_preserved(self.before, self.after)

    def test_v4_requires_matching_owner_and_folder(self):
        row = actor('new', 'V4House', 'MPR/ReferenceV4/Context', tags=['mpr-reference-exterior-v4'])
        self.assertEqual(row['classification'], 'new_exterior')
        for folder, owner in [('MPR/ReferenceV4/Context', NEW_OWNER),
                              ('MPR/ReferenceV3/Context', 'mpr-reference-exterior-v4'),
                              ('MPR/ReferenceV40/Context', 'mpr-reference-exterior-v4')]:
            self.assertEqual(actor('x', 'House', folder, tags=[owner])['classification'], 'protected_other')

    def test_v4_tag_does_not_override_interior_protection(self):
        row = actor('x', 'MPR_Floor', 'MPR/ReferenceV4/Context', tags=['mpr-reference-exterior-v4'])
        self.assertEqual(row['classification'], 'interior')


if __name__ == '__main__':
    unittest.main()
