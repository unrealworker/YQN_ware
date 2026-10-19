#include "GHSDockTruckHUDWidget.h"
#include "GHSHUDMotion.h"
#include "GHSDockTruckDataComponent.h"
#include "GHSStackerDataComponent.h"
#include "GHSMannedForkliftDataComponent.h"
#include "GHSMannedForkliftIdentityLibrary.h"
#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Fonts/FontMeasure.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Misc/Paths.h"

namespace
{
    const FVector2D CardSize(320, 184);
    const FVector2D CloseOrigin(290, 4);
    const FVector2D CloseSize(28, 28);
    const FLinearColor Ink = FLinearColor::FromSRGBColor(FColor::FromHex(TEXT("24384B")));
    const FLinearColor Muted = FLinearColor::FromSRGBColor(FColor::FromHex(TEXT("64788B")));
    const FLinearColor Blue = FLinearColor::FromSRGBColor(FColor::FromHex(TEXT("24569A")));
    const FLinearColor Border = FLinearColor::FromSRGBColor(FColor::FromHex(TEXT("C4D2DE")));
    FLinearColor Color(const TCHAR* Hex) { return FLinearColor::FromSRGBColor(FColor::FromHex(Hex)); }
    bool Inside(FVector2D P, FVector2D Origin, FVector2D Size)
    {
        return P.X >= Origin.X && P.Y >= Origin.Y && P.X <= Origin.X + Size.X && P.Y <= Origin.Y + Size.Y;
    }
    constexpr float LabelDuration = GHSHUDMotion::Duration;
    constexpr float PopupDuration = .22f;
    constexpr int32 RowsPerPage = 5;
    float Ease(float T) { T = FMath::Clamp(T, 0.f, 1.f); return T*T*(3-2*T); }
    FVector2D ClampPanel(FVector2D P, FVector2D S, FVector2D Canvas)
    {
        return FVector2D(FMath::Clamp(P.X, 12., FMath::Max(12., Canvas.X-S.X-12)),
            FMath::Clamp(P.Y, 12., FMath::Max(12., Canvas.Y-S.Y-12)));
    }
    FString StatusText(EGHSDockTruckStatus Status)
    {
        switch (Status)
        {
        case EGHSDockTruckStatus::Docked: return TEXT("已泊位");
        case EGHSDockTruckStatus::Loading: return TEXT("装载中");
        case EGHSDockTruckStatus::Warning: return TEXT("需关注");
        case EGHSDockTruckStatus::Fault: return TEXT("故障");
        case EGHSDockTruckStatus::Offline: return TEXT("离线");
        default: return TEXT("待接入");
        }
    }
    FLinearColor StatusColor(EGHSDockTruckStatus Status)
    {
        switch (Status)
        {
        case EGHSDockTruckStatus::Docked: return Blue;
        case EGHSDockTruckStatus::Loading: return Color(TEXT("16876A"));
        case EGHSDockTruckStatus::Warning: return Color(TEXT("A66514"));
        case EGHSDockTruckStatus::Fault: return Color(TEXT("BA4140"));
        default: return Color(TEXT("788896"));
        }
    }

    FSlateFontInfo Font(float Size, float Scale)
    {
        return FSlateFontInfo(FPaths::ProjectContentDir() / TEXT("GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf"), Size * Scale);
    }
    float TextWidth(const FString& Value, float Size, float Scale)
    {
        return FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Value, Font(Size, Scale)).X / Scale;
    }
    FString CompactMetric(const UGHSDockTruckDataComponent& Data)
    {
        return Data.HasTelemetry() ? FString::Printf(TEXT("%d/%d 托"), Data.LoadedPallets, Data.TotalPallets) : TEXT("--/-- 托");
    }
    struct FCompactLayout
    {
        float IdWidth;
        float StatusX;
        float StatusWidth;
        float DividerX;
        float MetricX;
        float MetricWidth;
        FVector2D Size;
        float DemoWidth;
        FCompactLayout(const FString& Id, const FString& Status, const FString& Metric, bool bDemo, float Scale, float MaxWidth)
        {
            IdWidth = FMath::Min(TextWidth(Id, 12, Scale), 86.f);
            StatusWidth = FMath::Min(TextWidth(Status, 10, Scale), 40.f);
            MetricWidth = FMath::Min(TextWidth(Metric, 10, Scale), 68.f);
            DemoWidth = bDemo ? 31.f : 0.f;
            // Fit the ID and metric inside their grid cell without reducing text
            // size. The painter applies ellipsis using these same measured slots.
            float Overflow = FMath::Max(0.f, 81 + IdWidth + StatusWidth + MetricWidth + DemoWidth - MaxWidth);
            const float IdReduction = FMath::Min(Overflow, FMath::Max(0.f, IdWidth - 36));
            IdWidth -= IdReduction;
            Overflow -= IdReduction;
            const float MetricReduction = FMath::Min(Overflow, FMath::Max(0.f, MetricWidth - 28));
            MetricWidth -= MetricReduction;
            Overflow -= MetricReduction;
            IdWidth = FMath::Max(0.f, IdWidth - Overflow);
            StatusX = 35 + IdWidth + 6;
            DividerX = StatusX + StatusWidth + 7;
            MetricX = DividerX + 8;
            Size = FVector2D(MetricX + MetricWidth + DemoWidth + 25, 34);
        }
    };

    // Compact layout dimensions are logical pixels; the minimum physical text
    // scale below is shared with projection, hit testing and collision checks.
    struct FPainter
    {
        const FGeometry& Geometry;
        FSlateWindowElementList& Elements;
        mutable int32 Layer;
        float Scale;
        float Alpha = 1;
        float Zoom = 1;
        FVector2D Offset = FVector2D::ZeroVector;
        FVector2D At(FVector2D P) const { return (Offset+P*Zoom)*Scale; }
        FLinearColor Tint(FLinearColor C) const { C.A *= Alpha; return C; }
        void Box(FVector2D P, FVector2D S, FLinearColor Fill, float Radius = 4, FLinearColor Outline = FLinearColor::Transparent) const
        {
            FSlateRoundedBoxBrush Brush(FLinearColor::White, Radius * Scale * Zoom, Tint(Outline), Outline.A > 0 ? Scale * Zoom : 0);
            Brush.OutlineSettings.bUseBrushTransparency = false;
            FSlateDrawElement::MakeBox(Elements, ++Layer, Geometry.ToPaintGeometry(S * Scale * Zoom, FSlateLayoutTransform(At(P))), &Brush, ESlateDrawEffect::None, Tint(Fill));
        }
        void Line(FVector2D A, FVector2D B, FLinearColor C, float Width = 1) const
        {
            TArray<FVector2D> Points{At(A), At(B)};
            FSlateDrawElement::MakeLines(Elements, ++Layer, Geometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Tint(C), true, Width * Scale * Zoom);
        }
        float Text(FVector2D P, const FString& Value, float Size, FLinearColor C, float MaxWidth = 1000) const
        {
            const FSlateFontInfo TextFont = Font(Size, Scale * Zoom);
            FString Fitted = Value;
            const auto Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
            if (Measure->Measure(Fitted, TextFont).X > MaxWidth * Scale * Zoom)
            {
                while (!Fitted.IsEmpty() && Measure->Measure(Fitted + TEXT("…"), TextFont).X > MaxWidth * Scale * Zoom) Fitted.LeftChopInline(1);
                Fitted += TEXT("…");
            }
            FSlateDrawElement::MakeText(Elements, ++Layer, Geometry.ToPaintGeometry(FVector2D(MaxWidth, Size + 8) * Scale * Zoom, FSlateLayoutTransform(At(P))), Fitted, TextFont, ESlateDrawEffect::None, Tint(C));
            return Measure->Measure(Fitted, TextFont).X / (Scale * Zoom);
        }
        void Truck(FVector2D P, float S, FLinearColor C) const
        {
            auto L = [&](float X1, float Y1, float X2, float Y2) { Line(P + FVector2D(X1,Y1)*S, P + FVector2D(X2,Y2)*S, C, 1.5f); };
            L(0,2,15,2); L(15,2,15,15); L(15,15,0,15); L(0,15,0,2);
            L(15,6,21,6); L(21,6,25,11); L(25,11,25,15); L(25,15,15,15);
            Box(P+FVector2D(3,13)*S,FVector2D(5,5)*S,C,2.5f*S);
            Box(P+FVector2D(18,13)*S,FVector2D(5,5)*S,C,2.5f*S);
        }
        void Stacker(FVector2D P, float S, FLinearColor C) const
        {
            auto L = [&](float X1,float Y1,float X2,float Y2) { Line(P+FVector2D(X1,Y1)*S,P+FVector2D(X2,Y2)*S,C,1.5f); };
            L(3,7,13,7); L(13,7,13,16); L(13,16,3,16); L(3,16,3,7);
            L(16,0,16,17); L(19,0,19,17); L(16,0,19,0); L(19,17,27,17);
            L(3,7,0,3); L(0,3,5,3);
            Box(P+FVector2D(4,15)*S,FVector2D(5,5)*S,C,2.5f*S);
            Box(P+FVector2D(19,16)*S,FVector2D(4,4)*S,C,2*S);
        }
        void MannedForklift(FVector2D P, float S, FLinearColor C) const
        {
            auto L = [&](float X1,float Y1,float X2,float Y2) { Line(P+FVector2D(X1,Y1)*S,P+FVector2D(X2,Y2)*S,C,1.5f); };
            L(1,9,12,9); L(12,9,12,17); L(12,17,1,17); L(1,17,1,9);
            L(4,9,4,4); L(4,4,10,4); L(10,4,14,9);
            L(16,0,16,18); L(16,18,25,18);
            Box(P+FVector2D(2,15)*S,FVector2D(5,5)*S,C,2.5f*S);
            Box(P+FVector2D(11,15)*S,FVector2D(5,5)*S,C,2.5f*S);
            // Person silhouette distinguishes the staffed vehicle from a stacker.
            Box(P+FVector2D(20,0)*S,FVector2D(4,4)*S,C,2*S);
            L(19,9,19,6); L(19,6,21,4); L(21,4,23,4); L(23,4,25,6); L(25,6,25,9);
        }
    };
}

void UGHSDockTruckHUDWidget::NativeConstruct()
{
    Super::NativeConstruct();
    SetVisibility(ESlateVisibility::Visible);
    SetIsFocusable(false);
    DiscoverTrucks();
}

void UGHSDockTruckHUDWidget::DiscoverTrucks()
{
    Trucks.Reset();
    Stackers.Reset();
    MannedForklifts.Reset();
    if (!GetWorld()) return;
    UGHSMannedForkliftIdentityLibrary::ReconcileWorld(GetWorld());
    TSet<FString> KnownIds;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        AActor* Actor = *It;
        if (Actor->ActorHasTag(TEXT("NormalWarehouseMannedForklift")))
        {
            if (!UGHSMannedForkliftIdentityLibrary::IsSupportedActor(Actor)) continue;
            auto* Forklift = Actor->FindComponentByClass<UGHSMannedForkliftDataComponent>();
            if (!Forklift)
            {
                Forklift = NewObject<UGHSMannedForkliftDataComponent>(Actor);
                if (!Forklift->InitializeFromActorTags()) continue;
                Actor->AddInstanceComponent(Forklift);
                Forklift->RegisterComponent();
                Forklift->ApplyDemoState(FCString::Atoi(*Forklift->ForkliftId.Mid(5))-1);
            }
            else if (!Forklift->InitializeFromActorTags()) continue;
            if (!KnownIds.Contains(Forklift->ForkliftId))
            { KnownIds.Add(Forklift->ForkliftId); MannedForklifts.Add(Forklift); }
            continue;
        }
        if (Actor->ActorHasTag(TEXT("NormalWarehouseFloorStacker")))
        {
            auto* Stacker = Actor->FindComponentByClass<UGHSStackerDataComponent>();
            if (!Stacker)
            {
                Stacker = NewObject<UGHSStackerDataComponent>(Actor);
                if (!Stacker->InitializeFromActorTags()) continue;
                Actor->AddInstanceComponent(Stacker);
                Stacker->RegisterComponent();
                Stacker->ApplyDemoState(FCString::Atoi(*Stacker->StackerId.Mid(8))-1);
            }
            else if (!Stacker->InitializeFromActorTags()) continue;
            if (!KnownIds.Contains(Stacker->StackerId))
            { KnownIds.Add(Stacker->StackerId); Stackers.Add(Stacker); }
            continue;
        }
        if (!Actor->ActorHasTag(TEXT("IndependentDockTruck"))) continue;
        auto* Data = Actor->FindComponentByClass<UGHSDockTruckDataComponent>();
        if (!Data)
        {
            Data = NewObject<UGHSDockTruckDataComponent>(Actor);
            if (!Data->InitializeFromActorTags()) continue;
            Actor->AddInstanceComponent(Data);
            Data->RegisterComponent();
        }
        else if (!Data->InitializeFromActorTags()) continue;
        if (KnownIds.Contains(Data->TruckId)) continue;
        KnownIds.Add(Data->TruckId);
        Trucks.Add(Data);
    }
}

int32 UGHSDockTruckHUDWidget::GetRegisteredTruckCount() const
{
    int32 Count = 0;
    for (const auto& Data : Trucks) if (Data.IsValid() && IsValid(Data->GetOwner())) ++Count;
    return Count;
}
int32 UGHSDockTruckHUDWidget::GetRegisteredStackerCount() const
{
    int32 Count = 0;
    for (const auto& Data : Stackers) if (Data.IsValid() && IsValid(Data->GetOwner())) ++Count;
    return Count;
}
int32 UGHSDockTruckHUDWidget::GetRegisteredMannedForkliftCount() const
{
    int32 Count = 0;
    for (const auto& Data : MannedForklifts) if (Data.IsValid() && IsValid(Data->GetOwner())) ++Count;
    return Count;
}
int32 UGHSDockTruckHUDWidget::GetRegisteredEquipmentCount() const
{
    return GetRegisteredTruckCount()+GetRegisteredStackerCount()+GetRegisteredMannedForkliftCount();
}
UGHSMannedForkliftDataComponent* UGHSDockTruckHUDWidget::GetMannedForkliftData(const FString& Id) const
{
    for (const auto& Data : MannedForklifts) if (Data.IsValid() && IsValid(Data->GetOwner()) && Data->ForkliftId == Id) return Data.Get();
    return nullptr;
}
UGHSStackerDataComponent* UGHSDockTruckHUDWidget::GetStackerData(const FString& Id) const
{
    for (const auto& Data : Stackers) if (Data.IsValid() && IsValid(Data->GetOwner()) && Data->StackerId == Id) return Data.Get();
    return nullptr;
}
bool UGHSDockTruckHUDWidget::ReadEquipment(const FString& Id, FEquipmentData& Out) const
{
    Out = FEquipmentData();
    if (const auto* Data = GetMannedForkliftData(Id))
    {
        Out.Owner=Data->GetOwner(); Out.Id=Data->ForkliftId; Out.Title=TEXT("人工叉车"); Out.bMannedForklift=true;
        Out.bAvailable=Data->HasTelemetry(); Out.bDemo=Data->bIsDemoData;
        Out.TaskId=Data->TaskId; Out.Location=Data->Area; Out.DriverId=Data->DriverId; Out.Reason=Data->Reason;
        Out.bOffline=Data->Status==EGHSMannedForkliftStatus::Offline;
        Out.StateColor=Color(TEXT("788896"));
        switch(Data->Status)
        {
        case EGHSMannedForkliftStatus::Running: Out.StatusText=TEXT("运行"); Out.StateColor=Color(TEXT("16876A")); break;
        case EGHSMannedForkliftStatus::Idle: Out.StatusText=TEXT("待机"); Out.StateColor=Blue; break;
        case EGHSMannedForkliftStatus::Warning: Out.StatusText=TEXT("预警"); Out.StateColor=Color(TEXT("A66514")); Out.Severity=1; break;
        case EGHSMannedForkliftStatus::Fault: Out.StatusText=TEXT("故障"); Out.StateColor=Color(TEXT("BA4140")); Out.Severity=2; break;
        case EGHSMannedForkliftStatus::Offline: Out.StatusText=TEXT("离线"); break;
        default: Out.StatusText=TEXT("待接入"); break;
        }
        Out.LeftValue=Out.bAvailable?FString::Printf(TEXT("%.1f"),Data->LoadTonnes):TEXT("--");
        Out.RightValue=Out.bAvailable?FString::Printf(TEXT("%.1f"),Data->SpeedKmh):TEXT("--");
        Out.Metric=Out.bAvailable?Out.LeftValue+TEXT(" t"):TEXT("--");
        const float Now=GetWorld()?GetWorld()->GetTimeSeconds():0.f;
        const float Timestamp=Out.bOffline?Data->LastOnlineSeconds:Data->LastUpdateSeconds;
        FString Age=TEXT("时间未知");
        if (Timestamp>=0.f)
        {
            const int32 Seconds=FMath::Max(0,FMath::FloorToInt(Now-Timestamp));
            Age=Seconds>=60?FString::Printf(TEXT("%d 分钟前"),Seconds/60):FString::Printf(TEXT("%d 秒前"),Seconds);
        }
        Out.ConnectionText=Out.bOffline?TEXT("最后在线 · ")+Age:TEXT("已连接 · ")+Age;
        if (Data->Status==EGHSMannedForkliftStatus::AwaitingData) Out.ConnectionText=TEXT("等待设备数据");
        if (Out.bDemo) Out.ConnectionText=Out.bOffline?TEXT("演示数据 · 离线"):TEXT("演示数据 · 非实时");
        return true;
    }
    if (const auto* Data = GetStackerData(Id))
    {
        Out.Owner=Data->GetOwner(); Out.Id=Data->StackerId; Out.Title=TEXT("电动堆高车"); Out.bStacker=true;
        Out.bAvailable=Data->HasTelemetry(); Out.bDemo=Data->bIsDemoData; Out.TaskId=Data->TaskId; Out.Location=TEXT("地堆区");
        Out.bOffline=Data->Status==EGHSStackerStatus::Offline;
        Out.StateColor=Muted;
        switch(Data->Status)
        {
        case EGHSStackerStatus::Running: Out.StatusText=TEXT("运行"); Out.StateColor=Color(TEXT("16876A")); break;
        case EGHSStackerStatus::Idle: Out.StatusText=TEXT("待机"); Out.StateColor=Blue; break;
        case EGHSStackerStatus::Warning: Out.StatusText=TEXT("预警"); Out.StateColor=Color(TEXT("A66514")); Out.Severity=1; break;
        case EGHSStackerStatus::Fault: Out.StatusText=TEXT("故障"); Out.StateColor=Color(TEXT("BA4140")); Out.Severity=2; break;
        case EGHSStackerStatus::Offline: Out.StatusText=TEXT("离线"); break;
        default: Out.StatusText=TEXT("待接入"); break;
        }
        Out.LeftValue=Out.bAvailable?FString::FromInt(FMath::RoundToInt(Data->BatteryPercent)):TEXT("--");
        Out.RightValue=Out.bAvailable?FString::Printf(TEXT("%.2f"),Data->ForkHeightCm/100.f):TEXT("--");
        Out.Metric=Out.LeftValue+TEXT("%"); Out.Progress=Out.bAvailable?Data->BatteryPercent/100.f:0.f;
        return true;
    }
    if (const auto* Data = GetTruckData(Id))
    {
        Out.Owner=Data->GetOwner(); Out.Id=Data->TruckId; Out.Title=TEXT("装卸车辆"); Out.StatusText=StatusText(Data->Status);
        Out.StateColor=StatusColor(Data->Status); Out.bDemo=Data->bIsDemoData; Out.bAvailable=Data->HasTelemetry();
        Out.bOffline=Data->Status==EGHSDockTruckStatus::Offline;
        Out.Severity=Data->Status==EGHSDockTruckStatus::Fault?2:(Data->Status==EGHSDockTruckStatus::Warning?1:0);
        Out.LeftValue=Out.bAvailable?FString::FromInt(Data->LoadedPallets):TEXT("--");
        Out.RightValue=Out.bAvailable?FString::FromInt(Data->GetRemainingPallets()):TEXT("--");
        Out.Metric=CompactMetric(*Data); Out.Progress=Data->GetLoadingProgress(); Out.Location=Data->DockId; Out.TaskId=Data->OrderId;
        return true;
    }
    return false;
}
FString UGHSDockTruckHUDWidget::GroupTitle(const TArray<FString>& Ids) const
{
    bool bTruck=false,bStacker=false,bManned=false;
    for (const auto& Id : Ids)
    { bTruck |= GetTruckData(Id)!=nullptr; bStacker |= GetStackerData(Id)!=nullptr; bManned |= GetMannedForkliftData(Id)!=nullptr; }
    if (int32(bTruck)+int32(bStacker)+int32(bManned)>1) return TEXT("仓储设备");
    return bManned?TEXT("人工叉车"):(bStacker?TEXT("堆高车"):TEXT("装卸车辆"));
}
int32 UGHSDockTruckHUDWidget::GetVisibleLabelCount() const
{
    int32 Count = 0;
    for (const auto& Label : Labels) if (!Label.bRetiring) ++Count;
    return Count;
}
UGHSDockTruckDataComponent* UGHSDockTruckHUDWidget::GetTruckData(const FString& TruckId) const
{
    for (const auto& Data : Trucks) if (Data.IsValid() && IsValid(Data->GetOwner()) && Data->TruckId == TruckId) return Data.Get();
    return nullptr;
}
bool UGHSDockTruckHUDWidget::SelectTruckById(const FString& TruckId)
{
    return GetTruckData(TruckId) && SelectEquipmentById(TruckId);
}
bool UGHSDockTruckHUDWidget::SelectEquipmentById(const FString& Id)
{
    FEquipmentData Data;
    if (!ReadEquipment(Id,Data)) return false;
    if (DisplayedEquipment != Id)
    {
        DetailTime = 0;
        DetailTransitionProgress = 0;
        bDetailPlacementPending = true;
    }
    else if (DetailTime <= 0) bDetailPlacementPending = true;
    SelectedEquipment = DisplayedEquipment = Id;
    CloseCluster();
    return true;
}
void UGHSDockTruckHUDWidget::CloseCluster() { ExpandedKey.Empty(); }
void UGHSDockTruckHUDWidget::ClearSelection() { SelectedEquipment.Empty(); CloseCluster(); }
FString UGHSDockTruckHUDWidget::GetSelectedTruckId() const { return GetTruckData(SelectedEquipment) ? SelectedEquipment : FString(); }
FString UGHSDockTruckHUDWidget::GetSelectedEquipmentId() const { FEquipmentData Data; return ReadEquipment(SelectedEquipment,Data) ? SelectedEquipment : FString(); }
const UGHSDockTruckHUDWidget::FTruckLabel* UGHSDockTruckHUDWidget::FindLabelForTruck(const FString& TruckId) const
{
    for (const auto& Label : Labels) if (!Label.bRetiring && Label.TruckIds.Contains(TruckId)) return &Label;
    return nullptr;
}
FVector2D UGHSDockTruckHUDWidget::GetVisibleLabelPosition(const FString& TruckId) const
{
    if (const auto* Label = FindLabelForTruck(TruckId)) return Label->Position * DrawScale;
    return FVector2D(-1,-1);
}
TArray<FGHSTruckHUDLabelInfo> UGHSDockTruckHUDWidget::GetVisibleLabels() const
{
    TArray<FGHSTruckHUDLabelInfo> Result;
    for (const auto& Label : Labels)
    {
        if (Label.bRetiring) continue;
        auto& Info = Result.AddDefaulted_GetRef();
        Info.Key = Label.Key; Info.TruckIds = Label.TruckIds; Info.EquipmentIds = Label.TruckIds;
        Info.Position = Label.Position * DrawScale; Info.Size = Label.Size * DrawScale;
        Info.Opacity = Label.Opacity;
    }
    return Result;
}
bool UGHSDockTruckHUDWidget::ToggleCluster(const FString& Key)
{
    for (const auto& Label : Labels)
    {
        if (Label.bRetiring || Label.Key != Key || Label.TruckIds.Num() < 2) continue;
        if (ExpandedKey == Key) { CloseCluster(); return true; }
        SelectedEquipment.Empty();
        if (ExpandedMembers != Label.TruckIds)
        {
            ClusterTime = 0; ClusterTransitionProgress = 0;
        }
        ExpandedKey = Key; ExpandedMembers = Label.TruckIds; ClusterPage = 0;
        bClusterPlacementPending = true;
        return true;
    }
    return false;
}
TArray<FString> UGHSDockTruckHUDWidget::GetExpandedClusterMembers() const
{
    return ExpandedKey.IsEmpty() ? TArray<FString>() : ExpandedMembers;
}
bool UGHSDockTruckHUDWidget::SetClusterPage(int32 Page)
{
    if (ExpandedKey.IsEmpty() || Page < 0 || Page * RowsPerPage >= ExpandedMembers.Num()) return false;
    ClusterPage = Page;
    return true;
}
FVector2D UGHSDockTruckHUDWidget::GetMemberRowPosition(const FString& TruckId) const
{
    const int32 Index = ExpandedMembers.Find(TruckId) - ClusterPage * RowsPerPage;
    if (!bClusterListVisible || ExpandedKey.IsEmpty() || Index < 0 || Index >= RowsPerPage) return FVector2D(-1,-1);
    return ClusterListPosition + FVector2D(8,34+Index*32) * ClusterZoom * DrawScale;
}

void UGHSDockTruckHUDWidget::UpdateLabels(const TArray<GHSTruckHUDLayout::FGroup>& Groups, float DeltaSeconds)
{
    // A regroup fades at its old and new locations. Labels never travel from a
    // member's position to a distant aggregate centroid, or back on a split.
    TArray<FTruckLabel> Previous = MoveTemp(Labels);
    TArray<FTruckLabel> Next;
    auto Retire = [](FTruckLabel& Label)
    {
        Label.bRetiring = true; Label.Time = 0;
        Label.StartPosition = Label.TargetPosition = Label.Position;
        Label.StartSize = Label.TargetSize = Label.Size;
        Label.StartOpacity = Label.Opacity;
    };
    for (const auto& Group : Groups)
    {
        // A retiring visual may share a key with a relocated live label; only
        // the live instance owns hit testing, selection and subsequent updates.
        const auto* Existing = Previous.FindByPredicate([&](const FTruckLabel& L) { return !L.bRetiring && L.Key == Group.Key; });
        FTruckLabel Visual;
        if (Existing)
        {
            Visual = *Existing;
            if (GHSHUDMotion::IsRelocation(Visual.TargetPosition, Group.Position))
            {
                // A resize or large projection jump crossfades in place. Do
                // not spawn trails or restart the same fade every camera frame.
                const bool bAlreadyRetiring = Previous.ContainsByPredicate([&](const FTruckLabel& L)
                    { return L.bRetiring && L.Key == Group.Key; });
                if (Visual.Time >= LabelDuration && !bAlreadyRetiring)
                {
                    FTruckLabel Retiring = Visual;
                    Retire(Retiring);
                    Next.Add(MoveTemp(Retiring));
                    Visual.Time = 0; Visual.StartOpacity = 0;
                }
                Visual.StartPosition = Group.Position + GHSHUDMotion::EntryOffset();
                Visual.Position = Visual.StartPosition;
                Visual.Size = Visual.StartSize = Group.Size;
            }
            else
            {
                // Keep the fade's local offset attached to the current target
                // while that target moves, rather than creating another path.
                Visual.StartPosition += Group.Position - Visual.TargetPosition;
            }
        }
        else
        {
            Visual.StartPosition = Group.Position + GHSHUDMotion::EntryOffset();
            Visual.Position = Visual.StartPosition;
            Visual.Size = Visual.StartSize = Group.Size;
        }
        Visual.Key = Group.Key; Visual.TruckIds = Group.Members; Visual.Anchor = Group.Anchor;
        Visual.TargetPosition = Group.Position; Visual.TargetSize = Group.Size; Visual.bRetiring = false;
        Next.Add(MoveTemp(Visual));
    }
    for (auto& Old : Previous)
    {
        if (!Old.bRetiring && Groups.ContainsByPredicate([&](const GHSTruckHUDLayout::FGroup& G) { return G.Key == Old.Key; })) continue;
        if (!Old.bRetiring) Retire(Old);
        if (Old.Time < LabelDuration) Next.Add(MoveTemp(Old));
    }
    const float Follow = 1-FMath::Exp(-24*DeltaSeconds);
    for (auto& Label : Next)
    {
        const bool bWasTransitioning = Label.Time < LabelDuration;
        Label.Time = FMath::Min(LabelDuration, Label.Time + DeltaSeconds);
        const float T = GHSHUDMotion::Progress(Label.Time);
        if (Label.bRetiring)
        {
            Label.Position = Label.StartPosition;
            Label.Size = Label.StartSize;
        }
        else if (Label.Time < LabelDuration)
        {
            Label.Position = GHSHUDMotion::EnterPosition(Label.TargetPosition, Label.StartPosition - Label.TargetPosition, T);
            Label.Size = FMath::Lerp(Label.StartSize, Label.TargetSize, T);
        }
        else
        {
            Label.Position = bWasTransitioning ? Label.TargetPosition
                : GHSHUDMotion::FollowPosition(Label.Position, Label.TargetPosition, DeltaSeconds);
            Label.Size = bWasTransitioning ? Label.TargetSize : FMath::Lerp(Label.Size, Label.TargetSize, Follow);
        }
        Label.Opacity = FMath::Lerp(Label.StartOpacity, Label.bRetiring ? 0.f : 1.f, T);
    }
    Next.RemoveAll([](const FTruckLabel& L) { return L.bRetiring && L.Time >= LabelDuration; });
    Labels = MoveTemp(Next);
}

void UGHSDockTruckHUDWidget::UpdatePopups(FVector2D Canvas, float DeltaSeconds)
{
    FEquipmentData SelectedData,DisplayedData;
    const auto* DetailLabel = ReadEquipment(SelectedEquipment,SelectedData) ? FindLabelForTruck(SelectedEquipment) : nullptr;
    const bool bOpenDetail = DetailLabel != nullptr;
    if (bOpenDetail)
    {
        if (bDetailPlacementPending)
        {
            bDetailAbove = DetailLabel->Position.Y >= CardSize.Y+20;
            DetailBasePosition = DetailLabel->Position;
        }
        FVector2D Target = DetailLabel->Position + FVector2D(0,bDetailAbove ? -CardSize.Y-8 : DetailLabel->Size.Y+8);
        Target = ClampPanel(Target, CardSize, Canvas);
        if (!bDetailPlacementPending && GHSHUDMotion::IsRelocation(DetailBasePosition,Target))
        { bDetailPlacementPending=true; if (DetailTime>=PopupDuration) DetailTime=0; }
        DetailBasePosition = bDetailPlacementPending ? Target : GHSHUDMotion::FollowPosition(DetailBasePosition, Target, DeltaSeconds);
        bDetailPlacementPending = false;
    }
    DetailTime = FMath::Clamp(DetailTime + (bOpenDetail ? DeltaSeconds : -DeltaSeconds), 0.f, PopupDuration);
    DetailTransitionProgress = Ease(DetailTime / PopupDuration);
    DetailZoom = FMath::Lerp(.96f,1.f,DetailTransitionProgress);
    bDetailVisible = DetailTime > 0 && ReadEquipment(DisplayedEquipment,DisplayedData);
    FVector2D DetailOrigin = DetailBasePosition + CardSize*(1-DetailZoom)*.5 + FVector2D(0,(bDetailAbove ? 8 : -8)*(1-DetailTransitionProgress));
    DetailPosition = ClampPanel(DetailOrigin,CardSize*DetailZoom,Canvas)*DrawScale;
    DetailSize = CardSize*DetailZoom*DrawScale;
    if (DetailTime == 0 && SelectedEquipment.IsEmpty()) DisplayedEquipment.Empty();

    const FTruckLabel* ClusterLabel = nullptr;
    if (!ExpandedKey.IsEmpty())
    {
        ClusterLabel = Labels.FindByPredicate([&](const FTruckLabel& L) { return !L.bRetiring && L.Key == ExpandedKey; });
        if (!ClusterLabel)
        {
            // Follow a regrouping only while it still contains the full open
            // group. A split dismisses the picker rather than changing rows under a click.
            ClusterLabel = Labels.FindByPredicate([&](const FTruckLabel& L)
            {
                if (L.bRetiring || L.TruckIds.Num()<2) return false;
                for (const auto& Id : ExpandedMembers) if (!L.TruckIds.Contains(Id)) return false;
                return true;
            });
            if (ClusterLabel) { ExpandedKey = ClusterLabel->Key; ExpandedMembers = ClusterLabel->TruckIds; }
            else CloseCluster();
        }
    }
    ExpandedMembers.RemoveAll([&](const FString& Id) { FEquipmentData Data; return !ReadEquipment(Id,Data); });
    if (ExpandedMembers.Num() < 2) { CloseCluster(); ClusterLabel = nullptr; }
    ClusterPage = FMath::Clamp(ClusterPage, 0, FMath::Max(0,(ExpandedMembers.Num()-1)/RowsPerPage));
    const FVector2D ListSize(260,34+FMath::Min(RowsPerPage,ExpandedMembers.Num())*32+28);
    if (ClusterLabel)
    {
        if (bClusterPlacementPending) bClusterAbove = ClusterLabel->Position.Y+34+8+ListSize.Y > Canvas.Y-12;
        FVector2D Target = ClusterLabel->Position + FVector2D(0,bClusterAbove ? -ListSize.Y-8 : ClusterLabel->Size.Y+8);
        Target = ClampPanel(Target,ListSize,Canvas);
        if (!bClusterPlacementPending && GHSHUDMotion::IsRelocation(ClusterBasePosition,Target))
        { bClusterPlacementPending=true; if (ClusterTime>=PopupDuration) ClusterTime=0; }
        ClusterBasePosition = bClusterPlacementPending ? Target : GHSHUDMotion::FollowPosition(ClusterBasePosition,Target,DeltaSeconds);
        bClusterPlacementPending = false;
    }
    const bool bOpenCluster = ClusterLabel && !ExpandedKey.IsEmpty();
    ClusterTime = FMath::Clamp(ClusterTime + (bOpenCluster ? DeltaSeconds : -DeltaSeconds),0.f,PopupDuration);
    ClusterTransitionProgress = Ease(ClusterTime/PopupDuration);
    ClusterZoom = FMath::Lerp(.96f,1.f,ClusterTransitionProgress);
    bClusterListVisible = ClusterTime > 0;
    const FVector2D ListOrigin = ClusterBasePosition+ListSize*(1-ClusterZoom)*.5+FVector2D(0,-8*(1-ClusterTransitionProgress));
    ClusterListPosition = ClampPanel(ListOrigin,ListSize*ClusterZoom,Canvas)*DrawScale;
    ClusterListSize = ListSize*ClusterZoom*DrawScale;
}

void UGHSDockTruckHUDWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
    Super::NativeTick(MyGeometry, InDeltaTime);
    DiscoveryCountdown -= InDeltaTime;
    if (DiscoveryCountdown <= 0) { DiscoverTrucks(); DiscoveryCountdown = 1; }
    APlayerController* PC = GetOwningPlayer();
    const FVector2D View = MyGeometry.GetLocalSize();
    if (!PC || View.X < 10 || View.Y < 10) return;
    const float Delta = FMath::Clamp(InDeltaTime,0.f,.1f);
    const float DPI = FMath::Max(.01f,UWidgetLayoutLibrary::GetViewportScale(this));
    const FVector2D Pixels = View*DPI;
    const float PixelScale = FMath::Min(FMath::Max(DPI,.75f),float(FMath::Min(Pixels.X/640,Pixels.Y/540)));
    DrawScale = PixelScale/DPI;
    const FVector2D Canvas = View/DrawScale;
    LastCanvas = Canvas;
    const auto* CameraPawn = Cast<AGHSWarehouseCameraPawn>(PC->GetPawn());
    const bool bAggregate = !CameraPawn || CameraPawn->ShouldAggregateTruckHUD();
    const float CompactMaxWidth = FMath::Min(275.f,
        float(Canvas.X/(bAggregate ? GHSTruckHUDLayout::GridColumns : 1) - 24));
    TArray<GHSTruckHUDLayout::FItem> Candidates;
    TArray<FString> EquipmentIds;
    for (const auto& Data : Trucks) if (Data.IsValid()) EquipmentIds.Add(Data->TruckId);
    for (const auto& Data : Stackers) if (Data.IsValid()) EquipmentIds.Add(Data->StackerId);
    for (const auto& Data : MannedForklifts) if (Data.IsValid()) EquipmentIds.Add(Data->ForkliftId);
    for (const auto& Id : EquipmentIds)
    {
        FEquipmentData Data;
        if (!ReadEquipment(Id,Data) || Data.Owner->IsHidden()) continue;
        const FBox Bounds = Data.Owner->GetComponentsBoundingBox(true);
        if (!Bounds.IsValid) continue;
        const FVector Anchor(Bounds.GetCenter().X,Bounds.GetCenter().Y,Bounds.Max.Z+80);
        FVector2D Screen;
        if (!UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC,Anchor,Screen,true)) continue;
        Screen /= DrawScale;
        if (!Inside(Screen,FVector2D(8,8),Canvas-FVector2D(16,16))) continue;
        Candidates.Add({Id,Screen,FCompactLayout(Data.Id,Data.StatusText,Data.Metric,Data.bDemo,DrawScale,CompactMaxWidth).Size,
            Data.bMannedForklift ? TEXT("MannedForklift") : (Data.bStacker ? TEXT("Stacker") : TEXT("DockTruck"))});
    }
    UpdateLabels(Clusterer.Update(Candidates,Canvas,Delta,bAggregate),Delta);
    // Resize clamps the animated geometry too, not only the target.
    for (auto& Label : Labels) Label.Position = ClampPanel(Label.Position,Label.Size,Canvas);
    UpdatePopups(Canvas,Delta);
}

bool UGHSDockTruckHUDWidget::HandlePointerClick(FVector2D LocalPosition)
{
    if (LocalPosition.ContainsNaN() || DrawScale <= 0) return false;
    if (bDetailVisible && Inside(LocalPosition,DetailPosition,DetailSize))
    {
        const FVector2D Local = (LocalPosition-DetailPosition)/(DrawScale*DetailZoom);
        if (Inside(Local,CloseOrigin,CloseSize)) ClearSelection();
        return true;
    }
    if (bClusterListVisible && Inside(LocalPosition,ClusterListPosition,ClusterListSize))
    {
        const FVector2D Local = (LocalPosition-ClusterListPosition)/(DrawScale*ClusterZoom);
        if (ExpandedKey.IsEmpty()) return true; // consume the retiring panel's clicks
        if (Inside(Local,FVector2D(232,3),FVector2D(26,28))) CloseCluster();
        else if (Local.Y >= 34 && Local.Y < 34+RowsPerPage*32)
        {
            const int32 Index = ClusterPage*RowsPerPage+int32((Local.Y-34)/32);
            if (ExpandedMembers.IsValidIndex(Index)) SelectEquipmentById(ExpandedMembers[Index]);
        }
        else if (Local.Y >= ClusterListSize.Y/(DrawScale*ClusterZoom)-28)
        {
            if (Local.X >= 220) SetClusterPage(ClusterPage+1);
            else if (Local.X >= 182) SetClusterPage(ClusterPage-1);
        }
        return true;
    }
    const FVector2D P = LocalPosition/DrawScale;
    for (int32 Index = Labels.Num()-1; Index>=0; --Index)
    {
        const auto& Label = Labels[Index];
        if (Label.bRetiring || Label.Opacity<.15f || !Inside(P,Label.Position,Label.Size)) continue;
        if (Label.TruckIds.Num()>1) return ToggleCluster(Label.Key);
        if (Label.TruckIds.Num()==1)
        {
            if (GetSelectedEquipmentId()==Label.TruckIds[0]) { ClearSelection(); return true; }
            return SelectEquipmentById(Label.TruckIds[0]);
        }
    }
    CloseCluster();
    return false;
}
FReply UGHSDockTruckHUDWidget::NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (Event.GetEffectingButton() == EKeys::LeftMouseButton && HandlePointerClick(Geometry.AbsoluteToLocal(Event.GetScreenSpacePosition())))
    {
        if (auto* PC = Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
        return FReply::Handled();
    }
    return FReply::Unhandled();
}
FReply UGHSDockTruckHUDWidget::NativeOnMouseButtonDoubleClick(const FGeometry& Geometry, const FPointerEvent& Event)
{
    return NativeOnMouseButtonDown(Geometry, Event);
}

int32 UGHSDockTruckHUDWidget::NativePaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& CullingRect,
    FSlateWindowElementList& Elements, int32 LayerId, const FWidgetStyle& Style, bool bParentEnabled) const
{
    FPainter P{Geometry, Elements, Super::NativePaint(Args, Geometry, CullingRect, Elements, LayerId, Style, bParentEnabled), DrawScale};
    for (int32 Pass=0; Pass<2; ++Pass)
    for (const auto& Label : Labels)
    {
        if (Label.Opacity <= .001f || Label.bRetiring != (Pass==0)) continue;
        P.Alpha = Label.Opacity;
        const FVector2D O = Label.Position;
        const bool bSelected = !SelectedEquipment.IsEmpty() && Label.TruckIds.Contains(SelectedEquipment);
        const bool bExpanded = !ExpandedKey.IsEmpty() && ExpandedKey==Label.Key;
        const FVector2D End(FMath::Clamp(Label.Anchor.X,O.X+12,O.X+Label.Size.X-12),
            Label.Anchor.Y>O.Y+Label.Size.Y/2 ? O.Y+Label.Size.Y : O.Y);
        P.Line(Label.Anchor,FVector2D(Label.Anchor.X,End.Y),bSelected||bExpanded ? Blue : Border);
        P.Line(FVector2D(Label.Anchor.X,End.Y),End,bSelected||bExpanded ? Blue : Border);
        P.Box(Label.Anchor-FVector2D(3,3),FVector2D(6,6),bSelected||bExpanded ? Blue : Border,3);
        if (Label.TruckIds.Num()>1)
        {
            P.Box(O+FVector2D(4,4),Label.Size-FVector2D(8,0),Color(TEXT("E4ECF5")),5,Border);
            P.Box(O,Label.Size,Color(TEXT("F8FAFCF5")),5,bSelected||bExpanded ? Blue : Border);
            bool bOnlyStackers = true, bOnlyMannedForklifts = true, bAnyDemo = false;
            int32 HighestSeverity = 0;
            FLinearColor AlertColor = Blue;
            for (const FString& Id : Label.TruckIds)
            {
                FEquipmentData Member;
                if (!ReadEquipment(Id,Member)) continue;
                bOnlyStackers &= Member.bStacker;
                bOnlyMannedForklifts &= Member.bMannedForklift;
                bAnyDemo |= Member.bDemo;
                if (Member.Severity > HighestSeverity)
                { HighestSeverity=Member.Severity; AlertColor=Member.StateColor; }
            }
            if (bOnlyMannedForklifts) P.MannedForklift(O+FVector2D(9,8),.75f,Blue);
            else if (bOnlyStackers) P.Stacker(O+FVector2D(9,8),.75f,Blue);
            else P.Truck(O+FVector2D(10,9),.75f,Blue);
            P.Text(O+FVector2D(35,bOnlyMannedForklifts&&bAnyDemo?10:9),GroupTitle(Label.TruckIds),
                bOnlyMannedForklifts&&bAnyDemo?10:11,Ink,bOnlyMannedForklifts&&bAnyDemo?56:72);
            if (bOnlyMannedForklifts && bAnyDemo)
                P.Text(O+FVector2D(91,13),TEXT("演示"),7,Muted,20);
            P.Box(O+FVector2D(112,7),FVector2D(36,20),Color(TEXT("E4ECF5")),4);
            const FString Count = FString::FromInt(Label.TruckIds.Num());
            P.Text(O+FVector2D(130-TextWidth(Count,11,DrawScale)/2,10),Count,11,Blue,34);
            const float ArrowY = bExpanded ? -3 : 3;
            P.Line(O+FVector2D(162,17-ArrowY/2),O+FVector2D(166,17+ArrowY/2),Blue,1.2f);
            P.Line(O+FVector2D(166,17+ArrowY/2),O+FVector2D(170,17-ArrowY/2),Blue,1.2f);
            // Keep an alert visible even when individual labels are aggregated.
            if (HighestSeverity>0) P.Box(O+FVector2D(3,7),FVector2D(3,20),AlertColor,1);
            continue;
        }
        FEquipmentData Data;
        if (Label.TruckIds.Num()!=1 || !ReadEquipment(Label.TruckIds[0],Data)) continue;
        const FLinearColor State=Data.StateColor;
        const FCompactLayout Layout(Data.Id,Data.StatusText,Data.Metric,Data.bDemo,DrawScale,Label.Size.X);
        P.Box(O+FVector2D(0,2),Label.Size,Color(TEXT("24384B12")),5);
        P.Box(O,Label.Size,Color(TEXT("F8FAFCEB")),5,bSelected?Blue:Border);
        P.Box(O+FVector2D(0,7),FVector2D(3,20),State,1);
        if (Data.bMannedForklift) P.MannedForklift(O+FVector2D(9,8),.75f,Blue);
        else if (Data.bStacker) P.Stacker(O+FVector2D(9,8),.75f,Blue);
        else P.Truck(O+FVector2D(10,9),.75f,Blue);
        P.Text(O+FVector2D(35,9),Data.Id,12,Ink,Layout.IdWidth);
        P.Text(O+FVector2D(Layout.StatusX,11),Data.StatusText,10,State,Layout.StatusWidth);
        P.Line(O+FVector2D(Layout.DividerX,9),O+FVector2D(Layout.DividerX,25),Border);
        P.Text(O+FVector2D(Layout.MetricX,11),Data.Metric,10,Muted,Layout.MetricWidth);
        if (Data.bDemo)
        {
            const float DemoX=Layout.MetricX+Layout.MetricWidth+4;
            P.Box(O+FVector2D(DemoX,10),FVector2D(28,15),Color(TEXT("E4ECF5")),3);
            P.Text(O+FVector2D(DemoX+3,12),TEXT("演示"),8,Muted,24);
        }
        const float ToggleX=Label.Size.X-13;
        P.Line(O+FVector2D(ToggleX-4,17),O+FVector2D(ToggleX+4,17),Blue,1.2f);
        if (!bSelected) P.Line(O+FVector2D(ToggleX,13),O+FVector2D(ToggleX,21),Blue,1.2f);
    }
    if (bClusterListVisible)
    {
        P.Alpha=ClusterTransitionProgress; P.Zoom=ClusterZoom; P.Offset=ClusterListPosition/DrawScale;
        const FVector2D Size=ClusterListSize/(DrawScale*ClusterZoom);
        P.Box(FVector2D(0,3),Size,Color(TEXT("24384B20")),6);
        P.Box(FVector2D::ZeroVector,Size,Color(TEXT("F8FAFCFA")),6,Border);
        P.Text(FVector2D(12,9),FString::Printf(TEXT("%s · %d"),*GroupTitle(ExpandedMembers),ExpandedMembers.Num()),12,Ink,210);
        P.Line(FVector2D(241,12),FVector2D(249,20),Muted,1.2f);
        P.Line(FVector2D(249,12),FVector2D(241,20),Muted,1.2f);
        P.Line(FVector2D(12,34),FVector2D(248,34),Border);
        const int32 End=FMath::Min(ExpandedMembers.Num(),(ClusterPage+1)*RowsPerPage);
        for (int32 Index=ClusterPage*RowsPerPage; Index<End; ++Index)
        {
            const float Y=34+(Index%RowsPerPage)*32;
            FEquipmentData Member;
            if (!ReadEquipment(ExpandedMembers[Index],Member)) continue;
            if (Index%2==0) P.Box(FVector2D(6,Y+2),FVector2D(248,28),Color(TEXT("EDF2F7")),3);
            if (Member.bMannedForklift) P.MannedForklift(FVector2D(11,Y+7),.6f,Blue);
            else if (Member.bStacker) P.Stacker(FVector2D(11,Y+7),.6f,Blue);
            else P.Truck(FVector2D(12,Y+8),.6f,Blue);
            P.Text(FVector2D(35,Y+8),Member.Id,11,Ink,100);
            P.Text(FVector2D(145,Y+9),Member.StatusText,10,Member.StateColor,47);
            if (Member.bDemo)
            {
                P.Box(FVector2D(200,Y+8),FVector2D(28,16),Color(TEXT("E4ECF5")),3);
                P.Text(FVector2D(203,Y+11),TEXT("演示"),8,Muted,24);
            }
            P.Line(FVector2D(238,Y+12),FVector2D(242,Y+16),Blue);
            P.Line(FVector2D(242,Y+16),FVector2D(238,Y+20),Blue);
        }
        const float Bottom=Size.Y-28;
        const int32 Pages=FMath::Max(1,FMath::DivideAndRoundUp(ExpandedMembers.Num(),RowsPerPage));
        P.Line(FVector2D(12,Bottom),FVector2D(248,Bottom),Border);
        P.Text(FVector2D(12,Bottom+7),FString::Printf(TEXT("%d / %d 页"),ClusterPage+1,Pages),9,Muted,125);
        const FLinearColor PreviousColor=ClusterPage>0?Blue:Border;
        const FLinearColor NextColor=ClusterPage+1<Pages?Blue:Border;
        P.Line(FVector2D(197,Bottom+9),FVector2D(193,Bottom+14),PreviousColor,1.2f);
        P.Line(FVector2D(193,Bottom+14),FVector2D(197,Bottom+19),PreviousColor,1.2f);
        P.Line(FVector2D(234,Bottom+9),FVector2D(238,Bottom+14),NextColor,1.2f);
        P.Line(FVector2D(238,Bottom+14),FVector2D(234,Bottom+19),NextColor,1.2f);
    }
    FEquipmentData Data;
    if (bDetailVisible && ReadEquipment(DisplayedEquipment,Data))
    {
        P.Alpha=DetailTransitionProgress; P.Zoom=DetailZoom; P.Offset=DetailPosition/DrawScale;
        const FVector2D O = FVector2D::ZeroVector;
        const FLinearColor State = Data.StateColor;
        P.Box(O+FVector2D(0,3),CardSize,Color(TEXT("24384B20")),6);
        P.Box(O,CardSize,Color(TEXT("F8FAFCF5")),6,Border);
        P.Box(O+FVector2D(12,12),FVector2D(28,28),Color(TEXT("E4ECF5")),4);
        if (Data.bMannedForklift) P.MannedForklift(O+FVector2D(15,16),.8f,Blue);
        else if (Data.bStacker) P.Stacker(O+FVector2D(15,16),.8f,Blue);
        else P.Truck(O+FVector2D(16,17),.8f,Blue);
        P.Text(O+FVector2D(48,8),Data.Title,14,Ink,172);
        P.Text(O+FVector2D(48,30),Data.Id,10,Muted,172);
        P.Box(O+FVector2D(230,11),FVector2D(58,22),State.CopyWithNewOpacity(.10f),4);
        P.Text(O+FVector2D(239,15),Data.StatusText,10,State,44);
        const FVector2D CloseCenter = O + CloseOrigin + CloseSize/2;
        P.Line(CloseCenter-FVector2D(4,4),CloseCenter+FVector2D(4,4),Muted,1.5f);
        P.Line(CloseCenter+FVector2D(4,-4),CloseCenter+FVector2D(-4,4),Muted,1.5f);
        P.Line(O+FVector2D(12,50),O+FVector2D(308,50),Border);
        if (Data.bMannedForklift)
        {
            P.Box(O+FVector2D(12,0),FVector2D(32,3),Blue,0);
            P.Text(O+FVector2D(12,58),TEXT("当前载荷"),10,Muted);
            P.Text(O+FVector2D(168,58),TEXT("行驶速度"),10,Muted);
            const float LoadWidth=P.Text(O+FVector2D(12,75),Data.LeftValue,26,Ink,108);
            const float SpeedWidth=P.Text(O+FVector2D(168,75),Data.RightValue,26,Ink,84);
            P.Text(O+FVector2D(18+LoadWidth,87),TEXT("t"),11,Muted,16);
            P.Text(O+FVector2D(174+SpeedWidth,87),TEXT("km/h"),10,Muted,43);
            P.Text(O+FVector2D(12,116),TEXT("驾驶员 ")+(Data.DriverId.IsEmpty()?TEXT("--"):Data.DriverId),10,Ink,151);
            const FString Area=Data.Location.IsEmpty()?TEXT("区域 --"):Data.Location;
            P.Text(O+FVector2D(174,116),Area,10,Muted,134);
            const FString Summary=Data.Reason.IsEmpty()?TEXT("任务信息待接入"):Data.Reason;
            P.Text(O+FVector2D(12,137),Summary,10,Data.Severity>0?State:Ink,193);
            P.Text(O+FVector2D(218,137),Data.TaskId.IsEmpty()?TEXT("--"):Data.TaskId,10,Muted,90);
            P.Text(O+FVector2D(12,158),Data.ConnectionText,9,Muted,280);
            return P.Layer;
        }
        P.Text(O+FVector2D(12,58),Data.bStacker?TEXT("剩余电量"):TEXT("已装数量"),10,Muted);
        P.Text(O+FVector2D(168,58),Data.bStacker?TEXT("货叉高度"):TEXT("剩余数量"),10,Muted);
        const float LeftWidth = P.Text(O+FVector2D(12,75),Data.LeftValue,26,Ink,112);
        const float RightWidth = P.Text(O+FVector2D(168,75),Data.RightValue,26,Ink,112);
        P.Text(O+FVector2D(18+LeftWidth,92),Data.bStacker?TEXT("%"):TEXT("托"),10,Muted,15);
        P.Text(O+FVector2D(174+RightWidth,92),Data.bStacker?TEXT("m"):TEXT("托"),10,Muted,15);
        P.Line(O+FVector2D(152,60),O+FVector2D(152,103),Border);
        P.Box(O+FVector2D(12,113),FVector2D(296,3),Color(TEXT("DCE5ED")),1.5f);
        if (Data.bAvailable && Data.Progress > 0)
            P.Box(O+FVector2D(12,113),FVector2D(296*Data.Progress,3),State,1.5f);
        P.Text(O+FVector2D(12,127),Data.bStacker?TEXT("区域"):TEXT("月台"),10,Muted,28);
        P.Text(O+FVector2D(45,127),Data.Location,10,Ink,99);
        P.Text(O+FVector2D(168,127),TEXT("任务"),10,Muted,28);
        P.Text(O+FVector2D(201,127),Data.TaskId.IsEmpty() ? TEXT("--") : Data.TaskId,10,Ink,107);
        P.Line(O+FVector2D(12,151),O+FVector2D(308,151),Border);
        P.Box(O+FVector2D(12,167),FVector2D(4,4),State,2);
        FString ConnectionText = Data.bAvailable ? TEXT("数据已接入") : (Data.bOffline ? TEXT("连接中断 · 数值已清空") : TEXT("等待设备数据"));
        if (Data.bDemo) ConnectionText = Data.bOffline ? TEXT("演示数据 · 离线") : TEXT("演示数据");
        P.Text(O+FVector2D(24,160),ConnectionText,9,Muted,182);
        const FString ProgressText = Data.bStacker
            ? (Data.bAvailable ? FString::Printf(TEXT("电量 %d%%"),FMath::RoundToInt(Data.Progress*100)) : TEXT("电量 --"))
            : (Data.bAvailable ? FString::Printf(TEXT("装载进度 %d%%"),FMath::RoundToInt(Data.Progress*100)) : TEXT("装载进度 --"));
        P.Text(O+FVector2D(214,160),ProgressText,9,Blue,94);
    }
    return P.Layer;
}
