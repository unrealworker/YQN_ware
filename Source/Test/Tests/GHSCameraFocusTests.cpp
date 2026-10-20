#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseCameraPawn.h"
#include "Camera/CameraComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"

namespace GHSCameraFocusTests
{
    constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
    struct FFixture
    {
        UWorld* World = nullptr;
        AGHSWarehouseCameraPawn* Camera = nullptr;
        FFixture()
        {
            World = UWorld::CreateWorld(EWorldType::Game, false);
            if (!World || !GEngine) return;
            // Use the normal game-world initialization, without an editor or OS viewport.
            GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
            World->InitializeActorsForPlay(FURL());
            Camera = World->SpawnActor<AGHSWarehouseCameraPawn>();
            if (Camera) Camera->ResetOverview(true);
        }
        ~FFixture()
        {
            if (!World) return;
            if (GEngine) GEngine->DestroyWorldContext(World);
            World->DestroyWorld(false);
        }
        void Tick(float Seconds)
        {
            Camera->LastDeltaTime = Seconds;
            Camera->Tick(Seconds);
            Camera->SpringArmComponent->TickComponent(Seconds, LEVELTICK_All, nullptr);
        }
        void Settle()
        {
            for (int I = 0; I < 180; ++I) Tick(1.f / 60.f);
        }
        FVector CameraPosition() const
        {
            return Camera->GetActorLocation() + Camera->SpringArmComponent->TargetOffset
                + Camera->GetActorRotation().RotateVector(Camera->SpringArmComponent->SocketOffset
                    - FVector(Camera->SpringArmComponent->TargetArmLength, 0, 0));
        }
        FVector2D Project(FVector Point, FVector2D Size) const
        {
            const FVector Relative = Camera->WarehouseCamera->GetComponentRotation().UnrotateVector(
                Point-Camera->WarehouseCamera->GetComponentLocation());
            const double FocalLength = Size.X / (2. * FMath::Tan(FMath::DegreesToRadians(Camera->WarehouseCamera->FieldOfView * .5)));
            return FVector2D(Size.X * .5 + Relative.Y * FocalLength / Relative.X,
                Size.Y * .5 - Relative.Z * FocalLength / Relative.X);
        }
    };
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSCameraModelPivot,
    "GHS.WarehouseCamera.Focus.ModelCenterAndFramingSurviveOrbitAndZoom", GHSCameraFocusTests::Flags)
bool FGHSCameraModelPivot::RunTest(const FString&)
{
    using namespace GHSCameraFocusTests;
    FFixture F;
    if (!TestNotNull(TEXT("Camera fixture"), F.Camera)) return false;
    const FVector Target(1200, -3400, 420);
    for (const FVector2D Size : {FVector2D(1920,1080), FVector2D(600,900)})
    {
        const FVector2D Centre = Size.X > 900 ? FVector2D(720,572) : FVector2D(300,242);
        F.Camera->FocusOnTarget(Target, 3200, FRotator(-40,95,0), Size, Centre);
        F.Settle();
        TestTrue(TEXT("Elevated model center is the physical orbit pivot"), F.Camera->GetActorLocation().Equals(Target,.01));
        TestTrue(TEXT("Model center lands on usable scene center"), F.Project(Target,Size).Equals(Centre,.5));
        F.Camera->OrbitPixels(FVector2D(280,-70));
        F.Settle();
        TestTrue(TEXT("Orbit keeps the actual model center"), F.Camera->GetActorLocation().Equals(Target,.01));
        TestTrue(TEXT("Orbit does not shift projected model center"), F.Project(Target,Size).Equals(Centre,.5));
        F.Camera->ZoomSteps(4);
        F.Settle();
        TestTrue(TEXT("Zoom keeps model center at scene center"), F.Project(Target,Size).Equals(Centre,.5));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSCameraPoseEase,
    "GHS.WarehouseCamera.Focus.UnifiedEaseAndInterruption", GHSCameraFocusTests::Flags)
bool FGHSCameraPoseEase::RunTest(const FString&)
{
    using namespace GHSCameraFocusTests;
    FFixture F;
    if (!TestNotNull(TEXT("Camera fixture"), F.Camera)) return false;
    const FVector Start = F.Camera->GetActorLocation(), Target(5000,-2000,600);
    const FVector CameraStart = F.CameraPosition();
    F.Camera->FocusOnTarget(Target, 2600, FRotator(-55,170,0), FVector2D(1920,1080), FVector2D(720,572), 1.f);
    TestTrue(TEXT("Starting a transition does not teleport the camera"), F.CameraPosition().Equals(CameraStart,.001));
    F.Tick(.05f);
    const double FirstTravel = (F.Camera->GetActorLocation()-Start).Length();
    TestTrue(TEXT("Transition starts with low velocity"), FirstTravel < (Target-Start).Length()*.005);
    for (int I=0; I<9; ++I) F.Tick(.05f);
    TestTrue(TEXT("Pivot reaches halfway at the shared ease midpoint"), F.Camera->GetActorLocation().Equals((Start+Target)*.5,.1));
    TestTrue(TEXT("Zoom shares the same transition clock"), FMath::IsNearlyEqual(F.Camera->SpringArmComponent->TargetArmLength,(F.Camera->OverviewDistance+2600)*.5f,.1f));
    for (int I=0; I<9; ++I) F.Tick(.05f);
    const FVector NearEnd=F.Camera->GetActorLocation();
    F.Tick(.05f);
    TestTrue(TEXT("Transition ends with low velocity"),(F.Camera->GetActorLocation()-NearEnd).Length()<(Target-Start).Length()*.005);
    TestFalse(TEXT("All channels finish together at the specified duration"),F.Camera->IsPoseTransitionActive());
    TestTrue(TEXT("Flight arrives exactly at the model center"),F.Camera->GetActorLocation().Equals(Target,.01));
    F.Camera->FocusOnTarget(FVector(1000,1000,300),3200,FRotator(-40,-160,0),FVector2D(1920,1080),FVector2D(720,572));
    F.Tick(.2f);
    const FVector Interrupted = F.CameraPosition();
    F.Camera->FocusOnTarget(FVector(-2200,4000,200), 4000, FRotator(-35,-170,0), FVector2D(1920,1080), FVector2D(720,572));
    TestTrue(TEXT("Retarget begins at the current actual camera pose"), F.CameraPosition().Equals(Interrupted,.001));
    F.Tick(.15f);
    const FVector BeforeCancel = F.CameraPosition();
    F.Camera->CancelPoseTransition();
    TestFalse(TEXT("Cancel stops the shared transition"), F.Camera->IsPoseTransitionActive());
    TestTrue(TEXT("Cancel does not jump to a stale target"), F.CameraPosition().Equals(BeforeCancel,.001));
    const FVector CancelledPivot = F.Camera->GetActorLocation();
    F.Settle();
    TestTrue(TEXT("Cancelled flight does not resume in later ticks"), F.Camera->GetActorLocation().Equals(CancelledPivot,.001));
    F.Camera->FocusOnTarget(Target,2600,FRotator(-55,170,0),FVector2D(1920,1080),FVector2D(720,572));
    F.Tick(.2f);
    F.Camera->OrbitPixels(FVector2D(15,0));
    TestFalse(TEXT("User orbit interrupts automatic flight"), F.Camera->IsPoseTransitionActive());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSCameraGroundReturn,
    "GHS.WarehouseCamera.Focus.GroundPanAndLegacyResetPreserveContract", GHSCameraFocusTests::Flags)
bool FGHSCameraGroundReturn::RunTest(const FString&)
{
    using namespace GHSCameraFocusTests;
    FFixture F;
    if (!TestNotNull(TEXT("Camera fixture"), F.Camera)) return false;
    F.Camera->FocusOnTarget(FVector(1200,-3400,800),3200,FRotator(-40,95,0),FVector2D(600,900),FVector2D(300,242));
    F.Settle();
    const FVector Before = F.CameraPosition();
    F.Camera->PrepareForGroundPan();
    TestTrue(TEXT("Changing to ground pan preserves the visible camera position"), F.CameraPosition().Equals(Before,.05));
    TestTrue(TEXT("Map drag returns pivot to warehouse ground"), FMath::IsNearlyZero(F.Camera->GetActorLocation().Z,.01));
    TestFalse(TEXT("Ground drag exits object pivot mode"), F.Camera->UsesObjectPivot());
    F.Camera->PanPixels(FVector2D(10,5),600);
    F.Settle();
    TestTrue(TEXT("Ground pan still stays on the ground"), FMath::IsNearlyZero(F.Camera->GetActorLocation().Z,.01));
    F.Camera->ResetOverview(true);
    TestTrue(TEXT("Legacy overview position remains unchanged"), F.Camera->GetActorLocation().Equals(F.Camera->OverviewCenter,.01));
    TestTrue(TEXT("Legacy overview clears framing offset"), F.Camera->SpringArmComponent->SocketOffset.IsNearlyZero(.001));
    TestTrue(TEXT("Legacy target offset remains zero"), F.Camera->SpringArmComponent->TargetOffset.IsNearlyZero(.001));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSCameraExternalGroundReturn,
    "GHS.WarehouseCamera.Focus.ExternalTargetGroundDragCannotClampOrExpandOutwards", GHSCameraFocusTests::Flags)
bool FGHSCameraExternalGroundReturn::RunTest(const FString&)
{
    using namespace GHSCameraFocusTests;
    FFixture F;
    if (!TestNotNull(TEXT("Camera fixture"), F.Camera)) return false;
    const FVector2D Viewport(1920,1080), Center(960,540);
    F.Camera->FocusOnTarget(FVector(40000,0,800),3200,FRotator(-40,0,0),Viewport,Center,0);
    const FVector Before=F.CameraPosition();
    F.Camera->PrepareForGroundPan();
    F.Camera->FreezeCurrentPose();
    TestTrue(TEXT("Pressing RMB outside normal pan bounds preserves the camera"),F.CameraPosition().Equals(Before,.05));
    const FVector Ground=F.Camera->GetActorLocation();
    TestTrue(TEXT("Regression fixture lands outside the nominal X boundary"),Ground.X>F.Camera->OverviewCenter.X+F.Camera->MaximumPan.X+10000);
    // The precise-drag plugin calls this setter even for a zero cursor delta.
    F.Camera->SetDesiredLocation(Ground,true);
    F.Tick(1.f/60.f);
    TestTrue(TEXT("First zero-delta precise-drag tick does not snap to normal bounds"),F.Camera->GetActorLocation().Equals(Ground,.05));
    TestTrue(TEXT("Zero-delta tick preserves visible camera"),F.CameraPosition().Equals(Before,.05));
    F.Camera->SetDesiredLocation(Ground+FVector(1000,0,0),true);
    TestTrue(TEXT("Temporary recovery bounds prohibit further outward travel"),F.Camera->GetActorLocation().Equals(Ground,.05));
    const FVector Inward=Ground-FVector(1000,0,0);
    F.Camera->SetDesiredLocation(Inward,true);
    F.Tick(1.f/60.f);
    TestTrue(TEXT("Camera can move inward smoothly from an exterior target"),F.Camera->GetActorLocation().Equals(Inward,.05));
    F.Camera->SetDesiredLocation(Ground,true);
    TestTrue(TEXT("Recovery boundary tightens rather than reopening the exterior range"),F.Camera->GetActorLocation().Equals(Inward,.05));
    TestTrue(TEXT("Other axes retain normal bounded pan range"),FMath::IsNearlyEqual(F.Camera->MaximumLocation.Y,F.Camera->OverviewCenter.Y+F.Camera->MaximumPan.Y,.01));

    F.Camera->FocusOnTarget(FVector(0,0,12000),95000,FRotator(-15,0,0),Viewport,Center,0);
    const FVector HighBefore=F.CameraPosition();
    F.Camera->PrepareForGroundPan();
    TestTrue(TEXT("Ground conversion may require an arm longer than normal navigation"),F.Camera->SpringArmComponent->TargetArmLength>F.Camera->MaximumZoom);
    const float ExtendedZoom=F.Camera->SpringArmComponent->TargetArmLength;
    F.Camera->FreezeCurrentPose();
    F.Camera->SetDesiredLocation(F.Camera->GetActorLocation(),true);
    F.Tick(1.f/60.f);
    TestTrue(TEXT("Ground press and first tick do not clamp preserved arm length"),FMath::IsNearlyEqual(F.Camera->SpringArmComponent->TargetArmLength,ExtendedZoom,.1f));
    TestTrue(TEXT("High exterior target can begin ground drag without moving the view"),F.CameraPosition().Equals(HighBefore,.1));
    F.Camera->ResetOverview(true);
    TestTrue(TEXT("Reset restores the original pan boundary"),FMath::IsNearlyEqual(F.Camera->MaximumLocation.X,F.Camera->OverviewCenter.X+F.Camera->MaximumPan.X,.01));
    TestTrue(TEXT("Reset restores the original zoom"),FMath::IsNearlyEqual(F.Camera->SpringArmComponent->TargetArmLength,F.Camera->OverviewDistance,.01f));
    return true;
}
#endif
