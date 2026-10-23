#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GHSWarehouseRoofComponent.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSOrderReplaySession.generated.h"

class AGHSOrderReplayActor;
class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UStaticMesh;
class FJsonValue;

/** Wall-frame deltas affect only this clock. Seeking is a pure absolute evaluation. */
struct TEST_API FGHSReplayClock
{
    double Time=0,Duration=0,Rate=1;
    bool Playing=false;
    bool Start(double Seconds);
    void Advance(double Seconds);
    void Seek(double Seconds);
    void SetRate(double Value);
    bool Completed() const {return Duration>0 && Time>=Duration;}
};

/** One pending intent; cancellation resumes precisely the state before the prompt. */
struct TEST_API FGHSReplayExitGuard
{
    FString Intent;
    bool WasPlaying=false;
    bool Request(const FString& Value,FGHSReplayClock& Clock);
    void Cancel(FGHSReplayClock& Clock);
    FString Consume();
    bool Pending() const {return !Intent.IsEmpty();}
};

UCLASS()
class TEST_API UGHSOrderReplaySession : public UActorComponent
{
    GENERATED_BODY()
public:
    UGHSOrderReplaySession();
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    bool Start(const FString& Order,const FString& StartUtc,const FString& EndUtc);
    void Stop();
    void Advance(float DeltaSeconds,FVector2D Viewport,FVector2D SceneCenter);
    void Play();
    void Pause();
    void Seek(double Seconds);
    void SetRate(double Rate);
    void Select(const FString& Id);
    void Follow(const FString& Id,FVector2D Viewport,FVector2D SceneCenter);
    void SetTrails(const FString& Mode);
    void SetEventWindow(double Start,double End,bool bReset=false);
    bool Pick(const FVector& Origin,const FVector& Direction,FString& Id) const;
    bool RequestExit(const FString& Intent,const FString& Title,const FString& Label);
    void CancelExit();
    FString ConfirmExit();
    UFUNCTION(BlueprintPure,Category="Warehouse Replay") bool IsReplaying() const {return bActive;}
    UFUNCTION(BlueprintPure,Category="Warehouse Replay") FString GetStateJson() const;
    UFUNCTION(BlueprintPure,Category="Warehouse Replay") FString GetRestorationReport() const;
    UFUNCTION(BlueprintPure,Category="Warehouse Replay") FBox GetWorkAreaBounds() const {return WorkAreaBounds;}
    bool IsExitPending() const {return Exit.Pending();}
    bool IsPreparing() const {return bPreparing;}
    const FString& GetFollowId() const {return FollowId;}
    AGHSOrderReplayActor* GetReplayActor() const {return Replay;}
    const FString& GetSelectedId() const {return SelectedId;}
private:
    struct FComponentState {TWeakObjectPtr<UActorComponent> Component;bool Tick=false;};
    struct FActorState {TWeakObjectPtr<AActor> Actor;bool Hidden=false,Tick=false;TArray<FComponentState> Components;};
    struct FInstanceState {TWeakObjectPtr<UInstancedStaticMeshComponent> Component;int32 Index=0;FTransform Transform;};
    struct FMeshState {TWeakObjectPtr<UStaticMeshComponent> Component;TWeakObjectPtr<UStaticMesh> Mesh;uint8 Mobility=0;};
    void CaptureAndIsolate();
    void Restore();
    bool HideSourceInstances();
    bool LoadParkingAlternates();
    UPROPERTY(Transient) TObjectPtr<AGHSOrderReplayActor> Replay;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMesh>> ParkingAlternates;
    TArray<FActorState> Originals;
    TArray<FInstanceState> Instances;
    TArray<FMeshState> Meshes;
    FGHSReplayClock Clock;
    FGHSReplayExitGuard Exit;
    FGHSCameraReplayPose CameraPose;
    FGHSWarehouseRoofReplayState RoofTransition;
    bool bSavedBuilding=true,bActive=false,bPreparing=false,bCaptured=false;
    FString OrderId,StartUtc,EndUtc,SelectedId,FollowId,TrailMode=TEXT("all"),Error,ExitTitle,ExitLabel;
    int32 RestoredActors=0,RestoredComponents=0,RestoredInstances=0,RestoredMeshes=0;
    bool bRestoreVerified=true;
    mutable TArray<TSharedPtr<FJsonValue>> CachedMarkers;
    double EventWindowStart=-1,EventWindowEnd=-1;
    uint64 EventWindowRevision=0;
    FBox WorkAreaBounds=FBox(ForceInit);
};
