#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseCameraPawn.h"
#include "../GHSWarehousePlayerController.h"
#include "../GHSDockTruckHUDWidget.h"
#include "../GHSTwinHUDWidget.h"
#include "Dom/JsonObject.h"
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
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

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

    bool SnapshotDeviceIds(const UGHSTwinHUDWidget* HUD, TArray<FString>& Ids)
    {
        // Positions and visibility can change during navigation. Compare the
        // registered identities, not a volatile whole-scene JSON snapshot.
        TSharedPtr<FJsonObject> Snapshot;
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(HUD->GetSnapshot()), Snapshot)
            || !Snapshot.IsValid()) return false;
        Ids.Reset();
        for (const FString Field : {FString(TEXT("equipment")), FString(TEXT("facilities"))})
        {
            const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
            if (!Snapshot->TryGetArrayField(Field, Entries) || !Entries) return false;
            for (const auto& Entry : *Entries)
            {
                const TSharedPtr<FJsonObject>* Object = nullptr;
                FString Id;
                if (!Entry.IsValid() || !Entry->TryGetObject(Object) || !Object || !Object->IsValid()
                    || !(*Object)->TryGetStringField(TEXT("id"), Id) || Id.IsEmpty()) return false;
                Ids.Add(Field + TEXT(":") + Id);
            }
        }
        Ids.Sort();
        return true;
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
    const bool bTwinMap = Controller->GetWorld()->GetMapName().Contains(TEXT("ZcoolSmartFactory"));
    const auto* OriginalTruckHUD = Controller->TruckHUDWidget.Get();
    const auto* OriginalTwinHUD = Controller->TwinHUDWidget.Get();
    TArray<FString> OriginalDeviceIds;
    if (bTwinMap)
    {
        if (!TestNotNull(TEXT("Main map has its production Twin HUD"), OriginalTwinHUD)
            || !TestNull(TEXT("Main map does not create the legacy truck HUD"), OriginalTruckHUD)) return false;
        if (!TestTrue(TEXT("Twin HUD uses the actual viewport pixels"),
                OriginalTwinHUD->GetViewportPixelSize().Equals(FVector2D(Size.X, Size.Y), 1.))
            || !TestTrue(TEXT("Twin panel has completed its initial layout"),
                FMath::IsNearlyEqual(OriginalTwinHUD->GetPanelTransitionProgress(), 1.f, .001f))
            || !TestTrue(TEXT("All drag test pixels belong to the unobscured scene"),
                OriginalTwinHUD->IsScenePoint(First) && OriginalTwinHUD->IsScenePoint(Second)
                && OriginalTwinHUD->IsScenePoint(Third))
            || !TestTrue(TEXT("Twin snapshot exposes registered device identities"),
                SnapshotDeviceIds(OriginalTwinHUD, OriginalDeviceIds))
            || !TestTrue(TEXT("Main map contains registered devices"), !OriginalDeviceIds.IsEmpty())) return false;
    }
    else if (!TestNotNull(TEXT("Legacy map has its dock-truck HUD"), OriginalTruckHUD)
        || !TestNull(TEXT("Legacy map does not create a Twin HUD"), OriginalTwinHUD)) return false;
    const int32 OriginalTruckCount = OriginalTruckHUD ? OriginalTruckHUD->GetRegisteredTruckCount() : 0;
    const FString OriginalSelection = OriginalTwinHUD ? OriginalTwinHUD->SelectedId : OriginalTruckHUD->GetSelectedTruckId();

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

    if (OriginalTwinHUD)
    {
        // Exercise the actual Controller and Pawn guard at visible UI regions,
        // not just the layout helper: UI must neither start nor continue a pan.
        const float Scale = OriginalTwinHUD->GetHUDScale();
        const auto Layout = FGHSTwinLayout::Calculate(FVector2D(Size.X, Size.Y) / Scale);
        if (!TestTrue(TEXT("Scene search is visible for the occlusion test"), OriginalTwinHUD->IsSceneSearchVisible())
            || !TestTrue(TEXT("Scene search has a laid-out hit area"),
                OriginalTwinHUD->GetSceneSearchSize().X > 0 && OriginalTwinHUD->GetSceneSearchSize().Y > 0)) return false;
        const TArray<FVector2D> BlockedPixels = {
            FVector2D(Size.X * .5, Layout.HeaderHeight * .5 * Scale),
            (OriginalTwinHUD->GetPanelVisualPosition() + OriginalTwinHUD->GetPanelVisualSize() * .5) * Scale,
            (OriginalTwinHUD->GetSceneSearchPosition() + OriginalTwinHUD->GetSceneSearchSize() * .5) * Scale
        };
        int32 BlockedCases = 0;
        for (FVector2D Pixel : BlockedPixels)
        {
            Pixel = FVector2D(FMath::RoundToInt(Pixel.X), FMath::RoundToInt(Pixel.Y));
            const FString Label = FString::Printf(TEXT("Twin UI region %d"), BlockedCases);
            Controller->CancelCameraDrag();
            Pawn->ResetOverview(true);
            Pawn->SetDesiredZoom(5000.f, true);
            SyncView(Pawn, Camera);
            if (!TestFalse(Label + TEXT(" is excluded from scene input"), OriginalTwinHUD->IsScenePoint(Pixel))
                || !Pointer.Move(Pixel)) return false;
            const FVector Before = Pawn->GetActorLocation();
            const FRotator RotationBefore = Pawn->GetActorRotation();
            const float ZoomBefore = Pawn->DesiredZoom;
            Controller->InputKey(FInputKeyParams(EKeys::RightMouseButton, IE_Pressed, 1.0));
            TestTrue(Label + TEXT(" blocks starting native pan"),
                Controller->DragMode == EGHSWarehouseDragMode::None && !Pawn->IsPreciseMouseDragging);
            Controller->InputKey(FInputKeyParams(EKeys::MouseWheelAxis, 1.0, FrameSeconds, 1));
            CameraFrame(Pawn, Camera);
            TestTrue(Label + TEXT(" blocks wheel and leaves actual and desired pose unchanged"),
                Pawn->GetActorLocation().Equals(Before, .01) && Pawn->DesiredLocation.Equals(Before, .01)
                && Pawn->GetActorRotation().Equals(RotationBefore, .001) && Pawn->DesiredRotation.Equals(RotationBefore, .001)
                && FMath::IsNearlyEqual(Pawn->DesiredZoom, ZoomBefore, .01f)
                && FMath::IsNearlyEqual(Pawn->SpringArmComponent->TargetArmLength, ZoomBefore, .01f));
            if (!Pointer.Move(First)) return false;
            Controller->InputKey(FInputKeyParams(EKeys::RightMouseButton, IE_Pressed, 1.0));
            TestTrue(Label + TEXT(" starts a valid scene pan before crossing UI"), Pawn->IsPreciseMouseDragging);
            if (!Pointer.Move(Pixel, true)) return false;
            TestFalse(Label + TEXT(" rejects an active pan cursor"), Controller->HasValidMapDragCursor());
            CameraFrame(Pawn, Camera);
            TestTrue(Label + TEXT(" cancels before the plugin moves through UI"),
                Controller->DragMode == EGHSWarehouseDragMode::None && !Pawn->IsPreciseMouseDragging
                && Pawn->GetActorLocation().Equals(Before, .01) && Pawn->DesiredLocation.Equals(Before, .01));
            CheckGround(Label);
            ++BlockedCases;
        }
        TestEqual(TEXT("Header, side panel and scene search all block map input"), BlockedCases, 3);
    }

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
    if (OriginalTwinHUD)
    {
        TestEqual(TEXT("Map navigation preserves Twin selection before the explicit overview reset"),
            OriginalTwinHUD->SelectedId, OriginalSelection);
        TArray<FString> CurrentDeviceIds;
        TestTrue(TEXT("Map navigation preserves registered Twin equipment and facilities"),
            SnapshotDeviceIds(OriginalTwinHUD, CurrentDeviceIds) && CurrentDeviceIds == OriginalDeviceIds);
        const FVector2D Pixels(Size.X, Size.Y);
        const float Scale = OriginalTwinHUD->GetHUDScale();
        const FVector2D LogicalSize = Pixels / Scale;
        const auto Destination = FGHSTwinLayout::Calculate(LogicalSize);
        const FVector2D ExpectedPixel = (Destination.ScenePosition + Destination.SceneSize * .5) * Scale;
        const FVector ExpectedPivot(Pawn->OverviewCenter.X, Pawn->OverviewCenter.Y, 0);
        const FRotator ExpectedRotation(Pawn->OverviewPitch, Pawn->OverviewYaw, 0);
        const float ExpectedZoom = FMath::Clamp(float(Pawn->OverviewDistance * LogicalSize.X / Destination.SceneSize.X),
            Pawn->MinimumZoom, Pawn->MaximumZoom);
        const FVector BeforeHome = Pawn->GetActorLocation();
        const float BeforeHomeZoom = Pawn->SpringArmComponent->TargetArmLength;
        Controller->InputKey(FInputKeyParams(EKeys::Home, IE_Pressed, 1.0));
        TestTrue(TEXT("Twin Home begins the production overview flight"), Pawn->IsPoseTransitionActive());
        TestTrue(TEXT("Twin Home does not teleport the actual camera on input"),
            Pawn->GetActorLocation().Equals(BeforeHome, .01)
            && FMath::IsNearlyEqual(Pawn->SpringArmComponent->TargetArmLength, BeforeHomeZoom, .01f));
        for (int32 Frame = 0; Frame < 120 && Pawn->IsPoseTransitionActive(); ++Frame) CameraFrame(Pawn, Camera);
        TestFalse(TEXT("Twin Home flight completes within two seconds"), Pawn->IsPoseTransitionActive());
        TestTrue(TEXT("Twin Home restores actual and desired ground overview pivot"),
            Pawn->GetActorLocation().Equals(ExpectedPivot, .01) && Pawn->DesiredLocation.Equals(ExpectedPivot, .01)
            && Pawn->GetFocusTarget().Equals(ExpectedPivot, .01));
        TestTrue(TEXT("Twin Home restores actual and desired overview orientation without banking"),
            Pawn->GetActorRotation().Equals(ExpectedRotation, .001) && Pawn->DesiredRotation.Equals(ExpectedRotation, .001));
        TestTrue(TEXT("Twin Home fits overview zoom to the unobscured scene width"),
            FMath::IsNearlyEqual(Pawn->DesiredZoom, ExpectedZoom, .01f)
            && FMath::IsNearlyEqual(Pawn->SpringArmComponent->TargetArmLength, ExpectedZoom, .01f));
        TestTrue(TEXT("Twin Home retains scene framing and a ground pivot"),
            Pawn->IsOverviewFraming() && !Pawn->UsesObjectPivot() && Pawn->CaptureReplayPose().UseFraming);
        TestTrue(TEXT("Twin Home has no target offset and has reached its framing socket offset"),
            Pawn->DesiredTargetOffset.IsNearlyZero(.001) && Pawn->SpringArmComponent->TargetOffset.IsNearlyZero(.001)
            && Pawn->DesiredSocketOffset.Equals(Pawn->SpringArmComponent->SocketOffset, .01));
        // An independent live projection verifies the visible result, including
        // the deliberate nonzero socket offset needed to avoid the side panel.
        CheckAnchor(TEXT("Twin Home overview is centered in the visible scene"), ExpectedPivot, ExpectedPixel);
        const FVector FinishedSocket = Pawn->SpringArmComponent->SocketOffset;
        for (int32 Frame = 0; Frame < 8; ++Frame) CameraFrame(Pawn, Camera);
        TestTrue(TEXT("Twin Home final pose remains stable after the flight"),
            Pawn->GetActorLocation().Equals(ExpectedPivot, .01) && Pawn->GetActorRotation().Equals(ExpectedRotation, .001)
            && FMath::IsNearlyEqual(Pawn->SpringArmComponent->TargetArmLength, ExpectedZoom, .01f)
            && Pawn->SpringArmComponent->SocketOffset.Equals(FinishedSocket, .01));
        CheckAnchor(TEXT("Twin Home settled framing"), ExpectedPivot, ExpectedPixel);
        TestTrue(TEXT("Existing Twin HUD object is preserved"), Controller->TwinHUDWidget.Get() == OriginalTwinHUD);
        TestTrue(TEXT("Twin Home explicitly clears selection"), OriginalTwinHUD->SelectedId.IsEmpty());
        TestTrue(TEXT("Twin Home preserves registered device identities"),
            SnapshotDeviceIds(OriginalTwinHUD, CurrentDeviceIds) && CurrentDeviceIds == OriginalDeviceIds);
    }
    else
    {
        Controller->InputKey(FInputKeyParams(EKeys::Home, IE_Pressed, 1.0));
        TestTrue(TEXT("Home restores ground overview center"), Pawn->DesiredLocation.Equals(FVector(Pawn->OverviewCenter.X, Pawn->OverviewCenter.Y, 0), 0.001));
        TestTrue(TEXT("Home restores orientation"), Pawn->DesiredRotation.Equals(FRotator(Pawn->OverviewPitch, Pawn->OverviewYaw, 0), 0.001));
        TestTrue(TEXT("Home restores distance"), FMath::IsNearlyEqual(Pawn->DesiredZoom, Pawn->OverviewDistance, 0.01f));
        CheckGround(TEXT("Home"));
        TestTrue(TEXT("Existing HUD object is preserved"), Controller->TruckHUDWidget.Get() == OriginalTruckHUD);
        TestEqual(TEXT("HUD truck count is preserved"), OriginalTruckHUD->GetRegisteredTruckCount(), OriginalTruckCount);
        TestEqual(TEXT("HUD selection is preserved"), OriginalTruckHUD->GetSelectedTruckId(), OriginalSelection);
    }
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
