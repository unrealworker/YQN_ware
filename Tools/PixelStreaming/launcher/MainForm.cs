using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;
namespace Ghs.PixelStreaming
{
    internal sealed class MainForm : Form
    {
        private static readonly Color Navy=LauncherTheme.Navy,Muted=LauncherTheme.Muted,Blue=LauncherTheme.Blue;
        private readonly string root=AppDomain.CurrentDomain.BaseDirectory;
        private readonly ServiceSession session;
        private readonly Panel settings=new Panel();
        private readonly TextBox executable=new TextBox();
        private readonly NumericUpDown httpPort=Number(1024,65535,8080),streamerPort=Number(1024,65535,8888),renderWidth=Number(320,7680,1920),renderHeight=Number(320,7680,1080);
        private readonly NumericUpDown fpsLimit=Number(15,120,60),minBitrate=Number(1,200,12),startBitrate=Number(1,200,35),maxBitrate=Number(1,200,60);
        private readonly CheckBox showWindow=new ToggleCheckBox(),adaptiveResources=new ToggleCheckBox();
        private readonly ComboBox mode=new ComboBox(),quality=new ComboBox(),urls=new ComboBox();
        private readonly Label modeHint=new Label(),qualityHint=new Label(),resolutionHint=new Label(),status=new Label(),viewers=new Label(),portFeedback=new Label(),pathFeedback=new Label();
        private readonly Label pageSubtitle=new Label(),footerHint=new Label(),sessionHint=new Label(),emptyHint=new Label(),sceneMode=new Label();
        private readonly Button start=Button("▷  启动服务",true),stop=Button("□  停止服务",false),probe=Button("重新检测",false),copy=Button("复制",false),open=Button("↗  打开网页",true);
        private readonly Button firewall=LinkButton("配置内网访问"),browse=Button("选择程序",false),sharedMode=Button("○  共享场景",false),independentMode=Button("○  每人独立",false);
        private readonly Button advanced=LinkButton("高级画面参数  ⌄"),logs=LinkButton("▤  服务日志  ⌃"),logsFolder=LinkButton("打开日志目录"),details=LinkButton("查看运行详情与日志 →");
        private readonly ListView instances=new ListView();
        private readonly TextBox log=new TextBox();
        private readonly Timer timer=new Timer();
        private readonly Panel header=new Panel(),body=new Panel(),content=new Panel(),footer=new Panel(),logDrawer=new Panel(),advancedFields=new Panel();
        private readonly RoundedPanel configCard=new RoundedPanel(),monitorCard=new RoundedPanel(),previewFrame=new RoundedPanel();
        private readonly PictureBox preview=new RoundedPictureBox();
        private readonly Dictionary<Control,RoundedPanel> fieldHosts=new Dictionary<Control,RoundedPanel>();
        private readonly List<Control> configLabels=new List<Control>();
        private readonly Label sectionTitle=new Label(),sceneTitle=new Label(),previewCaption=new Label(),connectionLabel=new Label(),sessionsTitle=new Label(),fpsColumnHint=new Label(),capacityHint=new Label(),hiddenHint=new Label(),adaptiveHint=new Label();
        private readonly Panel divider=new Panel();
        private readonly Button minimize=new Button(),maximize=new Button(),close=new Button();
        private Label pathLabel,httpLabel,streamLabel,resolutionLabel,qualityLabel,modeLabel;
        private bool startBusy,stopBusy,pollBusy,closing,allowClose,stopRequested,portConflict,loadingSettings,layoutBusy;
        private int pollFailures,onlineViewers;
        private string lastBackendLog="";
        private readonly List<string> localLogs=new List<string>();
        private LauncherConfig baseline=new LauncherConfig();
        private float layoutScale=1F;
        [DllImport("user32.dll")] private static extern bool ReleaseCapture();
        [DllImport("user32.dll")] private static extern IntPtr SendMessage(IntPtr hWnd,int msg,IntPtr wParam,IntPtr lParam);
        internal MainForm()
        {
            session=new ServiceSession(root); Text="像素流服务启动器"; BackColor=LauncherTheme.Canvas; ForeColor=Navy;
            Font=new Font("Microsoft YaHei UI",10F); AutoScaleDimensions=new SizeF(96F,96F); AutoScaleMode=AutoScaleMode.Dpi;
            ClientSize=new Size(1200,900); StartPosition=FormStartPosition.Manual;
            FormBorderStyle=FormBorderStyle.None; DoubleBuffered=true; KeyPreview=true; AccessibleName=Text;
            BuildLayout();
            using(Graphics graphics=CreateGraphics()) {
                float dpi=graphics.DpiX/96F; Rectangle workArea=Screen.FromPoint(Cursor.Position).WorkingArea;
                MinimumSize=FitWindowToWorkArea(new Size(1000,720),dpi,workArea.Size);
                ClientSize=FitWindowToWorkArea(new Size(1200,900),dpi,workArea.Size);
                Location=new Point(workArea.Left+(workArea.Width-Width)/2,workArea.Top+(workArea.Height-Height)/2); MaximizedBounds=workArea;
            }
            LoadSettings(); SetStatus("○  服务未启动",Muted); UpdateControls();
            timer.Interval=1000; timer.Tick+=async delegate { await Poll(); }; timer.Start();
            start.Click+=async delegate { await StartService(); }; stop.Click+=async delegate { if(ConfirmStop()) await StopService(); };
            probe.Click+=delegate { CheckPorts(); }; firewall.Click+=delegate { ConfigureFirewall(); };
            copy.Click+=delegate { if(urls.SelectedItem!=null) { try { Clipboard.SetText(urls.SelectedItem.ToString()); AppendLog("访问地址已复制。"); } catch(Exception ex) { ShowError(ex); } } };
            open.Click+=delegate { if(urls.SelectedItem!=null) OpenUrl(urls.SelectedItem.ToString()); };
            mode.SelectedIndexChanged+=delegate { UpdateModeHint(); }; adaptiveResources.CheckedChanged+=delegate { UpdateModeHint(); };
            quality.SelectedIndexChanged+=delegate { UpdateQualityHint(); }; fpsLimit.ValueChanged+=delegate { UpdateModeHint(); UpdateQualityHint(); };
            httpPort.ValueChanged+=delegate { ClearPortFeedback(); }; streamerPort.ValueChanged+=delegate { ClearPortFeedback(); };
            executable.TextChanged+=delegate { pathFeedback.Text=""; SetFieldError(executable,false); };
            FormClosing+=OnClosing; FormClosed+=delegate { timer.Stop(); timer.Dispose(); session.Dispose(); if(preview.Image!=null) preview.Image.Dispose(); };
        }
        internal static Size FitWindowToWorkArea(Size logicalSize,float scale,Size workArea)
        {
            return new Size(Math.Min(workArea.Width,(int)Math.Round(logicalSize.Width*scale)),Math.Min(workArea.Height,(int)Math.Round(logicalSize.Height*scale)));
        }
        private static NumericUpDown Number(int min,int max,int value) { return new NumericUpDown {Minimum=min,Maximum=max,Value=value,TextAlign=HorizontalAlignment.Left,ThousandsSeparator=false,BorderStyle=BorderStyle.None}; }
        private static Button Button(string text,bool primary) { return new RoundedButton {Text=text,Primary=primary,Height=44,ForeColor=Navy,BackColor=Color.White,TabStop=true}; }
        private static Button LinkButton(string text) { Button b=new Button {Text=text,FlatStyle=FlatStyle.Flat,BackColor=Color.White,ForeColor=Blue,Cursor=Cursors.Hand,TextAlign=ContentAlignment.MiddleLeft}; b.FlatAppearance.BorderSize=0; b.FlatAppearance.MouseOverBackColor=Color.FromArgb(239,244,255); return b; }
        private Label AddLabel(Control parent,string text,float size,bool bold,Color color) { Label label=new Label(); SetupLabel(label,parent,text,size,bold,color); return label; }
        private void SetupLabel(Label label,Control parent,string text,float size,bool bold,Color color) { label.Text=text; label.Font=new Font(Font.FontFamily,size,bold?FontStyle.Bold:FontStyle.Regular); label.ForeColor=color; label.BackColor=Color.Transparent; label.TextAlign=ContentAlignment.MiddleLeft; parent.Controls.Add(label); }
        private RoundedPanel Field(Control field,Control parent,string name)
        {
            RoundedPanel host=new RoundedPanel {BorderColor=LauncherTheme.Border}; fieldHosts.Add(field,host); parent.Controls.Add(host); host.Controls.Add(field);
            field.AccessibleName=name; field.BackColor=Color.White; field.ForeColor=Navy; field.Margin=Padding.Empty;
            if(field is TextBox) ((TextBox)field).BorderStyle=BorderStyle.None;
            if(field is ComboBox) { ((ComboBox)field).FlatStyle=FlatStyle.Flat; ((ComboBox)field).DropDownStyle=ComboBoxStyle.DropDownList; }
            host.Resize+=delegate { int pad=S(12); field.SetBounds(pad,Math.Max(S(6),(host.Height-field.PreferredSize.Height)/2),Math.Max(12,host.Width-pad*2),field.PreferredSize.Height); };
            field.Enter+=delegate { host.BorderColor=Blue; host.Invalidate(); }; field.Leave+=delegate { host.BorderColor=LauncherTheme.Border; host.Invalidate(); }; return host;
        }
        private void BuildLayout()
        {
            header.BackColor=Color.FromArgb(23,34,50); Controls.Add(header);
            AddLabel(header,"◉",23,false,Color.FromArgb(122,164,255)).Name="mark"; Label title=AddLabel(header,Text,14,true,Color.White); title.Name="title";
            header.MouseDown+=DragWindow; title.MouseDown+=DragWindow; header.DoubleClick+=delegate { ToggleMaximize(); }; title.DoubleClick+=delegate { ToggleMaximize(); };
            BuildCaption(minimize,"−","最小化",delegate { WindowState=FormWindowState.Minimized; }); BuildCaption(maximize,"□","最大化或还原",delegate { ToggleMaximize(); }); BuildCaption(close,"×","关闭启动器",delegate { Close(); });
            body.AutoScroll=true; body.BackColor=LauncherTheme.Canvas; Controls.Add(body); body.Controls.Add(content);
            SetupLabel(sectionTitle,content,"服务配置",18,true,Navy); SetupLabel(pageSubtitle,content,"配置流送程序，启动后分享内网地址。",10,false,Muted);
            content.Controls.Add(configCard); content.Controls.Add(monitorCard); configCard.Controls.Add(settings); settings.BackColor=Color.White;
            pathLabel=AddLabel(settings,"流送程序",10,false,Navy); Field(executable,settings,"流送程序路径"); settings.Controls.Add(browse); SetupLabel(pathFeedback,settings,"",9,false,LauncherTheme.Red);
            browse.Click+=delegate { using(OpenFileDialog dialog=new OpenFileDialog {Title="选择已打包的仓库程序",Filter="Windows 程序 (*.exe)|*.exe",CheckFileExists=true}) { try { dialog.InitialDirectory=Path.GetDirectoryName(ReadSettings().ResolveExecutable(root)); } catch {} if(dialog.ShowDialog(this)==DialogResult.OK) executable.Text=dialog.FileName; } };
            showWindow.Text="显示本地程序窗口"; showWindow.AccessibleName=showWindow.Text; showWindow.AccessibleDescription="关闭后仍在后台渲染，网页仍可访问。"; settings.Controls.Add(showWindow); SetupLabel(hiddenHint,settings,"关闭后在后台渲染，网页仍可访问",9,false,Muted);
            httpLabel=AddLabel(settings,"网页端口",10,false,Navy); streamLabel=AddLabel(settings,"串流端口",10,false,Navy); Field(httpPort,settings,"网页端口"); Field(streamerPort,settings,"串流端口"); settings.Controls.Add(probe); SetupLabel(portFeedback,settings,"尚未检测端口 · 启动时自动检查",9,false,Muted);
            resolutionLabel=AddLabel(settings,"流送分辨率",10,false,Navy); qualityLabel=AddLabel(settings,"画面质量",10,false,Navy); Field(renderWidth,settings,"渲染宽度"); Field(renderHeight,settings,"渲染高度"); AddLabel(settings,"×",11,false,Muted).Name="multiply";
            quality.Items.AddRange(new object[]{"流畅优先","清晰优先","超清细节"}); Field(quality,settings,"画面质量"); SetupLabel(resolutionHint,settings,"原生分辨率 · 帧率上限 60 FPS",9,false,Muted); SetupLabel(qualityHint,settings,"12–60 Mbps · 起始 35 Mbps",9,false,Muted);
            modeLabel=AddLabel(settings,"访问模式",10,false,Navy); mode.Items.AddRange(new object[]{"共享场景","每人独立"}); mode.Visible=false; settings.Controls.Add(mode);
            settings.Controls.Add(sharedMode); settings.Controls.Add(independentMode); sharedMode.AccessibleRole=AccessibleRole.RadioButton; independentMode.AccessibleRole=AccessibleRole.RadioButton; sharedMode.Click+=delegate { mode.SelectedIndex=0; }; independentMode.Click+=delegate { mode.SelectedIndex=1; };
            SetupLabel(modeHint,settings,"",9,false,Muted); modeHint.TextAlign=ContentAlignment.TopLeft;
            adaptiveResources.Text="按连接人数自动分配资源"; adaptiveResources.AccessibleName=adaptiveResources.Text; adaptiveResources.AccessibleDescription="独立模式按连接数调整目标帧率，实际帧率取决于负载。"; settings.Controls.Add(adaptiveResources);
            SetupLabel(adaptiveHint,settings,"优先保持清晰度，按实际负载调整目标帧率。",9,false,Muted); settings.Controls.Add(advanced); settings.Controls.Add(advancedFields); advancedFields.Visible=false;
            AddLabel(advancedFields,"帧率上限",9,false,Navy).Name="fpsLabel"; Field(fpsLimit,advancedFields,"帧率上限 FPS"); AddLabel(advancedFields,"最低 Mbps",9,false,Navy).Name="minLabel"; Field(minBitrate,advancedFields,"最低码率 Mbps"); AddLabel(advancedFields,"起始 Mbps",9,false,Navy).Name="startLabel"; Field(startBitrate,advancedFields,"起始码率 Mbps"); AddLabel(advancedFields,"最高 Mbps",9,false,Navy).Name="maxLabel"; Field(maxBitrate,advancedFields,"最高码率 Mbps"); AddLabel(advancedFields,"帧率为上限；实际值取决于场景、显卡与网络。",9,false,Muted).Name="fpsHelp";
            foreach(NumericUpDown value in new[]{minBitrate,startBitrate,maxBitrate}) value.ValueChanged+=delegate { if(loadingSettings) return; EnsureCustomQuality(); quality.SelectedIndex=3; UpdateQualityHint(); };
            advanced.Click+=delegate { advancedFields.Visible=!advancedFields.Visible; advanced.Text=advancedFields.Visible?"收起高级参数  ⌃":"高级画面参数  ⌄"; PerformLayout(); if(advancedFields.Visible) body.AutoScrollPosition=new Point(0,Math.Max(0,S(880)-body.ClientSize.Height)); };
            foreach(Control label in new[]{pathLabel,httpLabel,streamLabel,resolutionLabel,qualityLabel,modeLabel}) configLabels.Add(label);
            monitorCard.Controls.Add(previewFrame); previewFrame.Controls.Add(preview); preview.Dock=DockStyle.Fill; preview.SizeMode=PictureBoxSizeMode.Zoom; preview.BackColor=Color.FromArgb(224,230,237); preview.AccessibleName="GHS 普通仓库场景预览（静态图片）";
            using(Stream stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("Ghs.PixelStreaming.warehouse-overview.png")) { if(stream!=null) using(Image source=Image.FromStream(stream)) preview.Image=new Bitmap(source); }
            SetupLabel(sceneTitle,monitorCard,"GHS · 普通仓库",11,true,Navy); SetupLabel(previewCaption,monitorCard,"场景预览",9,false,Muted); SetupLabel(sceneMode,monitorCard,"",9,false,Muted); divider.BackColor=LauncherTheme.Border; monitorCard.Controls.Add(divider);
            SetupLabel(status,monitorCard,"○  服务未启动",12,true,Navy); SetupLabel(viewers,monitorCard,"0 / 3 在线",9,false,Muted); viewers.TextAlign=ContentAlignment.MiddleRight;
            SetupLabel(emptyHint,monitorCard,"启动后生成内网访问地址",10,false,Muted); SetupLabel(capacityHint,monitorCard,"同一内网的电脑可通过浏览器访问。\r\n第 4 位进入时，将通知并断开最早访问者。",9,false,Muted);
            SetupLabel(connectionLabel,monitorCard,"内网访问地址",9,false,Muted); urls.Font=new Font(Font.FontFamily,9F); urls.DropDownWidth=420; Field(urls,monitorCard,"内网访问地址"); monitorCard.Controls.Add(copy); monitorCard.Controls.Add(open);
            SetupLabel(sessionsTitle,monitorCard,"在线会话",10,true,Navy); SetupLabel(fpsColumnHint,monitorCard,"实际 / 当前目标 FPS",9,false,Muted); fpsColumnHint.TextAlign=ContentAlignment.MiddleRight;
            instances.View=View.Details; instances.FullRowSelect=true; instances.BorderStyle=BorderStyle.None; instances.HeaderStyle=ColumnHeaderStyle.None; instances.Font=new Font(Font.FontFamily,9F); instances.ForeColor=Navy; instances.Columns.Add("实例",100); instances.Columns.Add("状态",80); instances.Columns.Add("实际 / 当前目标 FPS",100,HorizontalAlignment.Right); instances.AccessibleName="实例状态与实际和当前目标帧率"; monitorCard.Controls.Add(instances);
            SetupLabel(sessionHint,monitorCard,"",9,false,Muted); sessionHint.TextAlign=ContentAlignment.TopLeft; monitorCard.Controls.Add(firewall); monitorCard.Controls.Add(logsFolder); monitorCard.Controls.Add(details); logsFolder.Click+=delegate { OpenLogFolder(); }; details.Click+=delegate { ToggleLogs(); };
            footer.BackColor=Color.White; Controls.Add(footer); footer.Controls.Add(logs); footer.Controls.Add(start); footer.Controls.Add(stop); ((RoundedButton)stop).Destructive=true; SetupLabel(footerHint,footer,"启动时自动保存配置",9,false,Muted); footerHint.TextAlign=ContentAlignment.MiddleRight; logs.Click+=delegate { ToggleLogs(); };
            logDrawer.BackColor=Color.White; Controls.Add(logDrawer); logDrawer.Visible=false; AddLabel(logDrawer,"服务日志",11,true,Navy).Name="logTitle";
            log.Multiline=true; log.ReadOnly=true; log.ScrollBars=ScrollBars.Vertical; log.WordWrap=true; log.BorderStyle=BorderStyle.None; log.BackColor=Color.White; log.ForeColor=Muted; log.Font=new Font("Microsoft YaHei UI",9F); log.AccessibleName="服务日志"; logDrawer.Controls.Add(log);
            Button collapse=LinkButton("收起日志  ⌄"); collapse.Name="collapse"; logDrawer.Controls.Add(collapse); collapse.Click+=delegate { ToggleLogs(); }; AcceptButton=start;
        }
        private void BuildCaption(Button button,string text,string name,Action action) { button.Text=text; button.AccessibleName=name; button.Font=new Font("Segoe UI",14F); button.FlatStyle=FlatStyle.Flat; button.FlatAppearance.BorderSize=0; button.BackColor=header.BackColor; button.ForeColor=Color.FromArgb(203,212,225); button.FlatAppearance.MouseOverBackColor=Color.FromArgb(47,61,80); button.TabStop=true; header.Controls.Add(button); button.Click+=delegate { action(); }; }
        private int S(float value) { return (int)Math.Round(value*layoutScale); }
        private void Place(Control control,int x,int y,int w,int h) { if(control!=null) control.SetBounds(S(x),S(y),Math.Max(1,S(w)),Math.Max(1,S(h))); }
        protected override void OnLayout(LayoutEventArgs e)
        {
            base.OnLayout(e); if(layoutBusy || header==null || header.Parent==null || pathLabel==null) return; layoutBusy=true;
            try {
                using(Graphics g=CreateGraphics()) layoutScale=g.DpiX/96F*(Font.SizeInPoints/10F);
                int width=(int)(ClientSize.Width/layoutScale),height=(int)(ClientSize.Height/layoutScale);
                Place(header,0,0,width,56); Place(header.Controls["mark"],24,5,32,46); Place(header.Controls["title"],60,0,width-220,56);
                Place(minimize,width-116,8,36,40); Place(maximize,width-80,8,36,40); Place(close,width-44,8,36,40);
                int drawer=logDrawer.Visible?210:0; Place(footer,0,height-84,width,84); Place(body,0,56,width,Math.Max(100,height-140-drawer));
                int configHeight=advancedFields.Visible?748:616,bodyHeight=Math.Max((int)(body.ClientSize.Height/layoutScale),configHeight+144);
                int available=Math.Max(1000,width)-(configHeight+144>height-140-drawer?(int)Math.Ceiling(SystemInformation.VerticalScrollBarWidth/layoutScale)+2:0);
                body.AutoScrollMinSize=new Size(width<1000?S(1000):0,S(configHeight+144)); content.SetBounds(body.AutoScrollPosition.X,body.AutoScrollPosition.Y,S(available)-1,S(bodyHeight));
                Place(sectionTitle,32,28,available-64,36); Place(pageSubtitle,32,68,available-64,24);
                int gap=32,left=(int)((available-64-gap)*.649F),right=available-64-gap-left;
                Place(configCard,32,112,left,configHeight); Place(settings,24,22,left-48,configHeight-44); Place(monitorCard,32+left+gap,112,right,616);
                LayoutSettings(left-48); LayoutMonitor(right-48);
                Place(logs,32,22,190,40); Place(start,width-188,20,156,44); Place(stop,width-188,20,156,44); Place(footerHint,240,24,width-446,36);
                if(logDrawer.Visible) { Place(logDrawer,0,height-84-drawer,width,drawer); Place(logDrawer.Controls["logTitle"],32,10,width-220,28); Place(logDrawer.Controls["collapse"],width-160,8,128,32); Place(log,32,48,width-64,drawer-60); }
            } finally { layoutBusy=false; }
        }
        private void LayoutSettings(int w)
        {
            if(!fieldHosts.ContainsKey(quality)) return;
            Place(pathLabel,0,0,w,24); Place(fieldHosts[executable],0,28,w-120,44); Place(browse,w-104,28,104,44); Place(pathFeedback,0,73,w,20);
            Place(showWindow,0,90,290,32); Place(hiddenHint,Math.Max(292,w/2),90,w-Math.Max(292,w/2),32);
            int port=(w-32)/3; Place(httpLabel,0,144,port,24); Place(streamLabel,port+16,144,port,24); Place(fieldHosts[httpPort],0,172,port,44); Place(fieldHosts[streamerPort],port+16,172,port,44); Place(probe,(port+16)*2,172,w-(port+16)*2,44); Place(portFeedback,0,220,w,25);
            int half=(w-20)/2; Place(resolutionLabel,0,260,half,24); Place(qualityLabel,half+20,260,half,24); int number=(half-26)/2;
            Place(fieldHosts[renderWidth],0,288,number,44); Place(settings.Controls["multiply"],number+4,288,18,44); Place(fieldHosts[renderHeight],number+26,288,number,44); Place(fieldHosts[quality],half+20,288,half,44);
            Place(resolutionHint,0,338,half,26); Place(qualityHint,half+20,338,half,26);
            Place(modeLabel,0,370,w,24); Place(sharedMode,0,398,half,46); Place(independentMode,half+20,398,half,46); Place(modeHint,0,456,w,38);
            Place(adaptiveResources,0,500,w,32); Place(adaptiveHint,48,534,w-205,30); Place(advanced,w-158,534,158,30);
            if(advancedFields.Visible && fieldHosts.ContainsKey(fpsLimit)) { Place(advancedFields,0,598,w,108); int q=(w-36)/4; string[] names={"fpsLabel","minLabel","startLabel","maxLabel"}; Control[] fields={fpsLimit,minBitrate,startBitrate,maxBitrate}; for(int i=0;i<4;i++) { Place(advancedFields.Controls[names[i]],(q+12)*i,0,q,23); Place(fieldHosts[fields[i]],(q+12)*i,27,q,40); } Place(advancedFields.Controls["fpsHelp"],0,73,w,26); }
        }
        private void LayoutMonitor(int w)
        {
            if(!fieldHosts.ContainsKey(urls)) return;
            bool running=session.State=="running" || startBusy || stopBusy; int x=24;
            if(running) {
                int thumb=Math.Min(144,(int)(w*.38F)); Place(status,x,22,w-74,30); Place(viewers,x+w-74,22,74,30); Place(previewFrame,x,66,thumb,84); Place(sceneTitle,x+thumb+16,70,w-thumb-16,28); Place(sceneMode,x+thumb+16,100,w-thumb-16,24); Place(previewCaption,x+thumb+16,126,w-thumb-16,24); Place(divider,x,166,w,1);
                Place(connectionLabel,x,184,w,24); Place(fieldHosts[urls],x,216,w-70,44); Place(copy,x+w-62,216,62,44); Place(open,x,276,w,44);
                Place(sessionsTitle,x,336,100,26); Place(fpsColumnHint,x+100,336,w-100,26); Place(instances,x,374,w,116);
                if(instances.Columns.Count==3) { instances.Columns[0].Width=S(Math.Max(72,(int)(w*.30F))); instances.Columns[1].Width=S(Math.Max(60,(int)(w*.25F))); instances.Columns[2].Width=S(Math.Max(80,w-(int)(w*.30F)-(int)(w*.25F)-5)); }
                Place(sessionHint,x,510,w,54); Place(details,x,568,w,28);
            } else {
                Place(previewFrame,x,24,w,180); Place(sceneTitle,x,220,w-80,32); Place(previewCaption,x+w-80,220,80,32); Place(divider,x,268,w,1); Place(status,x,286,w,32); Place(emptyHint,x,328,w,28); Place(capacityHint,x,368,w,60); Place(firewall,x,438,116,32); Place(logsFolder,x+120,438,w-120,32);
            }
            viewers.Visible=running; sceneMode.Visible=running; connectionLabel.Visible=running; fieldHosts[urls].Visible=running; copy.Visible=running; open.Visible=running; sessionsTitle.Visible=running; fpsColumnHint.Visible=running; instances.Visible=running; sessionHint.Visible=running; details.Visible=running;
            emptyHint.Visible=!running; capacityHint.Visible=!running; firewall.Visible=!running; logsFolder.Visible=!running; if(!running) monitorCard.Height=S(490);
        }
        private void DragWindow(object sender,MouseEventArgs e) { if(e.Button==MouseButtons.Left) { ReleaseCapture(); SendMessage(Handle,0xA1,(IntPtr)2,IntPtr.Zero); } }
        private void ToggleMaximize() { MaximizedBounds=Screen.FromControl(this).WorkingArea; WindowState=WindowState==FormWindowState.Maximized?FormWindowState.Normal:FormWindowState.Maximized; PerformLayout(); }
        protected override void WndProc(ref Message m)
        {
            base.WndProc(ref m);
            if(m.Msg==0x84 && WindowState==FormWindowState.Normal) { Point p=PointToClient(new Point(unchecked((short)((long)m.LParam&0xffff)),unchecked((short)(((long)m.LParam>>16)&0xffff)))); int edge=S(6); bool left=p.X<edge,right=p.X>=ClientSize.Width-edge,top=p.Y<edge,bottom=p.Y>=ClientSize.Height-edge; if(top && left) m.Result=(IntPtr)13; else if(top && right) m.Result=(IntPtr)14; else if(bottom && left) m.Result=(IntPtr)16; else if(bottom && right) m.Result=(IntPtr)17; else if(left) m.Result=(IntPtr)10; else if(right) m.Result=(IntPtr)11; else if(top) m.Result=(IntPtr)12; else if(bottom) m.Result=(IntPtr)15; }
        }
        private void ToggleLogs() { logDrawer.Visible=!logDrawer.Visible; logs.Text=logDrawer.Visible?"▤  服务日志  ⌄":"▤  服务日志  ⌃"; PerformLayout(); }
        private void OpenLogFolder() { try { string p=Path.Combine(root,"logs"); Directory.CreateDirectory(p); Process.Start(new ProcessStartInfo(p) {UseShellExecute=true}); } catch(Exception ex) { ShowError(ex); } }
        private void LoadSettings()
        {
            loadingSettings=true; try { baseline=LauncherConfig.Load(Path.Combine(root,"launcher.config.json")); } catch(Exception ex) { AppendLog("配置读取失败，已使用默认设置："+ex.Message); }
            executable.Text=baseline.executablePath; httpPort.Value=Clamp(baseline.httpPort,httpPort); streamerPort.Value=Clamp(baseline.streamerPort,streamerPort); renderWidth.Value=Clamp(baseline.width,renderWidth); renderHeight.Value=Clamp(baseline.height,renderHeight); showWindow.Checked=baseline.showWindow; mode.SelectedIndex=baseline.mode=="independent"?1:0;
            fpsLimit.Value=Clamp(baseline.fps,fpsLimit); minBitrate.Value=Clamp(baseline.minBitrateMbps,minBitrate); startBitrate.Value=Clamp(baseline.startBitrateMbps,startBitrate); maxBitrate.Value=Clamp(baseline.maxBitrateMbps,maxBitrate);
            if(baseline.qualityProfile=="custom") { EnsureCustomQuality(); quality.SelectedIndex=3; } else quality.SelectedIndex=baseline.qualityProfile=="balanced"?0:baseline.qualityProfile=="ultra"?2:1;
            adaptiveResources.Checked=baseline.adaptiveResourceBudget; loadingSettings=false; UpdateModeHint(); UpdateQualityHint(); AppendLog("请选择程序并启动服务。同一局域网内的浏览器可访问生成的地址。");
        }
        private void EnsureCustomQuality() { if(quality.Items.Count<4) quality.Items.Add("自定义码率"); }
        private static decimal Clamp(int value,NumericUpDown control) { return Math.Max(control.Minimum,Math.Min(control.Maximum,value)); }
        private LauncherConfig ReadSettings() { LauncherConfig c=new LauncherConfig {executablePath=executable.Text.Trim(),httpPort=(int)httpPort.Value,streamerPort=(int)streamerPort.Value,width=(int)renderWidth.Value,height=(int)renderHeight.Value,showWindow=showWindow.Checked,mode=mode.SelectedIndex==1?"independent":"shared",fps=(int)fpsLimit.Value,minBitrateMbps=(int)minBitrate.Value,startBitrateMbps=(int)startBitrate.Value,maxBitrateMbps=(int)maxBitrate.Value,adaptiveResourceBudget=adaptiveResources.Checked}; c.ApplyQualityProfile(quality.SelectedIndex==0?"balanced":quality.SelectedIndex==2?"ultra":quality.SelectedIndex==3?"custom":"clear"); return c; }
        private void UpdateModeHint()
        {
            bool separate=mode.SelectedIndex==1; modeHint.Text=separate?"每位访问者拥有独立视角与操作，最多同时 3 位。":"所有访问者共享同一场景、视角与操作，最多同时 3 位。";
            ((RoundedButton)sharedMode).Selected=!separate; ((RoundedButton)independentMode).Selected=separate; sharedMode.Text=separate?"○  共享场景":"◉  共享场景"; independentMode.Text=separate?"◉  每人独立":"○  每人独立"; sharedMode.AccessibleDescription=separate?"未选中":"当前选中"; independentMode.AccessibleDescription=separate?"当前选中":"未选中"; sharedMode.Invalidate(); independentMode.Invalidate(); sceneMode.Text=separate?"每人独立":"共享场景";
            adaptiveHint.Text=separate?(adaptiveResources.Checked?"保持清晰度，按连接数分配目标帧率。":"各实例保留目标上限，实际帧率取决于负载。") : "共享模式渲染一套场景，不按人数均分帧率。"; resolutionHint.Text="原生分辨率 · 帧率上限 "+fpsLimit.Value+" FPS";
        }
        private void UpdateQualityHint()
        {
            if(loadingSettings) return; LauncherConfig c=ReadSettings(); qualityHint.Text=c.minBitrateMbps+"–"+c.maxBitrateMbps+" Mbps · 起始 "+c.startBitrateMbps+" Mbps";
            if(quality.SelectedIndex!=3) { loadingSettings=true; minBitrate.Value=c.minBitrateMbps; startBitrate.Value=c.startBitrateMbps; maxBitrate.Value=c.maxBitrateMbps; loadingSettings=false; } resolutionHint.Text="原生分辨率 · 帧率上限 "+fpsLimit.Value+" FPS";
        }
        private void SetFieldError(Control control,bool error) { RoundedPanel host; if(fieldHosts.TryGetValue(control,out host)) { host.BorderColor=error?LauncherTheme.Red:LauncherTheme.Border; host.Invalidate(); } }
        private void ClearPortFeedback() { if(loadingSettings || session.State!="idle") return; portConflict=false; portFeedback.Text="端口已修改 · 请重新检测，启动时会再次检查"; portFeedback.ForeColor=Muted; SetFieldError(httpPort,false); SetFieldError(streamerPort,false); UpdateControls(); }
        private void CheckPorts()
        {
            if(session.State!="idle" || startBusy || stopBusy) return; portConflict=false; SetFieldError(httpPort,false); SetFieldError(streamerPort,false);
            if(httpPort.Value==streamerPort.Value) { portConflict=true; portFeedback.Text="网页端口与串流端口不能相同，请修改后重新检测。"; SetFieldError(httpPort,true); SetFieldError(streamerPort,true); }
            else foreach(NumericUpDown field in new[]{httpPort,streamerPort}) { try { PortProbe.EnsureAvailable((int)field.Value); } catch(InvalidOperationException) { portConflict=true; portFeedback.Text="端口 "+field.Value+" 已被占用或不可用，请更换端口后重新检测。"; SetFieldError(field,true); break; } }
            if(!portConflict) portFeedback.Text="✓  "+httpPort.Value+" / "+streamerPort.Value+" 端口可用"; portFeedback.ForeColor=portConflict?LauncherTheme.Red:LauncherTheme.BlueInk; AppendLog(portFeedback.Text); UpdateControls();
        }
        private void UpdateControls()
        {
            bool idle=session.State=="idle" && !startBusy && !stopBusy,canConfigure=idle && !closing; start.Enabled=canConfigure && !portConflict; probe.Enabled=canConfigure; firewall.Enabled=canConfigure;
            foreach(Control control in new Control[]{showWindow,adaptiveResources,mode,browse,sharedMode,independentMode,advanced}) control.Enabled=canConfigure;
            stop.Enabled=!idle && !stopBusy && !closing; start.Visible=idle; stop.Visible=!idle; stop.Text=stopBusy?"正在停止…":startBusy?"取消启动":"□  停止服务"; copy.Enabled=open.Enabled=urls.Items.Count>0 && session.State=="running" && !closing;
            pageSubtitle.Text=idle?"配置流送程序，启动后分享内网地址。":startBusy?"正在准备服务，可取消本次启动。":stopBusy?"正在断开访问并回收本次启动的程序。":"服务运行中，停止服务后可修改配置。"; footerHint.Text=idle?"启动时自动保存配置":"停止将断开访问并关闭本次启动的程序";
            if(session.State=="running") { portFeedback.Text="✓  "+httpPort.Value+" / "+streamerPort.Value+" 已监听"; portFeedback.ForeColor=LauncherTheme.BlueInk; }
            foreach(KeyValuePair<Control,RoundedPanel> pair in fieldHosts) if(pair.Key!=urls) { pair.Key.Enabled=canConfigure; pair.Value.BackColor=idle?Color.White:LauncherTheme.Canvas; pair.Key.BackColor=idle?Color.White:LauncherTheme.Canvas; pair.Value.Invalidate(); }
            foreach(Control label in configLabels) label.ForeColor=Navy; PerformLayout();
        }
        private async Task StartService()
        {
            if(startBusy || stopBusy || session.State!="idle") return; CheckPorts(); if(portConflict) return;
            LauncherConfig c; try { c=ReadSettings(); c.Validate(root,true); } catch(Exception ex) { bool missing=true; try { missing=!File.Exists(ReadSettings().ResolveExecutable(root)) || !string.Equals(Path.GetExtension(executable.Text),".exe",StringComparison.OrdinalIgnoreCase); } catch(ArgumentException) {} catch(NotSupportedException) {} if(missing) { pathFeedback.Text="找不到流送程序，请重新选择。"; SetFieldError(executable,true); } ShowError(ex); return; }
            startBusy=true; stopRequested=false; pollFailures=0; lastBackendLog=""; urls.Items.Clear(); instances.Items.Clear(); SetStatus("◌  正在启动服务",LauncherTheme.StateInk("starting")); sessionHint.Text="检查端口 → 启动流送服务 → 准备场景"; UpdateControls();
            try { c.Save(Path.Combine(root,"launcher.config.json")); AppendLog("正在启动"+(c.mode=="shared"?"共享":"独立")+"模式，渲染 "+c.width+" × "+c.height+"。"); await Task.Run(delegate {session.Start(c);}); if(stopRequested || closing) await Task.Run(delegate {session.Stop();}); else if(session.State=="running") { SetStatus("✓  服务运行中",LauncherTheme.StateInk(session.State)); await Poll(); } }
            catch(OperationCanceledException) { AppendLog("启动已取消。"); if(!closing) SetStatus("○  服务未启动",Muted); } catch(Exception ex) { if(!closing) ShowError(ex); else AppendLog(ex.Message); } finally { startBusy=false; UpdateControls(); }
        }
        private bool ConfirmStop() { if(onlineViewers<1) return true; return MessageBox.Show(this,"当前 "+onlineViewers+" 位访问者将断开连接。\r\n本次启动的服务及程序将一并关闭。","停止像素流服务？",MessageBoxButtons.OKCancel,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2)==DialogResult.OK; }
        private async Task StopService()
        {
            stopRequested=true; if(stopBusy) return; stopBusy=true; SetStatus("◌  正在停止服务",LauncherTheme.StateInk("stopping")); sessionHint.Text="断开访问 → 关闭本次启动的程序 → 回收服务"; UpdateControls();
            try { await Task.Run(delegate {session.Stop();}); AppendLog("本次服务和实例已停止。"); } catch(Exception ex) { AppendLog("停止时出现错误："+ex.Message); }
            finally { urls.Items.Clear(); instances.Items.Clear(); onlineViewers=0; viewers.Text="0 / 3 在线"; portConflict=false; portFeedback.Text="服务已停止 · 启动时重新检查端口"; portFeedback.ForeColor=Muted; SetStatus("○  服务未启动",Muted); stopBusy=false; UpdateControls(); }
        }
        private async Task Poll()
        {
            if(pollBusy || stopBusy || closing || session.State!="running") return; pollBusy=true; bool failed=false;
            try { ServiceStatus s=await Task.Run(delegate {return session.ReadStatus();}); if(closing || session.State!="running") return; pollFailures=0; ApplyStatus(s); }
            catch(Exception ex) { pollFailures++; AppendLog("状态读取失败："+ex.Message); failed=session.State=="idle" || pollFailures>=4; } finally { pollBusy=false; }
            if(failed) { await StopService(); SetStatus("服务异常 · 请查看日志",LauncherTheme.Red); }
        }
        private void ApplyStatus(ServiceStatus s)
        {
            onlineViewers=s.viewerCount; viewers.Text=s.viewerCount+" / "+(s.maxViewers>0?s.maxViewers:3)+" 在线"; SetStatus(s.state=="error"?"服务异常 · 请查看日志":"✓  服务运行中",LauncherTheme.StateInk(s.state));
            string selected=urls.SelectedItem as string; string[] current=s.urls ?? new string[0]; if(!urls.Items.Cast<string>().SequenceEqual(current)) { urls.Items.Clear(); urls.Items.AddRange(current); if(selected!=null && urls.Items.Contains(selected)) urls.SelectedItem=selected; else if(urls.Items.Count>0) urls.SelectedIndex=0; }
            instances.BeginUpdate(); instances.Items.Clear(); foreach(InstanceStatus item in s.instances ?? new InstanceStatus[0]) { string fps=(item.actualFps.HasValue?item.actualFps.Value.ToString("0.0",System.Globalization.CultureInfo.InvariantCulture):"—")+" / "+(item.targetFps>0?item.targetFps.ToString():"—"); ListViewItem row=new ListViewItem(new[]{item.id,StateText(item.state),fps}); row.UseItemStyleForSubItems=false; row.SubItems[1].ForeColor=LauncherTheme.StateInk(item.state); row.ToolTipText="PID "+item.pid+" · 实际 / 当前目标 FPS"; instances.Items.Add(row); } instances.EndUpdate(); instances.ShowItemToolTips=true;
            sessionHint.Text=s.viewerCount==0?"等待访问者连接。实际帧率在画面就绪后显示。":(mode.SelectedIndex==1 && adaptiveResources.Checked?"当前按 "+Math.Max(1,(s.instances??new InstanceStatus[0]).Length)+" 个独立场景分配资源。":"当前"+(mode.SelectedIndex==1?"每位访问者独立操作。":"所有访问者共享视角与操作。"))+"\r\n实际帧率取决于场景、显卡与网络。";
            string backend=string.Join(Environment.NewLine,s.logs ?? new string[0]); if(backend!=lastBackendLog) { lastBackendLog=backend; RenderLog(); } UpdateControls();
        }
        private static string StateText(string value) { switch(value) {case "running":return "运行中";case "ready":return "已就绪";case "starting":return "启动中";case "waiting":return "等待连接";case "connected":return "已连接";case "stopping":return "停止中";case "stopped":return "已停止";case "error":return "异常";case "exited":return "已退出";default:return value ?? "—";} }
        private void SetStatus(string text,Color color) { status.Text=text; status.ForeColor=color; }
        private void AppendLog(string text) { localLogs.Add(DateTime.Now.ToString("HH:mm:ss")+"  "+text); if(localLogs.Count>100) localLogs.RemoveAt(0); RenderLog(); }
        private void RenderLog() { log.Text=string.Join(Environment.NewLine,localLogs.ToArray())+(string.IsNullOrEmpty(lastBackendLog)?"":Environment.NewLine+lastBackendLog); log.SelectionStart=log.TextLength; log.ScrollToCaret(); }
        private void ShowError(Exception ex) { SetStatus("未能启动 · 请检查设置或日志",LauncherTheme.Red); AppendLog(ex.Message); if(string.IsNullOrEmpty(pathFeedback.Text) && !portConflict) { logDrawer.Visible=true; PerformLayout(); } }
        private void OpenUrl(string url) { try { Uri uri; if(!Uri.TryCreate(url,UriKind.Absolute,out uri) || uri.Scheme!="http") throw new ArgumentException("访问地址无效。"); Process.Start(new ProcessStartInfo(uri.AbsoluteUri) {UseShellExecute=true}); } catch(Exception ex) { ShowError(ex); } }
        private void ConfigureFirewall()
        {
            try { LauncherConfig c=ReadSettings(); c.Validate(root,false); string script=Path.Combine(root,"Enable-LanAccess.ps1"); if(!File.Exists(script)) throw new FileNotFoundException("缺少 Enable-LanAccess.ps1，请保留完整部署目录。"); if(MessageBox.Show(this,"将请求 Windows 管理员授权，仅允许本地子网访问网页端口和仓库视频端口。\r\n配置完成后，仍需点击“启动服务”。","配置内网访问",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK) return;
                string args="-NoProfile -ExecutionPolicy Bypass -File "+OwnedProcess.QuoteArgument(script)+" -HttpPort "+c.httpPort+" -ApplicationPath "+OwnedProcess.QuoteArgument(c.ResolveExecutable(root)); Process.Start(new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell","v1.0","powershell.exe"),args) {UseShellExecute=true,Verb="runas",WorkingDirectory=root}); AppendLog("已请求配置内网访问，请查看 Windows 授权窗口与脚本结果。");
            } catch(System.ComponentModel.Win32Exception ex) { AppendLog(ex.NativeErrorCode==1223?"已取消内网访问授权。":ex.Message); } catch(Exception ex) { ShowError(ex); }
        }
        private async void OnClosing(object sender,FormClosingEventArgs e)
        {
            if(allowClose) return; e.Cancel=true; if(closing) return; if(!ConfirmStop()) return; closing=true; timer.Stop(); UpdateControls();
            try { if(startBusy || session.State!="idle") await StopService(); while(startBusy || pollBusy || stopBusy) await Task.Delay(60); if(session.State!="idle") await StopService(); } finally { allowClose=true; Close(); }
        }
    }
}
