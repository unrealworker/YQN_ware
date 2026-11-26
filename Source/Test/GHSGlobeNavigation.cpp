#include "GHSGlobeNavigation.h"
#include "GHSGlobeWarehouseMarkers.h"
#include "GHSGlobeCountryLabels.h"
#include "SGHSGlobeWarehouseOverlay.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehouseRoofComponent.h"
#include "GHSStorageCapacityComponent.h"
#include "GHSTwinHUDWidget.h"
#include "GHSTwinViewport.h"
#include "Blueprint/WidgetTree.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Camera/CameraComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/LevelStreamingDynamic.h"
#include "Engine/Level.h"
#include "Engine/PostProcessVolume.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HAL/PlatformMisc.h"
#include "HAL/FileManager.h"
#include "HighResScreenshot.h"
#include "UnrealClient.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/UnrealType.h"
#include "Widgets/Layout/SDPIScaler.h"
#include "Widgets/SWindow.h"
#include "GenericPlatform/GenericWindow.h"
#include "InputKeyEventArgs.h"
#include "SceneView.h"

namespace
{
FString Encode(const TSharedRef<FJsonObject>& Object)
{ FString Result;FJsonSerializer::Serialize(Object,TJsonWriterFactory<>::Create(&Result));return Result; }
float Ease(float T) {T=FMath::Clamp(T,0.f,1.f);return T*T*T*(10.f+T*(-15.f+6.f*T));}
bool Number(const TSharedPtr<FJsonObject>& Object,const TCHAR* Key,double& Value)
{return Object->TryGetNumberField(Key,Value) && FMath::IsFinite(Value);}
}

TSharedRef<SWidget> UGHSGlobeHUD::RebuildWidget()
{
    if(!WidgetTree)WidgetTree=NewObject<UWidgetTree>(this,TEXT("GlobeTree"));
    auto* Canvas=WidgetTree->ConstructWidget<UCanvasPanel>();Canvas->SetVisibility(ESlateVisibility::SelfHitTestInvisible);WidgetTree->RootWidget=Canvas;
    const auto* PortalController=Cast<AGHSGlobePlayerController>(GetOwningPlayer());
    Browser=WidgetTree->ConstructWidget<UGHSTwinBrowser>();Browser->Document=PortalController&&PortalController->bPortalEntry?TEXT("entry.html"):TEXT("globe.html");Browser->bTransparent=true;
    BrowserSlot=Canvas->AddChildToCanvas(Browser);BrowserSlot->SetPosition(FVector2D::ZeroVector);BrowserSlot->SetSize(FVector2D(1920,1080));
    return Super::RebuildWidget();
}
void UGHSGlobeHUD::NativeConstruct()
{Super::NativeConstruct();SetVisibility(ESlateVisibility::SelfHitTestInvisible);if(Browser)Browser->Bind(GetOwningPlayer());}
void UGHSGlobeHUD::NativeTick(const FGeometry& Geometry,float Dt)
{
    Super::NativeTick(Geometry,Dt);
    const FVector2D Size=Geometry.GetLocalSize();if(Size.X>0&&Size.Y>0)FullSize=Size;
    LayoutScale=Geometry.GetAccumulatedLayoutTransform().GetScale();WindowDpi=1.f;
    if(GetWorld()&&GetWorld()->GetGameViewport())
    {
        const auto Window=GetWorld()->GetGameViewport()->GetWindow();
        if(Window.IsValid()&&Window->GetNativeWindow().IsValid())WindowDpi=Window->GetNativeWindow()->GetDPIScaleFactor();
    }
    FullBrowserCssSize=FGHSGlobeBrowserGeometry::ToCssSize(FullSize,LayoutScale,WindowDpi);
    bFullBrowserCoverage=false;
    if(Browser)
    {
        // Check allocated geometry, not the requested Canvas slot: the old compact
        // surface can remain cached for a layout frame after a return is requested.
        const auto& BrowserGeometry=Browser->GetCachedGeometry();
        const FVector2D Origin=Geometry.AbsoluteToLocal(BrowserGeometry.LocalToAbsolute(FVector2D::ZeroVector));
        const FVector2D End=Geometry.AbsoluteToLocal(BrowserGeometry.LocalToAbsolute(BrowserGeometry.GetLocalSize()));
        const FVector2D BrowserCss=FGHSGlobeBrowserGeometry::ToCssSize(BrowserGeometry.GetLocalSize(),BrowserGeometry.GetAccumulatedLayoutTransform().GetScale(),WindowDpi);
        bFullBrowserCoverage=FGHSGlobeBrowserGeometry::CoversFullLayout(FullSize,Origin,End,bSmall)&&BrowserCss.Equals(FullBrowserCssSize,1.);
    }
    if(BrowserSlot){BrowserSlot->SetPosition(bSmall?FVector2D(24,FMath::Max(70.,FullSize.Y-108.)):FVector2D::ZeroVector);BrowserSlot->SetSize(bSmall?FVector2D(200,44):FullSize);}
}
void UGHSGlobeHUD::Push(const FString& Json)
{if(Browser)Browser->Evaluate(TEXT("window.ghsGlobe&&window.ghsGlobe.receive(")+Json+TEXT(");"));}
void UGHSGlobeHUD::SetCompact(bool Value){bSmall=Value;}
void UGHSGlobeHUD::ShowWarehouseCluster(const TArray<FString>& Ids)
{
    auto Payload=MakeShared<FJsonObject>();TArray<TSharedPtr<FJsonValue>> Values;
    for(const auto& Id:Ids)Values.Add(MakeShared<FJsonValueString>(Id));
    Payload->SetArrayField(TEXT("ids"),Values);
    if(Browser)Browser->Evaluate(TEXT("window.ghsGlobe&&window.ghsGlobe.showCluster(")+Encode(Payload)+TEXT(");"));
}

AGHSGlobeGameMode::AGHSGlobeGameMode(){PlayerControllerClass=AGHSGlobePlayerController::StaticClass();}
AGHSGlobePlayerController::AGHSGlobePlayerController()
{
    bPortalEntry=!FParse::Param(FCommandLine::Get(),TEXT("LegacyGlobe"));
    // Destination-specific actors are discovered only by the selected experience adapter.
    if(WarehouseRoof)WarehouseRoof->bDeferWorldInitialization=true;
    if(StorageCapacity)StorageCapacity->bDeferWorldInitialization=true;
}
void AGHSGlobePlayerController::OnPossess(APawn* PawnToPossess)
{
    // A warehouse opened on its own uses its placed Player0 camera. As a streamed
    // destination that same auto-possession request must not replace the globe's
    // persistent camera: the placed pawn is destroyed when the destination unloads.
    if(PawnToPossess&&GetWorld()&&PawnToPossess->GetLevel()!=GetWorld()->PersistentLevel)
    {
        UE_LOG(LogTemp,Display,TEXT("GHS_GLOBE_REJECT_STREAMED_CAMERA pawn=%s level=%s persistent=%s"),
            *GetNameSafe(PawnToPossess),*GetNameSafe(PawnToPossess->GetLevel()),*GetNameSafe(GetPawn()));
        return;
    }
    Super::OnPossess(PawnToPossess);
    PersistentCamera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
}

void AGHSGlobePlayerController::BeginPlay()
{
    Super::BeginPlay();if(!IsLocalController())return;
    FString Catalog;
    if(!FFileHelper::LoadFileToString(Catalog,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/warehouses.json")))||!Registry.Load(Catalog,Error))
    {Phase=EPhase::Error;if(Error.IsEmpty())Error=TEXT("无法读取仓库目录");}
    for(TActorIterator<AActor> It(GetWorld());It;++It)
    {
        if(It->ActorHasTag(TEXT("GHS_GlobeStage")))
        {
            const auto* Volume=Cast<APostProcessVolume>(*It);
            StageActors.Add({*It,It->IsHidden(),It->IsActorTickEnabled(),Volume&&Volume->bEnabled});
        }
        if(It->ActorHasTag(TEXT("GHS_GlobeRoot"))){GlobeRoot=*It;GlobeCenter=It->GetActorLocation();InitialGlobeRotation=It->GetActorQuat();}
    }
    // The persistent world remains the streaming host, but the SaaS entry has no
    // visible globe, globe lights, post processing, or annotation allocation.
    if(bPortalEntry)for(const auto& Entry:StageActors)if(auto* Actor=Entry.Actor.Get())
    {
        Actor->SetActorHiddenInGame(true);Actor->SetActorTickEnabled(false);
        if(auto* Volume=Cast<APostProcessVolume>(Actor))Volume->bEnabled=false;
    }
    if(!bPortalEntry&&GlobeRoot.IsValid())
    {
        FActorSpawnParameters Params;
        Params.Owner=this;Params.OverrideLevel=GetWorld()->PersistentLevel;
        Params.ObjectFlags|=RF_Transient;
        WarehouseMarkers=GetWorld()->SpawnActor<AGHSGlobeWarehouseMarkers>(Params);
        if(WarehouseMarkers)
        {
            WarehouseMarkers->Initialize(GlobeRoot.Get(),GlobeRadius,Registry.GetEntries());
            StageActors.Add({WarehouseMarkers,false,false,false});
        }
        CountryLabels=GetWorld()->SpawnActor<AGHSGlobeCountryLabels>(Params);
        if(CountryLabels)
        {
            CountryLabels->Initialize(GlobeRoot.Get(),GlobeRadius);
            StageActors.Add({CountryLabels,false,false,false});
        }
    }
    GlobeHUD=CreateWidget<UGHSGlobeHUD>(this);
    if(GlobeHUD&&GetWorld()->GetGameViewport())
    {
        GlobeViewportWidget=SNew(SDPIScaler).DPIScale_Lambda([this]()
        {
            FVector2D Pixels(1920,1080);if(GetWorld()&&GetWorld()->GetGameViewport())GetWorld()->GetGameViewport()->GetViewportSize(Pixels);
            return float(FGHSTwinViewport::FromPixels(Pixels).SlateScale(UWidgetLayoutLibrary::GetViewportScale(this)));
        })[GlobeHUD->TakeWidget()];
        GetWorld()->GetGameViewport()->AddViewportWidgetContent(GlobeViewportWidget.ToSharedRef(),50);
        if(!bPortalEntry)
        {
            auto MarkerCommand=[this](const TCHAR* Action,const FString& Id,const FString& Source)
            {auto Message=MakeShared<FJsonObject>();Message->SetStringField(TEXT("action"),Action);Message->SetStringField(TEXT("id"),Id);Message->SetStringField(TEXT("inputSource"),Source);Command(Encode(Message));};
            SAssignNew(WarehouseOverlay,SGHSGlobeWarehouseOverlay)
                .OnSelect_Lambda([this,MarkerCommand](const FString& Id,const FString& Source){MarkerCommand(SelectedId==Id?TEXT("enter"):TEXT("select"),Id,Source);})
                .OnEnter_Lambda([MarkerCommand](const FString& Id,const FString& Source){MarkerCommand(TEXT("enter"),Id,Source);})
                .OnCluster_Lambda([this](const TArray<FString>& Ids){Command(TEXT("{\"action\":\"clear\"}"));if(GlobeHUD)GlobeHUD->ShowWarehouseCluster(Ids);});
            GetWorld()->GetGameViewport()->AddViewportWidgetContent(WarehouseOverlay.ToSharedRef(),51);
        }
    }
    ResetGlobeCamera(true);
#if !UE_BUILD_SHIPPING
    // Opt-in standalone validation can never close a user's editor/PIE process.
    const bool StandaloneValidation=FParse::Param(FCommandLine::Get(),TEXT("game"))&&GetWorld()->WorldType==EWorldType::Game;
    bSmokeTest=!bPortalEntry&&FParse::Param(FCommandLine::Get(),TEXT("GlobeSmokeTest"))&&StandaloneValidation;
    bPortalSmokeTest=bPortalEntry&&FParse::Param(FCommandLine::Get(),TEXT("PortalSmokeTest"))&&StandaloneValidation;
    SmokeStarted=SmokeStepStarted=FPlatformTime::Seconds();
#endif
    UE_LOG(LogTemp,Display,TEXT("GHS_GLOBE_READY warehouses=%d"),Registry.GetEntries().Num());
}
void AGHSGlobePlayerController::EndPlay(const EEndPlayReason::Type Reason)
{
    Curtain.Cancel();
    if(Experience){Experience->Exit(*this);Experience.Reset();}
    // Controller replacement within a live world must not orphan its streamed destination.
    if(GetWorld()&&(Reason==EEndPlayReason::Destroyed||Reason==EEndPlayReason::RemovedFromWorld))
    {SetStageVisible(true);UnloadDestination();}
    if(WarehouseMarkers){WarehouseMarkers->Destroy();WarehouseMarkers=nullptr;}
    if(CountryLabels){CountryLabels->Destroy();CountryLabels=nullptr;}
    if(WarehouseOverlay&&GetWorld()&&GetWorld()->GetGameViewport())GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(WarehouseOverlay.ToSharedRef());
    WarehouseOverlay.Reset();
    if(GlobeViewportWidget&&GetWorld()&&GetWorld()->GetGameViewport())GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(GlobeViewportWidget.ToSharedRef());
    GlobeViewportWidget.Reset();GlobeHUD=nullptr;Super::EndPlay(Reason);
}
bool AGHSGlobePlayerController::InputKey(const FInputKeyEventArgs& Params)
{
    if(Phase==EPhase::Warehouse)return Super::InputKey(Params);
    // Full-screen CEF owns globe gestures; it forwards only validated scene deltas.
    return APlayerController::InputKey(Params);
}
void AGHSGlobePlayerController::ResetGlobeCamera(bool Immediate)
{
    if(bPortalEntry)
    {
        // A fully opaque page owns entry composition. Do not send the camera
        // back through the earth when returning from either warehouse.
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn()))Camera->FreezeCurrentPose();
        return;
    }
    if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn()))
    {
        Camera->WarehouseCamera->FieldOfView=20.f;
        Camera->SetObjectOrbitNavigationEnabled(true);
        Camera->MinimumPitch=-80;Camera->MaximumPitch=80;Camera->MinimumZoom=GlobeRadius*2.5f;Camera->MaximumZoom=GlobeRadius*20;
        Camera->MinimumCameraHeight=0;
        // Perspective tangent sphere fit: silhouette radius is f*R/sqrt(d*d-R*R).
        // Match the reference's breathing room without clipping at narrow aspect ratios.
        const double Focal=Viewport.X/(2*FMath::Tan(FMath::DegreesToRadians(Camera->WarehouseCamera->FieldOfView*.5)));
        const double ScreenRadius=FMath::Max(1.,FMath::Min(SceneSize.X*.43,SceneSize.Y*.445));
        const float Distance=GlobeRadius*float(FMath::Sqrt(1+FMath::Square(Focal/ScreenRadius)));
        Camera->FocusOnTarget(GlobeCenter,Distance,FRotator(-32,-96,0),Viewport,ScenePosition+FVector2D(SceneSize.X*.53,SceneSize.Y*.48),Immediate?0:.85f);
    }
}
const FGHSGlobeWarehouse* AGHSGlobePlayerController::Selected()const
{return Registry.Find(SelectedId);}
FVector AGHSGlobePlayerController::Position(double Lat,double Lon)const
{
    const FVector Offset=GHSGlobe::ToSphere(Lat,Lon,GlobeRadius*1.003);
    return GlobeCenter+(GlobeRoot.IsValid()?GlobeRoot->GetActorQuat().RotateVector(Offset):Offset);
}
void AGHSGlobePlayerController::Fail(const FString& Message)
{
    Error=Message;bEntryRequested=false;bPreloadRequested=false;
    UE_LOG(LogTemp,Warning,TEXT("GHS_GLOBE_ERROR %s"),*Message);
    if(!bStageVisible)
    {
        // An adapter failure is recovered behind the same full-screen curtain as a normal return.
        // Do not expose a still-visible destination or fly the camera across worlds on an error.
        Phase=EPhase::Returning;PhaseTime=bReducedMotion?.18f:.4f;MaskOpacity=1;
        bReturningApplied=false;bReturningCommitted=false;
        if(GlobeHUD)GlobeHUD->SetCompact(false);
        BeginCurtain();PushState();return;
    }
    if(Experience){Experience->Exit(*this);Experience.Reset();}
    Curtain.Cancel();UnloadDestination();Phase=EPhase::Error;MaskOpacity=0;
    if(GlobeHUD)GlobeHUD->SetCompact(false);ResetGlobeCamera(true);PushState();
}
void AGHSGlobePlayerController::PreloadSelected()
{
    const auto* W=Selected();if(!W)return;
    if(Destination&&LoadedId==W->Id&&!bUnloadRequested)return;
    if(Destination){UnloadDestination();return;}
    if(!FGHSWarehouseStreamPolicy::CanStart(Destination!=nullptr,bUnloadRequested))return;
    Error.Empty();
    bool Success=false;ULevelStreamingDynamic::FLoadLevelInstanceParams Params(GetWorld(),W->Map,FTransform::Identity);
    Params.bInitiallyVisible=false;
    Destination=ULevelStreamingDynamic::LoadLevelInstance(Params,Success);
    if(!Success||!Destination){Fail(TEXT("仓库场景不可用，请检查地图是否已打包"));return;}
    LoadedId=W->Id;LoadStarted=GetWorld()->GetTimeSeconds();
    UE_LOG(LogTemp,Display,TEXT("GHS_GLOBE_PRELOAD id=%s map=%s"),*W->Id,*W->Map);
}
void AGHSGlobePlayerController::UnloadDestination()
{
    if(!Destination||bUnloadRequested)return;
    bUnloadRequested=true;bUnloadTimedOut=false;Destination->SetShouldBeVisible(false);Destination->SetShouldBeLoaded(false);Destination->SetIsRequestingUnloadAndRemoval(true);
    LoadStarted=GetWorld()->GetTimeSeconds();
}
void AGHSGlobePlayerController::PollDestination()
{
    if(bUnloadRequested&&Destination&&FGHSWarehouseStreamPolicy::FinishedUnloading(Destination->IsLevelLoaded(),GetWorld()->GetStreamingLevels().Contains(Destination)))
    {Destination=nullptr;LoadedId.Empty();bUnloadRequested=false;bUnloadTimedOut=false;}
    if(bUnloadRequested&&!bUnloadTimedOut&&GetWorld()->GetTimeSeconds()-LoadStarted>120)
    {
        // Keep ownership: a stuck unload must never permit overlapping destination activation.
        bUnloadTimedOut=true;bPreloadRequested=false;bEntryRequested=false;Error=TEXT("上一仓库仍在释放资源，可重新选择仓库等待重试");
        if(Phase!=EPhase::Returning)Phase=EPhase::Error;
    }
    if(bUnloadTimedOut&&Phase==EPhase::Returning&&bReturningCommitted&&!bReturningApplied&&Destination)
    {
        const auto* Level=Destination->GetLoadedLevel();
        const bool Safe=FGHSWarehouseStreamPolicy::CanRevealGlobe(Destination->IsLevelVisible(),
            Level&&(Level->bIsBeingRemoved||Level->bIsDisassociatingLevel),Level&&GetWorld()->GetLevels().Contains(Level));
        if(Safe)
        {
            // Rendering is detached; retain the allocation slot until full unload/removal finishes.
            Error=TEXT("上一仓库仍在释放资源，可重新选择仓库等待重试");
            SetStageVisible(true);ResetGlobeCamera(true);bReturningApplied=true;PhaseTime=0;
        }
        else Error=TEXT("上一仓库尚未完成隐藏，正在等待引擎释放，请稍候");
    }
    if(bPreloadRequested&&!Destination&&!bUnloadRequested)PreloadSelected();
}
void AGHSGlobePlayerController::StartFlight()
{
    const auto* W=Selected();if(!W)return;Phase=EPhase::Flying;PhaseTime=0;MaskOpacity=0;bArrivalStarted=false;bResettingGlobe=false;
    bAnnotationSceneTransition=true;
    if(WarehouseOverlay)WarehouseOverlay->SetPresentation(false,false,bReducedMotion,AnnotationInputSource==TEXT("keyboard"));
    BeginCurtain();
    if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn()))
    {
        Camera->FreezeCurrentPose();
        if(!bPortalEntry)Flight.Begin(Camera->CaptureReplayPose(),GlobeCenter,GlobeRadius,Position(W->Latitude,W->Longitude));
    }
    PushState();
}
float AGHSGlobePlayerController::EntryTransitionDuration()const
{return bPortalEntry?(bReducedMotion?.12f:.3f):(bReducedMotion?.22f:FGHSGlobeFlight::Duration);}
void AGHSGlobePlayerController::BeginCurtain()
{
    Curtain.Begin(GlobeHUD?GlobeHUD->GetFullBrowserCssSize():Viewport,GetWorld()->GetTimeSeconds());
    UE_LOG(LogTemp,Display,TEXT("GHS_GLOBE_CURTAIN_BEGIN generation=%u layout=%s scale=%.4f dpi=%.4f expectedCSS=%s reportedCSS=%s"),
        Curtain.GetGeneration(),* (GlobeHUD?GlobeHUD->GetFullSize():Viewport).ToString(),GlobeHUD?GlobeHUD->GetLayoutScale():1.f,
        GlobeHUD?GlobeHUD->GetWindowDpi():1.f,*Curtain.GetExpectedSize().ToString(),*Viewport.ToString());
}
bool AGHSGlobePlayerController::AwaitCurtain()
{
    const FVector2D FullSize=GlobeHUD?GlobeHUD->GetFullBrowserCssSize():Viewport;
    if(!Curtain.Active()||!FullSize.Equals(Curtain.GetExpectedSize(),1.)){BeginCurtain();PushState();}
    if(Curtain.Ready(GFrameCounter,GlobeHUD&&GlobeHUD->HasFullBrowserCoverage()))return true;
    if(Curtain.Expired(GetWorld()->GetTimeSeconds()))
    {
        UE_LOG(LogTemp,Warning,TEXT("GHS_GLOBE_CURTAIN_TIMEOUT generation=%u expectedCSS=%s reportedCSS=%s fullCoverage=%d"),
            Curtain.GetGeneration(),*Curtain.GetExpectedSize().ToString(),*Viewport.ToString(),GlobeHUD&&GlobeHUD->HasFullBrowserCoverage());
        if(Phase==EPhase::Returning)
        {
            // Nothing has been disposed yet. Keep the current warehouse usable and allow retry.
            Error=TEXT("全屏过渡遮罩未就绪，返回已取消，请重试");
            Curtain.Cancel();Phase=EPhase::Warehouse;MaskOpacity=0;
            if(GlobeHUD)GlobeHUD->SetCompact(true);PushState();
        }
        else Fail(TEXT("全屏过渡遮罩未就绪，进入已取消，请重试"));
    }
    return false;
}
void AGHSGlobePlayerController::SetStageVisible(bool Visible)
{
    if(bStageVisible==Visible)return;
    bStageVisible=Visible;
    if(!Visible&&WarehouseOverlay)
    {WarehouseOverlay->SetPresentation(false,false,bReducedMotion,true);WarehouseOverlay->SetMarkers({});}
    for(auto& Entry:StageActors)if(auto* Actor=Entry.Actor.Get())
    {
        auto* Volume=Cast<APostProcessVolume>(Actor);
        if(!Visible)
        {Entry.bHidden=Actor->IsHidden();Entry.bTickEnabled=Actor->IsActorTickEnabled();Entry.bPostProcessEnabled=Volume&&Volume->bEnabled;}
        Actor->SetActorHiddenInGame(bPortalEntry||!Visible||Entry.bHidden);Actor->SetActorTickEnabled(!bPortalEntry&&Visible&&Entry.bTickEnabled);
        if(Volume)Volume->bEnabled=!bPortalEntry&&Visible&&Entry.bPostProcessEnabled;
    }
}
void AGHSGlobePlayerController::Command(const FString& Json)
{
    if(Json.Len()>8192)return;TSharedPtr<FJsonObject> O;FString Action;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),O)||!O||!O->TryGetStringField(TEXT("action"),Action))return;
    FString InputSource;O->TryGetStringField(TEXT("inputSource"),InputSource);
    if(InputSource!=TEXT("pointer")&&InputSource!=TEXT("keyboard"))InputSource=TEXT("unknown");
    if(Action==TEXT("ready")){bReady=true;PushState(true);return;}
#if !UE_BUILD_SHIPPING
    if(Action==TEXT("portalSmokePage")&&bPortalSmokeTest)
    {FString Page;O->TryGetStringField(TEXT("page"),Page);bPortalSmokeLogin=Page==TEXT("warehouses");return;}
#endif
    if(Action==TEXT("reducedMotion")){O->TryGetBoolField(TEXT("enabled"),bReducedMotion);return;}
    if(Action==TEXT("curtainReady"))
    {
        double Generation,W,H;
        if((Phase==EPhase::Flying||(Phase==EPhase::Returning&&!bReturningCommitted))
            &&Number(O,TEXT("generation"),Generation)&&Generation>=1&&Generation<=MAX_uint32&&Generation==FMath::FloorToDouble(Generation)
            &&Number(O,TEXT("width"),W)&&Number(O,TEXT("height"),H))
        {
            if(Curtain.Accept(uint32(Generation),FVector2D(W,H),MaskOpacity,GFrameCounter)&&LastLoggedCurtainAck!=Curtain.GetGeneration())
            {
                LastLoggedCurtainAck=Curtain.GetGeneration();
                UE_LOG(LogTemp,Display,TEXT("GHS_GLOBE_CURTAIN_ACK generation=%u expectedCSS=%s receivedCSS=%.0fx%.0f fullCoverage=%d"),
                    LastLoggedCurtainAck,*Curtain.GetExpectedSize().ToString(),W,H,GlobeHUD&&GlobeHUD->HasFullBrowserCoverage());
            }
        }
        return;
    }
    if(Action==TEXT("viewport"))
    {
        double W,H,X,Y,SW,SH;
        if(Number(O,TEXT("width"),W)&&Number(O,TEXT("height"),H)&&Number(O,TEXT("sceneX"),X)&&Number(O,TEXT("sceneY"),Y)&&Number(O,TEXT("sceneWidth"),SW)&&Number(O,TEXT("sceneHeight"),SH)
            &&W>0&&H>0&&W<20000&&H<20000&&SW>0&&SH>0&&X>=0&&Y>=0&&X+SW<=W+1&&Y+SH<=H+1)
        {
            const bool Changed=!Viewport.Equals(FVector2D(W,H),1)||!SceneSize.Equals(FVector2D(SW,SH),1);
            Viewport=FVector2D(W,H);ScenePosition=FVector2D(X,Y);SceneSize=FVector2D(SW,SH);
            if(Changed&&(Phase==EPhase::Idle||Phase==EPhase::Selected||Phase==EPhase::Error))ResetGlobeCamera(true);
        }return;
    }
    if(Action==TEXT("back")&&Phase==EPhase::Warehouse)
    {AnnotationInputSource=InputSource;bAnnotationSceneTransition=true;if(WarehouseOverlay)WarehouseOverlay->SetPresentation(false,false,bReducedMotion,true);Phase=EPhase::Returning;PhaseTime=0;MaskOpacity=0;bReturningApplied=false;bReturningCommitted=false;bPreloadRequested=false;Error.Empty();if(GlobeHUD)GlobeHUD->SetCompact(false);CancelCameraDrag();BeginCurtain();PushState();return;}
    if(Phase==EPhase::Warehouse||Phase==EPhase::Flying||Phase==EPhase::Revealing||Phase==EPhase::Returning)return;
    if(bPortalEntry&&Action==TEXT("cancel"))
    {
        SelectedId.Empty();Phase=EPhase::Idle;bEntryRequested=false;bPreloadRequested=false;
        Curtain.Cancel();MaskOpacity=0;UnloadDestination();Error.Empty();PushState();return;
    }
    // Legacy CEF hover/focus/drag notifications no longer gate globe rotation.
    if(Action==TEXT("interaction"))return;
    if(Action==TEXT("select")||Action==TEXT("enter"))
    {
        // The page may only resolve stable catalog IDs, never arbitrary map URLs.
        // A loading request owns the slot until cancel or completion.
        if(bPortalEntry&&Phase==EPhase::Loading)return;
        FString Id;if(!O->TryGetStringField(TEXT("id"),Id)||!Registry.Find(Id))
        {if(bPortalEntry)Fail(TEXT("未找到所选仓库，请重新选择"));return;}
        SelectedId=Id;SelectionInputSource=InputSource;
        if(Action==TEXT("enter"))AnnotationInputSource=InputSource;
        Error.Empty();Phase=EPhase::Selected;bPreloadRequested=true;PreloadSelected();
        if(Action==TEXT("enter")&&Phase!=EPhase::Error){bEntryRequested=true;Phase=EPhase::Loading;if(Destination&&!bUnloadRequested&&LoadedId==SelectedId&&Destination->IsLevelLoaded())StartFlight();}
        if(bUnloadTimedOut)Error=TEXT("上一仓库仍在释放资源，释放完成后会自动继续，请稍候");
        PushState();return;
    }
    if(Action==TEXT("clear")){SelectedId.Empty();Phase=EPhase::Idle;bEntryRequested=false;bPreloadRequested=false;UnloadDestination();Error.Empty();PushState();return;}
    if(Action==TEXT("home")||Action==TEXT("reset"))
    {
        bEntryRequested=false;Phase=SelectedId.IsEmpty()?EPhase::Idle:EPhase::Selected;Error.Empty();
        if(!bPortalEntry&&GlobeRoot.IsValid())
        {
            ResetStartRotation=GlobeRoot->GetActorQuat();GlobeResetTime=0;bResettingGlobe=!bReducedMotion;
            if(bReducedMotion)GlobeRoot->SetActorRotation(InitialGlobeRotation);
        }
        ResetGlobeCamera(bReducedMotion);PushState();return;
    }
    if(Phase==EPhase::Loading)return;
    if(Action==TEXT("fullscreen"))
    {
        // Only a real standalone game window may change display mode. PIE shares
        // editor UI, while Pixel Streaming browser fullscreen belongs to its outer player.
        auto* World=GetWorld();auto* Client=World?World->GetGameViewport():nullptr;
        if(!IsLocalController()||!World||World->WorldType!=EWorldType::Game||!Client||Client->bIsPlayInEditorViewport
            ||!Client->Viewport||FParse::Param(FCommandLine::Get(),TEXT("RenderOffscreen")))return;
        const TSharedPtr<SWindow> Window=Client->GetWindow();
        if(!Window.IsValid()||!Window->GetNativeWindow().IsValid()||!Window->IsVisible())return;
        CancelCameraDrag();Client->HandleToggleFullscreenCommand();return;
    }
    if(!bPortalEntry)if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn()))
    {
        double DX,DY,Steps;
        if(Action==TEXT("orbit")||Action==TEXT("zoom"))bResettingGlobe=false;
        if(Action==TEXT("orbit")&&Number(O,TEXT("dx"),DX)&&Number(O,TEXT("dy"),DY))Camera->OrbitPixels(FVector2D(FMath::Clamp(DX,-500.,500.),FMath::Clamp(DY,-500.,500.)));
        if(Action==TEXT("zoom")&&Number(O,TEXT("steps"),Steps))Camera->ZoomSteps(float(FMath::Clamp(Steps,-5.,5.)));
    }
}

void AGHSGlobePlayerController::PlayerTick(float Dt)
{
    Super::PlayerTick(Dt);if(!IsLocalController()||!FMath::IsFinite(Dt)||Dt<=0)return;
    const double Now=GetWorld()->GetTimeSeconds();PhaseTime+=Dt;
    PollDestination();
    if(Destination&&!bUnloadRequested&&!Destination->IsLevelLoaded()&&Now-LoadStarted>120&&Phase!=EPhase::Warehouse)
        Fail(TEXT("仓库加载超时，可重新选择后重试"));
    if(Phase==EPhase::Loading&&bEntryRequested&&Destination&&!bUnloadRequested&&LoadedId==SelectedId&&Destination->IsLevelLoaded())StartFlight();
    if(bResettingGlobe&&GlobeRoot.IsValid())
    {
        GlobeResetTime+=Dt;GlobeRoot->SetActorRotation(FQuat::Slerp(ResetStartRotation,InitialGlobeRotation,Ease(GlobeResetTime/.85f)));
        if(GlobeResetTime>=.85f)bResettingGlobe=false;
    }
    // Browsing and selection do not interrupt the globe's constant angular speed.
    // Camera flights and explicit home resets retain exclusive pose ownership.
    const bool Browsing=Phase==EPhase::Idle||Phase==EPhase::Selected||Phase==EPhase::Loading||Phase==EPhase::Error;
    if(!bPortalEntry&&Browsing&&bStageVisible&&!bReducedMotion&&!bResettingGlobe&&GlobeRoot.IsValid())
        GlobeRoot->AddActorWorldRotation(FRotator(0,IdleRotationDegreesPerSecond*Dt,0));
    if(Phase==EPhase::Flying)
    {
        const float Duration=EntryTransitionDuration();
        if(!bPortalEntry&&!bReducedMotion)if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn()))Camera->RestoreReplayPose(Flight.Sample(PhaseTime/Duration));
        MaskOpacity=bPortalEntry?Ease(PhaseTime/Duration):Ease((PhaseTime-Duration*.68f)/(Duration*.27f));
        if(PhaseTime>=Duration&&Destination&&AwaitCurtain())
        {
            MaskOpacity=1;Destination->SetShouldBeVisible(true);
            if(Destination->IsLevelVisible())
            {
                SetStageVisible(false);
                const auto* W=Selected();
                Experience=W?IGHSWarehouseExperience::Create(*W):nullptr;
                if(!Experience){Fail(TEXT("仓库运行配置不可用"));return;}
                Experience->Enter(*this,Viewport);Curtain.Cancel();Phase=EPhase::Revealing;PhaseTime=0;bEntryRequested=false;bPreloadRequested=false;LoadStarted=Now;
                UE_LOG(LogTemp,Display,TEXT("GHS_GLOBE_ENTERED %s"),*LoadedId);
            }
            else if(PhaseTime>120){Destination->SetShouldBeVisible(false);Fail(TEXT("仓库初始化超时，请重试"));}
        }
    }
    if(Phase==EPhase::Revealing)
    {
        // Keep the opaque curtain until the original warehouse browser is ready.
        if(!Experience||!Experience->IsReady(*this)){PhaseTime=0;MaskOpacity=1;if(Now-LoadStarted>45)Fail(TEXT("仓库界面未就绪，请重试"));}
        else
        {
            if(!bArrivalStarted){Experience->BeginArrival(*this,bReducedMotion);bArrivalStarted=true;PhaseTime=0;}
            const bool Arrived=Experience->TickArrival(*this,Dt);
            MaskOpacity=1-Ease(PhaseTime/(bReducedMotion?.18f:.55f));
            if(MaskOpacity<=0&&Arrived){Phase=EPhase::Warehouse;if(GlobeHUD)GlobeHUD->SetCompact(true);PushState();}
        }
    }
    if(Phase==EPhase::Returning)
    {
        const float Duration=bReducedMotion?.18f:.4f;
        if(!bReturningApplied)
        {
            MaskOpacity=Ease(PhaseTime/Duration);
            if(PhaseTime>=Duration)
            {
                if(!bReturningCommitted&&AwaitCurtain())
                {
                    bReturningCommitted=true;Curtain.Cancel();
                    if(Experience){Experience->Exit(*this);Experience.Reset();}UnloadDestination();
                }
                if(bReturningCommitted&&!Destination&&!bUnloadRequested)
                {SetStageVisible(true);ResetGlobeCamera(true);bReturningApplied=true;PhaseTime=0;}
            }
        }
        else {MaskOpacity=1-Ease(PhaseTime/Duration);if(MaskOpacity<=0){Phase=!Error.IsEmpty()?EPhase::Error:(SelectedId.IsEmpty()?EPhase::Idle:EPhase::Selected);}}
    }
    if(bSmokeTest)TickSmokeTest();
    if(bPortalSmokeTest)TickPortalSmokeTest();
}

void AGHSGlobePlayerController::UpdateCameraManager(float Dt)
{
    Super::UpdateCameraManager(Dt);
    // The world updates camera caches after Pawn/SpringArm ticks. Project labels
    // here so the same frame's globe transform and rendered view are sampled.
    if(!IsLocalController()||!GetWorld()||!bReady||!FMath::IsFinite(Dt)||Dt<=0)return;
    UpdateGlobeAnnotations(Dt);
    const double Now=GetWorld()->GetTimeSeconds();
    if(Now>=NextPush){NextPush=Now+(Phase==EPhase::Warehouse?.5:1./20.);PushState();}
}

void AGHSGlobePlayerController::UpdateGlobeAnnotations(float DeltaSeconds)
{
    if(!WarehouseOverlay)return;
    const bool Visible=Phase==EPhase::Idle||Phase==EPhase::Selected||Phase==EPhase::Loading||Phase==EPhase::Error;
    if(!bStageVisible||(!Visible&&Phase!=EPhase::Flying))
    {WarehouseOverlay->SetPresentation(false,false,bReducedMotion,true);WarehouseOverlay->SetMarkers({});return;}
    int32 Width=0,Height=0;GetViewportSize(Width,Height);
    auto* Local=GetLocalPlayer();FSceneViewProjectionData Projection;
    if(!WarehouseMarkers||Width<=0||Height<=0||!Local||!Local->ViewportClient||!Local->ViewportClient->Viewport
        ||!Local->GetProjectionData(Local->ViewportClient->Viewport,Projection)||!Projection.IsValidViewRectangle())
    {WarehouseOverlay->SetPresentation(false,false,bReducedMotion,true);WarehouseOverlay->SetMarkers({});return;}
    // Only scene transitions use this clock. The return starts after the CEF
    // curtain has gone, so this overlay (above CEF) cannot leak through it.
    WarehouseOverlay->SetPresentation(Visible,Visible,bReducedMotion,
        !bAnnotationSceneTransition||AnnotationInputSource==TEXT("keyboard"));
    WarehouseOverlay->AdvancePresentation(DeltaSeconds);
    if(Visible&&WarehouseOverlay->GetAnnotationOpacity()>=1.f)bAnnotationSceneTransition=false;
    if(!Visible&&WarehouseOverlay->GetAnnotationOpacity()<=0.f){WarehouseOverlay->SetMarkers({});return;}
    const FVector2D Scale(Width/Viewport.X,Height/Viewport.Y);
    const FSlateRect Scene(ScenePosition.X*Scale.X,ScenePosition.Y*Scale.Y,
        (ScenePosition.X+SceneSize.X)*Scale.X,(ScenePosition.Y+SceneSize.Y)*Scale.Y);
    WarehouseOverlay->SetSceneRect(Scene);
    const FMatrix Matrix=Projection.ComputeViewProjectionMatrix();
    TArray<FGHSWarehouseProjectedPoint> Points;
    for(const auto& W:Registry.GetEntries())
    {
        FVector Anchor;FVector2D Pixels;
        if(!WarehouseMarkers->GetWorldAnchor(W.Id,Anchor)||!GHSGlobe::IsSurfaceVisible(Anchor,Projection.ViewOrigin,GlobeCenter)
            ||!FSceneView::ProjectWorldToScreen(Anchor,Projection.GetConstrainedViewRect(),Matrix,Pixels))continue;
        Pixels-=FVector2D(Projection.GetConstrainedViewRect().Min);
        if(!PostProcessWorldToScreen(Anchor,Pixels,true)||Pixels.X<Scene.Left||Pixels.X>Scene.Right||Pixels.Y<Scene.Top||Pixels.Y>Scene.Bottom)continue;
        Points.Add({W.Id,Pixels});
    }
    TArray<FGHSGlobeScreenMarker> Markers;
    for(const auto& Cluster:GHSClusterWarehousePoints(Points,SelectedId,48))
    {
        FGHSGlobeScreenMarker Marker;Marker.Id=Cluster.Id;Marker.Ids=Cluster.Ids;Marker.PointPixels=Cluster.Position;Marker.bSelected=Cluster.Id==SelectedId;
        if(const auto* Warehouse=Registry.Find(Cluster.Id))Marker.Name=Warehouse->Name;
        Markers.Add(MoveTemp(Marker));
    }
    WarehouseOverlay->SetMarkers(Markers);
}

void AGHSGlobePlayerController::TickSmokeTest()
{
#if !UE_BUILD_SHIPPING
    const double Now=FPlatformTime::Seconds();
    auto Snapshot=[&](const TCHAR* Name)
    {
        const FString Folder=FPaths::ProjectSavedDir()/TEXT("GlobeValidation");IFileManager::Get().MakeDirectory(*Folder,true);
        FFileHelper::SaveStringToFile(GetState(),*(Folder/(FString(Name)+TEXT(".json"))));
        FScreenshotRequest::RequestScreenshot(FPaths::ConvertRelativePathToFull(Folder/(FString(Name)+TEXT(".png"))),true,false);
    };
    auto EnterSelected=[&]()
    {
        if(bReducedMotion!=bSmokeReducedMotion)SmokeError=TEXT("Requested smoke motion mode changed before entry");
        auto Request=MakeShared<FJsonObject>();Request->SetStringField(TEXT("action"),TEXT("enter"));Request->SetStringField(TEXT("id"),SelectedId);Command(Encode(Request));
    };
    auto CheckWarehouse=[&]()
    {
        if(!Destination||!Destination->IsLevelVisible()||!Experience||!Experience->IsReady(*this))
        {SmokeError=TEXT("Destination or selected experience not initialized");return;}
        const auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
        if(!Camera||Camera!=PersistentCamera||Camera->GetLevel()!=GetWorld()->PersistentLevel)
        {SmokeError=TEXT("Warehouse replaced the persistent globe camera");return;}
        if(GetViewTarget()!=PersistentCamera)
        {SmokeError=TEXT("Warehouse replaced the persistent camera view target");return;}
        const float ExpectedFov=GetDefault<AGHSWarehouseCameraPawn>()->WarehouseCamera->FieldOfView;
        if(!Camera||!Camera->WarehouseCamera||!FMath::IsNearlyEqual(Camera->WarehouseCamera->FieldOfView,ExpectedFov,.01f))
            SmokeError=TEXT("Warehouse camera FOV was not restored from its class default");
        else ++SmokeWarehouseFovChecks;
        if(Experience->UsesWarehouseHUD())
        {
            if(!TwinHUDWidget||!WarehouseRoof||!WarehouseRoof->HasRoof()||!WarehouseRoof->IsRoofClosed())
                SmokeError=TEXT("Warehouse HUD or closed roof was not rebuilt on entry");
            const TWeakObjectPtr<UGHSTwinHUDWidget> CurrentHUD(TwinHUDWidget.Get());
            if(SmokeCycles==0)SmokePreviousHUD=CurrentHUD;
            else if(CurrentHUD==SmokePreviousHUD)SmokeError=TEXT("Second warehouse entry reused the disposed HUD");
            else bSmokeHUDRebuilt=true;
        }
        else if(TwinHUDWidget)SmokeError=TEXT("Generic profile unexpectedly created a GHS HUD");
        else if(SmokeCycles>0)bSmokeHUDRebuilt=true;
    };
    auto CheckReturned=[&]()
    {
        if(Destination||bUnloadRequested||TwinHUDWidget||CampusTraffic||Experience||!bStageVisible)
            SmokeError=TEXT("Return did not unload destination and release its HUD/experience/traffic");
        if(bReducedMotion!=bSmokeReducedMotion)SmokeError=TEXT("Requested smoke motion mode changed during transition");
        const auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
        if(!Camera||Camera!=PersistentCamera||Camera->GetLevel()!=GetWorld()->PersistentLevel)
        {SmokeError=TEXT("Return lost the persistent globe camera");return;}
        if(GetViewTarget()!=PersistentCamera)
        {SmokeError=TEXT("Return did not restore the persistent camera view target");return;}
        if(!Camera||!Camera->WarehouseCamera||!FMath::IsNearlyEqual(Camera->WarehouseCamera->FieldOfView,20.f,.01f))
            SmokeError=TEXT("Globe camera FOV was not restored after return");
        else ++SmokeGlobeFovChecks;
        if(WarehouseRoof)
        {
            const auto RoofState=WarehouseRoof->CaptureReplayState();
            if(RoofState.HasRoofVisibility||!RoofState.Roofs.IsEmpty()||!RoofState.Shells.IsEmpty()||RoofState.TickEnabled||!FMath::IsNearlyZero(WarehouseRoof->GetOpenProgress()))
                SmokeError=TEXT("Return retained roof transition or shell state");
            // HasRoof() alone could hide a stale strong reference to a pending-kill actor.
            const auto* MeshProperty=FindFProperty<FObjectPropertyBase>(WarehouseRoof->GetClass(),TEXT("RoofMesh"));
            if(!MeshProperty||MeshProperty->GetObjectPropertyValue_InContainer(WarehouseRoof))
                SmokeError=TEXT("Return retained the strong roof component reference");
            const auto* PartsProperty=FindFProperty<FArrayProperty>(WarehouseRoof->GetClass(),TEXT("RoofParts"));
            if(!PartsProperty)
                SmokeError=TEXT("Roof part lifetime validation property is missing");
            else
            {
                const FScriptArrayHelper Parts(PartsProperty,PartsProperty->ContainerPtrToValuePtr<void>(WarehouseRoof));
                if(Parts.Num()!=0)SmokeError=TEXT("Return retained strong roof actor/component/material references");
            }
        }
        if(SmokeError.IsEmpty())++SmokeCycles;
    };
    auto OpenRoofBeforeReturn=[&]()
    {
        if(bSmokeRoofOpened||Now-SmokeStepStarted<.5)return;
        bSmokeRoofOpened=true;
        if(Experience&&Experience->UsesWarehouseHUD()&&(!WarehouseRoof||!WarehouseRoof->OpenRoof(true)))
            SmokeError=TEXT("Unable to exercise roof state before returning");
    };
    if(Phase==EPhase::Error)SmokeError=Error;
    if(Now-SmokeStarted>240)SmokeError=TEXT("Validation exceeded 240 seconds");
    if(!SmokeError.IsEmpty())SmokeStep=99;
    if(SmokeStep==0&&bReady&&Now-SmokeStepStarted>3)
    {
        // Exercise normal motion by default, independently of the host OS accessibility setting.
        bSmokeReducedMotion=FParse::Param(FCommandLine::Get(),TEXT("GlobeSmokeReducedMotion"));
        Command(bSmokeReducedMotion?TEXT("{\"action\":\"reducedMotion\",\"enabled\":true}"):TEXT("{\"action\":\"reducedMotion\",\"enabled\":false}"));
        Command(TEXT("{\"action\":\"interaction\",\"active\":false}"));
        if(Registry.GetEntries().IsEmpty()){SmokeError=TEXT("No warehouses");SmokeStep=99;}
        else if(!GlobeRoot.IsValid()){SmokeError=TEXT("Globe root unavailable for idle rotation validation");SmokeStep=99;}
        else
        {
            TSharedPtr<FJsonObject> State;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(GetState()),State);
            if(!State||State->GetArrayField(TEXT("pois")).IsEmpty()||!State->GetArrayField(TEXT("pois"))[0]->AsObject()->GetBoolField(TEXT("visible")))
                {SmokeError=TEXT("Initial warehouse POI is not visible");SmokeStep=99;}
            else {SmokeIdleYawStart=GlobeRoot->GetActorRotation().Yaw;Snapshot(TEXT("01-initial"));SmokeStep=1;SmokeStepStarted=Now;}
        }
    }
    else if(SmokeStep==1&&Now-SmokeStepStarted>8)
    {
        // Rotation runs continuously in normal motion mode, without an input cooldown.
        SmokeIdleYawEnd=GlobeRoot.IsValid()?GlobeRoot->GetActorRotation().Yaw:SmokeIdleYawStart;
        const double Travel=FMath::Abs(FMath::FindDeltaAngleDegrees(SmokeIdleYawStart,SmokeIdleYawEnd));
        bSmokeIdleRotationVerified=GlobeRoot.IsValid()&&(bSmokeReducedMotion?Travel<.001:Travel>5.);
        if(!bSmokeIdleRotationVerified)SmokeError=TEXT("Idle globe rotation did not match the requested motion mode");
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn()))
        {
            const double BeforeYaw=Camera->DesiredRotation.Yaw,BeforeZoom=Camera->DesiredZoom;
            Command(TEXT("{\"action\":\"orbit\",\"dx\":30,\"dy\":0}"));Command(TEXT("{\"action\":\"zoom\",\"steps\":1}"));
            if(FMath::IsNearlyEqual(BeforeYaw,Camera->DesiredRotation.Yaw)||Camera->DesiredZoom>=BeforeZoom)SmokeError=TEXT("Camera orbit/zoom bridge did not change the existing camera targets");
            for(int32 I=0;I<40;++I)Command(TEXT("{\"action\":\"zoom\",\"steps\":-5}"));
        }
        else SmokeError=TEXT("Existing warehouse camera pawn unavailable");
        SmokeStep=12;SmokeStepStarted=Now;
    }
    else if(SmokeStep==12&&Now-SmokeStepStarted>2)
    {
        const auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
        bool InsideBackground=false;
        if(Camera)for(const auto& Entry:StageActors)if(auto* Actor=Entry.Actor.Get();Actor&&Actor->ActorHasTag(TEXT("GHS_GlobeBackground")))
        {
            FVector Center,Extent;Actor->GetActorBounds(false,Center,Extent);
            InsideBackground=(Camera->WarehouseCamera->GetComponentLocation()-Center).Size()<Extent.GetMin();
        }
        bSmokeZoomBounds=Camera&&InsideBackground&&FMath::IsNearlyEqual(Camera->CaptureReplayPose().Distance,Camera->MaximumZoom,1.f)
            &&Camera->GetActorLocation().Equals(GlobeCenter,.01);
        if(!bSmokeZoomBounds)SmokeError=TEXT("Maximum zoom escaped background or moved globe pivot");
        Snapshot(TEXT("05-maximum-zoom-out"));
        for(int32 I=0;I<40;++I)Command(TEXT("{\"action\":\"zoom\",\"steps\":5}"));
        SmokeStep=13;SmokeStepStarted=Now;
    }
    else if(SmokeStep==13&&Now-SmokeStepStarted>2)
    {
        const auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
        bSmokeZoomBounds&=Camera&&FMath::IsNearlyEqual(Camera->CaptureReplayPose().Distance,Camera->MinimumZoom,1.f)
            &&(Camera->WarehouseCamera->GetComponentLocation()-GlobeCenter).Size()>GlobeRadius;
        if(!bSmokeZoomBounds)SmokeError=TEXT("Minimum zoom failed surface clearance");
        Snapshot(TEXT("06-maximum-zoom-in"));Command(TEXT("{\"action\":\"home\"}"));SmokeStep=14;SmokeStepStarted=Now;
    }
    else if(SmokeStep==14&&Now-SmokeStepStarted>1.2)
    {
        const auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
        const FRotator HomeDelta=GlobeRoot.IsValid()?(GlobeRoot->GetActorQuat()*InitialGlobeRotation.Inverse()).Rotator():FRotator::ZeroRotator;
        const double MaxContinuedYaw=bSmokeReducedMotion?.0001:FMath::Abs(IdleRotationDegreesPerSecond)*(Now-SmokeStepStarted)+.1;
        bSmokeHomeReset=Camera&&!Camera->IsPoseTransitionActive()&&Camera->GetActorRotation().Equals(FRotator(-32,-96,0),.01)
            &&Camera->GetActorLocation().Equals(GlobeCenter,.01)&&GlobeRoot.IsValid()&&!bResettingGlobe
            &&FMath::Abs(HomeDelta.Pitch)<.001&&FMath::Abs(HomeDelta.Roll)<.001&&FMath::Abs(HomeDelta.Yaw)<=MaxContinuedYaw;
        if(!bSmokeHomeReset)SmokeError=TEXT("Home did not restore camera and globe orientation");
        auto Request=MakeShared<FJsonObject>();Request->SetStringField(TEXT("action"),TEXT("select"));Request->SetStringField(TEXT("id"),Registry.GetEntries()[0].Id);Command(Encode(Request));SmokeStep=2;SmokeStepStarted=Now;
    }
    else if(SmokeStep==2&&Phase==EPhase::Selected&&Now-SmokeStepStarted>3)
    {Snapshot(TEXT("02-selected"));SmokeStep=3;SmokeStepStarted=Now;}
    else if(SmokeStep==3&&Now-SmokeStepStarted>2)
    {
        EnterSelected();SmokeStep=4;SmokeStepStarted=Now;
    }
    else if(SmokeStep==4&&Phase==EPhase::Warehouse&&Now-SmokeStepStarted>3)
    {
        CheckWarehouse();Snapshot(TEXT("03-warehouse"));SmokeStep=5;SmokeStepStarted=Now;bSmokeRoofOpened=false;
    }
    else if(SmokeStep==5)
    {
        OpenRoofBeforeReturn();
        if(Now-SmokeStepStarted>3)
        {
            if(Experience&&Experience->UsesWarehouseHUD()&&(!WarehouseRoof||!WarehouseRoof->IsInteriorAvailable()))SmokeError=TEXT("Roof opening did not complete before first return");
            Command(TEXT("{\"action\":\"back\"}"));SmokeStep=6;SmokeStepStarted=Now;
        }
    }
    else if(SmokeStep==6&&Phase==EPhase::Selected&&Now-SmokeStepStarted>3)
    {
        CheckReturned();Snapshot(TEXT("04-returned"));SmokeStep=7;SmokeStepStarted=Now;
    }
    else if(SmokeStep==7&&Now-SmokeStepStarted>3)
    {EnterSelected();SmokeStep=8;SmokeStepStarted=Now;}
    else if(SmokeStep==8&&Phase==EPhase::Warehouse&&Now-SmokeStepStarted>3)
    {CheckWarehouse();SmokeStep=9;SmokeStepStarted=Now;bSmokeRoofOpened=false;}
    else if(SmokeStep==9)
    {
        OpenRoofBeforeReturn();
        if(Now-SmokeStepStarted>3)
        {
            if(Experience&&Experience->UsesWarehouseHUD()&&(!WarehouseRoof||!WarehouseRoof->IsInteriorAvailable()))SmokeError=TEXT("Roof opening did not complete before second return");
            Command(TEXT("{\"action\":\"back\"}"));SmokeStep=10;SmokeStepStarted=Now;
        }
    }
    else if(SmokeStep==10&&Phase==EPhase::Selected&&Now-SmokeStepStarted>3)
    {CheckReturned();SmokeStep=11;SmokeStepStarted=Now;}
    else if((SmokeStep==11&&Now-SmokeStepStarted>3)||SmokeStep==99)
    {
        auto Report=MakeShared<FJsonObject>();Report->SetBoolField(TEXT("success"),SmokeError.IsEmpty());Report->SetStringField(TEXT("error"),SmokeError);Report->SetNumberField(TEXT("elapsedSeconds"),Now-SmokeStarted);
        Report->SetBoolField(TEXT("testedReducedMotion"),bSmokeReducedMotion);
        Report->SetNumberField(TEXT("cycles"),SmokeCycles);Report->SetBoolField(TEXT("idleRotationVerified"),bSmokeIdleRotationVerified);
        Report->SetNumberField(TEXT("idleYawStart"),SmokeIdleYawStart);Report->SetNumberField(TEXT("idleYawEnd"),SmokeIdleYawEnd);
        Report->SetBoolField(TEXT("cameraFovRestored"),SmokeWarehouseFovChecks==2&&SmokeGlobeFovChecks==2);
        Report->SetBoolField(TEXT("hudRebuilt"),bSmokeHUDRebuilt);
        Report->SetBoolField(TEXT("zoomBoundsVerified"),bSmokeZoomBounds);Report->SetBoolField(TEXT("homeResetVerified"),bSmokeHomeReset);
        Report->SetBoolField(TEXT("flightCaptured"),bSmokeFlightCaptured);Report->SetBoolField(TEXT("arrivalCaptured"),bSmokeArrivalCaptured);
        Report->SetBoolField(TEXT("browserReady"),bReady);Report->SetBoolField(TEXT("warehouseUnloadedOnReturn"),!Destination&&!bUnloadRequested);Report->SetStringField(TEXT("scope"),TEXT("Real CEF readiness, viewport screenshots, idle rotation, camera FOV, two warehouse entry/return cycles, HUD recreation and roof reference cleanup; not OS input latency"));
        const FString Folder=FPaths::ProjectSavedDir()/TEXT("GlobeValidation");IFileManager::Get().MakeDirectory(*Folder,true);FFileHelper::SaveStringToFile(Encode(Report),*(Folder/TEXT("result.json")));
        UE_LOG(LogTemp,Display,TEXT("GHS_GLOBE_SMOKE %s"),*Encode(Report));bSmokeTest=false;FPlatformMisc::RequestExitWithStatus(false,SmokeError.IsEmpty()?0:1);
    }
    if(!bSmokeReducedMotion&&Phase==EPhase::Flying&&PhaseTime>FGHSGlobeFlight::Duration*.5f&&!bSmokeFlightCaptured)
    {Snapshot(TEXT("07-flight-midpoint"));bSmokeFlightCaptured=true;}
    if(!bSmokeReducedMotion&&Phase==EPhase::Revealing&&bArrivalStarted&&PhaseTime>.65f&&!bSmokeArrivalCaptured)
    {Snapshot(TEXT("08-warehouse-arrival"));bSmokeArrivalCaptured=true;}
#endif
}
void AGHSGlobePlayerController::TickPortalSmokeTest()
{
#if !UE_BUILD_SHIPPING
    const double Now=FPlatformTime::Seconds();
    auto Snapshot=[&](const TCHAR* Name)
    {
        const FString Folder=FPaths::ProjectSavedDir()/TEXT("PortalValidation");IFileManager::Get().MakeDirectory(*Folder,true);
        FFileHelper::SaveStringToFile(GetState(),*(Folder/(FString(Name)+TEXT(".json"))));
        FScreenshotRequest::RequestScreenshot(FPaths::ConvertRelativePathToFull(Folder/(FString(Name)+TEXT(".png"))),true,false);
    };
    auto Advance=[&](int32 Step){SmokeStep=Step;SmokeStepStarted=Now;};
    auto CheckWarehouse=[&](const TCHAR* Id)
    {
        if(SelectedId!=Id||LoadedId!=Id||!Destination||!Destination->IsLevelVisible()||!Experience||!Experience->IsReady(*this))
            SmokeError=TEXT("Selected destination is not fully visible and ready");
        const auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
        if(!Camera||Camera!=PersistentCamera||Camera->GetLevel()!=GetWorld()->PersistentLevel||GetViewTarget()!=Camera)
            SmokeError=TEXT("Warehouse lost the persistent camera or view target");
        if(!Camera||!Camera->WarehouseCamera||!FMath::IsNearlyEqual(Camera->WarehouseCamera->FieldOfView,GetDefault<AGHSWarehouseCameraPawn>()->WarehouseCamera->FieldOfView,.01f))
            SmokeError=TEXT("Warehouse camera FOV was not restored");
        if(!TwinHUDWidget||!WarehouseRoof||!WarehouseRoof->HasRoof()||!WarehouseRoof->IsRoofClosed())
            SmokeError=TEXT("Warehouse HUD or closed roof was not initialized");
        if(WarehouseMarkers||CountryLabels||WarehouseOverlay)
            SmokeError=TEXT("Portal allocated globe annotations");
        if(SmokeCycles==0)SmokePreviousHUD=TwinHUDWidget;
        else if(TWeakObjectPtr<UGHSTwinHUDWidget>(TwinHUDWidget.Get())==SmokePreviousHUD)
            SmokeError=TEXT("Second warehouse reused the disposed HUD");
        else bSmokeHUDRebuilt=true;
    };
    auto CheckReturned=[&]()
    {
        if(Destination||bUnloadRequested||TwinHUDWidget||CampusTraffic||Experience||!bStageVisible)
            SmokeError=TEXT("Return retained destination, HUD, traffic or experience");
        if(GetPawn()!=PersistentCamera||GetViewTarget()!=PersistentCamera)
            SmokeError=TEXT("Return lost the persistent camera");
        if(WarehouseRoof)
        {
            const auto Roof=WarehouseRoof->CaptureReplayState();
            if(Roof.HasRoofVisibility||!Roof.Roofs.IsEmpty()||!Roof.Shells.IsEmpty()||Roof.TickEnabled)
                SmokeError=TEXT("Return retained roof state");
        }
        for(const auto& Entry:StageActors)if(const auto* Actor=Entry.Actor.Get())
            if(!Actor->IsHidden()||Actor->IsActorTickEnabled())SmokeError=TEXT("Returning exposed the legacy globe stage");
        ++SmokeCycles;
    };
    if(Now-SmokeStarted>300)SmokeError=TEXT("Portal validation exceeded 300 seconds");
    if(SmokeStep==12&&!bPortalSmokeLogin&&Now-SmokeStepStarted>5)SmokeError=TEXT("CEF login submit did not reach the warehouse selection page");
    if(SmokeStep>1&&Phase==EPhase::Error)SmokeError=Error;
    if(!SmokeError.IsEmpty())SmokeStep=99;
    if(SmokeStep==0&&bReady&&Now-SmokeStepStarted>3)
    {
        if(!Registry.Find(TEXT("ghs-ca"))||!Registry.Find(TEXT("mpr-nj")))SmokeError=TEXT("GHS/MPR catalog entries unavailable");
        Snapshot(TEXT("01-login"));Advance(1);
    }
    else if(SmokeStep==1&&Now-SmokeStepStarted>1)
    {
        // Exercise the mounted CEF page's real submit control. No credentials,
        // session token or server-side authentication are invented by this test.
        if(GlobeHUD&&GlobeHUD->Browser)GlobeHUD->Browser->Evaluate(TEXT("document.getElementById('login-button')?.click();"));
        Advance(2);
    }
    else if(SmokeStep==2&&Now-SmokeStepStarted>1)
    {
        if(GlobeHUD&&GlobeHUD->Browser)GlobeHUD->Browser->Evaluate(TEXT("window.ue.twin.command(JSON.stringify({action:'portalSmokePage',page:window.ghsEntry?.getPage()}));"));
        Advance(12);
    }
    else if(SmokeStep==12&&bPortalSmokeLogin)
    {
        Snapshot(TEXT("02-warehouse-selection"));Advance(13);
    }
    else if(SmokeStep==13&&Now-SmokeStepStarted>1)
    {
        Command(TEXT("{\"action\":\"enter\",\"id\":\"missing-warehouse\"}"));
        bPortalSmokeRecovery=Phase==EPhase::Error&&!Error.IsEmpty()&&!Destination;
        Command(TEXT("{\"action\":\"cancel\"}"));
        bPortalSmokeRecovery=bPortalSmokeRecovery&&Phase==EPhase::Idle&&Error.IsEmpty();
        Command(TEXT("{\"action\":\"enter\",\"id\":\"ghs-ca\"}"));
        if(Phase==EPhase::Loading)Command(TEXT("{\"action\":\"cancel\"}"));
        bPortalSmokeCancellation=Phase==EPhase::Idle&&!bEntryRequested&&!bPreloadRequested&&SelectedId.IsEmpty();
        if(!bPortalSmokeRecovery||!bPortalSmokeCancellation)SmokeError=TEXT("Invalid selection recovery or loading cancellation failed");
        Advance(3);
    }
    else if(SmokeStep==3&&!Destination&&!bUnloadRequested&&Now-SmokeStepStarted>1)
    {
        if(GlobeHUD&&GlobeHUD->Browser)GlobeHUD->Browser->Evaluate(TEXT("document.querySelector('[data-enter=\"ghs-ca\"]')?.click();"));
        Advance(4);
    }
    else if(SmokeStep==4&&Phase==EPhase::Warehouse)Advance(16);
    else if(SmokeStep==16&&Now-SmokeStepStarted>1)
    {CheckWarehouse(TEXT("ghs-ca"));Snapshot(TEXT("03-ghs-warehouse"));Advance(5);}
    else if(SmokeStep==5&&Now-SmokeStepStarted>1)
    {
        if(!WarehouseRoof||!WarehouseRoof->OpenRoof(true))SmokeError=TEXT("GHS roof could not be opened before return");
        if(GlobeHUD&&GlobeHUD->Browser)GlobeHUD->Browser->Evaluate(TEXT("document.getElementById('back-button')?.click();"));
        Advance(6);
    }
    else if(SmokeStep==6&&(Phase==EPhase::Idle||Phase==EPhase::Selected)&&!Destination&&!bUnloadRequested)
    {CheckReturned();Advance(14);}
    else if(SmokeStep==14&&Now-SmokeStepStarted>1)
    {Snapshot(TEXT("04-ghs-return"));Advance(7);}
    else if(SmokeStep==7&&Now-SmokeStepStarted>1)
    {
        if(GlobeHUD&&GlobeHUD->Browser)GlobeHUD->Browser->Evaluate(TEXT("document.querySelector('[data-enter=\"mpr-nj\"]')?.click();"));
        Advance(8);
    }
    else if(SmokeStep==8&&Phase==EPhase::Warehouse)Advance(17);
    else if(SmokeStep==17&&Now-SmokeStepStarted>1)
    {CheckWarehouse(TEXT("mpr-nj"));Snapshot(TEXT("05-mpr-warehouse"));Advance(9);}
    else if(SmokeStep==9&&Now-SmokeStepStarted>1)
    {
        if(GlobeHUD&&GlobeHUD->Browser)GlobeHUD->Browser->Evaluate(TEXT("document.getElementById('back-button')?.click();"));
        Advance(10);
    }
    else if(SmokeStep==10&&(Phase==EPhase::Idle||Phase==EPhase::Selected)&&!Destination&&!bUnloadRequested)
    {CheckReturned();Advance(15);}
    else if(SmokeStep==15&&Now-SmokeStepStarted>1)
    {Snapshot(TEXT("06-mpr-return"));Advance(11);}
    else if(SmokeStep==11&&Now-SmokeStepStarted>1)SmokeStep=99;
    if(SmokeStep==99)
    {
        const bool Passed=SmokeError.IsEmpty()&&SmokeCycles==2&&bPortalSmokeLogin&&bPortalSmokeCancellation&&bPortalSmokeRecovery&&bSmokeHUDRebuilt;
        auto Report=MakeShared<FJsonObject>();Report->SetBoolField(TEXT("success"),Passed);Report->SetStringField(TEXT("error"),SmokeError);
        Report->SetNumberField(TEXT("warehouseCycles"),SmokeCycles);Report->SetBoolField(TEXT("loadingCancellation"),bPortalSmokeCancellation);
        Report->SetBoolField(TEXT("loginSubmitReachedSelection"),bPortalSmokeLogin);
        Report->SetBoolField(TEXT("invalidSelectionRecovery"),bPortalSmokeRecovery);Report->SetBoolField(TEXT("hudRecreated"),bSmokeHUDRebuilt);
        Report->SetBoolField(TEXT("browserReady"),bReady);Report->SetBoolField(TEXT("destinationUnloaded"),!Destination&&!bUnloadRequested);
        Report->SetStringField(TEXT("scope"),TEXT("Real CEF login, GHS/MPR card and return button clicks with screenshots; curtain acknowledgements, HUD recreation and unloading; native command checks for loading cancellation and invalid selection recovery"));
        const FString Folder=FPaths::ProjectSavedDir()/TEXT("PortalValidation");IFileManager::Get().MakeDirectory(*Folder,true);
        FFileHelper::SaveStringToFile(Encode(Report),*(Folder/TEXT("result.json")));
        UE_LOG(LogTemp,Display,TEXT("GHS_PORTAL_SMOKE %s"),*Encode(Report));bPortalSmokeTest=false;FPlatformMisc::RequestExitWithStatus(false,Passed?0:1);
    }
#endif
}
void AGHSGlobePlayerController::PushState(bool bIncludeCatalog){if(bReady&&GlobeHUD)GlobeHUD->Push(BuildState(bIncludeCatalog));}
FString AGHSGlobePlayerController::GetState()const{return BuildState(true);}
FString AGHSGlobePlayerController::BuildState(bool bIncludeCatalog)const
{
    static const TCHAR* Names[]={TEXT("idle"),TEXT("selected"),TEXT("loading"),TEXT("flying"),TEXT("revealing"),TEXT("warehouse"),TEXT("returning"),TEXT("error")};
    auto Root=MakeShared<FJsonObject>();Root->SetStringField(TEXT("phase"),Names[int32(Phase)]);Root->SetStringField(TEXT("selectedId"),SelectedId);Root->SetStringField(TEXT("error"),Error);
    Root->SetBoolField(TEXT("reducedMotion"),bReducedMotion);Root->SetBoolField(TEXT("stageVisible"),bStageVisible);
    Root->SetBoolField(TEXT("portalEntry"),bPortalEntry);
    Root->SetBoolField(TEXT("nativeWarehouseAnnotations"),WarehouseOverlay.IsValid());
    Root->SetBoolField(TEXT("nativeCountryLabels"),CountryLabels!=nullptr);
    Root->SetStringField(TEXT("selectionInputSource"),SelectionInputSource);
    auto View=MakeShared<FJsonObject>();View->SetNumberField(TEXT("width"),Viewport.X);View->SetNumberField(TEXT("height"),Viewport.Y);Root->SetObjectField(TEXT("viewport"),View);
    auto Transition=MakeShared<FJsonObject>();Transition->SetNumberField(TEXT("opacity"),MaskOpacity);Transition->SetNumberField(TEXT("progress"),FMath::Clamp(PhaseTime/EntryTransitionDuration(),0.f,1.f));
    Transition->SetNumberField(TEXT("generation"),Curtain.GetGeneration());
    Transition->SetBoolField(TEXT("waitingForDestination"),
        (Phase==EPhase::Flying&&PhaseTime>EntryTransitionDuration()+2)
        ||(Phase==EPhase::Revealing&&!bArrivalStarted&&GetWorld()->GetTimeSeconds()-LoadStarted>2));
    Transition->SetBoolField(TEXT("awaitingCurtain"),Curtain.Active()&&!Curtain.Ready(GFrameCounter,GlobeHUD&&GlobeHUD->HasFullBrowserCoverage())&&(Phase==EPhase::Flying||(Phase==EPhase::Returning&&!bReturningCommitted)));
    Transition->SetNumberField(TEXT("width"),Curtain.GetExpectedSize().X);Transition->SetNumberField(TEXT("height"),Curtain.GetExpectedSize().Y);Root->SetObjectField(TEXT("transition"),Transition);
    TArray<TSharedPtr<FJsonValue>> Pois,Countries;
    int32 PW=0,PH=0;GetViewportSize(PW,PH);
    FSceneViewProjectionData ProjectionData;
    const auto* Local=GetLocalPlayer();
    const bool bHasProjection=!bPortalEntry&&bStageVisible&&PW>0&&PH>0&&Local&&Local->ViewportClient&&Local->ViewportClient->Viewport
        &&Local->GetProjectionData(Local->ViewportClient->Viewport,ProjectionData)&&ProjectionData.IsValidViewRectangle();
    const FMatrix ViewProjection=bHasProjection?ProjectionData.ComputeViewProjectionMatrix():FMatrix::Identity;
    const auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetPawn());
    const FVector Eye=bHasProjection?ProjectionData.ViewOrigin:
        (Camera&&Camera->WarehouseCamera?Camera->WarehouseCamera->GetComponentLocation():FVector::ZeroVector);
    if(bIncludeCatalog&&Camera)
    {
        const auto Pose=Camera->CaptureReplayPose();auto Diagnostics=MakeShared<FJsonObject>();
        Diagnostics->SetStringField(TEXT("pivot"),Pose.Pivot.ToString());Diagnostics->SetStringField(TEXT("eye"),Eye.ToString());
        Diagnostics->SetStringField(TEXT("rotation"),Pose.Rotation.ToString());Diagnostics->SetNumberField(TEXT("distance"),Pose.Distance);
        Diagnostics->SetNumberField(TEXT("desiredDistance"),Camera->DesiredZoom);Diagnostics->SetNumberField(TEXT("globeYaw"),GlobeRoot.IsValid()?GlobeRoot->GetActorRotation().Yaw:0);
        Diagnostics->SetNumberField(TEXT("annotationOpacity"),WarehouseOverlay?WarehouseOverlay->GetAnnotationOpacity():0.f);
        Diagnostics->SetBoolField(TEXT("annotationInteractive"),WarehouseOverlay&&WarehouseOverlay->IsAnnotationInteractive());
        Diagnostics->SetNumberField(TEXT("radiusFromCenter"),(Eye-GlobeCenter).Size());Root->SetObjectField(TEXT("camera"),Diagnostics);
    }
    // Reuse one projection/eye for both visibility and every point. Preserve the
    // player-relative screen origin before converting physical pixels to CSS.
    auto ProjectPoint=[&](const FVector& P,FVector2D& Css)
    {
        if(!bHasProjection||!GHSGlobe::IsSurfaceVisible(P,Eye,GlobeCenter))return false;
        FVector2D Pixels=FVector2D::ZeroVector;
        if(!FSceneView::ProjectWorldToScreen(P,ProjectionData.GetConstrainedViewRect(),ViewProjection,Pixels))return false;
        Pixels-=FVector2D(ProjectionData.GetConstrainedViewRect().Min);
        if(!PostProcessWorldToScreen(P,Pixels,true))return false;
        Css=FVector2D(Pixels.X*Viewport.X/PW,Pixels.Y*Viewport.Y/PH);
        return true;
    };
    auto Project=[&](double Lat,double Lon,TSharedRef<FJsonObject> O)
    {
        FVector2D Css=FVector2D::ZeroVector;const bool Visible=ProjectPoint(Position(Lat,Lon),Css);
        O->SetBoolField(TEXT("visible"),Visible);O->SetNumberField(TEXT("x"),Visible?Css.X:0);O->SetNumberField(TEXT("y"),Visible?Css.Y:0);
    };
    // Cull geometry first, then merge all remaining members into a bounded screen-grid payload.
    TArray<FGHSWarehouseProjectedPoint> VisiblePoints;
    if(bHasProjection)
    {
        for(const auto& W:Registry.GetEntries())
        {
            FVector P;FVector2D Logical=FVector2D::ZeroVector;
            if(!WarehouseMarkers||!WarehouseMarkers->GetWorldAnchor(W.Id,P))continue;
            if(!ProjectPoint(P,Logical))continue;
            if(Logical.X<ScenePosition.X||Logical.X>ScenePosition.X+SceneSize.X||Logical.Y<ScenePosition.Y||Logical.Y>ScenePosition.Y+SceneSize.Y)continue;
            VisiblePoints.Add({W.Id,Logical});
        }
    }
    for(const auto& Cluster:GHSClusterWarehousePoints(VisiblePoints,SelectedId))
    {
        auto Poi=MakeShared<FJsonObject>();Poi->SetStringField(TEXT("id"),Cluster.Id);Poi->SetNumberField(TEXT("x"),Cluster.Position.X);Poi->SetNumberField(TEXT("y"),Cluster.Position.Y);Poi->SetBoolField(TEXT("visible"),true);
        TArray<TSharedPtr<FJsonValue>> Ids;for(const auto& Id:Cluster.Ids)Ids.Add(MakeShared<FJsonValueString>(Id));Poi->SetArrayField(TEXT("ids"),Ids);Poi->SetNumberField(TEXT("count"),Cluster.Ids.Num());Pois.Add(MakeShared<FJsonValueObject>(Poi));
    }
    struct FCountry{const TCHAR* Name;double Lat,Lon;};
    static const FCountry Labels[]={{TEXT("加拿大"),57,-105},{TEXT("美国"),39,-98},{TEXT("墨西哥"),23,-102},{TEXT("哥伦比亚"),4,-74},{TEXT("委内瑞拉"),8,-65},{TEXT("秘鲁"),-9,-75},{TEXT("巴西"),-10,-52},{TEXT("智利"),-34,-71},{TEXT("阿根廷"),-37,-64},{TEXT("中国"),35,103},{TEXT("澳大利亚"),-25,134},{TEXT("印度"),22,79},{TEXT("俄罗斯"),61,100},{TEXT("南非"),-29,25}};
    if(!bPortalEntry&&bStageVisible)for(const auto& C:Labels){auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("id"),C.Name);O->SetStringField(TEXT("label"),C.Name);Project(C.Lat,C.Lon,O);Countries.Add(MakeShared<FJsonValueObject>(O));}
    Root->SetNumberField(TEXT("catalogRevision"),double(Registry.GetRevision()));
    Root->SetBoolField(TEXT("poisComplete"),true);Root->SetNumberField(TEXT("poiBudget"),256);
    Root->SetArrayField(TEXT("pois"),Pois);Root->SetArrayField(TEXT("countries"),Countries);
    FString Result=Encode(Root);
    if(bIncludeCatalog){Result.LeftChopInline(1);Result+=TEXT(",\"warehouses\":")+Registry.GetCatalogJson()+TEXT("}");}
    return Result;
}
