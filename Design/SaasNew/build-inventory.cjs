// Read-only source audit; writes only the SaasNew migration inventory.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const penPath='Design/GHS_Twin_SaaS_Concept/Saas.pen';
const pen=read(penPath),catalog=read('Design/GHS_Twin_SaaS_Concept/current-design.json');
const routes=read('Design/GHS_SaaS_Interactive_20261026/src/pages.json');
const components=[],images=[],types={};
function walk(n,board){
  types[n.type]=(types[n.type]||0)+1;
  if(n.reusable)components.push({id:n.id,name:n.name,board:board.id,width:n.width,height:n.height});
  for(const fill of n.fill?(Array.isArray(n.fill)?n.fill:[n.fill]):[]){
    if(fill&&fill.type==='image')images.push({nodeId:n.id,name:n.name,boardId:board.id,url:fill.url,exists:fs.existsSync(path.resolve(root,'Design/GHS_Twin_SaaS_Concept',fill.url))});
  }
  for(const child of n.children||[])walk(child,board);
}
pen.children.forEach(n=>walk(n,n));
const nativePages=new Set([1,2,3,4,5,6,10,11,12,13,14,15,16,17,18,19,20,23,24,31,32,33,34,44,45,46,47,48,49,50,51,52,53]);
const modules={
  foundation:[0,7,8,9,21,22,30,33,34],
  campus:[1,2,3,4,6,10,23,24,31,32,44],
  business:[11,12,13,14,16,17,18,19,20],
  replay:[5,15,45,46,47,48,49,50,51,52,53],
  launcher:[25,26,27],
  connection:[28,29,40,41],
  administration:[35,36,37,38,39,42,43]
};
const runtimeOverrides=[
  {id:'motion',boards:[1,2,4,5,6,11,12,13,14,15,16,17,18,19,20,31,44,45,46,47,48,49,50,51,52,53],rule:'生产侧栏已使用 React Bits 数字与 ECharts SVG 图表；以当前实际页面内容/颜色/布局为准。导航选中高光仅点击或键盘激活后移动；hover仅显示本按钮淡蓝反馈。',source:['Content/GHSTwinUI/web/app.js','Tools/GHSTwinMotion/src/runtime.jsx','Tools/GHSTwinMotion/src/charts.js','Tools/GHSTwinMotion/README.md']},
  {id:'startup',boards:[1,31],rule:'初始保持#F4F6F9底色，正式视口和字体准备完毕后呈现；禁止展示1×1临时纹理中的业务内容。ready握手即时发送；字体失败可回退，尺寸条件不得超时绕过。',source:['Content/GHSTwinUI/web/startup.js','Content/GHSTwinUI/web/index.html']},
  {id:'roof',boards:[1,16,31,32,33,34],rule:'手动点击POI/屋顶开顶0.8s，设备定位快速开顶0.5s，恢复合顶0.55s；从中央向两侧平滑打开，长蓝色拖尾。闭顶及过渡中内部标签和拾取锁定。纠正旧画板统一写0.5s的描述。',source:['Source/Test/GHSWarehouseRoofComponent.h','Source/Test/GHSWarehouseRoofComponent.cpp']},
  {id:'replay-trail',boards:[5,9,15,47,48,53],rule:'只显示移动中人工叉车当前任务尚未行驶的路线；统一#356BFA主题蓝前端到#8BB9FF淡蓝透明尾端。18cm宽，2.25m实段+0.75m空段，1.2m/s流动，不要白色流光。不同叉车路线以高度3cm+i×0.8cm错开；暂停保留当前剩余路线；静止/取放/故障无路线；卡车无路线。',source:['Scripts/ghs/replay_repair_trail_material.py','Source/Test/GHSOrderReplayActor.cpp','Source/Test/GHSOrderReplaySimulation.h']},
  {id:'replay-ripple',boards:[5,47,48,53],rule:'追溯叉车底座扩散圈使用与路线一致的可辨认主题蓝渐变；普通场景人工叉车不显示追溯扩散圈；暂停和跳转跟随同一回放时钟。',source:['Scripts/ghs/replay_ripple_shader.py','Source/Test/GHSOrderReplayActor.cpp','docs/changes/2026-10-26-replay-ripple-visibility.md']},
  {id:'replay-camera',boards:[5,47,48,53],rule:'回放全景覆盖地堆作业区；跟随可左键旋转/滚轮缩放，右键平移无效，不脱离跟随；面板收展与时间轴宽度同步平滑变化，保持镜头连续，无跳帧重定位。',source:['Source/Test/GHSWarehouseCameraPawn.cpp','Source/Test/GHSOrderReplaySession.cpp','Content/GHSTwinUI/web/replay-overlay.js']},
  {id:'agv-model',boards:[2,4,7,20,23],rule:'按实际设备ID匹配外观：AGV-01为白色扁平AGV，STACKER-04为当前场景蓝色小车。2/23页使用AGV-01的充电区场景和白色模型缩略图，4页使用STACKER-04的地堆作业区场景与蓝色模型缩略图；不能把STEP蓝色外壳误标为AGV-01。本次仅整理设计素材，不修改生产模型。',source:['Design/SaasNew/runtime/detail-alignment-validation.json','Design/SaasNew/runtime/assets/agv.png','Design/SaasNew/runtime/assets/stacker.png']},
  {id:'streaming-scope',boards:[25,26,27,28,29,35,36,37,38,39,40,41,42,43],rule:'本地Windows启动器和连接页已有实现，按Tools/PixelStreaming实际功能核对；35–43后台/管理员登录保留设计状态，不把独立React原型的模拟操作标成已部署后台。',source:['Tools/PixelStreaming/README.md','Tools/PixelStreaming/server/README.md','Tools/PixelStreaming/launcher/MainForm.cs','Tools/PixelStreaming/player/app.js','Design/GHS_Twin_SaaS_Concept/streaming-admin-design.md']}
];
const motion=[
  {name:'导航选中高光',ms:250,trigger:'点击/键盘确认导航',details:'hover不迁移选中高光；焦点有可见边框'},
  {name:'指标数字',ms:680,trigger:'首次或数值更新',details:'从当前值滚动到新值；编号/时间/未知值不滚动'},
  {name:'环图展开',ms:600,trigger:'进入相应页面'},
  {name:'柱条生长',ms:450,trigger:'进入相应页面'},
  {name:'折线描画',ms:650,trigger:'进入相应页面'},
  {name:'图表数据更新',ms:350,trigger:'实际数据变化',details:'复用实例及稳定数据ID，不变数据不重播'},
  {name:'面板条目错峰',ms:300,staggerMs:35,maxDelayMs:210,details:'轻移淡入；遥测刷新不重播'},
  {name:'业务页面切换',exitMs:120,enterMs:200,details:'保留旧内容直到淡出结束；快速导航以最后目标为准'},
  {name:'原生侧栏收展',ms:420,details:'搜索框与时间轴同步收展；追溯相机保持连续'},
  {name:'原生菜单',ms:160,details:'淡入和短距离移动'},
  {name:'POI合并拆分',ms:120,maxLocalDriftPx:8,details:'原地淡入淡出，不跨屏飞行'},
  {name:'相机定位',ms:850,details:'默认值，实际飞行范围700–1000ms；屋顶完成打开后才定位'},
  {name:'减弱动态效果',ms:0,details:'立即收敛，不循环动画；隐藏页面暂停无意义绘制'}
];
const pages=routes.map(route=>{
  const board=pen.children.find(n=>Number(n.name.match(/^\d+/)?.[0])===route.number);
  if(!board)throw Error('Missing board '+route.number);
  const index=catalog.artboards.find(x=>x.id===board.id);
  const module=Object.entries(modules).find(([,ids])=>ids.includes(route.number))?.[0];
  return {...route,id:board.id,sourceName:board.name,width:board.width,height:board.height,module,
    sourcePriority:nativePages.has(route.number)?'current UE runtime > current code > Saas.pen > prototype':route.number>=35&&route.number<=43?'Saas.pen approved design; React prototype is simulation':'current implementation where available; otherwise approved Saas.pen',
    preview:index?'Design/GHS_Twin_SaaS_Concept/'+index.preview:null,
    runtimeOverrides:runtimeOverrides.filter(x=>x.boards.includes(route.number)).map(x=>x.id),
    imageNodes:images.filter(x=>x.boardId===board.id).map(x=>x.nodeId)
  };
});
const sourcePriority=[
  {priority:1,source:'UE actual runtime screenshots + Content/GHSTwinUI/web + Tools/GHSTwinMotion',appliesTo:'Current warehouse business UI and latest motion/state behavior'},
  {priority:2,source:'Source/Test roof/replay/camera/HUD and saved Zcool scene',appliesTo:'3D interaction, POIs, roof, replay, camera, current model shape'},
  {priority:3,source:penPath,appliesTo:'Complete 54-board page/state inventory, editable components and approved unimplemented admin designs'},
  {priority:4,source:'Design/GHS_SaaS_Interactive_20261026',appliesTo:'Reference interaction flows only; prototype simulations are not evidence of production integration'},
  {priority:5,source:'Design/GHS_Warehouse_HUD',appliesTo:'Earlier separate NormalWarehouse HUD history; do not merge old V9 dual-sidebar style into SaasNew'}
];
const inventory={name:'SaasNew',auditedAt:'2026-10-27',scope:'54 approved Saas.pen pages and all their states, synchronized against latest actual warehouse UI',
  source:{path:penPath,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,penPath))).digest('hex'),version:pen.version},
  counts:{artboards:pages.length,components:components.length,images:images.length,missingImages:images.filter(x=>!x.exists).length,nodeTypes:types},
  sourcePriority,modules,pages,components,images,runtimeOverrides,motion,
  replayNavigation:read('Design/GHS_Twin_SaaS_Concept/order-replay-navigation.json'),
  figmaSuggestedPages:['00 封面与版本说明','01 设计系统与公共组件','02 园区与空间交互','03 库存订单设备告警','04 订单追溯完整流程','05 像素流启动器与连接页','06 后台与登录设计','07 交互与动效规范'],
  completionBoundary:'This inventory does not mean the Figma import has occurred. Figma file URL, node counts, screenshots and prototype links must be verified by the main task.'};
if(pages.length!==54||components.length!==47||inventory.counts.missingImages)throw Error('Inventory validation failed');
fs.writeFileSync(path.join(__dirname,'inventory.json'),JSON.stringify(inventory,null,2)+'\n');
const header='# SaasNew · 最新设计迁移清单\n\n审计日期：2026-10-27。目标是将 Saas.pen 的全部 54 个页面/状态与 47 个可复用组件整理到 Figma；不是仅迁移七个导航页。该目录为迁移准备资料，不能作为已完成 Figma 上传的证明。\n\n';
const priority='## 设计源优先级\n\n'+sourcePriority.map(x=>`${x.priority}. **${x.source}**：${x.appliesTo}`).join('\n')+'\n\n';
const pageTable='## 全部页面与状态\n\n| 编号 | 页面/状态 | 模块 | 交互 | 最新差异 |\n|---|---|---|---|---|\n'+pages.map(p=>`| ${String(p.number).padStart(2,'0')} | ${p.name.replace(/^\d+ · /,'')} | ${p.module} | ${p.interactions.join('；')} | ${p.runtimeOverrides.join('、')||'沿用批准布局并核对实际数据'} |`).join('\n')+'\n\n';
const delta='## 必须同步的最新差异\n\n'+runtimeOverrides.map(x=>`### ${x.id}\n\n${x.rule}\n\n证据：${x.source.map(s=>'`'+s+'`').join('、')}。\n`).join('\n')+'\n';
const motions='## 动效与交互参数\n\n| 动效 | 参数 | 行为 |\n|---|---|---|\n'+motion.map(x=>`| ${x.name} | ${x.ms===undefined?`${x.exitMs}ms退出 + ${x.enterMs}ms进入`:`${x.ms}ms`}${x.staggerMs?`；错峰${x.staggerMs}ms，上限${x.maxDelayMs}ms`:''} | ${[x.trigger,x.details].filter(Boolean).join('；')} |`).join('\n')+'\n\n';
const boundaries='## 数据与可用性约束\n\n- 337,783 现存、336,006 可用、156 货主、14,373 SKU；叉车台账82/正常62/禁用20/维修中0为用户核验的静态摘录，不是实时接口。\n- 库容饼图、48格货位、订单、告警和示例遥测保留“数据未核验”；真实容量/单位/场景映射缺失不补造。\n- 原生顶部搜索只查询场景目录，业务面板搜索只查询已提供样例；不能在设计注释里声称两者已经完整贯通。\n- 主仓 POI文字为“GHS · 主仓库 / 点击查看”，不恢复“普通仓库”。顶栏地址与America/Los_Angeles实时时钟保留。\n- 默认屋顶闭合，内部标签与拾取关闭；全仓恢复屋顶，定位内部设备先开顶再定位。\n- 图层四开关即时生效；货架80%、地堆100%只调整可视货物，不修改业务库存；货物图层隐藏时禁用滑条并保留数值。\n- 回放区间至少实际3600秒；4个测试订单复用5叉车+3卡车数据。跟随可旋转缩放但不可平移；点击关键事件暂停并跳转，保留当前跟随目标。\n- 回放退出必须确认；取消恢复原播放状态，确认先恢复场景再执行原操作一次。\n- 25–29为现有启动器/连接流程；35–43后台登录保持获批设计状态，不宣称真实管理员认证/云端部署已完成。\n- 蓝色用于交互/选择，橙色用于等待/待处理，红色用于故障，灰色用于禁用/未知；不以新霓虹光效替代原风格。\n\n';
const flow='## 页面导航与状态流\n\n```mermaid\nflowchart TD\n  A[31 园区默认闭顶] -->|点击POI/屋顶| B[32 开顶0.8s]\n  B --> C[01 内部总览]\n  C --> D[七个业务入口]\n  D --> E[11 库存与17物料]\n  D --> F[12/19 订单与18详情]\n  D --> G[13 设备台账/场景与02详情]\n  D --> H[14 告警与04详情]\n  D --> I[16 场景设置]\n  D --> J[15 追溯时段]\n  J -->|不足1小时| K[46 校验错误]\n  J -->|合法区间| L[45 测试订单]\n  L --> M[05 全设备回放]\n  M --> N[47 暂停/跟随]\n  M --> O[48 关键事件定位]\n  M --> P[49 区间完成]\n  M -->|切换页面| Q[50 跨页退出确认]\n  M -->|手动结束| R[51 结束确认]\n  Q -->|确认恢复场景| D\n  R -->|确认恢复场景| L\n  Q -->|取消恢复播放状态| M\n  R -->|取消恢复播放状态| M\n  C -->|全仓/Home/中键| A\n  S[42 管理员登录设计] --> T[35 后台运行中设计]\n  S --> U[43 登录失败设计]\n  T --> V[37 结束用户确认]\n  T --> W[38 停止服务确认]\n  W --> X[36 后台已停止]\n  Y[25 启动器待启动] --> Z[26 启动器运行]\n  Z --> AA[28 用户连接]\n  AA -->|首帧就绪| A\n  AA --> AB[29 连接边界]\n```\n\n';
const handoff='## Figma 文件组织与验收\n\n'+inventory.figmaSuggestedPages.map((x,i)=>`${i+1}. ${x}`).join('\n')+'\n\n保留可编辑文字、矢量、组件与实例；3D场景可以用当前项目截图作为位图底图。不要将54张整页PNG当成完成可编辑迁移。每张画板保留原编号与来源ID，注明当前实现/设计待开发边界；交互写入原型连线与附近的行为说明。最终需记录Figma文件URL、54页覆盖表、47组件迁移情况、图源日期、缺失资源清单与实际保存/原型预览证据。\n\n旧 `Design/GHS_Warehouse_HUD` 是不同阶段设计，保留档案，不纳入当前SaasNew的双侧栏视觉。源文件与历史导出不删除。后续经用户批准的设计以SaasNew为维护入口，源代码仍是运行行为核对依据。\n';
fs.writeFileSync(path.join(__dirname,'DESIGN_INVENTORY.md'),header+priority+pageTable+delta+motions+boundaries+flow+handoff);
console.log(JSON.stringify({pages:pages.length,components:components.length,imageFills:images.length,missingImages:inventory.counts.missingImages,output:__dirname}));
