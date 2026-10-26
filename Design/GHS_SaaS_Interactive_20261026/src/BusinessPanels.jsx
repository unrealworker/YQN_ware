import React, { useEffect, useState } from "react";
import { Chart, Badge, Button, Icon, Metric, Empty, Section } from "./ui.jsx";
import "./business.css";

const blue = "#356BFA",
  ink = "#172f50";
const numbers = new Intl.NumberFormat("zh-CN");
const regions = [
  "GHS-R · 货架",
  "GHS-SR",
  "GHS-T",
  "GHS-MOVE · 转仓",
  "GHS-HL · 恒林",
  "GHS-WALL01 · 靠墙",
  "GHS-G · 地堆",
  "GHS-DG · 地柜",
  "GHS-DOCK01 · 暂存",
  "GHS-TEMP · 退货",
];
const stockSamples = [
  ["8551268", 10, 10],
  ["7111566", 0, 0],
  ["8556512", 4, 3],
  ["8703069", 1, 0],
  ["10274458", -1, -1],
];
const orderRows = {
  out: [
    ["OUT-20261020-121", "SKU2038", "电机安装支架", 0, 120, "待拣货"],
    ["OUT-20261020-119", "SKU2041", "直线导轨", 160, 240, "装车中"],
    ["OUT-20261020-155", "SKU3072", "缓冲垫", 0, 800, "待作业"],
    ["OUT-20261020-156", "SKU2066", "铝型材接头", 0, 360, "异常 · 月台占用"],
  ],
  in: [
    ["IN-20261020-096", "SKU2038", "电机安装支架", 480, 480, "已完成"],
    ["IN-20261020-118", "SKU2041", "直线导轨", 240, 400, "上架中"],
    ["IN-20261020-127", "SKU3072", "缓冲垫", 0, 600, "待收货"],
    ["IN-20261020-128", "SKU2066", "铝型材接头", 0, 360, "异常 · 质检待复核"],
  ],
};
const sceneDevices = [
  {
    id: "AGV-07",
    kind: "搬运机器人",
    status: "运行",
    area: "充电区 C · CH-07",
    battery: 82,
    speed: "1.2 m/s",
  },
  {
    id: "AGV-08",
    kind: "搬运机器人",
    status: "待机",
    area: "充电区 C · CH-08",
    battery: null,
    speed: null,
  },
  {
    id: "AGV-12",
    kind: "搬运机器人",
    status: "低电量",
    area: "货架区 A · 主通道",
    battery: 18,
    speed: "0.8 m/s",
  },
  {
    id: "FORK-01",
    kind: "人工叉车",
    status: "运行",
    area: "A 区 · A-03-12",
    battery: null,
    speed: "5.0 km/h",
  },
  {
    id: "STACKER-01",
    kind: "电动堆高车",
    status: "运行",
    area: "地堆区 B",
    battery: 82,
    speed: "2.4 km/h",
  },
  {
    id: "TRUCK-002",
    kind: "装卸车辆",
    status: "装载中",
    area: "DOCK-02",
    battery: null,
    speed: "0 km/h",
  },
];
const facilities = [
  ["CH-07", "充电中", "AGV-03", "18.6 kW", "37%"],
  ["CH-12", "空闲", null, "0.0 kW", "—"],
  ["CH-19", "充电中", "AGV-16", "22.0 kW", "68%"],
  ["CH-52", "离线", null, "— kW", "—"],
];
const initialAlerts = [
  {
    id: "STACKER-04",
    name: "货叉举升异常",
    level: "故障",
    time: "13:48:25",
    confirmed: true,
  },
  {
    id: "TRUCK-042",
    name: "驱动异常",
    level: "故障",
    time: "14:03:16",
    confirmed: false,
  },
  {
    id: "FORK-07",
    name: "行驶速度预警",
    level: "预警",
    time: "14:08:50",
    confirmed: false,
  },
  {
    id: "FORK-12",
    name: "行驶速度预警",
    level: "预警",
    time: "13:56:22",
    confirmed: true,
  },
  {
    id: "TRUCK-009",
    name: "超速预警",
    level: "预警",
    time: "14:10:05",
    confirmed: false,
  },
  {
    id: "TRUCK-016",
    name: "发动机温度偏高",
    level: "预警",
    time: "13:44:30",
    confirmed: true,
  },
  {
    id: "AGV-12",
    name: "低电量 18%",
    level: "预警",
    time: "14:18:32",
    confirmed: false,
  },
];

function DemoNote({ children = "场景示例 · 数据未核验" }) {
  return (
    <p className="biz-note">
      <Icon name="Info" size={14} />
      {children}
    </p>
  );
}
function Header({ title, description, badge = "示例数据", back, onBack }) {
  return (
    <header className="biz-header">
      {back && (
        <button className="biz-back" onClick={onBack}>
          <Icon name="ArrowLeft" size={15} />
          {back}
        </button>
      )}
      <div className="biz-title-row">
        <h1>{title}</h1>
        {badge && (
          <Badge tone={badge === "台账数据" ? "blue" : "orange"}>{badge}</Badge>
        )}
      </div>
      {description && <p>{description}</p>}
    </header>
  );
}
function Tabs({ items, value, onChange, label }) {
  return (
    <div className="biz-tabs" role="tablist" aria-label={label}>
      {items.map((i) => (
        <button
          key={i[0]}
          role="tab"
          aria-selected={value === i[0]}
          className={value === i[0] ? "active" : ""}
          onClick={() => onChange(i[0])}
        >
          {i[1]}
        </button>
      ))}
    </div>
  );
}
function Search({ value, onChange, placeholder }) {
  return (
    <label className="biz-search">
      <Icon name="Search" size={16} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button aria-label="清除搜索" onClick={() => onChange("")}>
          <Icon name="X" size={14} />
        </button>
      )}
    </label>
  );
}
function Stats({ items }) {
  return (
    <div className="biz-mini-stats">
      {items.map(([value, label, tone]) => (
        <div key={label} className={tone || ""}>
          <strong>{value}</strong>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}
function Pair({ label, children }) {
  return (
    <div className="biz-pair">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}
function TextLink({ children, onClick }) {
  return (
    <button className="biz-text-link" onClick={onClick}>
      {children}
      <Icon name="ArrowUpRight" size={13} />
    </button>
  );
}

function Capacity({ onRegionClick, defaultExpanded = false, compact = false }) {
  const [info, setInfo] = useState(defaultExpanded);
  useEffect(() => setInfo(defaultExpanded), [defaultExpanded]);
  const option = {
    animationDuration: 420,
    tooltip: { trigger: "item", formatter: "{b}：{c} 托位 ({d}%)" },
    color: [blue, "#a7c1ff", "#dce5f2"],
    series: [
      {
        type: "pie",
        radius: ["72%", "87%"],
        center: ["50%", "50%"],
        padAngle: 2,
        itemStyle: { borderRadius: 4 },
        label: { show: false },
        data: [
          { value: 1920, name: "已占用" },
          { value: 416, name: "可用" },
          { value: 64, name: "空位锁定" },
        ],
      },
    ],
  };
  return (
    <Section title="库容占用" action={<Badge tone="orange">演示数据</Badge>}>
      <div className="biz-capacity">
        <div className="biz-donut">
          <Chart
            option={option}
            height={compact ? 132 : 154}
            onClick={onRegionClick}
          />
          <div className="biz-donut-label">
            <strong>
              80.0<span>%</span>
            </strong>
            <small>占用率</small>
          </div>
        </div>
        <div className="biz-legend">
          {[
            ["已占用", "1,920", blue],
            ["可用", "416", "#a7c1ff"],
            ["空位锁定", "64", "#dce5f2"],
          ].map(([n, v, c]) => (
            <button key={n} onClick={() => onRegionClick?.({ name: n })}>
              <i style={{ background: c }} />
              <span>{n}</span>
              <strong>{v}</strong>
            </button>
          ))}
        </div>
      </div>
      <button
        className="biz-info-toggle"
        aria-expanded={info}
        onClick={() => setInfo(!info)}
      >
        <Icon name="Info" size={14} />
        示例容量 2,400 托位
        <Icon name={info ? "ChevronUp" : "ChevronDown"} size={14} />
      </button>
      {info && (
        <div className="biz-inset">
          已占用 1,920 + 可用 416 + 锁定 64 = 2,400
          托位。此图保留原设计，真实容量与货位映射尚未核验。
        </div>
      )}
    </Section>
  );
}

function Overview({ onNavigate, onLocate, initialState }) {
  const option = {
    grid: { left: 3, right: 6, top: 4, bottom: 0, containLabel: true },
    xAxis: { type: "value", max: 156, show: false },
    yAxis: {
      type: "category",
      data: ["出库", "入库"],
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: ink, fontSize: 12 },
    },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    color: [blue, "#89adff", "#dce5f2", "#e4a853"],
    series: [
      ["已完成", [118, 96]],
      ["执行中", [24, 22]],
      ["待作业", [10, 8]],
      ["异常", [4, 2]],
    ].map(([name, data]) => ({
      name,
      type: "bar",
      stack: "orders",
      barWidth: 10,
      data,
      itemStyle: { borderRadius: 2 },
    })),
  };
  return (
    <>
      <Header title="仓库运营总览" description="库存、设备与作业概况" />
      <button className="biz-alert-strip" onClick={() => onNavigate("alerts")}>
        <span>
          <Icon name="TriangleAlert" size={18} />
          告警 <b>7</b> 项待关注
        </span>
        <Icon name="ArrowRight" size={17} />
      </button>
      <div className="biz-metric-grid">
        <Metric label="现存数量" value={337783} detail="数量单位待确认" />
        <Metric label="可用数量" value={336006} detail="数量单位待确认" />
        <Metric label="货主数" value={156} />
        <Metric label="SKU 编码数" value={14373} />
      </div>
      <Section
        title="叉车台账"
        action={
          <TextLink onClick={() => onNavigate("devices")}>查看台账</TextLink>
        }
      >
        <Stats
          items={[
            [82, "台账总数"],
            [62, "正常", "blue"],
            [20, "禁用"],
            [0, "维修中", "orange"],
          ]}
        />
        <DemoNote>管理状态统计，不代表实时在线状态</DemoNote>
      </Section>
      <Capacity
        compact
        defaultExpanded={initialState === 44}
        onRegionClick={() => onNavigate("inventory")}
      />
      <Section title="订单进度" action={<Badge tone="orange">演示数据</Badge>}>
        <Chart option={option} height={92} />
        <div className="biz-chart-legend">
          {[
            ["已完成", blue],
            ["执行中", "#89adff"],
            ["待作业", "#dce5f2"],
            ["异常", "#e4a853"],
          ].map(([n, c]) => (
            <span key={n}>
              <i style={{ background: c }} />
              {n}
            </span>
          ))}
        </div>
        <div className="biz-section-foot">
          <span>入库 96 / 128 · 出库 118 / 156</span>
          <TextLink onClick={() => onNavigate("orders")}>查看订单</TextLink>
        </div>
      </Section>
      <button
        className="biz-bottom-link"
        onClick={() => onLocate({ label: "GHS · 主仓库", type: "warehouse" })}
      >
        返回园区全景
        <Icon name="Focus" size={16} />
      </button>
    </>
  );
}

function Inventory({ initialState, onLocate, notify }) {
  const [detail, setDetail] = useState(null),
    [selected, setSelected] = useState(12),
    [query, setQuery] = useState(""),
    [region, setRegion] = useState("全部区域");
  useEffect(() => {
    setDetail(
      initialState === 17 ? "material" : initialState === 6 ? "slot" : null,
    );
    setQuery("");
  }, [initialState]);
  const locate = () =>
    onLocate({
      label: `A-03-${String(selected).padStart(2, "0")}`,
      type: "location",
    });
  if (detail === "material")
    return (
      <>
        <Header
          title="库存明细"
          description="样例记录与物料信息分别展示"
          back="返回库存与货位"
          onBack={() => setDetail(null)}
        />
        <Section title="库存样例 · 5 条">
          <table className="biz-table">
            <thead>
              <tr>
                <th>明细 ID</th>
                <th>现存</th>
                <th>可用</th>
              </tr>
            </thead>
            <tbody>
              {stockSamples.map(([id, a, b]) => (
                <tr key={id}>
                  <td>{id}</td>
                  <td>{a}</td>
                  <td>{b}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <DemoNote>
            部分已核验记录；数量单位待确认，零量及负量保留原值。
          </DemoNote>
        </Section>
        <Section
          title="物料详情"
          action={<Badge tone="orange">数据未核验</Badge>}
        >
          <div className="biz-object-title">
            <Icon name="Package" size={25} />
            <div>
              <h2>电机安装支架</h2>
              <p>SKU2038 · BH-M8 · 镀锌钢</p>
            </div>
          </div>
          <Stats
            items={[
              [480, "当前库存 / 件"],
              [360, "可用 / 件"],
              [120, "已分配 / 件"],
            ]}
          />
          <Pair label="批次">B20261018</Pair>
          <Pair label="货位">A-03-12</Pair>
          <Pair label="包装">24 箱 × 20 件 / 箱 · 1 托</Pair>
          <Pair label="托盘码">PLT202610200038</Pair>
          <DemoNote>物料为原设计示例，与上方真实明细未建立关联。</DemoNote>
          <Button onClick={locate}>定位示例货位</Button>
        </Section>
      </>
    );
  if (detail === "slot")
    return (
      <>
        <Header
          title={`货位 A-03-${String(selected).padStart(2, "0")}`}
          description="场景货架 A / 03 排"
          back="返回库存与货位"
          onBack={() => setDetail(null)}
        />
        <div className="biz-slot-preview">
          <Icon name="Boxes" size={60} />
          <span>
            {selected <= 34 ? "已占用" : selected <= 44 ? "空闲" : "盘点锁定"}
          </span>
        </div>
        <Pair label="货位状态">
          {selected <= 34 ? "已占用" : selected <= 44 ? "空闲" : "盘点中"}
        </Pair>
        <Pair label="托盘数量">{selected <= 34 ? "1" : "0"}</Pair>
        {selected <= 34 && <Pair label="关联物料">SKU2038</Pair>}
        <DemoNote>货位状态、托盘与物料均为设计示例。</DemoNote>
        <div className="biz-actions">
          <Button onClick={locate}>定位货位</Button>
          {selected <= 34 ? (
            <Button variant="secondary" onClick={() => setDetail("material")}>
              查看物料示例
            </Button>
          ) : (
            <Button
              variant="secondary"
              onClick={() =>
                notify(
                  selected <= 44
                    ? "该空闲货位暂无关联物料。"
                    : "锁定记录：2026-10-20 13:20 开始盘点，等待复核。",
                )
              }
            >
              {selected <= 44 ? "查看空闲状态" : "查看锁定记录"}
            </Button>
          )}
        </div>
      </>
    );
  const filtered = regions.filter(
    (r) =>
      (region === "全部区域" || r === region) &&
      r.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <Header
        title="库存与货位"
        description="库存数量与空间分布"
        badge="台账数据"
      />
      <div className="biz-metric-grid">
        <Metric label="现存数量" value={337783} detail="数量单位待确认" />
        <Metric label="可用数量" value={336006} detail="数量单位待确认" />
      </div>
      <div className="biz-inline-meta">
        冻结 55 <i /> 已分配 1,722 <i /> 待移出 0
      </div>
      <div className="biz-inset">156 货主 · 14,373 SKU · 76,752 条明细</div>
      <Capacity
        onRegionClick={() => {
          setDetail("slot");
          setSelected(12);
        }}
      />
      <Section
        title="货架 A-03"
        action={<Badge tone="orange">48 格示意</Badge>}
      >
        <div className="biz-slot-grid">
          {Array.from({ length: 48 }, (_, i) => i + 1).map((i) => (
            <button
              key={i}
              className={
                i <= 34 ? "occupied" : i <= 44 ? "available" : "locked"
              }
              aria-label={`A-03-${String(i).padStart(2, "0")} ${i <= 34 ? "已占用" : i <= 44 ? "空闲" : "锁定"}`}
              onClick={() => {
                setSelected(i);
                setDetail("slot");
                onLocate({
                  label: `A-03-${String(i).padStart(2, "0")}`,
                  type: "location",
                });
              }}
            >
              {String(i).padStart(2, "0")}
            </button>
          ))}
        </div>
        <div className="biz-chart-legend">
          <span>
            <i style={{ background: blue }} />
            占用 34
          </span>
          <span>
            <i style={{ background: "#e7eefc" }} />
            可用 10
          </span>
          <span>
            <i style={{ background: "#b9c6d8" }} />
            锁定 4
          </span>
        </div>
      </Section>
      <Section
        title="区域目录"
        action={<span className="biz-meta">10 个区域</span>}
      >
        <Search
          value={query}
          onChange={setQuery}
          placeholder="搜索区域编号或名称"
        />
        <select
          aria-label="库存区域筛选"
          className="biz-select"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        >
          <option>全部区域</option>
          {regions.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        {filtered.length ? (
          <div className="biz-region-list">
            {filtered.map((r) => (
              <button
                key={r}
                onClick={() => {
                  onLocate({ label: r, type: "region" });
                  notify(`${r}：真实区域数量待接入。`);
                }}
              >
                <Icon name="MapPin" size={15} />
                {r}
                <Icon name="ChevronRight" size={15} />
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title="没有匹配的区域"
            description="保留当前搜索和筛选，可清除后重新查看。"
            action="清除筛选"
            onAction={() => {
              setQuery("");
              setRegion("全部区域");
            }}
          />
        )}
        <DemoNote>仅区域目录已核验，各区域数量与场景映射待确认。</DemoNote>
        <Button variant="secondary" onClick={() => setDetail("material")}>
          查看库存样例明细
        </Button>
      </Section>
    </>
  );
}

function Orders({ initialState, onLocate, onNavigate }) {
  const [tab, setTab] = useState("out"),
    [detail, setDetail] = useState(null),
    [query, setQuery] = useState(""),
    [onlyException, setOnlyException] = useState(false),
    [date, setDate] = useState("2026-10-20");
  useEffect(() => {
    setTab(initialState === 19 ? "in" : "out");
    setDetail(initialState === 18 ? orderRows.out[0] : null);
  }, [initialState]);
  const rows =
    date === "2026-10-20"
      ? orderRows[tab].filter(
          (r) =>
            `${r[0]} ${r[1]} ${r[2]}`
              .toLowerCase()
              .includes(query.toLowerCase()) &&
            (!onlyException || r[5].includes("异常")),
        )
      : [];
  const chart = {
    color: [blue, "#87aaff"],
    tooltip: { trigger: "axis" },
    grid: { left: 29, right: 5, top: 16, bottom: 24 },
    xAxis: {
      type: "category",
      data: ["06:00", "08:00", "10:00", "12:00", "14:00"],
      axisLine: { lineStyle: { color: "#dbe4ef" } },
      axisTick: { show: false },
      axisLabel: { fontSize: 10, color: "#71829b" },
    },
    yAxis: {
      type: "value",
      splitNumber: 3,
      axisLabel: { fontSize: 10, color: "#71829b" },
      splitLine: { lineStyle: { color: "#eef2f7" } },
    },
    series: [
      {
        name: "入库",
        type: "line",
        smooth: true,
        symbolSize: 5,
        data: [0, 16, 38, 72, 96],
      },
      {
        name: "出库",
        type: "line",
        smooth: true,
        symbolSize: 5,
        data: [0, 25, 55, 84, 118],
      },
    ],
  };
  if (detail) {
    const [id, sku, name, done, total, status] = detail;
    return (
      <>
        <Header
          title="订单详情"
          description={id}
          back={`返回${tab === "out" ? "出库" : "入库"}订单 · 保留筛选`}
          onBack={() => setDetail(null)}
        />
        <div className="biz-detail-status">
          <Badge tone={status.includes("异常") ? "orange" : "blue"}>
            {status}
          </Badge>
          <span>要求完成 15:00</span>
        </div>
        <Section
          title="本单物料"
          action={
            <TextLink onClick={() => onNavigate("inventory")}>
              查看库存
            </TextLink>
          }
        >
          <h2 className="biz-item-heading">{name}</h2>
          <p className="biz-meta">{sku} · 批次 B20261018</p>
          <div className="biz-order-big">
            {done}
            <span> / {total} 件</span>
          </div>
          <div className="biz-progress">
            <i style={{ width: `${(done / total) * 100}%` }} />
          </div>
        </Section>
        <Section title="作业关联">
          <Pair label="来源货位">
            <TextLink
              onClick={() => onLocate({ label: "A-03-12", type: "location" })}
            >
              A-03-12
            </TextLink>
          </Pair>
          <Pair label="目标月台">
            <TextLink
              onClick={() => onLocate({ label: "DOCK-02", type: "dock" })}
            >
              DOCK-02
            </TextLink>
          </Pair>
          <Pair label="执行设备">
            <TextLink
              onClick={() => onLocate({ label: "FORK-01", type: "device" })}
            >
              FORK-01
            </TextLink>
          </Pair>
          <Pair label="关联任务">T-0401</Pair>
        </Section>
        <Section title="作业进度">
          <ol className="biz-timeline">
            {[
              [
                "13:52",
                "订单创建",
                `计划${tab === "out" ? "出库" : "入库"} ${total} 件`,
              ],
              ["13:58", "库存分配", "关联 A-03-12"],
              ["14:02", "设备已接单", "等待开始拣货"],
              ["—", "复核与出库", "等待拣货完成"],
            ].map(([time, title, desc], i) => (
              <li
                key={title}
                className={i === 2 ? "current" : i === 3 ? "future" : ""}
              >
                <time>{time}</time>
                <div>
                  <strong>{title}</strong>
                  <p>{desc}</p>
                </div>
              </li>
            ))}
          </ol>
        </Section>
        <div className="biz-actions">
          <Button
            onClick={() => onLocate({ label: "FORK-01", type: "device" })}
          >
            定位执行设备
          </Button>
          <Button variant="secondary" onClick={() => onNavigate("replay")}>
            订单追溯
          </Button>
        </div>
        <DemoNote>订单、物料、设备关联为演示数据。</DemoNote>
      </>
    );
  }
  return (
    <>
      <Header title="今日出入库订单" description="出入库作业、进度与关联设备" />
      <Tabs
        label="订单类型"
        items={[
          ["in", "入库 128"],
          ["out", "出库 156"],
        ]}
        value={tab}
        onChange={setTab}
      />
      <Stats
        items={
          tab === "out"
            ? [
                [118, "已完成", "blue"],
                [24, "执行中"],
                [10, "待作业"],
                [4, "异常", "orange"],
              ]
            : [
                [96, "已完成", "blue"],
                [22, "执行中"],
                [8, "待作业"],
                [2, "异常", "orange"],
              ]
        }
      />
      <Section
        title="累计完成"
        action={<span className="biz-meta">演示趋势 / 单</span>}
      >
        <Chart option={chart} height={162} />
        <div className="biz-chart-legend">
          <span>
            <i style={{ background: blue }} />
            入库
          </span>
          <span>
            <i style={{ background: "#87aaff" }} />
            出库
          </span>
        </div>
      </Section>
      <Section title="订单列表">
        <Search
          value={query}
          onChange={setQuery}
          placeholder="搜索订单号 / 物料"
        />
        <div className="biz-filter-row">
          <input
            aria-label="订单日期"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
          <label>
            <input
              type="checkbox"
              checked={onlyException}
              onChange={(e) => setOnlyException(e.target.checked)}
            />
            只看异常
          </label>
        </div>
        {rows.length ? (
          <div className="biz-row-list">
            {rows.map((r) => (
              <button
                className="biz-order-row"
                key={r[0]}
                onClick={() => {
                  setDetail(r);
                  onLocate({ label: r[0], type: "order" });
                }}
              >
                <div className="biz-row-top">
                  <strong>{r[0]}</strong>
                  <Icon name="ChevronRight" size={16} />
                </div>
                <p>
                  {r[1]} · {r[2]}
                </p>
                <div className="biz-row-bottom">
                  <span>
                    {r[3]} / {r[4]} 件
                  </span>
                  <Badge
                    tone={
                      r[5].includes("异常")
                        ? "orange"
                        : r[5] === "已完成"
                          ? "green"
                          : "blue"
                    }
                  >
                    {r[5]}
                  </Badge>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title={
              date !== "2026-10-20" ? "所选日期没有样例订单" : "没有匹配的订单"
            }
            description="原型展示 2026-10-20 的 4 条样例订单。"
            action="恢复演示筛选"
            onAction={() => {
              setQuery("");
              setDate("2026-10-20");
              setOnlyException(false);
            }}
          />
        )}
        <DemoNote>
          展示 {rows.length} 条样例，合计为原设计统计，未接入真实订单。
        </DemoNote>
      </Section>
    </>
  );
}

function DeviceDetails({ device, onBack, onLocate, onNavigate }) {
  const [tab, setTab] = useState("status");
  const isFacility = device.id?.startsWith("CH-");
  const isTruck = device.id?.startsWith("TRUCK");
  return (
    <>
      <Header
        title="设备详情"
        description="场景模型与参数示例"
        back="返回设备列表"
        onBack={onBack}
      />
      <div className="biz-device-preview">
        <img
          src={`/assets/device-${isFacility ? "charger" : isTruck ? "truck" : device.kind === "搬运机器人" ? "agv" : device.kind === "电动堆高车" ? "stacker" : "forklift"}.png`}
          alt={`${device.kind}项目模型预览`}
        />
        <span>项目模型预览</span>
      </div>
      <div className="biz-object-title">
        <div>
          <h2>{device.id}</h2>
          <p>
            {device.kind} · {device.area}
          </p>
        </div>
        <Badge tone={device.status === "低电量" ? "orange" : "blue"}>
          {device.status}
        </Badge>
      </div>
      <Tabs
        label="设备详情分类"
        items={[
          ["status", "运行状态"],
          ["task", "任务信息"],
          ["events", "事件"],
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "status" ? (
        <>
          <div className="biz-metric-grid">
            <Metric
              label={
                isTruck ? "装载进度" : isFacility ? "充电功率" : "剩余电量"
              }
              value={
                isTruck ? "66.7" : isFacility ? "18.6" : (device.battery ?? "—")
              }
              unit={
                isTruck
                  ? "%"
                  : isFacility
                    ? "kW"
                    : device.battery != null
                      ? "%"
                      : ""
              }
            />
            <Metric
              label={isTruck ? "待装数量" : "行驶速度"}
              value={isTruck ? "80" : (device.speed ?? "—")}
              unit={isTruck ? "件" : ""}
            />
          </div>
          <Pair label="当前位置">{device.area}</Pair>
          <Pair label="当前任务">
            {device.status === "待机" ? "暂无任务" : "T-20261020-034"}
          </Pair>
          <DemoNote>
            {device.battery == null
              ? "未知指标保留为 —，不视为零。"
              : "参数为原设计示例，不代表真实设备遥测。"}
          </DemoNote>
        </>
      ) : tab === "task" ? (
        <Section title="当前任务">
          <Pair label="任务编号">T-20261020-034</Pair>
          <Pair label="作业类型">{isTruck ? "月台装载" : "托盘搬运"}</Pair>
          <Pair label="来源">A-03-12</Pair>
          <Pair label="目的地">DOCK-02</Pair>
          <Pair label="载荷">{device.id === "FORK-01" ? "1.2 t" : "—"}</Pair>
          <Pair label="驾驶员">{device.id === "FORK-01" ? "OP-07" : "—"}</Pair>
        </Section>
      ) : (
        <Section title="近期事件">
          <ol className="biz-timeline">
            {[
              ["14:12:32", "任务下发"],
              ["14:13:05", "前往目标点"],
              ["14:20:08", "运输中"],
            ].map(([time, title]) => (
              <li key={time}>
                <time>{time}</time>
                <strong>{title}</strong>
              </li>
            ))}
          </ol>
        </Section>
      )}
      <div className="biz-actions">
        <Button
          onClick={() =>
            onLocate({ label: device.id, type: "device", follow: true })
          }
        >
          跟随设备
        </Button>
        <Button variant="secondary" onClick={() => onNavigate("replay")}>
          订单追溯
        </Button>
      </div>
    </>
  );
}

function Devices({
  initialState,
  onLocate,
  onNavigate,
  notify,
  selectedEntity,
}) {
  const [mode, setMode] = useState("ledger"),
    [detail, setDetail] = useState(null),
    [query, setQuery] = useState(""),
    [onlyIdle, setOnlyIdle] = useState(false),
    [groupPage, setGroupPage] = useState(0),
    [warningOnly, setWarningOnly] = useState(false);
  useEffect(() => {
    setDetail(
      initialState === 2
        ? sceneDevices.find((d) => d.id === selectedEntity) || sceneDevices[0]
        : null,
    );
    setMode(
      initialState === 20
        ? "facilities"
        : [2, 3, 7, 10].includes(initialState)
          ? "scene"
          : "ledger",
    );
    setWarningOnly(initialState === 10);
    setGroupPage(initialState === 3 ? 1 : 0);
    setQuery("");
  }, [initialState, selectedEntity]);
  if (detail)
    return (
      <DeviceDetails
        key={detail.id}
        device={detail}
        onBack={() => setDetail(null)}
        onLocate={onLocate}
        onNavigate={onNavigate}
      />
    );
  const ledger = [
    ["2574", "SITDOWN-GHS-L-OUT-S1"],
    ["2575", "SITDOWN-GHS-L-OUT-S2"],
    ["2576", "SITDOWN-GHS-L-IN-S3"],
    ["2577", "SITDOWN-GHS-L-IN-S4"],
    ["2578", "SITDOWN-GHS-L-IN-S5"],
  ].filter((r) => r.join(" ").toLowerCase().includes(query.toLowerCase()));
  const models = sceneDevices.filter(
    (d) =>
      `${d.id} ${d.kind}`.toLowerCase().includes(query.toLowerCase()) &&
      (!warningOnly || d.status === "低电量"),
  );
  return (
    <>
      <Header
        title={mode === "ledger" ? "设备台账" : "场景设备"}
        description={
          mode === "ledger"
            ? "管理台账与场景模型分别查看"
            : "点位、模型与作业参数示意"
        }
        badge={mode === "ledger" ? "台账数据" : "数据未核验"}
      />
      <Tabs
        label="设备视图"
        items={[
          ["ledger", "真实台账"],
          ["scene", "场景模型"],
          ["facilities", "充电设施"],
        ]}
        value={mode}
        onChange={(v) => {
          setMode(v);
          setQuery("");
          setGroupPage(0);
        }}
      />
      {mode === "ledger" ? (
        <>
          <Stats
            items={[
              [82, "台账总数"],
              [62, "正常", "blue"],
              [20, "禁用"],
              [0, "维修中", "orange"],
            ]}
          />
          <DemoNote>
            管理状态不表示实时在线；真实台账尚未关联场景模型。
          </DemoNote>
          <Section
            title="设备类型"
            action={<span className="biz-meta">总数 / 正常 / 禁用</span>}
          >
            <table className="biz-table device-types">
              <tbody>
                {[
                  ["电动托盘车", 8, 8, 0],
                  ["ORDER PICKER", 20, 19, 1],
                  ["REACH", 18, 16, 2],
                  ["Rider", 9, 4, 5],
                  ["坐式叉车", 27, 15, 12],
                ].map(([name, ...ns]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    {ns.map((n, i) => (
                      <td key={i}>{n}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
          <Section title="台账样例 · 5 条">
            <Search
              value={query}
              onChange={setQuery}
              placeholder="搜索设备编号 / 台账 ID"
            />
            {ledger.length ? (
              ledger.map(([id, name]) => (
                <button
                  className="biz-ledger-row"
                  key={id}
                  onClick={() =>
                    notify(
                      `ID ${id} · ${name}：坐式叉车，尚未建立场景映射，暂不能定位。`,
                    )
                  }
                >
                  <div>
                    <strong>{name}</strong>
                    <p>ID {id} · 坐式叉车</p>
                  </div>
                  <Badge tone="neutral">未关联</Badge>
                </button>
              ))
            ) : (
              <Empty
                title="没有匹配的台账"
                description="当前仅显示 5 条已核验样例。"
                action="清除搜索"
                onAction={() => setQuery("")}
              />
            )}
            <DemoNote>
              部分记录，不代表完整设备清单。电量、速度、载荷暂无数据。
            </DemoNote>
          </Section>
        </>
      ) : mode === "scene" ? (
        <>
          <Search
            value={query}
            onChange={(v) => {
              setQuery(v);
              setGroupPage(0);
            }}
            placeholder="搜索场景设备 / 类型"
          />
          <div className="biz-filter-row">
            <span>场景模型示例</span>
            <label>
              <input
                type="checkbox"
                checked={warningOnly}
                onChange={(e) => {
                  setWarningOnly(e.target.checked);
                  setGroupPage(0);
                }}
              />
              仅看预警
            </label>
          </div>
          <div className="biz-row-list">
            {models.length ? (
              models.slice(groupPage * 3, groupPage * 3 + 3).map((d) => (
                <button
                  key={d.id}
                  className="biz-device-row"
                  onClick={() => {
                    setDetail(d);
                    onLocate({ label: d.id, type: "device" });
                  }}
                >
                  <div className="biz-device-symbol">
                    <Icon
                      name={
                        d.id.startsWith("TRUCK")
                          ? "Truck"
                          : d.kind === "搬运机器人"
                            ? "Bot"
                            : "Forklift"
                      }
                      size={28}
                    />
                  </div>
                  <div>
                    <strong>{d.id}</strong>
                    <p>{d.kind}</p>
                    <small>{d.area}</small>
                  </div>
                  <Badge tone={d.status === "低电量" ? "orange" : "blue"}>
                    {d.status}
                  </Badge>
                </button>
              ))
            ) : (
              <Empty
                title="没有匹配的场景设备"
                description="检查搜索词或状态筛选。"
                action="清除筛选"
                onAction={() => {
                  setQuery("");
                  setWarningOnly(false);
                  setGroupPage(0);
                }}
              />
            )}
          </div>
          {models.length > 3 && (
            <div className="biz-pagination">
              <span>
                {groupPage * 3 + 1}–{Math.min(groupPage * 3 + 3, models.length)}{" "}
                / {models.length} 个样例
              </span>
              <button
                aria-label="上一页设备"
                disabled={!groupPage}
                onClick={() => setGroupPage(0)}
              >
                <Icon name="ChevronLeft" size={16} />
              </button>
              <button
                aria-label="下一页设备"
                disabled={groupPage > 0}
                onClick={() => setGroupPage(1)}
              >
                <Icon name="ChevronRight" size={16} />
              </button>
            </div>
          )}
          <DemoNote>场景设备与 82 条真实台账未完成映射，参数为演示。</DemoNote>
        </>
      ) : (
        <>
          <Stats
            items={[
              [56, "充电设施"],
              [18, "充电中", "blue"],
              [36, "空闲"],
              [2, "离线"],
            ]}
          />
          <Search
            value={query}
            onChange={setQuery}
            placeholder="搜索充电位 / 关联设备"
          />
          <label className="biz-check">
            <input
              type="checkbox"
              checked={onlyIdle}
              onChange={(e) => setOnlyIdle(e.target.checked)}
            />
            只看空闲设施
          </label>
          {facilities
            .filter(
              (r) =>
                r.join(" ").toLowerCase().includes(query.toLowerCase()) &&
                (!onlyIdle || r[1] === "空闲"),
            )
            .map(([id, status, device, power, battery]) => (
              <div className="biz-facility" key={id}>
                <div className="biz-row-top">
                  <strong>{id}</strong>
                  <Badge
                    tone={
                      status === "离线"
                        ? "neutral"
                        : status === "空闲"
                          ? "green"
                          : "blue"
                    }
                  >
                    {status}
                  </Badge>
                </div>
                <div className="biz-row-bottom">
                  <span>
                    {power} · {battery}
                  </span>
                  <span>{device || "未连接设备"}</span>
                </div>
                <Button
                  variant="ghost"
                  disabled={!device}
                  onClick={() => {
                    setDetail({
                      ...sceneDevices[0],
                      id: device,
                      area: `充电区 C · ${id}`,
                      status: "充电中",
                      battery: parseInt(battery),
                    });
                    onLocate({ label: device, type: "device" });
                  }}
                >
                  {device ? "定位关联设备" : "暂无关联设备"}
                </Button>
              </div>
            ))}
          {!facilities.some(
            (r) =>
              r.join(" ").toLowerCase().includes(query.toLowerCase()) &&
              (!onlyIdle || r[1] === "空闲"),
          ) && (
            <Empty
              title="没有匹配的充电设施"
              action="清除筛选"
              onAction={() => {
                setQuery("");
                setOnlyIdle(false);
              }}
            />
          )}
          <DemoNote>设施使用独立统计口径，当前展示 4 个示例。</DemoNote>
        </>
      )}
    </>
  );
}

function Alerts({ initialState, onLocate, onNavigate, notify }) {
  const [items, setItems] = useState(initialAlerts),
    [detail, setDetail] = useState(null),
    [level, setLevel] = useState("全部级别"),
    [status, setStatus] = useState("current"),
    [rules, setRules] = useState(false);
  useEffect(() => {
    setDetail(initialState === 4 ? initialAlerts[6] : null);
  }, [initialState]);
  const selected = detail ? items.find((a) => a.id === detail.id) : null;
  const confirm = (id) => {
    setItems((prev) =>
      prev.map((a) => (a.id === id ? { ...a, confirmed: true } : a)),
    );
    notify("告警已确认；设备仍未恢复，继续保留在当前队列。");
  };
  if (selected)
    return (
      <>
        <Header
          title="告警详情"
          description="确认表示已知晓，恢复另行记录"
          back="返回当前告警"
          onBack={() => setDetail(null)}
        />
        <div className="biz-warning-card">
          <Icon name="TriangleAlert" size={28} />
          <div>
            <h2>{selected.id}</h2>
            <p>{selected.name}</p>
          </div>
          <Badge tone={selected.level === "故障" ? "red" : "orange"}>
            {selected.level}
          </Badge>
        </div>
        {selected.id === "AGV-12" && (
          <div className="biz-metric-grid">
            <Metric label="剩余电量" value="18" unit="%" />
            <Metric label="预警阈值" value="20" unit="%" />
          </div>
        )}
        <Pair label="发生时间">2026-10-20 {selected.time}</Pair>
        <Pair label="设备恢复状态">
          <Badge tone="orange">未恢复</Badge>
        </Pair>
        <Pair label="人工处理状态">
          {selected.confirmed ? "已确认" : "待确认"}
        </Pair>
        {selected.id === "AGV-12" && (
          <Section title="附近空闲充电位">
            <button
              className="biz-location-link"
              onClick={() => onLocate({ label: "CH-12", type: "facility" })}
            >
              <Icon name="BatteryCharging" size={20} />
              <div>
                <strong>CH-12 · 空闲</strong>
                <p>充电区 C</p>
              </div>
              <Icon name="ArrowUpRight" size={17} />
            </button>
          </Section>
        )}
        <div className="biz-inset">
          {selected.confirmed
            ? "值守员 OP-07 已确认；本次告警仍未恢复。"
            : `${selected.time} 系统触发，等待值守人员确认。`}
        </div>
        <div className="biz-actions">
          <Button
            disabled={selected.confirmed}
            onClick={() => confirm(selected.id)}
          >
            {selected.confirmed ? "已确认告警" : "确认告警"}
          </Button>
          <Button variant="secondary" onClick={() => onNavigate("replay")}>
            查看历史轨迹
          </Button>
        </div>
        <button
          className="biz-info-toggle"
          onClick={() => setRules(!rules)}
          aria-expanded={rules}
        >
          <Icon name="Info" size={14} />
          确认规则
          <Icon name={rules ? "ChevronUp" : "ChevronDown"} size={14} />
        </button>
        {rules && (
          <DemoNote>
            确认仅记录人工已知晓，不会清除故障，也不会自动标记设备恢复。
          </DemoNote>
        )}
      </>
    );
  const filtered =
    status === "recovered"
      ? []
      : items.filter((a) => level === "全部级别" || a.level === level);
  return (
    <>
      <Header title="设备告警" description="分级队列与处理进度" />
      <div className="biz-alert-total">
        <strong>7</strong>
        <div>
          项未恢复告警
          <p>
            待确认 {items.filter((a) => !a.confirmed).length} · 已确认{" "}
            {items.filter((a) => a.confirmed).length}
          </p>
        </div>
        <span>
          <b>2</b> 故障
          <br />
          <b>5</b> 预警
        </span>
      </div>
      <Tabs
        label="告警记录"
        items={[
          ["current", "当前告警 7"],
          ["recovered", "已恢复记录"],
        ]}
        value={status}
        onChange={setStatus}
      />
      <div className="biz-filter-row">
        <select
          aria-label="告警级别"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          <option>全部级别</option>
          <option>故障</option>
          <option>预警</option>
        </select>
        <span>按严重程度排序</span>
      </div>
      {filtered.length ? (
        <div className="biz-row-list">
          {filtered.map((a) => (
            <button
              key={a.id}
              className="biz-alarm-row"
              onClick={() => {
                setDetail(a);
                onLocate({ label: a.id, type: "alert" });
              }}
            >
              <div
                className={`biz-alarm-dot ${a.level === "故障" ? "red" : "orange"}`}
              />
              <div>
                <div className="biz-row-top">
                  <strong>{a.id}</strong>
                  <span>{a.confirmed ? "已确认" : "待确认"}</span>
                </div>
                <p>{a.name}</p>
                <small>{a.time} · 未恢复</small>
              </div>
              <Icon name="ChevronRight" size={16} />
            </button>
          ))}
        </div>
      ) : (
        <Empty
          title="暂无已恢复记录"
          description="当前 7 项告警仍未恢复，人工确认不会移出队列。"
          action="查看当前告警"
          onAction={() => setStatus("current")}
        />
      )}
      <DemoNote>订单的 6 单异常在订单入口查看，不与设备告警相加。</DemoNote>
    </>
  );
}

export function BusinessStates({
  kind = 22,
  notify = () => {},
  onNavigate = () => {},
}) {
  const [state, setState] = useState("empty");
  const [busy, setBusy] = useState(false);
  const data =
    kind === 8
      ? {
          empty: [
            "未找到 FORK-99",
            "检查编号，或清除类型与状态筛选。",
            "清除筛选",
          ],
          history: [
            "此时间范围没有历史记录",
            "查询成功，当前无法回放；不代表设备未运行。",
            "调整时间",
          ],
          error: [
            "暂时无法读取历史记录",
            "已保留 AGV-12 与时间范围，请重试。",
            "重试",
          ],
          stale: [
            "数据已 2 分钟未更新",
            "82% 为最近有效电量值，并非实时值。",
            "刷新数据",
          ],
          waiting: [
            "AGV-08 等待数据接入",
            "还没有可用样本。电量 —，速度 —。",
            "返回场景",
          ],
          offline: [
            "TRUCK-087 已离线",
            "保留设备位置关联。已装数量 —，剩余数量 —。",
            "查看历史",
          ],
        }
      : {
          empty: [
            "未找到 SKU9999",
            "已保留货架 A-03 和已占用筛选。",
            "清除筛选",
          ],
          history: [
            "所选日期没有订单",
            "当前日期 2026-10-19，入库 0 单，出库 0 单。",
            "选择日期",
          ],
          loading: [
            "正在读取库存",
            "保留货架位置、筛选和字段标签。数量 —。",
            "返回场景",
          ],
          error: [
            "库存刷新失败",
            "保留最近有效库存值，并标记为旧值。",
            "重试库存",
          ],
          locked: [
            "A-03-15 · 盘点锁定",
            "无物料，0 托；盘点期间暂不允许分配。",
            "查看锁定记录",
          ],
          confirmed: [
            "AGV-12 · 已确认 / 未恢复",
            "OP-07 于 14:21:05 确认，低电量预警仍存在。",
            "查看处理记录",
          ],
        };
  const selected = data[state] || data.empty;
  return (
    <>
      <Header title="业务反馈状态" description="空值、异常与确认结果" />
      <div className="biz-state-options">
        {Object.entries(data).map(([key, v]) => (
          <button
            key={key}
            className={state === key ? "active" : ""}
            onClick={() => setState(key)}
          >
            {v[0]}
          </button>
        ))}
      </div>
      <div className="biz-state-demo">
        <Icon
          name={
            state === "error"
              ? "CircleAlert"
              : state === "loading" || busy
                ? "LoaderCircle"
                : "SearchX"
          }
          size={42}
        />
        <h2>{busy ? "正在重新读取…" : selected[0]}</h2>
        <p>{selected[1]}</p>
        <Button
          disabled={busy}
          onClick={() => {
            if (state === "history" || state === "offline") {
              onNavigate(kind === 8 ? "replay" : "orders");
              return;
            }
            if (state === "waiting" || state === "loading") {
              onNavigate("overview");
              return;
            }
            setBusy(true);
            window.setTimeout(() => {
              setBusy(false);
              notify(
                state === "locked"
                  ? "盘点记录：2026-10-20 13:20，由 OP-07 发起。"
                  : state === "confirmed"
                    ? "处理记录：人工已确认，设备状态未恢复。"
                    : "原型演示：已重新加载有效样例。",
              );
            }, 500);
          }}
        >
          {selected[2]}
        </Button>
      </div>
      <DemoNote>边界反馈演示，所有操作只改变当前原型。</DemoNote>
    </>
  );
}

export default function BusinessPanels({
  page,
  initialState,
  selectedEntity,
  onNavigate = () => {},
  onLocate = () => {},
  notify = () => {},
}) {
  const common = { initialState, selectedEntity, onNavigate, onLocate, notify };
  return (
    <div
      className={`business-panels ${page === "overview" ? "business-overview" : ""}`}
    >
      {[8, 22].includes(initialState) ? (
        <BusinessStates kind={initialState} {...common} />
      ) : page === "inventory" ? (
        <Inventory {...common} />
      ) : page === "orders" ? (
        <Orders {...common} />
      ) : page === "devices" ? (
        <Devices {...common} />
      ) : page === "alerts" ? (
        <Alerts {...common} />
      ) : (
        <Overview {...common} />
      )}
    </div>
  );
}
