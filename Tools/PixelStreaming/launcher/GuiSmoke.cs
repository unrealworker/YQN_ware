using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Web.Script.Serialization;
using System.Windows.Forms;
namespace Ghs.PixelStreaming
{
    // Offscreen presentation fixtures. Runtime samples below are not live service telemetry.
    internal static class GuiSmoke
    {
        private static readonly BindingFlags Private=BindingFlags.Instance|BindingFlags.NonPublic;
        private static object Field(MainForm form,string name) { return typeof(MainForm).GetField(name,Private).GetValue(form); }
        private static void Set(MainForm form,string name,object value) { typeof(MainForm).GetField(name,Private).SetValue(form,value); }
        private static void Call(MainForm form,string name,params object[] args) { typeof(MainForm).GetMethod(name,Private).Invoke(form,args); }
        private static int FreePort() { TcpListener listener=new TcpListener(IPAddress.Any,0); listener.Start(); int value=((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop(); return value; }
        private static void Capture(MainForm form,string path,List<object> captures)
        {
            form.PerformLayout(); Application.DoEvents();
            Panel footer=(Panel)Field(form,"footer"); Button start=(Button)Field(form,"start"),stop=(Button)Field(form,"stop");
            bool actionsVisible=form.ClientRectangle.Contains(footer.Bounds) && footer.ClientRectangle.Contains(start.Bounds) && footer.ClientRectangle.Contains(stop.Bounds);
            if(!actionsVisible) throw new InvalidOperationException("Launcher start/stop actions extend outside the visible window: "+path);
            using(Bitmap image=new Bitmap(form.Width,form.Height)) { form.DrawToBitmap(image,new Rectangle(Point.Empty,image.Size)); image.Save(path,ImageFormat.Png); }
            captures.Add(new {file=Path.GetFileName(path),width=form.Width,height=form.Height,footerActionsVisible=actionsVisible,bodyScrolls=((Panel)Field(form,"body")).VerticalScroll.Visible});
        }
        public static int Run(string imagePath)
        {
            string absolute=Path.GetFullPath(imagePath),directory=Path.GetDirectoryName(absolute),stem=Path.GetFileNameWithoutExtension(absolute); Directory.CreateDirectory(directory); List<object> captures=new List<object>();
            using(MainForm form=new MainForm())
            {
                ((Timer)Field(form,"timer")).Stop(); form.ShowInTaskbar=false; form.StartPosition=FormStartPosition.Manual; form.Location=new Point(-30000,-30000); form.Show(); Application.DoEvents();
                Capture(form,absolute,captures); Size regular=form.ClientSize;
                ((ComboBox)Field(form,"mode")).SelectedIndex=1;
                ((Button)Field(form,"advanced")).PerformClick(); Capture(form,Path.Combine(directory,stem+"-advanced.png"),captures); ((Button)Field(form,"advanced")).PerformClick(); ((Panel)Field(form,"body")).AutoScrollPosition=Point.Empty;
                TcpListener owner=new TcpListener(IPAddress.Any,0); owner.ExclusiveAddressUse=true; owner.Start();
                try { ((NumericUpDown)Field(form,"httpPort")).Value=((IPEndPoint)owner.LocalEndpoint).Port; ((NumericUpDown)Field(form,"streamerPort")).Value=FreePort(); Call(form,"CheckPorts"); Capture(form,Path.Combine(directory,stem+"-port-conflict.png"),captures); }
                finally { owner.Stop(); }
                ((NumericUpDown)Field(form,"httpPort")).Value=8080; ((NumericUpDown)Field(form,"streamerPort")).Value=8888;
                Set(form,"startBusy",true); Call(form,"SetStatus","◌  正在启动服务",LauncherTheme.Blue); Call(form,"UpdateControls"); Capture(form,Path.Combine(directory,stem+"-starting.png"),captures); Set(form,"startBusy",false);
                ServiceSession session=(ServiceSession)Field(form,"session"); typeof(ServiceSession).GetField("state",Private).SetValue(session,"running");
                Call(form,"ApplyStatus",new ServiceStatus {state="running",mode="independent",viewerCount=2,maxViewers=3,instances=new[]{new InstanceStatus {id="会话 01",pid=12001,state="connected",targetFps=30,actualFps=29.7},new InstanceStatus {id="会话 02",pid=12002,state="connected",targetFps=30,actualFps=null}},urls=new[]{"http://192.168.1.20:8080"},logs=new[]{"界面检查样例：第 4 位访问者进入，已通知并断开最早访问者。"}});
                Capture(form,Path.Combine(directory,stem+"-running.png"),captures);
                Size originalMinimum=form.MinimumSize; form.MinimumSize=MainForm.FitWindowToWorkArea(new Size(1000,720),1.5F,new Size(1920,1032)); form.ClientSize=MainForm.FitWindowToWorkArea(new Size(1200,900),1.5F,new Size(1920,1032));
                Capture(form,Path.Combine(directory,stem+"-1080p-150pct.png"),captures);
                if(!((Panel)Field(form,"body")).VerticalScroll.Visible) throw new InvalidOperationException("1080p at 150 percent must scroll the body while keeping actions visible.");
                form.MinimumSize=originalMinimum; form.ClientSize=regular;
                form.ClientSize=form.MinimumSize; Capture(form,Path.Combine(directory,stem+"-compact.png"),captures); form.ClientSize=regular;
                Call(form,"ToggleLogs"); Capture(form,Path.Combine(directory,stem+"-logs.png"),captures); Call(form,"ToggleLogs");
                Set(form,"stopBusy",true); Call(form,"SetStatus","◌  正在停止服务",LauncherTheme.Muted); Call(form,"UpdateControls"); Capture(form,Path.Combine(directory,stem+"-stopping.png"),captures);
                Set(form,"stopBusy",false); Set(form,"onlineViewers",0); typeof(ServiceSession).GetField("state",Private).SetValue(session,"idle");
                form.Close(); Application.DoEvents();
            }
            File.WriteAllText(Path.Combine(directory,stem+"-report.json"),new JavaScriptSerializer().Serialize(new {fixtureOnly=true,capturedAt=DateTime.UtcNow.ToString("o"),captures=captures})); return 0;
        }
    }
}
