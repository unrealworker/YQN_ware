#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseCameraPawn.h"
#include "../GHSWarehousePlayerController.h"
#include "../GHSTwinHUDWidget.h"
#include "Camera/CameraComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/PlayerInput.h"
#include "Misc/AutomationTest.h"

#include <limits>

namespace GHSWarehouseCameraTests
{
    constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
    constexpr float FrameSeconds = 1.0f / 60.0f;

    // A real disposable game World and possession, without a LocalPlayer or OS
    // viewport. This exercises input aggregation without changing an open map.
    struct FFixture
    {
        UWorld* World = nullptr;
        AGHSWarehouseCameraPawn* Pawn = nullptr;
        AGHSWarehousePlayerController* Controller = nullptr;

        FFixture()
        {
            World = UWorld::CreateWorld(EWorldType::Game, false);
            if (!World || !GEngine) return;
            GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
            World->InitializeActorsForPlay(FURL());

            FActorSpawnParameters Spawn;
            Spawn.ObjectFlags |= RF_Transient;
            Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            Pawn = World->SpawnActor<AGHSWarehouseCameraPawn>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
            Controller = World->SpawnActor<AGHSWarehousePlayerController>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
            if (Pawn && Controller)
            {
                // PlayerTick requires a UPlayerInput. No viewport, Enhanced Input
                // mappings, rendering, or external input devices are required.
                Controller->PlayerInput = NewObject<UPlayerInput>(Controller);
                Controller->Possess(Pawn);
                Pawn->ResetOverview(true);
            }
        }

        ~FFixture()
        {
            if (World)
            {
                if (Controller) Controller->UnPossess();
                if (GEngine) GEngine->DestroyWorldContext(World);
                World->DestroyWorld(false);
            }
        }

        bool Check(FAutomationTestBase& Test) const
        {
            if (!Test.TestNotNull(TEXT("Transient game world"), World)
                || !Test.TestNotNull(TEXT("Warehouse Pawn"), Pawn)
                || !Test.TestNotNull(TEXT("Warehouse Controller"), Controller)) return false;
            return Test.TestTrue(TEXT("Controller possesses actual warehouse Pawn"), Controller->GetPawn() == Pawn);
        }

        bool Key(FKey KeyName, EInputEvent Event, double Value = 1.0)
        {
            return Controller->InputKey(FInputKeyParams(KeyName, Event, Value));
        }

        void Mouse(double ScreenX, double ScreenY)
        {
            Controller->InputKey(FInputKeyParams(EKeys::MouseX, ScreenX, FrameSeconds, 1));
            Controller->InputKey(FInputKeyParams(EKeys::MouseY, -ScreenY, FrameSeconds, 1));
        }

        void InputFrame()
        {
            Controller->PlayerTick(FrameSeconds);
        }

        void CameraFrame()
        {
            // This fixture has no running World clock. Supply the plugin's
            // previous-frame time before exercising its real lag Tick.
            Pawn->LastDeltaTime = FrameSeconds;
            Pawn->Tick(FrameSeconds);
        }
    };

    bool Near(FAutomationTestBase& Test, const TCHAR* Label, double Actual, double Expected, double Tolerance = 0.001)
    {
        return Test.TestTrue(FString::Printf(TEXT("%s: actual %.9f, expected %.9f"), Label, Actual, Expected),
            FMath::IsFinite(Actual) && FMath::Abs(Actual - Expected) <= Tolerance);
    }

    struct FDesiredPose
    {
        FVector Location;
        FVector Offset;
        FVector TargetOffset;
        FRotator Rotation;
        float Distance;

        explicit FDesiredPose(const AGHSWarehouseCameraPawn& Pawn)
            : Location(Pawn.DesiredLocation), Offset(Pawn.DesiredSocketOffset), TargetOffset(Pawn.DesiredTargetOffset),
              Rotation(Pawn.DesiredRotation), Distance(Pawn.DesiredZoom) {}

        void CheckUnchanged(FAutomationTestBase& Test, const AGHSWarehouseCameraPawn& Pawn, const TCHAR* Reason) const
        {
            Test.TestTrue(FString(Reason) + TEXT(" pivot"), Pawn.DesiredLocation.Equals(Location, 0.001));
            Test.TestTrue(FString(Reason) + TEXT(" socket offset"), Pawn.DesiredSocketOffset.Equals(Offset, 0.001));
            Test.TestTrue(FString(Reason) + TEXT(" target offset"), Pawn.DesiredTargetOffset.Equals(TargetOffset, 0.001));
            Test.TestTrue(FString(Reason) + TEXT(" rotation"), Pawn.DesiredRotation.Equals(Rotation, 0.001));
            Near(Test, *(FString(Reason) + TEXT(" zoom")), Pawn.DesiredZoom, Distance);
        }
    };

    void CheckGroundPlane(FAutomationTestBase& Test, const AGHSWarehouseCameraPawn& Pawn)
    {
        Near(Test, TEXT("Desired pivot remains on warehouse ground"), Pawn.DesiredLocation.Z, 0.0);
        Near(Test, TEXT("Actual Pawn remains on warehouse ground"), Pawn.GetActorLocation().Z, 0.0);
        Near(Test, TEXT("Plugin rotation keeps a level horizon during diagonal orbit"), Pawn.GetActorRotation().Roll, 0.0);
        Test.TestTrue(TEXT("Desired socket offset is zero"), Pawn.DesiredSocketOffset.IsNearlyZero(0.001));
        Test.TestTrue(TEXT("Desired target offset is zero"), Pawn.DesiredTargetOffset.IsNearlyZero(0.001));
        Test.TestTrue(TEXT("Actual socket offset is zero"), Pawn.SpringArmComponent->SocketOffset.IsNearlyZero(0.001));
        Test.TestTrue(TEXT("Actual target offset is zero"), Pawn.SpringArmComponent->TargetOffset.IsNearlyZero(0.001));
    }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseCameraMouseGestures,
    "GHS.WarehouseCamera.Input.MouseGestures", GHSWarehouseCameraTests::Flags)

bool FGHSWarehouseCameraMouseGestures::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    const double InitialYaw = F.Pawn->DesiredRotation.Yaw;
    const double InitialPitch = F.Pawn->DesiredRotation.Pitch;

    TestTrue(TEXT("Left press consumed"), F.Key(EKeys::LeftMouseButton, IE_Pressed));
    TestTrue(TEXT("Left press selects orbit"), F.Controller->DragMode == EGHSWarehouseDragMode::Orbit);
    F.Mouse(2, 0);
    F.InputFrame();
    Near(*this, TEXT("Sub-threshold click does not move view"), F.Pawn->DesiredRotation.Yaw, InitialYaw);
    F.Key(EKeys::LeftMouseButton, IE_Released);
    TestTrue(TEXT("Tap release clears orbit"), F.Controller->DragMode == EGHSWarehouseDragMode::None);

    // Slate delivers IE_DoubleClick instead of another IE_Pressed on the second
    // quick click. Holding that click must still start an orbit gesture.
    F.Key(EKeys::LeftMouseButton, IE_DoubleClick);
    TestTrue(TEXT("Second click held starts orbit"), F.Controller->DragMode == EGHSWarehouseDragMode::Orbit);
    F.Mouse(20, 10);
    F.InputFrame();
    Near(*this, TEXT("Double-click drag consumes raw horizontal pixels"),
         F.Pawn->DesiredRotation.Yaw, InitialYaw + 20 * F.Pawn->OrbitDegreesPerPixel);
    Near(*this, TEXT("Double-click drag consumes screen-down pixels"),
         F.Pawn->DesiredRotation.Pitch, InitialPitch - 10 * F.Pawn->PitchDegreesPerPixel);
    F.Mouse(0, -20);
    F.InputFrame();
    Near(*this, TEXT("Screen-up drag raises pitch instead of reversing only one direction"),
         F.Pawn->DesiredRotation.Pitch, InitialPitch + 10 * F.Pawn->PitchDegreesPerPixel);
    CheckGroundPlane(*this, *F.Pawn);
    F.Key(EKeys::RightMouseButton, IE_Pressed);
    TestTrue(TEXT("Right press cannot steal active orbit"), F.Controller->DragMode == EGHSWarehouseDragMode::Orbit);
    F.Key(EKeys::RightMouseButton, IE_Released);
    TestTrue(TEXT("Unrelated release cannot stop orbit"), F.Controller->DragMode == EGHSWarehouseDragMode::Orbit);
    F.Key(EKeys::LeftMouseButton, IE_Released);
    TestTrue(TEXT("Owning button release ends orbit"), F.Controller->DragMode == EGHSWarehouseDragMode::None);
    const FDesiredPose Released(*F.Pawn);
    F.Mouse(40, 20);
    F.InputFrame();
    Released.CheckUnchanged(*this, *F.Pawn, TEXT("Mouse motion after release"));

    F.Key(EKeys::RightMouseButton, IE_Pressed);
    // A map grab requires a real local viewport and a valid ground point.
    // The rendered runtime test covers RMB ownership and double-click dragging.
    TestTrue(TEXT("No viewport means no ground grab"), F.Controller->DragMode == EGHSWarehouseDragMode::None);
    F.Key(EKeys::RightMouseButton, IE_Released);
    F.Key(EKeys::RightMouseButton, IE_DoubleClick);
    TestTrue(TEXT("Double-click also requires a valid viewport"), F.Controller->DragMode == EGHSWarehouseDragMode::None);
    F.Key(EKeys::RightMouseButton, IE_Released);
    TestTrue(TEXT("Double-click pan release clears mode"), F.Controller->DragMode == EGHSWarehouseDragMode::None);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinFastMouseRelease,
    "GHS.WarehouseCamera.Input.TwinFastRelease", GHSWarehouseCameraTests::Flags)

bool FGHSTwinFastMouseRelease::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    F.Controller->TwinHUDWidget = NewObject<UGHSTwinHUDWidget>(F.Controller);
    F.Controller->TwinHUDWidget->SelectedId = TEXT("AGV-07");
    const double InitialYaw = F.Pawn->DesiredRotation.Yaw;

    // Real SceneViewport ordering: release first, then the frame's accumulated
    // pointer axes. This used to treat a short fast drag as an empty-scene click.
    F.Key(EKeys::LeftMouseButton, IE_Pressed);
    F.Key(EKeys::LeftMouseButton, IE_Released);
    F.Mouse(100, 0);
    F.InputFrame();
    Near(*this, TEXT("Fast released drag consumes the final pointer batch"),
        F.Pawn->DesiredRotation.Yaw, InitialYaw + 100 * F.Pawn->OrbitDegreesPerPixel);
    TestEqual(TEXT("Fast drag preserves the open object"), F.Controller->TwinHUDWidget->SelectedId, FString(TEXT("AGV-07")));
    TestTrue(TEXT("Release finishes after the input batch"), F.Controller->DragMode == EGHSWarehouseDragMode::None);
    const FDesiredPose Released(*F.Pawn);
    F.Mouse(30, 0);
    F.InputFrame();
    Released.CheckUnchanged(*this, *F.Pawn, TEXT("Uncaptured movement after finished release"));

    F.Key(EKeys::LeftMouseButton, IE_Pressed);
    F.Key(EKeys::LeftMouseButton, IE_Released);
    F.Controller->CancelCameraDrag();
    F.Mouse(100, 0);
    F.InputFrame();
    Released.CheckUnchanged(*this, *F.Pawn, TEXT("Focus cancellation discards pending gesture"));

    F.Key(EKeys::LeftMouseButton, IE_Pressed);
    F.Key(EKeys::LeftMouseButton, IE_Released);
    F.Key(EKeys::LeftMouseButton, IE_DoubleClick);
    TestEqual(TEXT("Another press in the unflushed batch never emits a stale click"),
        F.Controller->TwinHUDWidget->SelectedId, FString(TEXT("AGV-07")));
    F.Mouse(100, 0);
    F.Key(EKeys::LeftMouseButton, IE_Released);
    F.InputFrame();
    Near(*this, TEXT("Same-frame second gesture consumes accumulated movement once"),
        F.Pawn->DesiredRotation.Yaw, InitialYaw + 200 * F.Pawn->OrbitDegreesPerPixel);
    TestEqual(TEXT("Same-frame double-click drag preserves detail"),
        F.Controller->TwinHUDWidget->SelectedId, FString(TEXT("AGV-07")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseCameraCancellation,
    "GHS.WarehouseCamera.Input.CancelFlushAndHome", GHSWarehouseCameraTests::Flags)

bool FGHSWarehouseCameraCancellation::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    const FDesiredPose Overview(*F.Pawn);

    F.Key(EKeys::LeftMouseButton, IE_Pressed);
    F.Mouse(50, 20); // Pending input has not been applied yet.
    F.Controller->FlushPressedKeys();
    TestTrue(TEXT("Focus-loss flush clears drag mode"), F.Controller->DragMode == EGHSWarehouseDragMode::None);
    F.InputFrame();
    Overview.CheckUnchanged(*this, *F.Pawn, TEXT("Flush discards queued motion"));

    F.Key(EKeys::LeftMouseButton, IE_Pressed);
    F.Mouse(1, 0);
    F.InputFrame();
    Overview.CheckUnchanged(*this, *F.Pawn, TEXT("New drag does not inherit prior threshold travel"));
    F.Key(EKeys::Home, IE_Pressed);
    TestTrue(TEXT("Home cancels active drag"), F.Controller->DragMode == EGHSWarehouseDragMode::None);

    F.Pawn->OrbitPixels(FVector2D(120, -40));
    F.Pawn->PanPixels(FVector2D(200, 20), 1600);
    F.Controller->InputKey(FInputKeyParams(EKeys::MouseWheelAxis, 2.0, FrameSeconds, 1));
    TestTrue(TEXT("Wheel InputKey changes zoom"), F.Pawn->DesiredZoom < F.Pawn->OverviewDistance);
    F.Key(EKeys::RightMouseButton, IE_DoubleClick);
    F.Mouse(100, 100);
    F.Key(EKeys::Home, IE_Pressed);
    F.InputFrame();
    Overview.CheckUnchanged(*this, *F.Pawn, TEXT("Home restores all overview targets and discards pending pan"));
    TestTrue(TEXT("Home clears pan state"), F.Controller->DragMode == EGHSWarehouseDragMode::None);

    F.Key(EKeys::LeftMouseButton, IE_Pressed);
    F.Mouse(60, 10);
    F.Controller->UnPossess();
    TestTrue(TEXT("UnPossess cancels drag"), F.Controller->DragMode == EGHSWarehouseDragMode::None);
    F.Controller->Possess(F.Pawn);
    F.InputFrame();
    Overview.CheckUnchanged(*this, *F.Pawn, TEXT("Possession change cannot replay old motion"));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseCameraMiddleReset,
    "GHS.WarehouseCamera.Input.MiddleClickResetsOverview", GHSWarehouseCameraTests::Flags)

bool FGHSWarehouseCameraMiddleReset::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    const FDesiredPose Overview(*F.Pawn);
    F.Pawn->OrbitPixels(FVector2D(120,-40));
    F.Pawn->PanPixels(FVector2D(200,20),1600);
    F.Pawn->ZoomSteps(2);
    F.Key(EKeys::LeftMouseButton,IE_Pressed);
    F.Mouse(60,20);
    TestTrue(TEXT("Middle click is consumed"),F.Key(EKeys::MiddleMouseButton,IE_Pressed));
    TestTrue(TEXT("Middle click cancels the active gesture"),F.Controller->DragMode==EGHSWarehouseDragMode::None);
    F.InputFrame();
    Overview.CheckUnchanged(*this,*F.Pawn,TEXT("Middle click restores overview and discards pending drag"));

    F.Pawn->OrbitPixels(FVector2D(30,10));
    const FDesiredPose AfterPress(*F.Pawn);
    F.Key(EKeys::MiddleMouseButton,IE_Released);
    AfterPress.CheckUnchanged(*this,*F.Pawn,TEXT("Middle release must not restart overview"));
    TestTrue(TEXT("Rapid second middle click is consumed"),F.Key(EKeys::MiddleMouseButton,IE_DoubleClick));
    Overview.CheckUnchanged(*this,*F.Pawn,TEXT("Rapid second click also restores overview"));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinMiddleResetClearsSelection,
    "GHS.WarehouseCamera.Input.MiddleClickClearsTwinSelection", GHSWarehouseCameraTests::Flags)

bool FGHSTwinMiddleResetClearsSelection::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    F.Controller->TwinHUDWidget=NewObject<UGHSTwinHUDWidget>(F.Controller);
    F.Controller->TwinHUDWidget->SelectedId=TEXT("AGV-07");
    TestTrue(TEXT("Twin scene middle click is consumed"),F.Key(EKeys::MiddleMouseButton,IE_Pressed));
    TestTrue(TEXT("Middle reset uses overview to clear the selected object"),F.Controller->TwinHUDWidget->SelectedId.IsEmpty());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseCameraZoomKeepsPan,
    "GHS.WarehouseCamera.Composition.ZoomKeepsRemotePan", GHSWarehouseCameraTests::Flags)

bool FGHSWarehouseCameraZoomKeepsPan::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    const FVector Center = F.Pawn->DesiredLocation;
    const double UnitsPerPixel = 2.0 * F.Pawn->DesiredZoom *
        FMath::Tan(FMath::DegreesToRadians(double(F.Pawn->WarehouseCamera->FieldOfView) * 0.5)) / 1600.0;
    F.Pawn->PanPixels(FVector2D(-22000.0 / UnitsPerPixel, 0), 1600);
    Near(*this, TEXT("Choose a remote aisle 220 m sideways by moving the pivot"),
         F.Pawn->DesiredLocation.X, Center.X + 22000.0, 0.01);
    Near(*this, TEXT("Horizontal pan preserves ground Y at overview yaw"), F.Pawn->DesiredLocation.Y, Center.Y);
    const FVector SelectedPivot = F.Pawn->DesiredLocation;
    CheckGroundPlane(*this, *F.Pawn);

    for (int32 Step = 0; Step < 50; ++Step)
    {
        F.Pawn->ZoomSteps(1.0f);
        TestTrue(TEXT("Zoom must not recenter the selected remote aisle"),
                 F.Pawn->DesiredLocation.Equals(SelectedPivot, 0.01));
        F.CameraFrame();
        CheckGroundPlane(*this, *F.Pawn);
    }
    Near(*this, TEXT("Zoom reaches useful close inspection distance"), F.Pawn->DesiredZoom, F.Pawn->MinimumZoom);
    TestFalse(TEXT("Pan moves the orbit pivot away from the original warehouse center"),
              F.Pawn->DesiredLocation.Equals(Center, 0.001));
    TestTrue(TEXT("Close view maintains floor clearance"), F.Pawn->GetDesiredCameraWorldLocation().Z >= F.Pawn->MinimumCameraHeight - 0.01);
    F.Pawn->ZoomSteps(-1000.0f);
    TestTrue(TEXT("Zooming back out preserves the same aisle"), F.Pawn->DesiredLocation.Equals(SelectedPivot, 0.01));
    F.Pawn->OrbitPixels(FVector2D(250, 80));
    TestTrue(TEXT("Orbit rotates about the moved pivot without recentering"),
             F.Pawn->DesiredLocation.Equals(SelectedPivot, 0.01));
    for (int32 Frame = 0; Frame < 150; ++Frame)
    {
        F.CameraFrame();
        CheckGroundPlane(*this, *F.Pawn);
    }
    TestTrue(TEXT("Actual Pawn converges to the selected ground pivot"),
             F.Pawn->GetActorLocation().Equals(SelectedPivot, 0.05));
    Near(*this, TEXT("Real Tick applies pitch lag"), F.Pawn->GetActorRotation().Pitch, F.Pawn->DesiredRotation.Pitch, 0.01);
    Near(*this, TEXT("Real Tick applies zoom lag"), F.Pawn->SpringArmComponent->TargetArmLength, F.Pawn->DesiredZoom, 0.1);
    F.Pawn->ResetOverview(true);
    TestTrue(TEXT("Only reset recenters the ground pivot"), F.Pawn->DesiredLocation.Equals(Center, 0.001));
    TestTrue(TEXT("Immediate reset also restores the actual Pawn"), F.Pawn->GetActorLocation().Equals(Center, 0.001));
    CheckGroundPlane(*this, *F.Pawn);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseCameraGroundPan,
    "GHS.WarehouseCamera.Composition.GroundPlanePan", GHSWarehouseCameraTests::Flags)

bool FGHSWarehouseCameraGroundPan::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    const FVector Center(-646.665, 833.981, 0.0);
    TestTrue(TEXT("Overview center is the warehouse ground center"), F.Pawn->OverviewCenter.Equals(Center, 0.001));
    const double UnitsPerPixel = 2.0 * F.Pawn->OverviewDistance *
        FMath::Tan(FMath::DegreesToRadians(double(F.Pawn->WarehouseCamera->FieldOfView) * 0.5)) / 1600.0;

    // At yaw -90, screen right is world +X and ground forward is world -Y.
    // At pitch -30, five vertical screen pixels cover ten ground pixel units.
    // The isolated fixture intentionally has no OS viewport. Supply its width
    // directly; controller ownership/threshold/cancellation are tested above.
    F.Pawn->PanPixels(FVector2D(10, 5), 1600);
    Near(*this, TEXT("Right drag moves ground pivot opposite screen-right X"),
         F.Pawn->DesiredLocation.X, Center.X - 10.0 * UnitsPerPixel, 0.05);
    Near(*this, TEXT("Down drag moves ground pivot forward along negative world Y"),
         F.Pawn->DesiredLocation.Y, Center.Y - 10.0 * UnitsPerPixel, 0.05);
    CheckGroundPlane(*this, *F.Pawn);
    F.Pawn->ResetOverview(true);
    F.Pawn->SetDesiredRotation(FRotator(-30, 0, 0), true);
    F.Pawn->PanPixels(FVector2D(10, 5), 1600);
    Near(*this, TEXT("Pan follows yaw: ground forward becomes world +X"),
         F.Pawn->DesiredLocation.X, Center.X + 10.0 * UnitsPerPixel, 0.05);
    Near(*this, TEXT("Pan follows yaw: screen right becomes world +Y"),
         F.Pawn->DesiredLocation.Y, Center.Y - 10.0 * UnitsPerPixel, 0.05);
    CheckGroundPlane(*this, *F.Pawn);

    F.Pawn->ResetOverview(true);
    F.Pawn->SetDesiredRotation(FRotator(-60, 0, 0), true);
    F.Pawn->PanPixels(FVector2D(10, 5), 1600);
    Near(*this, TEXT("Steeper pitch compensates vertical ground projection"), F.Pawn->DesiredLocation.X,
         Center.X + 5.0 * UnitsPerPixel / FMath::Sin(FMath::DegreesToRadians(60.0)), 0.05);
    CheckGroundPlane(*this, *F.Pawn);

    F.Pawn->ResetOverview(true);
    F.Pawn->PanPixels(FVector2D(10, 5), 800);
    Near(*this, TEXT("Half viewport width doubles ground pan X"), F.Pawn->DesiredLocation.X,
         Center.X - 20.0 * UnitsPerPixel, 0.05);
    Near(*this, TEXT("Half viewport width doubles ground pan Y"), F.Pawn->DesiredLocation.Y,
         Center.Y - 20.0 * UnitsPerPixel, 0.05);
    CheckGroundPlane(*this, *F.Pawn);

    F.Pawn->ResetOverview(true);
    F.Pawn->ZoomSteps(1.0f);
    F.Pawn->PanPixels(FVector2D(10, 5), 1600);
    Near(*this, TEXT("Zoom-adaptive pan remains usable in close views"), F.Pawn->DesiredLocation.X,
         Center.X - 10.0 * UnitsPerPixel * FMath::Exp(-0.12), 0.05);
    CheckGroundPlane(*this, *F.Pawn);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseCameraNonFinite,
    "GHS.WarehouseCamera.Input.RejectNonFiniteValues", GHSWarehouseCameraTests::Flags)

bool FGHSWarehouseCameraNonFinite::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;
    F.Pawn->OrbitPixels(FVector2D(20, -5));
    F.Pawn->PanPixels(FVector2D(50, 10), 1600);
    F.Pawn->ZoomSteps(1.0f);
    const FDesiredPose Before(*F.Pawn);

    // Construct valid first, then assign fields: FVector2D's diagnostic
    // constructor can sanitize NaN before the method under test receives it.
    for (const double Invalid : {std::numeric_limits<double>::quiet_NaN(),
                                  std::numeric_limits<double>::infinity(),
                                  -std::numeric_limits<double>::infinity()})
    {
        FVector2D InvalidX(0, 7);
        InvalidX.X = Invalid;
        F.Pawn->OrbitPixels(InvalidX);
        Before.CheckUnchanged(*this, *F.Pawn, TEXT("Non-finite orbit X rejected atomically"));
        F.Pawn->PanPixels(InvalidX, 1600);
        Before.CheckUnchanged(*this, *F.Pawn, TEXT("Non-finite pan X rejected atomically"));
        FVector2D InvalidY(7, 0);
        InvalidY.Y = Invalid;
        F.Pawn->OrbitPixels(InvalidY);
        Before.CheckUnchanged(*this, *F.Pawn, TEXT("Non-finite orbit Y rejected atomically"));
        F.Pawn->PanPixels(InvalidY, 1600);
        Before.CheckUnchanged(*this, *F.Pawn, TEXT("Non-finite pan Y rejected atomically"));
    }
    F.Pawn->ZoomSteps(std::numeric_limits<float>::quiet_NaN());
    F.Pawn->ZoomSteps(std::numeric_limits<float>::infinity());
    F.Pawn->ZoomSteps(-std::numeric_limits<float>::infinity());
    Before.CheckUnchanged(*this, *F.Pawn, TEXT("Non-finite wheel input rejected"));
    F.Pawn->PanPixels(FVector2D(50, 25), 0);
    F.Pawn->PanPixels(FVector2D(50, 25), -1);
    Before.CheckUnchanged(*this, *F.Pawn, TEXT("Missing viewport dimensions rejected"));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseCameraHUDThreshold,
    "GHS.WarehouseCamera.HUD.ActualSpringArmControlsAggregation", GHSWarehouseCameraTests::Flags)

bool FGHSWarehouseCameraHUDThreshold::RunTest(const FString& Parameters)
{
    using namespace GHSWarehouseCameraTests;
    FFixture F;
    if (!F.Check(*this)) return false;

    Near(*this, TEXT("Aggregation minimum defaults to 10000"), F.Pawn->HUDClusterMinArmLength, 10000);
    F.Pawn->SpringArmComponent->TargetArmLength = 9999;
    F.Pawn->DesiredZoom = 20000;
    TestFalse(TEXT("Near current camera remains ungrouped while zooming out"), F.Pawn->ShouldAggregateTruckHUD());
    F.Pawn->SpringArmComponent->TargetArmLength = 10000;
    F.Pawn->DesiredZoom = 2000;
    TestTrue(TEXT("Equality aggregates even while desired zoom is nearer"), F.Pawn->ShouldAggregateTruckHUD());
    F.Pawn->HUDClusterMinArmLength = 12000;
    TestFalse(TEXT("Changing the exposed threshold immediately changes eligibility"), F.Pawn->ShouldAggregateTruckHUD());
    F.Pawn->HUDClusterMinArmLength = 0;
    F.Pawn->SpringArmComponent->TargetArmLength = 900;
    TestTrue(TEXT("Zero permits aggregation at the closest camera distance"), F.Pawn->ShouldAggregateTruckHUD());
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
