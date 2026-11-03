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
        private const string QueuedStatusJson = "{\"state\":\"running\",\"mode\":\"independent\",\"viewerCount\":2,\"maxViewers\":5,\"instances\":[{\"id\":\"viewer-000000000001\",\"pid\":12345,\"state\":\"ready\",\"targetFps\":60,\"actualFps\":59.8},{\"id\":\"viewer-000000000002\",\"pid\":null,\"state\":\"queued\",\"targetFps\":60,\"actualFps\":null}],\"viewers\":[],\"urls\":[],\"logs\":[]}";
        private static void AssertQueuedStatusPolling()
        {
            string root=FixtureRoot(); BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
            using(ServiceSession session=new ServiceSession(root)) {
                session.Start(FixtureConfig());
                FieldInfo portField=typeof(ServiceSession).GetField("controlPort",flags);
                int originalPort=(int)portField.GetValue(session);
                string expectedAuthorization="Authorization: Bearer "+(string)typeof(ServiceSession).GetField("token",flags).GetValue(session);
                TcpListener listener=new TcpListener(IPAddress.Loopback,0); listener.Start();
                Exception serverFailure=null; int requests=0;
                Thread server=new Thread(delegate() {
                    try {
                        for(int i=0;i<4;i++) using(TcpClient client=listener.AcceptTcpClient()) {
                            client.ReceiveTimeout=4000; client.SendTimeout=4000;
                            using(NetworkStream stream=client.GetStream()) using(StreamReader reader=new StreamReader(stream,Encoding.ASCII,false,1024,true)) {
                                Assert(reader.ReadLine()=="GET /status HTTP/1.1","ReadStatus changed its control request");
                                bool authorized=false; string header;
                                while(!string.IsNullOrEmpty(header=reader.ReadLine())) if(header==expectedAuthorization) authorized=true;
                                Assert(authorized,"ReadStatus lost authenticated control access");
                                byte[] body=Encoding.UTF8.GetBytes(QueuedStatusJson);
                                byte[] head=Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "+body.Length+"\r\nConnection: close\r\n\r\n");
                                stream.Write(head,0,head.Length); stream.Write(body,0,body.Length); stream.Flush(); requests++;
                            }
                        }
                    } catch(Exception ex) { serverFailure=ex; }
                });
                server.IsBackground=true; server.Start();
                try {
                    portField.SetValue(session,((IPEndPoint)listener.LocalEndpoint).Port);
                    for(int i=0;i<4;i++) {
                        ServiceStatus result=session.ReadStatus();
                        Assert(result.instances.Length==2 && (object)result.instances[1].pid==null,"Queued PID must remain absent during HTTP polling");
                        Assert(result.instances[0].pid==12345 && session.State=="running","Queued status interrupted the running session");
                    }
                    Assert(server.Join(4000),"Status fixture did not complete");
                    Assert(serverFailure==null && requests==4,"Authenticated status fixture failed");
                } finally {
                    portField.SetValue(session,originalPort); listener.Stop(); server.Join(4000); session.Stop();
                }
            }
        }
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
            Test("UE58 prerequisites require VC x64 and GameInput and build an explicit elevated installer action",delegate {
                string root=Path.Combine(scratch,"中文 运行组件"); Directory.CreateDirectory(root); Assert(RuntimePrerequisites.MissingFiles(root).Length==3,"Missing prerequisites were not detected"); Throws<FileNotFoundException>(delegate {RuntimePrerequisites.CreateInstaller(root);});
                foreach(string relative in RuntimePrerequisites.RequiredFiles) {string file=Path.Combine(root,relative); Directory.CreateDirectory(Path.GetDirectoryName(file)); File.WriteAllText(file,"fixture-only");}
                Assert(RuntimePrerequisites.MissingFiles(root).Length==0,"UE58 prerequisites were not detected"); ProcessStartInfo info=RuntimePrerequisites.CreateInstaller(root);
                Assert(info.Verb=="runas" && info.UseShellExecute && info.Arguments.Contains("Install-RuntimeDependencies.ps1") && info.Arguments.Contains("中文 运行组件") && !info.Arguments.Contains("UEPrereqSetup"),"Installer action uses incorrect dependencies or loses Unicode path");
                File.Delete(Path.Combine(root,RuntimePrerequisites.RequiredFiles[2])); Throws<FileNotFoundException>(delegate {RuntimePrerequisites.CreateInstaller(root);});
            });
            Test("access protection defaults off for new and missing-field legacy configurations",delegate {
                Dictionary<string,object> fresh=ConfigValues(Config()); Assert(fresh.ContainsKey("accessProtectionEnabled") && !(bool)fresh["accessProtectionEnabled"],"New configuration must explicitly default access protection off");
                string file=Path.Combine(scratch,"legacy-access.json"); File.WriteAllText(file,"{\"networkMode\":\"public\",\"publicUrl\":\"http://fixture.example.com:8080\",\"accessCode\":\"fixture-only-preserved-code\"}");
                LauncherConfig legacy=LauncherConfig.Load(file).Clone(); legacy.ValidateNetwork(scratch); Assert(!(bool)ConfigValues(legacy)["accessProtectionEnabled"] && legacy.accessCode=="fixture-only-preserved-code","Legacy config enabled protection or lost its saved code");
            });
            Test("access protection validates codes in LAN and public only when explicitly enabled",delegate {
                JavaScriptSerializer accessJson=new JavaScriptSerializer();
                foreach(string network in new[]{"lan","public"}) {
                    Dictionary<string,object> values=ConfigValues(Config()); values["networkMode"]=network; values["publicUrl"]="http://fixture.example.com:8080"; values["accessCode"]=""; values["accessProtectionEnabled"]=false;
                    LauncherConfig off=accessJson.Deserialize<LauncherConfig>(accessJson.Serialize(values)); off.ValidateNetwork(scratch);
                    values["accessProtectionEnabled"]=true; foreach(string invalid in new[]{"","short","            "}) { values["accessCode"]=invalid; LauncherConfig enabled=accessJson.Deserialize<LauncherConfig>(accessJson.Serialize(values)); Throws<ArgumentException>(delegate { enabled.ValidateNetwork(scratch); }); }
                    values["accessCode"]="fixture-only-protected-code"; LauncherConfig valid=accessJson.Deserialize<LauncherConfig>(accessJson.Serialize(values)); valid.ValidateNetwork(scratch); string file=Path.Combine(scratch,"protected-"+network+".json"); valid.Save(file); LauncherConfig restored=LauncherConfig.Load(file).Clone(); Assert((bool)ConfigValues(restored)["accessProtectionEnabled"] && restored.accessCode==valid.accessCode,"Protection or stored code lost in save/load/clone");
                }
                LauncherConfig noAddress=Config(); noAddress.networkMode="public"; Throws<ArgumentException>(delegate { noAddress.ValidateNetwork(scratch); });
            });
            Test("access protection JSON rejects coerced strings numbers null and containers",delegate {
                string file=Path.Combine(scratch,"access-types.json");
                foreach(string invalid in new[]{"\"true\"","\"false\"","\"\"","0","1","null","{}","[]"}) {
                    File.WriteAllText(file,"{\"accessProtectionEnabled\":"+invalid+"}");
                    try { LauncherConfig.Load(file); throw new Exception("Accepted non-boolean access policy: "+invalid); }
                    catch(ArgumentException ex) { Assert(ex.Message.Contains("布尔值"),"Non-boolean policy did not produce clear type validation: "+invalid); }
                }
                foreach(bool enabled in new[]{false,true}) { File.WriteAllText(file,"{\"accessProtectionEnabled\":"+(enabled?"true":"false")+"}"); LauncherConfig read=LauncherConfig.Load(file); Assert(read.accessProtectionEnabled==enabled,"Boolean value changed while loading"); read.Save(file); Assert(LauncherConfig.Load(file).Clone().accessProtectionEnabled==enabled,"Boolean value changed during save/load/clone"); }
            });
            Test("GUI access protection disables credential actions without discarding stored code",delegate {
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; LauncherConfig c=Config(); c.accessCode="fixture-only-existing-code";
                using(PublicSettingsForm form=new PublicSettingsForm(scratch,c)) {
                    CheckBox toggle=(CheckBox)typeof(PublicSettingsForm).GetField("accessProtection",flags).GetValue(form),reveal=(CheckBox)typeof(PublicSettingsForm).GetField("reveal",flags).GetValue(form); TextBox code=(TextBox)typeof(PublicSettingsForm).GetField("code",flags).GetValue(form); Button generate=(Button)typeof(PublicSettingsForm).GetField("generate",flags).GetValue(form);
                    Assert(!toggle.Checked && !code.Enabled && !generate.Enabled && !reveal.Enabled && code.UseSystemPasswordChar,"Off protection left credential controls active or exposed");
                    Assert(!form.Read().accessProtectionEnabled && form.Read().accessCode==c.accessCode,"Opening disabled protection erased code");
                    toggle.Checked=true; Assert(code.Enabled && generate.Enabled && reveal.Enabled && form.Read().accessProtectionEnabled,"Enabled protection did not enable credential editing"); reveal.Checked=true; Assert(!code.UseSystemPasswordChar,"Reveal did not show code");
                    code.Text="fixture-only-edited-code"; toggle.Checked=false; Assert(!reveal.Checked && code.UseSystemPasswordChar && !code.Enabled && !generate.Enabled && !reveal.Enabled,"Turning off failed to remask and disable actions");
                    LauncherConfig saved=form.Read(); saved.Save(Path.Combine(scratch,"access-disabled.json")); saved=LauncherConfig.Load(Path.Combine(scratch,"access-disabled.json")); Assert(!saved.accessProtectionEnabled && saved.accessCode=="fixture-only-edited-code","Off save dropped edited code");
                    toggle.Checked=true; Assert(code.Text=="fixture-only-edited-code","Enabling again lost stored code"); form.Read().ValidateNetwork(scratch);
                }
            });
            Test("GUI main access toggle loads saved state and agrees with access settings after save",delegate {
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; string folder=Path.Combine(scratch,"access-main"); Directory.CreateDirectory(folder); LauncherConfig c=Config(); c.accessProtectionEnabled=true; c.accessCode="fixture-only-main-code"; c.Save(Path.Combine(folder,"launcher.config.json"));
                using(MainForm form=new MainForm()) {
                    typeof(MainForm).GetField("root",flags).SetValue(form,folder); typeof(MainForm).GetMethod("LoadSettings",flags).Invoke(form,null); CheckBox toggle=(CheckBox)typeof(MainForm).GetField("accessProtection",flags).GetValue(form);
                    Assert(toggle.Checked,"Main switch did not load saved protection"); toggle.Checked=false; LauncherConfig read=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); Assert(!read.accessProtectionEnabled && read.accessCode==c.accessCode,"Main switch did not reach settings or cleared code");
                    using(PublicSettingsForm dialog=new PublicSettingsForm(folder,read)) { Assert(!dialog.Read().accessProtectionEnabled,"Dialog ignored main switch"); ((CheckBox)typeof(PublicSettingsForm).GetField("accessProtection",flags).GetValue(dialog)).Checked=true; LauncherConfig accepted=dialog.Read(); typeof(MainForm).GetMethod("ApplyAccessSettings",flags).Invoke(form,new object[]{accepted}); }
                    Assert(toggle.Checked && ((LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null)).accessProtectionEnabled,"Saved dialog and main switch diverged");
                    foreach(string busy in new[]{"startBusy","stopBusy"}) { typeof(MainForm).GetField(busy,flags).SetValue(form,true); typeof(MainForm).GetMethod("UpdateControls",flags).Invoke(form,null); Assert(!toggle.Enabled,"Protection could change during lifecycle transition"); typeof(MainForm).GetField(busy,flags).SetValue(form,false); }
                    typeof(MainForm).GetMethod("UpdateControls",flags).Invoke(form,null); Assert(toggle.Enabled,"Protection did not unlock while stopped");
                }
            });
            Test("explicit access protection reaches child runtime configuration without exposing or replacing credentials",delegate {
                foreach(bool enabled in new[]{false,true}) { string fixture=FixtureRoot(); LauncherConfig c=FixtureConfig(); c.accessProtectionEnabled=enabled; c.accessCode="fixture-only-runtime-code"; using(ServiceSession session=new ServiceSession(fixture)) { session.Start(c); string file=Directory.GetFiles(Path.Combine(fixture,"sessions"),"config.json",SearchOption.AllDirectories)[0]; LauncherConfig runtime=LauncherConfig.Load(file); Assert(runtime.accessProtectionEnabled==enabled && runtime.accessCode==c.accessCode,"Runtime access policy or credentials changed"); session.Stop(); } }
            });
            Test("warm standby is opt-in for new and missing-field legacy configurations",delegate {
                Dictionary<string,object> fresh=ConfigValues(Config()); Assert(fresh.ContainsKey("warmStandbyEnabled") && !(bool)fresh["warmStandbyEnabled"],"New configuration must explicitly default warm standby off");
                string file=Path.Combine(scratch,"legacy-warm.json"); File.WriteAllText(file,"{\"mode\":\"independent\",\"accessCode\":\"fixture-only-preserved-code\"}");
                LauncherConfig legacy=LauncherConfig.Load(file).Clone(); Dictionary<string,object> values=ConfigValues(legacy);
                Assert(values.ContainsKey("warmStandbyEnabled") && !(bool)values["warmStandbyEnabled"] && legacy.accessCode=="fixture-only-preserved-code","Legacy configuration enabled standby or lost its saved code");
            });
            Test("warm standby JSON requires booleans and preserves explicit settings across save load and clone",delegate {
                string file=Path.Combine(scratch,"warm-types.json");
                foreach(string invalid in new[]{"\"true\"","0","1","null","{}","[]"}) { File.WriteAllText(file,"{\"warmStandbyEnabled\":"+invalid+"}"); Throws<ArgumentException>(delegate {LauncherConfig.Load(file);}); }
                foreach(bool enabled in new[]{true,false}) {
                    File.WriteAllText(file,"{\"mode\":\"independent\",\"warmStandbyEnabled\":"+(enabled?"true":"false")+"}");
                    LauncherConfig c=LauncherConfig.Load(file).Clone(); c.Save(file); Dictionary<string,object> read=ConfigValues(LauncherConfig.Load(file));
                    Assert(read.ContainsKey("warmStandbyEnabled") && (bool)read["warmStandbyEnabled"]==enabled,"Saved standby preference was lost");
                }
            });
            Test("GUI standby switch is independent-only and retains its preference through mode and lifecycle changes",delegate {
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; using(MainForm form=new MainForm()) {
                    FieldInfo field=typeof(MainForm).GetField("warmStandby",flags); Assert(field!=null,"Standby switch is missing"); CheckBox toggle=(CheckBox)field.GetValue(form);
                    ComboBox mode=(ComboBox)typeof(MainForm).GetField("mode",flags).GetValue(form); MethodInfo update=typeof(MainForm).GetMethod("UpdateControls",flags),read=typeof(MainForm).GetMethod("ReadSettings",flags);
                    mode.SelectedIndex=1; update.Invoke(form,null); Assert(toggle.Enabled && !toggle.Checked,"Independent mode did not offer the opt-in switch"); toggle.Checked=true;
                    mode.SelectedIndex=0; Assert(!toggle.Enabled && toggle.Checked,"Shared mode must disable but retain the preference");
                    mode.SelectedIndex=1; Assert(toggle.Enabled && (bool)ConfigValues((LauncherConfig)read.Invoke(form,null))["warmStandbyEnabled"],"Returning to independent mode lost the selected preference");
                    Label hint=(Label)typeof(MainForm).GetField("warmHint",flags).GetValue(form); Assert(hint.Text.Contains("资源"),"Extra resource cost is not disclosed");
                    foreach(string busy in new[]{"startBusy","stopBusy"}) { typeof(MainForm).GetField(busy,flags).SetValue(form,true); update.Invoke(form,null); Assert(!toggle.Enabled,"Standby preference remained editable during a transition"); typeof(MainForm).GetField(busy,flags).SetValue(form,false); }
                    update.Invoke(form,null); Assert(toggle.Enabled,"Stopped service did not unlock standby control");
                    form.PerformLayout(); Control adaptive=(Control)typeof(MainForm).GetField("adaptiveResources",flags).GetValue(form);
                    Assert(toggle.Parent.ClientRectangle.Contains(toggle.Bounds) && !toggle.Bounds.IntersectsWith(adaptive.Bounds) && !hint.Bounds.IntersectsWith(adaptive.Bounds),"Standby settings overlap existing controls");
                }
            });
            Test("GUI standby status distinguishes ready and preparing counts without counting them as viewers",delegate {
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; using(MainForm form=new MainForm()) {
                    FieldInfo field=typeof(MainForm).GetField("warmStatus",flags); Assert(field!=null,"Standby status summary is missing");
                    foreach(string counts in new[]{"\"warmReadyCount\":1,\"warmStartingCount\":0","\"warmReadyCount\":0,\"warmStartingCount\":1"}) {
                        ServiceStatus status=new JavaScriptSerializer().Deserialize<ServiceStatus>("{\"state\":\"running\",\"mode\":\"independent\",\"viewerCount\":0,\"maxViewers\":5,\"warmStandbyEnabled\":true,"+counts+"}");
                        typeof(MainForm).GetMethod("ApplyStatus",flags).Invoke(form,new object[]{status}); Label label=(Label)field.GetValue(form);
                        Assert(label.Text.Contains(counts.Contains("warmReadyCount\":1")?"就绪 1":"准备中 1"),"Standby readiness was not rendered from server status");
                        Assert(((Label)typeof(MainForm).GetField("viewers",flags).GetValue(form)).Text.StartsWith("0 / 5"),"Standby was incorrectly counted as a visitor");
                    }
                    ServiceStatus waiting=new JavaScriptSerializer().Deserialize<ServiceStatus>("{\"state\":\"running\",\"mode\":\"independent\",\"warmStandbyEnabled\":true,\"warmBlockedReason\":\"first-frame\"}");
                    typeof(MainForm).GetMethod("ApplyStatus",flags).Invoke(form,new object[]{waiting});
                    Assert(((Label)field.GetValue(form)).Text.Contains("等待用户首帧稳定"),"First-frame stability gate is not explained");
                }
            });
            Test("standby preference reaches the actual child runtime configuration",delegate {
                foreach(bool enabled in new[]{false,true}) { string root=FixtureRoot(); LauncherConfig c=FixtureConfig(); Dictionary<string,object> values=ConfigValues(c); values["warmStandbyEnabled"]=enabled; c=new JavaScriptSerializer().Deserialize<LauncherConfig>(new JavaScriptSerializer().Serialize(values)); c.mode="independent";
                    using(ServiceSession session=new ServiceSession(root)) { session.Start(c); string file=Directory.GetFiles(Path.Combine(root,"sessions"),"config.json",SearchOption.AllDirectories)[0]; Dictionary<string,object> saved=ConfigValues(LauncherConfig.Load(file)); Assert(saved.ContainsKey("warmStandbyEnabled") && (bool)saved["warmStandbyEnabled"]==enabled,"Child runtime lost standby preference"); session.Stop(); }
                }
            });
            Test("PixelStreaming2 defaults and explicit frame budgets roundtrip without an SDK",delegate {
                LauncherConfig fresh=Config(); Assert(fresh.fps==60 && fresh.fixedFps && fresh.encoderAsync && fresh.encoder=="NVIDIA" && !fresh.adaptiveResourceBudget,"PixelStreaming2 defaults changed");
                Assert(fresh.qualityProfile=="balanced" && fresh.minBitrateMbps==1 && fresh.startBitrateMbps==8 && fresh.maxBitrateMbps==24,"New configuration did not use the balanced network budget");
                foreach(int fps in new[]{0,15,30,120}) { LauncherConfig c=Config(); c.fps=fps; c.fixedFps=fps>0; c.accessCode="fixture-only-preserved-code"; c.Validate(scratch,false); string file=Path.Combine(scratch,"fps-"+fps+".json"); c.Save(file); LauncherConfig restored=LauncherConfig.Load(file).Clone(); Assert(restored.fps==fps && restored.accessCode==c.accessCode,"Frame cap or access code changed during roundtrip"); }
                foreach(int fps in new[]{-1,1,14,121}) { LauncherConfig c=Config(); c.fps=fps; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); }
            });
            Test("PixelStreaming2 settings save and validate without overwriting access configuration",delegate {
                LauncherConfig c=Config(); c.encoder="Auto"; c.encoderAsync=false; c.fixedFps=false; c.fps=0; c.adaptiveResourceBudget=true; c.accessCode="fixture-kept-code";
                string file=Path.Combine(scratch,"ps2-controls.json"); c.Save(file); LauncherConfig d=LauncherConfig.Load(file); d.Validate(scratch,false);
                Assert(d.encoder=="Auto" && !d.encoderAsync && !d.fixedFps && d.fps==0 && d.adaptiveResourceBudget && d.accessCode==c.accessCode,"PS2 controls or saved access code lost");
                d.fixedFps=true; Throws<ArgumentException>(delegate {d.Validate(scratch,false);}); d.fps=60; Throws<ArgumentException>(delegate {d.Validate(scratch,false);}); d.adaptiveResourceBudget=false; d.Validate(scratch,false); d.encoder="invalid"; Throws<ArgumentException>(delegate {d.Validate(scratch,false);});
            });
            Test("GUI fixed target locks adaptive budget and all encoder choices reach runtime config",delegate {
                using(MainForm form=new MainForm()) {
                    BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                    CheckBox fixedTarget=(CheckBox)typeof(MainForm).GetField("fixedFps",flags).GetValue(form), adaptive=(CheckBox)typeof(MainForm).GetField("adaptiveResources",flags).GetValue(form), asyncCapture=(CheckBox)typeof(MainForm).GetField("encoderAsync",flags).GetValue(form);
                    ComboBox encoder=(ComboBox)typeof(MainForm).GetField("encoder",flags).GetValue(form); NumericUpDown fps=(NumericUpDown)typeof(MainForm).GetField("fpsLimit",flags).GetValue(form);
                    fixedTarget.Checked=false; adaptive.Checked=true; fps.Value=0; fixedTarget.Checked=true;
                    Assert(!adaptive.Checked && !adaptive.Enabled && fps.Value==60,"Fixed FPS did not resolve adaptive conflict or invalid zero FPS");
                    encoder.SelectedIndex=1; asyncCapture.Checked=false; LauncherConfig c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null);
                    Assert(c.fixedFps && c.fps==60 && c.encoder=="Auto" && !c.encoderAsync && !c.adaptiveResourceBudget,"PS2 UI values not read");
                    fixedTarget.Checked=false; Assert(adaptive.Enabled,"Disabling fixed FPS did not restore adaptive control");
                }
            });
            Test("GUI reopens explicit preset budgets unchanged until the user switches quality",delegate {
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                foreach(string profile in new[]{"balanced","clear","ultra","custom"}) {
                    string root=Path.Combine(scratch,"preset-"+profile); Directory.CreateDirectory(root);
                    LauncherConfig saved=Config(); saved.qualityProfile=profile; saved.minBitrateMbps=8; saved.startBitrateMbps=20; saved.maxBitrateMbps=35; saved.fps=45; saved.accessCode="fixture-only-preset-code"; saved.Save(Path.Combine(root,"launcher.config.json"));
                    using(MainForm form=new MainForm()) {
                        typeof(MainForm).GetField("root",flags).SetValue(form,root); typeof(MainForm).GetMethod("LoadSettings",flags).Invoke(form,null);
                        NumericUpDown fps=(NumericUpDown)typeof(MainForm).GetField("fpsLimit",flags).GetValue(form); fps.Value=30;
                        LauncherConfig read=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null);
                        Assert(read.qualityProfile==profile && read.minBitrateMbps==8 && read.startBitrateMbps==20 && read.maxBitrateMbps==35 && read.fps==30 && read.accessCode==saved.accessCode,"Opening or reading settings replaced an explicit saved budget");
                        ComboBox quality=(ComboBox)typeof(MainForm).GetField("quality",flags).GetValue(form); quality.SelectedIndex=profile=="ultra"?0:2;
                        read=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null);
                        Assert(read.minBitrateMbps==1 && read.startBitrateMbps==(profile=="ultra"?8:16) && read.maxBitrateMbps==(profile=="ultra"?24:50),"Changing quality did not apply the new preset");
                    }
                }
            });
            Test("GUI uncapped targets and queued instances remain distinct from zero measured FPS",delegate {
                using(MainForm form=new MainForm()) {
                    BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                    ((CheckBox)typeof(MainForm).GetField("fixedFps",flags).GetValue(form)).Checked=false; NumericUpDown fps=(NumericUpDown)typeof(MainForm).GetField("fpsLimit",flags).GetValue(form); fps.Value=0;
                    ((ComboBox)typeof(MainForm).GetField("mode",flags).GetValue(form)).SelectedIndex=1;
                    LauncherConfig c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); c.executablePath=Executable; c.Validate(scratch,false); Assert(c.fps==0,"GUI replaced uncapped FPS");
                    Label hint=(Label)typeof(MainForm).GetField("adaptiveHint",flags).GetValue(form); Assert(hint.Text.Contains("不按人数限帧") && hint.Text.Contains("排队"),"Uncapped resource policy was not explained");
                    typeof(MainForm).GetMethod("ApplyStatus",flags).Invoke(form,new object[]{new ServiceStatus {state="running",viewerCount=2,instances=new[]{new InstanceStatus {id="running",state="connected",actualFps=0,targetFps=0},new InstanceStatus {id="waiting",state="queued",actualFps=null,targetFps=0}},viewers=new[]{new ViewerStatus {playerId="1",state="queued"}}}});
                    ListView list=(ListView)typeof(MainForm).GetField("instances",flags).GetValue(form);
                    Assert(list.Items[0].SubItems[2].Text=="0.0 / 无固定上限" && list.Items[1].SubItems[2].Text=="— / 无固定上限","Actual zero and an uncapped target were conflated");
                    Assert(list.Items[1].SubItems[1].Text=="排队中" && list.Items[1].SubItems[1].ForeColor==LauncherTheme.Amber,"Queued instance state was not presented");
                    ListView viewers=(ListView)typeof(MainForm).GetField("connections",flags).GetValue(form); Assert(viewers.Items[0].SubItems[2].Text=="排队中","Queued viewer state was not presented");
                    fps.Value=14; c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); c.executablePath=Executable; Throws<ArgumentException>(delegate {c.Validate(scratch,false);});
                }
            });
            Test("dual origin defaults empty and survives launcher save clone and runtime handoff",delegate {
                Assert(ConfigValues(Config()).ContainsKey("backupPublicUrl") && (string)ConfigValues(Config())["backupPublicUrl"]=="","New configuration must explicitly disable backup origin");
                string fixture=FixtureRoot(),file=Path.Combine(fixture,"launcher.config.json"); File.WriteAllText(file,"{\"networkMode\":\"lan\"}"); Assert((string)ConfigValues(LauncherConfig.Load(file))["backupPublicUrl"]=="","Legacy file enabled backup origin");
                LauncherConfig source=FixtureConfig(); source.networkMode="public"; source.publicUrl="https://warehouse-sim.iyunquna.com"; source.externalTlsTermination=true; source.accessCode="fixture-only-preserved-code";
                var values=ConfigValues(source); values["backupPublicUrl"]="http://47.96.135.179:8080"; LauncherConfig c=new JavaScriptSerializer().Deserialize<LauncherConfig>(new JavaScriptSerializer().Serialize(values)); c.Validate(fixture,false); c.Save(file); c=LauncherConfig.Load(file).Clone();
                Assert((string)ConfigValues(c)["backupPublicUrl"]==values["backupPublicUrl"].ToString() && c.accessCode==source.accessCode,"Backup or credentials lost in persistence");
                using(ServiceSession session=new ServiceSession(fixture)) { session.Start(c); string runtime=Directory.GetFiles(Path.Combine(fixture,"sessions"),"config.json",SearchOption.AllDirectories)[0]; LauncherConfig child=LauncherConfig.Load(runtime); Assert((string)ConfigValues(child)["backupPublicUrl"]==values["backupPublicUrl"].ToString() && child.publicUrl==source.publicUrl && child.externalTlsTermination && !child.trustProxy,"Dual origin missing from real runtime config"); session.Stop(); }
            });
            Test("dual origin JSON rejects nonstring values without coercion",delegate {
                string file=Path.Combine(scratch,"backup-types.json"); foreach(string invalid in new[]{"null","0","1","true","{}","[]"}) { File.WriteAllText(file,"{\"backupPublicUrl\":"+invalid+"}"); Throws<ArgumentException>(delegate {LauncherConfig.Load(file);}); }
            });
            Test("backup origin canonical scheme host and default port reach saved and runtime configuration",delegate {
                string fixture=FixtureRoot(),file=Path.Combine(fixture,"launcher.config.json"); LauncherConfig c=FixtureConfig(); c.networkMode="public"; c.publicUrl="https://warehouse-sim.iyunquna.com"; c.externalTlsTermination=true;
                using(PublicSettingsForm access=new PublicSettingsForm(fixture,c)) { TextBox backup=(TextBox)typeof(PublicSettingsForm).GetField("backupAddress",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(access); backup.Text="HTTP://BACKUP.Example.COM:80/"; c=access.Read(); }
                c.Validate(fixture,false); Assert(c.backupPublicUrl=="http://backup.example.com","Origin was not canonicalized"); c.Save(file); c=LauncherConfig.Load(file); Assert(c.backupPublicUrl=="http://backup.example.com","Saved origin was not canonical");
                using(ServiceSession session=new ServiceSession(fixture)) { session.Start(c); string runtime=Directory.GetFiles(Path.Combine(fixture,"sessions"),"config.json",SearchOption.AllDirectories)[0]; Assert(LauncherConfig.Load(runtime).backupPublicUrl=="http://backup.example.com","Runtime received uppercase or noncanonical origin"); session.Stop(); }
            });
            Test("deployment-only fields survive load clone GUI edits save and runtime handoff",delegate {
                string fixture=FixtureRoot(),file=Path.Combine(fixture,"launcher.config.json"); var values=ConfigValues(FixtureConfig()); values["networkMode"]="public"; values["publicUrl"]="https://warehouse-sim.iyunquna.com"; values["backupPublicUrl"]="http://47.96.135.179:8080"; values["externalTlsTermination"]=true;
                values["publicMediaAddress"]="47.96.135.179"; values["customDeployment"] = new Dictionary<string,object>{{"mediaPort",50000},{"preserve",true}}; values["fps"]=30; values["warmStandbyEnabled"]=true; values["encoderAsync"]=true;
                File.WriteAllText(file,new JavaScriptSerializer().Serialize(values)); LauncherConfig c=LauncherConfig.Load(file).Clone(); BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                using(PublicSettingsForm access=new PublicSettingsForm(fixture,c)) c=access.Read();
                using(MainForm main=new MainForm()) { typeof(MainForm).GetMethod("ApplyAccessSettings",flags).Invoke(main,new object[]{c}); c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(main,null); }
                c.executablePath=Executable; c.httpPort=FreePort(); c.streamerPort=FreePort(); c.Save(file); var saved=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(file)); Assert(saved["publicMediaAddress"].ToString()=="47.96.135.179" && ((Dictionary<string,object>)saved["customDeployment"])["preserve"].Equals(true),"UI/save dropped backend-only fields");
                using(ServiceSession session=new ServiceSession(fixture)) { session.Start(c); string runtime=Directory.GetFiles(Path.Combine(fixture,"sessions"),"config.json",SearchOption.AllDirectories)[0]; var child=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(runtime)); Assert(child["publicMediaAddress"].ToString()=="47.96.135.179" && ((Dictionary<string,object>)child["customDeployment"])["mediaPort"].Equals(50000),"Runtime dropped backend-only fields"); session.Stop(); }
            });
            Test("backup origin accepts only complete HTTP origins with ALB HTTPS primary",delegate {
                JavaScriptSerializer originJson=new JavaScriptSerializer(); var values=ConfigValues(Config()); values["networkMode"]="public"; values["publicUrl"]="https://warehouse-sim.iyunquna.com"; values["externalTlsTermination"]=true;
                foreach(string url in new[]{"http://47.96.135.179:8080","http://47.96.135.179:8080/","http://backup.example.com","http://[2001:db8::1]:8080"}) { values["backupPublicUrl"]=url; originJson.Deserialize<LauncherConfig>(originJson.Serialize(values)).ValidateNetwork(scratch); }
                foreach(string url in new[]{"https://47.96.135.179:8080","http://user:pass@47.96.135.179:8080","http://47.96.135.179:8080/path","http://47.96.135.179:8080?","http://47.96.135.179:8080#","http://*.example.com:8080","http://47.96.135.179:0","http://47.96.135.179:65536","http://47.96.135.179:","http://47.96.135.179:8080//"," http://47.96.135.179:8080","http://47.96.135.179:8080 ","http://47.96.135.179:\t8080","http://47.96.135.179:8080\r\n","http://47.96.135.179:8080\0","http://47.96.135.179:8080/..","http://47.96.135.179:8080/%2e","http://47.96.135.179:8080\\","http://backup..example.com:8080","http://warehouse-sim.iyunquna.com","http://warehouse-sim.iyunquna.com:80"}) { values["backupPublicUrl"]=url; LauncherConfig c=originJson.Deserialize<LauncherConfig>(originJson.Serialize(values)); Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);}); }
                values["backupPublicUrl"]="http://47.96.135.179:8080";
                values["externalTlsTermination"]=false; Throws<ArgumentException>(delegate {originJson.Deserialize<LauncherConfig>(originJson.Serialize(values)).ValidateNetwork(scratch);});
                values["externalTlsTermination"]=true; values["networkMode"]="lan"; Throws<ArgumentException>(delegate {originJson.Deserialize<LauncherConfig>(originJson.Serialize(values)).ValidateNetwork(scratch);});
                values["networkMode"]="public"; values["publicUrl"]="http://warehouse-sim.iyunquna.com"; Throws<ArgumentException>(delegate {originJson.Deserialize<LauncherConfig>(originJson.Serialize(values)).ValidateNetwork(scratch);});
            });
            Test("GUI backup entry persists through main settings and mode changes cannot silently enable it",delegate {
                BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; LauncherConfig c=Config(); c.networkMode="public"; c.publicUrl="https://warehouse-sim.iyunquna.com"; c.externalTlsTermination=true;
                using(PublicSettingsForm form=new PublicSettingsForm(scratch,c)) {
                    FieldInfo f=typeof(PublicSettingsForm).GetField("backupAddress",flags); Assert(f!=null,"Backup address input missing"); TextBox backup=(TextBox)f.GetValue(form); Assert(backup.Enabled,"ALB backup input is disabled"); backup.Text="http://47.96.135.179:8080"; LauncherConfig saved=form.Read(); saved.ValidateNetwork(scratch);
                    using(MainForm main=new MainForm()) { typeof(MainForm).GetMethod("ApplyAccessSettings",flags).Invoke(main,new object[]{saved}); LauncherConfig roundtrip=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(main,null); Assert((string)ConfigValues(roundtrip)["backupPublicUrl"]==backup.Text,"Main form dropped backup origin"); Assert(((Label)typeof(MainForm).GetField("networkSummary",flags).GetValue(main)).Text.Contains("备用"),"Dual entry not visible in main summary"); }
                    ((ComboBox)typeof(PublicSettingsForm).GetField("tlsMode",flags).GetValue(form)).SelectedIndex=0; Assert(!backup.Enabled,"Non-ALB mode left backup input enabled"); Assert((string)ConfigValues(form.Read())["backupPublicUrl"]=="","Non-ALB mode transmitted a stale backup");
                    ((ComboBox)typeof(PublicSettingsForm).GetField("tlsMode",flags).GetValue(form)).SelectedIndex=3; Assert(backup.Text=="","Reenabling ALB silently reactivated backup"); backup.Text="http://47.96.135.179:\t8080"; Throws<ArgumentException>(delegate {form.Read().ValidateNetwork(scratch);});
                }
            });
            Test("cloud HTTPS termination accepts private HTTP backhaul and survives configuration save and clone",delegate {
                JavaScriptSerializer serializer=new JavaScriptSerializer(); Dictionary<string,object> values=ConfigValues(Config());
                values["networkMode"]="public"; values["publicUrl"]="https://warehouse-sim.iyunquna.com"; values["accessCode"]="fixture-only-cloud-code"; values["externalTlsTermination"]=true;
                LauncherConfig cloud=serializer.Deserialize<LauncherConfig>(serializer.Serialize(values)); cloud.ValidateNetwork(scratch);
                string file=Path.Combine(scratch,"cloud.json"); cloud.Save(file); LauncherConfig restored=LauncherConfig.Load(file).Clone(); Dictionary<string,object> actual=ConfigValues(restored);
                Assert(actual.ContainsKey("externalTlsTermination") && (bool)actual["externalTlsTermination"],"Cloud HTTPS mode was dropped during save or clone");
                Assert(!restored.trustProxy && restored.tlsCertPath=="" && restored.publicUrl=="https://warehouse-sim.iyunquna.com","Cloud mode changed local proxy or public origin");
            });
            Test("public defaults, bounds and local configuration roundtrip",delegate { LauncherConfig c=Config(); Assert(c.maxViewers==5,"Default capacity is not five"); c.networkMode="public"; c.publicUrl="http://198.51.100.20:8080"; c.accessProtectionEnabled=true; c.accessCode="test-only-code-12345"; c.turnUrl="turn:relay.example.com:3478?transport=udp"; c.turnUsername="test-user"; c.turnPassword="test-password"; c.Validate(scratch,false); string file=Path.Combine(scratch,"public.json"); c.Save(file); LauncherConfig restored=LauncherConfig.Load(file); Assert(restored.publicUrl==c.publicUrl && restored.accessCode==c.accessCode && restored.turnPassword==c.turnPassword && restored.maxViewers==5,"Public fields lost"); c.maxViewers=6; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); c.maxViewers=5; c.accessCode="short"; Throws<ArgumentException>(delegate {c.Validate(scratch,false);}); });
            Test("legacy six-to-ten visitor limits migrate to five without losing unrelated settings",delegate {
                string file=Path.Combine(scratch,"legacy-capacity.json");
                foreach(int limit in new[]{1,5,6,7,10}) {
                    File.WriteAllText(file,"{\"maxViewers\":"+limit+",\"mode\":\"independent\",\"warmStandbyEnabled\":true,\"accessCode\":\"fixture-existing-code\",\"width\":2560}");
                    LauncherConfig c=LauncherConfig.Load(file); c.ValidateNetwork(scratch); Assert(c.maxViewers==(limit>5?5:limit) && c.warmStandbyEnabled && c.width==2560 && c.accessCode=="fixture-existing-code","Capacity migration changed the wrong fields");
                    c.Save(file); Assert(LauncherConfig.Load(file).Clone().maxViewers==c.maxViewers,"Migrated capacity did not persist");
                }
                foreach(int invalid in new[]{0,-1,11}) { File.WriteAllText(file,"{\"maxViewers\":"+invalid+"}"); LauncherConfig c=LauncherConfig.Load(file); Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);}); }
                using(PublicSettingsForm form=new PublicSettingsForm(scratch,Config())) {
                    NumericUpDown capacity=(NumericUpDown)typeof(PublicSettingsForm).GetField("capacity",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(form);
                    Assert(capacity.Minimum==1 && capacity.Maximum==5 && capacity.Value==5,"Capacity UI allows more than five visitors"); capacity.Value=3; Assert(form.Read().maxViewers==3,"Capacity selection was not saved");
                }
            });
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
                c.accessProtectionEnabled=true; c.accessCode="short"; Throws<ArgumentException>(delegate {c.ValidateNetwork(scratch);});
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
            Test("degraded status shows an amber warning and backend explanation",delegate { using(MainForm form=new MainForm()) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; typeof(MainForm).GetMethod("ApplyStatus",flags).Invoke(form,new object[]{new ServiceStatus {state="degraded",message="实例启动失败，请检查显卡。",viewerCount=1,maxViewers=5,instances=new[]{new InstanceStatus {id="viewer-1",state="failed"}},viewers=new ViewerStatus[0]}}); Label status=(Label)typeof(MainForm).GetField("status",flags).GetValue(form),message=(Label)typeof(MainForm).GetField("healthMessage",flags).GetValue(form); Assert(status.Text=="部分实例异常" && status.ForeColor==LauncherTheme.Amber,"Degraded service presented as healthy"); Assert(message.Text.Contains("实例启动失败"),"Backend explanation was hidden"); ListView instances=(ListView)typeof(MainForm).GetField("instances",flags).GetValue(form); Assert(instances.Items[0].SubItems[1].Text=="异常","Failed instance state remained untranslated"); } });
            Test("real status JSON preserves queued null PID and renders a waiting process hint",delegate {
                ServiceStatus parsed=new JavaScriptSerializer().Deserialize<ServiceStatus>(QueuedStatusJson);
                Assert(parsed.instances[0].pid==12345 && (object)parsed.instances[1].pid==null,"Status JSON lost numeric or absent PID semantics");
                using(MainForm form=new MainForm()) {
                    BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic;
                    typeof(MainForm).GetMethod("ApplyStatus",flags).Invoke(form,new object[]{parsed});
                    ListView list=(ListView)typeof(MainForm).GetField("instances",flags).GetValue(form);
                    Assert(list.Items[0].ToolTipText.StartsWith("PID 12345 ·"),"An allocated PID tooltip changed");
                    Assert(list.Items[1].ToolTipText.StartsWith("PID 等待分配 ·") && list.Items[1].SubItems[1].Text=="排队中","Queued instance did not explain its absent PID");
                    Assert(((Label)typeof(MainForm).GetField("status",flags).GetValue(form)).Text=="✓  服务运行中","Queued status displayed a service error");
                }
            });
            Test("four authenticated ReadStatus polls tolerate queued null PID without stopping service",AssertQueuedStatusPolling);
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
            Test("legacy default bitrate is preserved as custom without changing other settings",delegate { string p=Path.Combine(scratch,"legacy-default.json"); File.WriteAllText(p,"{\"executablePath\":\"App/中文 仓库.exe\",\"httpPort\":8091,\"streamerPort\":8891,\"width\":2560,\"height\":1440,\"mode\":\"independent\",\"fps\":60,\"showWindow\":true,\"minBitrateMbps\":8,\"startBitrateMbps\":20,\"maxBitrateMbps\":35}"); LauncherConfig c=LauncherConfig.Load(p); Assert(c.minBitrateMbps==8 && c.startBitrateMbps==20 && c.maxBitrateMbps==35,"Legacy explicit bitrate was replaced"); Assert(c.width==2560 && c.height==1440 && c.mode=="independent" && c.httpPort==8091 && c.streamerPort==8891 && c.executablePath=="App/中文 仓库.exe" && c.showWindow,"Unrelated settings changed during migration"); Dictionary<string,object> v=ConfigValues(c); Assert(v.ContainsKey("qualityProfile") && (string)v["qualityProfile"]=="custom","Legacy explicit budget was not labelled custom"); Assert(v.ContainsKey("adaptiveResourceBudget") && (bool)v["adaptiveResourceBudget"],"Adaptive resource budget did not default on"); });
            Test("legacy custom bitrate survives migration and another save-load cycle",delegate { string p=Path.Combine(scratch,"legacy-custom.json"); File.WriteAllText(p,"{\"minBitrateMbps\":10,\"startBitrateMbps\":27,\"maxBitrateMbps\":48,\"fps\":45}"); LauncherConfig c=LauncherConfig.Load(p); c.Save(p); LauncherConfig d=LauncherConfig.Load(p); Assert(d.minBitrateMbps==10 && d.startBitrateMbps==27 && d.maxBitrateMbps==48 && d.fps==45,"Custom bitrate or FPS was replaced"); Dictionary<string,object> v=ConfigValues(d); Assert(v.ContainsKey("qualityProfile") && (string)v["qualityProfile"]=="custom","Custom bitrate not labelled custom"); });
            Test("explicit balanced quality and disabled resource budget survive reopening",delegate { string p=Path.Combine(scratch,"balanced.json"); File.WriteAllText(p,"{\"qualityProfile\":\"balanced\",\"adaptiveResourceBudget\":false,\"minBitrateMbps\":8,\"startBitrateMbps\":20,\"maxBitrateMbps\":35}"); LauncherConfig c=LauncherConfig.Load(p); c.Save(p); LauncherConfig d=LauncherConfig.Load(p); Assert(d.minBitrateMbps==8 && d.startBitrateMbps==20 && d.maxBitrateMbps==35,"Explicit balanced quality was migrated again"); Dictionary<string,object> v=ConfigValues(d); Assert(v.ContainsKey("adaptiveResourceBudget") && !(bool)v["adaptiveResourceBudget"],"Disabled resource budget was lost"); });
            Test("unsupported quality profile is rejected before service launch",delegate { string p=Path.Combine(scratch,"invalid-quality.json"); Dictionary<string,object> v=ConfigValues(Config()); v["qualityProfile"]="unlimited"; File.WriteAllText(p,new JavaScriptSerializer().Serialize(v)); LauncherConfig c=LauncherConfig.Load(p); Throws<ArgumentException>(delegate { c.Validate(scratch,false); }); });
            Test("GUI quality choices affect encoder budget but preserve render dimensions and FPS",delegate { using(MainForm form=new MainForm()) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; FieldInfo qualityField=typeof(MainForm).GetField("quality",flags); Assert(qualityField!=null,"Quality selector is missing"); ComboBox quality=(ComboBox)qualityField.GetValue(form); ((NumericUpDown)typeof(MainForm).GetField("renderWidth",flags).GetValue(form)).Value=2560; ((NumericUpDown)typeof(MainForm).GetField("renderHeight",flags).GetValue(form)).Value=1440; int[][] budgets={new[]{1,8,24},new[]{1,10,35},new[]{1,16,50}}; for(int i=0;i<budgets.Length;i++) { quality.SelectedIndex=i; LauncherConfig c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); Assert(c.minBitrateMbps==budgets[i][0] && c.startBitrateMbps==budgets[i][1] && c.maxBitrateMbps==budgets[i][2],"Preset did not reach backend configuration"); Assert(c.width==2560 && c.height==1440 && c.fps==60,"Quality selector modified dimensions or target FPS"); } } });
            Test("GUI resource budget toggle reaches configuration for either scene mode",delegate { using(MainForm form=new MainForm()) { BindingFlags flags=BindingFlags.Instance|BindingFlags.NonPublic; ((CheckBox)typeof(MainForm).GetField("fixedFps",flags).GetValue(form)).Checked=false; CheckBox adaptive=(CheckBox)typeof(MainForm).GetField("adaptiveResources",flags).GetValue(form); ComboBox sceneMode=(ComboBox)typeof(MainForm).GetField("mode",flags).GetValue(form); for(int modeIndex=0;modeIndex<2;modeIndex++) { sceneMode.SelectedIndex=modeIndex; foreach(bool enabled in new[]{false,true}) { adaptive.Checked=enabled; LauncherConfig c=(LauncherConfig)typeof(MainForm).GetMethod("ReadSettings",flags).Invoke(form,null); Assert((bool)ConfigValues(c)["adaptiveResourceBudget"]==enabled,"Resource budget selection did not reach backend"); Assert(c.mode==(modeIndex==0?"shared":"independent"),"Resource budget selection changed scene mode"); } } } });
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
                        foreach(string field in new[]{"executable","httpPort","streamerPort","renderWidth","renderHeight","showWindow","mode","quality","adaptiveResources","accessProtection","publicSettings"}) Assert(!((Control)typeof(MainForm).GetField(field,flags).GetValue(form)).Enabled,"Running setting remains enabled: "+field);
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
            Test("authenticated status, duplicate start, repeat stop and restart",delegate { string root=FixtureRoot(); using(ServiceSession session=new ServiceSession(root)) { LauncherConfig c=FixtureConfig(); session.Start(c); ServiceStatus status=session.ReadStatus(); Assert(session.State=="running" && status.mode==c.mode && status.maxViewers==5,"No authenticated running status"); Throws<InvalidOperationException>(delegate { session.Start(c); }); session.Stop(); session.Stop(); Assert(session.State=="idle","Stop did not restore idle"); session.Start(c); session.Stop(); } });
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
