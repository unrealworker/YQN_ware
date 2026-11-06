"""Verified CAD symbol semantics and signed planar transform contracts.

Evidence: original MPR all-in-one DXF, reviewed 2026-11-06. A personnel
silhouette or flow arrow is drafting evidence, never conveyor geometry.
"""
import math

DRAFTING_SYMBOLS = {
    'terwrq434': ('personnel_position', 'Top-view person silhouette; 185 short outline lines, not a chute'),
    '*U257': ('flow_direction', 'Two-polyline flow arrow, not a structural support'),
    '*U1667': ('flow_direction', 'Two-polyline bidirectional flow arrow, not a structural support'),
}
DRIVE_DETAIL_BLOCKS = {'*U1656', '*U258', '*U259'}


def covered_drive_detail(placement, straight_runs):
    """Recognize a drive drawing over an already modeled continuous carrier.

    The source envelope includes an offset motor. Its full width is not a second
    conveyor. Only merge when its complete longitudinal span is already present.
    """
    if placement['block'] not in DRIVE_DETAIL_BLOCKS:
        return None
    def axis_record(row):
        width, length = row['size_m'];yaw = row['rotation_deg']
        if width > length:
            width, length, yaw = length, width, yaw-90
        a = math.radians(yaw)
        return width,length,yaw,(-math.sin(a),math.cos(a)),(math.cos(a),math.sin(a))
    width,length,yaw,axis,normal = axis_record(placement)
    half=length/2;intervals=[];references=[]
    for run in straight_runs:
        run_width,run_length,run_yaw,_,_ = axis_record(run)
        if abs(math.sin(math.radians(run_yaw-yaw)))>.0001:
            continue
        delta=[run['position_m'][k]-placement['position_m'][k] for k in (0,1)]
        along=sum(delta[k]*axis[k] for k in (0,1));cross=sum(delta[k]*normal[k] for k in (0,1))
        if abs(cross)>min(.2,run_width/2):
            continue
        lo=max(-half,along-run_length/2);hi=min(half,along+run_length/2)
        if hi>lo:
            intervals.append((lo,hi));references.append(dict(source_handles=run['source_handles'],width_m=run_width,cross_offset_m=cross,overlap_interval_m=[lo,hi]))
    end=-half;covered=0
    for lo,hi in sorted(intervals):
        covered+=max(0,hi-max(end,lo));end=max(end,hi)
    if covered<length-0.00002:
        return None
    return dict(source_handles=placement['source_handles'],block=placement['block'],position_m=placement['position_m'],
                size_m=placement['size_m'],rotation_deg=placement['rotation_deg'],longitudinal_covered_m=covered,
                mainline_sources=references,reason='CAD drive detail overlaps an existing continuous mainline; do not create a second full-width roller deck')


def planar_handedness(a, b):
    """Keep reflection separately from the yaw derived from the X basis."""
    determinant = a[0] * b[1] - a[1] * b[0]
    if not math.isfinite(determinant) or abs(determinant) < 1e-15:
        raise ValueError('Degenerate CAD planar basis')
    return -1 if determinant < 0 else 1


def turn_requires_reflection(reference, placement):
    """A turn mesh is baked in the first measured placement's handedness."""
    return reference.get('planar_handedness', 1) != placement.get('planar_handedness', 1)


def reflected_mesh_roles(roles):
    """Reflect local Y and reverse winding so positive-scale instances render correctly.

    CAD extraction already absorbs the sign of the X basis into its yaw.
    The remaining difference between opposite planar handedness is local Y.
    """
    return {
        role: [[(x, -y, z) for x, y, z in vertices],
               [tuple(reversed(face)) for face in faces]]
        for role, (vertices, faces) in roles.items()
    }
