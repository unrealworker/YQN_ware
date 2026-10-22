"""Semantic checks shared by the UE importer and its captured-geometry regression."""


def configure_capacity_component(get_component, mesh, materials, properties, bases):
    # Each editor property notification can reconstruct a Blueprint's components.
    # Never carry a component reference across such a notification.
    for key, value in properties.items():
        get_component().set_editor_property(key, value)
    component = get_component()
    assert component.get_instance_count() == len(bases), 'Live instance count changed'
    component.set_static_mesh(mesh)
    for index, material in enumerate(materials):
        component.set_material(index, material)
    if component.get_editor_property('num_custom_data_floats') < 1:
        component.set_num_custom_data_floats(1)
    stride = component.get_editor_property('num_custom_data_floats')
    assert stride >= 1
    assert len(component.get_editor_property('per_instance_sm_custom_data')) == len(bases) * stride
    for index, value in enumerate(bases):
        assert component.set_custom_data_value(index, 0, value, mark_render_state_dirty=index == len(bases)-1), ('Custom data write rejected', index, stride)
    assert get_component() == component, 'Unexpected reconstruction during custom data assignment'
    data = component.get_editor_property('per_instance_sm_custom_data')
    assert [data[index*stride] for index in range(len(bases))] == bases
    return component


def validate_lod_layout(lods, slot_roles, full_triangle_count):
    assert slot_roles == ['Upright', 'Beam', 'Braces', 'Pallet', 'Cargo', 'CargoEdges', 'Detail']
    assert len(lods) == 4
    for index, lod in enumerate(lods):
        assert lod['lod'] == index
        sections = lod['section_rows']
        roles = [section['material_index'] for section in sections]
        assert len(set(roles)) == len(roles), ('Duplicate material remap', index, roles)
        assert set(roles).issubset(range(7)), ('Unknown material remap', index, roles)
        assert set(range(5)).issubset(roles), ('Missing steel, pallet or cargo', index, roles)
        assert all(section['triangle_count'] > 0 for section in sections)
        assert sum(section['triangle_count'] for section in sections) == lod['triangles']
        if index == 0:
            assert set(roles) == set(range(7)), 'Full mesh must retain all material roles'
            assert lod['triangles'] == full_triangle_count, 'Full source geometry was lost'
        else:
            assert 0 < lod['triangles'] <= lods[index-1]['triangles']
