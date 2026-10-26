import React from "react";
import { Badge, Button, Icon, Metric, Section } from "./ui";
export default function Settings({
  settings,
  setSettings,
  roof,
  setRoof,
  notify,
}) {
  const update = (key, value) => setSettings((p) => ({ ...p, [key]: value }));
  const layers = [
    ["structure", "货架与建筑", "显示仓库结构与区域范围", "Warehouse"],
    ["devices", "作业设备", "显示场景设备与点位", "Forklift"],
    ["poi", "POI 标签", "显示编号与作业状态", "MapPin"],
    ["traffic", "道路车辆", "显示园区周边动态交通", "Truck"],
  ];
  return (
    <div className="settings-content">
      <div className="panel-title">
        <div>
          <p className="eyebrow">SCENE CONTROLS</p>
          <h1>场景设置</h1>
          <p>让视图聚焦当前工作</p>
        </div>
        <Badge>即时预览</Badge>
      </div>
      <Section title="观察模式">
        <div className="segmented">
          <button
            className={!roof ? "active" : ""}
            onClick={() => setRoof(false)}
          >
            园区总览
          </button>
          <button
            className={roof ? "active" : ""}
            onClick={() => setRoof(true)}
          >
            仓库内部
          </button>
        </div>
      </Section>
      <Section title="图层显示">
        {layers.map(([key, title, desc, icon]) => (
          <label className="layer-row" key={key}>
            <Icon name={icon} size={21} />
            <span>
              <strong>{title}</strong>
              <small>{desc}</small>
            </span>
            <input
              className="toggle"
              type="checkbox"
              role="switch"
              aria-label={title}
              checked={settings[key]}
              onChange={(e) => update(key, e.target.checked)}
            />
          </label>
        ))}
      </Section>
      <Section title="库容展示" action={<Badge tone="gray">演示调节</Badge>}>
        <p className="muted compact">
          仅调节原型中的空间显示，不改变业务库存。
        </p>
        {[
          ["rack", "货架库容", 0.8, 1600],
          ["floor", "地堆库容", 1, 800],
        ].map(([key, name, def, cap]) => (
          <div className="capacity-control" key={key}>
            <div className="split">
              <label htmlFor={key}>{name}</label>
              <strong>
                {Math.round(settings[key] * 100)}
                <small>%</small>
              </strong>
            </div>
            <input
              id={key}
              type="range"
              min="0"
              max="1"
              step=".01"
              value={settings[key]}
              onChange={(e) => update(key, +e.target.value)}
            />
            <div className="split muted">
              <span>0%</span>
              <span>默认 {def * 100}%</span>
              <span>100%</span>
            </div>
            <div className="capacity-squares">
              {Array.from({ length: 30 }, (_, i) => (
                <span
                  className={i < settings[key] * 30 ? "filled" : ""}
                  key={i}
                />
              ))}
            </div>
            <Metric
              label="示意占用"
              value={Math.round(settings[key] * cap)}
              unit="托位"
            />
          </div>
        ))}
      </Section>
      <Button
        variant="secondary"
        className="full"
        onClick={() => {
          setSettings({
            structure: true,
            devices: true,
            poi: true,
            traffic: true,
            rack: 0.8,
            floor: 1,
          });
          setRoof(false);
          notify("已恢复默认图层与库容");
        }}
      >
        <Icon name="RotateCcw" />
        恢复默认设置
      </Button>
    </div>
  );
}
