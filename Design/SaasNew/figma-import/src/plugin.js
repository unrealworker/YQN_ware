/* Native editable migration; deliberately never clears or deletes existing document nodes. */
const Migration = (() => {
  let activeReport=null;
  function errorDetails(error){let message='Unknown migration error',stack='';try{message=String(error&&error.message||error);}catch(_){}try{stack=String(error&&error.stack||'');}catch(_){}return{message,stack};}
  const MODULES={foundation:'01 · 设计系统与状态',campus:'02 · 园区与空间交互',business:'03 · 库存 / 订单 / 设备 / 告警',replay:'04 · 作业追溯',launcher:'05 · 本地启动',connection:'06 · 连接与异常',administration:'07 · 管理后台（设计阶段）'};
  const exactProps=new Set(['id','originalId','type','name','x','y','width','height','fill','stroke','strokeWidth','strokeAlignment','strokeLinejoin','strokeLinecap','cornerRadius','effect','opacity','enabled','rotation','layout','children','reusable','clip','gap','padding','alignItems','justifyContent','metadata','content','fontFamily','fontSize','fontWeight','textGrowth','lineHeight','textAlign','textAlignVertical','letterSpacing','library','icon','geometry','viewBox','innerRadius','startAngle','sweepAngle','ref','descendants','sourceComponent','expandedReference','svg']);
  function decode(s){const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',table=new Int16Array(128);table.fill(-1);for(let i=0;i<alphabet.length;i++)table[alphabet.charCodeAt(i)]=i;const out=new Uint8Array(Math.floor(s.length*3/4)-(s.endsWith('==')?2:s.endsWith('=')?1:0));let buffer=0,bits=0,offset=0;for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);if(c===61)break;const n=c<128?table[c]:-1;if(n<0)continue;buffer=(buffer<<6)|n;bits+=6;if(bits>=8){bits-=8;out[offset++]=(buffer>>bits)&255;}}return offset===out.length?out:out.slice(0,offset);}
  function solid(hex){const c=SaasModel.color(hex);return{type:'SOLID',color:{r:c.r,g:c.g,b:c.b},opacity:c.a};}
  const xml=s=>String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
  const cssColor=hex=>{const c=SaasModel.color(hex);return 'rgba('+[c.r,c.g,c.b].map(v=>Math.round(v*255)).concat(c.a).join(',')+')';};
  const putData=(node,key,value)=>node.setSharedPluginData('saasnew',key,value);
  const readData=(node,key)=>node.getSharedPluginData('saasnew',key);
  const pageNames=['01 · 全流程原型 / 54 画板','02 · 组件库 / 47 主组件','03 · 交互规范与迁移说明'];
  const approvedRevisionBase='339ca0174b7fbb54bbc3b742b383885a5bb85552a98f78d61371ce23a8cfec34';
  async function ownedResume(figma,payload,ix){
    if(figma.root.children.length!==3)return null;
    const pages=pageNames.map(name=>figma.root.children.filter(p=>p.name===name));if(pages.some(a=>a.length!==1))return null;
    const [nativePage,library,docs]=pages.map(a=>a[0]);
    let owner;try{owner=JSON.parse(readData(figma.root,'saas.migrationOwner')||'null');}catch(_){return null;}
    const revision=payload.revisionFrom;
    const revisionValid=revision&&revision.sourceHash===approvedRevisionBase&&revision.completed===true&&(revision.boards||[]).length===54&&(revision.components||[]).length===47&&revision.tree;
    const knownPreviousRevision=revisionValid&&owner&&owner.revisionBaseHash===approvedRevisionBase&&(revision.allowedRevisionHashes||[]).includes(owner.sourceHash);
    const updatingRevision=revisionValid&&owner&&(owner.sourceHash===approvedRevisionBase||knownPreviousRevision)&&payload.sourceHash!==approvedRevisionBase;
    const continuingRevision=revisionValid&&owner&&owner.sourceHash===payload.sourceHash&&owner.revisionBaseHash===approvedRevisionBase;
    if(!owner||owner.sourceHash!==payload.sourceHash||updatingRevision||continuingRevision){
      const allow=updatingRevision||continuingRevision?revision:payload.resumeFrom;if(!allow||(!(updatingRevision||continuingRevision)&&allow.sourceHash!==payload.sourceHash))return null;
      for(const saved of [].concat(allow.components||[],allow.runtimeComponents||[],allow.boards||[])){
        const actual=await figma.getNodeByIdAsync(saved.id);if(!actual||readData(actual,'saas.sourceId')!==saved.sourceId)return null;
        let top=actual;while(top.parent&&top.parent.type!=='DOCUMENT')top=top.parent;
        if(![nativePage.id,library.id,docs.id].includes(top.id))return null;
      }
      if((allow.components||[]).length!==47||(allow.boards||[]).length!==((updatingRevision||continuingRevision)?54:40))return null;
    }
    const base=updatingRevision||continuingRevision?revision.tree:{boards:[],components:[],runtimeComponents:[]};
    const sourceBoards=new Map(payload.pen.children.map(b=>[b.id,SaasModel.expand(b,ix.components)]));
    function validateNode(actual,expected,master=false,previous){
      if(readData(actual,'saas.sourceId')!==(expected.originalId||expected.id))throw new Error('非本次源节点，拒绝复用：'+actual.name);
      const types={frame:master?'COMPONENT':'FRAME',text:'TEXT',rectangle:'RECTANGLE',ellipse:'ELLIPSE',icon:'FRAME',svg:'FRAME',path:'FRAME'};
      if(actual.type!==types[expected.type])throw new Error('复用节点类型不一致：'+actual.name);
      if(['icon','svg','path'].includes(expected.type))return;
      const children=expected.children||[],older=previous&&previous.children||[],seen=new Set();
      for(const child of actual.children||[]){const id=readData(child,'saas.sourceId');if(seen.has(id))throw new Error('已有重复源节点：'+id);seen.add(id);const old=older.find(n=>n.id===id),match=children.find(n=>(n.originalId||n.id)===id)||old;if(!match)throw new Error('出现未属于本次导入的子节点：'+child.name);validateNode(child,match,false,old);}
    }
    for(const child of library.children){
      if(child.type==='SECTION'&&child.name==='最新 UE 实际页面组件'){
        for(const c of child.children){const id=readData(c,'saas.sourceId'),old=base.runtimeComponents.find(n=>n.id===id),source=ix.runtimeComponents.find(n=>n.id===id);if(!source&&!old)throw new Error('未知当前组件：'+c.name);validateNode(c,source?SaasModel.expand(source,ix.components):old,true,old);}
      }else{const id=readData(child,'saas.sourceId'),source=ix.components[id],old=base.components.find(n=>n.id===id);if(!source&&!old)throw new Error('未知主组件：'+child.name);validateNode(child,source?SaasModel.expand(source,ix.components):old,true,old);}
    }
    for(const section of nativePage.children){
      const module=Object.keys(MODULES).find(k=>MODULES[k]===section.name);if(section.type!=='SECTION'||!module)throw new Error('未知页面分区：'+section.name);
      for(const child of section.children){const id=readData(child,'saas.sourceId'),board=sourceBoards.get(id);
        if(board){const info=payload.inventory.pages.find(p=>p.id===id);if(info.module!==module)throw new Error('画板所属模块不匹配');validateNode(child,board,false,base.boards.find(n=>n.id===id));}
        else if(id&&id.startsWith('note-')&&!id.startsWith('note-text-')){const bid=id.slice(5);if(!sourceBoards.has(bid)||child.type!=='FRAME'||child.children.length>1||child.children.some(c=>c.type!=='TEXT'||readData(c,'saas.sourceId')!=='note-text-'+bid))throw new Error('未知交互说明：'+child.name);}
        else throw new Error('未知画板节点：'+child.name);
      }
    }
    if(docs.children.some(n=>readData(n,'saas.sourceId')!=='docs'||n.type!=='FRAME'||n.children.some(c=>readData(c,'saas.sourceId')!=='docs-text'||c.type!=='TEXT')))throw new Error('交互规范页包含未知内容');
    return{nativePage,library,docs,owned:true,revisionBaseHash:updatingRevision||continuingRevision?approvedRevisionBase:null};
  }
  function interruptedScaffold(figma,first){
    const names=['01 · 全流程原型 / 54 画板','02 · 组件库 / 47 主组件','03 · 交互规范与迁移说明'];
    if(figma.root.children.length!==3)return null;
    const pages=names.map(name=>figma.root.children.filter(p=>p.name===name));if(pages.some(a=>a.length!==1))return null;
    const [nativePage,library,docs]=pages.map(a=>a[0]);if(nativePage.children.length||docs.children.length||library.children.length!==1)return null;
    const node=library.children[0];
    if(node.type!=='COMPONENT'||node.name!==first.name||node.children.length||node.width!==100||node.height!==100||node.x!==0||node.y!==0||node.visible!==true||node.fills.length!==0||node.layoutMode!=='NONE')return null;
    return{nativePage,library,docs,component:node};
  }
  function svgFor(n,payload){
    if(n.type==='svg')return n.svg;
    if(n.type==='icon')return '<svg xmlns="http://www.w3.org/2000/svg" width="'+(n.width||24)+'" height="'+(n.height||24)+'" viewBox="0 0 24 24" fill="none" stroke="'+cssColor(n.fill||'#25364B')+'" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+payload.icons[n.icon]+'</svg>';
    return '<svg xmlns="http://www.w3.org/2000/svg" width="'+(n.width||1)+'" height="'+(n.height||1)+'" viewBox="'+(n.viewBox||[0,0,n.width||1,n.height||1]).join(' ')+'"><path d="'+xml(n.geometry)+'" fill="'+(n.fill?cssColor(n.fill):'none')+'" stroke="'+(n.stroke?cssColor(n.stroke):'none')+'" stroke-width="'+(n.strokeWidth||1)+'" stroke-linecap="'+(n.strokeLinecap||'butt')+'" stroke-linejoin="'+(n.strokeLinejoin||'miter')+'"/></svg>';
  }
  async function run(figma,payload,progress=()=>{}){
    const report={schemaVersion:1,name:'SaasNew',startedAt:new Date().toISOString(),source:payload.source,sourceHash:payload.sourceHash,corrections:payload.corrections||[],completed:false,counts:{boards:0,components:0,runtimeComponents:0,editableBoardNodes:0,texts:0,characters:0,imageUses:0,uniqueImages:0,icons:0,paths:0,expandedReferences:0,prototypeConnections:0,notes:0},fonts:[],warnings:[],errors:[],boards:[],components:[],runtimeComponents:[],links:[],coverage:[]};
    activeReport=report;report.phase='validate-document';
    try {
    if(figma.editorType!=='figma')throw new Error('请在 Figma Design 中运行。');
    if(figma.root.name.trim()!=='SaasNew')throw new Error('仅可导入名为 SaasNew 的新空白文件；当前文件：'+figma.root.name);
    await figma.loadAllPagesAsync();
    const ix=SaasModel.index(payload.pen);
    report.phase='validate-existing-document';
    const resume=interruptedScaffold(figma,Object.values(ix.components)[0])||await ownedResume(figma,payload,ix);
    if(figma.root.children.some(p=>p.children.length>0)&&!resume)throw new Error('文档不是空白，已拒绝导入。仅可续传经过源哈希和节点ID核验的本次导入；插件不会清空任何内容。');
    if(resume){report.resumedEmptyScaffold=!resume.owned;report.resumedOwnedImport=!!resume.owned;report.warnings.push(resume.owned?'已按源ID续传本次部分导入；没有删除已有节点。':'已复用上次无ID私有数据错误留下的精确空骨架；没有删除节点。');}
    ix.allNodes.forEach(n=>Object.keys(n).forEach(k=>{if(!exactProps.has(k))throw new Error('尚未支持的属性 '+n.id+'.'+k+'；未开始导入，请补齐转换。');}));
    if(payload.pen.children.length!==54||Object.keys(ix.components).length!==47)throw new Error('54 画板 / 47 组件完整性检查失败。');
    report.phase='preflight-source';
    const allFonts=await figma.listAvailableFontsAsync(),fontMap={},images={},boardNodes={},nodeMaps={},expanded=payload.pen.children.map(n=>SaasModel.expand(n,ix.components));
    expanded.forEach(b=>SaasModel.walk(b,n=>{
      Object.keys(n).forEach(k=>{if(!exactProps.has(k))throw new Error('尚未支持的覆盖属性 '+n.id+'.'+k);});
      if(n.fill){if(typeof n.fill==='string')SaasModel.color(n.fill);else if(n.fill.type!=='image'||!payload.images[n.fill.url])throw new Error('未支持或缺少图片填充 '+n.id);}
      if(n.stroke)SaasModel.color(n.stroke);
      if(n.effect)(Array.isArray(n.effect)?n.effect:[n.effect]).forEach(e=>{if(e.type!=='shadow')throw new Error('Unsupported effect '+e.type);SaasModel.color(e.color);});
      if(n.type==='icon'&&!payload.icons[n.icon])throw new Error('未支持图标 '+n.icon);
      if(n.type==='svg'&&(!n.svg||!n.svg.trim().startsWith('<svg')))throw new Error('SVG 内容无效 '+n.id);
      if(n.metadata&&n.metadata.scroll&&!['VERTICAL','HORIZONTAL','BOTH','NONE'].includes(n.metadata.scroll.direction))throw new Error('未知滚动方向 '+n.id);
    }));
    const sourceMaps={};payload.inventory.pages.forEach(p=>{const b=expanded.find(n=>n.id===p.id);if(!b)throw new Error('Missing inventory board '+p.number);const counts={};SaasModel.walk(b,n=>{const id=n.originalId||n.id;counts[id]=(counts[id]||0)+1;});sourceMaps[p.number]=counts;});
    const invalidLinks=payload.links.filter(link=>link.sourceBoard===link.targetBoard||!sourceMaps[link.targetBoard]||(sourceMaps[link.sourceBoard]||{})[link.sourceNodeId]!==1);
    if(invalidLinks.length)throw new Error('交互连线预检失败 '+invalidLinks.length+' 条，未开始导入：'+JSON.stringify(invalidLinks.slice(0,12)));
    const styleFor=w=>String(w)==='600'?'SemiBold':String(w)==='500'?'Medium':String(w)==='700'?'Bold':'Regular';
    async function fontFor(n){
      const family=n.fontFamily||'Noto Sans SC',style=styleFor(n.fontWeight),key=family+' / '+style;
      if(fontMap[key])return fontMap[key];
      const families=[family,'Noto Sans SC','Noto Sans CJK SC','Microsoft YaHei','PingFang SC','Source Han Sans CN','Arial Unicode MS','Inter'];
      let chosen=null;
      const closest=style==='SemiBold'?['SemiBold','Semibold','DemiBold','Bold','Medium','Regular']:style==='Bold'?['Bold','SemiBold','Semibold','DemiBold','Medium','Regular']:style==='Medium'?['Medium','Regular','SemiBold','Semibold','Bold']:['Regular','Normal','Book','Medium'];
      for(const f of families){const candidates=allFonts.filter(v=>v.fontName.family===f);for(const s of closest){chosen=candidates.find(v=>v.fontName.style===s);if(chosen)break;}chosen=chosen||candidates[0];if(chosen)break;}
      if(!chosen)throw new Error('没有可加载字体，请安装 Noto Sans SC。');
      await figma.loadFontAsync(chosen.fontName);fontMap[key]=chosen.fontName;
      report.fonts.push({requested:key,resolved:chosen.fontName.family+' / '+chosen.fontName.style,fallback:chosen.fontName.family!==family||chosen.fontName.style!==style,uses:0});
      return chosen.fontName;
    }
    const requested={};expanded.forEach(b=>SaasModel.walk(b,n=>{if(n.type==='text')requested[(n.fontFamily||'Noto Sans SC')+'|'+(n.fontWeight||'normal')]=n;}));
    report.phase='load-fonts';
    for(const n of Object.values(requested))await fontFor(n);
    await fontFor({fontFamily:'Noto Sans SC',fontWeight:'600'});
    progress('字体已加载；正在嵌入离线图像');
    report.phase='embed-images';
    for(const [url,asset]of Object.entries(payload.images)){if(Math.max(asset.width,asset.height)>4096)throw new Error('图片超出 4096: '+url);images[url]=figma.createImage(decode(asset.base64)).hash;}
    report.counts.uniqueImages=Object.keys(images).length;
    const nativePage=resume?resume.nativePage:figma.root.children[0];nativePage.name='01 · 全流程原型 / 54 画板';
    const library=resume?resume.library:figma.createPage();library.name='02 · 组件库 / 47 主组件';
    const docs=resume?resume.docs:figma.createPage();docs.name='03 · 交互规范与迁移说明';
    let resumeComponent=resume&&resume.component;
    putData(figma.root,'saas.migrationOwner',JSON.stringify({sourceHash:payload.sourceHash,schemaVersion:1,revisionBaseHash:resume&&resume.revisionBaseHash||null}));
    report.counts.reusedNodes=0;
    report.counts.hiddenObsoleteNodes=0;report.hiddenObsoleteNodes=[];const hiddenIds=new Set();
    async function hideObsolete(node){
      if(readData(node,'saas.sourceId')){node.visible=false;putData(node,'saas.obsoleteFor',payload.sourceHash);if(!hiddenIds.has(node.id)){hiddenIds.add(node.id);report.hiddenObsoleteNodes.push({id:node.id,sourceId:readData(node,'saas.sourceId'),name:node.name});report.counts.hiddenObsoleteNodes++;}}
      if(typeof node.setReactionsAsync==='function'&&(node.reactions||[]).length)await node.setReactionsAsync([]);
      for(const child of node.children||[])await hideObsolete(child);
    }
    async function hideExtras(parent,ids){for(const child of parent.children||[]){const id=readData(child,'saas.sourceId');if(id&&!ids.has(id))await hideObsolete(child);}}
    function existing(parent,n,scope){const id=n.originalId||n.id,found=parent.children.filter(c=>readData(c,'saas.sourceId')===id);if(found.length>1)throw new Error('重复源节点不能续传：'+n.id);if(found.length)return found[0];if(!scope)return null;const candidates=[];function scan(node){if(node!==scope&&readData(node,'saas.sourceId')===id)candidates.push(node);if(node!==scope&&readData(node,'saas.componentId'))return;for(const child of node.children||[])scan(child);}scan(scope);if(candidates.length>1)throw new Error('移动节点源ID不唯一：'+id);return candidates[0];}
    function sectionFor(parent,name){const matches=parent.children.filter(c=>c.type==='SECTION'&&c.name===name);if(matches.length>1)throw new Error('重复分区 '+name);const section=matches[0]||figma.createSection();section.name=name;parent.appendChild(section);putData(section,'saas.sectionOwner',payload.sourceHash);return section;}
    figma.skipInvisibleInstanceChildren=false;
    function paints(fill){
      if(!fill)return[];
      if(typeof fill==='string')return[solid(fill)];
      if(fill.type==='image'){
        if(!images[fill.url])throw new Error('未嵌入图片 '+fill.url);
        const p={type:'IMAGE',imageHash:images[fill.url],scaleMode:fill.mode==='contain'?'FIT':'FILL',visible:fill.enabled!==false};
        if(fill.transform){const t=fill.transform;p.scaleMode='CROP';p.imageTransform=[[t[0],t[2],t[4]],[t[1],t[3],t[5]]];}
        return[p];
      }
      throw new Error('未支持填充 '+JSON.stringify(fill));
    }
    function box(n,node,parent){
      node.name=n.name||n.content||n.icon||n.type;
      putData(node,'saas.sourceId',n.originalId||n.id);
      putData(node,'saas.sourceType',n.type);
      if(n.metadata)putData(node,'saas.metadata',JSON.stringify(n.metadata));
      if(n.sourceComponent){putData(node,'saas.componentId',n.sourceComponent);putData(node,'saas.referenceMode','expanded-editable');}
      node.visible=n.enabled!==false;putData(node,'saas.obsoleteFor','');
      if(hiddenIds.delete(node.id)){report.hiddenObsoleteNodes=report.hiddenObsoleteNodes.filter(v=>v.id!==node.id);report.counts.hiddenObsoleteNodes--;}
      node.opacity=n.opacity===undefined?1:n.opacity;
      node.rotation=n.rotation?-n.rotation:0;
      const w=typeof n.width==='number'?Math.max(.01,n.width):null,h=typeof n.height==='number'?Math.max(.01,n.height):null;
      if(node.type!=='TEXT'&&(w||h))node.resize(w||Math.max(.01,node.width),h||Math.max(.01,node.height));
      if(parent.layoutMode&&parent.layoutMode!=='NONE'){
        if(n.width==='fill_container')node.layoutSizingHorizontal='FILL';
        if(n.height==='fill_container')node.layoutSizingVertical='FILL';
      }else{node.x=Number(n.x)||0;node.y=Number(n.y)||0;}
      if(!['icon','path','svg'].includes(n.type)&&'fills'in node)node.fills=paints(n.fill);
      if(!['icon','path','svg'].includes(n.type)&&'strokes'in node){node.strokes=n.stroke?[solid(n.stroke)]:[];if(n.stroke){if(n.strokeWidth&&typeof n.strokeWidth==='object'){node.strokeWeight=0;for(const side of ['top','right','bottom','left'])node['stroke'+side[0].toUpperCase()+side.slice(1)+'Weight']=n.strokeWidth[side]||0;}else node.strokeWeight=n.strokeWidth===undefined?1:n.strokeWidth;}node.strokeAlign=n.strokeAlignment==='inner'?'INSIDE':n.strokeAlignment==='outer'?'OUTSIDE':'CENTER';}
      if(n.cornerRadius!==undefined&&'cornerRadius'in node)node.cornerRadius=n.cornerRadius;
      if(n.effect){const effects=Array.isArray(n.effect)?n.effect:[n.effect];node.effects=effects.map(e=>{if(e.type!=='shadow')throw new Error('Unsupported effect '+e.type);const c=SaasModel.color(e.color);return{type:e.shadowType==='inner'?'INNER_SHADOW':'DROP_SHADOW',color:{r:c.r,g:c.g,b:c.b,a:c.a},offset:e.offset||{x:0,y:0},radius:e.blur||0,spread:0,visible:true,blendMode:'NORMAL'};});}
    }
    async function create(n,parent,ctx,isMaster=false,scope=null){
      report.activeNode={sourceId:n.originalId||n.id,type:n.type,name:n.name||n.content||'',parentId:parent.id};
      let node=existing(parent,n,scope);
      if(node)report.counts.reusedNodes++;
      else if(n.type==='frame'){if(isMaster&&resumeComponent&&parent===library){node=resumeComponent;resumeComponent=null;}else node=isMaster?figma.createComponent():figma.createFrame();}
      else if(n.type==='text')node=figma.createText();
      else if(n.type==='rectangle')node=figma.createRectangle();
      else if(n.type==='ellipse')node=figma.createEllipse();
      else if(['icon','path','svg'].includes(n.type))node=figma.createNodeFromSvg(svgFor(n,payload));
      else throw new Error('Unsupported expanded type '+n.type+' '+n.id);
      parent.appendChild(node);
      if(typeof node.setReactionsAsync==='function'&&(node.reactions||[]).length)await node.setReactionsAsync([]);
      if(n.type==='frame'){
        node.fills=[];node.clipsContent=n.clip===true;
        if(n.metadata&&n.metadata.scroll){const direction=n.metadata.scroll.direction;if(!['VERTICAL','HORIZONTAL','BOTH','NONE'].includes(direction))throw new Error('未知滚动方向 '+direction);node.overflowDirection=direction;}
        node.layoutMode=n.layout==='none'?'NONE':n.layout==='vertical'?'VERTICAL':'HORIZONTAL';
        if(node.layoutMode!=='NONE'){
          node.primaryAxisSizingMode='FIXED';node.counterAxisSizingMode='FIXED';node.itemSpacing=n.gap||0;
          const p=Array.isArray(n.padding)?n.padding:[n.padding||0,n.padding||0];
          node.paddingTop=p[0]||0;node.paddingBottom=p.length===4?p[2]:p[0]||0;node.paddingRight=p[1]||0;node.paddingLeft=p.length===4?p[3]:p[1]||0;
          node.primaryAxisAlignItems=n.justifyContent==='center'?'CENTER':n.justifyContent==='space_between'?'SPACE_BETWEEN':'MIN';node.counterAxisAlignItems=n.alignItems==='center'?'CENTER':'MIN';
        }
      }
      if(n.type==='text'){
        node.fontName=await fontFor(n);node.fontSize=n.fontSize||14;node.characters=String(n.content||'');
        node.textAutoResize=n.textGrowth==='fixed-width-height'?'NONE':n.textGrowth==='fixed-width'?'HEIGHT':'WIDTH_AND_HEIGHT';
        if(n.textGrowth&&typeof n.width==='number')node.resize(Math.max(.01,n.width),Math.max(.01,typeof n.height==='number'?n.height:node.height));
        if(n.lineHeight!==undefined)node.lineHeight={unit:'PERCENT',value:n.lineHeight*100};
        if(n.letterSpacing!==undefined)node.letterSpacing={unit:'PIXELS',value:n.letterSpacing};
        node.textAlignHorizontal=n.textAlign==='center'?'CENTER':n.textAlign==='right'?'RIGHT':'LEFT';
        node.textAlignVertical=n.textAlignVertical==='middle'?'CENTER':n.textAlignVertical==='bottom'?'BOTTOM':'TOP';
        const fr=report.fonts.find(f=>f.requested===(n.fontFamily||'Noto Sans SC')+' / '+styleFor(n.fontWeight));if(fr)fr.uses++;
      }
      box(n,node,parent);
      if(n.type==='ellipse'&&(n.innerRadius!==undefined||n.sweepAngle!==undefined)){const start=(n.startAngle||0)*Math.PI/180;node.arcData={startingAngle:start,endingAngle:start+(n.sweepAngle===undefined?360:n.sweepAngle)*Math.PI/180,innerRadius:n.innerRadius||0};}
      if(ctx){
        const key=n.originalId||n.id;(ctx.nodes[key]||(ctx.nodes[key]=[])).push(node);
        report.counts.editableBoardNodes++;
        if(n.expandedReference)report.counts.expandedReferences++;
        if(n.type==='text'){report.counts.texts++;report.counts.characters+=node.characters.length;ctx.texts.push([key,node.characters]);}
        if(n.fill&&n.fill.type==='image')report.counts.imageUses++;
        if(n.type==='icon')report.counts.icons++;if(n.type==='path'||n.type==='svg')report.counts.paths++;
      }
      const childScope=n.sourceComponent||!scope?node:scope;
      for(const child of n.children||[])await create(child,node,ctx,false,childScope);
      if(n.type==='frame')await hideExtras(node,new Set((n.children||[]).map(c=>c.originalId||c.id)));
      if(n.type==='frame'&&node.layoutMode!=='NONE'){
        if(n.width===undefined)node.layoutSizingHorizontal='HUG';
        if(n.height===undefined)node.layoutSizingVertical='HUG';
      }
      return node;
    }
    await figma.setCurrentPageAsync(library);
    report.phase='update-components';
    let cindex=0;
    for(const original of Object.values(ix.components)){
      const n=SaasModel.expand(original,ix.components);const node=await create(n,library,null,true);
      node.x=(cindex%3)*1400;node.y=Math.floor(cindex/3)*1300;node.description='Saas.pen 主组件 '+original.id+'。画板引用已展开为原生可编辑节点，保留来源 ID 与覆盖内容。';
      report.components.push({sourceId:original.id,id:node.id,name:node.name});report.counts.components++;cindex++;
    }
    if(ix.runtimeComponents.length){
      const latest=sectionFor(library,'最新 UE 实际页面组件');latest.x=4500;latest.y=0;let index=0;
      for(const original of ix.runtimeComponents){const n=SaasModel.expand(original,ix.components),node=await create(n,latest,null,true);node.x=(index%3)*1500+80;node.y=Math.floor(index/3)*1500+100;node.name='UE 当前 / '+(n.name||n.id);node.description='依据当前 UE 实际页面提取的可编辑组件；与原 Saas.pen 47 个历史主组件分开保留。';report.runtimeComponents.push({sourceId:n.id,id:node.id,name:node.name});report.counts.runtimeComponents++;index++;}
      latest.resizeWithoutConstraints(4600,Math.ceil(index/3)*1500+200);
    }
    await figma.setCurrentPageAsync(nativePage);
    report.phase='update-boards';
    const sections={};let moduleY=0;
    for(const [key,label]of Object.entries(MODULES)){
      const boards=payload.inventory.pages.filter(p=>p.module===key);
      const section=sectionFor(nativePage,label);section.x=0;section.y=moduleY;sections[key]=section;
      let y=100;
      for(const info of boards){
        const source=expanded.find(n=>n.id===info.id);if(!source)throw new Error('Missing board '+info.id);
        const ctx={nodes:{},texts:[]};const board=await create(source,section,ctx);
        board.x=80;board.y=y;board.name=info.number===32?source.name.replace(/0\.5\s*(s|秒)/g,'0.8 秒'):source.name;
        const status=info.module==='administration'?'设计阶段 · 未连接生产后台':payload.overrides.boardStatus&&payload.overrides.boardStatus[info.number]||'已批准设计 · 以最新 UE 实现覆盖为准';
        putData(board,'saas.route',String(info.number));putData(board,'saas.implementation',status);
        const expected=payload.expected.textByBoard[info.id]||[];const actual=ctx.texts;
        const textOK=JSON.stringify(expected)===JSON.stringify(actual);if(!textOK)report.errors.push('Text mismatch board '+info.number);
        report.coverage.push({board:info.number,sourceId:info.id,texts:actual.length,expectedTexts:expected.length,textExact:textOK});
        boardNodes[info.number]=board;nodeMaps[info.number]=ctx.nodes;report.boards.push({number:info.number,sourceId:info.id,id:board.id,name:board.name,width:board.width,height:board.height,status});report.counts.boards++;
        const extra=info.module==='administration'?'后台画板为设计与模拟流程，未声明生产管理功能已接入。':info.module==='replay'?'追溯使用测试订单/预制设备路径；最小时段 1 小时。只显示回放设备，退出/换页必须确认结束。':'';
        const interactions=(payload.overrides.boardInteractions&&payload.overrides.boardInteractions[info.number]||info.interactions).map(s=>info.number===32||info.number===33||info.number===34?s.replace(/0\.5\s*秒(溶解|开顶)/g,'0.8 秒$1'):s);
        const notes=[board.name,status,'交互：',...interactions.map((s,i)=>(i+1)+'. '+s),extra,'通用：点击后导航高光跟随 250 ms；hover 仅改变悬停背景。面板过渡 420 ms，镜头跟随及时间轴连续。','屋顶：手动展开 0.8 s；从设备定位展开 0.5 s；重置恢复屋顶。'].filter(Boolean).join('\n');
        const card=await create({type:'frame',id:'note-'+info.id,name:'交互与执行状态 · '+info.number,layout:'vertical',width:640,padding:28,gap:16,fill:'#FFFFFF',cornerRadius:16,children:[{type:'text',id:'note-text-'+info.id,content:notes,fontFamily:'Noto Sans SC',fontSize:18,lineHeight:1.7,width:584,textGrowth:'fixed-width',fill:'#25364B'}]},section,null);
        card.x=board.x+board.width+60;card.y=y;report.counts.notes++;
        y+=Math.max(board.height,card.height)+160;
        progress('画板 '+report.counts.boards+'/54 · '+board.name);
      }
      section.resizeWithoutConstraints(Math.max(5000,...boards.map(p=>p.width+900)),y+80);moduleY+=y+420;
    }
    for(const link of payload.links){
      report.phase='update-prototype-links';
      const sourceList=(nodeMaps[link.sourceBoard]||{})[link.sourceNodeId]||[],target=boardNodes[link.targetBoard];
      if(sourceList.length!==1||!target){report.errors.push('Ambiguous/missing link '+JSON.stringify(link));continue;}
      const node=sourceList[0];await node.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:target.id,navigation:'NAVIGATE',transition:{type:'DISSOLVE',easing:{type:'EASE_OUT'},duration:.2},preserveScrollPosition:false}]}]);
      report.links.push({...link,nodeId:node.id,destinationId:target.id});report.counts.prototypeConnections++;
    }
    const expectedReactions=new Map(report.links.map(link=>[link.nodeId,link.destinationId]));let actualConnections=0;const checked=new Set();
    report.phase='verify-reactions';
    for(const entries of Object.values(nodeMaps))for(const list of Object.values(entries))for(const node of list){if(checked.has(node.id))continue;checked.add(node.id);const reactions=node.reactions||[],destination=expectedReactions.get(node.id);if(destination){const r=reactions[0],a=r&&(r.actions||[r.action])[0];if(reactions.length!==1||r.trigger.type!=='ON_CLICK'||!a||a.type!=='NODE'||a.destinationId!==destination)report.errors.push('实际连线回读不一致：'+node.id);else actualConnections++;}else if(reactions.length)report.errors.push('存在过期连线：'+node.id);}
    for(const old of report.hiddenObsoleteNodes){const node=await figma.getNodeByIdAsync(old.id);if(node.visible||(node.reactions||[]).length)report.errors.push('旧节点隐藏/清线失败：'+old.id);}
    report.counts.actualPrototypeConnections=actualConnections;
    nativePage.flowStartingPoints=[{nodeId:boardNodes[31].id,name:'GHS 仓储数字孪生 · 主流程'},{nodeId:boardNodes[15].id,name:'作业追溯 · 完整流程'},{nodeId:boardNodes[42].id,name:'管理后台 · 设计演示'}];
    await figma.setCurrentPageAsync(docs);
    report.phase='update-documentation';
    const docText=['SaasNew · 最新设计迁移','54 个画板 / 47 个主组件 / 原生可编辑文字、图形和图像填充','来源优先级：最新 UE 实际页面 > 当前生产代码 > 已批准 Saas.pen > 独立交互原型。','主组件独立整理；画板中的组件引用展开为原生可编辑图层，覆盖文字/布局/图标完整保留，来源 ID 记录在 pluginData。','原型连线用于说明页面与关键路径；真实业务数据、实时 3D、连续轨迹播放仍由 UE 项目执行。','后台与登录管理页面：设计阶段，未声明已连接真实后台。','屋顶：手动展开 0.8 秒；定位设备 0.5 秒；重置 0.55 秒。','图层开关选中蓝 #356BFA；货架库容默认 0.8，地堆库容默认 1。','导航 250ms；数字 680ms；环图 600ms；柱图 450ms；折线 650ms；更新 350ms。','面板交错 300ms + 每项35ms（上限210ms）；出场120ms / 入场200ms；侧栏420ms；减少动画设置为0。','追溯：至少1小时；测试订单；5个人工叉车、3辆装卸车；暂停、倍速、拖动、事件标记、设备跟随、手动结束。','叉车轨迹：仅行驶且只余程；主题蓝渐变虚线，实线2.25m/间隔0.75m，流速1.2m/s，无白流光。叉车底部扩散保持同蓝色，非回放不出现。','跟随视角可旋转，平移无效；侧栏变化保持镜头连续；装卸车不显示轨迹。','验收边界：构建检查并不能替代 Figma 真实导入。导入完成后下载 acceptance.json，必须检查画板54、组件47、文本完全一致、连线匹配、错误0，以及字体替代记录。','图片变换：Pencil 的 6 值 affine transform 按同矩阵导入 CROP；需抽查带裁剪场景的视图，若存在差异应在正式验收中记录。'].join('\n\n');
    await create({type:'frame',id:'docs',name:'迁移说明与交互规范',layout:'vertical',width:1200,padding:56,fill:'#F4F6F9',children:[{type:'text',id:'docs-text',content:docText,fontFamily:'Noto Sans SC',fontSize:24,lineHeight:1.7,width:1088,textGrowth:'fixed-width',fill:'#25364B'}]},docs,null);
    report.counts.fontFallbacks=report.fonts.filter(f=>f.fallback).length;
    const checks={boards:report.counts.boards===payload.expected.boards,components:report.counts.components===payload.expected.components,runtimeComponents:report.counts.runtimeComponents===(payload.expected.runtimeComponents||0),texts:report.counts.texts===payload.expected.texts,characters:report.counts.characters===payload.expected.characters,images:report.counts.imageUses===payload.expected.imageUses,links:report.counts.prototypeConnections===payload.links.length,actualReactions:actualConnections===payload.links.length,sourceCoverage:report.coverage.every(v=>v.textExact),errors:report.errors.length===0};
    report.checks=checks;report.completed=Object.values(checks).every(Boolean);report.finishedAt=new Date().toISOString();
    if(payload.expected.imageUses&&Object.values(ix.nodes).some(n=>n.fill&&n.fill.transform))report.warnings.push('带 transform 的图片裁剪已使用原 affine 矩阵；需要实际 Figma 视觉抽查。');
    if(report.counts.fontFallbacks)report.warnings.push('存在字体替代，请检查 fonts 字段，特别是中文行高/换行。');
    putData(figma.root,'saas.migrationSummary',JSON.stringify({source:report.source,sourceHash:report.sourceHash,counts:report.counts,completed:report.completed,finishedAt:report.finishedAt}));
    await figma.setCurrentPageAsync(nativePage);figma.viewport.scrollAndZoomIntoView([boardNodes[31]]);
    report.phase='completed';delete report.activeNode;
    return report;
    } catch(error) { const detail=errorDetails(error);report.errors.push(detail.message);report.failure={message:detail.message,stack:detail.stack,phase:report.phase,activeNode:report.activeNode||null};report.finishedAt=new Date().toISOString();const wrapped=new Error(detail.message);wrapped.migrationReport=report;wrapped.originalStack=detail.stack;throw wrapped; }
  }
  async function exportVisuals(figma,report,emit){
    if(!report||!report.completed||report.boards.length!==54)throw new Error('请先完成54画板导入及验收，再导出视觉核验包。');
    const summary={source:'Figma node.exportAsync',format:'PNG',scale:.5,startedAt:new Date().toISOString(),expected:54,exported:0,totalBytes:0,files:[]};
    for(const board of report.boards.slice().sort((a,b)=>a.number-b.number)){
      const node=await figma.getNodeByIdAsync(board.id);
      if(!node||typeof node.exportAsync!=='function')throw new Error('画板缺失或无法导出：'+board.number+' / '+board.id);
      const data=await node.exportAsync({format:'PNG',constraint:{type:'SCALE',value:.5}});
      const name='boards/'+String(board.number).padStart(2,'0')+'-'+board.name.replace(/[<>:"/\\|?*\u0000-\u001f]/g,'_')+'.png';
      const info={number:board.number,nodeId:board.id,name,bytes:data.length};summary.files.push(info);summary.exported++;summary.totalBytes+=data.length;
      emit({type:'visual-file',name,bytes:data,number:board.number,index:summary.exported,total:54});
    }
    summary.completed=summary.exported===54;summary.finishedAt=new Date().toISOString();return summary;
  }
  return{run,decode,svgFor,solid,exportVisuals,errorDetails,getLastReport:()=>activeReport};
})();
if(typeof module!=='undefined')module.exports=Migration;
if(typeof figma!=='undefined'){
 figma.showUI(__html__,{width:520,height:600,themeColors:true});
 let busy=false,lastReport=null;
 figma.ui.onmessage=async message=>{
  if(message.type==='import'&&!busy){busy=true;try{lastReport=await Migration.run(figma,message.payload,text=>figma.ui.postMessage({type:'progress',text}));figma.ui.postMessage({type:'report',report:lastReport});figma.notify(lastReport.completed?'SaasNew 已导入，请下载验收报告并检查字体与场景裁剪。':'导入存在待检查项，请下载报告。');}catch(error){const detail=Migration.errorDetails(error);lastReport=error&&error.migrationReport||Migration.getLastReport()||lastReport;figma.ui.postMessage({type:'error',text:detail.message+'\n阶段：'+(lastReport&&lastReport.phase||'unknown')+'\n'+(error&&error.originalStack||detail.stack),report:lastReport});figma.notify('导入停止：'+detail.message,{error:true});}finally{busy=false;}}
  if(message.type==='export-visuals'&&!busy){busy=true;try{const summary=await Migration.exportVisuals(figma,lastReport,item=>figma.ui.postMessage(item));lastReport.visualExport=summary;figma.ui.postMessage({type:'visual-complete',report:lastReport,summary});}catch(error){figma.ui.postMessage({type:'visual-error',text:String(error.message||error)});figma.notify('视觉导出停止：'+String(error.message||error),{error:true});}finally{busy=false;}}
  if(message.type==='close')figma.closePlugin();
 };
}
