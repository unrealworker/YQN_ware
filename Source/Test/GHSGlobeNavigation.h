#pragma once

#include "CoreMinimal.h"
#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseGameMode.h"
#include "GHSWarehouseRegistry.h"
#include "GHSWarehouseExperience.h"
#include "GHSGlobeTransition.h"
#include "GHSGlobeFlight.h"
#include "Blueprint/UserWidget.h"
#include "GHSGlobeNavigation.generated.h"

class UGHSTwinBrowser;
class UCanvasPanelSlot;
class ULevelStreamingDynamic;
class AGHSWarehouseCameraPawn;
class AGHSGlobeWarehouseMarkers;
class AGHSGlobeCountryLabels;
class SGHSGlobeWarehouseOverlay;

/** Reuses the warehouse CEF surface, with a small return control inside the warehouse. */
UCLASS()
class TEST_API UGHSGlobeHUD : public UUserWidget
{
    GENERATED_BODY()
public:
    void Push(const FString& Json);
    void SetCompact(bool bCompact);
    void ShowWarehouseCluster(const TArray<FString>& Ids);
    FVector2D GetFullSize()const{return FullSize;}
    FVector2D GetFullBrowserCssSize()const{return FullBrowserCssSize;}
    bool HasFullBrowserCoverage()const{return !bSmall&&bFullBrowserCoverage;}
    float GetLayoutScale()const{return LayoutScale;}
    float GetWindowDpi()const{return WindowDpi;}
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
    virtual void NativeConstruct() override;
    virtual void NativeTick(const FGeometry& Geometry,float DeltaSeconds) override;
private:
    UPROPERTY(Transient) TObjectPtr<UGHSTwinBrowser> Browser;
    UPROPERTY(Transient) TObjectPtr<UCanvasPanelSlot> BrowserSlot;
    bool bSmall=false;
    FVector2D FullSize=FVector2D(1920,1080);
    FVector2D FullBrowserCssSize=FVector2D(1920,1080);
    float LayoutScale=1,WindowDpi=1;
    bool bFullBrowserCoverage=false;
};

/** Persistent globe world streams destination maps; no browser or WebRTC connection is replaced. */
UCLASS(Blueprintable)
class TEST_API AGHSGlobePlayerController : public AGHSWarehousePlayerController
{
    GENERATED_BODY()
public:
    AGHSGlobePlayerController();
    virtual void PlayerTick(float DeltaSeconds) override;
    virtual void UpdateCameraManager(float DeltaSeconds) override;
    virtual bool InputKey(const FInputKeyEventArgs& Params) override;
    UFUNCTION(BlueprintCallable,Category="Globe") void Command(const FString& Json);
    UFUNCTION(BlueprintPure,Category="Globe") FString GetState() const;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Globe") FVector GlobeCenter=FVector(0,0,300000);
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Globe") float GlobeRadius=10000.f;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Globe") float IdleRotationDegreesPerSecond=1.5f;
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void OnPossess(APawn* PawnToPossess) override;
private:
    enum class EPhase : uint8 {Idle,Selected,Loading,Flying,Revealing,Warehouse,Returning,Error};
    void ResetGlobeCamera(bool bImmediate);
    void PreloadSelected();
    void UnloadDestination();
    void PollDestination();
    void StartFlight();
    void BeginCurtain();
    bool AwaitCurtain();
    void SetStageVisible(bool bVisible);
    void Fail(const FString& Message);
    FVector Position(double Latitude,double Longitude) const;
    const FGHSGlobeWarehouse* Selected() const;
    void PushState(bool bIncludeCatalog=false);
    void UpdateGlobeAnnotations(float DeltaSeconds);
    FString BuildState(bool bIncludeCatalog)const;
    void TickSmokeTest();
    UPROPERTY(Transient) TObjectPtr<UGHSGlobeHUD> GlobeHUD;
    UPROPERTY(Transient) TObjectPtr<ULevelStreamingDynamic> Destination;
    UPROPERTY(Transient) TObjectPtr<AGHSWarehouseCameraPawn> PersistentCamera;
    UPROPERTY(Transient) TObjectPtr<AGHSGlobeWarehouseMarkers> WarehouseMarkers;
    UPROPERTY(Transient) TObjectPtr<AGHSGlobeCountryLabels> CountryLabels;
    FGHSWarehouseRegistry Registry;
    TUniquePtr<IGHSWarehouseExperience> Experience;
    FGHSGlobeCurtainGate Curtain;
    uint32 LastLoggedCurtainAck=0;
    struct FStageActorState
    {
        TWeakObjectPtr<AActor> Actor;
        bool bHidden=false,bTickEnabled=false,bPostProcessEnabled=false;
    };
    TArray<FStageActorState> StageActors;
    TWeakObjectPtr<AActor> GlobeRoot;
    FQuat InitialGlobeRotation=FQuat::Identity,ResetStartRotation=FQuat::Identity;
    FGHSGlobeFlight Flight;
    float GlobeResetTime=0;
    bool bResettingGlobe=false,bArrivalStarted=false;
    TSharedPtr<SWidget> GlobeViewportWidget;
    TSharedPtr<SGHSGlobeWarehouseOverlay> WarehouseOverlay;
    bool bAnnotationSceneTransition=false;
    EPhase Phase=EPhase::Idle;
    FString SelectedId,LoadedId,Error;
    FString SelectionInputSource=TEXT("unknown"),AnnotationInputSource=TEXT("unknown");
    FVector2D Viewport=FVector2D(1920,1080),ScenePosition=FVector2D(0,64),SceneSize=FVector2D(1420,1016);
    double LoadStarted=0,NextPush=0;
    float PhaseTime=0,MaskOpacity=0;
    bool bReady=false,bReducedMotion=false,bEntryRequested=false,bStageVisible=true,bReturningApplied=false,bReturningCommitted=false;
    bool bUnloadRequested=false,bPreloadRequested=false,bUnloadTimedOut=false;
    int32 SmokeStep=0,SmokeCycles=0,SmokeWarehouseFovChecks=0,SmokeGlobeFovChecks=0;
    double SmokeStarted=0,SmokeStepStarted=0;
    double SmokeIdleYawStart=0,SmokeIdleYawEnd=0;
    bool bSmokeTest=false,bSmokeReducedMotion=false;
    bool bSmokeIdleRotationVerified=false,bSmokeHUDRebuilt=false,bSmokeRoofOpened=false;
    bool bSmokeZoomBounds=false,bSmokeHomeReset=false,bSmokeFlightCaptured=false,bSmokeArrivalCaptured=false;
    TWeakObjectPtr<UGHSTwinHUDWidget> SmokePreviousHUD;
    FString SmokeError;
};

UCLASS(Blueprintable)
class TEST_API AGHSGlobeGameMode : public AGHSWarehouseGameMode
{
    GENERATED_BODY()
public:
    AGHSGlobeGameMode();
};
