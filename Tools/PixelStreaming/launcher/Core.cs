using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Web.Script.Serialization;

namespace Ghs.PixelStreaming
{
    public class LauncherConfig
    {
        public string executablePath { get; set; }
        public int httpPort { get; set; }
        public int streamerPort { get; set; }
        public bool showWindow { get; set; }
        public int width { get; set; }
        public int height { get; set; }
        public string mode { get; set; }
        public int fps { get; set; }
        public int minBitrateMbps { get; set; }
        public int startBitrateMbps { get; set; }
        public int maxBitrateMbps { get; set; }
        public string qualityProfile { get; set; }
        public bool adaptiveResourceBudget { get; set; }
        public LauncherConfig() { executablePath="App/Windows/Test/Binaries/Win64/TestGame.exe"; httpPort=8080; streamerPort=8888; width=1920; height=1080; mode="shared"; fps=60; adaptiveResourceBudget=true; ApplyQualityProfile("clear"); }
        public void ApplyQualityProfile(string profile)
        {
            switch(profile) {
                case "balanced": minBitrateMbps=8; startBitrateMbps=20; maxBitrateMbps=35; break;
                case "clear": minBitrateMbps=12; startBitrateMbps=35; maxBitrateMbps=60; break;
                case "ultra": minBitrateMbps=20; startBitrateMbps=50; maxBitrateMbps=90; break;
                case "custom": break;
                default: throw new ArgumentException("请选择流畅、清晰优先或超清细节画质。");
            }
            qualityProfile=profile;
        }
        public string ResolveExecutable(string root) { return Path.GetFullPath(Path.Combine(root,executablePath ?? "")); }
        public void Validate(string root, bool checkPorts)
        {
            if(string.IsNullOrWhiteSpace(executablePath) || !File.Exists(ResolveExecutable(root)) || !string.Equals(Path.GetExtension(executablePath),".exe",StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("请选择存在的仓库程序（.exe）。");
            if(httpPort<1024 || httpPort>65535 || streamerPort<1024 || streamerPort>65535) throw new ArgumentException("端口范围必须为 1024–65535。");
            if(httpPort==streamerPort) throw new ArgumentException("网页端口与串流端口不能相同。");
            if(width<320 || width>7680 || height<320 || height>7680) throw new ArgumentException("分辨率范围：宽、高均为 320–7680。");
            if(mode!="shared" && mode!="independent") throw new ArgumentException("请选择共享或每人独立模式。");
            if(qualityProfile!="balanced" && qualityProfile!="clear" && qualityProfile!="ultra" && qualityProfile!="custom") throw new ArgumentException("画质配置无效，请重新选择画质。");
            if(fps<15 || fps>120 || minBitrateMbps<1 || minBitrateMbps>startBitrateMbps || startBitrateMbps>maxBitrateMbps || maxBitrateMbps>200) throw new ArgumentException("帧率必须为 15–120；码率须满足 1 ≤ 最小 ≤ 初始 ≤ 最大 ≤ 200 Mbps。");
            if(checkPorts) { PortProbe.EnsureAvailable(httpPort); PortProbe.EnsureAvailable(streamerPort); }
        }
        public void Save(string path)
        {
            string absolute=Path.GetFullPath(path); Directory.CreateDirectory(Path.GetDirectoryName(absolute));
            string temp=absolute+"."+Guid.NewGuid().ToString("N")+".tmp";
            try { File.WriteAllText(temp,new JavaScriptSerializer().Serialize(this),new UTF8Encoding(false)); if(File.Exists(absolute)) File.Replace(temp,absolute,null); else File.Move(temp,absolute); }
            finally { if(File.Exists(temp)) File.Delete(temp); }
        }
        public static LauncherConfig Load(string path)
        {
            if(!File.Exists(path)) return new LauncherConfig();
            string text=File.ReadAllText(path,Encoding.UTF8); JavaScriptSerializer json=new JavaScriptSerializer();
            LauncherConfig c=json.Deserialize<LauncherConfig>(text); if(c==null) throw new ArgumentException("配置文件为空。");
            Dictionary<string,object> fields=json.Deserialize<Dictionary<string,object>>(text);
            // Upgrade only the old shipped defaults. Existing custom budgets stay intact.
            if(!fields.ContainsKey("qualityProfile")) {
                if(c.minBitrateMbps==8 && c.startBitrateMbps==20 && c.maxBitrateMbps==35) c.ApplyQualityProfile("clear");
                else if(fields.ContainsKey("minBitrateMbps") || fields.ContainsKey("startBitrateMbps") || fields.ContainsKey("maxBitrateMbps")) c.qualityProfile="custom";
            }
            return c;
        }
    }
    public static class PortProbe
    {
        public static void EnsureAvailable(int port)
        {
            if(port<1 || port>65535) throw new ArgumentException("端口范围必须为 1–65535。");
            TcpListener listener=new TcpListener(IPAddress.Any,port); listener.ExclusiveAddressUse=true;
            try { listener.Start(); } catch(SocketException ex) { throw new InvalidOperationException("端口 "+port+" 已被占用或不可用。请更换端口，或关闭占用它的应用；启动器不会结束占用者。",ex); } finally { listener.Stop(); }
        }
    }
}
