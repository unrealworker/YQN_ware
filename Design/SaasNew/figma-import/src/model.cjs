/* Pure source normalization shared by builder, plugin and verification. */
const SaasModel = (() => {
  const types = new Set(['frame','text','rectangle','icon','ellipse','ref','path','svg']);
  const clone = value => JSON.parse(JSON.stringify(value));
  const walk = (node, visit) => { visit(node); (node.children || []).forEach(child => walk(child, visit)); };
  function index(document) {
    const nodes = {}, components = {}, definitionNodes = {};
    document.children.forEach(board => walk(board, node => {
      if (nodes[node.id]) throw new Error('Duplicate source ID: ' + node.id);
      if (!types.has(node.type)) throw new Error('Unsupported node type: ' + node.type + ' (' + node.id + ')');
      nodes[node.id] = node;
      if (node.reusable) components[node.id] = node;
    }));
    // Legacy masters are a separate registry, even when updated canvases reused
    // the old root ID. This prevents new DOM children invalidating old overrides.
    for (const definition of document.componentDefinitions || []) {
      if (!definition.id) throw new Error('Component definition has no ID');
      components[definition.id] = definition;
      walk(definition, node => {
        if (!types.has(node.type)) throw new Error('Unsupported definition node type: ' + node.type);
        if (definitionNodes[node.id] && JSON.stringify(definitionNodes[node.id]) !== JSON.stringify(node)) throw new Error('Conflicting component definition node: ' + node.id);
        definitionNodes[node.id] = node;
        if (node.reusable) components[node.id] = node;
      });
    }
    const runtimeComponents=document.runtimeComponentDefinitions||[],runtimeNodes=[];
    runtimeComponents.forEach(def=>walk(def,n=>{if(!types.has(n.type))throw new Error('Unsupported runtime component type: '+n.type);runtimeNodes.push(n);}));
    const allNodes=Object.values(nodes).concat(Object.values(definitionNodes),runtimeNodes);
    allNodes.forEach(node => {
      if (node.type !== 'ref') return;
      if (!components[node.ref]) throw new Error('Missing component: ' + node.ref);
      const targets=new Set();walk(expand(components[node.ref],components),n=>targets.add(n.originalId||n.id));
      for (const id of Object.keys(node.descendants||{})) {
        if(!targets.has(id)) throw new Error('Stale override target: '+node.id+' -> '+node.ref+' / '+id);
        for(const key of ['id','type','children','ref','descendants']) if(key in node.descendants[id])throw new Error('Unsupported structural replacement override: '+node.id+' / '+id+'.'+key);
      }
    });
    return { nodes, components, definitionNodes, runtimeComponents, runtimeNodes, allNodes };
  }
  function expand(node, components, inherited = {}, trail = []) {
    if (node.type === 'ref') {
      if (trail.includes(node.ref)) throw new Error('Circular component: ' + trail.concat(node.ref).join(' > '));
      const patch = Object.assign({}, node.descendants || {}, inherited);
      const result = expand(components[node.ref], components, patch, trail.concat(node.ref));
      Object.keys(node).forEach(key => {
        if (!['type','ref','descendants','children','reusable'].includes(key)) result[key] = clone(node[key]);
      });
      result.originalId = node.id;
      result.sourceComponent = node.ref;
      result.expandedReference = true;
      delete result.reusable;
      return result;
    }
    const result = Object.assign(clone(node), clone(inherited[node.id] || {}));
    result.originalId = node.id;
    if (node.children) result.children = node.children.map(child => expand(child, components, inherited, trail));
    return result;
  }
  function color(hex) {
    if (typeof hex !== 'string' || !/^#[a-f\d]{6}([a-f\d]{2})?$/i.test(hex)) throw new Error('Unsupported color: ' + JSON.stringify(hex));
    return {r:parseInt(hex.slice(1,3),16)/255,g:parseInt(hex.slice(3,5),16)/255,b:parseInt(hex.slice(5,7),16)/255,a:hex.length===9?parseInt(hex.slice(7,9),16)/255:1};
  }
  function audit(document) {
    const ix = index(document), expanded = document.children.map(b => expand(b, ix.components));
    const out = {boards:document.children.length,components:Object.keys(ix.components).length,runtimeComponents:ix.runtimeComponents.length,sourceNodes:Object.keys(ix.nodes).length,definitionNodes:Object.keys(ix.definitionNodes).length,sourceTypes:{},references:0,expandedBoardNodes:0,texts:0,characters:0,imageUses:0,icons:0,paths:0,textByBoard:{}};
    Object.values(ix.nodes).forEach(n => {out.sourceTypes[n.type]=(out.sourceTypes[n.type]||0)+1;if(n.type==='ref')out.references++;});
    expanded.forEach(b => {
      const texts=[];
      walk(b,n=> {out.expandedBoardNodes++;if(n.type==='text'){out.texts++;out.characters+=String(n.content||'').length;texts.push([n.originalId,String(n.content||'')]);}if(n.fill&&n.fill.type==='image')out.imageUses++;if(n.type==='icon')out.icons++;if(n.type==='path'||n.type==='svg')out.paths++;});
      out.textByBoard[b.id]=texts;
    });
    return out;
  }
  return {types,clone,walk,index,expand,color,audit};
})();
if (typeof module !== 'undefined') module.exports = SaasModel;
