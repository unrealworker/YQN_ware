"""Archive native MPR measurements without promoting failed runs to success.

--check-inputs validates completed timing/LOD/tests and reports workflow readiness.
--finalize requires successful full workflow and independent cart-cache regressions.
--verify reads only the archive and rechecks bytes and native CSV measurements.
No UE connection, scene write, source-report rewrite or Git operation is performed.
"""
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import struct

ROOT = Path(__file__).resolve().parents[2]
CACHE = "Saved/MPR/optimization_20261112"
OUT = ROOT / "SourceAssets/MPR/optimization_20261112"
MAP = "/Game/Maps/MPR_CAD_Warehouse_B50B57"
INPUTS = {
    "before": f"{CACHE}/runtime/before/20261112T111433Z/report.json",
    "after": f"{CACHE}/runtime/after/20261112T121131Z/report.json",
    "lod": f"{CACHE}/runtime/after/20261112T122126Z/report.json",
    "automation": f"{CACHE}/automation_verified/index.json",
    "rack_apply": f"{CACHE}/rack_clearance/validation.json",
    "rack_reload": f"{CACHE}/rack_clearance/reload_validation.json",
    "sorter": f"{CACHE}/optimized_sorter_runtime/report.json",
    "cart_cache": f"{CACHE}/cart_cache_runtime/report.json",
    "worker_policy": "SourceAssets/MPR/sorter_simulation/worker_presentation_policy.json",
}
VIEWS = ("overview", "rack-close", "sorter")
METRICS = ("FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime")
CART_CACHE_CHECKS = {
    "cart_cache_reset_republishes_96_once_and_120_stationary_updates_submit_nothing",
    "cart_submissions_match_changed_poses_through_both_complete_exchange_profiles",
    "cad64_full_outbound_handoff_empty_arrival_docking_and_receiving_recovery",
    "cad120_full_outbound_handoff_empty_arrival_docking_and_receiving_recovery",
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(raw):
    return json.loads(raw.decode("utf-8-sig"))


def source_relative(path):
    value = str(path).replace("\\", "/")
    # Original native reports retain absolute paths verbatim. This translation
    # also permits --verify after the committed archive is cloned elsewhere.
    for prefix in (ROOT.as_posix().rstrip("/") + "/", "D:/UEPro/Test/"):
        if value.lower().startswith(prefix.lower()):
            value = value[len(prefix):]
            break
    require(value.startswith("Saved/") and ".." not in Path(value).parts,
            "Evidence path is outside Saved: " + value)
    return value


def native_csv(raw):
    """Independently recompute all reported native timing statistics."""
    require(b"[HasHeaderRowAtEnd],1" in raw[-32768:], "CSV was not finalized")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    headers = [i for i, row in enumerate(rows) if row and row[0] == "EVENTS"]
    require(1 <= len(headers) <= 2, "CSV header count is invalid")
    initial, names = rows[headers[0]], rows[headers[-1]]
    require(initial == names[:len(initial)], "CSV headers are not append-only")
    frames = rows[headers[0] + 1 if len(headers) > 1 else 0:headers[-1]]
    require(len(frames) >= 50, "CSV has too few native frames")
    width = len(initial)
    for row in frames:
        require(width <= len(row) <= len(names), "CSV frame is truncated")
        width = len(row)
    result = {}
    values = {}
    for name in METRICS:
        require(initial.count(name) == 1, "Missing or ambiguous timing: " + name)
        col = names.index(name)
        seq = [float(row[col]) for row in frames]
        require(all(math.isfinite(x) and x >= 0 for x in seq), "Invalid timing")
        values[name] = seq
        ordered = sorted(seq)
        result[name] = dict(count=len(seq), mean_ms=statistics.fmean(ordered),
                            median_ms=statistics.median(ordered),
                            p95_ms=ordered[math.ceil(len(seq) * .95) - 1],
                            p99_ms=ordered[math.ceil(len(seq) * .99) - 1],
                            max_ms=ordered[-1],
                            over_16_67ms_count=sum(x > 1000 / 60 for x in seq),
                            over_33_33ms_count=sum(x > 1000 / 30 for x in seq),
                            over_50ms_count=sum(x > 50 for x in seq))
    gpu_passes = [i for i, name in enumerate(names)
                  if name.startswith("GPU/") and name not in ("GPU/Total", "GPU/Unaccounted")]
    require(gpu_passes, "No actual GPU pass timestamps")
    require(sum(x > 0 for x in values["GPUTime"]) / len(frames) >= .95,
            "GPUTime lacks positive samples")
    require(sum(any(i < len(row) and float(row[i]) > 0 for i in gpu_passes)
                for row in frames) / len(frames) >= .95, "GPU pass timings lack evidence")
    seconds = sum(values["FrameTime"]) / 1000
    require(seconds >= 10, "Native capture is too short")
    return dict(frame_count=len(frames), native_frame_time_seconds=seconds,
                fps=len(frames) / seconds, metrics=result)


def match_record(raw, record):
    require(sha(raw) == record["sha256"], "Native CSV SHA-256 changed")
    measured = native_csv(raw)
    require(record.get("gpu_verified") is True, "Native report did not verify GPU timings")
    for key in ("frame_count", "native_frame_time_seconds", "fps"):
        require(math.isclose(measured[key], record[key], rel_tol=1e-11, abs_tol=1e-9),
                "Native statistic differs: " + key)
    for name in METRICS:
        for key, value in measured["metrics"][name].items():
            require(math.isclose(value, record["metrics"][name][key], rel_tol=1e-11, abs_tol=1e-9),
                    "Native timing differs: " + name + "/" + key)
    return measured


def inspect(reader, final=False):
    reports = {}
    for key, path in INPUTS.items():
        try:
            reports[key] = read_json(reader(path))
        except FileNotFoundError:
            require(not final and key in ("sorter", "cart_cache"), "Missing required evidence: " + path)
            reports[key] = dict(success=False, stage="not_started")
    policy = reports["worker_policy"]
    require(policy["source_worker_count"] == 256
            and policy["expected_counts"]["omitted_cad_workers"] == 249
            and policy["expected_counts"]["runtime_worker_slots"] == 29
            and policy["expected_counts"]["idle_visible_workers"] == 7
            and policy["expected_counts"]["maximum_visible_workers"] == 8,
            "Worker presentation policy differs from the approved scope")
    before, after, lod, automation = (reports[k] for k in ("before", "after", "lod", "automation"))
    require(before["success"] is True and before.get("map_unchanged") is True, "Baseline incomplete")
    # The three timing samples completed before this historical LOD assertion.
    # Preserve the failed report as failed, including its complete traceback.
    require(after["success"] is False and after.get("stage") == "lod_far"
            and "AssertionError: far" in after.get("error", "")
            and "baseline_revisions" in after["error"], "Unexpected after-run failure")
    require(after.get("map_unchanged") is True, "After measurement changed the map")
    require(before["resolution"] == after["resolution"] == [1920, 1080], "Resolution mismatch")
    require(before["views"] == after["views"], "Fixed view specifications differ")
    require(lod["success"] is True and lod.get("map_unchanged") is True
            and lod["lod_diagnostics"]["success"] is True, "Independent LOD validation incomplete")
    for key in ("simulation_time_unchanged", "non_feed_pose_revisions_unchanged",
                "six_feed_native_bone_root_and_palm_poses_unchanged",
                "tested_far_near_far", "tested_offscreen_reentry"):
        require(lod["lod_diagnostics"].get(key) is True, "LOD check missing: " + key)
    require(automation["succeeded"] == 33 and automation["failed"] == 0
            and automation["notRun"] == 0 and automation["inProcess"] == 0, "33 tests have not all passed")
    applied, reloaded = reports["rack_apply"], reports["rack_reload"]
    require(applied["success"] is True and reloaded["success"] is True, "Map change lacks validation")
    require(applied["before_map_sha256"] == before["map_sha256"]
            and applied["map_sha256"] == after["map_sha256"] == lod["map_sha256"] == reloaded["map_sha256"],
            "Map hashes do not match the audited rack relocation")
    comparisons = []
    csv_records = []
    for phase in ("before", "after"):
        report = reports[phase]
        formal = [x for x in report["samples"] if not x["diagnostic_only"]]
        require([x["name"] for x in formal] == list(VIEWS), "Missing formal views")
        for sample in report["samples"]:
            native = sample["native_csv"]
            record = match_record(reader(source_relative(native["path"])), native)
            csv_records.append(dict(source_path=source_relative(native["path"]),
                                    phase=phase, view=sample["name"],
                                    diagnostic_only=sample["diagnostic_only"], **record))
        for sample in formal:
            total, visible = (278, 256) if phase == "before" else (29, 7)
            for key in ("workers_before", "workers_after"):
                require(sample[key]["total"] == total and sample[key]["visible"] == visible,
                        "Worker count changed during native sample")
    for name in VIEWS:
        a = next(s for s in before["samples"] if s["name"] == name)
        b = next(s for s in after["samples"] if s["name"] == name)
        require(len(a["camera"]) == len(b["camera"]) == 6
                and all(abs(x - y) < 1e-6 for x, y in zip(a["camera"], b["camera"])), "Actual camera mismatch")
        comparisons.append(dict(view=name, camera=a["camera"],
                                before={k: a["native_csv"][k] for k in ("fps", "metrics", "frame_count")},
                                after={k: b["native_csv"][k] for k in ("fps", "metrics", "frame_count")},
                                fps_change_percent=100 * (b["native_csv"]["fps"] / a["native_csv"]["fps"] - 1)))
    sorter = reports["sorter"]
    complete = sorter.get("success") is True and all(x.get("passed") is True for x in sorter.get("checks", []))
    cache = reports["cart_cache"]
    cache_complete = cache.get("success") is True and all(x.get("passed") is True for x in cache.get("checks", []))
    if final:
        require(complete and len(sorter.get("preserved_check_names", [])) == 16,
                "Final sorter workflow is not complete: " + str(sorter.get("stage")))
        require(set(sorter["preserved_check_names"]) <= {x["name"] for x in sorter["checks"]},
                "An original workflow check was dropped")
        require(sorter.get("validation_mode") == "full_workflow"
                and "only_sorter_workers_retained_with_exact_source_handles_and_roles" in {x["name"] for x in sorter["checks"]},
                "Full workflow/personnel regression checks are missing")
        require(sorter["map_sha256"] == after["map_sha256"] and sorter["resolution"] == [1920, 1080]
                and sorter["assets_saved"] is False, "Sorter validation scope mismatch")
        native = sorter["performance"]["native_csv"]
        measured = match_record(reader(source_relative(native["path"])), native)
        csv_records.append(dict(source_path=source_relative(native["path"]), phase="workflow",
                                view="workflow_camera_not_comparable_to_three_views", diagnostic_only=False, **measured))
        require(cache_complete and cache.get("validation_mode") == "cart_cache"
                and CART_CACHE_CHECKS <= {x["name"] for x in cache.get("checks", [])},
                "Independent cart-cache regression is not complete: " + str(cache.get("stage")))
        require(cache.get("map_sha256") == after["map_sha256"] and cache.get("resolution") == [1920, 1080]
                and cache.get("assets_saved") is False, "Cart-cache validation scope mismatch")
    return reports, dict(map=MAP, resolution=[1920, 1080],
                         map_sha256_before=before["map_sha256"], map_sha256_after=after["map_sha256"],
                         formal_timing_samples_valid=True, after_report_success_preserved=False,
                         historical_failure="121131Z: outdated feed pose revision assertion failed after all three timing samples completed",
                         independent_lod_validation_passed=True, automation_passed=33,
                         worker_policy=policy,
                         sorter_workflow_complete=complete, sorter_stage=sorter.get("stage"),
                         cart_cache_complete=cache_complete, cart_cache_stage=cache.get("stage"),
                         comparisons=comparisons, native_csv=csv_records,
                         attribution="Combined change: 249 CAD staff omitted, normal display LOD, changed-cart-only submissions, and audited rack relocation. No isolated per-change gain is claimed.",
                         limitations=["One local native UE game run per view; no repetitions or statistical confidence interval.",
                                      "No Pixel Streaming, network, multi-user, GPU-triangle or manufacturer-throughput claim.",
                                      "Before and after map hashes differ because 91 rack rows / 2392 instances moved; same camera and resolution do not isolate code changes.",
                                      "Historical diagnostic-only hidden-skeleton sample is archived but excluded from formal comparisons."])


def markdown(summary):
    rows = []
    labels = {"overview": "全仓俯视", "rack-close": "货架近景", "sorter": "播种区"}
    for row in summary["comparisons"]:
        a, b = row["before"], row["after"]
        rows.append(f"| {labels[row['view']]} | {a['fps']:.2f} → {b['fps']:.2f} | "
                    f"{a['metrics']['GPUTime']['mean_ms']:.2f} → {b['metrics']['GPUTime']['mean_ms']:.2f} | "
                    f"{a['metrics']['FrameTime']['p95_ms']:.2f} → {b['metrics']['FrameTime']['p95_ms']:.2f} |")
    return "\n".join([
        "# MPR 人员范围与运行性能验收", "",
        "已完成原生验证和归档。沿用原关卡 `/Game/Maps/MPR_CAD_Warehouse_B50B57`，没有新建关卡。", "",
        "运行时取消生成 249 名播种区外 CAD 人员，保留六名投料人员和 `2CCF61` 端台人员。22 个整车更换人员槽位按原流程出现：共 29 个组件，常态 7 人、换车时最多 8 人；完整 256 人 CAD 来源不删改。", "",
        "代码仅补回正常显示 LOD 的更新，并避免对不动的料框车重复提交 Transform/渲染脏标记。保留官方 Manny 网格、材质、动作骨骼计算、固定步长调度、连续环线和货物归属。", "",
        "以下是人员删减、LOD、提交缓存以及同轮货架侧移后的合计实测，不能把全部增益归因于代码优化。每个固定镜头预热 10 秒、原生 CSV 采样约 15 秒，1920×1080；统计保留全部边界帧和峰值。", "",
        "| 固定镜头 | 平均 FPS（前 → 后） | GPU 平均 ms（前 → 后） | 帧时间 P95 ms（前 → 后） |",
        "| --- | ---: | ---: | ---: |", *rows, "",
        "`manifest.json` 包含实际相机位置/角度、每项原生统计、原字节 SHA-256、gzip SHA-256 与归档路径。CSV 的均值、中位数、P95/P99、峰值、超预算帧数及 FPS 均在归档时独立重算；GPU 使用 UE RHI 的 `GPUTime` 和正值 GPU pass 时间戳。", "",
        "## 验证状态与失败记录", "",
        "- 自动化 33/33 通过；独立原生 LOD 远 → 近 → 远及出屏返回验证通过，固定端台姿势与六位投料人员骨骼/根变换/手掌位置保持。",
        "- `after/20261112T121131Z` 的报告原样保留 `success=false`。三个正式性能采样已完成，其后旧诊断把投料姿势重复提交计数误当成位移变化，触发 `AssertionError: far`。这些 CSV 通过完整性、哈希、相机、分辨率和原生时间戳复核，不能把该整轮报告说成成功。",
        "- 独立修正后的 `after/20261112T122126Z` LOD 诊断 `success=true`，没有覆盖前述失败报告。",
        "- 完整 sorter 工作流与独立料框车缓存诊断分别成功后才允许 `--finalize`。前者保留原 16 项流程及人员筛选检查，后者检查复位时 96 车重新提交、120 次静止更新零提交，以及两类整车更换各阶段的实际提交与姿态一致。两进程避免嵌入 Python 额外大报告读回干扰，覆盖范围不减少。工作流自身的性能镜头不同，不与上表三镜头混用。", "",
        "## 场景身份与比较边界", "",
        f"优化前地图 SHA-256：`{summary['map_sha256_before']}`。", "",
        f"优化后地图 SHA-256：`{summary['map_sha256_after']}`。", "",
        "哈希差异来自已独立验证的 91 列 / 2392 个货架实例侧移；原材质、网格、LOD/culling、设备、仿真配置和镜头配置由货架修改白名单保护。两次实测的实际相机与分辨率一致，但不是只改变一项因素的实验。", "",
        "这里只证明本机单次原生运行结果，不代表 Pixel Streaming、多用户并发、网络延迟或厂家吞吐指标。", "",
        "## 归档与复核", "",
        "`evidence/*.gz` 保存必要报告和 CSV 原字节，`previews/` 保存少量原始 PNG。报告中的其他 Saved 图片/状态文件路径是采样时来源，不表示全部已归档；以 manifest 的 evidence 清单为准。不含地图备份、构建产物或大体积全场景扫描。", "",
        "```powershell", "python Tools/MPRWarehouse/archive_mpr_optimization_20261112.py --verify", "```", "",
        "重新归档前先运行 `--check-inputs`，完整工作流结束后运行 `--finalize`。未成功、尚在运行或缺失必要输入时拒绝最终归档；已有归档原字节发生冲突也拒绝覆盖。", "",
        "![播种区优化后](previews/sorter-after.png)", "", "![现有模型近景与正常 LOD](previews/worker-near.png)", "",
    ])


def finalize():
    gathered = {}
    def reader(relative):
        raw = (ROOT / relative).read_bytes()
        if relative in gathered:
            require(gathered[relative] == raw, "Evidence changed during archive: " + relative)
        gathered[relative] = raw
        return raw
    reports, summary = inspect(reader, final=True)
    # Keep the previous test failure as provenance, not as final acceptance.
    reader(f"{CACHE}/automation_final/index.json")
    images = {}
    for phase, name, output in (("before", "sorter", "sorter-before.png"),
                                ("after", "sorter", "sorter-after.png"),
                                ("after", "rack-close", "rack-close-after.png")):
        record = next(c for c in reports[phase]["captures"] if c["name"] == name)
        path = source_relative(record["path"])
        raw = reader(path)
        require(sha(raw) == record["sha256"], "Capture SHA-256 changed")
        images[path] = "previews/" + output
    near = next(s for s in reports["lod"]["lod_diagnostics"]["stages"] if s["name"] == "near")
    path = source_relative(near["capture"])
    reader(path)
    images[path] = "previews/worker-near.png"
    evidence = []
    for source, raw in gathered.items():
        if source in images:
            require(raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (1920, 1080), "PNG resolution mismatch")
            relative, stored = images[source], raw
            encoding = "original"
        else:
            relative = "evidence/" + source.replace("/", "__") + ".gz"
            stored = gzip.compress(raw, compresslevel=9, mtime=0)
            require(gzip.decompress(stored) == raw, "gzip roundtrip failed")
            encoding = "gzip"
        target = OUT / relative
        if target.exists():
            require(target.read_bytes() == stored, "Refusing to overwrite different archived bytes: " + relative)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(stored)
        evidence.append(dict(source_path=source, archive_path=relative, encoding=encoding,
                             raw_sha256=sha(raw), raw_bytes=len(raw), archive_sha256=sha(stored), archive_bytes=len(stored)))
    manifest = dict(schema_version=1, status="complete", input_reports=INPUTS, **summary, evidence=evidence)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    (OUT / "README.md").write_text(markdown(summary), encoding="utf8", newline="\n")
    return verify()


def verify():
    manifest = read_json((OUT / "manifest.json").read_bytes())
    require(manifest["status"] == "complete" and manifest["input_reports"] == INPUTS, "Wrong archive schema/inputs")
    raw_files = {}
    for record in manifest["evidence"]:
        target = (OUT / record["archive_path"]).resolve()
        require(target.is_relative_to(OUT.resolve()), "Archive path escape")
        stored = target.read_bytes()
        require(len(stored) == record["archive_bytes"] and sha(stored) == record["archive_sha256"], "Archive bytes changed")
        raw = gzip.decompress(stored) if record["encoding"] == "gzip" else stored
        require(len(raw) == record["raw_bytes"] and sha(raw) == record["raw_sha256"], "Original evidence bytes changed")
        require(record["source_path"] not in raw_files, "Duplicate archive source")
        raw_files[record["source_path"]] = raw
    _, summary = inspect(lambda relative: raw_files[relative], final=True)
    require(all(manifest[key] == value for key, value in summary.items()), "Summary differs from archived evidence")
    return dict(verified=True, archived_files=len(raw_files), formal_samples=6,
                sorter_workflow_complete=True, archived_bytes=sum(r["archive_bytes"] for r in manifest["evidence"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-inputs", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.check_inputs:
        _, summary = inspect(lambda relative: (ROOT / relative).read_bytes())
        result = {key: value for key, value in summary.items() if key not in ("comparisons", "native_csv", "limitations", "worker_policy")}
    else:
        result = finalize() if args.finalize else verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
