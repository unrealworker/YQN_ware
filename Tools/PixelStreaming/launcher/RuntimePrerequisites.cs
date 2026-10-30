using System;
using System.Diagnostics;
using System.IO;
using System.Linq;

namespace Ghs.PixelStreaming
{
    internal static class RuntimePrerequisites
    {
        internal static readonly string[] RequiredFiles={"Install-RuntimeDependencies.ps1","App/Windows/Engine/Extras/Redist/en-us/vc_redist.x64.exe","App/Windows/Engine/Extras/Redist/en-us/GameInputRedist.msi"};
        internal static string[] MissingFiles(string root) { return RequiredFiles.Where(file=>!File.Exists(Path.Combine(root,file))).ToArray(); }
        internal static ProcessStartInfo CreateInstaller(string root)
        {
            string[] missing=MissingFiles(root); if(missing.Length>0) throw new FileNotFoundException("UE5.8 运行组件安装文件不完整："+string.Join("、",missing));
            string script=Path.Combine(Path.GetFullPath(root),RequiredFiles[0]);
            return new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell","v1.0","powershell.exe"),"-NoProfile -ExecutionPolicy Bypass -File "+OwnedProcess.QuoteArgument(script)) {UseShellExecute=true,Verb="runas",WindowStyle=ProcessWindowStyle.Hidden,WorkingDirectory=Path.GetFullPath(root)};
        }
    }
}
