import copy
import unittest

from storage_capacity_import_validation import configure_capacity_component, validate_lod_layout


class CapacityImportValidation(unittest.TestCase):
    def setUp(self):
        self.roles = ['Upright', 'Beam', 'Braces', 'Pallet', 'Cargo', 'CargoEdges', 'Detail']
        # Captured UE 5.4 render sections: reduction removes the tiny tapes/labels.
        counts = [[144,176,528,1224,4048,368,656], [144,48,496,1224,1466,368,184],
                  [112,48,272,608,1104], [50,48,12,72,1104]]
        self.lods = [dict(lod=i, triangles=sum(row), section_rows=[
            dict(material_index=j, triangle_count=n) for j,n in enumerate(row)]) for i,row in enumerate(counts)]

    def test_reduced_optional_details_keep_semantic_material_mapping(self):
        validate_lod_layout(self.lods, self.roles, 7144)

    def test_missing_core_cargo_or_steel_is_rejected(self):
        for role in range(5):
            lods = copy.deepcopy(self.lods)
            lods[2]['section_rows'] = [s for s in lods[2]['section_rows'] if s['material_index'] != role]
            with self.subTest(role=role), self.assertRaises(AssertionError):
                validate_lod_layout(lods, self.roles, 7144)

    def test_wrong_or_duplicate_material_mapping_is_rejected(self):
        for replacement in [0, 7, -1]:
            lods = copy.deepcopy(self.lods)
            lods[1]['section_rows'][4]['material_index'] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(AssertionError):
                validate_lod_layout(lods, self.roles, 7144)

    def test_incomplete_full_mesh_is_rejected(self):
        with self.assertRaises(AssertionError):
            validate_lod_layout(self.lods, self.roles, 5136)
        self.lods[0]['section_rows'].pop()
        with self.assertRaises(AssertionError):
            validate_lod_layout(self.lods, self.roles, 7144)

    def test_editor_notifications_reconstruct_components_before_custom_data_writes(self):
        class Component:
            def __init__(self, owner, properties=None):
                self.owner, self.properties = owner, dict(properties or {})
                self.floats, self.data, self.materials = 0, [], {}
                self.mesh = None
            def set_editor_property(self, key, value):
                self.properties[key] = value
                self.owner.current = Component(self.owner, self.properties)
            def get_editor_property(self, key):
                return self.floats if key == 'num_custom_data_floats' else self.data
            def get_instance_count(self):
                return 3 if self.owner.current is self else 0
            def set_static_mesh(self, mesh): self.mesh = mesh
            def set_material(self, index, material): self.materials[index] = material
            def set_num_custom_data_floats(self, count):
                self.floats, self.data = count, [0.] * (self.get_instance_count() * count)
            def set_custom_data_value(self, index, slot, value, mark_render_state_dirty=False):
                if self.get_instance_count() == 0: return False
                self.data[index * self.floats + slot] = value
                return True
        class Owner: pass
        owner = Owner()
        owner.current = Component(owner)
        stale = owner.current
        properties = dict(component_tags=['owned'], cast_static_shadow=False, affect_distance_field_lighting=False)
        current = configure_capacity_component(lambda: owner.current, 'full-mesh', ['steel', 'mask'], properties, [10.,16.,22.])
        self.assertIs(current, owner.current)
        self.assertIsNot(current, stale)
        self.assertEqual(current.properties, properties)
        self.assertEqual(current.data, [10.,16.,22.])
        self.assertEqual(current.mesh, 'full-mesh')
        self.assertEqual(current.materials, {0:'steel', 1:'mask'})


if __name__ == '__main__':
    unittest.main()
