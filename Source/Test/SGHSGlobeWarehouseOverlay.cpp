#include "SGHSGlobeWarehouseOverlay.h"

#include "Brushes/SlateRoundedBoxBrush.h"
#include "Misc/Paths.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SConstraintCanvas.h"
#include "Widgets/Layout/SDPIScaler.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Input/Events.h"

namespace
{
FLinearColor Color(const TCHAR* Hex) { return FLinearColor::FromSRGBColor(FColor::FromHex(Hex)); }
const FSlateFontInfo& MarkerFont()
{
    static const auto Composite = MakeShared<FCompositeFont>(TEXT("Regular"),
        FPaths::ProjectContentDir() / TEXT("GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf"),
        EFontHinting::Default, EFontLoadingPolicy::LazyLoad);
    static const FSlateFontInfo Font(Composite, 14);
    return Font;
}

// Capture only the event currently being handled. Unhandled/cancelled events
// must not label a later accessibility SimulateClick as pointer or keyboard.
// SButton handles touch through its pointer handlers as well.
class SGlobeInputButton : public SButton
{
public:
    using FArguments = SButton::FArguments;
    void Construct(const FArguments& Args, TSharedRef<FString> InSource)
    { Source = InSource; SButton::Construct(Args); }
    virtual FReply OnKeyDown(const FGeometry& G, const FKeyEvent& E) override
    { TGuardValue<FString> EventSource(*Source, TEXT("keyboard")); return SButton::OnKeyDown(G, E); }
    virtual FReply OnKeyUp(const FGeometry& G, const FKeyEvent& E) override
    { TGuardValue<FString> EventSource(*Source, TEXT("keyboard")); return SButton::OnKeyUp(G, E); }
    virtual FReply OnMouseButtonDown(const FGeometry& G, const FPointerEvent& E) override
    { TGuardValue<FString> EventSource(*Source, TEXT("pointer")); return SButton::OnMouseButtonDown(G, E); }
    virtual FReply OnMouseButtonUp(const FGeometry& G, const FPointerEvent& E) override
    { TGuardValue<FString> EventSource(*Source, TEXT("pointer")); return SButton::OnMouseButtonUp(G, E); }
    virtual FReply OnMouseButtonDoubleClick(const FGeometry& G, const FPointerEvent& E) override
    { TGuardValue<FString> EventSource(*Source, TEXT("pointer")); return SButton::OnMouseButtonDoubleClick(G, E); }
private:
    TSharedPtr<FString> Source;
};
DECLARE_DELEGATE_RetVal_OneParam(FReply, FOnGlobeMarkerClicked, const FString&);

/** Draws the card in physical pixels; its parent DPI scaler cancels window scaling. */
class SGlobeMarkerCard : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SGlobeMarkerCard) {}
        SLATE_ARGUMENT(TSharedPtr<FGHSGlobeScreenMarker>, Marker)
        SLATE_EVENT(FOnGlobeMarkerClicked, OnSelect)
        SLATE_EVENT(FOnGlobeMarkerClicked, OnEnter)
    SLATE_END_ARGS()

    void Construct(const FArguments& Args)
    {
        Marker = Args._Marker;
        SetVisibility(EVisibility::SelfHitTestInvisible);
        auto Activate = [Source = InputSource](FOnGlobeMarkerClicked Handler)
        {
            const FString EventSource = *Source;
            *Source = TEXT("unknown");
            return Handler.IsBound() ? Handler.Execute(EventSource) : FReply::Handled();
        };
        const auto* ButtonStyle = &FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("NoBorder");
        if (Marker->IsCluster())
        {
            ChildSlot[SNew(SGlobeInputButton, InputSource).ButtonStyle(ButtonStyle)
                .OnClicked_Lambda([Activate, Handler = Args._OnSelect] { return Activate(Handler); })
                .ToolTipText_Lambda([this] { return FText::Format(NSLOCTEXT("GHSGlobe", "Cluster", "查看此区域的 {0} 座仓库"), Marker->Ids.Num()); })
                .HAlign(HAlign_Center).VAlign(VAlign_Center)
                [SNew(STextBlock).Font(MarkerFont()).ColorAndOpacity(FLinearColor::White)
                    .Text_Lambda([this] { return FText::AsNumber(Marker->Ids.Num()); })]];
        }
        else
        {
            ChildSlot[SNew(SHorizontalBox)
                + SHorizontalBox::Slot().FillWidth(1.f)
                [SNew(SGlobeInputButton, InputSource).ButtonStyle(ButtonStyle).ContentPadding(FMargin(48, 0, 4, 0))
                    .HAlign(HAlign_Fill).VAlign(VAlign_Center)
                    .OnClicked_Lambda([Activate, Handler = Args._OnSelect] { return Activate(Handler); })
                    .ToolTipText_Lambda([this] { return FText::FromString(TEXT("选择 ") + Marker->Name); })
                    [SNew(STextBlock).Font(MarkerFont()).OverflowPolicy(ETextOverflowPolicy::Ellipsis)
                        .ColorAndOpacity_Lambda([this] { return Marker->bSelected ? FLinearColor::White : Color(TEXT("10254F")); })
                        .Text_Lambda([this] { return FText::FromString(Marker->Name); })]]
                + SHorizontalBox::Slot().AutoWidth()
                [SNew(SBox).WidthOverride(36)
                    [SNew(SGlobeInputButton, InputSource).ButtonStyle(ButtonStyle).ContentPadding(0)
                        .OnClicked_Lambda([Activate, Handler = Args._OnEnter] { return Activate(Handler); })
                        .ToolTipText_Lambda([this] { return FText::FromString(TEXT("进入 ") + Marker->Name); })]]];
        }
    }

    virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& G, const FSlateRect& Clip,
        FSlateWindowElementList& Elements, int32 Layer, const FWidgetStyle& Style, bool Enabled) const override
    {
        const FVector2D Size = G.GetLocalSize();
        const bool Selected = Marker->bSelected || Marker->IsCluster();
        const bool Focused = HasFocusedDescendants();
        const FLinearColor Accent = Color(TEXT("2E70FF"));
        const FLinearColor Tint = Style.GetColorAndOpacityTint();
        auto Box = [&](FVector2D At, FVector2D Dimensions, FLinearColor Fill, float Radius, FLinearColor Border, float Width)
        {
            const FSlateRoundedBoxBrush Brush(FLinearColor::White, Radius, Border * Tint, Width);
            FSlateDrawElement::MakeBox(Elements, ++Layer, G.ToPaintGeometry(Dimensions, FSlateLayoutTransform(At)), &Brush, ESlateDrawEffect::None, Fill * Tint);
        };
        Box(FVector2D(0, 3), Size, FLinearColor(0.01, .04, .12, .18), 11, FLinearColor::Transparent, 0);
        Box(FVector2D::ZeroVector, Size, Selected ? Accent : FLinearColor::White, 10,
            Focused ? Color(TEXT("79B5FF")) : (Selected ? Color(TEXT("91C2FF")) : Color(TEXT("D3E2F3"))), Focused ? 3 : 1);
        if (!Marker->IsCluster())
        {
            const FLinearColor Ink = Selected ? FLinearColor::White : Accent;
            Box(FVector2D(8, 8), FVector2D(32, 32), Selected ? FLinearColor(1, 1, 1, .16) : Color(TEXT("E7EFFF")), 7, FLinearColor::Transparent, 0);
            auto Line = [&](std::initializer_list<FVector2D> Points)
            {
                TArray<FVector2D> Path; for (const auto& P : Points) Path.Add(P);
                FSlateDrawElement::MakeLines(Elements, ++Layer, G.ToPaintGeometry(), Path, ESlateDrawEffect::None, Ink * Tint, true, 1.6f);
            };
            Line({{15, 21}, {24, 14}, {33, 21}});
            Line({{17, 20}, {17, 34}, {31, 34}, {31, 20}});
            Line({{21, 34}, {21, 24}, {27, 24}, {27, 34}});
            Line({{22, 27}, {26, 27}}); Line({{22, 30}, {26, 30}});
            Line({{Size.X - 21, 19}, {Size.X - 16, 24}, {Size.X - 21, 29}});
        }
        return SCompoundWidget::OnPaint(Args, G, Clip, Elements, Layer + 1, Style, Enabled);
    }

private:
    TSharedPtr<FGHSGlobeScreenMarker> Marker;
    TSharedRef<FString> InputSource = MakeShared<FString>(TEXT("unknown"));
};
}

float FGHSGlobeAnnotationFade::StandardEase(float Progress)
{
    const double X = FMath::Clamp(double(Progress), 0., 1.);
    if (X <= 0. || X >= 1.) return float(X);
    // CSS cubic-bezier(.4,0,.2,1): solve x(t)=progress, then evaluate y(t).
    double Low = 0., High = 1.;
    for (int32 I = 0; I < 24; ++I)
    {
        const double T = (Low + High) * .5, U = 1. - T;
        const double BezierX = 3. * U * U * T * .4 + 3. * U * T * T * .2 + T * T * T;
        if (BezierX < X) Low = T; else High = T;
    }
    const double T = (Low + High) * .5;
    return float(T * T * (3. - 2. * T));
}

void FGHSGlobeAnnotationFade::SetVisible(bool bVisible, bool bReducedMotion, bool bImmediate)
{
    const float Next = bVisible ? 1.f : 0.f;
    if (bImmediate) { Opacity = Start = Target = Next; Elapsed = Duration = 0.f; return; }
    if (Next == Target) return;
    Start = Opacity; Target = Next; Elapsed = 0.f;
    Duration = bReducedMotion ? .12f : (bVisible ? .18f : .16f);
}

void FGHSGlobeAnnotationFade::Advance(float DeltaSeconds)
{
    if (!FMath::IsFinite(DeltaSeconds) || DeltaSeconds <= 0.f || Duration <= 0.f) return;
    Elapsed = FMath::Min(Duration, Elapsed + DeltaSeconds);
    Opacity = FMath::Lerp(Start, Target, StandardEase(Elapsed / Duration));
    if (Elapsed >= Duration) { Opacity = Target; Duration = 0.f; }
}

FGHSGlobePOIGeometry FGHSGlobePOIGeometry::Make(FVector2D Point, const FSlateRect& Rect, bool Cluster)
{
    FGHSGlobePOIGeometry Result;
    Result.CardSize = Cluster ? FVector2D(48, 40) : FVector2D(248, 48);
    Result.CardPosition = Point + (Cluster ? -Result.CardSize * .5 : FVector2D(-156, -92));
    const bool Below = !Cluster && Result.CardPosition.Y < Rect.Top + 8;
    if (Below) Result.CardPosition.Y = Point.Y + 44;
    Result.CardPosition.X = FMath::Clamp(Result.CardPosition.X, double(Rect.Left + 8), FMath::Max(double(Rect.Left + 8), Rect.Right - Result.CardSize.X - 8));
    Result.CardPosition.Y = FMath::Clamp(Result.CardPosition.Y, double(Rect.Top + 8), FMath::Max(double(Rect.Top + 8), Rect.Bottom - Result.CardSize.Y - 8));
    Result.LineEnd = FVector2D(FMath::Clamp(Point.X - 30, Result.CardPosition.X + 12, Result.CardPosition.X + Result.CardSize.X - 12),
        Result.CardPosition.Y + (Below ? 0 : Result.CardSize.Y));
    Result.LineStart = Point + (Result.LineEnd - Point).GetSafeNormal() * (PointDiameter * .5);
    return Result;
}

FGHSGlobePOIGeometry FGHSGlobePOIGeometry::AvoidOverlaps(FVector2D Point, const FSlateRect& Rect,
    const TArray<FSlateRect>& Occupied, bool Cluster)
{
    auto Result = Make(Point, Rect, Cluster);
    if (Cluster) return Result;
    const FVector2D Preferred = Result.CardPosition;
    auto Clear = [&](FVector2D Position)
    {
        for (const auto& Other : Occupied)
            if (Position.X < Other.Right + 8 && Position.X + Result.CardSize.X + 8 > Other.Left
                && Position.Y < Other.Bottom + 8 && Position.Y + Result.CardSize.Y + 8 > Other.Top)
                return false;
        return true;
    };
    auto Try = [&](double Y)
    {
        const FVector2D Candidate(Preferred.X, FMath::Clamp(Y, double(Rect.Top + 8),
            FMath::Max(double(Rect.Top + 8), Rect.Bottom - Result.CardSize.Y - 8)));
        if (Candidate.Y < Point.Y + 28 && Candidate.Y + Result.CardSize.Y > Point.Y - 28) return false;
        if (!Clear(Candidate)) return false;
        Result.CardPosition = Candidate;
        return true;
    };
    if (!Clear(Preferred) && !Try(Point.Y + 44))
    {
        // Stable-id placement tries the opposite side first, then nearby rows.
        // This moves only the label; its geographic point never moves.
        const double Step = Result.CardSize.Y + 8;
        const int32 Rows = FMath::CeilToInt((Rect.Bottom - Rect.Top) / Step);
        for (int32 I = 1; I <= Rows; ++I)
            if (Try(Preferred.Y + I * Step) || Try(Preferred.Y - I * Step)) break;
    }
    const bool Below = Result.CardPosition.Y > Point.Y;
    Result.LineEnd = FVector2D(FMath::Clamp(Point.X - 30, Result.CardPosition.X + 12,
        Result.CardPosition.X + Result.CardSize.X - 12), Result.CardPosition.Y + (Below ? 0 : Result.CardSize.Y));
    Result.LineStart = Point + (Result.LineEnd - Point).GetSafeNormal() * (PointDiameter * .5);
    return Result;
}

struct SGHSGlobeWarehouseOverlay::FEntry
{
    TSharedPtr<FGHSGlobeScreenMarker> Marker;
    TSharedPtr<SWidget> Widget;
    FGHSGlobePOIGeometry Layout;
};

void SGHSGlobeWarehouseOverlay::Construct(const FArguments& Args)
{
    OnSelect = Args._OnSelect; OnEnter = Args._OnEnter;
    OnCluster = Args._OnCluster; OnInteraction = Args._OnInteraction;
    SetVisibility(EVisibility::SelfHitTestInvisible);
    SetCanTick(true);
    ChildSlot[SAssignNew(Canvas, SConstraintCanvas)];
}

void SGHSGlobeWarehouseOverlay::SetSceneRect(const FSlateRect& InSceneRect)
{
    SceneRect = InSceneRect;
}

void SGHSGlobeWarehouseOverlay::SetPresentation(bool bVisible, bool bInteractive, bool bReducedMotion, bool bImmediate)
{
    Fade.SetVisible(bVisible, bReducedMotion, bImmediate);
    bAnnotationInteractive = bVisible && bInteractive;
    SetVisibility(bAnnotationInteractive ? EVisibility::SelfHitTestInvisible : EVisibility::HitTestInvisible);
    if (!bAnnotationInteractive && bWasInteracting)
    {
        bWasInteracting = false;
        OnInteraction.ExecuteIfBound(false);
    }
    SetRenderOpacity(Fade.Opacity);
}

void SGHSGlobeWarehouseOverlay::AdvancePresentation(float DeltaSeconds)
{
    Fade.Advance(DeltaSeconds);
    SetRenderOpacity(Fade.Opacity);
}

void SGHSGlobeWarehouseOverlay::SetMarkers(const TArray<FGHSGlobeScreenMarker>& InMarkers)
{
    TSet<FString> Incoming;
    OrderedIds.Reset(InMarkers.Num());
    for (const auto& Marker : InMarkers) { Incoming.Add(Marker.Id); OrderedIds.Add(Marker.Id); }
    OrderedIds.Sort();
    for (auto It = Entries.CreateIterator(); It; ++It)
        if (!Incoming.Contains(It.Key())) { Canvas->RemoveSlot(It.Value()->Widget.ToSharedRef()); It.RemoveCurrent(); }
    if (Entries.IsEmpty() && bWasInteracting)
    {
        bWasInteracting = false;
        OnInteraction.ExecuteIfBound(false);
    }
    for (const auto& Marker : InMarkers)
    {
        if (const auto* Found = Entries.Find(Marker.Id)) { *(*Found)->Marker = Marker; continue; }
        auto Entry = MakeShared<FEntry>();
        Entry->Marker = MakeShared<FGHSGlobeScreenMarker>(Marker);
        const TWeakPtr<SGHSGlobeWarehouseOverlay> WeakThis = StaticCastSharedRef<SGHSGlobeWarehouseOverlay>(AsShared());
        auto Select = [WeakThis, Value = Entry->Marker](const FString& Source)
        {
            if (auto Self = WeakThis.Pin(); Self && Self->bAnnotationInteractive)
            {
                if (Value->IsCluster()) Self->OnCluster.ExecuteIfBound(Value->Ids);
                else Self->OnSelect.ExecuteIfBound(Value->Id, Source);
            }
            return FReply::Handled();
        };
        Entry->Widget = SNew(SDPIScaler).DPIScale_Lambda([this] { return PixelUnit; })
            [SNew(SGlobeMarkerCard).Marker(Entry->Marker).OnSelect_Lambda(Select)
                .OnEnter_Lambda([WeakThis, Value = Entry->Marker](const FString& Source)
                { if (auto Self = WeakThis.Pin(); Self && Self->bAnnotationInteractive) Self->OnEnter.ExecuteIfBound(Value->Id, Source); return FReply::Handled(); })];
        Canvas->AddSlot().Anchors(FAnchors(0, 0)).Alignment(FVector2D::ZeroVector)
            .Offset_Lambda([this, Entry]
            {
                const auto& Layout = Entry->Layout;
                return FMargin(Layout.CardPosition.X * PixelUnit, Layout.CardPosition.Y * PixelUnit,
                    Layout.CardSize.X * PixelUnit, Layout.CardSize.Y * PixelUnit);
            })[Entry->Widget.ToSharedRef()];
        Entries.Add(Marker.Id, Entry);
    }
    TArray<FSlateRect> Occupied;
    for (const FString& Id : OrderedIds)
    {
        auto& Entry = *Entries.FindChecked(Id);
        Entry.Layout = FGHSGlobePOIGeometry::AvoidOverlaps(Entry.Marker->PointPixels, SceneRect, Occupied, Entry.Marker->IsCluster());
        Occupied.Emplace(Entry.Layout.CardPosition.X, Entry.Layout.CardPosition.Y,
            Entry.Layout.CardPosition.X + Entry.Layout.CardSize.X, Entry.Layout.CardPosition.Y + Entry.Layout.CardSize.Y);
    }
    Invalidate(EInvalidateWidgetReason::Layout | EInvalidateWidgetReason::Paint);
}

void SGHSGlobeWarehouseOverlay::Tick(const FGeometry& Geometry, double Time, float DeltaTime)
{
    SCompoundWidget::Tick(Geometry, Time, DeltaTime);
    PixelUnit = 1.f / FMath::Max(.01f, Geometry.GetAccumulatedLayoutTransform().GetScale());
    bool Interacting = false;
    if (bAnnotationInteractive) for (const auto& Entry : Entries)
        Interacting |= Entry.Value->Widget->IsHovered() || Entry.Value->Widget->HasFocusedDescendants();
    if (Interacting != bWasInteracting) { bWasInteracting = Interacting; OnInteraction.ExecuteIfBound(Interacting); }
}

int32 SGHSGlobeWarehouseOverlay::OnPaint(const FPaintArgs& Args, const FGeometry& G, const FSlateRect& Clip,
    FSlateWindowElementList& Elements, int32 Layer, const FWidgetStyle& Style, bool Enabled) const
{
    const float Unit = 1.f / FMath::Max(.01f, G.GetAccumulatedLayoutTransform().GetScale());
    const FLinearColor Tint = Style.GetColorAndOpacityTint();
    auto Circle = [&](FVector2D Center, float Diameter, FLinearColor Fill)
    {
        const FSlateRoundedBoxBrush Brush(FLinearColor::White, Diameter * Unit * .5f);
        // Keep odd/even diameter layers on the same continuous screen anchor.
        // Independent pixel rounding makes the rim and core jump out of phase
        // during slow globe rotation; the rounded-box shader handles edge AA.
        FSlateDrawElement::MakeBox(Elements, ++Layer,
            G.ToPaintGeometry(FVector2D(Diameter) * Unit, FSlateLayoutTransform((Center - FVector2D(Diameter * .5)) * Unit)),
            &Brush, ESlateDrawEffect::NoPixelSnapping, Fill * Tint);
    };
    for (const FString& Id : OrderedIds)
    {
        const auto& Entry = *Entries.FindChecked(Id);
        const auto& Marker = *Entry.Marker;
        if (Marker.IsCluster()) continue;
        const auto& Layout = Entry.Layout;
        const TArray<FVector2D> Line{Layout.LineStart * Unit, Layout.LineEnd * Unit};
        // Slate line thickness is already measured in render pixels.
        FSlateDrawElement::MakeLines(Elements, ++Layer, G.ToPaintGeometry(), Line, ESlateDrawEffect::None, FLinearColor(.015, .07, .18, .55) * Tint, true, 3.5f);
        FSlateDrawElement::MakeLines(Elements, ++Layer, G.ToPaintGeometry(), Line, ESlateDrawEffect::None, FLinearColor::White * Tint, true, 1.5f);
        Circle(Marker.PointPixels, FGHSGlobePOIGeometry::HaloDiameter, Color(TEXT("277BFF")).CopyWithNewOpacity(.14f));
        Circle(Marker.PointPixels, 29, Color(TEXT("349BFF")).CopyWithNewOpacity(.23f));
        Circle(Marker.PointPixels, 23, Color(TEXT("1153B6")).CopyWithNewOpacity(.75f));
        Circle(Marker.PointPixels, FGHSGlobePOIGeometry::PointDiameter, FLinearColor::White);
        Circle(Marker.PointPixels, 15, Color(Marker.bSelected ? TEXT("16B1FF") : TEXT("247AFF")));
        Circle(Marker.PointPixels + FVector2D(-2, -2), 4, FLinearColor(1, 1, 1, .9));
    }
    return SCompoundWidget::OnPaint(Args, G, Clip, Elements, Layer + 1, Style, Enabled);
}
