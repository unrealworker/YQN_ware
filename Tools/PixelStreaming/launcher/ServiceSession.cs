using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
namespace Ghs.PixelStreaming
{
    public class InstanceStatus { public string id {get;set;} public int pid {get;set;} public string state {get;set;} public int targetFps {get;set;} public double? actualFps {get;set;} }
    public class ServiceStatus { public string state {get;set;} public string message {get;set;} public string mode {get;set;} public int viewerCount {get;set;} public int maxViewers {get;set;} public InstanceStatus[] instances {get;set;} public string[] urls {get;set;} public string[] logs {get;set;} }
    public sealed class ServiceSession : IDisposable
    {
        private readonly string root;
        private readonly object gate=new object();
        private readonly object stateGate=new object();
        private volatile string state="idle";
        private volatile bool cancelStart;
        private OwnedProcess process;
        private int controlPort;
        private string token;
        private string sessionDirectory;
        private class ControlInfo { public int controlPort {get;set;} public int pid {get;set;} public int httpPort {get;set;} public int streamerPort {get;set;} }
        public ServiceSession(string root) { this.root=Path.GetFullPath(root); }
        public string State { get { return state; } }
        public string LogPath {get;private set;}
        public void Start(LauncherConfig config)
        {
            lock(stateGate) { if(state!="idle") throw new InvalidOperationException("服务正在启动或运行，请先停止。"); cancelStart=false; state="starting"; }
            lock(gate)
            {
                try
                {
                    config.Validate(root,true);
                    string node=Path.Combine(root,"runtime","node.exe"); string server=Path.Combine(root,"server","server.js");
                    if(!File.Exists(node) || !File.Exists(server)) throw new FileNotFoundException("部署文件不完整：需要 runtime\\node.exe 和 server\\server.js。");
                    Directory.CreateDirectory(Path.Combine(root,"logs"));
                    string sessionId=DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N").Substring(0,8);
                    sessionDirectory=Path.Combine(root,"sessions",sessionId); Directory.CreateDirectory(sessionDirectory);
                    LogPath=Path.Combine(root,"logs","server-"+sessionId+".log");
                    byte[] random=new byte[32]; using(RandomNumberGenerator generator=RandomNumberGenerator.Create()) generator.GetBytes(random); token=Convert.ToBase64String(random);
                    string configPath=Path.Combine(sessionDirectory,"config.json"); string controlPath=Path.Combine(sessionDirectory,"control.json");
                    LauncherConfig runtime=new JavaScriptSerializer().Deserialize<LauncherConfig>(new JavaScriptSerializer().Serialize(config)); runtime.executablePath=config.ResolveExecutable(root); runtime.Save(configPath);
                    ThrowIfCanceled();
                    process=OwnedProcess.Start(node,new[]{server,"--config",configPath,"--control-file",controlPath},root,new Dictionary<string,string>{{"GHS_CONTROL_TOKEN",token}},LogPath);
                    Stopwatch wait=Stopwatch.StartNew();
                    while(wait.ElapsedMilliseconds<20000)
                    {
                        ThrowIfCanceled();
                        if(process.HasExited) throw new InvalidOperationException("服务启动后提前退出。请查看日志："+LogPath+Environment.NewLine+ReadLogTail());
                        if(File.Exists(controlPath))
                        {
                            ControlInfo control;
                            try { control=new JavaScriptSerializer().Deserialize<ControlInfo>(File.ReadAllText(controlPath,Encoding.UTF8)); }
                            catch(IOException) { Thread.Sleep(80); continue; }
                            catch(ArgumentException) { Thread.Sleep(80); continue; }
                            if(control==null || control.pid!=process.Id || control.controlPort<1 || control.controlPort>65535 || control.httpPort!=config.httpPort || control.streamerPort!=config.streamerPort) throw new InvalidOperationException("服务控制信息与本次启动不匹配，已停止本次进程。");
                            controlPort=control.controlPort;
                            Request("GET","/status"); ThrowIfCanceled(); state="running"; return;
                        }
                        Thread.Sleep(80);
                    }
                    throw new TimeoutException("服务启动超过 20 秒，已回收本次进程。日志："+LogPath);
                }
                catch { Cleanup(); state="idle"; throw; }
            }
        }
        private void ThrowIfCanceled() { if(cancelStart) throw new OperationCanceledException("启动已取消。"); }
        public void Stop()
        {
            lock(stateGate) { if(state=="idle") return; cancelStart=true; }
            lock(gate)
            {
                if(state=="idle") return;
                state="stopping";
                try { if(process!=null && !process.HasExited && controlPort>0) { try { Request("POST","/stop"); } catch(WebException) {} catch(IOException) {} process.WaitForExit(8000); } }
                finally { Cleanup(); state="idle"; }
            }
        }
        public ServiceStatus ReadStatus()
        {
            lock(gate)
            {
                if(state!="running" || process==null) throw new InvalidOperationException("服务尚未运行。");
                if(process.HasExited) { Cleanup(); state="idle"; throw new InvalidOperationException("串流服务已退出；已回收它拥有的实例。请查看日志后重新开启。"); }
                return new JavaScriptSerializer().Deserialize<ServiceStatus>(Request("GET","/status"));
            }
        }
        private string Request(string method,string route)
        {
            HttpWebRequest request=(HttpWebRequest)WebRequest.Create("http://127.0.0.1:"+controlPort+route);
            request.Method=method; request.Proxy=null; request.AllowAutoRedirect=false; request.Timeout=1800; request.ReadWriteTimeout=1800; request.KeepAlive=false; request.Headers[HttpRequestHeader.Authorization]="Bearer "+token;
            if(method=="POST") request.ContentLength=0;
            using(WebResponse response=request.GetResponse()) using(StreamReader reader=new StreamReader(response.GetResponseStream(),Encoding.UTF8)) return reader.ReadToEnd();
        }
        private string ReadLogTail()
        {
            try { using(FileStream stream=new FileStream(LogPath,FileMode.Open,FileAccess.Read,FileShare.ReadWrite)) using(StreamReader reader=new StreamReader(stream,Encoding.UTF8)) { string text=reader.ReadToEnd(); return text.Length>2500?text.Substring(text.Length-2500):text; } } catch(IOException) { return ""; }
        }
        private void Cleanup()
        {
            if(process!=null) { process.Dispose(); process=null; }
            controlPort=0; token=null;
            if(sessionDirectory!=null) { try { Directory.Delete(sessionDirectory,true); } catch(IOException) {} catch(UnauthorizedAccessException) {} sessionDirectory=null; }
        }
        public void Dispose() { Stop(); }
    }
}
