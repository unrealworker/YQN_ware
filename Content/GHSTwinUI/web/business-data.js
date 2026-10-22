(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.TwinBusinessData=factory();
})(typeof window==='undefined'?globalThis:window,function(){
'use strict';
// A dated extract of the user's answered questionnaire, not a production API.
// Scene IDs, coordinates and operational telemetry are deliberately separate.
const snapshot={
  schemaVersion:1,
  warehouse:{id:108,code:'GHS_CA_US',name:'YQN Los Angeles Warehouse #8',timeZone:'America/Los_Angeles',scope:'GHS 系统仓',physicalScopeConfirmed:false},
  source:{
    mode:'verified-extract',label:'表格核验数据',live:false,verifiedDate:'2026-10-22',
    workbook:'库存与设备数据对接问题表.xlsx',
    workbookSha256:'68BDE9E6807352C2700FF7B8062C2FCC6A940FF6E8A2B5B6A0660875636AFE6E',
    queryTime:'2026-10-22 22:27 UTC+08:00',
    inventoryEtlTime:'2026-10-22 22:01:21 UTC+08:00',
    forkliftEtlTime:'2026-10-08 10:45:34 UTC+08:00',
    forkliftSourceUpdatedTime:'2026-10-08 06:51:21 UTC+08:00',
    businessSnapshotTime:null,
    cells:{warehouse:'库存对接!E7',inventorySummary:['库存对接!E10','库存对接!E12'],inventorySamples:'库存对接!E17',forkliftSummary:'设备对接!E7,E9,E17',forkliftSamples:'设备对接!E17',forkliftTimes:'设备对接!E10',delivery:'接口与更新!E8,E10,E13'}
  },
  inventory:{
    sourceTable:'dwd_wms_inventory_item_wide',
    onHand:337783,available:336006,frozen:55,allocated:1722,pendingMove:0,
    owners:156,skus:14373,records:76752,referencedLocations:31497,
    unit:null,capacity:null,occupied:null,empty:null,locked:null,
    detailsComplete:false,sceneMappingConfirmed:false,
    regions:[
      {code:'GHS-R',name:'货架',onHand:null},
      {code:'GHS-SR',name:null,onHand:null},
      {code:'GHS-T',name:null,onHand:null},
      {code:'GHS-MOVE',name:'转仓',onHand:null},
      {code:'GHS-HL',name:'恒林',onHand:null},
      {code:'GHS-WALL01',name:'靠墙货架',onHand:null},
      {code:'GHS-G',name:'地堆',onHand:null},
      {code:'GHS-DG',name:'地柜',onHand:null},
      {code:'GHS-DOCK01',name:'临时存放',onHand:null},
      {code:'GHS-TEMP',name:'退货暂存',onHand:null}
    ],
    samples:[
      {id:'8551268',onHand:10,available:10,frozen:null,allocated:null,pendingMove:null,locationId:null,sku:null,ownerId:null,batch:null},
      {id:'7111566',onHand:0,available:0,frozen:null,allocated:null,pendingMove:null,locationId:null,sku:null,ownerId:null,batch:null},
      {id:'8556512',onHand:4,available:3,frozen:null,allocated:1,pendingMove:null,locationId:null,sku:null,ownerId:null,batch:null},
      {id:'8703069',onHand:1,available:0,frozen:1,allocated:null,pendingMove:null,locationId:null,sku:null,ownerId:null,batch:null},
      {id:'10274458',onHand:-1,available:-1,frozen:null,allocated:null,pendingMove:null,locationId:null,sku:null,ownerId:null,batch:null}
    ]
  },
  forklifts:{
    sourceTable:'dim_forklifts',total:82,normal:62,disabled:20,repair:0,
    online:null,telemetryAvailable:false,sceneMappingConfirmed:false,detailsComplete:false,
    types:[
      {name:'电动托盘车',count:8,normal:8,disabled:0,repair:0},
      {name:'ORDER PICKER',count:20,normal:19,disabled:1,repair:0},
      {name:'REACH',count:18,normal:16,disabled:2,repair:0},
      {name:'Rider',count:9,normal:4,disabled:5,repair:0},
      {name:'坐式叉车',count:27,normal:15,disabled:12,repair:0}
    ],
    samples:[
      {id:'2574',code:'SITDOWN-GHS-L-OUT-S1'},
      {id:'2575',code:'SITDOWN-GHS-L-OUT-S2'},
      {id:'2576',code:'SITDOWN-GHS-L-IN-S3'},
      {id:'2577',code:'SITDOWN-GHS-L-IN-S4'},
      {id:'2578',code:'SITDOWN-GHS-L-IN-S5'}
    ].map(row=>Object.assign(row,{type:'坐式叉车',status:1,statusName:'正常',sceneId:null,online:null,battery:null,speed:null,load:null,location:null,task:null}))
  }
};
function availableQuantity(row){
  // The workbook's null-as-zero rule applies to deductions in this formula only.
  // A missing observed on-hand quantity remains unknown.
  if(!row||typeof row.onHand!=='number'||!Number.isFinite(row.onHand))return null;
  let value=row.onHand;
  for(const key of ['frozen','allocated','pendingMove']){
    const amount=row[key];
    if(amount==null)continue;
    if(typeof amount!=='number'||!Number.isFinite(amount))return null;
    value-=amount;
  }
  return value;
}
function locationStatus(code){return ({0:'禁用',1:'启用',2:'占用'})[code]||'待确认';}
function managementStatus(code){return ({1:'正常',2:'维修中',3:'禁用'})[code]||'待确认';}
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
return freeze({snapshot,availableQuantity,locationStatus,managementStatus});
});
