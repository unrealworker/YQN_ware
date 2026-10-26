// Independent prototype fixtures. These are test orders and a 2D motion study,
// not warehouse telemetry or executable Unreal routes.
export const TEST_ORDERS = Array.from({ length: 4 }, (_, i) => ({
  id: `TEST-OUT-${String(i + 1).padStart(3, "0")}`,
  label: [
    "地堆出库 · 联合作业",
    "月台补货 · 循环搬运",
    "出库装车 · 全流程",
    "异常恢复 · 设备协同",
  ][i],
}));

export const FORKLIFTS = Array.from({ length: 5 }, (_, i) => ({
  id: `REPLAY-FORK-${String(i + 1).padStart(2, "0")}`,
  name: `人工叉车 ${String(i + 1).padStart(2, "0")}`,
  cargo: ["B-01-06", "B-02-12", "B-03-08", "B-04-16", "B-05-04"][i],
  truck: ["A", "B", "C", "A", "B"][i],
}));

export const TRUCKS = ["A", "B", "C"].map((letter) => ({
  id: `REPLAY-TRUCK-${letter}`,
  name: `装卸卡车 ${letter}`,
  letter,
}));

// Cubic control points live in the same 1920×1080 canvas as the source image.
// A lookup table gives consistent progress along curves, independent of FPS.
const curves = [
  [
    [410, 622],
    [406, 647],
    [460, 646],
    [680, 646],
    [680, 646],
    [924, 646],
    [1018, 643],
    [1018, 682],
  ],
  [
    [650, 621],
    [650, 641],
    [725, 640],
    [900, 640],
    [900, 640],
    [1144, 640],
    [1205, 643],
    [1205, 681],
  ],
  [
    [950, 622],
    [950, 651],
    [878, 652],
    [700, 652],
    [700, 652],
    [461, 652],
    [380, 647],
    [380, 681],
  ],
  [
    [260, 619],
    [260, 655],
    [352, 657],
    [600, 657],
    [600, 657],
    [920, 657],
    [1018, 654],
    [1018, 682],
  ],
  [
    [530, 620],
    [530, 636],
    [645, 635],
    [890, 635],
    [890, 635],
    [1138, 635],
    [1205, 643],
    [1205, 681],
  ],
];
function cubic(a, b, c, d, t) {
  const s = 1 - t;
  return [0, 1].map(
    (k) =>
      s * s * s * a[k] +
      3 * s * s * t * b[k] +
      3 * s * t * t * c[k] +
      t * t * t * d[k],
  );
}
export const ROUTES = curves.map((points) => {
  const samples = [];
  for (let segment = 0; segment < 2; segment++) {
    for (let step = 0; step <= 80; step++) {
      const offset = segment * 4;
      const point = cubic(...points.slice(offset, offset + 4), step / 80);
      if (samples.length && step === 0) continue;
      const last = samples.at(-1);
      samples.push({
        x: point[0],
        y: point[1],
        distance: last
          ? last.distance + Math.hypot(point[0] - last.x, point[1] - last.y)
          : 0,
      });
    }
  }
  const length = samples.at(-1).distance;
  return { samples, length };
});
export function routePoint(index, progress) {
  const { samples, length } = ROUTES[index];
  const distance = Math.min(1, Math.max(0, progress)) * length;
  const n = samples.findIndex((s) => s.distance >= distance);
  const right = samples[Math.max(1, n)],
    left = samples[Math.max(0, n - 1)];
  const t = Math.max(
    0,
    Math.min(
      1,
      (distance - left.distance) /
        Math.max(0.001, right.distance - left.distance),
    ),
  );
  return {
    x: left.x + (right.x - left.x) * t,
    y: left.y + (right.y - left.y) * t,
    angle: (Math.atan2(right.y - left.y, right.x - left.x) * 180) / Math.PI,
  };
}
export function remainingPath(index, progress, returning = false) {
  const route = ROUTES[index];
  const first = routePoint(index, progress);
  const points = returning
    ? route.samples
        .filter((p) => p.distance < progress * route.length)
        .reverse()
    : route.samples.filter((p) => p.distance > progress * route.length);
  return `M${first.x.toFixed(2)} ${first.y.toFixed(2)} ${points.map((p) => `L${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" ")}`;
}
export function forkliftState(index, time) {
  // Forklift 03 loses 45 seconds of work time to the fault. Its position and
  // load phase freeze, then resume continuously from the same point.
  const workTime =
    index === 2 && time >= 74
      ? time < 119
        ? 74
        : time - 45
      : Math.max(0, time);
  const phase = (workTime + index * 47) % 600;
  const trip = Math.floor((workTime + index * 47) / 600) + 1;
  let progress = 0,
    moving = false,
    carrying = false,
    returning = false,
    status = "等待任务";
  if (phase >= 60 && phase < 90) {
    status = "正在取货";
    carrying = phase >= 76;
  } else if (phase >= 90 && phase < 300) {
    progress = (phase - 90) / 210;
    moving = true;
    carrying = true;
    status = "运送托盘";
  } else if (phase >= 300 && phase < 330) {
    progress = 1;
    carrying = phase < 315;
    status = "正在放货";
  } else if (phase >= 330 && phase < 540) {
    progress = 1 - (phase - 330) / 210;
    moving = true;
    returning = true;
    status = "返回地堆";
  }
  if (index === 2 && time >= 74 && time < 119) {
    moving = false;
    status = "故障 · 等待恢复";
  }
  return {
    ...FORKLIFTS[index],
    phase,
    progress,
    moving,
    carrying,
    returning,
    trip,
    status,
    ...routePoint(index, progress),
  };
}
export function replayEvents(duration = 3600) {
  const rows = [];
  for (let base = 0; base < duration; base += 600) {
    FORKLIFTS.forEach((fork, i) => {
      const delayed = (t) => (i === 2 && t >= 74 ? t + 45 : t);
      const pick = delayed(base + 90 - i * 47);
      const drop = delayed(base + 315 - i * 47);
      if (pick >= 0 && pick <= duration)
        rows.push({
          time: pick,
          device: fork.id,
          label: "取货完成",
          detail: `${fork.cargo} · 上层 1 托`,
          kind: "pickup",
        });
      if (drop >= 0 && drop <= duration)
        rows.push({
          time: drop,
          device: fork.id,
          label: "放货完成",
          detail: `装卸卡车 ${fork.truck} · 完成 1 托交接`,
          kind: "dropoff",
        });
    });
    if (base + 533 <= duration)
      rows.push({
        time: base + 533,
        device: "REPLAY-TRUCK-B",
        label: "装车完成",
        detail: "已装满 · 沿出口驶离",
        kind: "depart",
      });
  }
  rows.push(
    {
      time: 74,
      device: "REPLAY-FORK-03",
      label: "车辆故障",
      detail: "电机过热 · 暂停作业",
      kind: "fault",
    },
    {
      time: 119,
      device: "REPLAY-FORK-03",
      label: "恢复作业",
      detail: "温度恢复 · 继续当前任务",
      kind: "recover",
    },
  );
  return rows.filter((x) => x.time <= duration).sort((a, b) => a.time - b.time);
}
export function elapsed(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}
export function localReplayTime(start, seconds, includeDate = false) {
  const parsed = new Date(`${start || "2026-10-26T09:00"}:00Z`);
  if (!Number.isFinite(parsed.getTime())) return "—";
  const iso = new Date(parsed.getTime() + seconds * 1000).toISOString();
  return includeDate ? iso.slice(0, 19).replace("T", " ") : iso.slice(11, 19);
}
