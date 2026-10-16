#include "GHSWarehouseCameraPawn.h"
#include "Camera/CameraComponent.h"

namespace
{
    bool Finite(FVector2D V) { return FMath::IsFinite(V.X) && FMath::IsFinite(V.Y); }
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
}

void AGHSWarehouseCameraPawn::BeginPlay()
{
    Super::BeginPlay();
    ResetOverview(true);
}

void AGHSWarehouseCameraPawn::ResetOverview(bool Immediate)
{
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

void AGHSWarehouseCameraPawn::OrbitPixels(FVector2D Delta)
{
    if (!Finite(Delta)) return;
    SetDesiredYaw(FRotator::NormalizeAxis(DesiredRotation.Yaw + Delta.X * OrbitDegreesPerPixel));
    // The plugin normalizes angles before constraining them. Clamp the pixel
    // delta's result first so a very large drag cannot wrap to the other limit.
    SetDesiredPitch(FMath::Clamp(DesiredRotation.Pitch - Delta.Y * PitchDegreesPerPixel,
        double(MinimumPitch), double(MaximumPitch)));
}

void AGHSWarehouseCameraPawn::PanPixels(FVector2D Delta, int32 ViewportWidth)
{
    if (!Finite(Delta) || ViewportWidth <= 0) return;
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
    const double Exponent = FMath::Clamp(-double(Steps) * WheelZoomExponent, -80.0, 80.0);
    // Clamp before converting to float; the plugin applies its zoom limits too.
    const double Distance = FMath::Clamp(double(DesiredZoom) * FMath::Exp(Exponent), double(MinimumZoom), double(MaximumZoom));
    SetDesiredZoom(float(Distance));
}

void AGHSWarehouseCameraPawn::Tick(float DeltaSeconds)
{
    if (DeltaSeconds <= SMALL_NUMBER) return;
    Super::Tick(DeltaSeconds);
}

FRotator AGHSWarehouseCameraPawn::Lag_GetTickDesiredRotation_Implementation(float DeltaTime)
{
    // Reuse the plugin's native interpolation. Its quaternion path can bank
    // while yaw and pitch change together; keep a level warehouse horizon.
    FRotator Rotation = Super::Lag_GetTickDesiredRotation_Implementation(DeltaTime);
    Rotation.Roll = 0;
    return Rotation;
}
