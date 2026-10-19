#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSWarehouseCameraPawn.h"
#include "../GHSWarehousePlayerController.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMapDragState,
    "GHS.WarehouseCamera.MapDrag.Cancellation",
    EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FGHSMapDragState::RunTest(const FString& Parameters)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    auto* Pawn = World->SpawnActor<AGHSWarehouseCameraPawn>();
    auto* Controller = World->SpawnActor<AGHSWarehousePlayerController>();
    Controller->Possess(Pawn);
    Pawn->ResetOverview(true);
    Controller->DragMode = EGHSWarehouseDragMode::Pan;
    TestFalse(TEXT("Missing local viewport cannot start map dragging"), Controller->BeginMapDrag());
    TestTrue(TEXT("Failed grab clears old pan state"), Controller->DragMode == EGHSWarehouseDragMode::None);
    Controller->DragMode = EGHSWarehouseDragMode::Orbit;
    TestFalse(TEXT("Map dragging cannot steal an orbit gesture"), Controller->BeginMapDrag());
    TestTrue(TEXT("Rejected grab preserves active orbit"), Controller->DragMode == EGHSWarehouseDragMode::Orbit);

    // Releasing a grab must stop the plugin and cancel any pending movement.
    const FVector Actual(1234, -2345, 0);
    Pawn->SetDesiredLocation(Actual, true);
    Pawn->SetDesiredLocation(Actual + FVector(300, 200, 0));
    Pawn->IsPreciseMouseDragging = true;
    Controller->DragMode = EGHSWarehouseDragMode::Pan;
    Controller->CancelCameraDrag();
    TestFalse(TEXT("Cancellation disables native plugin dragging"), Pawn->IsPreciseMouseDragging);
    TestTrue(TEXT("Release freezes the visible pivot, not the pending target"), Pawn->DesiredLocation.Equals(Actual));
    for (int Frame = 0; Frame < 30; ++Frame)
    {
        Pawn->LastDeltaTime = 1.0f / 60.0f;
        Pawn->Tick(1.0f / 60.0f);
    }
    TestTrue(TEXT("No movement or height drift after release"), Pawn->GetActorLocation().Equals(Actual));
    Controller->CancelCameraDrag();
    TestTrue(TEXT("Repeated cancellation stays stable"), Pawn->GetActorLocation().Equals(Actual));

    Controller->UnPossess();
    GEngine->DestroyWorldContext(World);
    World->DestroyWorld(false);
    return true;
}
#endif
