import React, { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Copy,
  ExternalLink,
  FileCode2,
  FileText,
  Globe2,
  Info,
  Layers3,
  Loader2,
  LockKeyhole,
  LogOut,
  Monitor,
  Play,
  Radio,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  Square,
  Users,
  Wifi,
  X,
} from "lucide-react";
import "./streaming.css";

const SESSION_SEED = [
  ["001", "Chrome · Windows", "192.168.150.21", "10:08:26", "32 分 14 秒"],
  ["002", "Edge · Windows", "192.168.150.36", "10:12:48", "27 分 52 秒"],
  ["003", "Chrome · macOS", "192.168.150.42", "10:20:11", "20 分 29 秒"],
  ["004", "Safari · macOS", "192.168.150.57", "10:25:03", "15 分 37 秒"],
  ["005", "Chrome · Windows", "192.168.150.68", "10:33:18", "07 分 22 秒"],
  ["006", "Edge · Windows", "192.168.150.79", "10:38:42", "01 分 58 秒"],
];
const DEFAULT_CONFIG = {
  resolution: "1920 × 1080",
  fps: "60",
  quality: "清晰优先",
  webPort: "8080",
  streamPort: "8889",
  codec: "H.264",
  bitrate: "20",
  retention: "60",
};
const CONNECT_STEPS = [
  "接入服务",
  "启动场景",
  "协商视频",
  "接收视频",
  "首帧就绪",
];
const BOUNDARIES = {
  ended: {
    icon: ShieldCheck,
    title: "管理员已结束连接",
    description:
      "本次会话已结束，您已与场景断开。如需继续访问，请手动重新连接。",
    notice: "管理员操作：结束本次连接。需要继续访问时，请重新连接。",
    action: "重新连接",
    foot: "自动重连已暂停，不会自动占用新会话。",
  },
  timeout: {
    icon: CircleAlert,
    title: "连接超时",
    description: "视频连接等待超过 120 秒，停留在“协商视频”阶段。",
    notice: "请检查网络连接，或联系管理员确认服务状态。",
    action: "重新连接",
    foot: "已保留当前仓库，重试会重新检查连接。",
  },
  stopped: {
    icon: Square,
    title: "像素流服务已暂停",
    description: "当前暂时无法进入场景，请在服务恢复后重新连接。",
    notice: "服务暂停维护，请稍后重新访问。",
    action: "检查服务状态",
    foot: "服务恢复后，可再次连接进入场景。",
  },
  recovering: {
    icon: RefreshCw,
    title: "正在恢复连接",
    description: "网络暂时中断，您的场景状态暂时保留。",
    notice: "将恢复原有会话，不会重复占用访问名额。",
    action: "恢复当前会话",
    foot: "当前为交互演示，可点击恢复继续体验。",
  },
  duplicate: {
    icon: Monitor,
    title: "会话已在其他标签页打开",
    description: "此页面的连接已结束。您可以返回原标签页，或在此重新进入。",
    notice: "为避免重复控制，当前页面已暂停自动重连。",
    action: "在此重新进入",
    foot: "继续后，将使用当前页面体验场景。",
  },
  playback: {
    icon: Play,
    title: "浏览器暂未允许播放",
    description: "连接已建立，但浏览器阻止了自动播放。允许播放后即可进入场景。",
    notice: "仅播放策略阻止时需要确认，正常访问会自动进入。",
    action: "允许播放",
    foot: "进入场景后默认静音。",
  },
};

function Action({ children, kind = "primary", className = "", ...props }) {
  return (
    <button className={`ss-button ss-${kind} ${className}`} {...props}>
      {children}
    </button>
  );
}
function Status({ children, tone = "blue" }) {
  return (
    <span className={`ss-status ss-tone-${tone}`}>
      <i />
      {children}
    </span>
  );
}
function Field({ label, children, hint, error }) {
  return (
    <label className={`ss-field ${error ? "ss-invalid" : ""}`}>
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
      {error && (
        <small role="alert" className="ss-error">
          {error}
        </small>
      )}
    </label>
  );
}
function FormSelect({ value, onChange, children, label, disabled }) {
  return (
    <span className="ss-select">
      <select
        aria-label={label}
        value={value}
        onChange={onChange}
        disabled={disabled}
      >
        {children}
      </select>
      <ChevronDown size={14} />
    </span>
  );
}
function Modal({ title, children, onClose, footer, busy = false }) {
  const dialogRef = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    dialogRef.current?.focus();
    return () => previous?.focus?.();
  }, []);
  return (
    <div
      className="ss-modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <section
        ref={dialogRef}
        tabIndex={-1}
        className="ss-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !busy) onClose();
          if (e.key === "Tab") {
            const f = [
              ...e.currentTarget.querySelectorAll(
                "button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled])",
              ),
            ];
            if (!f.length) {
              e.preventDefault();
              return;
            }
            const first = f[0],
              last = f[f.length - 1];
            if (
              e.shiftKey &&
              (document.activeElement === first ||
                document.activeElement === e.currentTarget)
            ) {
              last.focus();
              e.preventDefault();
            } else if (!e.shiftKey && document.activeElement === last) {
              first.focus();
              e.preventDefault();
            }
          }
        }}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="ss-icon-btn"
            aria-label="关闭对话框"
            disabled={busy}
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>
        <div className="ss-modal-content">{children}</div>
        <footer>{footer}</footer>
      </section>
    </div>
  );
}
function Header({ section, onNavigate }) {
  return (
    <header className="ss-header">
      <button className="ss-back" onClick={() => onNavigate(31)}>
        <ArrowLeft size={17} />
        <span>返回园区</span>
      </button>
      <div className="ss-brand">
        <span className="ss-logo">
          <i />
          <i />
          <i />
          <i />
        </span>
        <strong>GHS 仓储数字孪生</strong>
        <span className="ss-header-divider" />
        <span>{section}</span>
      </div>
      <div className="ss-header-actions">
        <span className="ss-demo-label">交互原型</span>
        <button onClick={() => onNavigate(25)}>本地启动器</button>
        <button onClick={() => onNavigate(42)}>
          <ShieldCheck size={15} />
          服务管理
        </button>
      </div>
    </header>
  );
}

export default function Streaming({
  screen = 35,
  onNavigate = () => {},
  notify = () => {},
}) {
  if ([42, 43].includes(Number(screen)))
    return (
      <Login
        key={screen}
        screen={Number(screen)}
        onNavigate={onNavigate}
        notify={notify}
      />
    );
  if ([28, 29, 40, 41].includes(Number(screen)))
    return (
      <Connection
        key={screen}
        screen={Number(screen)}
        onNavigate={onNavigate}
        notify={notify}
      />
    );
  if ([25, 26, 27].includes(Number(screen)))
    return (
      <Launcher
        key={screen}
        screen={Number(screen)}
        onNavigate={onNavigate}
        notify={notify}
      />
    );
  return (
    <Admin
      key={screen}
      screen={Number(screen)}
      onNavigate={onNavigate}
      notify={notify}
    />
  );
}

function Login({ screen, onNavigate, notify }) {
  const [account, setAccount] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(
    screen === 43 ? "账号或密码不正确，请重新输入。" : "",
  );
  const [busy, setBusy] = useState(false);
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  const login = (e) => {
    e.preventDefault();
    if (!account.trim() || !password.trim()) {
      setError("请填写账号和密码。");
      return;
    }
    setError("");
    setBusy(true);
    timer.current = setTimeout(() => {
      notify("已进入管理员演示会话");
      onNavigate(35);
    }, 650);
  };
  return (
    <div className="ss-app">
      <Header section="服务管理" onNavigate={onNavigate} />
      <main className="ss-login-layout">
        <div className="ss-login-story">
          <div className="ss-eyebrow">GHS / PIXEL STREAMING</div>
          <h1>
            一个入口，
            <br />
            连接整个仓库。
          </h1>
          <p>
            远端启停、参数配置与会话管理，
            <br />
            让每一位访问者拥有独立操作与视角。
          </p>
          <div className="ss-login-scene">
            <img src="/assets/campus.png" alt="GHS 仓库园区场景" />
            <span>
              <span className="ss-pulse-dot" />
              GHS · 园区场景
            </span>
          </div>
          <div className="ss-story-footer">
            <ShieldCheck size={17} />
            <span>独立会话</span>
            <span>·</span>
            <span>按需连接</span>
            <span>·</span>
            <span>集中管理</span>
          </div>
        </div>
        <section className="ss-login-card">
          <span className="ss-login-icon">
            <LockKeyhole size={23} />
          </span>
          <h2>管理员登录</h2>
          <p>登录后管理远端像素流服务</p>
          <form onSubmit={login}>
            <Field label="账号">
              <input
                name="account"
                autoComplete="username"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                placeholder="请输入管理员账号"
              />
            </Field>
            <Field label="密码" error={error}>
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError("");
                }}
                placeholder="请输入密码"
                aria-invalid={!!error}
              />
            </Field>
            <Action type="submit" disabled={busy} className="ss-full">
              {busy ? <Loader2 className="ss-spin" size={17} /> : null}
              {busy ? "正在进入…" : "登录"}
              {!busy && <ArrowRight size={17} />}
            </Action>
          </form>
          <div className="ss-login-note">
            <Info size={15} />
            <span>
              原型演示：填写任意非空账号与密码即可进入，不发送或保存凭据。
            </span>
          </div>
          <div className="ss-login-link">
            只想浏览仓库？
            <button onClick={() => onNavigate(28)}>
              打开场景连接页 <ArrowUpRight size={14} />
            </button>
          </div>
        </section>
      </main>
      <footer className="ss-page-footer">
        GHS 仓储数字孪生<span>管理与访问相互独立 · 当前为交互演示</span>
      </footer>
    </div>
  );
}

function Connection({ screen, onNavigate, notify }) {
  const [boundary, setBoundary] = useState(
    screen === 28
      ? ""
      : screen === 41
        ? "stopped"
        : screen === 29
          ? "timeout"
          : "ended",
  );
  const [step, setStep] = useState(0);
  const [round, setRound] = useState(0);
  const [help, setHelp] = useState(false);
  const [serviceChecked, setServiceChecked] = useState(false);
  useEffect(() => {
    if (boundary) return;
    setStep(0);
    let elapsed = 0;
    const interval = setInterval(() => {
      elapsed += 1;
      setStep(Math.min(elapsed, 5));
      if (elapsed >= 6) {
        clearInterval(interval);
        notify("连接演示完成，已进入园区原型");
        onNavigate(31);
      }
    }, 950);
    return () => clearInterval(interval);
  }, [boundary, round]);
  const reconnect = () => {
    setBoundary("");
    setRound((n) => n + 1);
  };
  const b = BOUNDARIES[boundary];
  const StateIcon = b?.icon || Radio;
  const handleAction = () => {
    if (boundary === "stopped" && !serviceChecked) {
      setServiceChecked(true);
      notify("演示检查完成：服务已恢复，可重新连接");
    } else if (boundary === "playback") {
      onNavigate(31);
    } else reconnect();
  };
  return (
    <div className="ss-app">
      <Header section="内网访问" onNavigate={onNavigate} />
      <main className="ss-connect-layout">
        <section className="ss-connect-scene">
          <img src="/assets/campus.png" alt="GHS 园区场景预览" />
          <div className="ss-scene-shade" />
          <div className="ss-connect-scene-title">
            <span className="ss-eyebrow">YOUR WAREHOUSE, CONNECTED</span>
            <h1>GHS</h1>
            <p>园区场景 · 仓储数字孪生</p>
            <span>场景预览 · 连接后进入交互画面</span>
          </div>
          <div className="ss-scene-caption">
            <Monitor size={16} />
            左键旋转<span>·</span>滚轮缩放<span>·</span>点击点位查看详情
          </div>
        </section>
        <section className="ss-connect-status">
          <span
            className={`ss-connection-icon ${!boundary ? "ss-connecting" : ""}`}
          >
            <StateIcon size={27} />
          </span>
          <h2>{b?.title || "正在连接仓库"}</h2>
          <p>{b?.description || "正在建立视频连接，请稍候。"}</p>
          {!boundary ? (
            <>
              <div className="ss-connect-progress-meta">
                <span>阶段 {Math.min(step + 1, 5)} / 5</span>
                <strong>
                  {step === 5
                    ? "已就绪"
                    : `已等待 ${String(step).padStart(2, "0")} 秒`}
                </strong>
              </div>
              <div className="ss-progress">
                <i style={{ width: `${((step + 1) * 100) / 6}%` }} />
              </div>
              <ol className="ss-connect-steps">
                {CONNECT_STEPS.map((name, i) => (
                  <li
                    key={name}
                    className={
                      step > i
                        ? "ss-step-done"
                        : step === i
                          ? "ss-step-active"
                          : ""
                    }
                  >
                    <span>
                      {step > i ? (
                        <Check size={13} />
                      ) : step === i ? (
                        <Loader2 size={13} className="ss-spin" />
                      ) : (
                        i + 1
                      )}
                    </span>
                    {name}
                    {step === i && <small>进行中</small>}
                    {step > i && <small>已完成</small>}
                  </li>
                ))}
              </ol>
              <p className="ss-connect-foot">
                画面就绪后自动进入，无需点击开始。
                <br />
                默认静音，进入后可开启声音。
              </p>
            </>
          ) : (
            <>
              <div className="ss-admin-notice">
                <strong>
                  {boundary === "ended" || boundary === "stopped"
                    ? "管理员通知"
                    : "连接说明"}
                </strong>
                <p>{b.notice}</p>
              </div>
              {serviceChecked && (
                <div className="ss-success-line">
                  <CheckCircle2 size={16} />
                  演示服务已恢复
                </div>
              )}
              <Action className="ss-full" onClick={handleAction}>
                {serviceChecked ? "重新连接" : b.action}
                <ArrowRight size={16} />
              </Action>
              <p className="ss-connect-foot">{b.foot}</p>
            </>
          )}
          <button
            className="ss-text-link ss-help-link"
            onClick={() => setHelp(!help)}
          >
            连接遇到问题？查看帮助 <ChevronDown size={14} />
          </button>
          {help && (
            <div className="ss-help-panel">
              确认浏览器与服务处于可达网络，检查服务是否正在运行。当前页面为本地原型，连接进度和提示均为演示，不会连接真实服务器。
              <button onClick={() => onNavigate(42)}>
                进入服务管理 <ArrowRight size={13} />
              </button>
            </div>
          )}
          {screen === 29 && (
            <div className="ss-state-picker">
              <label htmlFor="boundary-select">体验其他连接状态</label>
              <FormSelect
                label="连接边界状态"
                value={boundary || "connecting"}
                onChange={(e) => {
                  setBoundary(
                    e.target.value === "connecting" ? "" : e.target.value,
                  );
                  setServiceChecked(false);
                }}
              >
                <option value="connecting">自动连接</option>
                {Object.entries(BOUNDARIES).map(([key, value]) => (
                  <option value={key} key={key}>
                    {value.title}
                  </option>
                ))}
              </FormSelect>
            </div>
          )}
        </section>
      </main>
      <footer className="ss-page-footer">
        GHS / CONNECT<span>场景预览与连接反馈 · 原型演示</span>
      </footer>
    </div>
  );
}

function Admin({ screen, onNavigate, notify }) {
  const [running, setRunning] = useState(screen !== 36);
  const [sessions, setSessions] = useState(screen === 36 ? [] : SESSION_SEED);
  const [config, setConfig] = useState({ ...DEFAULT_CONFIG });
  const [applied, setApplied] = useState({ ...DEFAULT_CONFIG });
  const [savedConfig, setSavedConfig] = useState(null);
  const [advanced, setAdvanced] = useState(false);
  const [formError, setFormError] = useState("");
  const [status, setStatus] = useState("");
  const [modal, setModal] = useState(
    screen === 37
      ? { kind: "session", session: SESSION_SEED[0] }
      : screen === 38
        ? { kind: "service" }
        : null,
  );
  const [countdown, setCountdown] = useState(null);
  const [message, setMessage] = useState("");
  const [logs, setLogs] = useState(false);
  const [scenario, setScenario] = useState("");
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    setMessage(
      modal?.kind === "session"
        ? "管理员操作：结束本次连接。需要继续访问时，请重新连接。"
        : "服务即将暂停维护，请稍后重新访问。",
    );
  }, [modal]);
  const update = (key, value) => {
    setConfig((v) => ({ ...v, [key]: value }));
    setFormError("");
  };
  const validate = () => {
    const a = Number(config.webPort),
      b = Number(config.streamPort);
    if (![a, b].every((n) => Number.isInteger(n) && n >= 1 && n <= 65535))
      return "端口请输入 1–65535 之间的整数。";
    if (a === b) return "两个端口不能相同，请为像素流连接设置其他端口。";
    if (!(Number(config.bitrate) >= 1 && Number(config.bitrate) <= 100))
      return "目标码率请输入 1–100 Mbps。";
    if (!(Number(config.retention) >= 0 && Number(config.retention) <= 600))
      return "会话保留时间请输入 0–600 秒。";
    return "";
  };
  const save = () => {
    const error = validate();
    if (error) {
      setFormError(error);
      return;
    }
    setSavedConfig({ ...config });
    notify(
      running ? "参数已保存，下次启动服务时生效" : "参数已保存，可启动服务",
    );
  };
  const start = () => {
    const error = validate();
    if (error) {
      setFormError(error);
      return;
    }
    if (scenario === "start-failed") {
      setStatus("start-failed");
      return;
    }
    setStatus("starting");
    timer.current = setTimeout(() => {
      setRunning(true);
      setApplied({ ...config });
      setSavedConfig(null);
      setSessions([]);
      setStatus("");
      setScenario("");
      notify("演示服务已启动，等待用户连接");
    }, 1400);
  };
  const confirmEnd = () => {
    if (!message.trim()) {
      notify("请填写给用户的通知");
      return;
    }
    setCountdown(5);
    const target = modal;
    const tick = (remaining) => {
      if (remaining <= 0) {
        if (target.kind === "session") {
          setSessions((rows) => rows.filter((s) => s[0] !== target.session[0]));
          notify(`已结束访客 ${target.session[0]} 的演示连接`);
        } else {
          setSessions([]);
          if (scenario === "stop-failed") {
            setStatus("stop-failed");
            setRunning(false);
          } else {
            setRunning(false);
            setStatus("");
          }
          notify("服务维护通知已发送，演示会话已断开");
        }
        setModal(null);
        setCountdown(null);
        return;
      }
      setCountdown(remaining);
      timer.current = setTimeout(() => tick(remaining - 1), 1000);
    };
    tick(5);
  };
  const copyAddress = async () => {
    try {
      await navigator.clipboard.writeText(
        `http://192.168.150.14:${applied.webPort}`,
      );
      notify("已复制设计稿中的示例访问地址");
    } catch {
      notify("示例访问地址：http://192.168.150.14:" + applied.webPort);
    }
  };
  const selectScenario = (kind) => {
    clearTimeout(timer.current);
    setCountdown(null);
    setModal(null);
    setStatus("");
    setScenario(kind);
    if (kind === "invalid-ports") {
      setConfig((c) => ({ ...c, webPort: "8080", streamPort: "8080" }));
      setFormError("两个端口不能相同，请为像素流连接设置其他端口。");
    } else if (kind === "start-failed") {
      setRunning(false);
      setSessions([]);
      setStatus("start-failed");
    } else if (kind === "empty") {
      setRunning(true);
      setSessions([]);
    } else if (kind === "stop-failed") {
      setRunning(false);
      setSessions([]);
      setStatus("stop-failed");
    } else if (kind === "saved") {
      setRunning(true);
      setConfig((c) => ({ ...c, fps: "30" }));
      setSavedConfig({ ...config, fps: "30" });
    } else if (kind === "notice") {
      setModal({ kind: "session", session: SESSION_SEED[0] });
      setSessions(SESSION_SEED);
    } else if (kind === "advanced") setAdvanced(true);
  };
  return (
    <div className="ss-app">
      <Header section="服务管理" onNavigate={onNavigate} />
      <main className="ss-admin-main">
        <div className="ss-page-heading">
          <div>
            <div className="ss-eyebrow">GHS / OPERATIONS</div>
            <h1>像素流服务管理</h1>
            <p>管理远端服务，让每位访问者拥有独立的操作与视角。</p>
          </div>
          <div className="ss-admin-meta">
            <span>
              <Server size={15} />
              192.168.150.14
            </span>
            <button onClick={() => onNavigate(42)}>
              <LogOut size={15} />
              退出
            </button>
          </div>
        </div>
        <section className="ss-service-card">
          <div className="ss-service-preview">
            <img src="/assets/campus.png" alt="GHS 园区服务场景" />
            <span>GHS · 园区场景</span>
          </div>
          <div className="ss-service-summary">
            <div className="ss-service-title">
              <h2>GHS · 园区场景</h2>
              <Status
                tone={
                  status.includes("failed") ? "red" : running ? "green" : "gray"
                }
              >
                {status === "starting"
                  ? "启动中"
                  : status === "start-failed"
                    ? "启动失败"
                    : status === "stop-failed"
                      ? "停止失败"
                      : running
                        ? "运行中"
                        : "已停止"}
              </Status>
            </div>
            <p>
              {running
                ? `${sessions.length} 位用户在线 · ${applied.resolution} / ${applied.fps} FPS`
                : "服务已停止，访问者暂时无法进入场景。"}
            </p>
            <div className="ss-address-line">
              <Globe2 size={15} />
              <span>http://192.168.150.14:{applied.webPort}</span>
              <button
                className="ss-icon-btn"
                aria-label="复制示例访问地址"
                onClick={copyAddress}
              >
                <Copy size={14} />
              </button>
            </div>
          </div>
          <div className="ss-service-actions">
            <Action
              kind="secondary"
              onClick={() => onNavigate(running ? 28 : 41)}
            >
              <ExternalLink size={15} />
              打开访问页
            </Action>
            {running ? (
              <Action
                kind="danger"
                onClick={() => setModal({ kind: "service" })}
              >
                <Square size={14} />
                停止服务
              </Action>
            ) : (
              <Action
                onClick={start}
                disabled={status === "starting" || status === "stop-failed"}
              >
                {status === "starting" ? (
                  <Loader2 size={15} className="ss-spin" />
                ) : (
                  <Play size={15} />
                )}
                {status === "starting" ? "正在启动…" : "启动服务"}
              </Action>
            )}
            <small>
              {running ? "已运行 02:36:18" : "等待启动"} · 每人独立会话
            </small>
          </div>
        </section>
        {status.includes("failed") && (
          <div role="alert" className="ss-feedback ss-feedback-error">
            <CircleAlert size={21} />
            <div>
              <strong>
                {status === "start-failed"
                  ? "服务启动失败"
                  : "服务未能完全停止"}
              </strong>
              <p>
                {status === "start-failed"
                  ? "网页访问端口 8080 已被占用，请修改端口后重新启动。"
                  : "用户已断开，仍有 1 个场景进程未退出，当前暂不接收新连接。"}
              </p>
            </div>
            <Action
              kind="secondary"
              onClick={() => {
                if (status === "stop-failed") {
                  setStatus("");
                  setScenario("");
                  notify("演示进程已退出，可以重新启动");
                } else {
                  update("webPort", "8081");
                  setScenario("");
                  setStatus("");
                  notify("示例端口已改为 8081，请重新启动");
                }
              }}
            >
              {status === "stop-failed" ? "重试停止" : "修改参数"}
            </Action>
          </div>
        )}
        {savedConfig && (
          <div className="ss-feedback">
            <CheckCircle2 size={21} />
            <div>
              <strong>参数已保存{running ? "，待下次启动" : ""}</strong>
              <p>
                当前：{applied.resolution} / {applied.fps} FPS{" "}
                <span className="ss-feedback-arrow">→</span> 下次启动：
                {savedConfig.resolution} / {savedConfig.fps} FPS
              </p>
            </div>
            <span>当前用户连接不会中断</span>
          </div>
        )}
        {screen === 39 && (
          <div className="ss-scenario-toolbar">
            <span>
              <Layers3 size={15} />
              体验反馈状态
            </span>
            {[
              ["start-failed", "启动失败"],
              ["saved", "参数已保存"],
              ["invalid-ports", "端口校验"],
              ["advanced", "高级参数"],
              ["empty", "暂无用户"],
              ["stop-failed", "停止失败"],
              ["notice", "断开通知"],
            ].map(([id, label]) => (
              <button
                className={scenario === id ? "active" : ""}
                key={id}
                onClick={() => selectScenario(id)}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        <div className="ss-admin-grid">
          <section className="ss-card ss-parameters">
            <div className="ss-card-heading">
              <div>
                <h2>
                  <Settings2 size={18} />
                  服务参数
                </h2>
                <p>
                  {running ? "应用于下一次服务启动" : "启动服务时使用以下参数"}
                </p>
              </div>
            </div>
            <Field label="分辨率">
              <FormSelect
                label="流送分辨率"
                value={config.resolution}
                onChange={(e) => update("resolution", e.target.value)}
              >
                {[
                  "1280 × 720",
                  "1920 × 1080",
                  "2560 × 1440",
                  "3840 × 2160",
                ].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </FormSelect>
            </Field>
            <Field label="目标帧率">
              <div className="ss-segment" role="group" aria-label="目标帧率">
                {["30", "60"].map((v) => (
                  <button
                    key={v}
                    className={config.fps === v ? "selected" : ""}
                    onClick={() => update("fps", v)}
                  >
                    {v} FPS
                  </button>
                ))}
              </div>
            </Field>
            <Field label="画质预设">
              <FormSelect
                label="画质预设"
                value={config.quality}
                onChange={(e) => update("quality", e.target.value)}
              >
                {["流畅优先", "清晰优先", "超清优先"].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </FormSelect>
            </Field>
            <div className="ss-field-pair">
              <Field label="网页访问端口">
                <input
                  aria-label="网页访问端口"
                  inputMode="numeric"
                  value={config.webPort}
                  onChange={(e) => update("webPort", e.target.value)}
                />
              </Field>
              <Field label="像素流连接端口">
                <input
                  aria-label="像素流连接端口"
                  inputMode="numeric"
                  value={config.streamPort}
                  onChange={(e) => update("streamPort", e.target.value)}
                />
              </Field>
            </div>
            {formError && (
              <p className="ss-error" role="alert">
                {formError}
              </p>
            )}
            <button
              className="ss-advanced-toggle"
              aria-expanded={advanced}
              onClick={() => setAdvanced(!advanced)}
            >
              高级参数
              <ChevronDown
                size={16}
                style={{ transform: advanced ? "rotate(180deg)" : "" }}
              />
            </button>
            {advanced && (
              <div className="ss-advanced-fields">
                <Field label="视频编码">
                  <FormSelect
                    label="视频编码"
                    value={config.codec}
                    onChange={(e) => update("codec", e.target.value)}
                  >
                    <option>H.264</option>
                    <option>AV1</option>
                    <option>VP9</option>
                  </FormSelect>
                </Field>
                <Field label="目标码率 / Mbps">
                  <input
                    aria-label="目标码率"
                    type="number"
                    min="1"
                    max="100"
                    value={config.bitrate}
                    onChange={(e) => update("bitrate", e.target.value)}
                  />
                </Field>
                <Field label="断开后会话保留 / 秒">
                  <input
                    aria-label="会话保留时间"
                    type="number"
                    min="0"
                    max="600"
                    value={config.retention}
                    onChange={(e) => update("retention", e.target.value)}
                  />
                </Field>
              </div>
            )}
            <div className="ss-parameter-note">
              <Info size={15} />
              <span>保存不会中断当前用户，下次启动服务时生效。</span>
            </div>
            <Action className="ss-full" onClick={save}>
              <Check size={16} />
              保存参数
            </Action>
          </section>
          <section className="ss-card ss-sessions">
            <div className="ss-card-heading">
              <div>
                <h2>
                  在线用户 <span className="ss-count">{sessions.length}</span>
                </h2>
                <p>结束连接前将通知该用户，其他用户不受影响。</p>
              </div>
              <Status tone={running ? "green" : "gray"}>
                {running ? "服务可用" : "服务暂停"}
              </Status>
            </div>
            {sessions.length ? (
              <div className="ss-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>用户 / 会话</th>
                      <th>IP 地址</th>
                      <th>连接时间</th>
                      <th>已连接</th>
                      <th>状态</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s) => (
                      <tr key={s[0]}>
                        <td>
                          <span className="ss-user-name">
                            <span className="ss-user-avatar">
                              <Monitor size={16} />
                            </span>
                            <span>
                              <strong>访客 {s[0]}</strong>
                              <small>{s[1]}</small>
                            </span>
                          </span>
                        </td>
                        <td className="ss-mono">{s[2]}</td>
                        <td>{s[3]}</td>
                        <td>{s[4]}</td>
                        <td>
                          <Status tone="green">已连接</Status>
                        </td>
                        <td>
                          <button
                            className="ss-row-action"
                            onClick={() =>
                              setModal({ kind: "session", session: s })
                            }
                          >
                            结束连接
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="ss-empty">
                <Users size={34} />
                <h3>{running ? "服务运行中，暂无用户" : "服务尚未启动"}</h3>
                <p>
                  {running
                    ? "分享用户访问地址，连接建立后会显示在这里。"
                    : "启动服务后，在这里查看和管理连接用户。"}
                </p>
                <Action
                  kind="secondary"
                  onClick={running ? copyAddress : start}
                  disabled={status === "starting" || status === "stop-failed"}
                >
                  {running ? "复制访问地址" : "启动服务"}
                </Action>
              </div>
            )}
            <div className="ss-table-footer">
              <span>
                共 {sessions.length} 位在线用户 <em>演示会话</em>
              </span>
              <button
                onClick={() => {
                  if (!running) {
                    notify("请先启动服务");
                    return;
                  }
                  setSessions(SESSION_SEED);
                  notify("已恢复 6 位演示用户");
                }}
              >
                <RefreshCw size={13} />
                刷新示例
              </button>
            </div>
          </section>
        </div>
        <div className="ss-admin-bottom">
          <Info size={15} />
          <span>停止像素流服务后，此管理页面仍可访问。</span>
          <button onClick={() => setLogs(true)}>
            <FileText size={14} />
            查看运行日志
          </button>
        </div>
      </main>
      <footer className="ss-page-footer">
        GHS / PIXEL STREAMING<span>演示数据 · 本页操作仅影响原型</span>
      </footer>
      {modal && (
        <Modal
          title={
            modal.kind === "session"
              ? "结束这位用户的连接？"
              : "停止像素流服务？"
          }
          onClose={() => setModal(null)}
          busy={countdown !== null}
          footer={
            countdown !== null ? (
              <Action disabled>
                <Loader2 size={16} className="ss-spin" />
                正在通知并断开…
              </Action>
            ) : (
              <>
                <Action kind="secondary" onClick={() => setModal(null)}>
                  取消
                </Action>
                <Action kind="danger" onClick={confirmEnd}>
                  通知并{modal.kind === "session" ? "结束连接" : "停止服务"}
                </Action>
              </>
            )
          }
        >
          <p>
            {modal.kind === "session"
              ? `仅结束访客 ${modal.session[0]} 的本次会话，其他用户继续使用。`
              : `当前 ${sessions.length} 位在线用户将被断开，新的访问者暂时无法进入。`}
          </p>
          <div className="ss-modal-target">
            <Monitor size={22} />
            <span>
              <strong>
                {modal.kind === "session"
                  ? `访客 ${modal.session[0]} · ${modal.session[2]}`
                  : "GHS · 园区场景"}
              </strong>
              <small>
                {modal.kind === "session"
                  ? modal.session[1]
                  : `${sessions.length} 位用户在线 · 所有会话`}
              </small>
            </span>
          </div>
          {countdown !== null ? (
            <div className="ss-countdown" role="status">
              <strong>{countdown}</strong>
              <p>通知已发送，{countdown} 秒后断开连接</p>
            </div>
          ) : (
            <Field label="给用户的通知">
              <textarea
                rows="3"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </Field>
          )}
          <div className="ss-parameter-note">
            <Info size={15} />
            <span>
              先发送通知，5 秒后断开。用户需手动重新连接，管理页面保持可用。
            </span>
          </div>
        </Modal>
      )}
      {logs && (
        <Modal
          title="服务日志 · 演示"
          onClose={() => setLogs(false)}
          footer={
            <Action kind="secondary" onClick={() => setLogs(false)}>
              关闭
            </Action>
          }
        >
          <pre className="ss-log">
            10:08:20 服务配置检查完成{"\n"}10:08:25 像素流场景准备就绪{"\n"}
            10:08:26 访客 001 建立独立会话{"\n"}10:38:42 访客 006 建立独立会话
            {"\n"}10:40:40 当前会话数：{sessions.length}
            {"\n"}当前状态：{running ? "运行中" : "已停止"}
          </pre>
          <p className="ss-small">原型演示日志，不读取服务器或本机文件。</p>
        </Modal>
      )}
    </div>
  );
}

function Launcher({ screen, onNavigate, notify }) {
  const [running, setRunning] = useState(screen === 26);
  const [program, setProgram] = useState(
    "App/Windows/Test/Binaries/Win64/TestGame.exe",
  );
  const [webPort, setWebPort] = useState("8080");
  const [streamPort, setStreamPort] = useState("8888");
  const [resolution, setResolution] = useState("1920 × 1080");
  const [quality, setQuality] = useState("清晰优先");
  const [mode, setMode] = useState("independent");
  const [localWindow, setLocalWindow] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [error, setError] = useState(
    screen === 27 ? "端口 8080 已被占用，请更换端口。" : "",
  );
  const [stage, setStage] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [bitrate, setBitrate] = useState("35");
  const fileRef = useRef();
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  const detect = () => {
    if (
      ![webPort, streamPort].every(
        (v) => /^\d+$/.test(v) && +v > 0 && +v < 65536,
      )
    ) {
      setError("请输入 1–65535 之间的整数端口。");
      return false;
    }
    if (webPort === streamPort) {
      setError("网页端口和串流端口不能相同。");
      return false;
    }
    if (screen === 27 && webPort === "8080") {
      setError("端口 8080 已被占用，请更换端口，例如 8081。");
      return false;
    }
    if (!program.trim()) {
      setError("找不到流送程序，请重新选择。");
      return false;
    }
    if (!(Number(bitrate) >= 12 && Number(bitrate) <= 60)) {
      setError("起始码率请输入 12–60 Mbps。");
      return false;
    }
    setError("");
    return true;
  };
  const start = () => {
    if (!detect()) return;
    setStage("starting");
    timer.current = setTimeout(() => {
      setRunning(true);
      setStage("");
      notify("启动演示完成，已生成示例访问地址");
    }, 1500);
  };
  const stop = () => {
    setConfirm(false);
    setStage("stopping");
    timer.current = setTimeout(() => {
      setRunning(false);
      setStage("");
      notify("演示服务和会话已停止");
    }, 1000);
  };
  const pickFile = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setProgram(file.name);
      setError("");
      notify("已选择文件名，仅用于原型展示，不会上传或执行");
    }
  };
  return (
    <div className="ss-app">
      <Header section="本地启动器" onNavigate={onNavigate} />
      <main className="ss-launch-main">
        <div className="ss-page-heading">
          <div>
            <div className="ss-eyebrow">GHS / LAUNCHER</div>
            <h1>像素流服务启动器</h1>
            <p>配置流送程序，启动后分享内网访问地址。</p>
          </div>
          <Status tone={running ? "green" : "gray"}>
            {stage === "starting"
              ? "正在启动"
              : stage === "stopping"
                ? "正在停止"
                : running
                  ? "服务运行中"
                  : "服务未启动"}
          </Status>
        </div>
        <div className="ss-launch-grid">
          <section className="ss-card ss-launch-config">
            <div className="ss-card-heading">
              <div>
                <h2>服务配置</h2>
                <p>
                  {running
                    ? "服务运行中，停止服务后可修改配置。"
                    : "启动时自动保存当前配置。"}
                </p>
              </div>
              <Settings2 size={20} />
            </div>
            <fieldset disabled={running || !!stage}>
              <Field label="流送程序">
                <span className="ss-program-input">
                  <input
                    aria-label="流送程序路径"
                    value={program}
                    onChange={(e) => {
                      setProgram(e.target.value);
                      setError("");
                    }}
                  />
                  <button
                    onClick={() => fileRef.current?.click()}
                    type="button"
                  >
                    选择程序
                  </button>
                </span>
                <input
                  type="file"
                  accept=".exe"
                  ref={fileRef}
                  onChange={pickFile}
                  hidden
                />
              </Field>
              <div className="ss-toggle-row">
                <span>
                  <strong>显示本地程序窗口</strong>
                  <small>关闭后在后台渲染，网页仍可访问</small>
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-label="显示本地程序窗口"
                  aria-checked={localWindow}
                  className={`ss-toggle ${localWindow ? "on" : ""}`}
                  onClick={() => setLocalWindow(!localWindow)}
                >
                  <i />
                </button>
              </div>
              <div className="ss-field-pair">
                <Field label="网页端口">
                  <input
                    aria-label="启动器网页端口"
                    value={webPort}
                    onChange={(e) => {
                      setWebPort(e.target.value);
                      setError("");
                    }}
                  />
                </Field>
                <Field label="串流端口">
                  <input
                    aria-label="启动器串流端口"
                    value={streamPort}
                    onChange={(e) => {
                      setStreamPort(e.target.value);
                      setError("");
                    }}
                  />
                </Field>
              </div>
              <div className={`ss-port-feedback ${error ? "ss-error" : ""}`}>
                {error ? <CircleAlert size={14} /> : <CheckCircle2 size={14} />}
                <span>
                  {error ||
                    (running
                      ? `${webPort} / ${streamPort} 已监听`
                      : "端口配置有效")}
                </span>
                <button
                  onClick={() => {
                    if (detect()) notify("演示端口检测通过");
                  }}
                >
                  重新检测
                </button>
              </div>
              <div className="ss-field-pair">
                <Field label="流送分辨率">
                  <FormSelect
                    value={resolution}
                    label="启动器分辨率"
                    onChange={(e) => setResolution(e.target.value)}
                  >
                    {["1280 × 720", "1920 × 1080", "2560 × 1440"].map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </FormSelect>
                </Field>
                <Field label="画面质量">
                  <FormSelect
                    value={quality}
                    label="启动器画面质量"
                    onChange={(e) => setQuality(e.target.value)}
                  >
                    {["流畅优先", "清晰优先", "超清优先"].map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </FormSelect>
                </Field>
              </div>
              <Field label="访问模式">
                <div className="ss-mode-options">
                  {[
                    ["shared", "共享场景", "同一场景，共享操作与视角"],
                    ["independent", "每人独立", "独立场景，视角与操作互不影响"],
                  ].map(([id, title, desc]) => (
                    <button
                      key={id}
                      type="button"
                      className={mode === id ? "selected" : ""}
                      aria-pressed={mode === id}
                      onClick={() => setMode(id)}
                    >
                      <span className="ss-radio-dot" />
                      <strong>{title}</strong>
                      <small>{desc}</small>
                    </button>
                  ))}
                </div>
              </Field>
              <p className="ss-small">
                本地启动器最多同时 3 位。第 4 位进入时，通知并断开最早访问者。
              </p>
              <button
                className="ss-advanced-toggle"
                onClick={() => setAdvanced(!advanced)}
                aria-expanded={advanced}
              >
                高级画面参数
                <ChevronDown
                  size={16}
                  style={{ transform: advanced ? "rotate(180deg)" : "" }}
                />
              </button>
              {advanced && (
                <div className="ss-advanced-fields">
                  <Field
                    label="起始码率 / Mbps"
                    hint="最低 12 / 最高 60 Mbps · 帧率上限 60 FPS"
                  >
                    <input
                      aria-label="起始码率"
                      type="number"
                      min="12"
                      max="60"
                      value={bitrate}
                      onChange={(e) => setBitrate(e.target.value)}
                    />
                  </Field>
                  <p className="ss-small">
                    按连接人数分配资源。画质档位不承诺固定帧率。
                  </p>
                </div>
              )}
            </fieldset>
          </section>
          <section className="ss-card ss-launch-preview">
            <div className="ss-launch-image">
              <img src="/assets/campus.png" alt="GHS 场景预览" />
              <div>
                <strong>GHS · 园区场景</strong>
                <span>场景预览</span>
              </div>
            </div>
            <div className="ss-launch-preview-body">
              {stage ? (
                <div className="ss-launch-idle">
                  <Loader2 size={29} className="ss-spin" />
                  <h2>
                    {stage === "starting" ? "正在启动服务" : "正在停止服务"}
                  </h2>
                  <p>
                    {stage === "starting"
                      ? "检查端口 → 开启流送服务 → 准备场景"
                      : "断开访问 → 关闭本次启动的程序 → 回收服务"}
                  </p>
                </div>
              ) : running ? (
                <>
                  <div className="ss-preview-status">
                    <Status tone="green">服务运行中</Status>
                    <span>2 / 3 在线</span>
                  </div>
                  <label className="ss-address-label">内网访问地址</label>
                  <div className="ss-launch-address">
                    http://172.16.11.175:{webPort}
                  </div>
                  <Action className="ss-full" onClick={() => onNavigate(28)}>
                    打开网页 <ArrowUpRight size={16} />
                  </Action>
                  <div className="ss-launch-sessions">
                    <header>
                      <strong>在线会话</strong>
                      <span>实际 / 当前目标 FPS</span>
                    </header>
                    {[
                      ["01", "10:24", "31.2 / 30"],
                      ["02", "10:26", "30.1 / 30"],
                    ].map(([id, time, fps]) => (
                      <div key={id}>
                        <span>
                          <Monitor size={16} />
                          会话 {id}
                          <small>{time} 进入</small>
                        </span>
                        <strong>{fps}</strong>
                      </div>
                    ))}
                  </div>
                  <p className="ss-small">
                    当前按 2 个
                    {mode === "independent" ? "独立场景" : "共享访问"}
                    分配资源。实际帧率取决于负载。
                  </p>
                </>
              ) : (
                <div className="ss-launch-idle">
                  <Radio size={30} />
                  <h2>服务未启动</h2>
                  <p>
                    启动后生成内网访问地址，
                    <br />
                    同一内网的电脑可通过浏览器访问。
                  </p>
                  <button
                    className="ss-text-link"
                    onClick={() =>
                      notify(
                        "演示配置：允许网页端口与串流端口在内网访问，无需修改本机防火墙。",
                      )
                    }
                  >
                    配置内网访问 <ArrowRight size={14} />
                  </button>
                </div>
              )}
            </div>
          </section>
        </div>
        <div className="ss-launch-bottom">
          <button onClick={() => setShowLogs(true)}>
            <FileText size={17} />
            服务日志
          </button>
          <span>
            {running
              ? "停止将断开访问并关闭本次启动的程序"
              : "启动时自动保存配置"}
          </span>
          <Action
            disabled={!!stage}
            kind={running ? "danger" : "primary"}
            onClick={running ? () => setConfirm(true) : start}
          >
            {stage ? (
              <Loader2 size={16} className="ss-spin" />
            ) : running ? (
              <Square size={15} />
            ) : (
              <Play size={15} />
            )}
            {stage ? "处理中…" : running ? "停止服务" : "启动服务"}
          </Action>
        </div>
      </main>
      <footer className="ss-page-footer">
        GHS / LOCAL LAUNCHER<span>配置与流程演示 · 不会启动本地程序</span>
      </footer>
      {confirm && (
        <Modal
          title="停止像素流服务？"
          onClose={() => setConfirm(false)}
          footer={
            <>
              <Action kind="secondary" onClick={() => setConfirm(false)}>
                继续运行
              </Action>
              <Action kind="danger" onClick={stop}>
                停止服务
              </Action>
            </>
          }
        >
          <p>当前 2 位访问者将断开连接，本次启动的服务及程序将一并关闭。</p>
        </Modal>
      )}
      {showLogs && (
        <Modal
          title="服务日志 · 演示"
          onClose={() => setShowLogs(false)}
          footer={
            <Action kind="secondary" onClick={() => setShowLogs(false)}>
              关闭
            </Action>
          }
        >
          <pre className="ss-log">
            10:24:00 已保存启动配置{"\n"}10:24:01 端口检查：{webPort} /{" "}
            {streamPort}
            {"\n"}10:24:02 独立场景准备完成{"\n"}10:26:04 访问模式：
            {mode === "independent" ? "每人独立" : "共享场景"}
            {"\n"}当前：{running ? "2 位演示会话" : "服务未启动"}
          </pre>
          <p className="ss-small">本地原型不读取或生成真实服务日志。</p>
        </Modal>
      )}
    </div>
  );
}
