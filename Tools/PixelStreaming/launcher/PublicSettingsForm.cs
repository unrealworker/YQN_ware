using System;
using System.Drawing;
using System.IO;
using System.Security.Cryptography;
using System.Windows.Forms;

namespace Ghs.PixelStreaming
{
    // Deployment credentials are local configuration. They never enter service status or UI logs.
    internal sealed class PublicSettingsForm : Form
    {
        private readonly string root;
        private readonly LauncherConfig original;
        private readonly ComboBox network=new ComboBox(),tlsMode=new ComboBox();
        private readonly NumericUpDown capacity=new NumericUpDown();
        private readonly TextBox address=new TextBox(),code=new TextBox(),cert=new TextBox(),key=new TextBox(),stun=new TextBox(),turn=new TextBox(),username=new TextBox(),password=new TextBox();
        private readonly Label tlsHint=new Label();
        private Panel certField,keyField;
        private readonly Label error=new Label();
        internal LauncherConfig Result {get;private set;}
        internal PublicSettingsForm(string root,LauncherConfig config)
        {
            this.root=root; original=config.Clone(); Text="公网与访问设置"; Font=new Font("Microsoft YaHei UI",10F); BackColor=LauncherTheme.Canvas; ForeColor=LauncherTheme.Navy;
            AutoScaleDimensions=new SizeF(96,96); AutoScaleMode=AutoScaleMode.Dpi; FormBorderStyle=FormBorderStyle.Sizable; MinimizeBox=false; MaximizeBox=false; StartPosition=FormStartPosition.CenterParent; ClientSize=new Size(1000,880); MinimumSize=new Size(640,480);
            Panel footer=new Panel {Dock=DockStyle.Bottom,Height=80,BackColor=Color.White}; Controls.Add(footer);
            FlowLayoutPanel actions=new FlowLayoutPanel {Dock=DockStyle.Right,Width=270,Padding=new Padding(10,18,10,10),FlowDirection=FlowDirection.RightToLeft}; footer.Controls.Add(actions);
            RoundedButton save=new RoundedButton {Text="保存设置",Primary=true,Size=new Size(116,42)}; RoundedButton cancel=new RoundedButton {Text="取消",Size=new Size(110,42),DialogResult=DialogResult.Cancel}; actions.Controls.Add(save); actions.Controls.Add(cancel); AcceptButton=save; CancelButton=cancel;
            error.Dock=DockStyle.Fill; error.Padding=new Padding(24,10,0,8); error.ForeColor=LauncherTheme.Red; footer.Controls.Add(error); error.BringToFront();
            TabControl tabs=new TabControl {Dock=DockStyle.Fill,Padding=new Point(18,10)}; Controls.Add(tabs); tabs.BringToFront();
            TabPage entry=new TabPage("访问入口与安全") {BackColor=Color.White,AutoScroll=true},relay=new TabPage("网络穿透 / TURN") {BackColor=Color.White,AutoScroll=true}; tabs.TabPages.Add(entry); tabs.TabPages.Add(relay);
            TableLayoutPanel first=Table(entry),second=Table(relay);
            AddNote(first,"公网访问",true); AddNote(first,"填写服务器实际地址后启用。软件不会自动申请公网 IP、域名或配置路由器。",false);
            network.DropDownStyle=ComboBoxStyle.DropDownList; network.Items.AddRange(new object[]{"局域网 / 本机验证","公网访问"}); network.SelectedIndex=config.networkMode=="public"?1:0;
            capacity.Minimum=1; capacity.Maximum=10; capacity.Value=Math.Max(1,Math.Min(10,config.maxViewers));
            AddField(first,"网络模式",network); AddField(first,"最多在线人数",capacity); AddField(first,"公网访问地址",address); address.Text=config.publicUrl;
            AddNote(first,"例如 https://warehouse.example.com；临时 IP 测试可用 http://公网IP:8080（未加密）。",false);
            code.Text=config.accessCode; code.UseSystemPasswordChar=true; AddField(first,"访问码（至少 12 位）",code);
            FlowLayoutPanel credentials=new FlowLayoutPanel {AutoSize=true,Dock=DockStyle.Fill}; RoundedButton generate=new RoundedButton {Text="生成随机访问码",Width=210,Height=38}; CheckBox reveal=new CheckBox {Text="显示访问码",AutoSize=true,Margin=new Padding(18,8,0,0)}; credentials.Controls.Add(generate); credentials.Controls.Add(reveal); AddWide(first,credentials);
            generate.Click+=delegate { byte[] bytes=new byte[18]; using(RandomNumberGenerator rng=RandomNumberGenerator.Create()) rng.GetBytes(bytes); code.Text=Convert.ToBase64String(bytes).Replace('+','-').Replace('/','_'); };
            reveal.CheckedChanged+=delegate { code.UseSystemPasswordChar=!reveal.Checked; };
            AddNote(first,"访问码与 TURN 密码保存在本机 launcher.config.json，请仅分享访问地址和访问码。",false);
            AddNote(first,"HTTPS 连接",true);
            tlsMode.DropDownStyle=ComboBoxStyle.DropDownList; tlsMode.Items.AddRange(new object[]{"HTTP 临时验证（未加密）","原生 HTTPS（本机证书）","本机 HTTPS 反向代理","云负载均衡 HTTPS（ALB 等）"});
            tlsMode.SelectedIndex=config.externalTlsTermination?3:config.trustProxy?2:!string.IsNullOrWhiteSpace(config.tlsCertPath)?1:0; AddField(first,"HTTPS 接入方式",tlsMode);
            tlsHint.AutoSize=true; tlsHint.MaximumSize=new Size(900,0); tlsHint.ForeColor=LauncherTheme.Muted; tlsHint.Font=new Font("Microsoft YaHei UI",9F); AddWide(first,tlsHint);
            cert.Text=config.tlsCertPath; key.Text=config.tlsKeyPath; certField=AddFile(first,"证书 PEM",cert); keyField=AddFile(first,"私钥 PEM",key);
            network.SelectedIndexChanged+=delegate { UpdateTlsMode(); }; tlsMode.SelectedIndexChanged+=delegate { UpdateTlsMode(); }; UpdateTlsMode();
            AddNote(second,"STUN / TURN 网络穿透",true); AddNote(second,"跨运营商、移动网络或严格防火墙环境建议配置 TURN。请填写你自建或供应商提供的中继服务，启动器不包含 TURN 服务器。",false);
            stun.Text=config.stunUrl; turn.Text=config.turnUrl; username.Text=config.turnUsername; password.Text=config.turnPassword; password.UseSystemPasswordChar=true;
            AddField(second,"STUN 地址（可选）",stun); AddNote(second,"格式：stun:stun.example.com:3478",false); AddField(second,"TURN 地址（可选）",turn); AddNote(second,"格式：turn:turn.example.com:3478?transport=udp 或 turns:turn.example.com:5349?transport=tcp",false); AddField(second,"TURN 用户名",username); AddField(second,"TURN 密码",password);
            AddNote(second,"外网连通检查",true); AddNote(second,"① 公网 IP / 域名指向服务器\n② 防火墙和云安全组放行网页端口\n③ 直连时映射 UDP 50000–50199\n④ TURN 的监听与中继端口按供应商要求放行\n⑤ 用服务器外部网络的浏览器检查画面与操作",false);
            save.Click+=delegate { try { LauncherConfig next=Read(); next.ValidateNetwork(root); Result=next; DialogResult=DialogResult.OK; Close(); } catch(Exception ex) { error.Text=ex.Message; } };
            Shown+=delegate { Rectangle work=Screen.FromControl(this).WorkingArea; Size=new Size(Math.Min(Width,work.Width),Math.Min(Height,work.Height)); };
        }
        internal LauncherConfig Read()
        {
            if(tlsMode.SelectedIndex==1 && (string.IsNullOrWhiteSpace(cert.Text) || string.IsNullOrWhiteSpace(key.Text))) throw new ArgumentException("选择原生 HTTPS 时，请同时选择本机证书和私钥。");
            LauncherConfig c=original.Clone(); c.networkMode=network.SelectedIndex==1?"public":"lan"; c.maxViewers=(int)capacity.Value; c.publicUrl=address.Text.Trim(); c.accessCode=code.Text; c.tlsCertPath=tlsMode.SelectedIndex==1?cert.Text.Trim():""; c.tlsKeyPath=tlsMode.SelectedIndex==1?key.Text.Trim():""; c.trustProxy=network.SelectedIndex==1 && tlsMode.SelectedIndex==2; c.externalTlsTermination=network.SelectedIndex==1 && tlsMode.SelectedIndex==3; c.stunUrl=stun.Text.Trim(); c.turnUrl=turn.Text.Trim(); c.turnUsername=username.Text.Trim(); c.turnPassword=password.Text; return c;
        }
        private void UpdateTlsMode()
        {
            if(network.SelectedIndex!=1 && tlsMode.SelectedIndex>=2) tlsMode.SelectedIndex=0;
            certField.Enabled=keyField.Enabled=tlsMode.SelectedIndex==1;
            switch(tlsMode.SelectedIndex) {
                case 1: tlsHint.Text="证书与私钥成对选择，原生 HTTPS 使用启动器的网页端口。"; break;
                case 2: tlsHint.Text="仅适用于同一台服务器上的 HTTPS 反向代理。网页服务仅监听 127.0.0.1；代理需保留公网 Host 并支持 WebSocket。"; break;
                case 3: tlsHint.Text="证书由云负载均衡管理，HTTP 回源到服务器网页端口，无需本机证书。仅允许 ALB 回源来源访问该端口；需保留公网 Host 并支持 WebSocket。\n不自动信任转发 IP，在线用户来源地址可能显示为负载均衡地址。"; break;
                default: tlsHint.Text="HTTP 仅用于本机、局域网或临时验证，公网访问码和通信未加密。两种代理方式仅在公网模式可选。"; break;
            }
        }
        private static TableLayoutPanel Table(Control parent) { TableLayoutPanel t=new TableLayoutPanel {Dock=DockStyle.Top,AutoSize=true,Padding=new Padding(24,18,24,24),ColumnCount=2}; t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,225)); t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100)); parent.Controls.Add(t); return t; }
        private static void AddField(TableLayoutPanel t,string name,Control control) { int r=t.RowCount++; t.RowStyles.Add(new RowStyle(SizeType.AutoSize)); Label label=new Label {Text=name,AutoSize=true,Margin=new Padding(0,14,14,14),Dock=DockStyle.Fill}; t.Controls.Add(label,0,r); control.Dock=DockStyle.Fill; control.Margin=new Padding(0,9,0,9); control.MinimumSize=new Size(100,28); t.Controls.Add(control,1,r); }
        private static void AddWide(TableLayoutPanel t,Control control) { int r=t.RowCount++; t.RowStyles.Add(new RowStyle(SizeType.AutoSize)); control.Dock=DockStyle.Fill; control.Margin=new Padding(0,7,0,10); t.Controls.Add(control,0,r); t.SetColumnSpan(control,2); }
        private static void AddNote(TableLayoutPanel t,string text,bool title) { Label label=new Label {Text=text,AutoSize=true,MaximumSize=new Size(900,0),ForeColor=title?LauncherTheme.Navy:LauncherTheme.Muted,Font=new Font("Microsoft YaHei UI",title?13F:9F,title?FontStyle.Bold:FontStyle.Regular)}; AddWide(t,label); }
        private Panel AddFile(TableLayoutPanel table,string title,TextBox text) { Panel wrap=new Panel {Height=38}; RoundedButton select=new RoundedButton {Text="选择",Dock=DockStyle.Right,Width=68}; text.Dock=DockStyle.Fill; wrap.Controls.Add(text); wrap.Controls.Add(select); AddField(table,title,wrap); select.Click+=delegate { using(OpenFileDialog file=new OpenFileDialog {Title="选择"+title,Filter="PEM 文件 (*.pem;*.crt;*.key)|*.pem;*.crt;*.key|所有文件 (*.*)|*.*",CheckFileExists=true}) if(file.ShowDialog(this)==DialogResult.OK) text.Text=file.FileName; }; return wrap; }
    }
}
