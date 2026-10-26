import React, { useEffect, useRef } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BatteryCharging,
  Bot,
  Boxes,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Circle,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  ClipboardList,
  Clock3,
  Crosshair,
  Focus,
  Forklift,
  History,
  Info,
  LayoutDashboard,
  LoaderCircle,
  MapPin,
  Minus,
  Monitor,
  MonitorCog,
  Mouse,
  Package,
  PanelRightClose,
  PanelRightOpen,
  PanelsTopLeft,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Scan,
  Search,
  SearchX,
  SlidersHorizontal,
  TriangleAlert,
  Truck,
  Warehouse,
} from "lucide-react";
const Icons = {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BatteryCharging,
  Bot,
  Boxes,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Circle,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  ClipboardList,
  Clock3,
  Crosshair,
  Focus,
  Forklift,
  History,
  Info,
  LayoutDashboard,
  LoaderCircle,
  MapPin,
  Minus,
  Monitor,
  MonitorCog,
  Mouse,
  Package,
  PanelRightClose,
  PanelRightOpen,
  PanelsTopLeft,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Scan,
  Search,
  SearchX,
  SlidersHorizontal,
  TriangleAlert,
  Truck,
  Warehouse,
};
import * as echarts from "echarts/core";
import {
  PieChart,
  BarChart,
  LineChart,
  GaugeChart,
  HeatmapChart,
} from "echarts/charts";
import {
  TooltipComponent,
  LegendComponent,
  GridComponent,
  TitleComponent,
  GraphicComponent,
  VisualMapComponent,
  DataZoomComponent,
  AriaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import CountUp from "./react-bits/CountUp";
echarts.use([
  PieChart,
  BarChart,
  LineChart,
  GaugeChart,
  HeatmapChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  TitleComponent,
  GraphicComponent,
  VisualMapComponent,
  DataZoomComponent,
  AriaComponent,
  CanvasRenderer,
]);
export function Icon({ name = "Circle", size = 18, ...props }) {
  const C = Icons[name] || Icons.Circle;
  return <C size={size} strokeWidth={1.7} aria-hidden="true" {...props} />;
}
export function Button({
  variant = "primary",
  children,
  className = "",
  ...props
}) {
  return (
    <button className={`button ${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}
export function Badge({ children, tone = "blue", className = "" }) {
  return <span className={`badge ${tone} ${className}`}>{children}</span>;
}
export function Metric({ label, value, unit, detail }) {
  const v = typeof value === "number" ? value : NaN;
  const previous = useRef(v);
  useEffect(() => {
    previous.current = v;
  }, [v]);
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {Number.isFinite(v) ? (
          <CountUp
            to={v}
            from={Number.isFinite(previous.current) ? previous.current : v}
            duration={0.45}
            separator=","
            trigger="load"
          />
        ) : (
          value
        )}
        {unit && <small>{unit}</small>}
      </div>
      {detail && <div className="metric-detail">{detail}</div>}
    </div>
  );
}
export function Section({ title, action, children, className = "" }) {
  return (
    <section className={`section ${className}`}>
      <div className="section-heading">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Empty({ title, description, action, onAction }) {
  return (
    <div className="empty">
      <Icon name="SearchX" size={30} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action && (
        <Button variant="secondary" onClick={onAction}>
          {action}
        </Button>
      )}
    </div>
  );
}
export function Chart({ option, height = 180, onClick, className = "" }) {
  const ref = useRef(null),
    chart = useRef(null);
  const callback = useRef(onClick);
  callback.current = onClick;
  useEffect(() => {
    const el = ref.current;
    const instance = echarts.init(el, null, { renderer: "canvas" });
    chart.current = instance;
    instance.on("click", (p) => callback.current?.(p));
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);
  useEffect(() => {
    chart.current?.setOption(
      {
        color: ["#356BFA", "#8CAFF5", "#CAD8ED", "#D1843C", "#C85852"],
        textStyle: {
          fontFamily: '"Noto Sans SC", "Microsoft YaHei", sans-serif',
          color: "#536478",
          fontSize: 12,
        },
        animationDuration: 450,
        animationDurationUpdate: 350,
        aria: { enabled: true },
        ...option,
      },
      { notMerge: true },
    );
  }, [option]);
  return (
    <div
      ref={ref}
      className={`echart ${className}`}
      style={{ height, width: "100%" }}
      role="img"
      aria-label={option?.title?.text || "可交互业务图表，悬停查看数据"}
    />
  );
}
