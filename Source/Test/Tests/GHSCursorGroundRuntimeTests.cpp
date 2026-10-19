#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseCameraPawn.h"
#include "../GHSWarehousePlayerController.h"
#include "../GHSDockTruckHUDWidget.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "GameFramework/PlayerInput.h"
#include "Framework/Application/SlateApplication.h"
#include "Input/Events.h"
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Slate/SceneViewport.h"

namespace GHSMapDragRuntimeTests
{
    constexpr float FrameSeconds = 1.0f / 60.0f;

    void SyncView(AGHSWarehouseCameraPawn* Pawn, APlayerCameraManager* Camera)
    {
        Pawn->SpringArmComponent->TickComponent(FrameSeconds, LEVELTICK_All, nullptr);
        Camera->UpdateCamera(FrameSeconds);
    }

    void CameraFrame(AGHSWarehouseCameraPawn* Pawn, APlayerCameraManager* Camera)
    {
        Pawn->LastDeltaTime = FrameSeconds;
        Pawn->Tick(FrameSeconds);
        SyncView(Pawn, Camera);
    }

    struct FRestoreOverview
    {
        AGHSWarehouseCameraPawn* Pawn;
        AGHSWarehousePlayerController* Controller;
        APlayerCameraManager* Camera;
        ~FRestoreOverview()
        {
            Controller->CancelCameraDrag();
            Pawn->ResetOverview(true);
            SyncView(Pawn, Camera);
        }
    };

    bool GroundPoint(AGHSWarehousePlayerController* Controller, FVector2D Pixel, FVector& Point)
    {
        FVector Origin, Direction;
        // Independent expectation from the live public projection API, without
        // consulting the plugin's drag origin or production movement calculation.
        if (!Controller->DeprojectScreenPositionToWorld(Pixel.X, Pixel.Y, Origin, Direction)
            || Origin.ContainsNaN() || Direction.ContainsNaN() || Direction.Z >= -1.e-6) return false;
        const double Distance = -Origin.Z / Direction.Z;
        if (Distance < 0 || !FMath::IsFinite(Distance)) return false;
        Point = Origin + Direction * Distance;
        Point.Z = 0;
        return !Point.ContainsNaN();
    }

    struct FViewportPointer
    {
        FAutomationTestBase& Test;
        FSceneViewport* Viewport;
        AGHSWarehousePlayerController* Controller;
        FGeometry Geometry;
        FVector2D Previous = FVector2D::ZeroVector;

        bool Move(FVector2D Pixel, bool RightHeld = false)
        {
            TSet<FKey> Pressed;
            if (RightHeld) Pressed.Add(EKeys::RightMouseButton);
            const FPointerEvent Event(0,
                Pixel, Previous, Pressed, FKey(), 0.0f, FModifierKeysState());
            // Direct scene-viewport events only: never route through the native
            // application, capture a desktop window, or set the OS cursor. The
            // OnFocusLost below clears hidden capture before this synchronous
            // test. No button event is routed through Slate to reacquire it.
            if (!Test.TestFalse(TEXT("Synthetic pointer never has native capture"), Viewport->HasMouseCapture())) return false;
            Viewport->OnMouseMove(Geometry, Event);
            Previous = Pixel;
            FVector2D Readback;
            const bool Available = Controller->GetMousePosition(Readback.X, Readback.Y);
            if (Pixel.X < 0 || Pixel.Y < 0)
                return Test.TestFalse(TEXT("Negative viewport pointer is unavailable"), Available);
            return Test.TestTrue(TEXT("Plugin-facing absolute cursor is available"), Available)
                && Test.TestTrue(TEXT("Plugin-facing absolute cursor matches injected pixel"), Readback.Equals(Pixel, 0.01));
        }
    };
}

// This suite requires an actual game viewport, never the editor/commandlet or
// the user's interactive desktop. The parent runner owns the offscreen process.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMapDragRuntime,
    "WarehouseRuntime.MapDrag",
    EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FGHSMapDragRuntime::RunTest(const FString& Parameters)
{
    using namespace GHSMapDragRuntimeTests;
    if (!TestFalse(TEXT("Requires a standalone game, not a commandlet"), IsRunningCommandlet())
        || !TestTrue(TEXT("Use a disposable -RenderOffscreen game"), FParse::Param(FCommandLine::Get(), TEXT("RenderOffscreen")))
        || !TestNotNull(TEXT("Engine"), GEngine)) return false;

    AGHSWarehousePlayerController* Controller = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
    {
        UWorld* World = Context.World();
        if (Context.WorldType == EWorldType::Game && World)
        {
            auto* Candidate = Cast<AGHSWarehousePlayerController>(World->GetFirstPlayerController());
            if (Candidate && Candidate->GetLocalPlayer()) { Controller = Candidate; break; }
        }
    }
    if (!TestNotNull(TEXT("Actual game warehouse Controller and LocalPlayer"), Controller)) return false;
    auto* Pawn = Cast<AGHSWarehouseCameraPawn>(Controller->GetPawn());
    APlayerCameraManager* Camera = Controller->PlayerCameraManager;
    ULocalPlayer* Local = Controller->GetLocalPlayer();
    FViewport* BaseViewport = Local->ViewportClient ? Local->ViewportClient->Viewport : nullptr;
    if (!TestNotNull(TEXT("Actual possessed camera Pawn"), Pawn)
        || !TestNotNull(TEXT("Actual PlayerCameraManager"), Camera)
        || !TestNotNull(TEXT("Actual game Viewport"), BaseViewport)
        || !TestTrue(TEXT("Game viewport is a Slate scene viewport"), BaseViewport->IsSlateViewport())) return false;
    auto* Viewport = static_cast<FSceneViewport*>(BaseViewport);
    // Clear offscreen startup's hidden-capture flag through its native handler.
    // This only resets viewport input state; it does not focus an OS window.
    Viewport->OnFocusLost(FFocusEvent(EFocusCause::Cleared, FSlateApplication::Get().GetUserIndexForKeyboard()));
    FRestoreOverview Restore{Pawn, Controller, Camera};
    if (!TestTrue(TEXT("View target is possessed camera Pawn"), Controller->GetViewTarget() == Pawn)) return false;
    const FIntPoint Size = Viewport->GetSizeXY();
    if (!TestTrue(TEXT("Usable viewport dimensions"), Size.X > 100 && Size.Y > 100)) return false;
    FViewportPointer Pointer{*this, Viewport, Controller,
        FGeometry::MakeRoot(FVector2D(Size.X, Size.Y), FSlateLayoutTransform(1.0f))};
    const FVector2D First(FMath::RoundToInt(Size.X * 0.55), FMath::RoundToInt(Size.Y * 0.60));
    const FVector2D Second(FMath::RoundToInt(Size.X * 0.42), FMath::RoundToInt(Size.Y * 0.55));
    const FVector2D Third(FMath::RoundToInt(Size.X * 0.58), FMath::RoundToInt(Size.Y * 0.65));
    const auto* OriginalHUD = Controller->TruckHUDWidget.Get();
    if (!TestNotNull(TEXT("Existing dock-truck HUD"), OriginalHUD)) return false;
    const int32 OriginalTruckCount = OriginalHUD->GetRegisteredTruckCount();
    const FString OriginalSelection = OriginalHUD->GetSelectedTruckId();

    auto CheckGround = [this, Pawn](const FString& Label)
    {
        TestTrue(Label + TEXT(" desired Z=0"), FMath::IsNearlyZero(Pawn->DesiredLocation.Z, 0.001));
        TestTrue(Label + TEXT(" actual Pawn Z=0"), FMath::IsNearlyZero(Pawn->GetActorLocation().Z, 0.001));
        TestTrue(Label + TEXT(" desired camera offsets stay zero"), Pawn->DesiredSocketOffset.IsNearlyZero(0.001)
            && Pawn->DesiredTargetOffset.IsNearlyZero(0.001));
        TestTrue(Label + TEXT(" actual camera offsets stay zero"), Pawn->SpringArmComponent->SocketOffset.IsNearlyZero(0.001)
            && Pawn->SpringArmComponent->TargetOffset.IsNearlyZero(0.001));
        TestTrue(Label + TEXT(" no banking"), FMath::IsNearlyZero(Pawn->GetActorRotation().Roll, 0.01));
    };
    auto CheckAnchor = [this, Controller](const FString& Label, const FVector& Anchor, const FVector2D& Pixel)
    {
        FVector2D Projected;
        TestTrue(Label + TEXT(" grabbed world point projects into the view"),
            Controller->ProjectWorldLocationToScreen(Anchor, Projected, false));
        TestTrue(FString::Printf(TEXT("%s world anchor follows cursor: actual %s expected %s"),
            *Label, *Projected.ToString(), *Pixel.ToString()), Projected.Equals(Pixel, 0.75));
    };
    int32 Cases = 0;
    for (const double Yaw : {-170.0, -90.0, 0.0, 75.0, 179.0})
    {
        for (const double Pitch : {-15.0, -30.0, -60.0, -80.0})
        {
            const FString Label = FString::Printf(TEXT("Yaw %.0f pitch %.0f"), Yaw, Pitch);
            Controller->CancelCameraDrag();
            Pawn->ResetOverview(true);
            Pawn->SetDesiredRotation(FRotator(Pitch, Yaw, 0), true);
            Pawn->SetDesiredZoom(5000.0f, true);
            SyncView(Pawn, Camera);
            if (!Pointer.Move(First)) return false;
            FVector Anchor, SecondGround;
            if (!TestTrue(Label + TEXT(" initial ground anchor"), GroundPoint(Controller, First, Anchor))
                || !TestTrue(Label + TEXT(" second independent ground ray"), GroundPoint(Controller, Second, SecondGround))) return false;
            const FVector PivotBeforePress = Pawn->GetActorLocation();
            const FVector ExpectedMovedPivot = PivotBeforePress + Anchor - SecondGround;
            TestTrue(Label + TEXT(" movement stays inside bounds"),
                Pawn->GetClampedLocation(ExpectedMovedPivot).Equals(ExpectedMovedPivot, 0.01));
            Controller->InputKey(FInputKeyParams(EKeys::RightMouseButton, IE_Pressed, 1.0));
            TestTrue(Label + TEXT(" RMB starts native map drag"),
                Controller->DragMode == EGHSWarehouseDragMode::Pan && Pawn->IsPreciseMouseDragging);
            TestTrue(Label + TEXT(" press does not jump actual or desired pivot"),
                Pawn->GetActorLocation().Equals(PivotBeforePress, 0.01) && Pawn->DesiredLocation.Equals(PivotBeforePress, 0.01));
            TestTrue(Label + TEXT(" cursor remains visible"), Controller->bShowMouseCursor);
            TestFalse(Label + TEXT(" map drag disables cursor hiding"), Local->ViewportClient->HideCursorDuringCapture());
            TestTrue(Label + TEXT(" native plugin uses immediate Z=0 plane drag"),
                Pawn->PreciseMouseDragMode == EPreciseMouseDragMode::Plane
                && Pawn->PreciseMouseDragPoint.IsNearlyZero() && Pawn->PreciseMouseDragNormal.Equals(FVector::UpVector)
                && Pawn->PreciseMouseDragIgnoreMovementLag);
            CameraFrame(Pawn, Camera);
            TestTrue(Label + TEXT(" stationary initial frame does not jump"), Pawn->GetActorLocation().Equals(PivotBeforePress, 0.05));
            CheckAnchor(Label + TEXT(" press"), Anchor, First);

            // First-held ownership: the other button cannot steal or end RMB.
            Controller->InputKey(FInputKeyParams(EKeys::LeftMouseButton, IE_Pressed, 1.0));
            Controller->InputKey(FInputKeyParams(EKeys::LeftMouseButton, IE_Released, 0.0));
            TestTrue(Label + TEXT(" left-button chord preserves RMB ownership"),
                Controller->DragMode == EGHSWarehouseDragMode::Pan && Pawn->IsPreciseMouseDragging);
            if (!Pointer.Move(Second, true)) return false;
            TestTrue(Label + TEXT(" moved cursor is valid"), Controller->HasValidMapDragCursor());
            CameraFrame(Pawn, Camera);
            CheckAnchor(Label + TEXT(" drag"), Anchor, Second);
            TestTrue(Label + TEXT(" actual translation matches independent ground rays"), Pawn->GetActorLocation().Equals(ExpectedMovedPivot, 0.15));
            TestTrue(Label + TEXT(" drag has no residual movement lag"), Pawn->GetActorLocation().Equals(Pawn->DesiredLocation, 0.01));
            CheckGround(Label);
            const FVector Stationary = Pawn->GetActorLocation();
            for (int32 Repeat = 0; Repeat < 8; ++Repeat)
            {
                if (!Pointer.Move(Second, true)) return false;
                CameraFrame(Pawn, Camera);
            }
            TestTrue(Label + TEXT(" stationary pointer does not drift"), Pawn->GetActorLocation().Equals(Stationary, 0.15));
            CheckAnchor(Label + TEXT(" stationary"), Anchor, Second);
            Controller->InputKey(FInputKeyParams(EKeys::RightMouseButton, IE_Released, 0.0));
            TestTrue(Label + TEXT(" release clears both gesture states"),
                Controller->DragMode == EGHSWarehouseDragMode::None && !Pawn->IsPreciseMouseDragging);
            if (!Pointer.Move(Third)) return false;
            for (int32 Frame = 0; Frame < 8; ++Frame) CameraFrame(Pawn, Camera);
            TestTrue(Label + TEXT(" release stops immediately despite further pointer movement"),
                Pawn->GetActorLocation().Equals(Stationary, 0.15) && Pawn->DesiredLocation.Equals(Stationary, 0.15));
            Pawn->OrbitPixels(FVector2D(25, 15));
            for (int32 Frame = 0; Frame < 8; ++Frame) CameraFrame(Pawn, Camera);
            TestTrue(Label + TEXT(" subsequent orbit preserves moved ground center"), Pawn->GetActorLocation().Equals(Stationary, 0.15));
            CheckGround(Label + TEXT(" orbit"));
            ++Cases;
        }
    }
    TestEqual(TEXT("All yaw/pitch combinations tested"), Cases, 20);

    Controller->CancelCameraDrag();
    Pawn->ResetOverview(true);
    Pawn->SetDesiredZoom(5000.0f, true);
    SyncView(Pawn, Camera);
    if (!Pointer.Move(First)) return false;
    const FVector BeforeLag = Pawn->GetActorLocation();
    const FRotator ActualRotation = Pawn->GetActorRotation();
    const float ActualArm = Pawn->SpringArmComponent->TargetArmLength;
    FVector LagAnchor;
    if (!TestTrue(TEXT("Ground anchor before unfinished easing"), GroundPoint(Controller, First, LagAnchor))) return false;
    Pawn->SetDesiredLocation(BeforeLag + FVector(700, 400, 0));
    Pawn->SetDesiredRotation(FRotator(-55, 20, 0));
    Pawn->SetDesiredZoom(2500.0f);
    Controller->InputKey(FInputKeyParams(EKeys::RightMouseButton, IE_DoubleClick, 1.0));
    TestTrue(TEXT("RMB double click starts map drag"), Controller->DragMode == EGHSWarehouseDragMode::Pan && Pawn->IsPreciseMouseDragging);
    TestTrue(TEXT("Press freezes unfinished position rotation and zoom at actual view"),
        Pawn->DesiredLocation.Equals(BeforeLag, 0.01) && Pawn->DesiredRotation.Equals(ActualRotation, 0.001)
        && FMath::IsNearlyEqual(Pawn->DesiredZoom, ActualArm, 0.01f));
    for (int32 Frame = 0; Frame < 8; ++Frame) CameraFrame(Pawn, Camera);
    CheckAnchor(TEXT("unfinished easing canceled"), LagAnchor, First);
    TestTrue(TEXT("Unfinished easing does not move grabbed pivot"), Pawn->GetActorLocation().Equals(BeforeLag, 0.15));
    Controller->FlushPressedKeys();
    TestTrue(TEXT("Flush clears controller and plugin drag"), Controller->DragMode == EGHSWarehouseDragMode::None && !Pawn->IsPreciseMouseDragging);

    for (const FVector2D Invalid : {FVector2D(-1, First.Y), FVector2D(Size.X + 1, First.Y),
         FVector2D(First.X, -1), FVector2D(First.X, Size.Y + 1)})
    {
        if (!Pointer.Move(First)) return false;
        Controller->InputKey(FInputKeyParams(EKeys::RightMouseButton, IE_Pressed, 1.0));
        TestTrue(TEXT("Valid drag before invalid pixel"), Pawn->IsPreciseMouseDragging);
        const FVector Before = Pawn->GetActorLocation();
        if (!Pointer.Move(Invalid, true)) return false;
        TestFalse(TEXT("Outside/unavailable cursor fails native-drag guard"), Controller->HasValidMapDragCursor());
        // Real Pawn Tick must cancel BEFORE the plugin consumes invalid input.
        CameraFrame(Pawn, Camera);
        TestTrue(TEXT("Invalid pixel cancels both gesture states"), Controller->DragMode == EGHSWarehouseDragMode::None && !Pawn->IsPreciseMouseDragging);
        TestTrue(TEXT("Invalid pixel cannot move the camera"), Pawn->GetActorLocation().Equals(Before, 0.01) && Pawn->DesiredLocation.Equals(Before, 0.01));
        CheckGround(TEXT("invalid cursor"));
    }

    if (!Pointer.Move(First)) return false;
    Controller->InputKey(FInputKeyParams(EKeys::RightMouseButton, IE_Pressed, 1.0));
    const FVector BeforeWheel = Pawn->GetActorLocation();
    const float OldZoom = Pawn->DesiredZoom;
    Controller->InputKey(FInputKeyParams(EKeys::MouseWheelAxis, 1.0, FrameSeconds, 1));
    TestTrue(TEXT("Wheel keeps proportional zoom"), FMath::IsNearlyEqual(
        double(Pawn->DesiredZoom), double(OldZoom) * FMath::Exp(-double(Pawn->WheelZoomExponent)), 0.01));
    TestTrue(TEXT("Wheel ends native drag before changing zoom"), Controller->DragMode == EGHSWarehouseDragMode::None && !Pawn->IsPreciseMouseDragging);
    CameraFrame(Pawn, Camera);
    TestTrue(TEXT("Wheel preserves moved ground pivot"), Pawn->GetActorLocation().Equals(BeforeWheel, 0.01));
    Controller->InputKey(FInputKeyParams(EKeys::Home, IE_Pressed, 1.0));
    TestTrue(TEXT("Home restores ground overview center"), Pawn->DesiredLocation.Equals(FVector(Pawn->OverviewCenter.X, Pawn->OverviewCenter.Y, 0), 0.001));
    TestTrue(TEXT("Home restores orientation"), Pawn->DesiredRotation.Equals(FRotator(Pawn->OverviewPitch, Pawn->OverviewYaw, 0), 0.001));
    TestTrue(TEXT("Home restores distance"), FMath::IsNearlyEqual(Pawn->DesiredZoom, Pawn->OverviewDistance, 0.01f));
    CheckGround(TEXT("Home"));
    TestTrue(TEXT("Existing HUD object is preserved"), Controller->TruckHUDWidget.Get() == OriginalHUD);
    TestEqual(TEXT("HUD truck count is preserved"), OriginalHUD->GetRegisteredTruckCount(), OriginalTruckCount);
    TestEqual(TEXT("HUD selection is preserved"), OriginalHUD->GetSelectedTruckId(), OriginalSelection);
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
