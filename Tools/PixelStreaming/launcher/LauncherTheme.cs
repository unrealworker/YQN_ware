using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace Ghs.PixelStreaming
{
    internal static class LauncherTheme
    {
        internal static readonly Color Navy=Color.FromArgb(37,54,75);
        internal static readonly Color Muted=Color.FromArgb(83,100,120);
        internal static readonly Color Blue=Color.FromArgb(53,107,250);
        internal static readonly Color BlueInk=Color.FromArgb(36,85,204);
        internal static readonly Color Canvas=Color.FromArgb(244,246,249);
        internal static readonly Color Border=Color.FromArgb(204,214,227);
        internal static readonly Color DisabledInk=Color.FromArgb(107,119,136);
        internal static readonly Color Amber=Color.FromArgb(151,96,37);
        internal static readonly Color Red=Color.FromArgb(168,69,64);
        internal static readonly Color RedAccent=Color.FromArgb(200,88,82);
        internal static Color StateInk(string state)
        {
            switch(state)
            {
                case "running": case "ready": case "connected": return BlueInk;
                case "starting": case "waiting": case "reconnecting": return Amber;
                case "error": case "failed": return Red;
                case "idle": case "stopping": case "stopped": case "exited": return DisabledInk;
                default: return Muted;
            }
        }
        internal static GraphicsPath Round(RectangleF r,float radius)
        {
            float d=Math.Min(radius*2,Math.Min(r.Width,r.Height)); GraphicsPath path=new GraphicsPath();
            path.AddArc(r.X,r.Y,d,d,180,90); path.AddArc(r.Right-d,r.Y,d,d,270,90);
            path.AddArc(r.Right-d,r.Bottom-d,d,d,0,90); path.AddArc(r.X,r.Bottom-d,d,d,90,90); path.CloseFigure(); return path;
        }
    }
    internal sealed class RoundedPanel : Panel
    {
        internal Color BorderColor=Color.Transparent;
        internal int Radius=12;
        internal RoundedPanel() { SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true); BackColor=Color.White; }
        protected override void OnPaintBackground(PaintEventArgs e) { e.Graphics.Clear(Parent==null?LauncherTheme.Canvas:Parent.BackColor); }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            using(GraphicsPath p=LauncherTheme.Round(new RectangleF(.5F,.5F,Width-1,Height-1),Radius*e.Graphics.DpiX/96F))
            using(SolidBrush b=new SolidBrush(BackColor)) { e.Graphics.FillPath(b,p); if(BorderColor!=Color.Transparent) using(Pen pen=new Pen(BorderColor)) e.Graphics.DrawPath(pen,p); }
            base.OnPaint(e);
        }
        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e); if(Width<2 || Height<2) return;
            using(Graphics graphics=CreateGraphics()) using(GraphicsPath p=LauncherTheme.Round(new RectangleF(0,0,Width,Height),Radius*graphics.DpiX/96F)) { Region old=Region; Region=new Region(p); if(old!=null) old.Dispose(); }
            Invalidate();
        }
    }
    internal sealed class RoundedButton : Button
    {
        internal bool Primary;
        internal bool Destructive;
        internal bool Selected;
        private bool hovering;
        internal RoundedButton() { FlatStyle=FlatStyle.Flat; FlatAppearance.BorderSize=0; Cursor=Cursors.Hand; UseVisualStyleBackColor=false; BackColor=Color.White; ForeColor=LauncherTheme.Navy; }
        protected override void OnMouseEnter(EventArgs e) { hovering=true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hovering=false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnPaint(PaintEventArgs e)
        {
            // Button is opaque: WM_PAINT does not paint the background before this override.
            // Cover the buffer, including the area outside the rounded outline, on every repaint.
            Control background=Parent;
            while(background!=null && background.BackColor.A<255) background=background.Parent;
            using(SolidBrush backdrop=new SolidBrush(background==null?LauncherTheme.Canvas:background.BackColor))
                e.Graphics.FillRectangle(backdrop,ClientRectangle);
            e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            Color fill=Enabled?(Primary?LauncherTheme.Blue:(hovering?Color.FromArgb(239,244,255):BackColor)):LauncherTheme.Canvas;
            Color border=Enabled?(Destructive?LauncherTheme.RedAccent:(Primary || Selected?LauncherTheme.Blue:LauncherTheme.Border)):LauncherTheme.Border;
            Color ink=Enabled?(Primary?Color.White:(Destructive?LauncherTheme.Red:(Selected?LauncherTheme.BlueInk:ForeColor))):LauncherTheme.DisabledInk;
            using(GraphicsPath p=LauncherTheme.Round(new RectangleF(1,1,Width-2,Height-2),12*e.Graphics.DpiX/96F))
            using(SolidBrush brush=new SolidBrush(fill)) using(Pen pen=new Pen(border,Selected && Enabled?2:1)) { e.Graphics.FillPath(brush,p); e.Graphics.DrawPath(pen,p); }
            TextRenderer.DrawText(e.Graphics,Text,Font,new Rectangle(6,2,Width-12,Height-4),ink,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis);
            if(Focused && ShowFocusCues) ControlPaint.DrawFocusRectangle(e.Graphics,new Rectangle(5,5,Width-10,Height-10),ink,fill);
        }
    }
    internal sealed class RoundedPictureBox : PictureBox
    {
        protected override void OnPaintBackground(PaintEventArgs e) { e.Graphics.Clear(Parent==null?Color.White:Parent.BackColor); }
        protected override void OnPaint(PaintEventArgs e) { e.Graphics.SmoothingMode=SmoothingMode.AntiAlias; using(GraphicsPath path=LauncherTheme.Round(new RectangleF(0,0,Width,Height),8*e.Graphics.DpiX/96F)) { e.Graphics.SetClip(path); using(SolidBrush brush=new SolidBrush(BackColor)) e.Graphics.FillPath(brush,path); base.OnPaint(e); e.Graphics.ResetClip(); } }
    }
    internal sealed class ToggleCheckBox : CheckBox
    {
        internal ToggleCheckBox() { SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true); Cursor=Cursors.Hand; AutoSize=false; }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(BackColor); e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            float scale=e.Graphics.DpiX/96F; float w=36*scale,h=20*scale,y=(Height-h)/2;
            Color track=Checked&&Enabled?LauncherTheme.Blue:Color.FromArgb(148,163,184);
            using(GraphicsPath p=LauncherTheme.Round(new RectangleF(0,y,w,h),h/2)) using(SolidBrush b=new SolidBrush(track)) e.Graphics.FillPath(b,p);
            using(SolidBrush b=new SolidBrush(Color.White)) e.Graphics.FillEllipse(b,(Checked?18:2)*scale,y+2*scale,16*scale,16*scale);
            TextRenderer.DrawText(e.Graphics,Text,Font,new Rectangle((int)(48*scale),0,Width-(int)(48*scale),Height),Enabled?ForeColor:LauncherTheme.DisabledInk,TextFormatFlags.VerticalCenter|TextFormatFlags.Left|TextFormatFlags.EndEllipsis);
            if(Focused && ShowFocusCues) ControlPaint.DrawFocusRectangle(e.Graphics,new Rectangle(0,0,Width-1,Height-1));
        }
    }
}
