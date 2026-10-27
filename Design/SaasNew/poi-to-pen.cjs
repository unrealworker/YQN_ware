// Rebuild editable scene POIs from the live native HUD's measured screen geometry.
function convertPOIs(report,prefix,sceneWidth,sceneHeight){
 const children=[],actions=[];
 const rect=(id,x,y,width,height,fill,extra={})=>({type:'rectangle',id:prefix+'-'+id,x,y,width,height,fill,...extra});
 const text=(id,content,x,y,size,fill)=>({type:'text',id:prefix+'-'+id,name:content,content,x,y,fontFamily:'Microsoft YaHei',fontSize:size,fill});
 const icon=(id,name,x,y,fill,size=18)=>({type:'icon',id:prefix+'-'+id,name,icon:name,library:'lucide',x,y,width:size,height:size,fill});
 for(const [i,l]of (report.labels||[]).entries()){
   const x=l.x,y=l.y-64,w=l.width,h=l.height,p=prefix+'-'+i,accent='#'+(l.accent||'356BFA').slice(0,6),fill='#'+(l.fill||'FFFFFF').slice(0,6);
   if(x+w<0||x>sceneWidth||y+h<0||y>sceneHeight)continue;
   const warehouse=l.id==='WAREHOUSE:GHS';
   const ax=l.anchorX??x+w/2,ay=(l.anchorY??l.y+h+48)-64;
   const ex=Math.max(x,Math.min(ax,x+w)),ey=Math.max(y,Math.min(ay,y+h));
   children.push({type:'svg',id:p+'-stem',name:'实际锚点引线',x:0,y:0,width:sceneWidth,height:sceneHeight,svg:`<svg xmlns="http://www.w3.org/2000/svg" width="${sceneWidth}" height="${sceneHeight}"><path d="M${ex} ${ey}L${ax} ${ay}" fill="none" stroke="${accent}" stroke-opacity="0.6" stroke-width="1.25"/></svg>`});
   children.push({type:'ellipse',id:p+'-anchor',name:'实际定位锚点',x:ax-15,y:ay-7,width:30,height:14,fill:warehouse?'#FFFFFFDD':accent+'20',stroke:accent+'80',strokeWidth:1});
   children.push({type:'ellipse',id:p+'-dot',name:'锚点中心',x:ax-3,y:ay-3,width:6,height:6,fill:accent});
   const card={type:'frame',id:p+'-card',name:l.title||'GHS · 主仓库',x,y,width:w,height:h,fill,cornerRadius:warehouse?10:6,stroke:l.following?'#36B5C6':l.selected?'#356BFA':'#DFE7F2',strokeWidth:l.following?2.5:1,layout:'none',children:[],metadata:{source:'GetPOIReport',deviceId:l.id,selected:!!l.selected,following:!!l.following,capture:report.name}};
   if(warehouse){
     card.children=[rect(i+'-identity',12,14,28,28,'#EDF3FF',{cornerRadius:7}),icon(i+'-icon','warehouse',15,17,'#356BFA',22),text(i+'-title','GHS · 主仓库',52,7,18.67,'#25364B'),text(i+'-status','点击查看',52,30,16,'#536478'),icon(i+'-chevron','chevron-right',199,18,'#356BFA',20)];
   }else{
     const iconName={forklift:'forklift',truck:'truck',agv:'bot',stacker:'forklift',charger:'battery-charging',warehouse:'warehouse',rack:'boxes',region:'warehouse'}[l.icon]||'box';
     card.children=[icon(i+'-icon',iconName,12,(h-18)/2,l.selected?'#FFFFFF':accent),text(i+'-title',l.title||l.id,40,(h-22)/2,18.67,l.selected?'#FFFFFF':'#25364B')];
     if(l.state||l.statusText){const bw=l.badgeWidth||80,bx=w-bw-12;card.children.push(rect(i+'-badge',bx,(h-24)/2,bw,24,'#F0F4F9',{cornerRadius:2}),text(i+'-status',l.state||l.statusText,bx+8,(h-22)/2,16,accent));}
   }
   children.push(card);actions.push({id:card.id,deviceId:l.id,warehouse});
 }
 return {root:{type:'frame',id:prefix+'-root',name:'最新运行 POI · '+(report.name||''),x:0,y:0,width:sceneWidth,height:sceneHeight,layout:'none',clip:true,children},actions};
}
module.exports={convertPOIs};
