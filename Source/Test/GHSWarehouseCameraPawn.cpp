#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehousePlayerController.h"
#include "Camera/CameraComponent.h"

namespace
{
    bool Finite(FVector2D V) { return FMath::IsFinite(V.X) && FMath::IsFinite(V.Y); }
    bool Finite(FVector V) { return FMath::IsFinite(V.X) && FMath::IsFinite(V.Y) && FMath::IsFinite(V.Z); }
    bool Finite(FRotator R) { return FMath::IsFinite(R.Pitch) && FMath::IsFinite(R.Yaw) && FMath::IsFinite(R.Roll); }
    float FlightEase(float T) { T=FMath::Clamp(T,0.f,1.f); return T*T*T*(10.f+T*(-15.f+6.f*T)); }
}

AGHSWarehouseCameraPawn::AGHSWarehouseCameraPawn()
{
    WarehouseCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("WarehouseCamera"));
    WarehouseCamera->SetupAttachment(SpringArmComponent, USpringArmComponent::SocketName);
    WarehouseCamera->FieldOfView = 56.0f;
    WarehouseCamera->bConstrainAspectRatio = false;
    WarehouseCamera->bOverrideAspectRatioAxisConstraint = true;
    WarehouseCamera->AspectRatioAxisConstraint = EAspectRatioAxisConstraint::AspectRatio_MaintainXFOV;
    WarehouseCamera->PostProcessBlendWeight = 0.0f;
    SpringArmComponent->TargetArmLength = OverviewDistance;
    SpringArmComponent->bDoCollisionTest = false;
    SpringArmComponent->bEnableCameraLag = false;
    SpringArmComponent->bEnableCameraRotationLag = false;
    EnabledFeatures = Movement | Rotation | Zoom | LagMovement | LagRotation | LagZoom;
    DrawDebugSpheres = false;
    DebugPrintDesiredPosition = false;
    ConstrainPitch = true; MinimumPitch = -80.0f; MaximumPitch = -15.0f;
    ConstrainYaw = false;
    ConstrainRoll = true; MinimumRoll = MaximumRoll = 0.0f;
    ConstrainZoomMinimum = ConstrainZoomMaximum = true;
    MinimumZoom = 900.0f; MaximumZoom = 95000.0f;
    OffsetConstrainType = NoConstrain;
    UseAlternativeForwardVector = UseAlternativeRightVector = true;
    RotationLagSpeed = 16.0f;
    MovementLagSpeed = 18.0f;
    ZoomLagSpeed = 12.0f;
    ConfigureGroundRestrictions();
    PrimaryActorTick.bTickEvenWhenPaused = false;
    SetActorEnableCollision(false);
}

void AGHSWarehouseCameraPawn::ConfigureGroundRestrictions()
{
    // Use the plugin's restrictions, including for calls from other Blueprints.
    LocationConstrainType = ELocationConstrainType::Raw;
    ConstrainLocationMinimum.X = ConstrainLocationMinimum.Y = ConstrainLocationMinimum.Z = true;
    ConstrainLocationMaximum.X = ConstrainLocationMaximum.Y = ConstrainLocationMaximum.Z = true;
    MinimumLocation = FVector(OverviewCenter.X - MaximumPan.X, OverviewCenter.Y - MaximumPan.Y, 0);
    MaximumLocation = FVector(OverviewCenter.X + MaximumPan.X, OverviewCenter.Y + MaximumPan.Y, 0);
    if(bGroundPanRecovery)
    {
        // An exterior object's ground-projected pivot may start outside the
        // normal warehouse rectangle. Admit only that finite starting position,
        // and ratchet each exceeded boundary inward as the camera returns.
        const FVector Current=GetActorLocation();
        GroundRecoveryMinimum.X=FMath::Min(MinimumLocation.X,FMath::Max(GroundRecoveryMinimum.X,Current.X));
        GroundRecoveryMinimum.Y=FMath::Min(MinimumLocation.Y,FMath::Max(GroundRecoveryMinimum.Y,Current.Y));
        GroundRecoveryMaximum.X=FMath::Max(MaximumLocation.X,FMath::Min(GroundRecoveryMaximum.X,Current.X));
        GroundRecoveryMaximum.Y=FMath::Max(MaximumLocation.Y,FMath::Min(GroundRecoveryMaximum.Y,Current.Y));
        MinimumLocation=GroundRecoveryMinimum; MaximumLocation=GroundRecoveryMaximum;
    }
}

void AGHSWarehouseCameraPawn::ConfigureObjectRestrictions()
{
    ConfigureGroundRestrictions();
    // The selected bounds center can be above the floor, and may lie outside
    // the free-navigation boundary (e.g. a copied vehicle or an exterior dock).
    ConstrainLocationMinimum.X = ConstrainLocationMinimum.Y = ConstrainLocationMinimum.Z = false;
    ConstrainLocationMaximum.X = ConstrainLocationMaximum.Y = ConstrainLocationMaximum.Z = false;
}

void AGHSWarehouseCameraPawn::ApplyPose(FVector Pivot,FRotator Rotation,float Distance,FVector SocketOffset,FVector TargetOffset)
{
    Rotation.Roll=0;
    // Set the plugin's actual and desired poses together. Its independent lag
    // stages must not apply a second, frame-rate dependent ease to a flight.
    DesiredLocation=Pivot; DesiredRotation=Rotation; DesiredZoom=Distance;
    DesiredSocketOffset=SocketOffset; DesiredTargetOffset=TargetOffset;
    SetActorLocation(Pivot); SetActorRotation(Rotation);
    SpringArmComponent->TargetArmLength=Distance;
    SpringArmComponent->SocketOffset=SocketOffset;
    SpringArmComponent->TargetOffset=TargetOffset;
}

void AGHSWarehouseCameraPawn::FocusOnTarget(FVector TargetCenter,float Distance,FRotator Rotation,
    FVector2D ViewportSize,FVector2D SceneCenterPixels,float Duration)
{
    TransitionToPose(TargetCenter,Distance,Rotation,ViewportSize,SceneCenterPixels,false,Duration);
}

FGHSCameraReplayPose AGHSWarehouseCameraPawn::CaptureReplayPose() const
{
    return {GetActorLocation(),SpringArmComponent->SocketOffset,SpringArmComponent->TargetOffset,
        FocusTarget,FramingOffsetRatio,GetActorRotation(),SpringArmComponent->TargetArmLength,
        bObjectPivot,bUseSceneFraming,bOverviewFraming,bGroundPanRecovery,GroundRecoveryMinimum,GroundRecoveryMaximum};
}
void AGHSWarehouseCameraPawn::RestoreReplayPose(const FGHSCameraReplayPose& Pose)
{
    bReplayFollowing=false;
    CancelPoseTransition();
    bObjectPivot=Pose.ObjectPivot;bUseSceneFraming=Pose.UseFraming;bOverviewFraming=Pose.OverviewFraming;
    FramingOffsetRatio=Pose.FramingRatio;FocusTarget=Pose.FocusTarget;bGroundPanRecovery=Pose.GroundPanRecovery;
    GroundRecoveryMinimum=Pose.RecoveryMinimum;GroundRecoveryMaximum=Pose.RecoveryMaximum;
    ApplyPose(Pose.Pivot,Pose.Rotation,Pose.Distance,Pose.SocketOffset,Pose.TargetOffset);
    if(bObjectPivot) ConfigureObjectRestrictions();else ConfigureGroundRestrictions();
}
void AGHSWarehouseCameraPawn::SetReplayFollowEnabled(bool bEnabled)
{
    bReplayFollowing=bEnabled;
    if(bEnabled && IsPreciseMouseDragging) TogglePreciseMouseDrag(false);
}
void AGHSWarehouseCameraPawn::FollowReplayTarget(FVector Location,float DeltaSeconds)
{
    if(!Finite(Location) || !FMath::IsFinite(DeltaSeconds) || DeltaSeconds<0) return;
    bReplayFollowing=true;FocusTarget=Location;
    // The target may move during the entry flight. Keep its final pivot current.
    if(bPoseTransitionActive) {FlightEndPivot=Location;return;}
    const FVector Pivot=FMath::VInterpTo(GetActorLocation(),Location,DeltaSeconds,5.f);
    bObjectPivot=true;ConfigureObjectRestrictions();
    // Do not ApplyPose here: that would overwrite unfinished user orbit/zoom lag.
    DesiredLocation=Pivot;SetActorLocation(Pivot);
}
void AGHSWarehouseCameraPawn::UpdateReplayViewport(FVector2D ViewportSize,FVector2D SceneCenterPixels)
{
    if(!Finite(ViewportSize) || !Finite(SceneCenterPixels) || ViewportSize.X<=0 || ViewportSize.Y<=0) return;
    const double Units=2*FMath::Tan(FMath::DegreesToRadians(WarehouseCamera->FieldOfView*.5))/ViewportSize.X;
    const FVector Ratio(0,(ViewportSize.X*.5-SceneCenterPixels.X)*Units,(SceneCenterPixels.Y-ViewportSize.Y*.5)*Units);
    bUseSceneFraming=true;
    if(bPoseTransitionActive) FlightEndOffsetRatio=Ratio;
    else {FramingOffsetRatio=Ratio;UpdateFraming();}
}
float AGHSWarehouseCameraPawn::CalculateFramingDistance(const FBox& Bounds,FRotator Rotation,float FieldOfView,
    FVector2D ViewportSize,const FBox2D& SceneBounds)
{
    if(!Bounds.IsValid || !SceneBounds.bIsValid || !Finite(ViewportSize) || ViewportSize.X<=0 || ViewportSize.Y<=0 ||
        !FMath::IsFinite(FieldOfView) || FieldOfView<=1 || FieldOfView>=179 || !Finite(Rotation)) return 0;
    const FVector2D Size=SceneBounds.GetSize(),Center=SceneBounds.GetCenter();
    if(Size.X<=0 || Size.Y<=0) return 0;
    const double K=ViewportSize.X/(2*FMath::Tan(FMath::DegreesToRadians(FieldOfView*.5)));
    const double HalfX=Size.X/(2*K),HalfY=Size.Y/(2*K);
    const double CenterX=(Center.X-ViewportSize.X*.5)/K,CenterY=(ViewportSize.Y*.5-Center.Y)/K;
    const FRotationMatrix Basis(Rotation);double Distance=900;
    for(int32 I=0;I<8;++I)
    {
        const FVector Corner(I&1?Bounds.Max.X:Bounds.Min.X,I&2?Bounds.Max.Y:Bounds.Min.Y,I&4?Bounds.Max.Z:Bounds.Min.Z);
        const FVector Q=Basis.GetTransposed().TransformVector(Corner-Bounds.GetCenter());
        // Perspective fit includes the off-axis framing shift for the panel/timeline.
        Distance=FMath::Max(Distance,FMath::Max(FMath::Abs(Q.Y-CenterX*Q.X)/HalfX-Q.X,
            FMath::Abs(Q.Z-CenterY*Q.X)/HalfY-Q.X));
    }
    return float(Distance*1.04);
}

void AGHSWarehouseCameraPawn::TransitionToPose(FVector Pivot,float Distance,FRotator Rotation,
    FVector2D ViewportSize,FVector2D SceneCenterPixels,bool bGroundMode,float Duration)
{
    if(!Finite(Pivot) || !Finite(Rotation) || !FMath::IsFinite(Distance) || !FMath::IsFinite(Duration)
        || !Finite(ViewportSize) || !Finite(SceneCenterPixels) || ViewportSize.X<=0 || ViewportSize.Y<=0) return;
    CancelPoseTransition();
    bReplayFollowing=false;
    bOverviewFraming=false;
    if(IsPreciseMouseDragging) TogglePreciseMouseDrag(false);
    FlightStartPivot=GetActorLocation(); FlightStartRotation=GetActorRotation();
    FlightStartDistance=SpringArmComponent->TargetArmLength;
    FlightStartOffsetRatio=SpringArmComponent->SocketOffset/FMath::Max(1.f,FlightStartDistance);
    FlightStartTargetOffset=SpringArmComponent->TargetOffset;
    if(bGroundMode) Pivot.Z=0;
    FlightEndPivot=Pivot; FocusTarget=Pivot;
    Rotation.Pitch=FMath::Clamp(Rotation.Pitch,double(MinimumPitch),double(MaximumPitch));
    Rotation.Roll=0;
    Rotation.Yaw=FlightStartRotation.Yaw+FMath::FindDeltaAngleDegrees(FlightStartRotation.Yaw,Rotation.Yaw);
    FlightEndRotation=Rotation;
    FlightEndDistance=FMath::Clamp(Distance,MinimumZoom,MaximumZoom);
    const double UnitsPerDistance=2*FMath::Tan(FMath::DegreesToRadians(WarehouseCamera->FieldOfView*.5))/ViewportSize.X;
    // Camera-local Y is screen right and Z is screen up. Moving the camera
    // opposite to the target's desired screen displacement preserves the real
    // object pivot while positioning it within the unobscured scene rectangle.
    FlightEndOffsetRatio=FVector(0,(ViewportSize.X*.5-SceneCenterPixels.X)*UnitsPerDistance,
        (SceneCenterPixels.Y-ViewportSize.Y*.5)*UnitsPerDistance);
    FramingOffsetRatio=FlightStartOffsetRatio;
    bUseSceneFraming=true; bObjectPivot=!bGroundMode; bFlightEndsOnGround=bGroundMode;
    bGroundPanRecovery=false;
    ConfigureObjectRestrictions(); // Allow an elevated starting pose while returning to the ground.
    FlightDuration=Duration<=0?0:FMath::Clamp(Duration,.7f,1.f); FlightElapsed=0;
    bPoseTransitionActive=FlightDuration>0;
    if(!bPoseTransitionActive)
    {
        FramingOffsetRatio=FlightEndOffsetRatio;
        ApplyPose(FlightEndPivot,FlightEndRotation,FlightEndDistance,FramingOffsetRatio*FlightEndDistance,FVector::ZeroVector);
        if(bFlightEndsOnGround) ConfigureGroundRestrictions();
    }
}

void AGHSWarehouseCameraPawn::CancelPoseTransition()
{
    if(!bPoseTransitionActive) return;
    bPoseTransitionActive=false;
    const float Distance=SpringArmComponent->TargetArmLength;
    FramingOffsetRatio=SpringArmComponent->SocketOffset/FMath::Max(1.f,Distance);
    ApplyPose(GetActorLocation(),GetActorRotation(),Distance,SpringArmComponent->SocketOffset,SpringArmComponent->TargetOffset);
    // An interrupted ground flight can still have an elevated pivot. Keep
    // it there until an explicit ground-pan conversion or a completed flight.
    bObjectPivot=!FMath::IsNearlyZero(GetActorLocation().Z,.01) || bObjectPivot;
    if(bObjectPivot) ConfigureObjectRestrictions(); else ConfigureGroundRestrictions();
}

void AGHSWarehouseCameraPawn::PrepareForGroundPan()
{
    if(bReplayFollowing) return;
    bOverviewFraming=false;
    CancelPoseTransition();
    if(!bObjectPivot) return;
    const FRotator Rotation=GetActorRotation();
    const float Distance=SpringArmComponent->TargetArmLength;
    const FVector Ratio=SpringArmComponent->SocketOffset/FMath::Max(1.f,Distance);
    const FVector CameraVector=Rotation.RotateVector(Ratio-FVector::ForwardVector);
    const FVector CameraPosition=GetActorLocation()+SpringArmComponent->TargetOffset+CameraVector*Distance;
    if(CameraVector.Z<=SMALL_NUMBER || CameraPosition.Z<=0) return;
    // Keep the exact view and its framing while extending the view ray until
    // its pivot intersects the ground. Starting RMB must not drop the camera.
    const float GroundDistance=CameraPosition.Z/CameraVector.Z;
    FVector GroundPivot=CameraPosition-CameraVector*GroundDistance; GroundPivot.Z=0;
    FramingOffsetRatio=Ratio;
    ApplyPose(GroundPivot,Rotation,GroundDistance,Ratio*GroundDistance,FVector::ZeroVector);
    bObjectPivot=false; FocusTarget=GroundPivot;
    GroundRecoveryMinimum=FVector(FMath::Min(OverviewCenter.X-MaximumPan.X,GroundPivot.X),
        FMath::Min(OverviewCenter.Y-MaximumPan.Y,GroundPivot.Y),0);
    GroundRecoveryMaximum=FVector(FMath::Max(OverviewCenter.X+MaximumPan.X,GroundPivot.X),
        FMath::Max(OverviewCenter.Y+MaximumPan.Y,GroundPivot.Y),0);
    bGroundPanRecovery=true;
    ConfigureGroundRestrictions();
}

void AGHSWarehouseCameraPawn::FreezeCurrentPose()
{
    CancelPoseTransition();
    const float Distance=SpringArmComponent->TargetArmLength;
    FramingOffsetRatio=SpringArmComponent->SocketOffset/FMath::Max(1.f,Distance);
    ApplyPose(GetActorLocation(),GetActorRotation(),Distance,SpringArmComponent->SocketOffset,SpringArmComponent->TargetOffset);
    if(bGroundPanRecovery && !bObjectPivot) ConfigureGroundRestrictions();
}

void AGHSWarehouseCameraPawn::UpdateFraming()
{
    if(!bUseSceneFraming || bPoseTransitionActive) return;
    // The ratio follows actual arm length, so a wheel zoom does not slide the
    // selected model away from its panel-aware screen position during lag.
    DesiredSocketOffset=FramingOffsetRatio*DesiredZoom;
    SpringArmComponent->SocketOffset=FramingOffsetRatio*SpringArmComponent->TargetArmLength;
}

void AGHSWarehouseCameraPawn::BeginPlay()
{
    Super::BeginPlay();
    ResetOverview(true);
}

void AGHSWarehouseCameraPawn::ResetOverview(bool Immediate)
{
    bReplayFollowing=false;
    CancelPoseTransition();
    bOverviewFraming=true;
    bObjectPivot=false; bUseSceneFraming=false; bGroundPanRecovery=false; FramingOffsetRatio=FVector::ZeroVector;
    FocusTarget=FVector(OverviewCenter.X,OverviewCenter.Y,0);
    ConfigureGroundRestrictions();
    // Zero offsets keep both the physical Pawn and the orbit center together.
    SetDesiredTargetOffset(FVector::ZeroVector, true, true);
    SetDesiredSocketOffset(FVector::ZeroVector, true, true);
    SetDesiredLocation(FVector(OverviewCenter.X, OverviewCenter.Y, 0), Immediate);
    SetDesiredYaw(OverviewYaw, Immediate);
    SetDesiredPitch(OverviewPitch, Immediate);
    SetDesiredRoll(0, Immediate);
    SetDesiredZoom(OverviewDistance, Immediate);
}

void AGHSWarehouseCameraPawn::FrameOverview(FVector2D ViewportSize,FVector2D ScenePosition,FVector2D SceneSize,float Duration)
{
    if(!Finite(ViewportSize) || !Finite(ScenePosition) || !Finite(SceneSize)
        || ViewportSize.X<=0 || ViewportSize.Y<=0 || SceneSize.X<=0 || SceneSize.Y<=0 || !FMath::IsFinite(Duration)) return;
    const float Distance=FMath::Min(MaximumZoom,float(OverviewDistance*ViewportSize.X/SceneSize.X));
    TransitionToPose(OverviewCenter,Distance,FRotator(OverviewPitch,OverviewYaw,0),ViewportSize,
        ScenePosition+SceneSize*.5,true,Duration);
    bOverviewFraming=true;
    UE_LOG(LogTemp,Display,TEXT("GHS_OVERVIEW_FRAME viewport=%s scene=%s+%s distance=%.1f duration=%.2f"),
        *ViewportSize.ToString(),*ScenePosition.ToString(),*SceneSize.ToString(),Distance,Duration);
}

void AGHSWarehouseCameraPawn::OrbitPixels(FVector2D Delta)
{
    if (!Finite(Delta)) return;
    if(Delta.IsNearlyZero()) return;
    bOverviewFraming=false;
    CancelPoseTransition();
    SetDesiredYaw(FRotator::NormalizeAxis(DesiredRotation.Yaw + Delta.X * OrbitDegreesPerPixel));
    // The plugin normalizes angles before constraining them. Clamp the pixel
    // delta's result first so a very large drag cannot wrap to the other limit.
    SetDesiredPitch(FMath::Clamp(DesiredRotation.Pitch - Delta.Y * PitchDegreesPerPixel,
        double(MinimumPitch), double(MaximumPitch)));
}

void AGHSWarehouseCameraPawn::PanPixels(FVector2D Delta, int32 ViewportWidth)
{
    if(bReplayFollowing) return;
    if (!Finite(Delta) || ViewportWidth <= 0) return;
    if(Delta.IsNearlyZero()) return;
    PrepareForGroundPan();
    const double UnitsPerPixel = 2.0 * DesiredZoom * FMath::Tan(FMath::DegreesToRadians(WarehouseCamera->FieldOfView * 0.5)) / ViewportWidth;
    const double PitchProjection = FMath::Max(0.2, -FMath::Sin(FMath::DegreesToRadians(DesiredRotation.Pitch)));
    // Convert screen pixels to a ground-plane displacement, then let the plugin
    // move/limit/ease the actual Pawn. Mouse samples must not be multiplied by dt.
    const FVector Displacement = -GetAlternativeRightVector(DesiredRotation) * Delta.X * UnitsPerPixel
        + GetAlternativeForwardVector(DesiredRotation) * Delta.Y * UnitsPerPixel / PitchProjection;
    const FVector Destination = DesiredLocation + Displacement;
    ConfigureGroundRestrictions();
    SetDesiredLocation(FVector(Destination.X, Destination.Y, 0));
}

void AGHSWarehouseCameraPawn::ZoomSteps(float Steps)
{
    if (!FMath::IsFinite(Steps)) return;
    if(FMath::IsNearlyZero(Steps)) return;
    bOverviewFraming=false;
    CancelPoseTransition();
    const double Exponent = FMath::Clamp(-double(Steps) * WheelZoomExponent, -80.0, 80.0);
    // Clamp before converting to float; the plugin applies its zoom limits too.
    const double Distance = FMath::Clamp(double(DesiredZoom) * FMath::Exp(Exponent), double(MinimumZoom), double(MaximumZoom));
    SetDesiredZoom(float(Distance));
}

bool AGHSWarehouseCameraPawn::ShouldAggregateTruckHUD() const
{
    // The plugin eases TargetArmLength toward DesiredZoom. Follow the camera's
    // current arm length so HUDs change mode when the view reaches the threshold.
    return SpringArmComponent && SpringArmComponent->TargetArmLength >= FMath::Max(0.f, HUDClusterMinArmLength);
}

void AGHSWarehouseCameraPawn::Tick(float DeltaSeconds)
{
    if (!FMath::IsFinite(DeltaSeconds) || DeltaSeconds <= SMALL_NUMBER) return;
    if(bGroundPanRecovery && !bObjectPivot && !bPoseTransitionActive) ConfigureGroundRestrictions();
    if(bPoseTransitionActive)
    {
        FlightElapsed=FMath::Min(FlightElapsed+DeltaSeconds,FlightDuration);
        const float Alpha=FlightEase(FlightElapsed/FlightDuration);
        FramingOffsetRatio=FMath::Lerp(FlightStartOffsetRatio,FlightEndOffsetRatio,Alpha);
        const FVector Pivot=FMath::Lerp(FlightStartPivot,FlightEndPivot,Alpha);
        const FRotator Rotation(FMath::Lerp(FlightStartRotation.Pitch,FlightEndRotation.Pitch,Alpha),
            FMath::Lerp(FlightStartRotation.Yaw,FlightEndRotation.Yaw,Alpha),0);
        const float Distance=FMath::Lerp(FlightStartDistance,FlightEndDistance,Alpha);
        ApplyPose(Pivot,Rotation,Distance,FramingOffsetRatio*Distance,FMath::Lerp(FlightStartTargetOffset,FVector::ZeroVector,Alpha));
        if(FlightElapsed>=FlightDuration)
        {
            bPoseTransitionActive=false;
            if(bFlightEndsOnGround) ConfigureGroundRestrictions();
        }
    }
    if (IsPreciseMouseDragging)
    {
        auto* WarehouseController = Cast<AGHSWarehousePlayerController>(GetController());
        if (!WarehouseController) TogglePreciseMouseDrag(false);
        else if (!WarehouseController->HasValidMapDragCursor()) WarehouseController->CancelCameraDrag();
    }
    // The plugin divides by its previous frame time even in a disposable
    // automation world whose clock is stationary.
    if(LastDeltaTime<=SMALL_NUMBER) LastDeltaTime=DeltaSeconds;
    Super::Tick(DeltaSeconds);
    UpdateFraming();
}

FRotator AGHSWarehouseCameraPawn::Lag_GetTickDesiredRotation_Implementation(float DeltaTime)
{
    // Reuse the plugin's native interpolation. Its quaternion path can bank
    // while yaw and pitch change together; keep a level warehouse horizon.
    FRotator Rotation = Super::Lag_GetTickDesiredRotation_Implementation(DeltaTime);
    Rotation.Roll = 0;
    return Rotation;
}
