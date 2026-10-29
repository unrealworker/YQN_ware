(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.GhsPeerSession=api;})(typeof globalThis==='object'?globalThis:this,function(){
  'use strict';
  function socketUrl(href){const url=new URL('./',href);url.protocol=url.protocol==='https:'?'wss:':'ws:';url.search='';url.hash='';return url.href;}
  function bindSession(player,onEnd,timers=globalThis){
    let ended=false;
    const originalMessage=player.onWebSocketMessage.bind(player), originalConnect=player.connectedCallback.bind(player);
    function stop(title='已结束连接',message='已释放连接。切换方案前请等待场景实例回收。'){
      if(ended)return;ended=true;
      timers.clearTimeout(player.reconnect);
      if(player.ws){player.ws.onclose=null;player.ws.close();}
      player.pc?.close();player.pause();player.srcObject=null;
      if(player.audio){player.audio.pause();player.audio.srcObject=null;}
      onEnd(title,message);
    }
    // Leave the upstream SDK unchanged; terminal state guards its reconnect entry.
    player.connectedCallback=function(){if(!ended)return originalConnect();};
    player.onWebSocketMessage=function(raw){
      if(ended)return;
      let message;try{message=JSON.parse(raw);}catch{}
      if(message?.type==='deploymentStopped')return stop('会话已结束','服务已停止。服务恢复后可点击重新连接。');
      if(message?.type==='deploymentError')return stop('场景连接失败','请查看服务日志后重新连接。');
      return originalMessage(raw);
    };
    return {stop,get ended(){return ended;}};
  }
  return {socketUrl,bindSession};
});
