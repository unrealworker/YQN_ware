using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
namespace Ghs.PixelStreaming
{
    // A small IPC fixture, used only by TestProgram or the explicit --self-test route.
    internal static class BackendFixture
    {
        public static int Run(string[] args)
        {
            string root=Environment.CurrentDirectory; File.WriteAllText(Path.Combine(root,"starting.pid"),Process.GetCurrentProcess().Id.ToString());
            if(File.Exists(Path.Combine(root,"fail-start"))) return 7;
            if(File.Exists(Path.Combine(root,"delay-start"))) { Thread.Sleep(60000); return 0; }
            LauncherConfig config=LauncherConfig.Load(args[2]); string control=args[4]; string token=Environment.GetEnvironmentVariable("GHS_CONTROL_TOKEN");
            TcpListener listener=new TcpListener(IPAddress.Loopback,0); listener.Start(); int port=((IPEndPoint)listener.LocalEndpoint).Port;
            File.WriteAllText(control,new JavaScriptSerializer().Serialize(new {controlPort=port,pid=File.Exists(Path.Combine(root,"wrong-pid"))?1:Process.GetCurrentProcess().Id,httpPort=config.httpPort,streamerPort=config.streamerPort}));
            bool stop=false;
            while(!stop)
            {
                using(TcpClient client=listener.AcceptTcpClient()) using(NetworkStream stream=client.GetStream()) using(StreamReader reader=new StreamReader(stream,Encoding.ASCII,false,1024,true))
                {
                    string first=reader.ReadLine(); string line; bool authorized=false;
                    while(!string.IsNullOrEmpty(line=reader.ReadLine())) if(line=="Authorization: Bearer "+token && !string.IsNullOrEmpty(token)) authorized=true;
                    stop=authorized && first.StartsWith("POST /stop ");
                    string body=authorized?new JavaScriptSerializer().Serialize(new { state="running",message="fixture",mode=config.mode,viewerCount=0,maxViewers=3,instances=new object[0],urls=new[]{"http://127.0.0.1:"+config.httpPort},logs=new[]{"fixture ready"} }):"{}";
                    byte[] payload=Encoding.UTF8.GetBytes(body); byte[] header=Encoding.ASCII.GetBytes("HTTP/1.1 "+(authorized?"200 OK":"401 Unauthorized")+"\r\nContent-Type: application/json\r\nContent-Length: "+payload.Length+"\r\nConnection: close\r\n\r\n"); stream.Write(header,0,header.Length); stream.Write(payload,0,payload.Length);
                }
            }
            listener.Stop(); return 0;
        }
    }
}
