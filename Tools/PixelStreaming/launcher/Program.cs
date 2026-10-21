using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;
namespace Ghs.PixelStreaming
{
    internal static class Program
    {
        [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();
        [STAThread] public static int Main(string[] args)
        {
            if(args.Length>0 && args[0].EndsWith("server.js",StringComparison.OrdinalIgnoreCase)) return BackendFixture.Run(args);
            if(args.Length>0 && args[0]=="--test-worker") return SelfTests.Worker(args);
            if(args.Length>0 && args[0]=="--self-test") return SelfTests.Run(args.Length>1?args[1]:Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"logs","launcher-selftest.json"));
            SetProcessDPIAware(); Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            if(args.Length>0 && args[0]=="--gui-smoke") return GuiSmoke.Run(args.Length>1?args[1]:Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"logs","launcher-preview.png"));
            try { using(MainForm form=new MainForm()) Application.Run(form); return 0; }
            catch(Exception ex) { MessageBox.Show("启动器无法运行："+ex.Message,"像素流服务启动器",MessageBoxButtons.OK,MessageBoxIcon.Error); return 1; }
        }
    }
}
