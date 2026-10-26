import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Icon, Button, Badge, Section } from "./ui";
import BusinessPanels from "./BusinessPanels";
import Streaming from "./Streaming";
import { ReplayPanel, ReplayTimeline, ReplayMapOverlay } from "./Replay";
import Settings from "./Settings";
import pages from "./pages.json";

const nav = [
  ["overview", "总览", "LayoutDashboard", 31],
  ["inventory", "库存", "Package", 11],
  ["orders", "订单", "ClipboardList", 12],
  ["devices", "设备", "Forklift", 13],
  ["alerts", "告警", "TriangleAlert", 14],
  ["replay", "追溯", "History", 15],
  ["settings", "场景", "SlidersHorizontal", 16],
];
const initialReplay = {
  active: false,
  playing: false,
  time: 0,
  duration: 3600,
  rate: 1,
  follow: null,
  routes: "all",
  order: "",
  start: "2026-10-26T09:00",
  end: "2026-10-26T10:00",
};
const pageFor = (n) =>
  [5, 15, ...Array.from({ length: 9 }, (_, i) => 45 + i)].includes(n)
    ? "replay"
    : [6, 11, 17].includes(n)
      ? "inventory"
      : [12, 18, 19].includes(n)
        ? "orders"
        : [2, 3, 7, 10, 13, 20].includes(n)
          ? "devices"
          : [4, 14].includes(n)
            ? "alerts"
            : [16, 34].includes(n)
              ? "settings"
              : "overview";
const isStream = (n) => (n >= 25 && n <= 29) || (n >= 35 && n <= 43);
const isGuide = (n) => [0, 9, 21, 30, 33].includes(n);
function readScreen() {
  const raw = new URLSearchParams(location.hash.slice(1)).get("screen");
  const n = raw === null ? 31 : Number(raw);
  return Number.isInteger(n) && n >= 0 && n < 54 ? n : 31;
}

function LocalClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const zone = "America/Los_Angeles";
  return (
    <div className="warehouse-clock">
      <Icon name="Clock3" size={18} />
      <div>
        <span>仓库当地时间</span>
        <strong>{now.toLocaleTimeString("en-GB", { timeZone: zone })}</strong>
        <small>
          {now.toLocaleDateString("zh-CN", { timeZone: zone })} ·{" "}
          {
            new Intl.DateTimeFormat("en-US", {
              timeZone: zone,
              timeZoneName: "short",
            })
              .formatToParts(now)
              .find((x) => x.type === "timeZoneName").value
          }
        </small>
      </div>
    </div>
  );
}
function Directory({ onClose, onChoose, current }) {
  const [query, setQuery] = useState(""),
    [group, setGroup] = useState("全部");
  const matches = pages.filter(
    (p) =>
      (group === "全部" ||
        (group === "业务界面" &&
          !isStream(p.number) &&
          !isGuide(p.number) &&
          pageFor(p.number) !== "replay") ||
        (group === "订单追溯" && pageFor(p.number) === "replay") ||
        (group === "服务与连接" && isStream(p.number)) ||
        (group === "设计规范" && isGuide(p.number))) &&
      p.name.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <motion.div
      className="directory-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.section
        className="directory"
        role="dialog"
        aria-modal="true"
        aria-label="全部页面目录"
        initial={{ y: 20 }}
        animate={{ y: 0 }}
      >
        <header>
          <div>
            <p className="eyebrow">GHS / INTERACTIVE PROTOTYPE</p>
            <h1>每个页面，都可以抵达。</h1>
            <p>54 个设计页面与交互状态 · 源自 Saas.pen</p>
          </div>
          <button
            className="icon-button"
            autoFocus
            aria-label="关闭页面目录"
            onClick={onClose}
          >
            <Icon name="X" />
          </button>
        </header>
        <div className="directory-tools">
          <div className="directory-tabs">
            {["全部", "业务界面", "订单追溯", "服务与连接", "设计规范"].map(
              (g) => (
                <button
                  className={group === g ? "active" : ""}
                  onClick={() => setGroup(g)}
                  key={g}
                >
                  {g}
                </button>
              ),
            )}
          </div>
          <label className="input-with-icon">
            <Icon name="Search" size={16} />
            <input
              placeholder="搜索页面名称或编号"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        <div className="directory-grid">
          {matches.map((p) => (
            <button
              className={`page-tile ${current === p.number ? "selected" : ""}`}
              key={p.number}
              onClick={() => onChoose(p.number)}
            >
              <div
                className={`tile-thumb ${isStream(p.number) ? "stream-thumb" : ""}`}
              >
                <img
                  src={
                    pageFor(p.number) === "replay"
                      ? "/assets/interior.png"
                      : "/assets/campus.png"
                  }
                  alt=""
                />
                <div className="tile-mini-panel">
                  <i />
                  <i />
                  <b />
                  <i />
                  <i />
                  <b />
                </div>
                {isStream(p.number) && <Icon name="Monitor" size={32} />}
                <span>{String(p.number).padStart(2, "0")}</span>
              </div>
              <div className="tile-caption">
                <strong>{p.name.replace(/^\d+ · /, "")}</strong>
                <Icon name="ArrowUpRight" size={16} />
              </div>
              <small>{p.interactions?.[0] || "查看交互状态"}</small>
            </button>
          ))}
        </div>
        <footer>
          <span>{matches.length} 个页面</span>
          <span>所有服务操作均在原型内模拟</span>
          <Badge>React · ECharts · React Bits</Badge>
        </footer>
      </motion.section>
    </motion.div>
  );
}
function Guide({ screen, onNavigate }) {
  const data = pages[screen];
  return (
    <div className="guide-content">
      <p className="eyebrow">
        GHS DESIGN SYSTEM / {String(screen).padStart(2, "0")}
      </p>
      <h1>{data.name.replace(/^\d+ · /, "")}</h1>
      <p className="muted">从园区、信息到操作，使用同一套视觉语言。</p>
      <Section title="界面色彩">
        <div className="swatches">
          {[
            ["#356BFA", "主题蓝"],
            ["#25364B", "正文"],
            ["#536478", "辅助信息"],
            ["#E5EAF2", "结构线"],
            ["#D1843C", "待处理"],
            ["#C85852", "故障"],
          ].map(([c, n]) => (
            <div key={c}>
              <i style={{ background: c }} />
              <strong>{n}</strong>
              <small>{c}</small>
            </div>
          ))}
        </div>
      </Section>
      <Section title="七个业务入口">
        <div className="guide-nav">
          {nav.map(([id, name, icon, n]) => (
            <button key={id} onClick={() => onNavigate(n)}>
              <Icon name={icon} />
              <strong>{name}</strong>
              <Icon name="ArrowUpRight" size={15} />
            </button>
          ))}
        </div>
      </Section>
      <Section title="状态与反馈">
        <div className="split">
          <Badge>选中</Badge>
          <Badge tone="green">运行</Badge>
          <Badge tone="orange">待处理</Badge>
          <Badge tone="red">故障</Badge>
          <Badge tone="gray">禁用</Badge>
        </div>
        <div className="guide-links">
          <Button onClick={() => onNavigate(22)}>体验数据边界状态</Button>
          <Button variant="secondary" onClick={() => onNavigate(23)}>
            体验中文搜索
          </Button>
          <Button variant="secondary" onClick={() => onNavigate(31)}>
            体验主仓库 POI
          </Button>
        </div>
      </Section>
      <Section title="交互规则">
        <ol className="guide-rules">
          <li>屋顶关闭，仅显示主仓库 POI。点击后进入内部视图。</li>
          <li>已核验台账与示例数据分开呈现；缺失数据不显示虚假零值。</li>
          <li>追溯先选择时段，再选择测试订单。离开回放前需要确认。</li>
          <li>面板与时间条同步伸缩，减少动画偏好会自动关闭非必要动效。</li>
          <li>真实场景截图作为空间背景，原型以二维动画演示交互。</li>
        </ol>
      </Section>
    </div>
  );
}

export default function App() {
  const [screen, setScreen] = useState(readScreen),
    [directory, setDirectory] = useState(false),
    [collapsed, setCollapsed] = useState(false),
    [roof, setRoof] = useState(
      () =>
        ![0, 9, 15, 21, 24, 30, 31, 33, 44, 45, 46].includes(readScreen()) &&
        !isStream(readScreen()),
    ),
    [search, setSearch] = useState(() => (readScreen() === 23 ? "AGV" : "")),
    [searchFocus, setSearchFocus] = useState(() => readScreen() === 23),
    [warehouse, setWarehouse] = useState(() => readScreen() === 24),
    [selection, setSelection] = useState(null),
    [toast, setToast] = useState(""),
    [confirm, setConfirm] = useState(null),
    [replay, setReplay] = useState(initialReplay),
    [zoom, setZoom] = useState(1),
    [pan, setPan] = useState({ x: 0, y: 0 }),
    [settings, setSettings] = useState({
      structure: true,
      devices: true,
      poi: true,
      traffic: true,
      rack: 0.8,
      floor: 1,
    });
  const page = pageFor(screen);
  const sceneRef = useRef(null),
    drag = useRef(null),
    toastTimer = useRef(null);
  const notify = (message) => {
    setToast(message);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 3600);
  };
  const endReplay = () => {
    setReplay((p) => ({ ...p, playing: false }));
    setConfirm({
      resume: replay.playing,
      title: "结束当前追溯？",
      description: "回放将停止，场景恢复为带屋顶的园区总览。",
      action: () => {
        setReplay(initialReplay);
        setRoof(false);
        setSelection(null);
        setZoom(1);
        setPan({ x: 0, y: 0 });
        commitScreen(31);
      },
    });
  };
  function cancelConfirm() {
    if (confirm?.resume) setReplay((p) => ({ ...p, playing: true }));
    setConfirm(null);
  }
  function commitScreen(n) {
    setScreen(n);
    location.hash = `screen=${n}`;
    setSearch("");
    setSearchFocus(false);
    setWarehouse(n === 24);
    setDirectory(false);
    setSelection(null);
    if (n === 23) {
      setSearch("AGV");
      setSearchFocus(true);
    }
    setCollapsed(false);
    setRoof(
      ![0, 9, 15, 21, 24, 30, 31, 33, 44, 45, 46].includes(n) && !isStream(n),
    );
    if (n === 32) setTimeout(() => setRoof(true), 120);
  }
  function navigate(target) {
    const n =
      typeof target === "number"
        ? target
        : (nav.find((x) => x[0] === target)?.[3] ?? 31);
    if (replay.active && n === screen) return;
    if (replay.active && n !== screen) {
      setReplay((p) => ({ ...p, playing: false }));
      setConfirm({
        resume: replay.playing,
        title: "停止追溯并继续？",
        description:
          "停止后恢复场景，再进入你选择的页面。当前回放进度不会继续播放。",
        action: () => {
          setReplay(initialReplay);
          setRoof(false);
          commitScreen(n);
        },
      });
    } else commitScreen(n);
  }
  useEffect(() => {
    const handler = () => {
      const next = readScreen();
      if (next === screen) return;
      if (replay.active) {
        history.replaceState(null, "", `#screen=${screen}`);
        navigate(next);
      } else commitScreen(next);
    };
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, [screen, replay.active]);
  useEffect(() => {
    if (replay.active) setRoof(true);
    else if (screen === 51) setRoof(false);
    if (replay.endRequested) {
      setReplay((p) => ({ ...p, endRequested: false }));
      endReplay();
    }
  }, [replay.active, replay.endRequested]);
  useEffect(() => {
    const key = (e) => {
      if (e.key === "Escape") {
        setDirectory(false);
        setSearchFocus(false);
        setWarehouse(false);
        cancelConfirm();
      }
      if (e.key === "Tab") {
        const dialogs = [...document.querySelectorAll('[aria-modal="true"]')];
        const dialog = dialogs.at(-1);
        if (dialog) {
          const targets = [
            ...dialog.querySelectorAll(
              'button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]',
            ),
          ].filter((x) => x.getClientRects().length);
          const first = targets[0],
            last = targets.at(-1);
          if (
            e.shiftKey &&
            (document.activeElement === first ||
              !dialog.contains(document.activeElement))
          ) {
            e.preventDefault();
            last?.focus();
          } else if (
            !e.shiftKey &&
            (document.activeElement === last ||
              !dialog.contains(document.activeElement))
          ) {
            e.preventDefault();
            first?.focus();
          }
        }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        document.getElementById("global-search")?.focus();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [confirm]);
  useEffect(() => () => clearTimeout(toastTimer.current), []);
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    document
      .querySelector(".side-panel")
      ?.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [screen]);
  const locate = (object) => {
    if (object.type === "warehouse") {
      setRoof(false);
      setZoom(1);
      setSelection(null);
      return;
    }
    setRoof(true);
    setSelection(object);
    setZoom(1.16);
    notify(`已定位 ${object.label} · 场景示意`);
  };
  const results = [
    { label: "AGV-07", detail: "搬运机器人 · 充电区 C", type: "device" },
    { label: "AGV-08", detail: "搬运机器人 · 待机", type: "device" },
    { label: "AGV-12", detail: "搬运机器人 · 低电量预警", type: "device" },
    { label: "FORK-01", detail: "人工叉车 · 地堆区 B", type: "device" },
    { label: "A-03-12", detail: "货架区 A · 已占用", type: "location" },
    {
      label: "SKU2038 · 电机安装支架",
      detail: "物料示例 · 数据未核验",
      type: "material",
    },
  ].filter((x) =>
    `${x.label}${x.detail}`.toLowerCase().includes(search.toLowerCase()),
  );
  const openResult = (r) => {
    const n = r.type === "material" ? 17 : r.type === "location" ? 6 : 2;
    setSearchFocus(false);
    if (replay.active) {
      setReplay((p) => ({ ...p, playing: false }));
      setConfirm({
        resume: replay.playing,
        title: "停止追溯并定位设备？",
        description: "先结束当前回放，再查看所选对象的详情。",
        action: () => {
          setReplay(initialReplay);
          commitScreen(n);
          locate(r);
        },
      });
    } else {
      commitScreen(n);
      locate(r);
    }
  };
  const reset = () => {
    if (replay.active) {
      setReplay((p) => ({ ...p, follow: null }));
      setZoom(1);
      setPan({ x: 0, y: 0 });
      notify("已切换地堆全景");
      return;
    }
    setRoof(false);
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setSelection(null);
  };
  const pointerDown = (e) => {
    if (e.target.closest('button,a,input,select,[role="button"]')) return;
    drag.current = { x: e.clientX, y: e.clientY, start: pan };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const pointerMove = (e) => {
    if (!drag.current || replay.follow) return;
    setPan({
      x: drag.current.start.x + e.clientX - drag.current.x,
      y: drag.current.start.y + e.clientY - drag.current.y,
    });
  };
  const descriptor = pages.find((p) => p.number === screen);
  return (
    <>
      <div className="prototype-ribbon">
        <span>
          <i />
          交互原型
        </span>
        <button onClick={() => setDirectory(true)}>
          <Icon name="PanelsTopLeft" size={14} />
          页面目录 <b>54</b>
        </button>
        <span className="current-page">{descriptor.name}</span>
        <button onClick={() => navigate(42)}>
          <Icon name="MonitorCog" size={14} />
          服务管理
        </button>
      </div>
      {isStream(screen) ? (
        <Streaming screen={screen} onNavigate={navigate} notify={notify} />
      ) : (
        <div className={`workspace ${collapsed ? "panel-collapsed" : ""}`}>
          <header className="app-header">
            <a
              className="brand"
              href="#screen=31"
              onClick={(e) => {
                e.preventDefault();
                navigate(31);
              }}
            >
              <div className="brand-mark">
                <i />
                <i />
                <i />
                <i />
              </div>
              <strong>GHS 仓储数字孪生</strong>
            </a>
            <span className="product-name">三维运营中心</span>
            <div className="address">
              <Icon name="MapPin" />
              <div>
                <strong>17335 Glen Helen Pkwy</strong>
                <small>San Bernardino, CA 92407 美国</small>
              </div>
            </div>
            <LocalClock />
            <button
              className="panel-toggle"
              onClick={() => setCollapsed((v) => !v)}
            >
              <Icon
                name={collapsed ? "PanelRightOpen" : "PanelRightClose"}
                size={18}
              />
              {collapsed ? "展开面板" : "收起面板"}
            </button>
          </header>
          <main className="workspace-body">
            <div
              className={`scene ${replay.active ? "is-replay" : ""}`}
              ref={sceneRef}
            >
              <div
                className={`scene-canvas ${settings.structure ? "" : "structure-muted"}`}
                onPointerDown={pointerDown}
                onPointerMove={pointerMove}
                onPointerUp={() => (drag.current = null)}
                onWheel={(e) =>
                  setZoom((z) =>
                    Math.max(0.8, Math.min(1.8, z - e.deltaY * 0.0005)),
                  )
                }
                style={{
                  transform: `translate(${pan.x}px,${pan.y}px) scale(${zoom})`,
                }}
              >
                <img
                  className="map-image campus"
                  src="/assets/campus.png"
                  alt="GHS 园区实际场景"
                  draggable="false"
                />
                <img
                  className={`map-image interior ${roof ? "open" : ""}`}
                  src="/assets/interior.png"
                  alt={roof ? "主仓库内部实际场景" : ""}
                  draggable="false"
                />
                {!roof && settings.poi && (
                  <button
                    className="warehouse-poi"
                    aria-label="GHS 主仓库 点击查看"
                    onClick={() => {
                      setRoof(true);
                      notify("已进入仓库内部");
                    }}
                  >
                    <div>
                      <span className="poi-icon">
                        <Icon name="Warehouse" size={23} />
                      </span>
                      <span>
                        <strong>GHS · 主仓库</strong>
                        <small>点击查看</small>
                      </span>
                      <Icon name="ChevronRight" size={19} />
                    </div>
                    <i className="poi-leader" />
                    <b className="poi-anchor" />
                  </button>
                )}
                {roof && !replay.active && settings.devices && settings.poi && (
                  <div className="map-pois">
                    {[
                      ["AGV · 32", 26, 36, "Bot"],
                      ["人工叉车 · 8", 53, 52, "Forklift"],
                      ["装卸车 · 28", 65, 67, "Truck"],
                      ["货架 A-03", 14, 43, "Boxes"],
                    ].map(([label, x, y, icon]) => (
                      <button
                        key={label}
                        style={{ left: x + "%", top: y + "%" }}
                        onClick={() => {
                          locate({ label, type: "device" });
                          setScreen(label.includes("货架") ? 6 : 3);
                        }}
                      >
                        <Icon name={icon} size={15} />
                        {label}
                        <span>›</span>
                      </button>
                    ))}
                  </div>
                )}
                {selection && !replay.active && settings.poi && (
                  <div className="selected-poi">
                    <span className="selection-ripple" />
                    <button onClick={() => setSelection(null)}>
                      <Icon name="MapPin" size={16} />
                      {selection.label}
                      <Icon name="X" size={13} />
                    </button>
                  </div>
                )}
                {settings.traffic && !roof && (
                  <div className="traffic-demo" aria-label="道路交通动态示意">
                    <i />
                    <i />
                    <i />
                  </div>
                )}
                {replay.active && (
                  <ReplayMapOverlay replay={replay} setReplay={setReplay} />
                )}
              </div>
              <div className="scene-top">
                <div className="warehouse-selector">
                  <button
                    onClick={() => setWarehouse((v) => !v)}
                    aria-expanded={warehouse}
                  >
                    <span>
                      <strong>GHS</strong>
                      <small>{roof ? "仓库内部" : "园区总览"}</small>
                    </span>
                    <Icon name="ChevronDown" size={16} />
                  </button>
                  {warehouse && (
                    <div className="warehouse-menu">
                      <h3>切换仓库</h3>
                      <button
                        onClick={() => {
                          setWarehouse(false);
                          reset();
                        }}
                      >
                        GHS · 当前仓库
                        <Icon name="Check" size={15} />
                      </button>
                      <p>
                        暂无其他仓库
                        <br />
                        接入后会显示在这里
                      </p>
                    </div>
                  )}
                </div>
                <div className="global-search">
                  <label>
                    <Icon name="Search" size={18} />
                    <input
                      id="global-search"
                      placeholder="搜索设备、货位或物料"
                      value={search}
                      onFocus={() => setSearchFocus(true)}
                      onChange={(e) => setSearch(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && results[0])
                          openResult(results[0]);
                        if (e.key === "Escape") setSearchFocus(false);
                      }}
                    />
                    <kbd>Ctrl K</kbd>
                  </label>
                  {searchFocus && (
                    <div className="search-results">
                      <div className="split">
                        <small>
                          GHS · {search ? "匹配结果" : "常用设备与货位"}
                        </small>
                        <button
                          className="icon-button"
                          aria-label="关闭搜索"
                          onClick={() => setSearchFocus(false)}
                        >
                          <Icon name="X" size={14} />
                        </button>
                      </div>
                      {results.length ? (
                        results.map((r) => (
                          <button key={r.label} onClick={() => openResult(r)}>
                            <Icon
                              name={
                                r.type === "device" ? "Forklift" : "Package"
                              }
                              size={17}
                            />
                            <span>
                              <strong>{r.label}</strong>
                              <small>{r.detail}</small>
                            </span>
                            <Icon name="ArrowUpRight" size={15} />
                          </button>
                        ))
                      ) : (
                        <p className="search-empty">
                          没有匹配结果，试试 AGV 或 A-03。
                        </p>
                      )}
                      <footer>Enter 定位首项 · Esc 收起</footer>
                    </div>
                  )}
                </div>
              </div>
              {replay.active && (
                <div className="replay-mode-pill">
                  <span className="status-dot" />
                  {replay.follow ? `跟随 ${replay.follow}` : "全时段设备回放"}
                  <Badge>测试回放</Badge>
                </div>
              )}
              <div className="scene-bottom-label">
                <Icon name="Mouse" size={14} />
                <span>
                  {replay.active
                    ? "拖动查看 · 滚轮缩放 · 点击设备跟随"
                    : "拖动平移 · 滚轮缩放 · 点击仓库查看内部"}
                </span>
                <span className="scene-demo-label">场景交互示意</span>
              </div>
              {replay.active && (
                <div className="timeline-host">
                  <ReplayTimeline
                    replay={replay}
                    setReplay={setReplay}
                    onEnd={endReplay}
                  />
                </div>
              )}
            </div>
            <nav className="icon-rail" aria-label="业务导航">
              <div>
                {nav.map(([id, title, icon, n]) => (
                  <button
                    key={id}
                    className={page === id ? "active" : ""}
                    aria-current={page === id ? "page" : undefined}
                    onClick={() => navigate(n)}
                    title={title}
                  >
                    <Icon name={icon} size={20} />
                    <span>{title}</span>
                    {id === "alerts" && <i />}
                  </button>
                ))}
              </div>
              <div className="view-tools">
                <button
                  aria-label="放大场景"
                  title="放大"
                  onClick={() => setZoom((z) => Math.min(1.8, z + 0.12))}
                >
                  <Icon name="Plus" />
                </button>
                <button
                  aria-label="缩小场景"
                  title="缩小"
                  onClick={() => setZoom((z) => Math.max(0.8, z - 0.12))}
                >
                  <Icon name="Minus" />
                </button>
                <button aria-label="重置全景视角" onClick={reset}>
                  <Icon name="Scan" />
                  <span>全景</span>
                </button>
              </div>
            </nav>
            <aside
              className="side-panel"
              aria-hidden={collapsed}
              inert={collapsed ? true : undefined}
            >
              {isGuide(screen) ? (
                <Guide screen={screen} onNavigate={navigate} />
              ) : page === "replay" ? (
                <ReplayPanel
                  initialState={screen}
                  replay={replay}
                  setReplay={setReplay}
                  notify={notify}
                  onEnd={endReplay}
                  onNavigate={commitScreen}
                />
              ) : page === "settings" ? (
                <Settings
                  settings={settings}
                  setSettings={setSettings}
                  roof={roof}
                  setRoof={setRoof}
                  notify={notify}
                />
              ) : (
                <BusinessPanels
                  page={page}
                  initialState={screen}
                  selectedEntity={
                    selection?.type === "device" ? selection.label : null
                  }
                  onNavigate={navigate}
                  onLocate={locate}
                  notify={notify}
                />
              )}
            </aside>
          </main>
        </div>
      )}
      <AnimatePresence>
        {directory && (
          <Directory
            current={screen}
            onClose={() => setDirectory(false)}
            onChoose={navigate}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {confirm && (
          <motion.div
            className="modal-scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="confirm-title"
              className="confirm-dialog"
              initial={{ scale: 0.97, y: 8 }}
              animate={{ scale: 1, y: 0 }}
            >
              <div className="confirm-symbol">
                <Icon name="History" size={24} />
              </div>
              <h2 id="confirm-title">{confirm.title}</h2>
              <p>{confirm.description}</p>
              <div className="dialog-actions">
                <Button variant="secondary" autoFocus onClick={cancelConfirm}>
                  继续追溯
                </Button>
                <Button
                  onClick={() => {
                    confirm.action();
                    setConfirm(null);
                  }}
                >
                  停止并继续
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {toast && (
          <motion.div
            className="toast"
            role="status"
            initial={{ y: 16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ opacity: 0, y: 8 }}
          >
            <Icon name="CircleCheck" size={18} />
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
