#include "GHSTwinHUDWidget.h"
#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSHUDMotion.h"
#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/EditableTextBox.h"
#include "SWebBrowser.h"
#include "WebBrowserModule.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Rendering/DrawElements.h"
#include "GameFramework/SpringArmComponent.h"
#include "Camera/CameraComponent.h"

namespace
{
FLinearColor C(const TCHAR* Hex) { return FLinearColor::FromSRGBColor(FColor::FromHex(Hex)); }
bool Inside(FVector2D P, FVector2D At, FVector2D Size) { return P.X>=At.X && P.Y>=At.Y && P.X<At.X+Size.X && P.Y<At.Y+Size.Y; }
FSlateFontInfo Font(int32 Size) { return FSlateFontInfo(FPaths::ProjectContentDir()/TEXT("GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf"), Size); }
}

TSharedRef<SWidget> UGHSTwinBrowser::RebuildWidget()
{
    // Direct Slate hosting does not load the WebBrowserWidget plugin's startup hook.
    IWebBrowserModule::Get();
    FString File = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/web/index.html"));
    File.ReplaceInline(TEXT("\\"),TEXT("/"));
    SAssignNew(Browser,SWebBrowser)
        .InitialURL(TEXT("file:///")+File).ShowControls(false).ShowAddressBar(false)
        .SupportsTransparency(false).ShowInitialThrobber(true).BrowserFrameRate(60)
        .BackgroundColor(FColor::White)
        .OnBeforePopup_Lambda([](FString,FString){return true;})
        .OnBeforeNavigation_Lambda([](const FString& URL,const FWebNavigationRequest&){return !URL.StartsWith(TEXT("file:///"));})
        .OnSuppressContextMenu_Lambda([](){return true;})
        .OnLoadCompleted_Lambda([](){UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_BROWSER_DOCUMENT_LOADED"));})
        .OnLoadError_Lambda([](){UE_LOG(LogTemp,Error,TEXT("GHS_TWIN_BROWSER_DOCUMENT_FAILED"));});
    return Browser.ToSharedRef();
}
void UGHSTwinBrowser::Bind(UObject* Target) { if(Browser) Browser->BindUObject(TEXT("twin"),Target,true); }
void UGHSTwinBrowser::Evaluate(const FString& Script) { if(Browser) Browser->ExecuteJavascript(Script); }
void UGHSTwinBrowser::ReleaseSlateResources(bool bChildren) { Super::ReleaseSlateResources(bChildren); Browser.Reset(); }

TSharedRef<SWidget> UGHSTwinHUDWidget::RebuildWidget()
{
    if (!WidgetTree) WidgetTree=NewObject<UWidgetTree>(this,TEXT("TwinWidgetTree"));
    UCanvasPanel* Root = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(),TEXT("TwinCanvas"));
    Root->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
    Root->SetClipping(EWidgetClipping::ClipToBounds);
    WidgetTree->RootWidget=Root;
    Panel=WidgetTree->ConstructWidget<UGHSTwinBrowser>(UGHSTwinBrowser::StaticClass(),TEXT("BusinessPanel"));
    PanelSlot=Root->AddChildToCanvas(Panel);
    PanelSlot->SetPosition(FVector2D(1440,64)); PanelSlot->SetSize(FVector2D(480,1016));
    SearchBox=WidgetTree->ConstructWidget<UEditableTextBox>(UEditableTextBox::StaticClass(),TEXT("SceneSearch"));
    SearchBox->SetHintText(FText::FromString(TEXT("搜索设备、月台或物料")));
    SearchBox->WidgetStyle.SetFont(Font(13));
    SearchBox->WidgetStyle.SetForegroundColor(C(TEXT("25364B")));
    SearchBox->WidgetStyle.SetReadOnlyForegroundColor(C(TEXT("5B6C82")));
    SearchBox->OnTextCommitted.AddDynamic(this,&UGHSTwinHUDWidget::SearchCommitted);
    SearchSlot=Root->AddChildToCanvas(SearchBox);
    return Super::RebuildWidget();
}
void UGHSTwinHUDWidget::NativeConstruct()
{
    Super::NativeConstruct();
    SetVisibility(ESlateVisibility::SelfHitTestInvisible);
    if (Panel) Panel->Bind(this);
    GHSTwinSelection::BootstrapComponents(GetWorld());
    SceneData.Refresh(GetWorld());
    UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_UI_STARTED %s"),*GetWorld()->GetMapName());
}
void UGHSTwinHUDWidget::NativeDestruct() { SceneData.Refresh(nullptr); PreviousPositions.Empty(); Labels.Empty(); Super::NativeDestruct(); }
FString UGHSTwinHUDWidget::GetSnapshot() const { return SceneData.SnapshotJson(SelectedId); }
void UGHSTwinHUDWidget::PushSnapshot(bool bExplicitSelection)
{
    if(Panel) Panel->Evaluate(FString(bExplicitSelection?TEXT("window.twinSelect && window.twinSelect("):TEXT("window.twinReceive && window.twinReceive("))+GetSnapshot()+TEXT(");"));
}
FVector2D UGHSTwinHUDWidget::GetPanelVisualPosition() const
{
    return PanelSlot && Panel?PanelSlot->GetPosition()+Panel->GetRenderTransform().Translation:FGHSTwinLayout::Calculate(ViewSize).PanelPosition;
}
FVector2D UGHSTwinHUDWidget::GetPanelVisualSize() const
{
    return PanelSlot?PanelSlot->GetSize():FGHSTwinLayout::Calculate(ViewSize).PanelSize;
}
float UGHSTwinHUDWidget::GetPanelOpacity() const { return Panel?Panel->GetRenderOpacity():1.f; }
bool UGHSTwinHUDWidget::IsScenePoint(FVector2D Position) const
{
    if(!Inside(Position,FVector2D(0,Layout.HeaderHeight),FVector2D(ViewSize.X,ViewSize.Y-Layout.HeaderHeight))) return false;
    // Input follows the visible moving panel, not the area it occupied when open.
    return PanelVisibilityProgress<=0 || !Inside(Position,GetPanelVisualPosition(),GetPanelVisualSize());
}
void UGHSTwinHUDWidget::Navigate(const FString& Page)
{
    static const TSet<FString> Allowed{TEXT("overview"),TEXT("inventory"),TEXT("orders"),TEXT("devices"),TEXT("alerts"),TEXT("trace"),TEXT("settings")};
    if(Allowed.Contains(Page) && Panel) Panel->Evaluate(FString::Printf(TEXT("window.twinNavigate && window.twinNavigate('%s');"),*Page));
}
void UGHSTwinHUDWidget::SearchCommitted(const FText& Text,ETextCommit::Type Method)
{
    if(Method!=ETextCommit::OnEnter || !Panel) return;
    const FString Query=Text.ToString().TrimStartAndEnd();
    if(Query.IsEmpty()) return;
    if(!SelectObject(Query.ToUpper()))
    {
        FString Encoded; auto Writer=TJsonWriterFactory<>::Create(&Encoded); Writer->WriteValue(Query); Writer->Close();
        bPanelCollapsed=false;
        Panel->Evaluate(TEXT("window.twinSearch && window.twinSearch(")+Encoded+TEXT(");"));
    }
}
void UGHSTwinHUDWidget::Command(const FString& Json)
{
    TSharedPtr<FJsonObject> Object;
    if(Json.Len()>16384 || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Object) || !Object) return;
    FString Action,Id; Object->TryGetStringField(TEXT("action"),Action); Object->TryGetStringField(TEXT("id"),Id);
    if(Action!=TEXT("report") && Action!=TEXT("ready")) if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
    if(Action==TEXT("ready")) { bBrowserReady=true; PushSnapshot(); UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_BROWSER_READY")); }
    else if(Action==TEXT("select")) SelectObject(Id);
    else if(Action==TEXT("focus")) Focus(Id);
    else if(Action==TEXT("clear")) ClearSelection();
    else if(Action==TEXT("overview")) Overview();
    else if(Action==TEXT("layers"))
    {
        Object->TryGetBoolField(TEXT("equipment"),bEquipment); Object->TryGetBoolField(TEXT("racks"),bRacks); Object->TryGetBoolField(TEXT("pois"),bShowPOIs);
        SceneData.ApplyLayers(bEquipment,bRacks);
    }
    else if(Action==TEXT("poiDensity")) Object->TryGetStringField(TEXT("value"),Density);
    else if(Action==TEXT("preset"))
    {
        FString Value; Object->TryGetStringField(TEXT("value"),Value);
        if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
        {
            if(Value==TEXT("top"))
            {
                const float Distance=FMath::Min(95000.f,float(Cam->OverviewDistance*ViewSize.X/FMath::Max(1.,Layout.SceneSize.X)));
                Cam->TransitionToPose(Cam->OverviewCenter,Distance,FRotator(-78,Cam->OverviewYaw,0),ViewSize,Layout.ScenePosition+Layout.SceneSize*.5,true);
            }
            else if(Value==TEXT("racks") || Value==TEXT("floor")) FocusRegion(Value);
            else Overview();
        }
    }
    else if(Action==TEXT("report")) { LastBrowserReport=Json; UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_BROWSER_REPORT %s"),*Json); }
}
bool UGHSTwinHUDWidget::SelectObject(const FString& Id,bool bFocus)
{
    if(Id.StartsWith(TEXT("RACK:"))) return false;
    FVector Location,Extent; if(!SceneData.Resolve(Id,Location,Extent)) return false;
    SelectedId=Id; ActiveRegionId.Empty(); bPanelCollapsed=false;
    // Selection may open a previously collapsed panel. Use its final content area once.
    Layout=FGHSTwinLayout::Calculate(ViewSize,false);
    if(bFocus) Focus(Id); PushSnapshot(true); return true;
}
void UGHSTwinHUDWidget::ClearSelection() { SelectedId.Empty(); ActiveRegionId.Empty(); PushSnapshot(); if(Panel) Panel->Evaluate(TEXT("window.twinClearSelection && window.twinClearSelection();")); }
void UGHSTwinHUDWidget::Overview()
{
    ClearSelection();
    if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
    {
        const auto Destination=FGHSTwinLayout::Calculate(ViewSize,bPanelCollapsed);
        const float Distance=FMath::Min(95000.f,float(Cam->OverviewDistance*ViewSize.X/FMath::Max(1.,Destination.SceneSize.X)));
        const FRotator Rotation(Cam->OverviewPitch,Cam->OverviewYaw,0);
        Cam->TransitionToPose(Cam->OverviewCenter,Distance,Rotation,ViewSize,Destination.ScenePosition+Destination.SceneSize*.5,true);
    }
}
void UGHSTwinHUDWidget::Focus(const FString& Id)
{
    FVector Location,Extent; if(!SceneData.Resolve(Id,Location,Extent)) return;
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
    if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
    {
        FRotator Rotation=Cam->GetActorRotation(); Rotation.Pitch=-40;
        // Charging bays are best inspected from above, avoiding the tall charger backs.
        if(Id.StartsWith(TEXT("AGV-")) || Id.StartsWith(TEXT("CH-"))) Rotation.Pitch=ViewSize.X<900?-78:-65;
        const double Pitch=FMath::DegreesToRadians(-Rotation.Pitch);
        const float Distance=FMath::Clamp(float(FMath::Max(Extent.GetMax()*7,(Location.Z+550)/FMath::Sin(Pitch))),1600.f,18000.f);
        Cam->FocusOnTarget(Location,Distance,Rotation,ViewSize,Layout.ScenePosition+Layout.SceneSize*.5);
    }
}
void UGHSTwinHUDWidget::FocusRegion(const FString& Region)
{
    FVector Center,Extent; if(!SceneData.RegionBounds(Region,Center,Extent)) return;
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
    if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
    {
        ClearSelection(); ActiveRegionId=TEXT("REGION:")+Region;
        const double Tan=FMath::Tan(FMath::DegreesToRadians(Cam->WarehouseCamera->FieldOfView*.5));
        const double Fill=FMath::Clamp(FMath::Min(Layout.SceneSize.X/ViewSize.X,Layout.SceneSize.Y/ViewSize.X),.12,1.);
        const float Distance=FMath::Clamp(float(Extent.Size()/(Tan*Fill)*1.12),5000.f,95000.f);
        Cam->FocusOnTarget(Center,Distance,FRotator(-58,Cam->OverviewYaw,0),ViewSize,Layout.ScenePosition+Layout.SceneSize*.5,.95f);
    }
}
bool UGHSTwinHUDWidget::HandleChromeClick(FVector2D Position)
{
    if(Position.Y<Layout.HeaderHeight && Position.X>ViewSize.X-112)
    { bPanelCollapsed=!bPanelCollapsed; return true; }
    if(Inside(Position,FVector2D(20,Layout.HeaderHeight+16),FVector2D(104,36)))
    { Overview(); return true; }
    if(Layout.SceneSize.X>660 && Position.Y>=Layout.HeaderHeight+68 && Position.Y<Layout.HeaderHeight+100 && Position.X>=20 && Position.X<424)
    {
        const int32 Index=FMath::Clamp(int32((Position.X-20)/104),0,3);
        PointFilter=Index==1?TEXT("rack"):Index==2?TEXT("truck"):Index==3?TEXT("charger"):TEXT("all");
        return true;
    }
    const FVector2D Tool(ViewSize.X<900 ? ViewSize.X-60 : Layout.SceneSize.X-60,Layout.ScenePosition.Y+Layout.SceneSize.Y-132);
    if(Inside(Position,Tool,FVector2D(40,112)))
    {
        if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
        { const double Y=Position.Y-Tool.Y; if(Y<37) Cam->ZoomSteps(1); else if(Y<74) Cam->ZoomSteps(-1); else Overview(); }
        return true;
    }
    return false;
}
bool UGHSTwinHUDWidget::HandleSceneClick(FVector2D Position)
{
    if(HandleChromeClick(Position)) return true;
    if(!IsScenePoint(Position)) return false;
    for(int32 I=Labels.Num()-1; I>=0; --I) if(Inside(Position,Labels[I].Position,Labels[I].Size))
    {
        if(Labels[I].Id.StartsWith(TEXT("REGION:"))) { FocusRegion(Labels[I].Id.Mid(7)); return true; }
        if(Labels[I].Id.StartsWith(TEXT("GROUP:")))
        {
            bPanelCollapsed=false;
            if(Labels[I].Id==TEXT("GROUP:rack")) Navigate(TEXT("inventory"));
            else if(Panel) Panel->Evaluate(FString::Printf(TEXT("window.twinFilterType && window.twinFilterType('%s');"),*Labels[I].Id.Mid(6)));
            return true;
        }
        return SelectObject(Labels[I].Id);
    }
    FString Id; if(SceneData.Pick(GetOwningPlayer(),Position,Id)) return SelectObject(Id);
    ClearSelection(); return true;
}
void UGHSTwinHUDWidget::NativeTick(const FGeometry& Geometry,float DeltaSeconds)
{
    Super::NativeTick(Geometry,DeltaSeconds);
    const bool bViewportChanged=!ViewSize.Equals(Geometry.GetLocalSize(),.5);
    ViewSize=Geometry.GetLocalSize(); if(ViewSize.X<1 || ViewSize.Y<1) return;
    PanelMotion.Advance(DeltaSeconds,bPanelCollapsed);
    PanelVisibilityProgress=PanelMotion.Progress;
    Layout=FGHSTwinLayout::Calculate(ViewSize,bPanelCollapsed && PanelVisibilityProgress<=0);
    if(bInitialViewPending && GetOwningPlayerPawn()) { bInitialViewPending=false; Overview(); }
    // A panel toggle changes UI/input bounds only; it must never initiate camera focus.
    else if(bViewportChanged && !SelectedId.IsEmpty()) Focus(SelectedId);
    // Keep the CEF viewport at its expanded size throughout and after the slide.
    // Resizing it to zero on close causes a relayout/blank frame on the next open.
    const auto Expanded=FGHSTwinLayout::Calculate(ViewSize);
    if(PanelSlot) { PanelSlot->SetPosition(Expanded.PanelPosition); PanelSlot->SetSize(Expanded.PanelSize); }
    if(Panel)
    {
        Panel->SetVisibility(PanelVisibilityProgress<=0 ? ESlateVisibility::Collapsed : ESlateVisibility::Visible);
        Panel->SetRenderOpacity(1.f);
        Panel->SetRenderTranslation(PanelMotion.Position(Expanded)-Expanded.PanelPosition);
    }
    if(SearchSlot) { SearchSlot->SetPosition(FVector2D(FMath::Max(140.,Layout.SceneSize.X-384),Layout.HeaderHeight+16)); SearchSlot->SetSize(FVector2D(FMath::Min(360.,Layout.SceneSize.X-160),36)); }
    if(SearchBox) SearchBox->SetVisibility(Layout.SceneSize.X>=600 ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
    const double Now=GetWorld()->GetTimeSeconds();
    if(Now>=NextRefresh) { GHSTwinSelection::BootstrapComponents(GetWorld()); SceneData.Refresh(GetWorld()); PushSnapshot(); NextRefresh=Now+2; }
    Labels.Empty();
    if(!bShowPOIs || !GetOwningPlayer()) return;
    auto Points=SceneData.Points();
    if(!SelectedId.IsEmpty() && !Points.ContainsByPredicate([this](const FGHSTwinPoint& P){return P.Id==SelectedId;}))
    { FVector Location,Extent; if(SceneData.Resolve(SelectedId,Location,Extent)) Points.Add({SelectedId,TEXT("选中物料"),TEXT("material"),TEXT("scene"),Location+FVector(0,0,Extent.Z+80),false}); }
    Points.RemoveAll([this](const FGHSTwinPoint& P){return P.Id!=SelectedId && PointFilter!=TEXT("all") && P.Kind!=PointFilter;});
    if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()); Cam && Cam->SpringArmComponent->TargetArmLength>14000 && Density!=TEXT("all"))
    {
        TMap<FString,FGHSTwinPoint> Groups; TMap<FString,int32> Counts; TArray<FGHSTwinPoint> Chosen;
        for(const auto& P:Points)
        {
            if(P.Id==SelectedId || P.Id.StartsWith(TEXT("REGION:"))) { Chosen.Add(P); continue; }
            auto& Group=Groups.FindOrAdd(P.Kind); Group.Kind=P.Kind; Group.Location+=P.Location; Group.bAlert|=P.bAlert;
            if(P.Status==TEXT("fault")) Group.Status=TEXT("fault"); else if(P.bAlert && Group.Status!=TEXT("fault")) Group.Status=TEXT("warning");
            ++Counts.FindOrAdd(P.Kind);
        }
        const TMap<FString,FString> Names{{TEXT("agv"),TEXT("AGV")},{TEXT("forklift"),TEXT("人工叉车")},{TEXT("stacker"),TEXT("堆高车")},{TEXT("truck"),TEXT("装卸车")},{TEXT("charger"),TEXT("充电设施")},{TEXT("rack"),TEXT("货架区")}};
        for(auto& Entry:Groups) { auto& P=Entry.Value; P.Location/=Counts[Entry.Key]; P.Id=TEXT("GROUP:")+Entry.Key; const FString* Name=Names.Find(Entry.Key); P.Title=Entry.Key==TEXT("rack")?TEXT("货架区域"):FString::Printf(TEXT("%s · %d"),Name?**Name:*Entry.Key,Counts[Entry.Key]); Chosen.Add(P); }
        Points=MoveTemp(Chosen);
    }
    Points.StableSort([this](const FGHSTwinPoint& A,const FGHSTwinPoint& B) { if(A.Id==B.Id) return false; const bool AS=A.Id==SelectedId || A.Id==ActiveRegionId, BS=B.Id==SelectedId || B.Id==ActiveRegionId; if(AS!=BS) return AS; return A.bAlert && !B.bAlert; });
    const int32 Maximum=Density==TEXT("minimal") ? 6 : Density==TEXT("all") ? 32 : 16;
    // Keep adjacent equipment labels off the object the user is inspecting.
    FVector2D SelectedMin(1.e8,1.e8),SelectedMax(-1.e8,-1.e8);
    FVector SelectedCenter,SelectedExtent;
    bool bSelectedBoundsValid=!SelectedId.IsEmpty() && SceneData.Resolve(SelectedId,SelectedCenter,SelectedExtent);
    if(bSelectedBoundsValid) for(int I=0;I<8;++I)
    {
        FVector2D P;
        if(!GetOwningPlayer()->ProjectWorldLocationToScreen(SelectedCenter+SelectedExtent*FVector(I&1?1:-1,I&2?1:-1,I&4?1:-1),P,false)) { bSelectedBoundsValid=false; break; }
        SelectedMin.X=FMath::Min(SelectedMin.X,P.X-8);SelectedMin.Y=FMath::Min(SelectedMin.Y,P.Y-8);
        SelectedMax.X=FMath::Max(SelectedMax.X,P.X+8);SelectedMax.Y=FMath::Max(SelectedMax.Y,P.Y+8);
    }
    TSet<FString> Current;
    for(const auto& Point: Points)
    {
        FVector2D Screen;
        if(!GetOwningPlayer()->ProjectWorldLocationToScreen(Point.Location,Screen,false)) continue;
        const bool Selected=Point.Id==SelectedId || Point.Id==ActiveRegionId;
        const bool bRegion=Point.Id.StartsWith(TEXT("REGION:"));
        const FVector2D Size(bRegion ? 176 : Point.Id.StartsWith(TEXT("GROUP:")) ? 246 : 236,42);
        FVector2D At=Screen-FVector2D(Size.X*.5,Size.Y+28);
        if(!Layout.IsScenePoint(At-FVector2D(4,4)) || !Layout.IsScenePoint(At+Size+FVector2D(4,4)) || At.Y<Layout.HeaderHeight+64) continue;
        bool Overlap=false;
        const FVector2D Original=At;
        const int32 Attempts=Point.Id.StartsWith(TEXT("GROUP:")) || bRegion ?7:1;
        for(int32 Attempt=0;Attempt<Attempts;++Attempt)
        {
            At=Original+FVector2D(0,Attempt==0?0:((Attempt+1)/2)*60*(Attempt%2? -1:1));
            Overlap=!Layout.IsScenePoint(At) || !Layout.IsScenePoint(At+Size) || At.Y<Layout.HeaderHeight+110;
            // A displaced aggregate must leave its own world anchor outside the card.
            if(Inside(Screen,At-FVector2D(14,14),Size+FVector2D(28,28))) Overlap=true;
            if(!Selected && bSelectedBoundsValid && At.X<SelectedMax.X && At.X+Size.X>SelectedMin.X
                && At.Y<SelectedMax.Y && At.Y+Size.Y>SelectedMin.Y) Overlap=true;
            for(const auto& Existing:Labels) if(FMath::Abs((At+Size*.5-Existing.Position-Existing.Size*.5).X)<(Size.X+Existing.Size.X)*.5+12 && FMath::Abs((At+Size*.5-Existing.Position-Existing.Size*.5).Y)<(Size.Y+Existing.Size.Y)*.5+12) {Overlap=true; break;}
            if(!Overlap) break;
        }
        if(Overlap && !Selected) continue;
        if(auto* Previous=PreviousPositions.Find(Point.Id)) At=GHSHUDMotion::FollowPosition(*Previous,At,DeltaSeconds);
        PreviousPositions.Add(Point.Id,At); Current.Add(Point.Id);
        float& Age=LabelAges.FindOrAdd(Point.Id); Age+=DeltaSeconds;
        float CursorX=0,CursorY=0;
        const bool bHover=GetOwningPlayer()->GetMousePosition(CursorX,CursorY) && Inside(FVector2D(CursorX,CursorY),At,Size);
        FLabel L; L.Id=Point.Id; L.Text=Point.Title; L.Kind=Point.Kind; L.Status=Point.Status; L.Position=At; L.Anchor=Screen; L.Size=Size; L.bAlert=Point.bAlert; L.bSelected=Selected; L.bHovered=bHover; L.Opacity=GHSHUDMotion::Progress(Age);
        Labels.Add(L); if(Labels.Num()>=Maximum) break;
    }
    for(auto It=LabelAges.CreateIterator();It;++It) if(!Current.Contains(It.Key())) {PreviousPositions.Remove(It.Key());It.RemoveCurrent();}
}
FString UGHSTwinHUDWidget::GetPOIReport() const
{
    TArray<TSharedPtr<FJsonValue>> Items;
    for(const auto& Label:Labels)
    {
        auto Item=MakeShared<FJsonObject>(); Item->SetStringField(TEXT("id"),Label.Id); Item->SetStringField(TEXT("icon"),Label.Kind);
        Item->SetBoolField(TEXT("selected"),Label.bSelected); Item->SetNumberField(TEXT("height"),Label.Size.Y);
        Item->SetStringField(TEXT("fill"),Label.bSelected?TEXT("356BFA"):TEXT("FFFFFF"));
        Item->SetNumberField(TEXT("x"),Label.Position.X); Item->SetNumberField(TEXT("y"),Label.Position.Y);
        Items.Add(MakeShared<FJsonValueObject>(Item));
    }
    auto Root=MakeShared<FJsonObject>(); Root->SetArrayField(TEXT("labels"),Items); Root->SetNumberField(TEXT("selectionStroke"),4);
    FString Out; FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Out)); return Out;
}
int32 UGHSTwinHUDWidget::NativePaint(const FPaintArgs& Args,const FGeometry& G,const FSlateRect& Clip,FSlateWindowElementList& Elements,int32 Layer,const FWidgetStyle& Style,bool Enabled) const
{
    Layer=Super::NativePaint(Args,G,Clip,Elements,Layer,Style,Enabled);
    auto Box=[&](FVector2D At,FVector2D Size,FLinearColor Fill,float Radius=0.f,FLinearColor Border=FLinearColor::Transparent,float BorderWidth=1.f)
    { FSlateRoundedBoxBrush Brush(FLinearColor::White,Radius,Border,Border.A>0?BorderWidth:0); FSlateDrawElement::MakeBox(Elements,++Layer,G.ToPaintGeometry(Size,FSlateLayoutTransform(At)),&Brush,ESlateDrawEffect::None,Fill); };
    auto Text=[&](FVector2D At,const FString& Value,int Size,FLinearColor Color)
    { FSlateDrawElement::MakeText(Elements,++Layer,G.ToPaintGeometry(FVector2D(600,Size+10),FSlateLayoutTransform(At)),Value,Font(Size),ESlateDrawEffect::None,Color); };
    auto Line=[&](FVector2D A,FVector2D B,FLinearColor Color,float Width=1.f)
    { FSlateDrawElement::MakeLines(Elements,++Layer,G.ToPaintGeometry(),TArray<FVector2D>{A,B},ESlateDrawEffect::None,Color,true,Width); };
    Box(FVector2D::ZeroVector,FVector2D(ViewSize.X,Layout.HeaderHeight),C(TEXT("172131")));
    Box(FVector2D(22,20),FVector2D(9,9),C(TEXT("356BFA")),1); Box(FVector2D(34,20),FVector2D(9,9),C(TEXT("78A3FF")),1); Box(FVector2D(22,32),FVector2D(9,9),C(TEXT("78A3FF")),1); Box(FVector2D(34,32),FVector2D(9,9),C(TEXT("356BFA")),1);
    Text(FVector2D(57,Layout.HeaderHeight/2-12),TEXT("GHS 仓储数字孪生"),17,FLinearColor::White);
    if(ViewSize.X>850) {Text(FVector2D(300,24),TEXT("普通仓库  /  三维运营中心"),12,C(TEXT("A5B2C5"))); Text(FVector2D(ViewSize.X-310,24),TEXT("场景已连接  ·  业务演示"),12,C(TEXT("B8C5D8")));}
    Text(FVector2D(ViewSize.X-102,Layout.HeaderHeight/2-9),bPanelCollapsed?TEXT("展开面板"):TEXT("收起面板"),12,FLinearColor::White);
    Box(FVector2D(20,Layout.HeaderHeight+16),FVector2D(104,36),FLinearColor::White,4,C(TEXT("E5EAF2")));
    Text(FVector2D(36,Layout.HeaderHeight+25),TEXT("仓库总览"),12,C(TEXT("25364B")));
    if(Layout.SceneSize.X>660)
    {
        const TCHAR* Names[]={TEXT("全部设备"),TEXT("货架区域"),TEXT("装卸车辆"),TEXT("充电设施")};
        const TCHAR* Filters[]={TEXT("all"),TEXT("rack"),TEXT("truck"),TEXT("charger")};
        for(int I=0;I<4;++I) { const FVector2D At(20+I*104,Layout.HeaderHeight+68); Box(At,FVector2D(96,32),FLinearColor::White,4,C(PointFilter==Filters[I]?TEXT("356BFA"):TEXT("E5EAF2"))); Text(At+FVector2D(15,8),Names[I],11,C(TEXT("25364B"))); }
    }
    if(!SelectedId.IsEmpty())
    {
        FVector Location,Extent;
        if(SceneData.Resolve(SelectedId,Location,Extent))
        {
            FVector2D Min(1.e8,1.e8),Max(-1.e8,-1.e8); bool Valid=true;
            for(int I=0;I<8;++I)
            {
                FVector2D P; if(!GetOwningPlayer()->ProjectWorldLocationToScreen(Location+Extent*FVector(I&1?1:-1,I&2?1:-1,I&4?1:-1),P,false)) {Valid=false;break;}
                Min.X=FMath::Min(Min.X,P.X);Min.Y=FMath::Min(Min.Y,P.Y);Max.X=FMath::Max(Max.X,P.X);Max.Y=FMath::Max(Max.Y,P.Y);
            }
            if(Valid && Layout.IsScenePoint((Min+Max)*.5))
            {
                Min.X=FMath::Max(Min.X,8.);Min.Y=FMath::Max(Min.Y,Layout.HeaderHeight+8);Max.X=FMath::Min(Max.X,Layout.SceneSize.X-8);Max.Y=FMath::Min(Max.Y,Layout.ScenePosition.Y+Layout.SceneSize.Y-8);
                const FLinearColor Blue=C(TEXT("356BFA"));
                for(int I=0;I<4;++I) {const FVector2D P(I&1?Max.X:Min.X,I&2?Max.Y:Min.Y);Line(P,P+FVector2D(I&1?-24:24,0),Blue,4);Line(P,P+FVector2D(0,I&2?-24:24),Blue,4);}
            }
        }
    }
    // Render stems beneath every card. A tag moved below its anchor connects
    // from the top edge; neither its stem nor its anchor may overwrite text.
    for(const FLabel& L:Labels)
    {
        if(Inside(L.Anchor,L.Position-FVector2D(2,2),L.Size+FVector2D(4,4))) continue;
        FLinearColor Accent=C(TEXT("8490A2"));
        if(L.Status==TEXT("running") || L.Status==TEXT("charging")) Accent=C(TEXT("087B68"));
        else if(L.Status==TEXT("fault")) Accent=C(TEXT("B53743"));
        else if(L.Status==TEXT("warning") || L.bAlert) Accent=C(TEXT("92580D"));
        else if(L.Status==TEXT("scene")) Accent=C(TEXT("356BFA"));
        const FVector2D Edge(FMath::Clamp(L.Anchor.X,L.Position.X,L.Position.X+L.Size.X),
            FMath::Clamp(L.Anchor.Y,L.Position.Y,L.Position.Y+L.Size.Y));
        Line(Edge,L.Anchor,Accent.CopyWithNewOpacity(.6f*L.Opacity));
        TArray<FVector2D> Ring; for(int I=0;I<=24;++I) {const double A=I*2*PI/24;Ring.Add(L.Anchor+FVector2D(FMath::Cos(A)*12,FMath::Sin(A)*5));}
        FSlateDrawElement::MakeLines(Elements,++Layer,G.ToPaintGeometry(),Ring,ESlateDrawEffect::None,Accent.CopyWithNewOpacity(.55f*L.Opacity),true,1.f);
        Box(L.Anchor-FVector2D(3,3),FVector2D(6,6),Accent.CopyWithNewOpacity(L.Opacity),3);
    }
    for(const FLabel& L:Labels)
    {
        auto Fade=[&](FLinearColor Color){Color.A*=L.Opacity;return Color;};
        const bool bRegion=L.Id.StartsWith(TEXT("REGION:")), bGroup=L.Id.StartsWith(TEXT("GROUP:"));
        FString State=TEXT("待接入"); FLinearColor Accent=C(TEXT("8490A2"));
        if(L.Status==TEXT("running") || L.Status==TEXT("charging")) {State=L.Status==TEXT("charging")?TEXT("充电中"):TEXT("运行");Accent=C(TEXT("087B68"));}
        else if(L.Status==TEXT("fault")) {State=TEXT("故障");Accent=C(TEXT("B53743"));}
        else if(L.Status==TEXT("warning") || L.bAlert) {State=TEXT("预警");Accent=C(TEXT("92580D"));}
        else if(L.Status==TEXT("idle")) State=TEXT("待机");
        else if(L.Status==TEXT("offline")) State=TEXT("离线");
        else if(L.Status==TEXT("scene")) {State=TEXT("场景");Accent=C(TEXT("356BFA"));}
        if(bGroup && !L.bAlert) State=TEXT("设备");
        const FLinearColor Blue=C(TEXT("356BFA"));
        Box(L.Position+FVector2D(0,3),L.Size,Fade(FLinearColor(.08,.15,.25,.055)),6);
        Box(L.Position,L.Size,Fade(L.bSelected?Blue:FLinearColor::White),6,Fade(L.bSelected || L.bHovered?Blue:C(TEXT("DFE7F2"))),L.bHovered?1.5f:1.f);
        // Type marks follow the approved 24-unit line-icon system, not a generic status dot.
        const FVector2D IconAt=L.Position+FVector2D(12,12); const FLinearColor Ink=Fade(L.bSelected?FLinearColor::White:Accent);
        auto Path=[&](std::initializer_list<FVector2D> Points)
        { TArray<FVector2D> P; for(const auto& V:Points) P.Add(IconAt+V*.75); FSlateDrawElement::MakeLines(Elements,++Layer,G.ToPaintGeometry(),P,ESlateDrawEffect::None,Ink,true,1.5f); };
        if(L.Kind==TEXT("agv"))
        {Path({{4,9},{20,9},{20,19},{4,19},{4,9}});Path({{8,9},{8,5},{16,5},{16,9}});Path({{12,5},{12,2}});Path({{1,12},{4,12}});Path({{20,12},{23,12}});Path({{9,12},{9,16}});Path({{15,12},{15,16}});}
        else if(L.Kind==TEXT("forklift") || L.Kind==TEXT("stacker"))
        {Path({{3,16},{3,10},{10,10},{10,16},{17,16},{17,2}});Path({{17,18},{23,18}});Path({{5,10},{5,5},{12,5},{12,13}});Path({{2,18},{4,20},{6,18},{4,16},{2,18}});Path({{11,18},{13,20},{15,18},{13,16},{11,18}});}
        else if(L.Kind==TEXT("truck"))
        {Path({{2,17},{2,4},{14,4},{14,17},{2,17}});Path({{14,9},{19,9},{22,13},{22,17},{14,17}});Path({{5,17},{5,20},{8,20},{8,17}});Path({{17,17},{17,20},{20,20},{20,17}});}
        else if(L.Kind==TEXT("charger"))
        {Path({{6,5},{10,9},{6,13},{2,9},{6,5}});Path({{8,3},{11,6}});Path({{3,8},{6,11}});Path({{8,11},{12,15},{9,19},{13,22}});Path({{17,2},{14,8},{20,8},{17,14}});}
        else if(L.Kind==TEXT("rack"))
        {Path({{2,3},{22,3},{22,22}});Path({{2,3},{2,22}});Path({{2,12},{22,12}});Path({{2,21},{22,21}});Path({{5,5},{10,5},{10,10},{5,10},{5,5}});Path({{14,14},{19,14},{19,19},{14,19},{14,14}});}
        else
        {Path({{3,7},{12,2},{21,7},{21,18},{12,23},{3,18},{3,7},{12,12},{21,7}});Path({{12,12},{12,23}});Path({{8,4},{17,9}});}
        const FString Title=bRegion || bGroup?L.Text:L.Id.Len()<22?L.Id:TEXT("货架物料");
        Text(L.Position+FVector2D(40,11),Title,14,Fade(L.bSelected?FLinearColor::White:C(TEXT("25364B"))));
        if(!bRegion)
        {
            const double BadgeWidth=State.Len()*14.+12; const FVector2D BadgeAt=L.Position+FVector2D(L.Size.X-BadgeWidth-12,9);
            Box(BadgeAt,FVector2D(BadgeWidth,24),Fade(C(TEXT("F0F4F9"))),3);
            Text(BadgeAt+FVector2D(6,4),State,12,Fade(Accent));
        }
    }
    const FVector2D Tool(Layout.SceneSize.X-60,Layout.ScenePosition.Y+Layout.SceneSize.Y-132);
    Box(Tool,FVector2D(40,112),FLinearColor::White,4,C(TEXT("E5EAF2")));
    Text(Tool+FVector2D(13,5),TEXT("+"),22,C(TEXT("5B6C82"))); Box(Tool+FVector2D(14,55),FVector2D(12,2),C(TEXT("5B6C82"))); Text(Tool+FVector2D(8,83),TEXT("复位"),11,C(TEXT("5B6C82")));
    if(Layout.SceneSize.X>650) Text(FVector2D(22,Layout.ScenePosition.Y+Layout.SceneSize.Y-32),TEXT("左键拖动旋转  ·  右键平移  ·  滚轮缩放  ·  点击对象查看详情"),11,C(TEXT("5B6C82")));
    return Layer;
}
