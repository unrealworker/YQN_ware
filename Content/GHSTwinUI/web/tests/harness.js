const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
// Exercise the actual page/bridge controller without a browser dependency. Geometry is
// verified separately in UE's embedded Chromium using the emitted report payloads.
function boot({reducedMotion=true,search=""}={}){
  const commands=[],elements={},listeners={},windowListeners={},handlers={},windowHandlers={};
  const decode=value=>value.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
  const dataKey=name=>name.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase());
  function listen(store,dispatch,name,handler){(store[name]||(store[name]=[])).push(handler);dispatch[name]=event=>{event=event||{};event.preventDefault=event.preventDefault||function(){this.defaultPrevented=true};event.stopPropagation=event.stopPropagation||function(){};event.stopImmediatePropagation=event.stopImmediatePropagation||function(){this.immediateStopped=true};for(const fn of store[name]){fn(event);if(event.immediateStopped)break;}return event;};}
  function node(tag='DIV',id=''){
    const attrs={},classes=new Set();let markup='';
    const el={id,tagName:tag.toUpperCase(),textContent:'',hidden:true,scrollTop:0,scrollWidth:480,clientWidth:480,className:'',style:{},dataset:{},children:[],isConnected:true,value:'',
      classList:{add(...names){names.forEach(n=>classes.add(n))},remove(...names){names.forEach(n=>classes.delete(n))},toggle(n,on){if(on===undefined)on=!classes.has(n);on?classes.add(n):classes.delete(n);},contains(n){return classes.has(n)}},
      setAttribute(k,v){attrs[k]=String(v);if(k.startsWith('data-'))this.dataset[dataKey(k)]=String(v);else if(k==='value')this.value=String(v);else if(k==='id')this.id=String(v);},getAttribute(k){return attrs[k]??null},removeAttribute(k){delete attrs[k];},
      contains(other){return other===this||this.children.some(c=>c.contains(other))||id==='page'&&!!(other&&other.insidePage)},
      matches(selector){return Array.from(selector.matchAll(/\[([^=\]]+)(?:="([^"]*)")?\]/g)).every(([,key,value])=>this.getAttribute(key)!==null&&(value===undefined||this.getAttribute(key)===value));},
      closest(selector){if(this.matches(selector))return this;return this.parentNode?this.parentNode.closest(selector):null;},
      querySelectorAll(selector){return this.children.flatMap(c=>[...(c.matches(selector)?[c]:[]),...c.querySelectorAll(selector)]);},querySelector(selector){return this.querySelectorAll(selector)[0]||null;},
      appendChild(child){child.parentNode=this;child.isConnected=true;this.children.push(child);return child;},remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(c=>c!==this);this.isConnected=false;if(document.activeElement===this){document.activeElement=document.body;if(listeners.focusout)listeners.focusout({target:this});}},
      focus(){const previous=document.activeElement;document.activeElement=this;if(previous!==this&&listeners.focusout)listeners.focusout({target:previous});if(listeners.focusin)listeners.focusin({target:this});},
      dispatchEvent(event){event.target=this;if(listeners[event.type])listeners[event.type](event);return !event.defaultPrevented;},
      getBoundingClientRect(){if(this.rect)return this.rect;const left=parseFloat(this.style.left)||0,top=parseFloat(this.style.top)||0,width=parseFloat(this.style.width)||168,height=Math.min(this.scrollHeight+(this.className==='filter-listbox'?2:0),parseFloat(this.style.maxHeight)||Infinity);return{left,top,right:left+width,bottom:top+height,width,height};},scrollIntoView(){this.scrolledIntoView=true;}
    };
    Object.defineProperties(el,{innerHTML:{configurable:true,get:()=>markup,set:value=>{markup=value;for(const child of el.children)child.isConnected=false;el.children=[];for(const match of value.matchAll(/<(button|div)\b([^>]*\bdata-dropdown-(?:options|index)="[^"]*"[^>]*)>/g)){const child=node(match[1]);for(const attr of match[2].matchAll(/([\w-]+)="([^"]*)"/g))child.setAttribute(attr[1],decode(attr[2]));el.appendChild(child);}}},offsetWidth:{get:()=>el.className==='filter-listbox'?168:480},scrollHeight:{get:()=>el.className==='filter-listbox'?el.children.length*34+10:1016}});
    return el;
  }
  const element=id=>elements[id]||(elements[id]=node('DIV',id));
  const document={getElementById:element,documentElement:{style:{},scrollWidth:480,clientWidth:480,clientHeight:1016},styleSheets:[],images:[],activeElement:null,querySelectorAll(){return[]},querySelector(){return null},createElement:tag=>node(tag),dispatchEvent(event){if(listeners[event.type])listeners[event.type](event);},addEventListener(name,handler){listen(handlers,listeners,name,handler)}};
  document.documentElement=node('HTML');document.documentElement.clientHeight=1016;
  document.body=node('BODY');document.body.appendChild(element('main'));element('main').appendChild(element('page'));
  let queue=[],now=0,timerId=0,motionListener;
  const motion={matches:reducedMotion,addEventListener(event,fn){motionListener=fn;}};
  function advance(ms){const until=now+ms;for(;;){queue.sort((a,b)=>a.at-b.at);const next=queue[0];if(!next||next.at>until)break;queue.shift();now=next.at;next.fn();}now=until;}
  const context={location:{search},document,innerWidth:480,innerHeight:1016,console,Event:class{constructor(type,options={}){this.type=type;Object.assign(this,options)}},addEventListener(name,handler){listen(windowHandlers,windowListeners,name,handler)},performance:{now:()=>now},getComputedStyle:()=>({opacity:'1'}),matchMedia:()=>motion,requestAnimationFrame:fn=>fn(),setTimeout:(fn,delay=0)=>{const id=++timerId;queue.push({id,at:now+delay,fn});return id;},clearTimeout:id=>{queue=queue.filter(t=>t.id!==id);},setInterval(){return 1},clearInterval(){},ue:{twin:{command:json=>commands.push(JSON.parse(json))}}};
  context.window=context;context.globalThis=context;vm.createContext(context);
  for(const file of ['viewport.js','model.js','business-data.js','dropdown.js','app.js']){const source=path.join(__dirname,'..',file);if(fs.existsSync(source))vm.runInContext(fs.readFileSync(source,'utf8'),context,{filename:file});}
  return{window:context,commands,elements,listeners,windowListeners,advance,flush(){while(queue.length)advance(Math.max(...queue.map(t=>t.at))-now);},reduceMotion(){motion.matches=true;if(motionListener)motionListener(motion);},click(dataset){listeners.click({target:{closest:()=>({dataset,insidePage:true})}});},html:()=>element('page').innerHTML};
}

module.exports={boot};
