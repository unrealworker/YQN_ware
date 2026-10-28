using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace Ghs.PixelStreaming
{
    internal static class SelfTests
    {
        private static readonly List<string> Results = new List<string>();
        private static int failures;
        private static string scratch;
        private static string Executable { get { return Assembly.GetExecutingAssembly().Location; } }
        private static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
        private static void Throws<T>(Action action) where T : Exception { try { action(); } catch(T) { return; } throw new Exception("Expected " + typeof(T).Name); }
        private static void Test(string name, Action action) { try { action(); Results.Add("PASS " + name); } catch(Exception ex) { failures++; Results.Add("FAIL " + name + ": " + ex.Message); } }
        private static LauncherConfig Config() { LauncherConfig c = new LauncherConfig(); c.executablePath=Executable; return c; }
        private static void WaitForFile(string path) { Stopwatch t=Stopwatch.StartNew(); while(!File.Exists(path) && t.ElapsedMilliseconds<4000) Thread.Sleep(40); Assert(File.Exists(path), "Worker did not write " + path); }
        private static bool Alive(int id) { try { using(Process p=Process.GetProcessById(id)) return !p.HasExited; } catch(ArgumentException) { return false; } }
        private static int FreePort() { TcpListener listener=new TcpListener(IPAddress.Any,0); listener.Start(); int p=((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop(); return p; }
        private static string FixtureRoot() { string root=Path.Combine(scratch,Guid.NewGuid().ToString("N")); Directory.CreateDirectory(Path.Combine(root,"runtime")); Directory.CreateDirectory(Path.Combine(root,"server")); File.Copy(Executable,Path.Combine(root,"runtime","node.exe")); File.WriteAllText(Path.Combine(root,"server","server.js"),""); return root; }
        private static LauncherConfig FixtureConfig() { LauncherConfig c=Config(); c.httpPort=FreePort(); do { c.streamerPort=FreePort(); } while(c.httpPort==c.streamerPort); return c; }
        private static Dictionary<string,object> ConfigValues(LauncherConfig c) { JavaScriptSerializer json=new JavaScriptSerializer(); return json.Deserialize<Dictionary<string,object>>(json.Serialize(c)); }
        private static void EventuallyGone(int id) { Stopwatch t=Stopwatch.StartNew(); while(Alive(id) && t.ElapsedMilliseconds<4000) Thread.Sleep(40); Assert(!Alive(id),"Owned PID survived job close: "+id); }
        private static void AssertRoundedButtonBackgrounds()
        {
            BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
            MethodInfo paint=typeof(RoundedButton).GetMethod("OnPaint",flags);
            MethodInfo background=typeof(Control).GetMethod("OnPaintBackground",flags);
            MethodInfo style=typeof(Control).GetMethod("GetStyle",flags);
            foreach(int dpi in new[]{96,144,192})
            foreach(System.Drawing.Color parentColor in new[]{System.Drawing.Color.White,LauncherTheme.Canvas})
            using(Panel parent=new Panel {BackColor=parentColor})
            using(RoundedButton button=new RoundedButton {Text="按钮",Size=new System.Drawing.Size(180*dpi/96,44*dpi/96)})
            {
                parent.Controls.Add(button);
                for(int state=0;state<6;state++)
                {
                    button.Primary=state==1 || state==4; button.Selected=state==2 || state==5; button.Enabled=state<3;
                    using(System.Drawing.Bitmap bitmap=new System.Drawing.Bitmap(button.Width,button.Height))
                    {
                        bitmap.SetResolution(dpi,dpi);
                        using(System.Drawing.Graphics graphics=System.Drawing.Graphics.FromImage(bitmap))
                        using(PaintEventArgs args=new PaintEventArgs(graphics,button.ClientRectangle))
                        {
                            graphics.Clear(System.Drawing.Color.Black);
                            // WM_PAINT skips background painting for opaque controls. DrawToBitmap masks this defect.
                            if(!(bool)style.Invoke(button,new object[]{ControlStyles.Opaque})) background.Invoke(button,new object[]{args});
                            paint.Invoke(button,new object[]{args});
                        }
                        foreach(System.Drawing.Point corner in new[]{new System.Drawing.Point(0,0),new System.Drawing.Point(button.Width-1,0),new System.Drawing.Point(0,button.Height-1),new System.Drawing.Point(button.Width-1,button.Height-1)})
                            Assert(bitmap.GetPixel(corner.X,corner.Y).ToArgb()==parentColor.ToArgb(),"Unpainted rounded button corner at "+dpi+" DPI, state "+state+", parent "+parentColor);
                    }
                }
            }
        }
        public static int Run(string report)
        {
            failures=0; Results.Clear(); scratch=Path.Combine(Path.GetTempPath(),"GHS launcher 测试 "+Guid.NewGuid().ToString("N")); Directory.CreateDirectory(scratch);
            Test("GUI rounded button corners match their parent in enabled selected and disabled states at 100 150 and 200 percent DPI",AssertRoundedButtonBackgrounds);
            Test("valid existing executable accepted",delegate { Config().Validate(scratch,false); });
            Test("cloud HTTPS termination accepts private HTTP backhaul and survives configuration save and clone",delegate {
                JavaScriptSerializer serializer=new JavaScriptSerializer(); Dictionary<string,object> values=ConfigValues(Config());
                values["networkMode"]="public"; values["publicUrl"]="https://warehouse-sim.iyunquna.com"; values["accessCode"]="fixture-only-cloud-code"; values["externalTlsTermination"]=true;
                LauncherConfig cloud=serializer.Deserialize<LauncherConfig>(serializer.Serialize(values)); cloud.ValidateNetwork(scratch);
                string file=Path.Combine(scratch,"cloud.json"); cloud.Save(file); LauncherConfig restored=LauncherConfig.Load(file).Clone(); Dictionary<string,object> actual=ConfigValues(restored);
                Assert(actual.ContainsKey("externalTlsTermination") && (bool)actual["externalTlsTermination"],"Cloud HTTPS mode was dropped during save or clone");
                Assert(!restored.trustProxy && restored.tlsCertPath=="" && restored.publicUrl=="https://warehouse-sim.iyunquna.com","Cloud mode changed local proxy or public origin");
            });
            Test("public defaults, bounds and local configuration roundtrip",delegate { LauncherConfig c=Config(); Assert(c.maxViewers==10,"Default capacity is not ten"); c.networkMode="public"; c.publicUrl="http://198.51.100.20:8080"; c.accessCode="test-only-code-12345"; c.turnUrl="turn:relay.example.com:3478?transport=udp"; c.turnUsername="test-user"; c.turnPassword="test-password"; c.Validate(scratch,false); string file=Path.Combine(scratch,"public.json"); c.Save(file); LauncherConfig restored=LauncherConfig.Load(file); Assert(restored.publicUrl==c.publicUrl && restored.accessCode==c.accessCode && restored.turnPassword==c.turnPassword && restored.maxViewers==10,"Public fields lost"); c.maxViewers=11; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); c.maxViewers=10; c.accessCode="short"; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); });
            Test("public HTTPS, proxy and TURN requirements reject invalid combinations",delegate { LauncherConfig c=Config(); c.networkMode="public"; c.publicUrl="https://warehouse.example.com"; c.accessCode="test-only-code-12345"; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); c.trustProxy=true; c.Validate(scratch,false); c.publicUrl="https://warehouse.example.com/path"; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); c.publicUrl="https://warehouse.example.com"; c.turnUrl="turn:relay.example.com:3478"; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); c.turnUsername="u"; c.turnPassword="p"; c.Validate(scratch,false); c.stunUrl="https://wrong.example.com"; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); });
            Test("switching either public proxy to LAN clears it and does not silently restore it",delegate {
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                foreach(bool cloud in new[]{false,true}) {
                    LauncherConfig c=Config(); c.networkMode="public"; c.publicUrl="https://warehouse.example.com"; c.accessCode="test-only-code-12345"; c.trustProxy=!cloud; c.externalTlsTermination=cloud;
                    using(PublicSettingsForm form=new PublicSettingsForm(scratch,c)) {
                        ComboBox network=(ComboBox)typeof(PublicSettingsForm).GetField("network",flags).GetValue(form),tls=(ComboBox)typeof(PublicSettingsForm).GetField("tlsMode",flags).GetValue(form);
                        Assert(form.Read().trustProxy==!cloud && form.Read().externalTlsTermination==cloud,"Public mode was lost");
                        network.SelectedIndex=0; Assert(!form.Read().trustProxy && !form.Read().externalTlsTermination,"LAN retained a public proxy"); form.Read().ValidateNetwork(scratch);
                        tls.SelectedIndex=cloud?3:2; Assert(!form.Read().trustProxy && !form.Read().externalTlsTermination,"Public proxy could be enabled in LAN");
                        network.SelectedIndex=1; Assert(!form.Read().trustProxy && !form.Read().externalTlsTermination,"Public mode silently restored a stale proxy");
                    }
                    c.networkMode="lan"; Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);});
                }
            });
            Test("cloud HTTPS rejects HTTP origin local proxy certificates and short access code",delegate {
                LauncherConfig c=Config(); c.networkMode="public"; c.publicUrl="https://warehouse-sim.iyunquna.com"; c.accessCode="fixture-only-cloud-code"; c.externalTlsTermination=true; c.ValidateNetwork(scratch);
                c.publicUrl="http://warehouse-sim.iyunquna.com"; Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);}); c.publicUrl="https://warehouse-sim.iyunquna.com";
                c.trustProxy=true; Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);}); c.trustProxy=false;
                c.tlsCertPath=c.tlsKeyPath=Path.Combine(scratch,"fake.pem"); File.WriteAllText(c.tlsCertPath,"test-only"); Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);}); c.tlsCertPath=c.tlsKeyPath="";
                c.accessCode="short"; Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);});
                Assert(!Config().externalTlsTermination,"Old LAN configuration unexpectedly opted into external TLS");
            });
            Test("TLS selector changes modes without carrying inactive certificates or proxy flags",delegate {
                LauncherConfig c=Config(); c.networkMode="public"; c.publicUrl="https://warehouse-sim.iyunquna.com"; c.accessCode="fixture-only-cloud-code"; c.tlsCertPath="fixture.crt"; c.tlsKeyPath="fixture.key";
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                using(PublicSettingsForm form=new PublicSettingsForm(scratch,c)) {
                    ComboBox tls=(ComboBox)typeof(PublicSettingsForm).GetField("tlsMode",flags).GetValue(form); Assert(form.Read().tlsCertPath=="fixture.crt","Native certificate lost on open");
                    tls.SelectedIndex=3; LauncherConfig cloud=form.Read(); cloud.ValidateNetwork(scratch); Assert(cloud.externalTlsTermination && !cloud.trustProxy && cloud.tlsCertPath=="" && cloud.tlsKeyPath=="","Cloud retained local TLS settings");
                    Assert(!((TextBox)typeof(PublicSettingsForm).GetField("cert",flags).GetValue(form)).Enabled,"Cloud certificate field still editable");
                    tls.SelectedIndex=2; LauncherConfig proxy=form.Read(); proxy.ValidateNetwork(scratch); Assert(proxy.trustProxy && !proxy.externalTlsTermination && proxy.tlsCertPath=="","Local proxy inherited cloud TLS");
                    tls.SelectedIndex=1; LauncherConfig native=form.Read(); Assert(!native.trustProxy && !native.externalTlsTermination && native.tlsCertPath=="fixture.crt" && native.tlsKeyPath=="fixture.key","Native fields were not restored within the dialog");
                }
            });
            Test("choosing native HTTPS without certificate files cannot save as plain HTTP",delegate {
                LauncherConfig c=Config(); c.networkMode="public"; c.publicUrl="http://warehouse.example.com:8080"; c.accessCode="fixture-only-native-code";
                using(PublicSettingsForm form=new PublicSettingsForm(scratch,c)) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; ComboBox tls=(ComboBox)typeof(PublicSettingsForm).GetField("tlsMode",flags).GetValue(form); tls.SelectedIndex=1; Throws<ArgumentException>(delegate {form.Read().ValidateNetwork(scratch);}); }
            });
            Test("cloud mode reaches runtime config and prevents automatic broad firewall changes",delegate {
                string root=FixtureRoot(); BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                using(MainForm form=new MainForm()) {
                    LauncherConfig cloud=FixtureConfig(); cloud.networkMode="public"; cloud.publicUrl="https://warehouse-sim.iyunquna.com"; cloud.accessCode="fixture-only-cloud-code"; cloud.externalTlsTermination=true;
                    typeof(MainForm).GetField("baseline",flags).SetValue(form,cloud); typeof(MainForm).GetMethod("UpdateNetworkSummary",flags).Invoke(form,null);
                    Assert(!((Button)typeof(MainForm).GetField("firewall",flags).GetValue(form)).Enabled,"Cloud mode allowed automatic public firewall rules");
                    LauncherConfig fromUi=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); fromUi.executablePath=Executable; fromUi.httpPort=cloud.httpPort; fromUi.streamerPort=cloud.streamerPort;
                    using(ServiceSession session=new ServiceSession(root)) { session.Start(fromUi); string[] files=Directory.GetFiles(Path.Combine(root,"sessions"),"config.json",SearchOption.AllDirectories); LauncherConfig runtime=LauncherConfig.Load(files[0]); Assert(runtime.externalTlsTermination && !runtime.trustProxy && runtime.tlsCertPath=="" && runtime.publicUrl=="https://warehouse-sim.iyunquna.com","Cloud mode lost before child process launch"); session.Stop(); }
                    cloud.externalTlsTermination=false; typeof(MainForm).GetMethod("UpdateNetworkSummary",flags).Invoke(form,null); Assert(((Button)typeof(MainForm).GetField("firewall",flags).GetValue(form)).Enabled,"Leaving cloud mode did not restore firewall action");
                }
            });
            Test("TURN strict URI ports and missing URL match backend validation",delegate { LauncherConfig c=Config(); c.turnUsername="u"; c.turnPassword="p"; foreach(string invalid in new[]{"","turn:","turn://relay.example.com","turn:relay.example.com:0","turn:relay.example.com:65536","turn:relay.example.com/path","turn:relay.example.com?transport=sctp","turn:user@relay.example.com","stun:relay.example.com:3478"}) { c.turnUrl=invalid; Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);}); } foreach(string valid in new[]{"turn:relay.example.com","turn:relay.example.com:3478?transport=udp","turns:[2001:db8::1]:5349?transport=tcp"}) {c.turnUrl=valid; c.ValidateNetwork(scratch);} c.stunUrl="stun:host:65536"; Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);}); c.stunUrl="stuns:stun.example.com:5349"; c.ValidateNetwork(scratch); });
            Test("degraded status shows an amber warning and backend explanation",delegate { using(MainForm form=new MainForm()) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; typeof(MainForm).GetMethod("ApplyStatus",flags).Invoke(form,new object[]{new ServiceStatus {state="degraded",message="实例启动失败，请检查显卡。",viewerCount=1,maxViewers=10,instances=new[]{new InstanceStatus {id="viewer-1",state="failed"}},viewers=new ViewerStatus[0]}}); Label status=(Label)typeof(MainForm).GetField("status",flags).GetValue(form),message=(Label)typeof(MainForm).GetField("healthMessage",flags).GetValue(form); Assert(status.Text=="部分实例异常" && status.ForeColor==LauncherTheme.Amber,"Degraded service presented as healthy"); Assert(message.Text.Contains("实例启动失败"),"Backend explanation was hidden"); ListView instances=(ListView)typeof(MainForm).GetField("instances",flags).GetValue(form); Assert(instances.Items[0].SubItems[1].Text=="异常","Failed instance state remained untranslated"); } });
            Test("relative certificate paths resolve before temporary runtime configuration",delegate { string root=FixtureRoot(); File.WriteAllText(Path.Combine(root,"cert.pem"),"test-certificate"); File.WriteAllText(Path.Combine(root,"key.pem"),"test-key"); LauncherConfig c=FixtureConfig(); c.networkMode="public"; c.publicUrl="https://warehouse.example.com"; c.accessCode="test-only-code-12345"; c.tlsCertPath="cert.pem"; c.tlsKeyPath="key.pem"; using(ServiceSession session=new ServiceSession(root)) {session.Start(c); string[] configs=Directory.GetFiles(Path.Combine(root,"sessions"),"config.json",SearchOption.AllDirectories); LauncherConfig runtime=LauncherConfig.Load(configs[0]); Assert(runtime.tlsCertPath==Path.Combine(root,"cert.pem") && runtime.tlsKeyPath==Path.Combine(root,"key.pem"),"Relative certificate location changed"); session.Stop();} });
            Test("authenticated disconnect posts only chosen player and leaves service running",delegate { string root=FixtureRoot(); using(ServiceSession session=new ServiceSession(root)) { session.Start(FixtureConfig()); session.DisconnectViewer("7"); var request=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(root,"disconnect.json"))); Assert(request.Count==1 && (string)request["playerId"]=="7","Disconnect target changed"); Assert(session.ReadStatus().state=="running","Disconnect stopped the service"); Throws<ArgumentException>(delegate {session.DisconnectViewer("../stop");}); session.Stop(); Throws<InvalidOperationException>(delegate {session.DisconnectViewer("7");}); } });
            Test("viewer polling preserves selected ID and removes departed rows",delegate { using(MainForm form=new MainForm()) { form.CreateControl(); BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; ListView list=(ListView)typeof(MainForm).GetField("connections",flags).GetValue(form); list.CreateControl(); MethodInfo apply=typeof(MainForm).GetMethod("ApplyViewers",flags); ViewerStatus one=new ViewerStatus {playerId="1",displayName="Alice",address="198.51.100.1",state="connected",connectedAt=DateTimeOffset.UtcNow.AddMinutes(-2).ToString("o")}, two=new ViewerStatus {playerId="2",displayName="Bob",address="198.51.100.2",state="connected",connectedAt=DateTimeOffset.UtcNow.ToString("o")}; apply.Invoke(form,new object[]{new[]{one,two}}); list.Items["2"].Selected=true; apply.Invoke(form,new object[]{new[]{two,one}}); Assert(list.Items.Count==2 && list.Items["2"].Selected,"Polling changed the selected user"); apply.Invoke(form,new object[]{new[]{one}}); Assert(list.Items.Count==1 && !list.Items.ContainsKey("2"),"Departed user retained"); } });
            Test("missing executable rejected",delegate { LauncherConfig c=Config(); c.executablePath=Path.Combine(scratch,"missing.exe"); Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("invalid and duplicate ports rejected",delegate { LauncherConfig c=Config(); c.httpPort=0; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); c.httpPort=8888; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("invalid resolution and mode rejected",delegate { LauncherConfig c=Config(); c.width=0; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); c.width=1920; c.mode="bogus"; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("backend port range enforced before starting a child",delegate { LauncherConfig c=Config(); c.httpPort=0; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); c.httpPort=443; c.streamerPort=65535; c.Validate(scratch,false); c.streamerPort=65536; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("backend resolution boundaries accepted and rejected consistently",delegate { LauncherConfig c=Config(); c.height=319; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); c.height=320; c.width=320; c.Validate(scratch,false); c.height=7680; c.width=7680; c.Validate(scratch,false); c.height=7681; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("backend FPS range enforced before starting a child",delegate { LauncherConfig c=Config(); c.fps=14; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); c.fps=15; c.Validate(scratch,false); c.fps=120; c.Validate(scratch,false); c.fps=121; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("GUI prevents unsupported port and height choices",delegate { using(MainForm form=new MainForm()) { foreach(string field in new[]{"httpPort","streamerPort"}) { NumericUpDown number=(NumericUpDown)typeof(MainForm).GetField(field,BindingFlags.Instance|BindingFlags.NonPublic).GetValue(form); Throws<ArgumentOutOfRangeException>(delegate { number.Value=0; }); number.Value=443; number.Value=65535; } NumericUpDown height=(NumericUpDown)typeof(MainForm).GetField("renderHeight",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(form); Throws<ArgumentOutOfRangeException>(delegate { height.Value=319; }); height.Value=320; height.Value=7680; } });
            Test("GUI window sizing fits 1080p and laptop work areas at 150 percent without hiding footer",delegate {
                MethodInfo fit=typeof(MainForm).GetMethod("FitWindowToWorkArea",BindingFlags.Static|BindingFlags.NonPublic); Assert(fit!=null,"Screen work-area sizing is missing");
                int[][] cases={new[]{1920,1032,150,1800,1032,1500,1032},new[]{1366,728,150,1366,728,1366,728},new[]{3840,2080,200,2400,1800,2000,1440},new[]{1280,680,100,1200,680,1000,680}};
                foreach(int[] item in cases) { System.Drawing.Size area=new System.Drawing.Size(item[0],item[1]); float scale=item[2]/100F; System.Drawing.Size initial=(System.Drawing.Size)fit.Invoke(null,new object[]{new System.Drawing.Size(1200,900),scale,area}),minimum=(System.Drawing.Size)fit.Invoke(null,new object[]{new System.Drawing.Size(1000,720),scale,area}); Assert(initial==new System.Drawing.Size(item[3],item[4]) && minimum==new System.Drawing.Size(item[5],item[6]),"Window dimensions exceeded the scenario working area or changed unnecessarily"); }
            });
            Test("GUI initial bounds and minimum size stay inside the chosen actual screen work area",delegate { using(MainForm form=new MainForm()) { System.Drawing.Rectangle area=Screen.FromPoint(Cursor.Position).WorkingArea; Assert(area.Contains(form.Bounds),"Initial launcher window extends outside screen work area"); Assert(form.MinimumSize.Width<=area.Width && form.MinimumSize.Height<=area.Height,"Minimum window size exceeds screen work area"); } });
            Test("config Unicode path and settings round trip",delegate { LauncherConfig c=Config(); c.executablePath="App/中文 路径/仓库.exe"; c.mode="independent"; c.showWindow=true; c.width=2560; string p=Path.Combine(scratch,"配置.json"); c.Save(p); LauncherConfig d=LauncherConfig.Load(p); Assert(d.executablePath==c.executablePath && d.mode=="independent" && d.showWindow && d.width==2560,"Configuration was changed"); });
            Test("legacy default quality upgrades without changing resolution mode ports or executable",delegate { string p=Path.Combine(scratch,"legacy-default.json"); File.WriteAllText(p,"{\"executablePath\":\"App/中文 仓库.exe\",\"httpPort\":8091,\"streamerPort\":8891,\"width\":2560,\"height\":1440,\"mode\":\"independent\",\"fps\":60,\"showWindow\":true,\"minBitrateMbps\":8,\"startBitrateMbps\":20,\"maxBitrateMbps\":35}"); LauncherConfig c=LauncherConfig.Load(p); Assert(c.minBitrateMbps==12 && c.startBitrateMbps==35 && c.maxBitrateMbps==60,"Legacy default quality was not upgraded"); Assert(c.width==2560 && c.height==1440 && c.mode=="independent" && c.httpPort==8091 && c.streamerPort==8891 && c.executablePath=="App/中文 仓库.exe" && c.showWindow,"Unrelated settings changed during migration"); Dictionary<string,object> v=ConfigValues(c); Assert(v.ContainsKey("qualityProfile") && (string)v["qualityProfile"]=="clear","Migrated profile not clear"); Assert(v.ContainsKey("adaptiveResourceBudget") && (bool)v["adaptiveResourceBudget"],"Adaptive resource budget did not default on"); });
            Test("legacy custom bitrate survives migration and another save-load cycle",delegate { string p=Path.Combine(scratch,"legacy-custom.json"); File.WriteAllText(p,"{\"minBitrateMbps\":10,\"startBitrateMbps\":27,\"maxBitrateMbps\":48,\"fps\":45}"); LauncherConfig c=LauncherConfig.Load(p); c.Save(p); LauncherConfig d=LauncherConfig.Load(p); Assert(d.minBitrateMbps==10 && d.startBitrateMbps==27 && d.maxBitrateMbps==48 && d.fps==45,"Custom bitrate or FPS was replaced"); Dictionary<string,object> v=ConfigValues(d); Assert(v.ContainsKey("qualityProfile") && (string)v["qualityProfile"]=="custom","Custom bitrate not labelled custom"); });
            Test("explicit balanced quality and disabled resource budget survive reopening",delegate { string p=Path.Combine(scratch,"balanced.json"); File.WriteAllText(p,"{\"qualityProfile\":\"balanced\",\"adaptiveResourceBudget\":false,\"minBitrateMbps\":8,\"startBitrateMbps\":20,\"maxBitrateMbps\":35}"); LauncherConfig c=LauncherConfig.Load(p); c.Save(p); LauncherConfig d=LauncherConfig.Load(p); Assert(d.minBitrateMbps==8 && d.startBitrateMbps==20 && d.maxBitrateMbps==35,"Explicit balanced quality was migrated again"); Dictionary<string,object> v=ConfigValues(d); Assert(v.ContainsKey("adaptiveResourceBudget") && !(bool)v["adaptiveResourceBudget"],"Disabled resource budget was lost"); });
            Test("unsupported quality profile is rejected before service launch",delegate { string p=Path.Combine(scratch,"invalid-quality.json"); Dictionary<string,object> v=ConfigValues(Config()); v["qualityProfile"]="unlimited"; File.WriteAllText(p,new JavaScriptSerializer().Serialize(v)); LauncherConfig c=LauncherConfig.Load(p); Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("GUI quality choices affect encoder budget but preserve render dimensions and FPS",delegate { using(MainForm form=new MainForm()) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; FieldInfo qualityField=typeof(MainForm).GetField("quality",flags); Assert(qualityField!=null,"Quality selector is missing"); ComboBox quality=(ComboBox)qualityField.GetValue(form); ((NumericUpDown)typeof(MainForm).GetField("renderWidth",flags).GetValue(form)).Value=2560; ((NumericUpDown)typeof(MainForm).GetField("renderHeight",flags).GetValue(form)).Value=1440; int[][] budgets={new[]{8,20,35},new[]{12,35,60},new[]{20,50,90}}; for(int i=0;i<budgets.Length;i++) { quality.SelectedIndex=i; LauncherConfig c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); Assert(c.minBitrateMbps==budgets[i][0] && c.startBitrateMbps==budgets[i][1] && c.maxBitrateMbps==budgets[i][2],"Preset did not reach backend configuration"); Assert(c.width==2560 && c.height==1440 && c.fps==60,"Quality selector modified dimensions or target FPS"); } } });
            Test("GUI resource budget toggle reaches configuration for either scene mode",delegate { using(MainForm form=new MainForm()) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; CheckBox adaptive=(CheckBox)typeof(MainForm).GetField("adaptiveResources",flags).GetValue(form); ComboBox sceneMode=(ComboBox)typeof(MainForm).GetField("mode",flags).GetValue(form); for(int modeIndex=0;modeIndex<2;modeIndex++) { sceneMode.SelectedIndex=modeIndex; foreach(bool enabled in new[]{false,true}) { adaptive.Checked=enabled; LauncherConfig c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); Assert((bool)ConfigValues(c)["adaptiveResourceBudget"]==enabled,"Resource budget selection did not reach backend"); Assert(c.mode==(modeIndex==0?"shared":"independent"),"Resource budget selection changed scene mode"); } } } });
            Test("occupied port rejected without closing owner",delegate { TcpListener listener=new TcpListener(IPAddress.Any,0); listener.ExclusiveAddressUse=true; listener.Start(); try { int port=((IPEndPoint)listener.LocalEndpoint).Port; Throws<InvalidOperationException>(delegate { PortProbe.EnsureAvailable(port); }); Assert(listener.Server.IsBound,"Port owner was affected"); } finally { listener.Stop(); } });
            Test("released port accepted",delegate { TcpListener listener=new TcpListener(IPAddress.Any,0); listener.Start(); int port=((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop(); PortProbe.EnsureAvailable(port); });
            Test("GUI advanced budget preserves custom values and rejects inverted bitrate bounds before launch",delegate { using(MainForm form=new MainForm()) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; ((NumericUpDown)typeof(MainForm).GetField("fpsLimit",flags).GetValue(form)).Value=45; ((NumericUpDown)typeof(MainForm).GetField("minBitrate",flags).GetValue(form)).Value=10; ((NumericUpDown)typeof(MainForm).GetField("startBitrate",flags).GetValue(form)).Value=27; ((NumericUpDown)typeof(MainForm).GetField("maxBitrate",flags).GetValue(form)).Value=48; LauncherConfig c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); c.executablePath=Executable; c.Validate(scratch,false); Assert(c.fps==45 && c.qualityProfile=="custom" && c.minBitrateMbps==10 && c.startBitrateMbps==27 && c.maxBitrateMbps==48,"Advanced values did not reach the configuration"); ((NumericUpDown)typeof(MainForm).GetField("minBitrate",flags).GetValue(form)).Value=50; c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); c.executablePath=Executable; Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); } });
            Test("GUI port conflict blocks start inline and releases after correction without affecting owner",delegate {
                TcpListener owner=new TcpListener(IPAddress.Any,0); owner.ExclusiveAddressUse=true; owner.Start();
                try { using(MainForm form=new MainForm()) {
                    BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                    NumericUpDown port=(NumericUpDown)typeof(MainForm).GetField("httpPort",flags).GetValue(form);
                    NumericUpDown streamer=(NumericUpDown)typeof(MainForm).GetField("streamerPort",flags).GetValue(form);
                    Button launch=(Button)typeof(MainForm).GetField("start",flags).GetValue(form);
                    port.Value=((IPEndPoint)owner.LocalEndpoint).Port; streamer.Value=FreePort();
                    MethodInfo check=typeof(MainForm).GetMethod("CheckPorts",flags); Assert(check!=null,"Inline port check is missing"); check.Invoke(form,null);
                    Assert(!launch.Enabled,"Conflicting port left start enabled");
                    Label error=(Label)typeof(MainForm).GetField("portFeedback",flags).GetValue(form);
                    Assert(error.Text.Contains(port.Value.ToString()) && error.Text.Contains("占用"),"Port failure was not shown beside the configuration");
                    Assert(owner.Server.IsBound,"Port check affected another process");
                    port.Value=FreePort(); check.Invoke(form,null); Assert(launch.Enabled,"Corrected ports did not restore start");
                } } finally { owner.Stop(); }
            });
            Test("GUI running service locks every setting and labels listened ports with actual versus target FPS",delegate {
                string root=FixtureRoot(); using(MainForm form=new MainForm()) {
                    BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                    ServiceSession owned=(ServiceSession)typeof(MainForm).GetField("session",flags).GetValue(form); owned.Dispose();
                    using(ServiceSession live=new ServiceSession(root)) {
                        typeof(MainForm).GetField("session",flags).SetValue(form,live); live.Start(FixtureConfig());
                        typeof(MainForm).GetMethod("UpdateControls",flags).Invoke(form,null);
                        foreach(string field in new[]{"executable","httpPort","streamerPort","renderWidth","renderHeight","showWindow","mode","quality","adaptiveResources","publicSettings"}) Assert(!((Control)typeof(MainForm).GetField(field,flags).GetValue(form)).Enabled,"Running setting remains enabled: "+field);
                        MethodInfo apply=typeof(MainForm).GetMethod("ApplyStatus",flags); Assert(apply!=null,"Runtime status presentation is missing");
                        apply.Invoke(form,new object[]{new ServiceStatus {state="running",viewerCount=2,maxViewers=3,instances=new[]{new InstanceStatus {id="scene-1",pid=100,state="connected",targetFps=30,actualFps=29.7},new InstanceStatus {id="scene-2",pid=101,state="connected",targetFps=30,actualFps=null}},urls=new string[0],logs=new string[0]}});
                        Label ports=(Label)typeof(MainForm).GetField("portFeedback",flags).GetValue(form); Assert(ports.Text.Contains("已监听"),"Running ports were not labelled listened");
                        ListView list=(ListView)typeof(MainForm).GetField("instances",flags).GetValue(form);
                        Assert(list.Items.Count==2 && list.Items[0].SubItems[2].Text=="29.7 / 30" && list.Items[1].SubItems[2].Text=="— / 30","Actual FPS and unavailable telemetry were not distinguished from the target");
                        live.Stop();
                    }
                }
            });
            Test("Windows quoted arguments arrive intact",delegate { string output=Path.Combine(scratch,"参数.json"); string[] expected={"", "plain", "中文 路径", "embedded\"quote", "C:\\中文 路径\\", "slash\\\"quote"}; var args=new List<string>{"--test-worker","arguments",output}; args.AddRange(expected); using(OwnedProcess p=OwnedProcess.Start(Executable,args.ToArray(),scratch,null,Path.Combine(scratch,"arguments.log"))) { Assert(p.WaitForExit(4000),"Worker did not exit"); } string[] actual=new JavaScriptSerializer().Deserialize<string[]>(File.ReadAllText(output)); Assert(actual.Length==expected.Length,"Argument count changed"); for(int i=0;i<expected.Length;i++) Assert(actual[i]==expected[i],"Argument "+i+" changed"); });
            Test("job close reaps parent and descendant only",delegate { string pidFile=Path.Combine(scratch,"child.pid"); using(Process unrelated=Process.Start(new ProcessStartInfo(Executable,"--test-worker sleep") { UseShellExecute=false,CreateNoWindow=true })) { try { int own; int child; using(OwnedProcess p=OwnedProcess.Start(Executable,new[]{"--test-worker","tree",pidFile},scratch,null,Path.Combine(scratch,"tree.log"))) { own=p.Id; WaitForFile(pidFile); child=int.Parse(File.ReadAllText(pidFile)); Assert(Alive(own)&&Alive(child),"Owned tree did not start"); } EventuallyGone(own); EventuallyGone(child); Assert(!unrelated.HasExited,"Unrelated process was killed"); } finally { if(!unrelated.HasExited) unrelated.Kill(); unrelated.WaitForExit(); } } });
            Test("failed process creation releases ownership",delegate { Throws<System.ComponentModel.Win32Exception>(delegate { using(OwnedProcess p=OwnedProcess.Start(Path.Combine(scratch,"not-found.exe"),new string[0],scratch,null,Path.Combine(scratch,"missing.log"))) {} }); });
            Test("authenticated status, duplicate start, repeat stop and restart",delegate { string root=FixtureRoot(); using(ServiceSession session=new ServiceSession(root)) { LauncherConfig c=FixtureConfig(); session.Start(c); ServiceStatus status=session.ReadStatus(); Assert(session.State=="running" && status.mode==c.mode && status.maxViewers==10,"No authenticated running status"); Throws<InvalidOperationException>(delegate { session.Start(c); }); session.Stop(); session.Stop(); Assert(session.State=="idle","Stop did not restore idle"); session.Start(c); session.Stop(); } });
            Test("backend startup failure rolls back and permits restart",delegate { string root=FixtureRoot(); string marker=Path.Combine(root,"fail-start"); File.WriteAllText(marker,""); using(ServiceSession session=new ServiceSession(root)) { Throws<InvalidOperationException>(delegate { session.Start(FixtureConfig()); }); Assert(session.State=="idle","Failure left session busy"); File.Delete(marker); session.Start(FixtureConfig()); session.Stop(); } });
            Test("stop during startup cancels and reaps its child",delegate { string root=FixtureRoot(); File.WriteAllText(Path.Combine(root,"delay-start"),""); using(ServiceSession session=new ServiceSession(root)) { Exception failure=null; Thread start=new Thread(delegate() { try { session.Start(FixtureConfig()); } catch(Exception ex) { failure=ex; } }); start.Start(); string p=Path.Combine(root,"starting.pid"); WaitForFile(p); int pid=int.Parse(File.ReadAllText(p)); session.Stop(); Assert(start.Join(4000),"Start cancellation hung"); Assert(failure is OperationCanceledException && session.State=="idle","Start did not cancel cleanly"); EventuallyGone(pid); } });
            Test("control file cannot nominate an unrelated process",delegate { string root=FixtureRoot(); File.WriteAllText(Path.Combine(root,"wrong-pid"),""); using(ServiceSession session=new ServiceSession(root)) { Throws<InvalidOperationException>(delegate { session.Start(FixtureConfig()); }); Assert(session.State=="idle","Untrusted control file was accepted"); } });
            string json=new JavaScriptSerializer().Serialize(new { passed=Results.Count-failures,failed=failures,results=Results.ToArray(),testedAt=DateTime.UtcNow.ToString("o") });
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(report))); File.WriteAllText(report,json,new UTF8Encoding(false)); foreach(string r in Results) Console.WriteLine(r); Console.WriteLine("Report: "+report);
            try { Directory.Delete(scratch,true); } catch(IOException) {}
            return failures==0?0:1;
        }
        public static int Worker(string[] args)
        {
            if(args[1]=="arguments") { var values=new List<string>(); for(int i=3;i<args.Length;i++) values.Add(args[i]); File.WriteAllText(args[2],new JavaScriptSerializer().Serialize(values)); return 0; }
            if(args[1]=="tree") { using(Process child=Process.Start(new ProcessStartInfo(Executable,"--test-worker sleep") { UseShellExecute=false,CreateNoWindow=true })) File.WriteAllText(args[2],child.Id.ToString()); }
            Thread.Sleep(60000); return 0;
        }
    }
}
