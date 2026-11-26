"""Validate a GHS CSV export and build a static, sharded inventory snapshot.

No CAD correspondence is inferred here. Empty inventory and an unmapped scene
target are deliberately separate concepts. This importer uses only the stdlib.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile


DEFAULT_INPUT = Path("D:/Data/仓库数据/GHS/ghs_ca_us_ue5_location_inventory_detail_20261125.csv")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "Content/GHSTwinUI/data/inventory"
DEFAULT_EXPORTED_AT = "2026-11-25 14:00:46 UTC+08:00"
HEADERS = "warehouse_id,warehouse_code,location_id,location_code,location_name,warehouse_area_id,location_type,location_status,usage_model,location_row,location_col,location_layer,horizontal_num,passage,double_shelves_position,x_axis,y_axis,z_axis,location_length_m,location_width_m,location_height_m,maximum_tray_num,maximum_volume_cbm,inventory_item_id,sku,quantity,available_quantity,allocation_quantity,freeze_quantity,wait_move_in_quantity,wait_move_out_quantity,inventory_updated_at_utc8,location_updated_at,location_etl_at,scene_mapping_status,ue_scene_target_id,ue_cad_instance_id,ue_slot_level,ue_slot_column".split(",")
QUANTITIES = {
    "quantity": "quantity", "available_quantity": "availableQuantity",
    "allocation_quantity": "allocationQuantity", "freeze_quantity": "freezeQuantity",
    "wait_move_in_quantity": "waitMoveInQuantity", "wait_move_out_quantity": "waitMoveOutQuantity",
}
ITEM_FIELDS = {"inventory_item_id", "sku", "inventory_updated_at_utc8", *QUANTITIES}
METADATA_FIELDS = [field for field in HEADERS if field not in ITEM_FIELDS]
MAX_SAFE_INTEGER = 9007199254740991
SHARD_COUNT = 128


def nullable(value):
    return None if value == "" else value


def identity(value, field, line):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value) or int(value) <= 0:
        raise ValueError(f"Line {line}: invalid {field}")
    return value


def integer(value, field, line):
    if value == "":
        return None
    if not re.fullmatch(r"-?[0-9]+", value):
        raise ValueError(f"Line {line}: invalid integer {field}: {value!r}")
    result = int(value)
    if abs(result) > MAX_SAFE_INTEGER:
        raise ValueError(f"Line {line}: {field} exceeds safe JSON integer precision")
    return result


def timestamp(value, field, line):
    if value == "":
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Line {line}: invalid {field}: {value!r}") from error
    return value


def latest(values):
    known = [v for v in values if v is not None]
    return max(known, key=datetime.fromisoformat) if known else None


def known_sum(values):
    values = list(values)
    if any(value is None for value in values):
        return None
    result = sum(values)
    if abs(result) > MAX_SAFE_INTEGER:
        raise ValueError("Aggregate exceeds safe JSON integer precision")
    return result


def validate_metadata(raw, line):
    for field in ("x_axis", "y_axis", "z_axis", "location_length_m", "location_width_m",
                  "location_height_m", "maximum_volume_cbm"):
        if raw[field] == "":
            continue
        try:
            number = Decimal(raw[field])
        except InvalidOperation as error:
            raise ValueError(f"Line {line}: invalid {field}") from error
        if not number.is_finite():
            raise ValueError(f"Line {line}: non-finite {field}")
        if field not in ("x_axis", "y_axis", "z_axis") and number < 0:
            raise ValueError(f"Line {line}: negative dimension {field}")
    integer(raw["maximum_tray_num"], "maximum_tray_num", line)
    for field in ("location_updated_at", "location_etl_at"):
        timestamp(raw[field], field, line)


def build_snapshot(source_path, *, exported_at=DEFAULT_EXPORTED_AT):
    source_path = Path(source_path)
    raw_bytes = source_path.read_bytes()
    snapshot_id = hashlib.sha256(raw_bytes).hexdigest()
    reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig"), newline=""), strict=True)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames) != set(HEADERS):
        raise ValueError("CSV requires exactly the 39 documented unique headers")
    groups, codes, inventory_ids, no_record_ids = {}, {}, set(), set()
    for line, raw in enumerate(reader, 2):
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f"Line {line}: CSV column count differs from header")
        if raw["warehouse_id"] != "108" or raw["warehouse_code"] != "GHS_CA_US":
            raise ValueError(f"Line {line}: wrong or mixed warehouse")
        location_id = identity(raw["location_id"], "location_id", line)
        code = raw["location_code"]
        if not code or code != code.strip():
            raise ValueError(f"Line {line}: blank or padded location code")
        if code in codes and codes[code] != location_id:
            raise ValueError(f"Line {line}: duplicate location code with different ID: {code}")
        codes[code] = location_id
        validate_metadata(raw, line)
        metadata = {field: nullable(raw[field]) for field in METADATA_FIELDS}
        if location_id in groups and groups[location_id]["fields"] != metadata:
            raise ValueError(f"Line {line}: conflicting location metadata: {location_id}")
        group = groups.setdefault(location_id, {"id": location_id, "code": code,
                                  "warehouseId": "108", "warehouseCode": "GHS_CA_US",
                                  "fields": metadata, "items": []})
        item_id = raw["inventory_item_id"]
        if item_id == "":
            if any(raw[field] != "" for field in ITEM_FIELDS) or group["items"] or location_id in no_record_ids:
                raise ValueError(f"Line {line}: duplicate, mixed or orphan inventory join")
            no_record_ids.add(location_id)
            continue
        identity(item_id, "inventory_item_id", line)
        if item_id in inventory_ids:
            raise ValueError(f"Line {line}: duplicate inventory ID: {item_id}")
        if location_id in no_record_ids:
            raise ValueError(f"Line {line}: mixed no-record and inventory rows")
        if raw["sku"] == "" or raw["sku"] != raw["sku"].strip():
            raise ValueError(f"Line {line}: blank or padded SKU")
        inventory_ids.add(item_id)
        item = {"id": item_id, "sku": raw["sku"], "updatedAt": timestamp(raw["inventory_updated_at_utc8"], "inventory_updated_at_utc8", line)}
        item.update({target: integer(raw[field], field, line) for field, target in QUANTITIES.items()})
        group["items"].append(item)
    if not groups:
        raise ValueError("CSV contains no warehouse locations")

    locations, all_skus = [], set()
    shards = [{"schemaVersion": 1, "snapshotId": snapshot_id, "locations": {}} for _ in range(SHARD_COUNT)]
    for location_id in sorted(groups, key=lambda key: (int(key), key)):
        group = groups[location_id]
        items = group["items"]
        items.sort(key=lambda item: (int(item["id"]), item["id"]))
        quantities = [item["quantity"] for item in items]
        if any(value is None or value < 0 for value in quantities):
            state, empty_reason = "unknown", None
        elif any(value > 0 for value in quantities):
            state, empty_reason = "occupied", None
        else:
            state, empty_reason = "empty", "zero_quantity" if items else "no_inventory_record"
        totals = {field: known_sum(item[field] for item in items) for field in QUANTITIES.values()}
        skus = {item["sku"] for item in items}
        all_skus.update(skus)
        group.update(state=state, emptyReason=empty_reason, totals=totals, skuCount=len(skus),
                     recordCount=len(items), updatedAtMax=latest(item["updatedAt"] for item in items))
        shard_index = int(location_id) % SHARD_COUNT
        shards[shard_index]["locations"][location_id] = group
        locations.append({"id": location_id, "code": group["code"], "state": state,
                          "quantity": totals["quantity"], "availableQuantity": totals["availableQuantity"],
                          "recordCount": len(items), "skuCount": len(skus), "shard": f"{shard_index:03d}.json"})
    summary = {"locationCount": len(groups), "occupiedCount": sum(g["state"] == "occupied" for g in locations),
               "emptyCount": sum(g["state"] == "empty" for g in locations), "unknownCount": sum(g["state"] == "unknown" for g in locations),
               "recordCount": len(inventory_ids), "skuCount": len(all_skus)}
    summary.update({field: known_sum(g["totals"][field] for g in groups.values()) for field in
                    ("quantity", "availableQuantity", "allocationQuantity", "freezeQuantity")})
    index = {"schemaVersion": 1, "snapshotId": snapshot_id, "warehouseId": "108", "warehouseCode": "GHS_CA_US",
             "source": {"fileName": source_path.name, "sha256": snapshot_id, "exportedAt": exported_at,
                        "inventoryUpdatedAtMax": latest(g["updatedAtMax"] for g in groups.values()), "atomic": False},
             "summary": summary, "locations": locations}
    return index, shards


def write_payload(path, payload, *, script=False, global_name=None):
    """Replace one file atomically; index is published last by the caller."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".inventory-", suffix=".tmp",
                                         encoding="utf-8", newline="\n", delete=False) as handle:
            temporary = Path(handle.name)
            if script:
                # Escape HTML delimiters as well as JS line separators. Data is
                # always strict JSON, never source code assembled from a field.
                encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
                encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
                handle.write((f"window.{global_name}=" + encoded + ";\n") if global_name
                             else ("window.GHSInventoryPayload(" + encoded + ");\n"))
            else:
                handle.write(json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def floor_zone_index(scene_bytes, index, load_shard):
    """Resolve each CAD zone once. Stock stays in the original WMS shard."""
    scene = json.loads(scene_bytes)
    instances, zones, seen = {}, {}, set()
    for group in scene['groups']:
        if not group['mesh'].startswith('SM_GHS_Presentation_Cargo') or group['mesh'].endswith('_Occ70'):
            continue
        for pallet in group['instances']:
            code = pallet.get('zone_code')
            if not code:  # older layouts have no floor-zone identifiers
                continue
            sequence = pallet['sequence']
            if (pallet['id'] in instances or not str(sequence).isdigit() or int(sequence) < 1
                    or (code, int(sequence)) in seen):
                raise ValueError(f'Conflicting CAD floor pallet {code} / {sequence}')
            seen.add((code, int(sequence)))
            instances[pallet['id']] = dict(zoneCode=code, sequence=str(sequence))
            zones.setdefault(code, dict(palletCount=0, locationId=None))['palletCount'] += 1
    if index['warehouseId'] != '108' or index['warehouseCode'] != 'GHS_CA_US':
        raise ValueError('Wrong warehouse for GHS floor zones')
    seen_codes = set()
    for row in index['locations']:
        code = row['code']
        if code not in zones:
            continue
        if code in seen_codes:
            raise ValueError(f'Duplicate WMS floor zone {code}')
        seen_codes.add(code)
        name = row['shard']
        if not re.fullmatch(r'[0-9]{3}\.json', name):
            raise ValueError(f'Invalid shard name {name!r}')
        shard = load_shard(name)
        if shard['snapshotId'] != index['snapshotId']:
            raise ValueError(f'Stale floor zone shard {name}')
        location = shard['locations'][row['id']]
        if ((location['code'], location['id'], location['warehouseId'], location['warehouseCode'])
                != (code, row['id'], '108', 'GHS_CA_US')):
            raise ValueError(f'Conflicting WMS shard identity for {code}')
        if location['fields']['warehouse_area_id'] == '513':
            zones[code]['locationId'] = row['id']
    return dict(schemaVersion=1, snapshotId=index['snapshotId'],
                sourceSceneSha256=hashlib.sha256(scene_bytes).hexdigest(), instances=instances, zones=zones)


def refresh_floor_zones(directory):
    scene = (directory.parent/'scene-bindings.json').read_bytes()
    index = json.loads((directory/'index.json').read_bytes())
    payload = floor_zone_index(scene, index, lambda name: json.loads((directory/name).read_bytes()))
    write_payload(directory/'floor-zones.js', payload, script=True, global_name='GHSFloorZones')
    return payload


def import_inventory(source_path, output_dir, *, exported_at=DEFAULT_EXPORTED_AT):
    # Finish all validation before touching any previous output.
    index, shards = build_snapshot(source_path, exported_at=exported_at)
    output_dir = Path(output_dir)
    scene = output_dir.parent / 'scene-bindings.json'
    floor_zones = (floor_zone_index(scene.read_bytes(), index, lambda name: shards[int(name[:3])])
                  if scene.is_file() else None)
    output_dir.mkdir(parents=True, exist_ok=True)
    for number, shard in enumerate(shards):
        name = f"{number:03d}.json"
        write_payload(output_dir / name, shard)
        write_payload(output_dir / f"{number:03d}.js", {"kind": "shard", "shard": name, **shard}, script=True)
    # Readers must require matching snapshotId before joining index and shard.
    write_payload(output_dir / "index.json", index)
    write_payload(output_dir / "index.js", {"kind": "index", **index}, script=True)
    if floor_zones is not None:
        write_payload(output_dir/'floor-zones.js', floor_zones, script=True, global_name='GHSFloorZones')
    write_payload(output_dir / "summary.js", {key: value for key, value in index.items() if key != "locations"},
                  script=True, global_name='GHSInventorySummary')
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--exported-at", default=DEFAULT_EXPORTED_AT)
    args = parser.parse_args()
    try:
        index = import_inventory(args.input, args.output, exported_at=args.exported_at)
    except (ValueError, UnicodeError, csv.Error, OSError) as error:
        parser.exit(1, f"Inventory import rejected: {error}\n")
    files = [args.output / "index.json", args.output / "index.js", args.output / "summary.js",
             *(args.output / f"{i:03d}.{extension}" for i in range(SHARD_COUNT) for extension in ("json", "js"))]
    if (args.output/'floor-zones.js').is_file():
        files.append(args.output/'floor-zones.js')
    print(json.dumps({"snapshotId": index["snapshotId"], "summary": index["summary"],
                      "files": len(files), "bytes": sum(p.stat().st_size for p in files),
                      "indexBytes": files[0].stat().st_size, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
