using System;
using System.Collections;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace Ghs.PixelStreaming
{
    // The child is assigned while suspended. It cannot create an unowned descendant.
    public sealed class OwnedProcess : IDisposable
    {
        private IntPtr job;
        private IntPtr process;
        public int Id { get; private set; }
        public bool HasExited { get { return process==IntPtr.Zero || Native.WaitForSingleObject(process,0)==0; } }
        public bool WaitForExit(int timeout) { return process==IntPtr.Zero || Native.WaitForSingleObject(process,(uint)timeout)==0; }
        public static string QuoteArgument(string value)
        {
            if(value==null) value="";
            StringBuilder result=new StringBuilder("\""); int slashes=0;
            foreach(char ch in value) { if(ch=='\\') { slashes++; continue; } if(ch=='\"') { result.Append('\\',slashes*2+1); result.Append(ch); slashes=0; continue; } result.Append('\\',slashes); slashes=0; result.Append(ch); }
            result.Append('\\',slashes*2); result.Append('"'); return result.ToString();
        }
        public static OwnedProcess Start(string exe, string[] args, string cwd, IDictionary<string,string> env, string log)
        {
            OwnedProcess owner=new OwnedProcess(); Native.PROCESS_INFORMATION info=new Native.PROCESS_INFORMATION();
            IntPtr environment=IntPtr.Zero; IntPtr stdout=IntPtr.Zero; IntPtr stdin=IntPtr.Zero;
            try
            {
                owner.job=Native.CreateJobObject(IntPtr.Zero,null); Check(owner.job!=IntPtr.Zero);
                Native.JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits=new Native.JOBOBJECT_EXTENDED_LIMIT_INFORMATION(); limits.BasicLimitInformation.LimitFlags=0x2000; // KILL_ON_JOB_CLOSE
                Check(Native.SetInformationJobObject(owner.job,9,ref limits,(uint)Marshal.SizeOf(limits)));
                var vars=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);
                foreach(DictionaryEntry e in Environment.GetEnvironmentVariables()) vars[(string)e.Key]=(string)e.Value;
                if(env!=null) foreach(var e in env) vars[e.Key]=e.Value;
                StringBuilder block=new StringBuilder(); foreach(var e in vars) block.Append(e.Key).Append('=').Append(e.Value).Append('\0'); block.Append('\0');
                environment=Marshal.StringToHGlobalUni(block.ToString());
                Native.SECURITY_ATTRIBUTES security=new Native.SECURITY_ATTRIBUTES(); security.nLength=Marshal.SizeOf(security); security.bInheritHandle=true;
                stdout=Native.CreateFile(log,0x40000000,3,ref security,2,0x80,IntPtr.Zero); Check(stdout!=new IntPtr(-1));
                stdin=Native.CreateFile("NUL",0x80000000,3,ref security,3,0x80,IntPtr.Zero); Check(stdin!=new IntPtr(-1));
                Native.STARTUPINFO startup=new Native.STARTUPINFO(); startup.cb=Marshal.SizeOf(startup); startup.dwFlags=0x100; startup.hStdOutput=stdout; startup.hStdError=stdout; startup.hStdInput=stdin;
                StringBuilder command=new StringBuilder(QuoteArgument(exe)); foreach(string arg in args) command.Append(' ').Append(QuoteArgument(arg));
                // CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW
                Check(Native.CreateProcess(exe,command,IntPtr.Zero,IntPtr.Zero,true,0x08000404,environment,cwd,ref startup,out info));
                owner.process=info.hProcess; owner.Id=(int)info.dwProcessId;
                Check(Native.AssignProcessToJobObject(owner.job,info.hProcess));
                Check(Native.ResumeThread(info.hThread)!=uint.MaxValue);
                return owner;
            }
            catch { if(info.hProcess!=IntPtr.Zero) { Native.TerminateProcess(info.hProcess,1); Native.WaitForSingleObject(info.hProcess,2000); } owner.Dispose(); throw; }
            finally { Close(info.hThread); Close(stdout); Close(stdin); if(environment!=IntPtr.Zero) Marshal.FreeHGlobal(environment); }
        }
        private static void Check(bool ok) { if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        private static void Close(IntPtr value) { if(value!=IntPtr.Zero && value!=new IntPtr(-1)) Native.CloseHandle(value); }
        public void Dispose() { Close(job); job=IntPtr.Zero; if(process!=IntPtr.Zero) Native.WaitForSingleObject(process,2000); Close(process); process=IntPtr.Zero; }
        private static class Native
        {
            [StructLayout(LayoutKind.Sequential)] internal struct SECURITY_ATTRIBUTES { internal int nLength; internal IntPtr lpSecurityDescriptor; [MarshalAs(UnmanagedType.Bool)] internal bool bInheritHandle; }
            [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] internal struct STARTUPINFO { internal int cb; internal string lpReserved; internal string lpDesktop; internal string lpTitle; internal uint dwX,dwY,dwXSize,dwYSize,dwXCountChars,dwYCountChars,dwFillAttribute,dwFlags; internal ushort wShowWindow,cbReserved2; internal IntPtr lpReserved2,hStdInput,hStdOutput,hStdError; }
            [StructLayout(LayoutKind.Sequential)] internal struct PROCESS_INFORMATION { internal IntPtr hProcess,hThread; internal uint dwProcessId,dwThreadId; }
            [StructLayout(LayoutKind.Sequential)] internal struct JOBOBJECT_BASIC_LIMIT_INFORMATION { internal long PerProcessUserTimeLimit,PerJobUserTimeLimit; internal uint LimitFlags; internal UIntPtr MinimumWorkingSetSize,MaximumWorkingSetSize; internal uint ActiveProcessLimit; internal UIntPtr Affinity; internal uint PriorityClass,SchedulingClass; }
            [StructLayout(LayoutKind.Sequential)] internal struct IO_COUNTERS { internal ulong ReadOperationCount,WriteOperationCount,OtherOperationCount,ReadTransferCount,WriteTransferCount,OtherTransferCount; }
            [StructLayout(LayoutKind.Sequential)] internal struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION { internal JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation; internal IO_COUNTERS IoInfo; internal UIntPtr ProcessMemoryLimit,JobMemoryLimit,PeakProcessMemoryUsed,PeakJobMemoryUsed; }
            [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] internal static extern IntPtr CreateJobObject(IntPtr attributes,string name);
            [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] internal static extern bool SetInformationJobObject(IntPtr job,int type,ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION info,uint length);
            [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] internal static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
            [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] internal static extern bool CreateProcess(string application,StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,[MarshalAs(UnmanagedType.Bool)]bool inherit,uint flags,IntPtr environment,string cwd,ref STARTUPINFO startup,out PROCESS_INFORMATION process);
            [DllImport("kernel32.dll",SetLastError=true)] internal static extern uint ResumeThread(IntPtr thread);
            [DllImport("kernel32.dll",SetLastError=true)] internal static extern uint WaitForSingleObject(IntPtr handle,uint timeout);
            [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] internal static extern bool TerminateProcess(IntPtr process,uint code);
            [DllImport("kernel32.dll")] [return:MarshalAs(UnmanagedType.Bool)] internal static extern bool CloseHandle(IntPtr handle);
            [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] internal static extern IntPtr CreateFile(string file,uint access,uint share,ref SECURITY_ATTRIBUTES security,uint disposition,uint flags,IntPtr template);
        }
    }
}
