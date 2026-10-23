#include "GHSTwinHUDWidget.h"
#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehouseRoofComponent.h"
#include "GHSStorageCapacityComponent.h"
#include "GHSOrderReplaySession.h"
#include "GHSHUDMotion.h"
#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/EditableTextBox.h"
#include "SWebBrowser.h"
#include "WebBrowserModule.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Rendering/DrawElements.h"
#include "GameFramework/SpringArmComponent.h"
#include "Camera/CameraComponent.h"
#include "Framework/Application/SlateApplication.h"
#include "Fonts/FontMeasure.h"
#include "Widgets/Input/SEditableText.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Layout/SBorder.h"
#include "Brushes/SlateNoResource.h"
#include "Widgets/Text/SlateEditableTextLayout.h"
#include "GenericPlatform/ITextInputMethodSystem.h"
#include "Engine/GameViewportClient.h"

namespace
{
FLinearColor C(const TCHAR* Hex) { return FLinearColor::FromSRGBColor(FColor::FromHex(Hex)); }
bool Inside(FVector2D P, FVector2D At, FVector2D Size) { return P.X>=At.X && P.Y>=At.Y && P.X<At.X+Size.X && P.Y<At.Y+Size.Y; }
const FVector2D WarehousePOISize(228,56);
const FSlateFontInfo& Font(int32 Size)
{
    static const FString Path=FPaths::ProjectContentDir()/TEXT("GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf");
    static TMap<int32,FSlateFontInfo> Fonts;
    if(const auto* Existing=Fonts.Find(Size)) return *Existing;
    return Fonts.Add(Size,FSlateFontInfo(Path,Size));
}
const TArray<FVector2D>& UnitAnchorEllipse()
{
    static const TArray<FVector2D> Points=[]()
    {
        TArray<FVector2D> Result;Result.Reserve(25);
        for(int32 I=0;I<=24;++I) {const double A=I*2*PI/24;Result.Add(FVector2D(FMath::Cos(A)*12,FMath::Sin(A)*5));}
        return Result;
    }();
    return Points;
}
}

class SGHSTwinEditableText : public SEditableText
{
public:
    TWeakObjectPtr<UGHSTwinHUDWidget> Owner;
    bool IsComposing() const { return EditableTextLayout && EditableTextLayout->GetTextInputMethodContext()->IsComposing(); }
protected:
    virtual FReply OnFocusReceived(const FGeometry& Geometry,const FFocusEvent& Event) override
    { if(Owner.IsValid()) Owner->SetSearchOpen(true); return SEditableText::OnFocusReceived(Geometry,Event); }
    virtual FReply OnKeyDown(const FGeometry& Geometry,const FKeyEvent& Event) override
    {
        // Candidate navigation and Enter belong to Windows while IME is composing.
        if(!IsComposing() && Owner.IsValid() && Event.GetKey()!=EKeys::Enter && Owner->HandleSearchKey(Event.GetKey())) return FReply::Handled();
        return SEditableText::OnKeyDown(Geometry,Event);
    }
};

TSharedRef<SWidget> UGHSTwinSearchInput::RebuildWidget()
{
    static const FSlateRoundedBoxBrush Background(FLinearColor::White,12.f,C(TEXT("D9E3F1")),1.f);
    static const FButtonStyle ClearStyle=FButtonStyle().SetNormal(FSlateNoResource()).SetHovered(FSlateNoResource()).SetPressed(FSlateNoResource()).SetDisabled(FSlateNoResource());
    SAssignNew(Editor,SGHSTwinEditableText)
        .Font(Font(13)).ColorAndOpacity(C(TEXT("25364B")))
        .HintText(FText::FromString(TEXT("搜索设备、货位或物料")))
        .ClearKeyboardFocusOnCommit(false)
        .OnTextChanged_Lambda([this](const FText& Value){if(SearchOwner.IsValid()) SearchOwner->SearchChanged(Value);})
        .OnTextCommitted_Lambda([this](const FText& Value,ETextCommit::Type Method){if(SearchOwner.IsValid()) SearchOwner->SearchCommitted(Value,Method);});
    Editor->Owner=SearchOwner;
    return SNew(SBorder).BorderImage(&Background).Padding(FMargin(16,8)).VAlign(VAlign_Center)
    [SNew(SHorizontalBox)
        +SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[Editor.ToSharedRef()]
        +SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12,0,0,0)
        [SNew(SButton).ButtonStyle(&ClearStyle).ContentPadding(0)
            .IsEnabled_Lambda([this](){return Editor && !Editor->GetText().IsEmpty();})
            .OnClicked_Lambda([this](){if(SearchOwner.IsValid()) SearchOwner->SetSearchOpen(true);if(Editor) Editor->SetText(FText::GetEmpty());return FReply::Handled();})
            [SNew(STextBlock).Font(Font(11)).ColorAndOpacity(C(TEXT("356BFA")))
                .Text_Lambda([this](){return FText::FromString(Editor && !Editor->GetText().IsEmpty()?TEXT("清除"):TEXT("GHS"));})]]];
}
void UGHSTwinSearchInput::Bind(UGHSTwinHUDWidget* Owner) { SearchOwner=Owner;if(Editor) Editor->Owner=Owner; }
void UGHSTwinSearchInput::SetText(const FString& Value) { if(Editor) Editor->SetText(FText::FromString(Value)); }
bool UGHSTwinSearchInput::IsComposing() const { return Editor && Editor->IsComposing(); }
bool UGHSTwinSearchInput::HasInputFocus() const { return Editor && Editor->HasKeyboardFocus(); }
void UGHSTwinSearchInput::ReleaseSlateResources(bool bChildren) { Super::ReleaseSlateResources(bChildren);Editor.Reset(); }

TSharedRef<SWidget> UGHSTwinBrowser::RebuildWidget()
{
    // Direct Slate hosting does not load the WebBrowserWidget plugin's startup hook.
    IWebBrowserModule::Get();
    FString File = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/web")/Document);
    File.ReplaceInline(TEXT("\\"),TEXT("/"));
    SAssignNew(Browser,SWebBrowser)
        .InitialURL(TEXT("file:///")+File).ShowControls(false).ShowAddressBar(false)
        .SupportsTransparency(bTransparent).ShowInitialThrobber(!bTransparent).BrowserFrameRate(60)
        .BackgroundColor(bTransparent?FColor::Transparent:FColor(244,246,249))
        .OnBeforePopup_Lambda([](FString,FString){return true;})
        .OnBeforeNavigation_Lambda([](const FString& URL,const FWebNavigationRequest&){return !URL.StartsWith(TEXT("file:///"));})
        .OnSuppressContextMenu_Lambda([](){return true;})
        .OnLoadCompleted_Lambda([](){UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_BROWSER_DOCUMENT_LOADED"));})
        .OnLoadError_Lambda([](){UE_LOG(LogTemp,Error,TEXT("GHS_TWIN_BROWSER_DOCUMENT_FAILED"));});
    if(FSlateApplication::IsInitialized()) Browser->BindInputMethodSystem(FSlateApplication::Get().GetTextInputMethodSystem());
    return Browser.ToSharedRef();
}
void UGHSTwinBrowser::Bind(UObject* Target) { if(Browser) Browser->BindUObject(TEXT("twin"),Target,true); }
void UGHSTwinBrowser::Evaluate(const FString& Script) { if(Browser) Browser->ExecuteJavascript(Script); }
void UGHSTwinBrowser::ReleaseSlateResources(bool bChildren) { if(Browser) Browser->UnbindInputMethodSystem();Super::ReleaseSlateResources(bChildren); Browser.Reset(); }

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
    Panel->SetVisibility(ESlateVisibility::Hidden);
    ReplayOverlay=WidgetTree->ConstructWidget<UGHSTwinBrowser>(UGHSTwinBrowser::StaticClass(),TEXT("ReplayTransport"));
    ReplayOverlay->Document=TEXT("replay-overlay.html");ReplayOverlay->bTransparent=true;
    ReplayOverlaySlot=Root->AddChildToCanvas(ReplayOverlay);
    ReplayOverlaySlot->SetPosition(FVector2D(24,888));ReplayOverlaySlot->SetSize(FVector2D(1320,168));
    ReplayOverlay->SetVisibility(ESlateVisibility::Hidden);
    SearchBox=WidgetTree->ConstructWidget<UGHSTwinSearchInput>(UGHSTwinSearchInput::StaticClass(),TEXT("SceneSearch"));
    SearchBox->Bind(this);
    SearchSlot=Root->AddChildToCanvas(SearchBox);
    SearchBox->SetVisibility(ESlateVisibility::Hidden);
    return Super::RebuildWidget();
}
void UGHSTwinHUDWidget::NativeConstruct()
{
    Super::NativeConstruct();
    SetVisibility(ESlateVisibility::SelfHitTestInvisible);
    if (Panel) Panel->Bind(this);
    if (ReplayOverlay) ReplayOverlay->Bind(this);
    bDiagnostics=FParse::Param(FCommandLine::Get(),TEXT("TwinDiagnostics"));
    SceneData.Refresh(GetWorld(),true);
    NextRefresh=GetWorld()->GetTimeSeconds()+2;
    UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_UI_STARTED %s"),*GetWorld()->GetMapName());
}
void UGHSTwinHUDWidget::NativeDestruct() { SceneData.Refresh(nullptr); PreviousPositions.Empty(); LabelAges.Empty(); Labels.Empty(); VisibleLabels.Empty(); PreviousVisibleLabels.Empty(); Super::NativeDestruct(); }
FString UGHSTwinHUDWidget::GetSnapshot() const { return SceneData.SnapshotJson(SelectedId); }
void UGHSTwinHUDWidget::EvaluateDiagnostics(const FString& Script)
{
    if(bDiagnostics && Panel && Script.Len()<=32768) Panel->Evaluate(Script);
}
FString UGHSTwinHUDWidget::GetSceneControlsState() const
{
    auto Json=MakeShared<FJsonObject>();
    const auto* R=Roof();const auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer());
    const auto* Capacity=PC?PC->StorageCapacity.Get():nullptr;
    Json->SetBoolField(TEXT("building"),!R || R->IsBuildingVisible());
    Json->SetBoolField(TEXT("racks"),bRacks);Json->SetBoolField(TEXT("equipment"),bEquipment);Json->SetBoolField(TEXT("pois"),bShowPOIs);
    Json->SetStringField(TEXT("density"),Density);Json->SetNumberField(TEXT("sequence"),double(SettingsSequence));
    Json->SetNumberField(TEXT("rackCapacity"),Capacity?Capacity->GetRackCapacity():.8);
    Json->SetNumberField(TEXT("floorCapacity"),Capacity?Capacity->GetFloorCapacity():1.);
    Json->SetBoolField(TEXT("roofClosed"),R && R->IsRoofClosed());Json->SetBoolField(TEXT("roofOpening"),R && R->IsOpening());
    Json->SetBoolField(TEXT("roofClosing"),R && R->IsClosing());
    FString Text;FJsonSerializer::Serialize(Json,TJsonWriterFactory<>::Create(&Text));return Text;
}
void UGHSTwinHUDWidget::PushSceneControls(const FString& Notice,bool bForce)
{
    if(!Panel || !bBrowserReady || !bBrowserActive) return;
    const FString State=GetSceneControlsState();
    if(!bForce && Notice.IsEmpty() && State==LastSceneControls) return;
    LastSceneControls=State;FString Json=State;
    if(!Notice.IsEmpty())
    {
        TSharedPtr<FJsonObject> Object;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(State),Object);
        Object->SetStringField(TEXT("notice"),Notice);Json.Empty();FJsonSerializer::Serialize(Object.ToSharedRef(),TJsonWriterFactory<>::Create(&Json));
    }
    Panel->Evaluate(TEXT("window.twinSceneControls && window.twinSceneControls(")+Json+TEXT(");"));
}
void UGHSTwinHUDWidget::ApplySceneLayers()
{
    SceneData.ApplyLayers(bEquipment,bRacks);
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer());PC && PC->StorageCapacity) PC->StorageCapacity->SetStorageVisible(bRacks);
    if(!SelectedId.IsEmpty() && !SceneData.IsObjectVisible(SelectedId)) ClearSelection();
    POICadence.Invalidate();
}
bool UGHSTwinHUDWidget::RevealForNavigation(const FString& Id)
{
    FVector Location,Extent;if(!SceneData.Resolve(Id,Location,Extent)) return false;
    const bool bStorage=SceneData.IsStorageObject(Id);
    bool bChanged=false;
    if(bStorage && !bRacks) {bRacks=true;bChanged=true;}
    if(!bStorage && !bEquipment) {bEquipment=true;bChanged=true;}
    if(bChanged) {ApplySceneLayers();PushSceneControls(bStorage?TEXT("已显示货架与货物"):TEXT("已显示作业设备"));}
    return SceneData.IsObjectVisible(Id);
}
void UGHSTwinHUDWidget::PushSnapshot(bool bExplicitSelection,bool bForce)
{
    TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinHUD_PushSnapshot);
    if(!Panel || !bBrowserReady || !bBrowserActive) return;
    FString Json;
    if(SceneData.BuildSnapshotIfChanged(SelectedId,Json,bForce || bExplicitSelection))
        Panel->Evaluate(FString(bExplicitSelection?TEXT("window.twinSelect && window.twinSelect("):TEXT("window.twinReceive && window.twinReceive("))+Json+TEXT(");"));
}
void UGHSTwinHUDWidget::SetPanelCollapsed(bool bCollapsed,bool bExplicitSelection)
{
    const bool bOpening=bPanelCollapsed && !bCollapsed;
    bPanelCollapsed=bCollapsed;POICadence.Invalidate();
    if(bOpening) UpdateBrowserVisibility(true,bExplicitSelection);
}
void UGHSTwinHUDWidget::UpdateBrowserVisibility(bool bForce,bool bExplicitSelection)
{
    const bool bActive=GHSTwinHUDPerformance::ShouldRefreshBrowser(bPanelCollapsed,PanelVisibilityProgress);
    if(!Panel || !bBrowserReady) { bBrowserActive=bActive;return; }
    if(bActive==bBrowserActive && !bForce) return;
    bBrowserActive=bActive;
    // Queue the newest full snapshot while the page is still paused, then render
    // it once as visibility resumes. Explicit picks use this same ordering and do
    // not send a second selection snapshot after the panel has become visible.
    if(bActive) {PushSnapshot(bExplicitSelection,true);PushSceneControls(TEXT(""),true);}
    Panel->Evaluate(bActive?TEXT("window.twinSetVisibility && window.twinSetVisibility(true);"):TEXT("window.twinSetVisibility && window.twinSetVisibility(false);"));
}
void UGHSTwinHUDWidget::UpdateBrowserViewport(bool bForce)
{
    if(!Panel || !bBrowserReady) return;
    const FVector2D Size=GetPanelVisualSize();
    if(Size.X<=0 || Size.Y<=0 || (!bForce && Size.Equals(LastBrowserViewport,.01))) return;
    LastBrowserViewport=Size;
    // CEF has its own OS-DPI-sized CSS viewport. Give the page its design size
    // so its type, hit targets and responsive breakpoints match the native HUD.
    Panel->Evaluate(FString::Printf(TEXT("window.twinSetViewport && window.twinSetViewport(%.6f,%.6f);"),Size.X,Size.Y));
}
FVector2D UGHSTwinHUDWidget::GetPanelVisualPosition() const
{
    return PanelSlot && Panel?PanelSlot->GetPosition()+Panel->GetRenderTransform().Translation:FGHSTwinLayout::Calculate(ViewSize).PanelPosition;
}
FVector2D UGHSTwinHUDWidget::GetPanelVisualSize() const
{
    return PanelSlot?PanelSlot->GetSize():FGHSTwinLayout::Calculate(ViewSize).PanelSize;
}
FVector2D UGHSTwinHUDWidget::GetSceneControlsPosition() const
{
    return PanelMotion.SceneControlsPosition(ViewSize);
}
FVector2D UGHSTwinHUDWidget::GetSceneSearchPosition() const
{
    return SearchSlot?SearchSlot->GetPosition():PanelMotion.SceneSearchPosition(ViewSize);
}
FVector2D UGHSTwinHUDWidget::GetSceneSearchSize() const
{
    return SearchSlot?SearchSlot->GetSize():FVector2D::ZeroVector;
}
bool UGHSTwinHUDWidget::IsSceneSearchVisible() const
{
    return SearchBox && SearchBox->GetVisibility()==ESlateVisibility::Visible;
}
float UGHSTwinHUDWidget::GetPanelOpacity() const { return Panel?Panel->GetRenderOpacity():1.f; }
bool UGHSTwinHUDWidget::IsScenePoint(FVector2D Position) const
{
    if(bInitialLayoutPending) return false;
    Position=Viewport.ToLogical(Position);
    if(IsReplayActive() && ReplayOverlaySlot && Inside(Position,ReplayOverlaySlot->GetPosition(),ReplayOverlaySlot->GetSize())) return false;
    if(auto* Replay=ReplaySession();Replay && Replay->IsExitPending()) return false;
    if(!Inside(Position,FVector2D(0,Layout.HeaderHeight),FVector2D(ViewSize.X,ViewSize.Y-Layout.HeaderHeight))) return false;
    if(IsSceneSearchVisible() && Inside(Position,GetSceneSearchPosition(),GetSceneSearchSize())) return false;
    if(bSearchOpen && !bSearchIsRemote && IsSceneSearchVisible() && Inside(Position,SearchLayout().Position,SearchLayout().Size)) return false;
    if(bWarehouseMenuOpen && Inside(Position,FVector2D(24,Layout.HeaderHeight+110),FVector2D(320,176))) return false;
    if(FGHSTwinSceneChrome::IsHeadingPoint(Position,Layout.HeaderHeight)) return false;
    // Input follows the visible moving panel, not the area it occupied when open.
    return PanelVisibilityProgress<=0 || !Inside(Position,GetPanelVisualPosition(),GetPanelVisualSize());
}
void UGHSTwinHUDWidget::Navigate(const FString& Page)
{
    auto Object=MakeShared<FJsonObject>();Object->SetStringField(TEXT("action"),TEXT("navigate"));Object->SetStringField(TEXT("page"),Page);
    FString Intent;FJsonSerializer::Serialize(Object,TJsonWriterFactory<>::Create(&Intent));if(GuardReplayOperation(Intent)) return;
    SetSearchOpen(false); bWarehouseMenuOpen=false;
    static const TSet<FString> Allowed{TEXT("overview"),TEXT("inventory"),TEXT("orders"),TEXT("devices"),TEXT("alerts"),TEXT("trace"),TEXT("scene"),TEXT("settings")};
    if(Allowed.Contains(Page) && Panel) Panel->Evaluate(FString::Printf(TEXT("window.twinNavigate && window.twinNavigate('%s');"),*Page));
}
void UGHSTwinHUDWidget::SearchCommitted(const FText& Text,ETextCommit::Type Method)
{
    if(Method!=ETextCommit::OnEnter || (SearchBox && SearchBox->IsComposing())) return;
    const FString Query=Text.ToString().Left(128);const bool bChanged=Query!=SearchQuery;
    SearchQuery=Query;bSearchPending=false;RefreshSearch(bChanged?0:INDEX_NONE);
    if(SearchResults.IsValidIndex(SearchIndex)) SelectSearchResult(SearchResults[SearchIndex].Id);
}
void UGHSTwinHUDWidget::SearchChanged(const FText& Text)
{ PendingSearchText=Text.ToString().Left(128); bSearchPending=!bStreamSearchApplying; }
void UGHSTwinHUDWidget::SetSearchOpen(bool bOpen)
{
    bSearchOpen=bOpen;bSearchStateDirty=true;if(!bStreamSearchApplying) {SearchRequestId=0;SearchClientId.Empty();}
    if(bOpen) {bSearchIsRemote=bStreamSearchApplying;bWarehouseMenuOpen=false;RefreshSearch();}
    PushSearchState(true);
}
FGHSTwinSearchLayout UGHSTwinHUDWidget::SearchLayout() const
{
    const auto Expanded=FGHSTwinLayout::Calculate(ViewSize);
    return FGHSTwinSearchLayout::Calculate(GetSceneSearchPosition(),GetSceneSearchSize(),Expanded.ScenePosition.Y+Expanded.SceneSize.Y,SearchResults.Num());
}
void UGHSTwinHUDWidget::RefreshSearch(int32 Offset)
{
    const FString PreviousId=Offset==INDEX_NONE && SearchResults.IsValidIndex(SearchIndex)?SearchResults[SearchIndex].Id:FString();
    if(Offset!=INDEX_NONE) {SearchOffset=FMath::Max(0,Offset);SearchFirstVisible=0;}
    SearchResults=SceneData.Search(SearchQuery,50,&SearchTotal,SearchOffset);SearchRevision=SceneData.GetRevision();
    bSearchStateDirty=true;
    SearchIndex=SearchResults.IndexOfByPredicate([&](const FGHSTwinSearchResult& R){return R.Id==PreviousId;});
    if(SearchIndex==INDEX_NONE && !SearchResults.IsEmpty()) SearchIndex=0;
    SearchFirstVisible=FGHSTwinSearchLayout::WindowStart(SearchIndex,SearchFirstVisible,SearchLayout().VisibleRows,SearchResults.Num());
}
void UGHSTwinHUDWidget::MoveSearchSelection(int32 Delta)
{
    if(SearchTotal<=0) return;
    const int32 Global=FGHSTwinSearchLayout::MoveIndex(SearchOffset+FMath::Max(0,SearchIndex),Delta,SearchTotal);
    const int32 Page=Global/50*50;if(Page!=SearchOffset) RefreshSearch(Page);
    SearchIndex=Global-SearchOffset;
    SearchFirstVisible=FGHSTwinSearchLayout::WindowStart(SearchIndex,SearchFirstVisible,SearchLayout().VisibleRows,SearchResults.Num());
    PushSearchState(true);
}
bool UGHSTwinHUDWidget::HandleSearchWheel(FVector2D Position,double Delta)
{
    Position=Viewport.ToLogical(Position);
    if(!bSearchOpen || bSearchIsRemote || !IsSceneSearchVisible() || !Inside(Position,SearchLayout().Position,SearchLayout().Size)) return false;
    if(FMath::IsFinite(Delta) && !FMath::IsNearlyZero(Delta)) MoveSearchSelection(Delta>0?-3:3);
    return true;
}
bool UGHSTwinHUDWidget::HandleSearchKey(FKey Key)
{
    if(!bSearchOpen || bSearchIsRemote || (SearchBox && SearchBox->IsComposing())) return false;
    if(Key==EKeys::Escape) {SetSearchOpen(false);return true;}
    if(Key==EKeys::Up || Key==EKeys::Down)
    {
        MoveSearchSelection(Key==EKeys::Up?-1:1);return true;
    }
    return false;
}
bool UGHSTwinHUDWidget::SelectSearchResult(const FString& Id)
{
    if(!SceneData.MatchesSearch(SearchQuery,Id)) return false;
    if(!SelectObject(Id)) {RefreshSearch();PushSearchState(true);return false;}
    SetSearchOpen(false);return true;
}
FString UGHSTwinHUDWidget::GetSearchState(bool bGeometryOnly) const
{
    const auto Root=MakeShared<FJsonObject>();Root->SetStringField(TEXT("type"),TEXT("ghs.sceneSearch"));
    Root->SetBoolField(TEXT("visible"),IsSceneSearchVisible());
    const auto View=MakeShared<FJsonObject>();View->SetNumberField(TEXT("width"),ViewSize.X);View->SetNumberField(TEXT("height"),ViewSize.Y);Root->SetObjectField(TEXT("viewport"),View);
    const auto Rect=MakeShared<FJsonObject>();const FVector2D At=GetSceneSearchPosition(),Size=GetSceneSearchSize();
    Rect->SetNumberField(TEXT("x"),At.X);Rect->SetNumberField(TEXT("y"),At.Y);Rect->SetNumberField(TEXT("width"),Size.X);Rect->SetNumberField(TEXT("height"),Size.Y);Root->SetObjectField(TEXT("rect"),Rect);
    if(!bGeometryOnly)
    {
    Root->SetStringField(TEXT("clientId"),SearchClientId);Root->SetNumberField(TEXT("requestId"),SearchRequestId);Root->SetBoolField(TEXT("open"),bSearchOpen);
    Root->SetStringField(TEXT("query"),SearchQuery);Root->SetNumberField(TEXT("selectedIndex"),SearchIndex==INDEX_NONE?INDEX_NONE:SearchOffset+SearchIndex);Root->SetNumberField(TEXT("total"),SearchTotal);
    Root->SetNumberField(TEXT("offset"),SearchOffset);Root->SetBoolField(TEXT("hasMore"),SearchOffset+SearchResults.Num()<SearchTotal);
    TArray<TSharedPtr<FJsonValue>> Rows;
    for(const auto& R:SearchResults)
    {
        const auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("id"),R.Id);Row->SetStringField(TEXT("title"),R.Title);
        Row->SetStringField(TEXT("type"),R.Type);Row->SetStringField(TEXT("location"),R.Location);Row->SetStringField(TEXT("status"),R.Status);
        Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("results"),Rows);
    }
    FString Json;FJsonSerializer::Serialize(Root,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json));return Json;
}
void UGHSTwinHUDWidget::PushSearchState(bool bForce)
{
    if(!bStreamSearchReady) return;
    const FVector2D At=GetSceneSearchPosition(),Size=GetSceneSearchSize();const bool bVisible=IsSceneSearchVisible();
    if(!bForce && !bSearchStateDirty && At.Equals(LastSearchPosition,.01) && Size.Equals(LastSearchSize,.01) && ViewSize.Equals(LastSearchViewport,.01) && bVisible==bLastSearchVisible) return;
    const bool bGeometryOnly=!bForce && !bSearchStateDirty;
    LastSearchPosition=At;LastSearchSize=Size;LastSearchViewport=ViewSize;bLastSearchVisible=bVisible;bSearchStateDirty=false;
    const FString State=GetSearchState(bGeometryOnly);if(!bForce && State==LastSearchState) return;
    LastSearchState=State;if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->SendSearchResponse(State);
}
void UGHSTwinHUDWidget::HandleStreamSearch(const FString& Json)
{
    if(Json.Len()>4096) return;
    // The UE 5.4 browser frontend can reserve UTF-8-sized space while writing
    // UTF-16 code units. Chinese payloads consequently arrive with raw NUL
    // padding; remove only that transport suffix, preserving the JSON text.
    int32 PayloadLength=Json.Len();
    for(int32 I=0;I<Json.Len();++I) if(Json[I]==TCHAR(0)) {PayloadLength=I;break;}
    const FString Payload=Json.Left(PayloadLength);
    TSharedPtr<FJsonObject> Object;if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Payload),Object) || !Object) return;
    FString Type,Action;Object->TryGetStringField(TEXT("type"),Type);Object->TryGetStringField(TEXT("action"),Action);
    if(Type!=TEXT("ghs.sceneSearch")) return;
    static const TSet<FString> Allowed{TEXT("ready"),TEXT("open"),TEXT("query"),TEXT("select"),TEXT("close")};if(!Allowed.Contains(Action)) return;
    TGuardValue<bool> Applying(bStreamSearchApplying,true);
    bStreamSearchReady=true;SearchRequestId=0;Object->TryGetNumberField(TEXT("requestId"),SearchRequestId);
    SearchClientId.Empty();Object->TryGetStringField(TEXT("clientId"),SearchClientId);SearchClientId=SearchClientId.Left(128);
    if(!FMath::IsFinite(SearchRequestId)) SearchRequestId=0;
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
    auto ApplyQuery=[&](int32 Offset=0)
    {
        FString Query;if(!Object->TryGetStringField(TEXT("query"),Query)) return false;
        SearchQuery=Query.Left(128);bSearchIsRemote=true;
        if(SearchBox) SearchBox->SetText(SearchQuery);bSearchPending=false;RefreshSearch(Offset);return true;
    };
    if(Action==TEXT("ready")) {ApplyQuery();bSearchOpen=false;}
    else if(Action==TEXT("open")) {ApplyQuery();SetSearchOpen(true);}
    else if(Action==TEXT("close")) {ApplyQuery();SetSearchOpen(false);}
    else if(Action==TEXT("query"))
    {
        double Offset=0;Object->TryGetNumberField(TEXT("offset"),Offset);
        if(!FMath::IsFinite(Offset) || Offset<0 || Offset>MAX_int32) return;
        if(!ApplyQuery(int32(Offset))) return;bSearchOpen=true;bWarehouseMenuOpen=false;
    }
    else if(Action==TEXT("select"))
    {
        // Shared streams can interleave independent browser searches. Revalidate
        // this caller's committed query against current geometry before picking.
        ApplyQuery();FString Id;if(Object->TryGetStringField(TEXT("id"),Id)) SelectSearchResult(Id);
    }
    PushSearchState(true);
}
void UGHSTwinHUDWidget::Command(const FString& Json)
{
    TSharedPtr<FJsonObject> Object;
    if(Json.Len()>16384 || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Object) || !Object) return;
    FString Action,Id; Object->TryGetStringField(TEXT("action"),Action); Object->TryGetStringField(TEXT("id"),Id);
    if(Action.StartsWith(TEXT("replay"))) {HandleReplayCommand(Action,Object);return;}
    if(IsReplayActive() && Action!=TEXT("report") && Action!=TEXT("ready") && Action!=TEXT("zoomIn") && Action!=TEXT("zoomOut") && Action!=TEXT("clear"))
        if(GuardReplayOperation(Json)) return;
    double Sequence=0;if(Object->TryGetNumberField(TEXT("sequence"),Sequence) && FMath::IsFinite(Sequence)) SettingsSequence=FMath::Max(SettingsSequence,int64(Sequence));
    if(Action!=TEXT("report") && Action!=TEXT("ready")) if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
    if(Action==TEXT("ready"))
    {
        bBrowserReady=true;
        UpdateBrowserViewport(true);
        if(Panel) Panel->Evaluate(bDiagnostics?TEXT("window.twinSetDiagnostics && window.twinSetDiagnostics(true);"):TEXT("window.twinSetDiagnostics && window.twinSetDiagnostics(false);"));
        UpdateBrowserVisibility(true);
        UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_BROWSER_READY"));
    }
    else if(Action==TEXT("openWarehouse")) OpenWarehouse();
    else if(Action==TEXT("select")) {bool bFocus=true;Object->TryGetBoolField(TEXT("focusSelection"),bFocus);SelectObject(Id,bFocus);}
    else if(Action==TEXT("focus")) Focus(Id);
    else if(Action==TEXT("clear")) ClearSelection();
    else if(Action==TEXT("navigate")) {SetSearchOpen(false);bWarehouseMenuOpen=false;}
    else if(Action==TEXT("overview")) Overview();
    else if(Action==TEXT("zoomIn") || Action==TEXT("zoomOut"))
    { if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn())) Cam->ZoomSteps(Action==TEXT("zoomIn")?1:-1); }
    else if(Action==TEXT("layers"))
    {
        PendingInteriorAction.Empty();PendingInteriorId.Empty();
        Object->TryGetBoolField(TEXT("equipment"),bEquipment);Object->TryGetBoolField(TEXT("racks"),bRacks);Object->TryGetBoolField(TEXT("pois"),bShowPOIs);
        bool bBuilding=true;if(auto* R=Roof()) {bBuilding=R->IsBuildingVisible();if(Object->TryGetBoolField(TEXT("building"),bBuilding)) R->SetBuildingVisible(bBuilding);}
        ApplySceneLayers();PushSceneControls();
    }
    else if(Action==TEXT("capacity"))
    {
        double Rack=PendingRackCapacity,Floor=PendingFloorCapacity;
        Object->TryGetNumberField(TEXT("rack"),Rack);Object->TryGetNumberField(TEXT("floor"),Floor);
        if(FMath::IsFinite(Rack)) PendingRackCapacity=FMath::Clamp(float(Rack),0.f,1.f);
        if(FMath::IsFinite(Floor)) PendingFloorCapacity=FMath::Clamp(float(Floor),0.f,1.f);
        bCapacityPending=true;
    }
    else if(Action==TEXT("settingsReset"))
    {
        PendingInteriorAction.Empty();PendingInteriorId.Empty();bEquipment=bRacks=bShowPOIs=true;Density=TEXT("auto");
        if(auto* R=Roof()) R->SetBuildingVisible(true);
        PendingRackCapacity=.8f;PendingFloorCapacity=1.f;bCapacityPending=true;
        ApplySceneLayers();
    }
    else if(Action==TEXT("poiDensity"))
    {
        FString Value;if(Object->TryGetStringField(TEXT("value"),Value) && (Value==TEXT("auto") || Value==TEXT("minimal") || Value==TEXT("all"))) Density=Value;
        POICadence.Invalidate();PushSceneControls();
    }
    else if(Action==TEXT("preset"))
    {
        FString Value; Object->TryGetStringField(TEXT("value"),Value);
        if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
        {
            if(Value==TEXT("top"))
            {
                PendingInteriorAction.Empty();PendingInteriorId.Empty();
                const float Distance=FMath::Min(95000.f,float(Cam->OverviewDistance*ViewSize.X/FMath::Max(1.,Layout.SceneSize.X)));
                Cam->TransitionToPose(Cam->OverviewCenter,Distance,FRotator(-78,Cam->OverviewYaw,0),ViewSize,Layout.ScenePosition+Layout.SceneSize*.5,true);
            }
            else if(Value==TEXT("racks") || Value==TEXT("floor")) FocusRegion(Value);
            else Overview();
        }
    }
    else if(Action==TEXT("report") && bDiagnostics) { LastBrowserReport=Json; UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_BROWSER_REPORT %s"),*Json); }
}
bool UGHSTwinHUDWidget::SelectObject(const FString& Id,bool bFocus)
{
    if(IsReplayActive())
    {
        auto Intent=MakeShared<FJsonObject>();Intent->SetStringField(TEXT("action"),TEXT("select"));Intent->SetStringField(TEXT("id"),Id);Intent->SetBoolField(TEXT("focusSelection"),bFocus);
        FString Json;FJsonSerializer::Serialize(Intent,TJsonWriterFactory<>::Create(&Json));GuardReplayOperation(Json,TEXT("定位设备"));return false;
    }
    if(Id.StartsWith(TEXT("RACK:"))) return false;
    FVector Location,Extent; if(!SceneData.Resolve(Id,Location,Extent)) return false;
    if(!RevealForNavigation(Id)) return false;
    if(!IsInteriorAvailable()) return QueueInteriorAction(TEXT("select"),Id,bFocus);
    const bool bOpening=bPanelCollapsed;
    SelectedId=Id; ActiveRegionId.Empty(); POICadence.Invalidate();
    // Selection may open a previously collapsed panel. Use its final content area once.
    Layout=FGHSTwinLayout::Calculate(ViewSize,false);
    if(bFocus) Focus(Id);
    if(bOpening) SetPanelCollapsed(false,true); else PushSnapshot(true);
    return true;
}
void UGHSTwinHUDWidget::ClearSelection() { PendingInteriorAction.Empty(); PendingInteriorId.Empty(); SelectedId.Empty(); ActiveRegionId.Empty(); POICadence.Invalidate(); bSelectedScreenBoundsValid=false; PushSnapshot(); if(Panel) Panel->Evaluate(TEXT("window.twinClearSelection && window.twinClearSelection();")); }
UGHSWarehouseRoofComponent* UGHSTwinHUDWidget::Roof() const
{
    const auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer());
    return PC?PC->WarehouseRoof.Get():nullptr;
}
bool UGHSTwinHUDWidget::IsInteriorAvailable() const
{ const auto* R=Roof(); return !R || R->IsInteriorAvailable(); }
bool UGHSTwinHUDWidget::OpenWarehouse()
{ return BeginWarehouseOpen(false); }
bool UGHSTwinHUDWidget::BeginWarehouseOpen(bool bFast)
{
    auto* R=Roof();
    if(!R) return false;
    const bool bAlreadyOpening=R->IsOpening();
    if(!R->OpenRoof(bFast)) return false;
    if(R->IsInteriorAvailable()) return true;
    // A repeated manual request or fast upgrade must retain the queued target.
    if(!bAlreadyOpening) ClearSelection();
    SetSearchOpen(false); bWarehouseMenuOpen=false;
    VisibleLabels.Reset(); PreviousVisibleLabels.Reset(); PreviousPositions.Reset(); LabelAges.Reset();
    POICadence.Invalidate(); PushSceneControls(); return true;
}
bool UGHSTwinHUDWidget::QueueInteriorAction(const FString& Action,const FString& Id,bool bFocus)
{
    if(!BeginWarehouseOpen(true)) return false;
    PendingInteriorAction=Action; PendingInteriorId=Id; bPendingInteriorFocus=bFocus;
    // Keep the current view still until the full roof is gone. Latest request wins.
    if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn())) Cam->FreezeCurrentPose();
    return true;
}
void UGHSTwinHUDWidget::UpdateWarehousePOI()
{
    bWarehousePOIVisible=false; bWarehousePOIHovered=false;
    auto* R=Roof(); auto* PC=GetOwningPlayer();
    if(!bShowPOIs || !R || !R->IsBuildingVisible() || !R->HasRoof() ||
        (!R->IsRoofClosed() && !R->IsOpening()) || RoofHUDMotion.WarehouseOpacity()<=0.f || !PC) return;
    FVector2D Anchor;
    if(!PC->ProjectWorldLocationToScreen(R->GetPOIWorldLocation(),Anchor,false)) return;
    Anchor=Viewport.ToLogical(Anchor);
    if(!Layout.IsScenePoint(Anchor)) return;
    const FVector2D Size=WarehousePOISize;
    FVector2D At=Anchor-FVector2D(Size.X*.5,104);
    At.X=FMath::Clamp(At.X,Layout.ScenePosition.X+12,FMath::Max(Layout.ScenePosition.X+12,Layout.ScenePosition.X+Layout.SceneSize.X-Size.X-12));
    At.Y=FMath::Max(At.Y,Layout.HeaderHeight+112.);
    if(!Layout.IsScenePoint(At+Size)) return;
    if(IsSceneSearchVisible() && At.X<GetSceneSearchPosition().X+GetSceneSearchSize().X && At.X+Size.X>GetSceneSearchPosition().X && At.Y<GetSceneSearchPosition().Y+GetSceneSearchSize().Y) return;
    WarehousePOIPosition=At; WarehousePOIAnchor=Anchor; bWarehousePOIVisible=true;
    FVector2D CursorPosition;
    bWarehousePOIHovered=R->IsRoofClosed() && PC->GetMousePosition(CursorPosition.X,CursorPosition.Y) && Inside(Viewport.ToLogical(CursorPosition),At,Size);
}
bool UGHSTwinHUDWidget::ShouldDrawWarehousePOI() const
{
    const auto* R=Roof();
    return bWarehousePOIVisible && bShowPOIs && R && R->IsBuildingVisible() &&
        (R->IsRoofClosed() || R->IsOpening()) && RoofHUDMotion.WarehouseOpacity()>0.f;
}
void UGHSTwinHUDWidget::Overview()
{
    SetSearchOpen(false); bWarehouseMenuOpen=false;
    ClearSelection();
    if(auto* R=Roof()) {R->SetBuildingVisible(true);R->RestoreRoof(!bInitialViewPending);}
    PushSceneControls();
    VisibleLabels.Reset(); PreviousVisibleLabels.Reset(); PreviousPositions.Reset(); LabelAges.Reset();
    bWarehousePOIVisible=false;
    POICadence.Invalidate();
    if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
    {
        const auto Destination=FGHSTwinLayout::Calculate(ViewSize,bPanelCollapsed);
        Cam->FrameOverview(ViewSize,Destination.ScenePosition,Destination.SceneSize,bInitialViewPending?0.f:.85f);
    }
}
void UGHSTwinHUDWidget::Focus(const FString& Id)
{
    if(IsReplayActive()) {auto Intent=MakeShared<FJsonObject>();Intent->SetStringField(TEXT("action"),TEXT("focus"));Intent->SetStringField(TEXT("id"),Id);FString Json;FJsonSerializer::Serialize(Intent,TJsonWriterFactory<>::Create(&Json));GuardReplayOperation(Json);return;}
    FVector Location,Extent; if(!SceneData.Resolve(Id,Location,Extent)) return;
    if(!RevealForNavigation(Id)) return;
    if(!IsInteriorAvailable()) {QueueInteriorAction(TEXT("focus"),Id);return;}
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
    if(IsReplayActive()) {auto Intent=MakeShared<FJsonObject>();Intent->SetStringField(TEXT("action"),TEXT("preset"));Intent->SetStringField(TEXT("value"),Region);FString Json;FJsonSerializer::Serialize(Intent,TJsonWriterFactory<>::Create(&Json));GuardReplayOperation(Json);return;}
    FVector Center,Extent; if(!SceneData.RegionBounds(Region,Center,Extent)) return;
    if(!bRacks) {bRacks=true;ApplySceneLayers();PushSceneControls(TEXT("已显示货架与货物"));}
    if(!IsInteriorAvailable()) {QueueInteriorAction(TEXT("region"),Region);return;}
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
    if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
    {
        ClearSelection(); ActiveRegionId=TEXT("REGION:")+Region; POICadence.Invalidate();
        const double Tan=FMath::Tan(FMath::DegreesToRadians(Cam->WarehouseCamera->FieldOfView*.5));
        const double Fill=FMath::Clamp(FMath::Min(Layout.SceneSize.X/ViewSize.X,Layout.SceneSize.Y/ViewSize.X),.12,1.);
        const float Distance=FMath::Clamp(float(Extent.Size()/(Tan*Fill)*1.12),5000.f,95000.f);
        Cam->FocusOnTarget(Center,Distance,FRotator(-58,Cam->OverviewYaw,0),ViewSize,Layout.ScenePosition+Layout.SceneSize*.5,.95f);
    }
}
bool UGHSTwinHUDWidget::HandleChromeClick(FVector2D Position)
{
    if(bInitialLayoutPending) return false;
    if(auto* Replay=ReplaySession();Replay && Replay->IsExitPending()) return true;
    Position=Viewport.ToLogical(Position);
    if(IsSceneSearchVisible() && bSearchOpen && !bSearchIsRemote && Inside(Position,SearchLayout().Position,SearchLayout().Size))
    {
        const int32 Row=SearchLayout().RowAt(Position),Index=Row==INDEX_NONE?INDEX_NONE:SearchFirstVisible+Row;
        if(SearchResults.IsValidIndex(Index)) SelectSearchResult(SearchResults[Index].Id);
        return true;
    }
    if(FGHSTwinSceneChrome::IsHeadingPoint(Position,Layout.HeaderHeight))
    { bWarehouseMenuOpen=!bWarehouseMenuOpen;SetSearchOpen(false);return true; }
    if(bWarehouseMenuOpen)
    {
        const bool bInside=Inside(Position,FVector2D(24,Layout.HeaderHeight+110),FVector2D(320,176));
        bWarehouseMenuOpen=false;if(bInside) return true;
    }
    if(bSearchOpen && !Inside(Position,GetSceneSearchPosition(),GetSceneSearchSize())) SetSearchOpen(false);
    if(FGHSTwinHeaderLayout::Calculate(ViewSize.X).IsPanelButton(Position))
    { SetPanelCollapsed(!bPanelCollapsed); return true; }
    const int32 TypeIndex=IsInteriorAvailable() && !IsReplayActive()?FGHSTwinSceneChrome::FilterAt(Position,Layout):INDEX_NONE;
    if(TypeIndex!=INDEX_NONE)
    {
        PointFilter=TypeIndex==1?TEXT("rack"):TypeIndex==2?TEXT("truck"):TypeIndex==3?TEXT("charger"):TEXT("all");
        POICadence.Invalidate();
        return true;
    }
    return false;
}
bool UGHSTwinHUDWidget::HandleSceneClick(FVector2D Position)
{
    if(HandleChromeClick(Position)) return true;
    if(!IsScenePoint(Position)) return false;
    if(auto* Replay=ReplaySession();Replay && Replay->IsReplaying())
    {
        FVector Origin,Direction;FString Id;
        if(GetOwningPlayer()->DeprojectScreenPositionToWorld(Position.X,Position.Y,Origin,Direction) && Replay->Pick(Origin,Direction,Id)) Replay->Select(Id);
        else Replay->Select(TEXT(""));
        PushReplayState();return true;
    }
    const FVector2D LogicalPosition=Viewport.ToLogical(Position);
    if(!IsInteriorAvailable())
    {
        auto* R=Roof(); FVector Origin,Direction;
        if(R && R->IsRoofClosed() && ((bWarehousePOIVisible && Inside(LogicalPosition,WarehousePOIPosition,WarehousePOISize)) ||
            (GetOwningPlayer()->DeprojectScreenPositionToWorld(Position.X,Position.Y,Origin,Direction) && R->HitRoofRay(Origin,Direction)))) OpenWarehouse();
        // Bounds-based equipment picking must never run through an opaque or dissolving roof.
        return true;
    }
    for(int32 I=VisibleLabels.Num()-1; I>=0; --I) if(Inside(LogicalPosition,Labels[VisibleLabels[I]].Position,Labels[VisibleLabels[I]].Size))
    {
        const auto& Label=Labels[VisibleLabels[I]];
        if(Label.bRegion) { FocusRegion(Label.Id.Mid(7)); return true; }
        if(Label.bGroup)
        {
            SetPanelCollapsed(false);
            if(Label.Id==TEXT("GROUP:rack")) Navigate(TEXT("inventory"));
            else if(Panel) Panel->Evaluate(FString::Printf(TEXT("window.twinFilterType && window.twinFilterType('%s');"),*Label.Id.Mid(6)));
            return true;
        }
        return SelectObject(Label.Id);
    }
    FString Id; if(SceneData.Pick(GetOwningPlayer(),Position,Id)) return SelectObject(Id);
    ClearSelection(); return true;
}
void UGHSTwinHUDWidget::NativeTick(const FGeometry& Geometry,float DeltaSeconds)
{
    TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinHUD_Tick);
    Super::NativeTick(Geometry,DeltaSeconds);
    // Wall time must continue while scene simulation is paused, and must never
    // inherit the viewer's or deployment server's local time zone.
    WarehouseClock.Refresh(FDateTime::UtcNow());
    const FVector2D AllocatedSize=Geometry.GetLocalSize();
    if(AllocatedSize.X<1 || AllocatedSize.Y<1) return;
    FVector2D Pixels=AllocatedSize;
    if(GetWorld() && GetWorld()->GetGameViewport()) GetWorld()->GetGameViewport()->GetViewportSize(Pixels);
    Viewport=FGHSTwinViewport::FromPixels(Pixels);
    // The first Slate allocation may still use its pre-viewport DPI scale. Do
    // not frame the camera or expose that temporary layout for even one frame.
    // This is a geometry condition, not a timer, and does not alter later resizes.
    if(bInitialLayoutPending && !Viewport.MatchesGeometry(AllocatedSize)) return;
    bInitialLayoutPending=false;
    // Menus use the approved 160ms fade/short slide; the drawer retains its 420ms motion.
    WarehouseMenuProgress=FMath::FInterpConstantTo(WarehouseMenuProgress,bWarehouseMenuOpen?1.f:0.f,DeltaSeconds,1.f/.16f);
    SearchMenuProgress=bSearchIsRemote?0.f:FMath::FInterpConstantTo(SearchMenuProgress,bSearchOpen?1.f:0.f,DeltaSeconds,1.f/.16f);
    const bool bViewportChanged=!ViewSize.Equals(AllocatedSize,.5);
    ViewSize=AllocatedSize;
    // Use the actual allocated geometry at the pixel boundary, including any
    // fractional Slate rounding during a window resize.
    Viewport.LogicalSize=ViewSize;
    PanelMotion.Advance(DeltaSeconds,bPanelCollapsed);
    PanelVisibilityProgress=PanelMotion.Progress;
    UpdateBrowserVisibility();
    if(bViewportChanged) POICadence.Invalidate();
    const FVector2D PreviousSceneSize=Layout.SceneSize;
    Layout=FGHSTwinLayout::Calculate(ViewSize,bPanelCollapsed && PanelVisibilityProgress<=0);
    if(!PreviousSceneSize.Equals(Layout.SceneSize,.5)) POICadence.Invalidate();
    if(bInitialViewPending && GetOwningPlayerPawn()) { Overview(); bInitialViewPending=false; }
    // A panel toggle changes UI/input bounds only; it must never initiate camera focus.
    else if(bViewportChanged && !SelectedId.IsEmpty() && !IsReplayActive()) Focus(SelectedId);
    else if(bViewportChanged)
    {
        // Packaged windows can tick at a temporary narrow size before -ResX/-ResY
        // is applied. Recompute the untouched overview for the final viewport;
        // do not retain bottom-sheet framing or overwrite a user's orbit/pan/zoom.
        if(auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn());Cam && Cam->IsOverviewFraming())
        {
            const auto Destination=FGHSTwinLayout::Calculate(ViewSize,bPanelCollapsed);
            Cam->FrameOverview(ViewSize,Destination.ScenePosition,Destination.SceneSize,0.f);
        }
    }
    // Keep the CEF viewport at its expanded size throughout and after the slide.
    // Resizing it to zero on close causes a relayout/blank frame on the next open.
    const auto Expanded=FGHSTwinLayout::Calculate(ViewSize);
    if(PanelSlot) { PanelSlot->SetPosition(Expanded.PanelPosition); PanelSlot->SetSize(Expanded.PanelSize); }
    UpdateBrowserViewport();
    if(Panel)
    {
        Panel->SetVisibility(PanelVisibilityProgress<=0 ? ESlateVisibility::Collapsed : ESlateVisibility::Visible);
        Panel->SetRenderOpacity(1.f);
        Panel->SetRenderTranslation(PanelMotion.Position(Expanded)-Expanded.PanelPosition);
    }
    if(ReplayOverlay && ReplayOverlaySlot)
    {
        const FVector2D OverlaySize(FMath::Max(320.,Layout.SceneSize.X-48),168);
        const FVector2D OverlayPosition(Layout.ScenePosition.X+24,ViewSize.Y-192);
        const bool bChanged=!LastReplayViewport.Equals(OverlaySize,.1);
        ReplayOverlaySlot->SetPosition(OverlayPosition);ReplayOverlaySlot->SetSize(OverlaySize);
        ReplayOverlay->SetVisibility(IsReplayActive()?ESlateVisibility::Visible:ESlateVisibility::Hidden);
        if(bChanged && bReplayOverlayReady && IsReplayActive())
        {ReplayOverlay->Evaluate(FString::Printf(TEXT("window.twinSetViewport && window.twinSetViewport(%.4f,168);"),OverlaySize.X));LastReplayViewport=OverlaySize;}
    }
    // Search uses the same eased edge as the scene controls. Keep its dimensions
    // and responsive visibility stable while the drawer moves so it cannot snap
    // or suddenly appear at the final frame of the animation.
    if(SearchSlot) { SearchSlot->SetPosition(PanelMotion.SceneSearchPosition(ViewSize)); SearchSlot->SetSize(FVector2D(FMath::Max(0.,FMath::Min(360.,Expanded.SceneSize.X-160)),48)); }
    if(SearchBox) SearchBox->SetVisibility(Expanded.SceneSize.X>=720 ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
    const double Now=GetWorld()->GetTimeSeconds();
    {
        TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinHUD_SceneRefresh);
        if(!IsReplayActive())
        {
            SceneData.MaintainCache(128);
            if(Now>=NextRefresh) { SceneData.Refresh(GetWorld(),true); PushSnapshot(); NextRefresh=Now+2; }
        }
    }
    if(bSearchPending && (!SearchBox || !SearchBox->IsComposing()))
    {
        SearchQuery=PendingSearchText;bSearchPending=false;bSearchOpen=true;bSearchIsRemote=false;SearchRequestId=0;SearchClientId.Empty();RefreshSearch(0);
    }
    else if(bSearchOpen && SearchRevision!=SceneData.GetRevision()) RefreshSearch();
    PushSearchState();
    if(bCapacityPending)
    {
        bCapacityPending=false;
        if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer());PC && PC->StorageCapacity)
            PC->StorageCapacity->SetCapacity(PendingRackCapacity,PendingFloorCapacity);
        if(!SelectedId.IsEmpty() && !SceneData.IsObjectVisible(SelectedId)) ClearSelection();
        PushSceneControls();
    }
    const bool bInterior=IsInteriorAvailable();
    const auto* R=Roof();
    const bool bRoofClosed=R && R->IsRoofClosed(),bRoofOpening=R && R->IsOpening(),bRoofClosing=R && R->IsClosing();
    RoofHUDMotion.Advance(bRoofClosed,bRoofOpening,bInterior,DeltaSeconds);
    if(bInterior!=bLastInteriorAvailable || bRoofClosed!=bLastRoofClosed || bRoofOpening!=bLastRoofOpening || bRoofClosing!=bLastRoofClosing)
    {
        bLastInteriorAvailable=bInterior;bLastRoofClosed=bRoofClosed;bLastRoofOpening=bRoofOpening;bLastRoofClosing=bRoofClosing;
        POICadence.Invalidate();PushSceneControls();
    }
    if(bInterior && !PendingInteriorAction.IsEmpty())
    {
        const FString Action=PendingInteriorAction,Id=PendingInteriorId;const bool bFocus=bPendingInteriorFocus;
        PendingInteriorAction.Empty();PendingInteriorId.Empty();
        if(Action==TEXT("select")) SelectObject(Id,bFocus);
        else if(Action==TEXT("focus")) Focus(Id);
        else if(Action==TEXT("region")) FocusRegion(Id);
    }
    if(auto* Replay=ReplaySession();Replay && Replay->IsReplaying())
    {
        const FVector4 Rect=GetReplaySceneRect();
        Replay->Advance(DeltaSeconds,ViewSize,FVector2D(Rect.X+Rect.Z*.5,Rect.Y+Rect.W*.5));
        if(Now>=NextReplayPush) {PushReplayState();NextReplayPush=Now+.1;}
        bWarehousePOIVisible=false;bSelectedScreenBoundsValid=false;
        VisibleLabels.Reset();PreviousVisibleLabels.Reset();PreviousPositions.Reset();LabelAges.Reset();return;
    }
    UpdateWarehousePOI();
    UpdateSelectedScreenBounds();
    if(!bInterior || !bShowPOIs || !GetOwningPlayer())
    { VisibleLabels.Reset();PreviousVisibleLabels.Reset();PreviousPositions.Reset();LabelAges.Reset();return; }
    auto* Cam=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn());
    const bool bAggregate=Cam && Cam->SpringArmComponent->TargetArmLength>14000 && Density!=TEXT("all");
    const bool bCandidatesChanged=POICadence.Consume(Now,SceneData.GetRevision(),bAggregate);
    if(bCandidatesChanged) RebuildPOICandidates(bAggregate);
    // Fast movement may expose a different candidate between cadence ticks. It only
    // repeats visibility layout; it does not regenerate catalogue strings or groups.
    const FRotator Rotation=Cam?Cam->GetActorRotation():FRotator::ZeroRotator;
    const FVector Location=Cam?Cam->GetActorLocation():FVector::ZeroVector;
    const FRotator Delta=(Rotation-LastLayoutRotation).GetNormalized();
    const bool bFastMovement=FMath::Abs(Delta.Yaw)>2.5 || FMath::Abs(Delta.Pitch)>2.5 || FVector::DistSquared(Location,LastLayoutLocation)>40000;
    const bool bRelayout=bCandidatesChanged || bViewportChanged || bFastMovement;
    if(bRelayout) {LastLayoutRotation=Rotation;LastLayoutLocation=Location;}
    UpdateVisiblePOIs(DeltaSeconds,bRelayout);
}
void UGHSTwinHUDWidget::RebuildPOICandidates(bool bAggregate)
{
    TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinHUD_POICandidates);
    ++CandidateBuildCount;
    auto Points=SceneData.Points();
    if(!SelectedId.IsEmpty() && !Points.ContainsByPredicate([this](const FGHSTwinPoint& P){return P.Id==SelectedId;}))
    { FVector Location; if(SceneData.ResolvePoint(SelectedId,Location)) Points.Add({SelectedId,TEXT("选中物料"),TEXT("material"),TEXT("scene"),Location,false}); }
    Points.RemoveAll([this](const FGHSTwinPoint& P){return P.Id!=SelectedId && PointFilter!=TEXT("all") && P.Kind!=PointFilter;});
    if(bAggregate)
    {
        TMap<FString,FGHSTwinPoint> Groups; TMap<FString,int32> Counts; TArray<FGHSTwinPoint> Chosen;
        for(const auto& P:Points)
        {
            if(P.Id==SelectedId || P.Id.StartsWith(TEXT("REGION:"))) { Chosen.Add(P); continue; }
            auto& Group=Groups.FindOrAdd(P.Kind); Group.Kind=P.Kind; Group.Location+=P.Location; Group.bAlert|=P.bAlert;
            if(P.Status==TEXT("fault")) Group.Status=TEXT("fault"); else if(P.bAlert && Group.Status!=TEXT("fault")) Group.Status=TEXT("warning");
            ++Counts.FindOrAdd(P.Kind);
        }
        static const TMap<FString,FString> Names{{TEXT("agv"),TEXT("AGV")},{TEXT("forklift"),TEXT("人工叉车")},{TEXT("stacker"),TEXT("堆高车")},{TEXT("truck"),TEXT("装卸车")},{TEXT("charger"),TEXT("充电设施")},{TEXT("rack"),TEXT("货架区")}};
        for(auto& Entry:Groups) { auto& P=Entry.Value; P.Location/=Counts[Entry.Key]; P.Id=TEXT("GROUP:")+Entry.Key; const FString* Name=Names.Find(Entry.Key); P.Title=Entry.Key==TEXT("rack")?TEXT("货架区域"):FString::Printf(TEXT("%s · %d"),Name?**Name:*Entry.Key,Counts[Entry.Key]); Chosen.Add(P); }
        Points=MoveTemp(Chosen);
    }
    Points.StableSort([this](const FGHSTwinPoint& A,const FGHSTwinPoint& B) { if(A.Id==B.Id) return false; const bool AS=A.Id==SelectedId || A.Id==ActiveRegionId, BS=B.Id==SelectedId || B.Id==ActiveRegionId; if(AS!=BS) return AS; return A.bAlert && !B.bAlert; });
    Labels.Reset();Labels.Reserve(Points.Num());
    for(const auto& P:Points)
    {
        FLabel L;L.Id=P.Id;L.Text=P.Title;L.Kind=P.Kind;L.Status=P.Status;L.WorldLocation=P.Location;L.bAlert=P.bAlert;
        L.bRegion=P.Id.StartsWith(TEXT("REGION:"));L.bGroup=P.Id.StartsWith(TEXT("GROUP:"));
        L.Size=FVector2D(L.bRegion?176:L.bGroup?246:236,42);
        L.DisplayTitle=L.bRegion || L.bGroup?L.Text:L.Id.Len()<22?L.Id:TEXT("货架物料");
        L.State=TEXT("待接入");L.Accent=C(TEXT("8490A2"));
        if(L.Status==TEXT("running") || L.Status==TEXT("charging")) {L.State=L.Status==TEXT("charging")?TEXT("充电中"):TEXT("运行");L.Accent=C(TEXT("087B68"));}
        else if(L.Status==TEXT("fault")) {L.State=TEXT("故障");L.Accent=C(TEXT("B53743"));}
        else if(L.Status==TEXT("warning") || L.bAlert) {L.State=TEXT("预警");L.Accent=C(TEXT("92580D"));}
        else if(L.Status==TEXT("idle")) L.State=TEXT("待机");
        else if(L.Status==TEXT("offline")) L.State=TEXT("离线");
        else if(L.Status==TEXT("scene")) {L.State=TEXT("场景");L.Accent=C(TEXT("356BFA"));}
        if(L.bGroup && !L.bAlert) L.State=TEXT("设备");
        L.TitleMetrics=GHSTwinTypography::Measure(L.DisplayTitle,Font(14));L.StateMetrics=GHSTwinTypography::Measure(L.State,Font(12));
        L.BadgeWidth=FMath::Max(40.,L.StateMetrics.Size.X+16.);
        Labels.Add(MoveTemp(L));
    }
}
void UGHSTwinHUDWidget::UpdateSelectedScreenBounds()
{
    TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinHUD_SelectedProjection);
    bSelectedScreenBoundsValid=false;
    if(!IsInteriorAvailable() || SelectedId.IsEmpty() || !GetOwningPlayer()) return;
    FVector Center,Extent;if(!SceneData.Resolve(SelectedId,Center,Extent)) return;
    SelectedScreenMin=FVector2D(1.e8,1.e8);SelectedScreenMax=FVector2D(-1.e8,-1.e8);
    for(int32 I=0;I<8;++I)
    {
        FVector2D P;
        ++SelectionProjectionCount;
        if(!GetOwningPlayer()->ProjectWorldLocationToScreen(Center+Extent*FVector(I&1?1:-1,I&2?1:-1,I&4?1:-1),P,false)) return;
        P=Viewport.ToLogical(P);
        SelectedScreenMin.X=FMath::Min(SelectedScreenMin.X,P.X);SelectedScreenMin.Y=FMath::Min(SelectedScreenMin.Y,P.Y);
        SelectedScreenMax.X=FMath::Max(SelectedScreenMax.X,P.X);SelectedScreenMax.Y=FMath::Max(SelectedScreenMax.Y,P.Y);
    }
    bSelectedScreenBoundsValid=true;
}
void UGHSTwinHUDWidget::UpdateVisiblePOIs(float DeltaSeconds,bool bRelayout)
{
    TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinHUD_VisibleProjection);
    ++VisibleProjectionFrames;
    Swap(VisibleLabels,PreviousVisibleLabels);VisibleLabels.Reset();
    const int32 Maximum=Density==TEXT("minimal")?6:Density==TEXT("all")?32:16;
    const FVector2D SelectedMin=SelectedScreenMin-FVector2D(8,8),SelectedMax=SelectedScreenMax+FVector2D(8,8);
    TSet<FString> Current;
    float CursorX=0,CursorY=0;const bool bCursor=GetOwningPlayer()->GetMousePosition(CursorX,CursorY);
    const FVector2D LogicalCursor=Viewport.ToLogical(FVector2D(CursorX,CursorY));
    const int32 Count=bRelayout?Labels.Num():PreviousVisibleLabels.Num();
    for(int32 I=0;I<Count;++I)
    {
        const int32 Index=bRelayout?I:PreviousVisibleLabels[I];
        if(!Labels.IsValidIndex(Index)) continue;
        auto& L=Labels[Index];FVector World=L.WorldLocation;
        // Aggregates intentionally retain the 100ms centroid. Actual objects and
        // selected CAD instances resolve their current world anchor on every frame.
        if(!L.bGroup && !SceneData.ResolvePoint(L.Id,World)) continue;
        ++PointProjectionCount;
        FVector2D Screen;if(!GetOwningPlayer()->ProjectWorldLocationToScreen(World,Screen,false)) continue;
        Screen=Viewport.ToLogical(Screen);
        const bool Selected=L.Id==SelectedId || L.Id==ActiveRegionId;
        const FVector2D Size=L.Size;
        FVector2D At=Screen-FVector2D(Size.X*.5,Size.Y+28);
        if(!Layout.IsScenePoint(At-FVector2D(4,4)) || !Layout.IsScenePoint(At+Size+FVector2D(4,4)) || At.Y<Layout.HeaderHeight+64) continue;
        bool Overlap=false;const FVector2D Original=At;
        const int32 Attempts=L.bGroup || L.bRegion?7:1;
        for(int32 Attempt=0;Attempt<Attempts;++Attempt)
        {
            At=Original+FVector2D(0,Attempt==0?0:((Attempt+1)/2)*60*(Attempt%2?-1:1));
            Overlap=!Layout.IsScenePoint(At) || !Layout.IsScenePoint(At+Size) || At.Y<Layout.HeaderHeight+110;
            Overlap|=FGHSTwinSceneChrome::Overlaps(At,Size,Layout);
            if(Inside(Screen,At-FVector2D(14,14),Size+FVector2D(28,28))) Overlap=true;
            if(!Selected && bSelectedScreenBoundsValid && At.X<SelectedMax.X && At.X+Size.X>SelectedMin.X && At.Y<SelectedMax.Y && At.Y+Size.Y>SelectedMin.Y) Overlap=true;
            for(int32 ExistingIndex:VisibleLabels)
            {
                const auto& Existing=Labels[ExistingIndex];
                if(FMath::Abs((At+Size*.5-Existing.Position-Existing.Size*.5).X)<(Size.X+Existing.Size.X)*.5+12 && FMath::Abs((At+Size*.5-Existing.Position-Existing.Size*.5).Y)<(Size.Y+Existing.Size.Y)*.5+12) {Overlap=true;break;}
            }
            if(!Overlap) break;
        }
        if(Overlap && !Selected) continue;
        // Scene headings and filters always win, including over selected labels.
        if(FGHSTwinSceneChrome::Overlaps(At,Size,Layout)) continue;
        if(auto* Previous=PreviousPositions.Find(L.Id)) At=GHSHUDMotion::FollowPosition(*Previous,At,DeltaSeconds);
        if(FGHSTwinSceneChrome::Overlaps(At,Size,Layout)) continue;
        PreviousPositions.Add(L.Id,At);Current.Add(L.Id);
        float& Age=LabelAges.FindOrAdd(L.Id);Age+=DeltaSeconds;
        L.Position=At;L.Anchor=Screen;L.bSelected=Selected;L.bHovered=bCursor && Inside(LogicalCursor,At,Size);
        L.Opacity=FMath::Min(GHSHUDMotion::Progress(Age),RoofHUDMotion.InteriorOpacity());
        VisibleLabels.Add(Index);if(VisibleLabels.Num()>=Maximum) break;
    }
    for(auto It=LabelAges.CreateIterator();It;++It) if(!Current.Contains(It.Key())) {PreviousPositions.Remove(It.Key());It.RemoveCurrent();}
}
FString UGHSTwinHUDWidget::GetPOIReport() const
{
    TArray<TSharedPtr<FJsonValue>> Items;
    if(ShouldDrawWarehousePOI())
    {
        auto Item=MakeShared<FJsonObject>();Item->SetStringField(TEXT("id"),TEXT("WAREHOUSE:GHS"));
        Item->SetStringField(TEXT("icon"),TEXT("warehouse"));Item->SetNumberField(TEXT("x"),WarehousePOIPosition.X);Item->SetNumberField(TEXT("y"),WarehousePOIPosition.Y);
        Item->SetNumberField(TEXT("width"),WarehousePOISize.X);Item->SetNumberField(TEXT("height"),WarehousePOISize.Y);Items.Add(MakeShared<FJsonValueObject>(Item));
        Item->SetNumberField(TEXT("opacity"),RoofHUDMotion.WarehouseOpacity());Item->SetBoolField(TEXT("interactive"),Roof()->IsRoofClosed());
    }
    if(IsInteriorAvailable()) for(const int32 Index:VisibleLabels)
    {
        const auto& Label=Labels[Index];
        auto Item=MakeShared<FJsonObject>(); Item->SetStringField(TEXT("id"),Label.Id); Item->SetStringField(TEXT("icon"),Label.Kind);
        Item->SetBoolField(TEXT("selected"),Label.bSelected); Item->SetNumberField(TEXT("height"),Label.Size.Y);
        Item->SetNumberField(TEXT("opacity"),Label.Opacity);
        Item->SetStringField(TEXT("fill"),Label.bSelected?TEXT("356BFA"):TEXT("FFFFFF"));
        Item->SetNumberField(TEXT("x"),Label.Position.X); Item->SetNumberField(TEXT("y"),Label.Position.Y);
        Item->SetNumberField(TEXT("titleInkTop"),Label.TitleMetrics.CenteredOriginY(Label.Size.Y)+Label.TitleMetrics.InkTop);
        Item->SetNumberField(TEXT("titleInkBottom"),Label.TitleMetrics.CenteredOriginY(Label.Size.Y)+Label.TitleMetrics.InkBottom);
        Item->SetNumberField(TEXT("badgeHeight"),24);
        Item->SetNumberField(TEXT("badgeInkTop"),Label.StateMetrics.CenteredOriginY(24)+Label.StateMetrics.InkTop);
        Item->SetNumberField(TEXT("badgeInkBottom"),Label.StateMetrics.CenteredOriginY(24)+Label.StateMetrics.InkBottom);
        Items.Add(MakeShared<FJsonValueObject>(Item));
    }
    auto Root=MakeShared<FJsonObject>(); Root->SetArrayField(TEXT("labels"),Items); Root->SetNumberField(TEXT("selectionStroke"),6);
    Root->SetStringField(TEXT("pointFilter"),PointFilter);
    Root->SetBoolField(TEXT("interiorAvailable"),IsInteriorAvailable());
    Root->SetStringField(TEXT("pendingNavigation"),PendingInteriorAction);
    Root->SetStringField(TEXT("pendingNavigationId"),PendingInteriorId);
    Root->SetNumberField(TEXT("warehousePOIOpacity"),ShouldDrawWarehousePOI()?RoofHUDMotion.WarehouseOpacity():0.f);
    Root->SetNumberField(TEXT("interiorLabelOpacity"),IsInteriorAvailable()?RoofHUDMotion.InteriorOpacity():0.f);
    if(const auto* R=Roof())
    {Root->SetBoolField(TEXT("roofClosed"),R->IsRoofClosed());Root->SetBoolField(TEXT("roofOpening"),R->IsOpening());Root->SetBoolField(TEXT("roofClosing"),R->IsClosing());Root->SetBoolField(TEXT("roofTransitioning"),R->IsTransitioning());Root->SetNumberField(TEXT("roofProgress"),R->GetOpenProgress());}
    if(bDiagnostics)
    {
        const auto Header=FGHSTwinHeaderLayout::Calculate(ViewSize.X);
        auto Clock=MakeShared<FJsonObject>();
        Clock->SetStringField(TEXT("time"),WarehouseClock.TimeText);Clock->SetStringField(TEXT("date"),WarehouseClock.DateText);
        Clock->SetStringField(TEXT("zone"),TEXT("America/Los_Angeles"));Clock->SetNumberField(TEXT("headerHeight"),Header.Height);
        Clock->SetNumberField(TEXT("width"),ViewSize.X);Clock->SetNumberField(TEXT("addressX"),Header.AddressPosition.X);Clock->SetNumberField(TEXT("addressY"),Header.AddressPosition.Y);
        Clock->SetNumberField(TEXT("clockX"),Header.ClockPosition.X);Clock->SetNumberField(TEXT("clockY"),Header.ClockPosition.Y);
        Root->SetObjectField(TEXT("warehouseClock"),Clock);
        TArray<TSharedPtr<FJsonValue>> Regions;
        for(const auto& Point:SceneData.Points()) if(Point.Id.StartsWith(TEXT("REGION:")))
        {
            auto Region=MakeShared<FJsonObject>();Region->SetStringField(TEXT("id"),Point.Id);
            Region->SetArrayField(TEXT("worldPosition"),{MakeShared<FJsonValueNumber>(Point.Location.X),MakeShared<FJsonValueNumber>(Point.Location.Y),MakeShared<FJsonValueNumber>(Point.Location.Z)});
            Regions.Add(MakeShared<FJsonValueObject>(Region));
        }
        Root->SetArrayField(TEXT("regionPoints"),Regions);
    }
    auto Work=MakeShared<FJsonObject>();Work->SetNumberField(TEXT("candidateBuilds"),double(CandidateBuildCount));
    Work->SetNumberField(TEXT("projectionFrames"),double(VisibleProjectionFrames));Work->SetNumberField(TEXT("pointProjections"),double(PointProjectionCount));
    Work->SetNumberField(TEXT("selectionProjections"),double(SelectionProjectionCount));Work->SetNumberField(TEXT("candidateCount"),Labels.Num());
    Work->SetBoolField(TEXT("browserActive"),bBrowserActive);Work->SetBoolField(TEXT("diagnostics"),bDiagnostics);
    const auto Cache=SceneData.GetCacheStats();
    Work->SetNumberField(TEXT("worldScans"),double(Cache.WorldScans));Work->SetNumberField(TEXT("snapshotSerializations"),double(Cache.SnapshotSerializations));
    Root->SetObjectField(TEXT("performance"),Work);
    FString Out; FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Out)); return Out;
}
int32 UGHSTwinHUDWidget::NativePaint(const FPaintArgs& Args,const FGeometry& G,const FSlateRect& Clip,FSlateWindowElementList& Elements,int32 Layer,const FWidgetStyle& Style,bool Enabled) const
{
    TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinHUD_Paint);
    if(bInitialLayoutPending) return Layer;
    Layer=Super::NativePaint(Args,G,Clip,Elements,Layer,Style,Enabled);
    float DrawOpacity=1;
    auto Box=[&](FVector2D At,FVector2D Size,FLinearColor Fill,float Radius=0.f,FLinearColor Border=FLinearColor::Transparent,float BorderWidth=1.f)
    { Fill.A*=DrawOpacity;Border.A*=DrawOpacity;FSlateRoundedBoxBrush Brush(FLinearColor::White,Radius,Border,Border.A>0?BorderWidth:0); FSlateDrawElement::MakeBox(Elements,++Layer,G.ToPaintGeometry(Size,FSlateLayoutTransform(At)),&Brush,ESlateDrawEffect::None,Fill); };
    auto Text=[&](FVector2D At,const FString& Value,int Size,FLinearColor Color)
    { Color.A*=DrawOpacity;FSlateDrawElement::MakeText(Elements,++Layer,G.ToPaintGeometry(FVector2D(600,Size+10),FSlateLayoutTransform(At)),Value,Font(Size),ESlateDrawEffect::None,Color); };
    auto Line=[&](FVector2D A,FVector2D B,FLinearColor Color,float Width=1.f)
    { FSlateDrawElement::MakeLines(Elements,++Layer,G.ToPaintGeometry(),TArray<FVector2D>{A,B},ESlateDrawEffect::None,Color,true,Width); };
    const auto Header=FGHSTwinHeaderLayout::Calculate(ViewSize.X);
    const FLinearColor HeaderMuted=C(TEXT("B3C1D1")),HeaderIcon=C(TEXT("8BAFFF"));
    auto HeaderText=[&](FVector2D At,const FString& Value,int Size,double RowHeight,FLinearColor Ink)
    { Text(At+FVector2D(0,GHSTwinTypography::Measure(Value,Font(Size)).CenteredOriginY(RowHeight)),Value,Size,Ink); };
    Box(FVector2D::ZeroVector,FVector2D(ViewSize.X,Layout.HeaderHeight),C(TEXT("172333")));
    const double LogoY=(Header.BrandRowHeight-21)*.5;
    Box(FVector2D(22,LogoY),FVector2D(9,9),C(TEXT("356BFA")),1); Box(FVector2D(34,LogoY),FVector2D(9,9),C(TEXT("78A3FF")),1); Box(FVector2D(22,LogoY+12),FVector2D(9,9),C(TEXT("78A3FF")),1); Box(FVector2D(34,LogoY+12),FVector2D(9,9),C(TEXT("356BFA")),1);
    HeaderText(FVector2D(57,0),Header.bCompactBrand?TEXT("GHS 数字孪生"):TEXT("GHS 仓储数字孪生"),17,Header.BrandRowHeight,FLinearColor::White);
    if(Header.bShowContext) HeaderText(FVector2D(300,0),TEXT("三维运营中心"),12,Header.BrandRowHeight,HeaderMuted);
    if(ViewSize.X>=1000)
    {
        Line(FVector2D(Header.AddressPosition.X-20,18),FVector2D(Header.AddressPosition.X-20,46),C(TEXT("354253")));
        Line(FVector2D(ViewSize.X-128,18),FVector2D(ViewSize.X-128,46),C(TEXT("354253")));
    }
    const FVector2D Address=Header.AddressPosition,Clock=Header.ClockPosition;
    // Small line icons match the existing native HUD; no icon texture or tick is needed.
    auto HeaderPath=[&](FVector2D At,std::initializer_list<FVector2D> Points)
    { TArray<FVector2D> P;for(const auto& V:Points) P.Add(At+V);FSlateDrawElement::MakeLines(Elements,++Layer,G.ToPaintGeometry(),P,ESlateDrawEffect::None,HeaderIcon,true,1.3f); };
    HeaderPath(Address+FVector2D(0,15),{{8,18},{2,10},{1,6},{3,2},{8,0},{13,2},{15,6},{14,10},{8,18}});
    HeaderPath(Address+FVector2D(0,15),{{8,4},{5,7},{8,10},{11,7},{8,4}});
    HeaderText(Address+FVector2D(28,0),TEXT("17335 Glen Helen Pkwy"),13,23,FLinearColor::White);
    HeaderText(Address+FVector2D(28,25),TEXT("San Bernardino, CA 92407 美国"),11,19,HeaderMuted);
    TArray<FVector2D> Circle;
    for(int32 I=0;I<=20;++I) {const double A=I*2.*PI/20.;Circle.Add(Clock+FVector2D(8+8*FMath::Cos(A),23+8*FMath::Sin(A)));}
    FSlateDrawElement::MakeLines(Elements,++Layer,G.ToPaintGeometry(),Circle,ESlateDrawEffect::None,HeaderIcon,true,1.3f);
    HeaderPath(Clock+FVector2D(8,23),{{0,-5},{0,0},{4,2}});
    HeaderText(Clock+FVector2D(28,0),TEXT("仓库当地时间"),11,23,HeaderMuted);
    // Each digit has a fixed advance, so even fallback fonts cannot jitter the clock.
    double DigitX=Clock.X+130;
    for(const TCHAR Ch:WarehouseClock.TimeText)
    {
        const FString Glyph=FString::Chr(Ch);const double Cell=Ch==TEXT(':')?7:15;
        const double Width=GHSTwinTypography::Measure(Glyph,Font(19)).Size.X;
        HeaderText(FVector2D(DigitX+(Cell-Width)*.5,Clock.Y),Glyph,19,23,FLinearColor::White);DigitX+=Cell;
    }
    // The bundled CJK font lacks the mathematical minus glyph; use its normal
    // hyphen for the visible offset instead of rendering a missing-glyph box.
    HeaderText(Clock+FVector2D(28,25),WarehouseClock.DateText.Replace(TEXT("−"),TEXT("-")),11,19,HeaderMuted);
    HeaderText(Header.PanelButtonPosition+FVector2D(10,0),bPanelCollapsed?TEXT("展开面板"):TEXT("收起面板"),12,Header.PanelButtonSize.Y,FLinearColor::White);
    Box(FVector2D(24,Layout.HeaderHeight+16),FVector2D(256,84),FLinearColor::White,12,C(TEXT("DFE7F2")));
    Text(FVector2D(48,Layout.HeaderHeight+28),TEXT("GHS"),22,C(TEXT("25364B")));
    FString Area=SceneData.LocationLabel(SelectedId);
    if(Area.IsEmpty()) Area=ActiveRegionId==TEXT("REGION:racks")?TEXT("货架区域"):ActiveRegionId==TEXT("REGION:floor")?TEXT("地堆区域"):TEXT("全部区域");
    Text(FVector2D(48,Layout.HeaderHeight+65),Area.Left(12),11,C(TEXT("5B6C82")));
    Line(FVector2D(252,Layout.HeaderHeight+53),FVector2D(257,Layout.HeaderHeight+58),C(TEXT("5B6C82")),1.5);
    Line(FVector2D(257,Layout.HeaderHeight+58),FVector2D(262,Layout.HeaderHeight+53),C(TEXT("5B6C82")),1.5);
    if(IsInteriorAvailable() && !IsReplayActive() && FGHSTwinSceneChrome::FiltersVisible(Layout))
    {
        Text(FVector2D(32,Layout.HeaderHeight+116),TEXT("按类型查看"),11,C(TEXT("5B6C82")));
        const TCHAR* Names[]={TEXT("全部设备"),TEXT("货架区域"),TEXT("装卸车辆"),TEXT("充电设施")};
        const TCHAR* Filters[]={TEXT("all"),TEXT("rack"),TEXT("truck"),TEXT("charger")};
        for(int I=0;I<4;++I) { const FVector2D At=FGHSTwinSceneChrome::FilterPosition(Layout.HeaderHeight,I); Box(At,FGHSTwinSceneChrome::FilterSize(),FLinearColor::White,FGHSTwinSceneChrome::CornerRadius,C(PointFilter==Filters[I]?TEXT("356BFA"):TEXT("E5EAF2")),PointFilter==Filters[I]?3.f:1.f); Text(At+FVector2D(15,12),Names[I],11,C(PointFilter==Filters[I]?TEXT("356BFA"):TEXT("25364B"))); }
    }
    if(IsInteriorAvailable() && bSelectedScreenBoundsValid && Layout.IsScenePoint((SelectedScreenMin+SelectedScreenMax)*.5))
    {
        // Tick already projected the eight model corners for POI avoidance.
        FVector2D Min=SelectedScreenMin,Max=SelectedScreenMax;
        Min.X=FMath::Max(Min.X,8.);Min.Y=FMath::Max(Min.Y,Layout.HeaderHeight+8);Max.X=FMath::Min(Max.X,Layout.SceneSize.X-8);Max.Y=FMath::Min(Max.Y,Layout.ScenePosition.Y+Layout.SceneSize.Y-8);
        const FLinearColor Blue=C(TEXT("356BFA"));
        for(const float Width:{9.f,6.f}) for(int I=0;I<4;++I) {const FVector2D P(I&1?Max.X:Min.X,I&2?Max.Y:Min.Y);const FLinearColor Ink=Width>6?FLinearColor::White:Blue;Line(P,P+FVector2D(I&1?-28:28,0),Ink,Width);Line(P,P+FVector2D(0,I&2?-28:28),Ink,Width);}
    }
    if(ShouldDrawWarehousePOI())
    {
        DrawOpacity=RoofHUDMotion.WarehouseOpacity();
        const FVector2D At=WarehousePOIPosition,Anchor=WarehousePOIAnchor,Size=WarehousePOISize;
        const FLinearColor Blue=C(TEXT("356BFA"));
        Line(At+FVector2D(Size.X*.5,Size.Y),Anchor,Blue.CopyWithNewOpacity(.65f*DrawOpacity),1.25f);
        Box(Anchor-FVector2D(15,7),FVector2D(30,14),FLinearColor::White,7,Blue.CopyWithNewOpacity(.45f));
        Box(Anchor-FVector2D(3,3),FVector2D(6,6),Blue,3);
        Box(At+FVector2D(0,3),Size,FLinearColor(.05,.10,.18,.065),10);
        Box(At,Size,FLinearColor::White,10,bWarehousePOIHovered?Blue:C(TEXT("D6DFEC")),bWarehousePOIHovered?2.f:1.f);
        Box(At+FVector2D(12,14),FVector2D(28,28),C(TEXT("EDF3FF")),7);
        const FVector2D Icon=At+FVector2D(15,17);
        auto WarehouseLine=[&](FVector2D A,FVector2D B){Line(Icon+A,Icon+B,Blue.CopyWithNewOpacity(DrawOpacity),1.5f);};
        WarehouseLine({0,7},{11,1});WarehouseLine({11,1},{22,7});WarehouseLine({2,7},{2,21});WarehouseLine({20,7},{20,21});WarehouseLine({2,21},{20,21});
        WarehouseLine({7,21},{7,11});WarehouseLine({7,11},{15,11});WarehouseLine({15,11},{15,21});WarehouseLine({7,15},{15,15});
        const FString Status=Roof()->IsOpening()?TEXT("正在打开"):TEXT("点击查看");
        const auto Title=GHSTwinTypography::Measure(TEXT("GHS · 主仓库"),Font(14));
        const auto Subtitle=GHSTwinTypography::Measure(Status,Font(12));
        Text(At+FVector2D(52,7+Title.CenteredOriginY(22)),TEXT("GHS · 主仓库"),14,C(TEXT("25364B")));
        Text(At+FVector2D(52,30+Subtitle.CenteredOriginY(18)),Status,12,C(TEXT("536478")));
        Line(At+FVector2D(204,22),At+FVector2D(210,28),Blue.CopyWithNewOpacity(DrawOpacity),1.5f);Line(At+FVector2D(210,28),At+FVector2D(204,34),Blue.CopyWithNewOpacity(DrawOpacity),1.5f);
        DrawOpacity=1.f;
    }
    // Render stems beneath every card. A tag moved below its anchor connects
    // from the top edge; neither its stem nor its anchor may overwrite text.
    if(IsInteriorAvailable()) for(const int32 Index:VisibleLabels)
    {
        const FLabel& L=Labels[Index];
        if(Inside(L.Anchor,L.Position-FVector2D(2,2),L.Size+FVector2D(4,4))) continue;
        const FLinearColor Accent=L.Accent;
        const FVector2D Edge(FMath::Clamp(L.Anchor.X,L.Position.X,L.Position.X+L.Size.X),
            FMath::Clamp(L.Anchor.Y,L.Position.Y,L.Position.Y+L.Size.Y));
        Line(Edge,L.Anchor,Accent.CopyWithNewOpacity(.6f*L.Opacity));
        FSlateDrawElement::MakeLines(Elements,++Layer,G.ToPaintGeometry(FVector2D(24,10),FSlateLayoutTransform(L.Anchor)),UnitAnchorEllipse(),ESlateDrawEffect::None,Accent.CopyWithNewOpacity(.55f*L.Opacity),true,1.f);
        Box(L.Anchor-FVector2D(3,3),FVector2D(6,6),Accent.CopyWithNewOpacity(L.Opacity),3);
    }
    if(IsInteriorAvailable()) for(const int32 Index:VisibleLabels)
    {
        const FLabel& L=Labels[Index];
        auto Fade=[&](FLinearColor Color){Color.A*=L.Opacity;return Color;};
        const FLinearColor Accent=L.Accent;
        const FLinearColor Blue=C(TEXT("356BFA"));
        Box(L.Position+FVector2D(0,3),L.Size,Fade(FLinearColor(.08,.15,.25,.055)),FGHSTwinSceneChrome::CornerRadius);
        Box(L.Position,L.Size,Fade(L.bSelected?Blue:FLinearColor::White),FGHSTwinSceneChrome::CornerRadius,Fade(L.bSelected || L.bHovered?Blue:C(TEXT("DFE7F2"))),L.bHovered?1.5f:1.f);
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
        Text(L.Position+FVector2D(40,L.TitleMetrics.CenteredOriginY(L.Size.Y)),L.DisplayTitle,14,Fade(L.bSelected?FLinearColor::White:C(TEXT("25364B"))));
        if(!L.bRegion)
        {
            const FVector2D BadgeAt=L.Position+FVector2D(L.Size.X-L.BadgeWidth-12,(L.Size.Y-24)*.5);
            Box(BadgeAt,FVector2D(L.BadgeWidth,24),Fade(C(TEXT("F0F4F9"))),3);
            Text(BadgeAt+FVector2D((L.BadgeWidth-L.StateMetrics.Size.X)*.5,L.StateMetrics.CenteredOriginY(24)),L.State,12,Fade(Accent));
        }
    }
    // Scene guidance stays below menus so a short viewport never obscures results.
    if(Layout.SceneSize.X>650)
    {
        const auto* Replay=ReplaySession();const bool bFollowing=Replay && Replay->IsReplaying() && !Replay->GetFollowId().IsEmpty();
        const FString Hint=IsReplayActive()?(bFollowing?TEXT("跟随中  ·  左键旋转  ·  滚轮缩放  ·  右键平移无效"):TEXT("左键旋转  ·  右键平移  ·  滚轮缩放  ·  点击选择回放设备")):(IsInteriorAvailable()?TEXT("左键旋转  ·  右键平移  ·  滚轮缩放  ·  中键返回园区  ·  点击查看详情"):TEXT("左键旋转  ·  右键平移  ·  滚轮缩放  ·  点击仓库查看内部"));
        const auto Metrics=GHSTwinTypography::Measure(Hint,Font(11));
        const FVector2D At(22,Layout.ScenePosition.Y+Layout.SceneSize.Y-44);
        Box(At,FVector2D(Metrics.Size.X+28,32),FLinearColor::White.CopyWithNewOpacity(.94f),8,C(TEXT("DFE7F2")));
        Text(At+FVector2D(14,Metrics.CenteredOriginY(32)),Hint,11,C(TEXT("536478")));
    }
    if(WarehouseMenuProgress>0)
    {
        DrawOpacity=WarehouseMenuProgress*WarehouseMenuProgress*(3-2*WarehouseMenuProgress);
        const FVector2D At(24,Layout.HeaderHeight+110-8*(1-DrawOpacity));
        Box(At,FVector2D(320,176),FLinearColor::White,12,C(TEXT("DFE7F2")));
        Text(At+FVector2D(16,14),TEXT("切换仓库"),11,C(TEXT("5B6C82")));
        Box(At+FVector2D(16,46),FVector2D(288,48),C(TEXT("EDF3FF")),12);
        Text(At+FVector2D(32,60),TEXT("GHS · 当前仓库"),14,C(TEXT("356BFA")));
        Text(At+FVector2D(16,116),TEXT("暂无其他仓库"),11,C(TEXT("5B6C82")));
        Text(At+FVector2D(16,142),TEXT("接入后会显示在这里"),11,C(TEXT("5B6C82")));
    }
    if(SearchMenuProgress>0 && !bSearchIsRemote && IsSceneSearchVisible())
    {
        DrawOpacity=SearchMenuProgress*SearchMenuProgress*(3-2*SearchMenuProgress);
        const auto Drop=SearchLayout();const FVector2D At=Drop.Position-FVector2D(0,8*(1-DrawOpacity));
        Box(At,Drop.Size,FLinearColor::White,12,C(TEXT("DFE7F2")));
        Text(At+FVector2D(16,10),FString::Printf(TEXT("GHS · 匹配结果（%d）"),SearchTotal),11,C(TEXT("5B6C82")));
        for(int32 I=0;I<Drop.VisibleRows;++I)
        {
            const int32 Index=SearchFirstVisible+I;if(!SearchResults.IsValidIndex(Index)) break;
            const auto& R=SearchResults[Index];const FVector2D RowAt=At+FVector2D(8,Drop.HeaderHeight+I*Drop.RowHeight);
            if(Index==SearchIndex) Box(RowAt,FVector2D(Drop.Size.X-16,Drop.RowHeight-4),C(TEXT("EDF3FF")),12);
            Text(RowAt+FVector2D(12,6),R.Title.Left(14),13,C(TEXT("25364B")));
            Text(RowAt+FVector2D(12,33),(R.Type+TEXT(" · ")+R.Location).Left(24),10,C(TEXT("5B6C82")));
            Text(RowAt+FVector2D(Drop.Size.X-86,7),R.Status,11,C(TEXT("356BFA")));
        }
        if(SearchResults.IsEmpty()) Text(At+FVector2D(16,52),SearchQuery.TrimStartAndEnd().IsEmpty()?TEXT("输入设备名称、类型、编号或物料"):TEXT("GHS 中未找到匹配设备或物料"),12,C(TEXT("5B6C82")));
        Text(At+FVector2D(16,Drop.Size.Y-27),FString::Printf(TEXT("↑ ↓ / 滚轮   %d / %d   Enter 定位   Esc 收起"),SearchIndex==INDEX_NONE?0:SearchOffset+SearchIndex+1,SearchTotal),10,C(TEXT("5B6C82")));
    }
    DrawOpacity=1;
    return Layer;
}
