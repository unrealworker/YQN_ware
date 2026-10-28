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
        public int maxViewers { get; set; }
        public string networkMode { get; set; }
        public string publicUrl { get; set; }
        public bool accessProtectionEnabled { get; set; }
        public string accessCode { get; set; }
        public string tlsCertPath { get; set; }
        public string tlsKeyPath { get; set; }
        public bool trustProxy { get; set; }
        public bool externalTlsTermination { get; set; }
        public string stunUrl { get; set; }
        public string turnUrl { get; set; }
        public string turnUsername { get; set; }
        public string turnPassword { get; set; }
        public LauncherConfig() { executablePath="App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe"; httpPort=8080; streamerPort=8888; width=1920; height=1080; mode="shared"; fps=0; maxViewers=10; networkMode="lan"; publicUrl=accessCode=tlsCertPath=tlsKeyPath=stunUrl=turnUrl=turnUsername=turnPassword=""; adaptiveResourceBudget=true; ApplyQualityProfile("balanced"); }
        public LauncherConfig Clone() { JavaScriptSerializer json=new JavaScriptSerializer(); return json.Deserialize<LauncherConfig>(json.Serialize(this)); }
        public string ResolveLocalFile(string root,string file) { return string.IsNullOrWhiteSpace(file)?"":Path.GetFullPath(Path.Combine(root,file)); }
        public void ValidateNetwork(string root)
        {
            if(maxViewers<1 || maxViewers>10) throw new ArgumentException("在线人数上限必须为 1–10。");
            if(networkMode!="lan" && networkMode!="public") throw new ArgumentException("请选择局域网或公网访问。");
            if(trustProxy && networkMode!="public") throw new ArgumentException("本机 HTTPS 反向代理仅适用于公网模式；局域网访问请关闭此选项。");
            if(externalTlsTermination && networkMode!="public") throw new ArgumentException("云负载均衡 HTTPS 仅适用于公网模式。");
            foreach(string value in new[]{publicUrl,accessCode,tlsCertPath,tlsKeyPath,stunUrl,turnUrl,turnUsername,turnPassword}) if(value==null || value.Length>4096 || value.IndexOfAny(new[]{'\r','\n','\0'})>=0) throw new ArgumentException("网络配置不能包含换行、空字符或超过 4096 个字符。");
            Uri url;
            if(!string.IsNullOrEmpty(publicUrl) && (!Uri.TryCreate(publicUrl,UriKind.Absolute,out url) || (url.Scheme!="https" && url.Scheme!="http") || !string.IsNullOrEmpty(url.UserInfo) || (url.AbsolutePath!="/" && url.AbsolutePath!="") || !string.IsNullOrEmpty(url.Query) || !string.IsNullOrEmpty(url.Fragment))) throw new ArgumentException("公网地址须为完整 HTTP / HTTPS 地址，不含路径、账号、查询或片段。");
            if(networkMode=="public" && string.IsNullOrWhiteSpace(publicUrl)) throw new ArgumentException("公网模式需要填写公网访问地址。");
            if(accessProtectionEnabled && (string.IsNullOrWhiteSpace(accessCode) || accessCode.Length<12)) throw new ArgumentException("开启安全访问仓库后，需要设置至少 12 位访问码。");
            if(string.IsNullOrWhiteSpace(tlsCertPath)!=string.IsNullOrWhiteSpace(tlsKeyPath)) throw new ArgumentException("HTTPS 证书与私钥需要成对选择。");
            if(trustProxy && !string.IsNullOrWhiteSpace(tlsCertPath)) throw new ArgumentException("本机反向代理与原生 HTTPS 证书不可同时启用。");
            if(externalTlsTermination && (trustProxy || !string.IsNullOrWhiteSpace(tlsCertPath))) throw new ArgumentException("云负载均衡 HTTPS 不能同时使用本机代理或本机证书。");
            foreach(string file in new[]{tlsCertPath,tlsKeyPath}) if(!string.IsNullOrWhiteSpace(file) && !File.Exists(ResolveLocalFile(root,file))) throw new ArgumentException("找不到 HTTPS 证书或私钥文件。");
            if(networkMode=="public" && publicUrl.StartsWith("https://",StringComparison.OrdinalIgnoreCase) && !trustProxy && !externalTlsTermination && string.IsNullOrWhiteSpace(tlsCertPath)) throw new ArgumentException("HTTPS 地址需要原生证书、本机反向代理或云负载均衡 HTTPS 接入方式。");
            if(networkMode=="public" && publicUrl.StartsWith("http://",StringComparison.OrdinalIgnoreCase) && (!string.IsNullOrWhiteSpace(tlsCertPath) || trustProxy || externalTlsTermination)) throw new ArgumentException("已启用 HTTPS 或代理时，请填写 HTTPS 公网地址。");
            ValidateIce(stunUrl,new[]{"stun:","stuns:"},"STUN"); ValidateIce(turnUrl,new[]{"turn:","turns:"},"TURN");
            if(!string.IsNullOrWhiteSpace(turnUrl) && (string.IsNullOrWhiteSpace(turnUsername) || string.IsNullOrWhiteSpace(turnPassword))) throw new ArgumentException("TURN 中继需要填写用户名和密码。");
            if(string.IsNullOrWhiteSpace(turnUrl) && (!string.IsNullOrEmpty(turnUsername) || !string.IsNullOrEmpty(turnPassword))) throw new ArgumentException("已填写 TURN 账号，请同时填写 TURN 服务地址。");
        }
        private static void ValidateIce(string value,string[] schemes,string label)
        {
            if(string.IsNullOrWhiteSpace(value)) return;
            bool valid=false; foreach(string scheme in schemes) if(value.StartsWith(scheme,StringComparison.Ordinal) && value.Length>scheme.Length) valid=true;
            if(!valid || !System.Text.RegularExpressions.Regex.IsMatch(value,@"^(?:stuns?|turns?):(?:\[[a-fA-F0-9:]+\]|[a-zA-Z0-9.-]+)(?::\d{1,5})?(?:\?transport=(?:udp|tcp))?$")) throw new ArgumentException(label+" 地址格式无效，请使用协议:主机:端口，可附加 ?transport=udp 或 tcp。");
            System.Text.RegularExpressions.Match port=System.Text.RegularExpressions.Regex.Match(value,@":(\d+)(?:\?|$)");
            if(port.Success && (int.Parse(port.Groups[1].Value)<1 || int.Parse(port.Groups[1].Value)>65535)) throw new ArgumentException(label+" 端口必须是 1–65535。");
        }
        public void ApplyQualityProfile(string profile)
        {
            switch(profile) {
                case "balanced": minBitrateMbps=1; startBitrateMbps=8; maxBitrateMbps=24; break;
                case "clear": minBitrateMbps=1; startBitrateMbps=10; maxBitrateMbps=35; break;
                case "ultra": minBitrateMbps=1; startBitrateMbps=16; maxBitrateMbps=50; break;
                case "custom": break;
                default: throw new ArgumentException("请选择流畅、清晰优先或超清细节画质。");
            }
            qualityProfile=profile;
        }
        public string ResolveExecutable(string root) { return Path.GetFullPath(Path.Combine(root,executablePath ?? "")); }
        public void Validate(string root, bool checkPorts)
        {
            if(string.IsNullOrWhiteSpace(executablePath) || !File.Exists(ResolveExecutable(root)) || !string.Equals(Path.GetExtension(executablePath),".exe",StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("请选择存在的仓库程序（.exe）。");
            if(httpPort<1 || httpPort>65535 || streamerPort<1 || streamerPort>65535) throw new ArgumentException("端口范围必须为 1–65535。");
            ValidateNetwork(root);
            if(httpPort==streamerPort) throw new ArgumentException("网页端口与串流端口不能相同。");
            if(width<320 || width>7680 || height<320 || height>7680) throw new ArgumentException("分辨率范围：宽、高均为 320–7680。");
            if(mode!="shared" && mode!="independent") throw new ArgumentException("请选择共享或每人独立模式。");
            if(qualityProfile!="balanced" && qualityProfile!="clear" && qualityProfile!="ultra" && qualityProfile!="custom") throw new ArgumentException("画质配置无效，请重新选择画质。");
            if((fps!=0 && (fps<15 || fps>120)) || minBitrateMbps<1 || minBitrateMbps>startBitrateMbps || startBitrateMbps>maxBitrateMbps || maxBitrateMbps>200) throw new ArgumentException("帧率须为 0（无固定上限）或 15–120；码率须满足 1 ≤ 最小 ≤ 初始 ≤ 最大 ≤ 200 Mbps。");
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
            Dictionary<string,object> fields=json.Deserialize<Dictionary<string,object>>(text);
            if(fields==null) throw new ArgumentException("配置文件为空。");
            if(fields.ContainsKey("accessProtectionEnabled") && !(fields["accessProtectionEnabled"] is bool)) throw new ArgumentException("安全访问仓库配置 accessProtectionEnabled 必须为 true 或 false 布尔值。");
            LauncherConfig c=json.Deserialize<LauncherConfig>(text); if(c==null) throw new ArgumentException("配置文件为空。");
            // An explicit budget always wins, including the old 8/20/35 defaults.
            bool explicitBudget=fields.ContainsKey("minBitrateMbps") || fields.ContainsKey("startBitrateMbps") || fields.ContainsKey("maxBitrateMbps");
            if(!fields.ContainsKey("qualityProfile") && explicitBudget) c.qualityProfile="custom";
            else if(!explicitBudget && (c.qualityProfile=="balanced" || c.qualityProfile=="clear" || c.qualityProfile=="ultra")) c.ApplyQualityProfile(c.qualityProfile);
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
