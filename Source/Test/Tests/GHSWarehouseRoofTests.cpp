#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseRoofComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "Misc/AutomationTest.h"
#include <limits>

namespace GHSWarehouseRoofTests
{
constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofOpeningClock,
    "GHS.WarehouseRoof.ClosedUntilHalfSecondAndResetCancels", GHSWarehouseRoofTests::Flags)
bool FGHSRoofOpeningClock::RunTest(const FString&)
{
    FGHSWarehouseRoofTransition State;
    TestTrue(TEXT("Initial state has a roof"), State.IsClosed());
    TestFalse(TEXT("Initial state forbids interior access"), State.IsOpen());
    State.Open();
    TestTrue(TEXT("Click starts opening"), State.IsOpening());
    State.Advance(.25f);
    TestEqual(TEXT("Shared material progress at midpoint"), State.Progress(), .5f);
    TestFalse(TEXT("Interior still blocked at midpoint"), State.IsOpen());
    State.Open();
    TestEqual(TEXT("A repeated click does not restart the clock"), State.Progress(), .5f);
    State.Advance(.249f);
    TestFalse(TEXT("Interior still blocked just before 0.5s"), State.IsOpen());
    State.Advance(.0011f);
    TestTrue(TEXT("Roof is fully open at 0.5s"), State.IsOpen());
    TestEqual(TEXT("Progress clamps at complete"), State.Progress(), 1.f);
    State.Restore();
    TestTrue(TEXT("Reset immediately restores closed state"), State.IsClosed());
    State.Open();
    State.Advance(.2f);
    State.Restore();
    State.Advance(10.f);
    TestTrue(TEXT("Cancelled opening never completes later"), State.IsClosed());
    State.Open();
    State.Advance(-.1f);
    State.Advance(std::numeric_limits<float>::quiet_NaN());
    TestEqual(TEXT("Invalid deltas do not poison animation"), State.Progress(), 0.f);
    State.Advance(2.f);
    TestTrue(TEXT("A long frame completes, without overshoot"), State.IsOpen());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofRayShape,
    "GHS.WarehouseRoof.PickingPreservesOfficeNotchAndTransform", GHSWarehouseRoofTests::Flags)
bool FGHSRoofRayShape::RunTest(const FString&)
{
    const FTransform Identity = FTransform::Identity;
    TestTrue(TEXT("Main roof can be clicked without physics collision"),
        UGHSWarehouseRoofComponent::RayHitsRoofFootprint(FVector(0,0,5000),FVector(0,0,-1),Identity));
    TestTrue(TEXT("Office wing is included"),
        UGHSWarehouseRoofComponent::RayHitsRoofFootprint(FVector(-22000,7000,5000),FVector(0,0,-1),Identity));
    TestFalse(TEXT("Office notch is not a bounding-box false positive"),
        UGHSWarehouseRoofComponent::RayHitsRoofFootprint(FVector(0,7000,5000),FVector(0,0,-1),Identity));
    TestFalse(TEXT("Diagonal southeast cut is excluded"),
        UGHSWarehouseRoofComponent::RayHitsRoofFootprint(FVector(22500,5800,5000),FVector(0,0,-1),Identity));
    TestFalse(TEXT("Ray pointing away does not hit"),
        UGHSWarehouseRoofComponent::RayHitsRoofFootprint(FVector(0,0,5000),FVector(0,0,1),Identity));
    TestFalse(TEXT("Parallel ray does not hit"),
        UGHSWarehouseRoofComponent::RayHitsRoofFootprint(FVector(0,0,5000),FVector(1,0,0),Identity));
    const FTransform Moved(FRotator(0,37,0),FVector(400,-600,170),FVector(1.2,.8,1.1));
    TestTrue(TEXT("Picking follows roof rotation, scale and translation"),
        UGHSWarehouseRoofComponent::RayHitsRoofFootprint(Moved.TransformPosition(FVector(0,0,5000)),
            Moved.TransformVector(FVector(0,0,-1)).GetSafeNormal(),Moved));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofRuntimeLifecycle,
    "GHS.WarehouseRoof.MaterialOverrideAndIdleTickLifecycle", GHSWarehouseRoofTests::Flags)
bool FGHSRoofRuntimeLifecycle::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if (!TestNotNull(TEXT("Fixture world"),World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    AStaticMeshActor* Roof=World->SpawnActor<AStaticMeshActor>();
    Roof->Tags.Add(TEXT("GHS_WarehouseRoof"));
    auto* Mesh=Roof->GetStaticMeshComponent();
    Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
    auto* Original=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/GHSZcoolSmartFactory/OfficeFacade/Materials/M_GHSFacade_Glass.M_GHSFacade_Glass"));
    TestNotNull(TEXT("User skylight material is available"),Original);
    Mesh->SetMaterial(0,Original);
    AStaticMeshActor* Facade=World->SpawnActor<AStaticMeshActor>();
    Facade->Tags.Add(TEXT("GHS_OfficeFacade"));
    Facade->GetStaticMeshComponent()->SetStaticMesh(Mesh->GetStaticMesh());
    AActor* Owner=World->SpawnActor<AActor>();
    auto* Component=NewObject<UGHSWarehouseRoofComponent>(Owner);
    Owner->AddInstanceComponent(Component);
    Component->RegisterComponent();
    Component->InitializeRoof();
    TestTrue(TEXT("Tagged roof found"),Component->HasRoof());
    TestFalse(TEXT("Closed state has no ticking cost"),Component->IsComponentTickEnabled());
    TestTrue(TEXT("Source component material preserved initially"),Mesh->GetMaterial(0)==Original);
    Component->OpenRoof();
    TestTrue(TEXT("Dissolve enables tick only while needed"),Component->IsComponentTickEnabled());
    TestFalse(TEXT("Interior stays locked during dissolve"),Component->IsInteriorAvailable());
    TestTrue(TEXT("Opening actually installs the dissolve material"),Mesh->GetMaterial(0)!=Original);
    if(Mesh->GetMaterial(0))
        TestTrue(TEXT("Dissolve uses masked shading, not translucent sorting"),Mesh->GetMaterial(0)->GetBlendMode()==BLEND_Masked);
    Component->TickComponent(.25f,LEVELTICK_All,nullptr);
    Component->RestoreRoof();
    TestFalse(TEXT("Mid-animation reset disables tick"),Component->IsComponentTickEnabled());
    TestTrue(TEXT("Reset restores exact user material override object"),Mesh->GetMaterial(0)==Original);
    TestFalse(TEXT("Reset restores roof visibility"),Roof->IsHidden());
    Component->OpenRoof();
    Component->TickComponent(.5f,LEVELTICK_All,nullptr);
    TestTrue(TEXT("Completed opening hides the complete actor"),Roof->IsHidden());
    TestTrue(TEXT("Interior available only after hidden"),Component->IsInteriorAvailable());
    TestFalse(TEXT("Open state has no ticking cost"),Component->IsComponentTickEnabled());
    Component->RestoreRoof();
    TestTrue(TEXT("Second reset still preserves the original material"),Mesh->GetMaterial(0)==Original);
    Component->SetBuildingVisible(false);
    Component->TickComponent(.2f,LEVELTICK_All,nullptr);
    TestFalse(TEXT("Shell remains visible during opening lock"),Facade->IsHidden());
    Component->SetBuildingVisible(true);
    Component->TickComponent(.5f,LEVELTICK_All,nullptr);
    TestFalse(TEXT("Last toggle wins over delayed shell hide"),Facade->IsHidden());
    TestTrue(TEXT("Showing shell does not reclose roof"),Component->IsInteriorAvailable());
    Component->SetBuildingVisible(false);
    TestTrue(TEXT("Open shell hides immediately"),Facade->IsHidden());
    Component->SetBuildingVisible(true);Component->RestoreRoof();
    TestFalse(TEXT("Overview restores shell"),Facade->IsHidden());
    TestTrue(TEXT("Overview closes roof"),Component->IsRoofClosed());
    GEngine->DestroyWorldContext(World);
    World->DestroyWorld(false);
    return true;
}

#endif
