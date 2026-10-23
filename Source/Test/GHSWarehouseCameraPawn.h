#pragma once

#include "CoreMinimal.h"
#include "UniversalCamera.h"
#include "GHSWarehouseCameraPawn.generated.h"

struct FGHSCameraReplayPose
{
    FVector Pivot,SocketOffset,TargetOffset,FocusTarget,FramingRatio;
    FRotator Rotation;
    float Distance=0;
    bool ObjectPivot=false,UseFraming=false,OverviewFraming=false;
    bool GroundPanRecovery=false;
    FVector RecoveryMinimum=FVector::ZeroVector,RecoveryMaximum=FVector::ZeroVector;
};

/** Ground navigation plus explicit object-centered camera flights for the twin HUD. */
UCLASS(Blueprintable)
class TEST_API AGHSWarehouseCameraPawn : public AUniversalCamera
{
    GENERATED_BODY()
public:
    AGHSWarehouseCameraPawn();
    virtual void Tick(float DeltaSeconds) override;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Warehouse Camera")
    TObjectPtr<UCameraComponent> WarehouseCamera;

    /** Current spring-arm lengths below this value show individual truck HUDs. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera",
        meta=(ClampMin="0", UIMin="0", Units="cm", DisplayName="HUD 聚合最小臂长",
            ToolTip="当前弹簧臂长度低于此值时，装卸车与电动堆高车 HUD 不聚合；达到或超过时使用四等分聚合。0 表示始终允许聚合。"))
    float HUDClusterMinArmLength = 10000.0f;

    UFUNCTION(BlueprintPure, Category="Warehouse Camera")
    bool ShouldAggregateTruckHUD() const;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview")
    FVector OverviewCenter = FVector(-646.665, 833.981, 0.0);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview", meta=(ClampMin="900"))
    float OverviewDistance = 53500.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview")
    float OverviewPitch = -30.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview")
    float OverviewYaw = -90.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0.01", ClampMax="1"))
    float OrbitDegreesPerPixel = 0.18f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0.01", ClampMax="1"))
    float PitchDegreesPerPixel = 0.14f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0.01", ClampMax="0.5"))
    float WheelZoomExponent = 0.12f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0"))
    float MinimumCameraHeight = 150.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="100"))
    FVector2D MaximumPan = FVector2D(30000.0, 15000.0);

    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void ResetOverview(bool Immediate = false);
    /** The overview may be reframed when the real viewport replaces the startup window size. */
    void FrameOverview(FVector2D ViewportSize, FVector2D ScenePosition, FVector2D SceneSize, float Duration = 0.85f);
    bool IsOverviewFraming() const { return bOverviewFraming; }
    /** Delta is measured in screen pixels, positive Y down. Do not multiply by time. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void OrbitPixels(FVector2D Delta);
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void PanPixels(FVector2D Delta, int32 ViewportWidth);
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void ZoomSteps(float Steps);

    /** Orbit the actual 3D model center; panel framing is a separate camera-local offset. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera|Focus")
    void FocusOnTarget(FVector TargetCenter, float Distance, FRotator Rotation,
        FVector2D ViewportSize, FVector2D SceneCenterPixels, float Duration = 0.85f);
    /** One ease clock for pivot, rotation, distance and framing. Duration 0 applies immediately. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera|Focus")
    void TransitionToPose(FVector Pivot, float Distance, FRotator Rotation,
        FVector2D ViewportSize, FVector2D SceneCenterPixels, bool bGroundMode = true, float Duration = 0.85f);
    /** Freeze at the actual current pose, never at an unfinished desired destination. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera|Focus")
    void CancelPoseTransition();
    /** Convert a 3D object orbit into ground navigation without moving the rendered camera. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera|Focus")
    void PrepareForGroundPan();
    /** Stop manual-navigation lag at the actual view without applying destination clamps. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera|Focus")
    void FreezeCurrentPose();
    UFUNCTION(BlueprintPure, Category="Warehouse Camera|Focus")
    bool IsPoseTransitionActive() const { return bPoseTransitionActive; }
    UFUNCTION(BlueprintPure, Category="Warehouse Camera|Focus")
    bool UsesObjectPivot() const { return bObjectPivot; }
    UFUNCTION(BlueprintPure, Category="Warehouse Camera|Focus")
    FVector GetFocusTarget() const { return FocusTarget; }
    FGHSCameraReplayPose CaptureReplayPose() const;
    void RestoreReplayPose(const FGHSCameraReplayPose& Pose);
    /** Tracking moves only the pivot; orbit and zoom retain their own input/lag targets. */
    void FollowReplayTarget(FVector Location, float DeltaSeconds);
    void UpdateReplayViewport(FVector2D ViewportSize,FVector2D SceneCenterPixels);
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera|Replay")
    void SetReplayFollowEnabled(bool bEnabled);
    UFUNCTION(BlueprintPure, Category="Warehouse Camera|Replay")
    bool IsReplayFollowing() const {return bReplayFollowing;}
    static float CalculateFramingDistance(const FBox& Bounds,FRotator Rotation,float FieldOfView,
        FVector2D ViewportSize,const FBox2D& SceneBounds);

protected:
    virtual void BeginPlay() override;
    virtual FRotator Lag_GetTickDesiredRotation_Implementation(float DeltaTime) override;
private:
    void ConfigureGroundRestrictions();
    void ConfigureObjectRestrictions();
    void ApplyPose(FVector Pivot, FRotator Rotation, float Distance, FVector SocketOffset, FVector TargetOffset);
    void UpdateFraming();
    bool bPoseTransitionActive = false;
    bool bObjectPivot = false;
    bool bUseSceneFraming = false;
    bool bOverviewFraming = false;
    bool bGroundPanRecovery = false;
    bool bReplayFollowing = false;
    FVector GroundRecoveryMinimum = FVector::ZeroVector, GroundRecoveryMaximum = FVector::ZeroVector;
    bool bFlightEndsOnGround = true;
    float FlightElapsed = 0, FlightDuration = 0;
    FVector FlightStartPivot, FlightEndPivot, FlightStartOffsetRatio, FlightEndOffsetRatio, FlightStartTargetOffset;
    FRotator FlightStartRotation, FlightEndRotation;
    float FlightStartDistance = 0, FlightEndDistance = 0;
    FVector FramingOffsetRatio = FVector::ZeroVector;
    FVector FocusTarget = FVector::ZeroVector;
};
