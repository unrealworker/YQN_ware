import React, { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./ui";
import {
  TEST_ORDERS,
  FORKLIFTS,
  TRUCKS,
  forkliftState,
  remainingPath,
  replayEvents,
  elapsed,
  localReplayTime,
} from "./replay-data";
import "./replay.css";

const initialTimes = { start: "2026-10-26T09:00", end: "2026-10-26T10:00" };
const initialPlayback = {
  active: true,
  playing: true,
  time: 230,
  duration: 3600,
  rate: 1,
  follow: null,
  routes: "all",
  order: "TEST-OUT-001",
  ...initialTimes,
};
const RpButton = ({
  children,
  primary,
  danger,
  small,
  className = "",
  ...props
}) => (
  <button
    className={`rp-button ${primary ? "rp-primary" : ""} ${danger ? "rp-danger" : ""} ${small ? "rp-small" : ""} ${className}`}
    {...props}
  >
    {children}
  </button>
);
const TestBadge = ({ children = "测试数据" }) => (
  <span className="rp-test-badge">{children}</span>
);

export function ReplayPanel({
  initialState = 15,
  replay,
  setReplay,
  notify = () => {},
  onEnd,
  onNavigate,
}) {
  const [stage, setStage] = useState("query");
  const [tab, setTab] = useState("devices");
  const [queryError, setQueryError] = useState("");
  const [eventPage, setEventPage] = useState(0);
  const [demoDialog, setDemoDialog] = useState(null);
  const [boundary, setBoundary] = useState("loading");
  const queryTimer = useRef(null);
  const prevState = useRef(null);
  const events = useMemo(
    () => replayEvents(replay.duration),
    [replay.duration],
  );
  const patch = (value) => setReplay((r) => ({ ...r, ...value }));

  useEffect(() => {
    if (prevState.current === initialState) return;
    prevState.current = initialState;
    clearTimeout(queryTimer.current);
    setQueryError("");
    setDemoDialog(null);
    setEventPage(0);
    setTab("devices");
    const number = Number(initialState);
    if ([5, 47, 48, 49, 50, 51, 53].includes(number)) {
      setStage("playback");
      setReplay((r) => ({
        ...r,
        ...initialPlayback,
        playing: [5, 53].includes(number),
        time: number === 49 ? 3600 : number === 48 ? 74 : 230,
        follow: [47, 48].includes(number) ? "REPLAY-FORK-03" : null,
      }));
      if (number === 48) setTab("events");
      if (number === 50 || number === 51)
        setDemoDialog(number === 50 ? "navigate" : "end");
    } else {
      setReplay((r) => ({
        ...r,
        active: false,
        playing: false,
        ...initialTimes,
        ...(number === 46 ? { end: "2026-10-26T09:30" } : {}),
      }));
      setStage(
        number === 45 ? "results" : number === 52 ? "boundary" : "query",
      );
      if (number === 46) setQueryError("时间范围至少 1 小时，请调整结束时间。");
    }
  }, [initialState, setReplay]);

  useEffect(() => {
    if (!replay.active || !replay.playing) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const delta = Math.min((now - last) / 1000, 0.5);
      last = now;
      setReplay((r) => {
        if (!r.active || !r.playing) return r;
        const time = Math.min(r.duration, r.time + delta * r.rate);
        return { ...r, time, playing: time < r.duration };
      });
    }, 50);
    return () => window.clearInterval(timer);
  }, [replay.active, replay.playing, setReplay]);
  useEffect(() => () => clearTimeout(queryTimer.current), []);

  const duration = Math.round(
    (new Date(replay.end).getTime() - new Date(replay.start).getTime()) / 1000,
  );
  function query() {
    if (!Number.isFinite(duration))
      return setQueryError("请选择完整的开始时间和结束时间。");
    if (duration < 3600)
      return setQueryError("时间范围至少 1 小时，请调整结束时间。");
    if (duration > 24 * 3600)
      return setQueryError("原型支持最长 24 小时。请缩小范围后重试。");
    setQueryError("");
    setStage("loading");
    queryTimer.current = window.setTimeout(() => {
      patch({ duration, time: 0 });
      setStage("results");
    }, 650);
  }
  function shortcut(hours) {
    const start = new Date(replay.start);
    if (!Number.isFinite(start.getTime())) return;
    const offset = start.getTimezoneOffset() * 60 * 1000;
    patch({
      end: new Date(start.getTime() + hours * 3600000 - offset)
        .toISOString()
        .slice(0, 16),
    });
    setQueryError("");
  }
  function startOrder(id) {
    patch({
      active: true,
      playing: true,
      time: 0,
      rate: 1,
      follow: null,
      routes: "all",
      order: id,
      duration: Number.isFinite(duration) && duration >= 3600 ? duration : 3600,
    });
    setStage("playback");
    setTab("devices");
    notify("已进入测试回放 · 5 台人工叉车与 3 台装卸车");
  }
  function end() {
    if (onEnd) onEnd();
    else patch({ endRequested: true });
  }
  const selectedEvents = events.slice(eventPage * 8, eventPage * 8 + 8);

  if (stage === "boundary" && !replay.active)
    return (
      <section className="rp-panel">
        <div className="rp-heading">
          <div>
            <span className="rp-eyebrow">TRACE / STATES</span>
            <h2>查询与恢复边界</h2>
          </div>
          <TestBadge>交互示例</TestBadge>
        </div>
        <p className="rp-muted">
          保留所选区间和最近结果，每一种情况都有下一步。
        </p>
        <div className="rp-chip-row">
          {[
            ["loading", "加载中"],
            ["empty", "无订单"],
            ["failed", "查询失败"],
            ["dst", "夏令时"],
            ["restore", "恢复失败"],
          ].map(([v, l]) => (
            <button
              key={v}
              className={boundary === v ? "rp-chip rp-selected" : "rp-chip"}
              onClick={() => setBoundary(v)}
            >
              {l}
            </button>
          ))}
        </div>
        <div className="rp-boundary-box">
          <Icon
            name={
              boundary === "loading"
                ? "LoaderCircle"
                : boundary === "empty"
                  ? "Search"
                  : "Info"
            }
            size={28}
          />
          <h3>
            {
              {
                loading: "正在索引订单",
                empty: "该时段暂无订单",
                failed: "索引失败，请重试",
                dst: "请选择当地时间偏移",
                restore: "场景恢复失败",
              }[boundary]
            }
          </h3>
          <p>
            {
              {
                loading: "所选区间已保留，正在读取订单索引。",
                empty: "这是正式数据空态演示；测试模式始终返回 4 个测试订单。",
                failed: "已保留输入和上次结果，查询失败不会切换场景。",
                dst: "夏令时回拨可能出现重复时刻。真实数据接入时须明确 PDT 或 PST，不能静默猜测。",
                restore: "回放保持暂停，原导航尚未执行；恢复成功后仅执行一次。",
              }[boundary]
            }
          </p>
          {boundary === "dst" ? (
            <div className="rp-actions">
              <RpButton
                onClick={() => {
                  notify("已选择 PDT · UTC−07:00");
                  setStage("query");
                }}
              >
                PDT · UTC−07:00
              </RpButton>
              <RpButton
                onClick={() => {
                  notify("已选择 PST · UTC−08:00");
                  setStage("query");
                }}
              >
                PST · UTC−08:00
              </RpButton>
            </div>
          ) : (
            <RpButton
              primary
              onClick={() => {
                setStage(boundary === "loading" ? "results" : "query");
                notify(
                  boundary === "restore"
                    ? "已恢复原型场景"
                    : boundary === "loading"
                      ? "已索引 4 个测试订单"
                      : "返回时段选择",
                );
              }}
            >
              {boundary === "failed"
                ? "重试索引"
                : boundary === "restore"
                  ? "重试恢复"
                  : boundary === "loading"
                    ? "查看索引结果"
                    : "调整时间"}
            </RpButton>
          )}
        </div>
        <p className="rp-caption">
          仅演示边界反馈，不请求真实订单或操作远端服务。
        </p>
      </section>
    );

  return (
    <section className="rp-panel">
      <div className="rp-heading">
        <div>
          <span className="rp-eyebrow">OPERATIONS / REPLAY</span>
          <h2>订单追溯</h2>
        </div>
        {replay.active ? (
          <RpButton small onClick={end}>
            结束追溯
          </RpButton>
        ) : (
          <TestBadge />
        )}
      </div>
      {!replay.active &&
        (stage === "query" || stage === "loading" || stage === "playback") && (
          <>
            <p className="rp-intro">选一个时段，回看仓库里的每一次作业。</p>
            <div className="rp-timezone">
              <Icon name="Clock3" size={17} />
              <div>
                仓库当地时间<span>America/Los_Angeles · PDT / PST</span>
              </div>
            </div>
            <label className="rp-field">
              开始时间
              <input
                type="datetime-local"
                value={replay.start}
                onChange={(e) => {
                  patch({ start: e.target.value });
                  setQueryError("");
                }}
                disabled={stage === "loading"}
              />
            </label>
            <label className="rp-field">
              结束时间
              <input
                type="datetime-local"
                aria-invalid={!!queryError}
                value={replay.end}
                onChange={(e) => {
                  patch({ end: e.target.value });
                  setQueryError("");
                }}
                disabled={stage === "loading"}
              />
            </label>
            <div className="rp-field">
              <span>快捷时长</span>
              <div className="rp-chip-row">
                {[1, 2, 4].map((h) => (
                  <button
                    key={h}
                    className={`rp-chip ${duration === h * 3600 ? "rp-selected" : ""}`}
                    onClick={() => shortcut(h)}
                    disabled={stage === "loading"}
                  >
                    {h} 小时
                  </button>
                ))}
              </div>
            </div>
            {queryError ? (
              <p role="alert" className="rp-error">
                <Icon name="CircleAlert" size={15} />
                {queryError}
              </p>
            ) : (
              <p className="rp-caption">
                {Number.isFinite(duration) && duration > 0
                  ? `已选 ${(duration / 3600).toFixed(duration % 3600 ? 1 : 0)} 小时`
                  : "请选择时间范围"}{" "}
                · 最少 1 小时
              </p>
            )}
            <RpButton
              primary
              className="rp-wide"
              onClick={query}
              disabled={stage === "loading"}
            >
              {stage === "loading" ? (
                <>
                  <span className="rp-spinner" />
                  索引中…
                </>
              ) : (
                <>
                  <Icon name="Search" size={17} />
                  索引订单
                </>
              )}
            </RpButton>
            <div className="rp-notice">
              <Icon name="Info" size={17} />
              <div>
                <strong>测试订单</strong>
                <p>
                  任意有效时段返回同一组 4 个订单。选择后回放该时段全部 5
                  台人工叉车与 3 台装卸车。
                </p>
              </div>
            </div>
            <div className="rp-process">
              <span>01 选择时段</span>
              <i />
              <span>02 索引订单</span>
              <i />
              <span>03 回放作业</span>
            </div>
          </>
        )}
      {!replay.active && stage === "results" && (
        <>
          <p className="rp-intro">选择一个订单，进入全时段设备回放。</p>
          <div className="rp-range-summary">
            <div>
              <span>
                所选区间 ·{" "}
                {Number.isFinite(duration) ? Math.max(1, duration / 3600) : 1}{" "}
                小时
              </span>
              <strong>{replay.start?.slice(0, 10)}</strong>
              <span>
                {replay.start?.slice(11)} — {replay.end?.slice(11)} ·
                仓库当地时间
              </span>
            </div>
            <button
              className="rp-text-action"
              onClick={() => setStage("query")}
            >
              修改
            </button>
          </div>
          <div className="rp-section-heading">
            <h3>4 个测试订单</h3>
            <span>相同设备与路径</span>
          </div>
          {TEST_ORDERS.map((order) => (
            <button
              key={order.id}
              className="rp-order"
              onClick={() => startOrder(order.id)}
            >
              <div>
                <strong>{order.id}</strong>
                <TestBadge>测试订单</TestBadge>
              </div>
              <p>{order.label}</p>
              <span>5 台人工叉车 · 3 台装卸车</span>
              <b>
                开始回放 <Icon name="ArrowUpRight" size={16} />
              </b>
            </button>
          ))}
          <p className="rp-caption">订单作为回放入口，不会筛选该时段的设备。</p>
        </>
      )}
      {replay.active && (
        <>
          <div className="rp-session">
            <div>
              <strong>{replay.order || "TEST-OUT-001"}</strong>
              <TestBadge>测试回放</TestBadge>
            </div>
            <p>
              {replay.start?.replace("T", " ")} — {replay.end?.slice(11)}
            </p>
            <span>全时段 8 台设备 · 二维交互演示</span>
          </div>
          {replay.time >= replay.duration && (
            <div className="rp-completed">
              <Icon name="CircleCheck" size={22} />
              <div>
                <strong>回放完成</strong>
                <p>已停在区间终点，不会自动重播。</p>
              </div>
              <RpButton small onClick={() => patch({ time: 0, playing: true })}>
                从头回放
              </RpButton>
            </div>
          )}
          <div className="rp-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={tab === "devices"}
              onClick={() => setTab("devices")}
            >
              设备 <span>8</span>
            </button>
            <button
              role="tab"
              aria-selected={tab === "events"}
              onClick={() => setTab("events")}
            >
              关键事件 <span>{events.length}</span>
            </button>
          </div>
          {tab === "devices" ? (
            <div className="rp-device-list">
              {FORKLIFTS.map((device, i) => {
                const state = forkliftState(i, replay.time),
                  follow = replay.follow === device.id;
                return (
                  <div
                    className={`rp-device ${follow ? "rp-followed" : ""}`}
                    key={device.id}
                  >
                    <div className="rp-device-top">
                      <span className="rp-device-icon">
                        <Icon name="Forklift" size={24} />
                      </span>
                      <div>
                        <strong>{device.name}</strong>
                        <small>{device.id}</small>
                      </div>
                      <span
                        className={
                          state.status.includes("故障")
                            ? "rp-status rp-fault"
                            : "rp-status"
                        }
                      >
                        {state.status}
                      </span>
                    </div>
                    <div className="rp-device-bottom">
                      <span>
                        {state.carrying ? "载有托盘" : "空载"} · 第 {state.trip}{" "}
                        趟
                      </span>
                      <button
                        onClick={() =>
                          patch({ follow: follow ? null : device.id })
                        }
                      >
                        {follow ? "取消跟随" : "跟随视角"}
                        <Icon name={follow ? "X" : "Crosshair"} size={13} />
                      </button>
                    </div>
                  </div>
                );
              })}
              {TRUCKS.map((device, i) => (
                <div className="rp-device" key={device.id}>
                  <div className="rp-device-top">
                    <span className="rp-device-icon">
                      <Icon name="Truck" size={24} />
                    </span>
                    <div>
                      <strong>{device.name}</strong>
                      <small>{device.id}</small>
                    </div>
                    <span className="rp-status">
                      {i === 1 && replay.time % 600 > 533
                        ? "满载驶离"
                        : "等待装载"}
                    </span>
                  </div>
                  <div className="rp-device-bottom">
                    <span>
                      已装 {Math.floor(((replay.time + i * 93) % 600) / 150)} /
                      4 托
                    </span>
                    <button
                      onClick={() => {
                        patch({ follow: device.id });
                        notify(`已突出 ${device.name}`);
                      }}
                    >
                      定位车辆
                      <Icon name="Crosshair" size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <>
              <div className="rp-section-heading">
                <h3>测试事件</h3>
                <span>点击定位并暂停</span>
              </div>
              <div className="rp-events">
                {selectedEvents.map((event, i) => (
                  <button
                    key={`${event.device}-${event.time}`}
                    className={`rp-event ${event.kind === "fault" ? "rp-event-fault" : ""} ${Math.abs(event.time - replay.time) < 1 ? "rp-event-selected" : ""}`}
                    onClick={() =>
                      patch({
                        time: event.time,
                        playing: false,
                        follow: event.device,
                      })
                    }
                  >
                    <time>{localReplayTime(replay.start, event.time)}</time>
                    <span className="rp-event-dot" />
                    <div>
                      <strong>{event.label}</strong>
                      <span>{event.device}</span>
                      <p>{event.detail}</p>
                    </div>
                    <Icon name="ChevronRight" size={15} />
                  </button>
                ))}
              </div>
              <div className="rp-pagination">
                <RpButton
                  small
                  disabled={eventPage === 0}
                  onClick={() => setEventPage((p) => p - 1)}
                >
                  上一页
                </RpButton>
                <span>
                  {eventPage + 1} / {Math.max(1, Math.ceil(events.length / 8))}
                </span>
                <RpButton
                  small
                  disabled={(eventPage + 1) * 8 >= events.length}
                  onClick={() => setEventPage((p) => p + 1)}
                >
                  下一页
                </RpButton>
              </div>
            </>
          )}
          <p className="rp-caption rp-footer-note">
            当前任务剩余路线 · 仅叉车移动时显示
          </p>
        </>
      )}
      {demoDialog && (
        <div
          className="rp-inline-dialog"
          role="dialog"
          aria-modal="true"
          aria-label="结束追溯确认"
        >
          <Icon name="CircleHelp" size={28} />
          <h3>
            {demoDialog === "navigate" ? "停止追溯并前往总览？" : "结束追溯？"}
          </h3>
          <p>
            当前回放将结束，场景恢复到进入追溯前的状态。时间区间与订单列表会保留。
          </p>
          <div className="rp-actions">
            <RpButton
              onClick={() => {
                setDemoDialog(null);
                patch({ playing: true });
              }}
            >
              继续追溯
            </RpButton>
            <RpButton
              primary
              onClick={() => {
                const navigating = demoDialog === "navigate";
                setDemoDialog(null);
                patch({ active: false, playing: false, follow: null });
                setStage("results");
                notify("已结束测试回放并恢复场景");
                if (navigating) onNavigate?.(31);
              }}
            >
              {demoDialog === "navigate" ? "停止并前往总览" : "结束并恢复场景"}
            </RpButton>
          </div>
        </div>
      )}
    </section>
  );
}

export function ReplayTimeline({ replay, setReplay, onEnd = () => {} }) {
  const events = useMemo(
    () => replayEvents(replay.duration),
    [replay.duration],
  );
  if (!replay.active) return null;
  const patch = (value) => setReplay((r) => ({ ...r, ...value }));
  return (
    <div className="replay-timeline" aria-label="作业回放时间轴">
      <div className="replay-timeline-top">
        <div>
          <strong>作业回放</strong>
          <span className={`rp-play-state ${replay.playing ? "rp-live" : ""}`}>
            {replay.time >= replay.duration
              ? "已完成"
              : replay.playing
                ? "播放中"
                : "已暂停"}
          </span>
          <span className="rp-timeline-clock">
            {localReplayTime(replay.start, replay.time, true)}
          </span>
        </div>
        <span>
          {elapsed(replay.time)} <i>/</i> {elapsed(replay.duration)}
        </span>
      </div>
      <div className="rp-time-track">
        <div className="rp-time-events">
          {events.map((event, index) => (
            <button
              key={`${event.time}-${index}`}
              className={`rp-time-dot ${event.kind === "fault" ? "rp-time-fault" : ""}`}
              style={{ left: `${(event.time / replay.duration) * 100}%` }}
              title={`${elapsed(event.time)} · ${event.device} · ${event.label}`}
              aria-label={`${elapsed(event.time)} ${event.device} ${event.label}`}
              onClick={() =>
                patch({
                  time: event.time,
                  playing: false,
                  follow: event.device,
                })
              }
            />
          ))}
        </div>
        <input
          type="range"
          aria-label="回放进度"
          min="0"
          max={replay.duration}
          step="1"
          value={replay.time}
          onChange={(e) =>
            patch({ time: Number(e.target.value), playing: false })
          }
          style={{ "--progress": `${(replay.time / replay.duration) * 100}%` }}
        />
      </div>
      <div className="rp-timeline-times">
        <span>{localReplayTime(replay.start, 0, true)}</span>
        <span>
          {localReplayTime(replay.start, replay.duration, true)} · 仓库当地时间
        </span>
      </div>
      <div className="replay-timeline-controls">
        <div className="rp-controls-left">
          <RpButton
            primary
            small
            onClick={() =>
              patch(
                replay.time >= replay.duration
                  ? { time: 0, playing: true }
                  : { playing: !replay.playing },
              )
            }
          >
            <Icon name={replay.playing ? "Pause" : "Play"} size={15} />
            {replay.time >= replay.duration
              ? "重播"
              : replay.playing
                ? "暂停"
                : "播放"}
          </RpButton>
          <RpButton
            small
            onClick={() => patch({ time: Math.max(0, replay.time - 30) })}
          >
            −30 秒
          </RpButton>
          <RpButton
            small
            onClick={() =>
              patch({ time: Math.min(replay.duration, replay.time + 30) })
            }
          >
            +30 秒
          </RpButton>
          <label>
            倍率
            <select
              aria-label="回放倍率"
              value={replay.rate}
              onChange={(e) => patch({ rate: Number(e.target.value) })}
            >
              {[1, 2, 4, 8, 16, 32, 64].map((rate) => (
                <option key={rate} value={rate}>
                  {rate}×
                </option>
              ))}
            </select>
          </label>
          <label className="rp-view-select">
            视角
            <select
              aria-label="回放视角"
              value={replay.follow || ""}
              onChange={(e) => patch({ follow: e.target.value || null })}
            >
              <option value="">地堆全景</option>
              {[...FORKLIFTS, ...TRUCKS].map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="rp-controls-right">
          <label>
            剩余路线
            <select
              aria-label="剩余路线显示"
              value={replay.routes}
              onChange={(e) => patch({ routes: e.target.value })}
            >
              <option value="all">全部叉车</option>
              <option value="selected">仅选中</option>
              <option value="off">关闭</option>
            </select>
          </label>
          <button className="rp-end-text" onClick={onEnd}>
            结束
          </button>
        </div>
      </div>
    </div>
  );
}

export function ReplayMapOverlay({ replay, setReplay }) {
  const [hovered, setHovered] = useState(null);
  if (!replay.active) return null;
  const select = (id) =>
    setReplay((r) => ({ ...r, follow: r.follow === id ? null : id }));
  return (
    <svg
      className="replay-map-overlay"
      viewBox="0 0 1920 1080"
      preserveAspectRatio="xMidYMid slice"
      aria-label="测试回放设备与路线示意"
      style={{
        zIndex: 3,
        "--replay-play-state": replay.playing ? "running" : "paused",
      }}
    >
      <defs>
        <linearGradient id="rpRouteGradient" x1="0%" y1="0%" x2="100%" y2="20%">
          <stop offset="0%" stopColor="#A8CAFA" />
          <stop offset="42%" stopColor="#689DF3" />
          <stop offset="100%" stopColor="#356BFA" />
        </linearGradient>
        <filter id="rpRouteGlow" x="-30%" y="-80%" width="160%" height="260%">
          <feGaussianBlur stdDeviation="2.1" />
        </filter>
      </defs>
      {FORKLIFTS.map((fork, index) => {
        const s = forkliftState(index, replay.time),
          selected = replay.follow === fork.id,
          show =
            s.moving &&
            replay.time < replay.duration &&
            replay.routes !== "off" &&
            (replay.routes !== "selected" || selected),
          path = remainingPath(index, s.progress, s.returning);
        return (
          <g key={fork.id}>
            {show && (
              <g className="rp-route">
                <path
                  d={path}
                  fill="none"
                  stroke="#356BFA"
                  strokeWidth="5"
                  opacity=".2"
                  filter="url(#rpRouteGlow)"
                />
                <path
                  className="rp-route-dashes"
                  d={path}
                  fill="none"
                  stroke="url(#rpRouteGradient)"
                  strokeWidth="3.6"
                  strokeLinecap="round"
                  strokeDasharray="25 10"
                />
              </g>
            )}
            <g
              className="rp-fork-marker"
              role="button"
              tabIndex="0"
              aria-label={`${fork.name} ${s.status}，点击跟随`}
              onClick={() => select(fork.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  select(fork.id);
                }
              }}
              onMouseEnter={() => setHovered(fork.id)}
              onMouseLeave={() => setHovered(null)}
              transform={`translate(${s.x.toFixed(2)} ${s.y.toFixed(2)})`}
            >
              <ellipse
                className="rp-wave rp-wave-one"
                rx={16 + ((replay.time * 4 + index * 6) % 19)}
                ry={8 + ((replay.time * 2 + index * 3) % 9.5)}
                fill="none"
                stroke="#356BFA"
                strokeWidth="2"
                opacity={0.8 - ((replay.time * 4 + index * 6) % 19) / 32}
              />
              <ellipse rx="17" ry="9" fill="#356BFA" opacity=".13" />
              <g transform={`rotate(${s.angle + (s.returning ? 180 : 0)})`}>
                <rect
                  x="-11"
                  y="-7"
                  width="20"
                  height="14"
                  rx="3"
                  fill={selected ? "#356BFA" : "#fff"}
                  stroke="#25364B"
                  strokeWidth="1.2"
                />
                <rect
                  x="-4"
                  y="-5"
                  width="8"
                  height="10"
                  rx="1"
                  fill="#31465F"
                />
                <path d="M9 -5h12M9 5h12" stroke="#263A54" strokeWidth="2.5" />
                <path
                  d="M-7 -9h5M4 -9h4M-7 9h5M4 9h4"
                  stroke="#1D2A3A"
                  strokeWidth="4"
                />
                {s.carrying && (
                  <g>
                    <rect
                      x="15"
                      y="-10"
                      width="16"
                      height="20"
                      rx="1"
                      fill="#DCE3EC"
                      stroke="#A4B4C8"
                    />
                    <path d="M15 10h16" stroke="#356BFA" strokeWidth="3" />
                    <path
                      d="M23 -10v20M15 0h16"
                      stroke="#B8C3D0"
                      strokeWidth="1"
                    />
                  </g>
                )}
              </g>
              <g
                className={`rp-map-label ${selected ? "rp-map-label-selected" : ""}`}
                transform={`translate(${-57} ${-38 - (index % 3) * 44})`}
              >
                <rect
                  width="114"
                  height="25"
                  rx="6"
                  fill={selected ? "#356BFA" : "#fff"}
                  stroke={selected ? "#356BFA" : "#D5DFEC"}
                  strokeWidth="1.3"
                />
                <text
                  x="10"
                  y="17"
                  fill={selected ? "#fff" : "#25364B"}
                  fontSize="12"
                  fontFamily="Noto Sans SC,Microsoft YaHei,sans-serif"
                >
                  {fork.name}
                </text>
                <circle
                  cx="100"
                  cy="12.5"
                  r="3"
                  fill={
                    s.status.includes("故障")
                      ? "#C85852"
                      : selected
                        ? "#fff"
                        : "#356BFA"
                  }
                />
                <path
                  d={`M57 25v${10 + (index % 3) * 44}`}
                  stroke="#356BFA"
                  strokeWidth="1"
                />
              </g>
              {(selected || hovered === fork.id) && (
                <g transform="translate(-66 22)">
                  <rect width="132" height="23" rx="5" fill="#163455" />
                  <text
                    x="66"
                    y="15.5"
                    textAnchor="middle"
                    fill="white"
                    fontSize="10.5"
                    fontFamily="Noto Sans SC,Microsoft YaHei,sans-serif"
                  >
                    {s.status} · {s.carrying ? "载货" : "空载"}
                  </text>
                </g>
              )}
            </g>
          </g>
        );
      })}
      {TRUCKS.map((truck, index) => {
        const departing = index === 1 && replay.time % 600 > 533,
          offset = departing
            ? Math.min(450, ((replay.time % 600) - 533) * 7)
            : 0,
          x = [1018, 1205, 380][index] + offset,
          y = 716 + offset * 0.15;
        return (
          <g
            key={truck.id}
            className="rp-truck-marker"
            role="button"
            tabIndex="0"
            aria-label={`${truck.name}，定位车辆`}
            onClick={() => select(truck.id)}
            onKeyDown={(e) => e.key === "Enter" && select(truck.id)}
            transform={`translate(${x} ${y})`}
            opacity={1 - offset / 500}
          >
            <g transform={`rotate(${departing ? 12 : 90})`}>
              <rect
                x="-28"
                y="-9"
                width="46"
                height="18"
                rx="2"
                fill="#F8FAFC"
                stroke="#AEBCCF"
              />
              <rect
                x="19"
                y="-8"
                width="15"
                height="16"
                rx="2"
                fill="#356BFA"
              />
              <path d="M-27 6h45" stroke="#356BFA" strokeWidth="2" />
            </g>
            <g transform="translate(-49 38)">
              <rect
                width="98"
                height="22"
                rx="5"
                fill="white"
                stroke="#D5DFEC"
              />
              <text
                x="49"
                y="15"
                textAnchor="middle"
                fill="#31435A"
                fontSize="11"
                fontFamily="Noto Sans SC,Microsoft YaHei,sans-serif"
              >
                {truck.name}
              </text>
            </g>
          </g>
        );
      })}
    </svg>
  );
}
