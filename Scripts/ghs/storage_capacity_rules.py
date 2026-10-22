"""Deterministic full-slot ordering, also implemented by GHSStorageCapacityComponent.

97 is coprime with both current category counts. All shader intermediates stay
below 2**24, so the integer permutation is exact in float32. No random seed or
instance insertion/removal is involved when a capacity changes.
"""
import math

MULTIPLIER = 97
OFFSET = 17


def clamp_capacity(value, previous):
    return min(1., max(0., value)) if math.isfinite(value) else previous


def slot_rank(slot, count):
    if count <= 0 or slot < 0 or slot >= count:
        return -1
    return (slot * MULTIPLIER + OFFSET) % count


def is_visible(slot, count, capacity):
    rank = slot_rank(slot, count)
    return rank >= 0 and math.isfinite(capacity) and rank < math.floor(min(1., max(0., capacity)) * count + .5)


def slot_boxes(stacks, width, depth):
    return [dict(index=i, level=s['level'], column=s['column'],
                 min_cm=[(s['pallet_center_x_m'] - width / 2) * 100, -depth * 50, s['base_z_m'] * 100],
                 max_cm=[(s['pallet_center_x_m'] + width / 2) * 100, depth * 50, s['stack_top_z_m'] * 100])
            for i, s in enumerate(stacks)]


def find_slot(boxes, point):
    for box in boxes:
        if all(a - .02 <= v <= b + .02 for a, v, b in zip(box['min_cm'], point, box['max_cm'])):
            return box['index']
    return None
