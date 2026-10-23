#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseRoofComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/AutomationTest.h"
#include <limits>

namespace GHSWarehouseRoofTests
{
constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofOpeningClock,
    "GHS.WarehouseRoof.ManualRevealKeepsInteriorLockedUntilComplete", GHSWarehouseRoofTests::Flags)
bool FGHSRoofOpeningClock::RunTest(const FString&)
{
    FGHSWarehouseRoofTransition State;
    TestTrue(TEXT("Initial state has a roof"), State.IsClosed());
    TestFalse(TEXT("Initial state forbids interior access"), State.IsOpen());
    State.Open();
    TestTrue(TEXT("Click starts opening"), State.IsOpening());
    State.Advance(.4f);
    TestEqual(TEXT("Shared material progress at midpoint"), State.Progress(), .5f);
    TestFalse(TEXT("Interior still blocked at midpoint"), State.IsOpen());
    State.Open();
    TestEqual(TEXT("A repeated click does not restart the clock"), State.Progress(), .5f);
    State.Advance(.399f);
    TestFalse(TEXT("Interior still blocked just before 0.8s"), State.IsOpen());
    State.Advance(.0011f);
    TestTrue(TEXT("Roof is fully open at 0.8s"), State.IsOpen());
    TestEqual(TEXT("Progress clamps at complete"), State.Progress(), 1.f);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofReversalClock,
    "GHS.WarehouseRoof.ReversalPreservesApertureAndRemainingTravel", GHSWarehouseRoofTests::Flags)
bool FGHSRoofReversalClock::RunTest(const FString&)
{
    FGHSWarehouseRoofTransition State;
    State.Open();
    State.Advance(.2f);
    TestEqual(TEXT("Opening eases in at quarter time"),State.Progress(),.15625f);
    State.Restore();
    TestTrue(TEXT("Reset enters closing"),State.IsClosing());
    TestFalse(TEXT("Closing continues to lock the interior"),State.IsOpen());
    TestEqual(TEXT("Reversal has no aperture jump"),State.Progress(),.15625f);
    State.Advance(.055f);
    const float PartiallyClosed=State.Progress();
    TestTrue(TEXT("Closing moves toward the center"),PartiallyClosed>0.f && PartiallyClosed<.15625f);
    State.Restore();
    TestEqual(TEXT("Repeated reset preserves closing progress"),State.Progress(),PartiallyClosed);
    State.Open();
    TestTrue(TEXT("Navigation can reopen while closing"),State.IsOpening());
    TestEqual(TEXT("Reopening has no aperture jump"),State.Progress(),PartiallyClosed);
    State.Advance(.6801f);
    TestTrue(TEXT("Reopened roof completes only its remaining travel"),State.IsOpen());
    State.Restore();
    TestEqual(TEXT("Closing a fully open roof starts fully cut away"),State.Progress(),1.f);
    State.Advance(.275f);
    TestEqual(TEXT("Full closing reaches halfway after 0.275s"),State.Progress(),.5f);
    State.Restore();
    State.Advance(.274f);
    TestTrue(TEXT("Closing is not finished early"),State.IsClosing());
    State.Advance(.0011f);
    TestTrue(TEXT("Full closing finishes at 0.55s without repeat delay"),State.IsClosed());
    TestEqual(TEXT("Closed progress is exact"),State.Progress(),0.f);
    TestFalse(TEXT("Closed clock is idle"),State.IsTransitioning());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofFastClock,
    "GHS.WarehouseRoof.FastUpgradeNeverRestartsOrSlowsOpening", GHSWarehouseRoofTests::Flags)
bool FGHSRoofFastClock::RunTest(const FString&)
{
    FGHSWarehouseRoofTransition State;
    State.Open(true);
    State.Advance(.25f);
    TestEqual(TEXT("Fast opening midpoint"),State.Progress(),.5f);
    State.Open();
    State.Advance(.249f);
    TestTrue(TEXT("Manual repeat cannot finish fast animation early"),State.IsOpening());
    State.Advance(.0011f);
    TestTrue(TEXT("Manual repeat cannot slow fast animation"),State.IsOpen());

    State.Restore(false);
    State.Open();
    State.Advance(.2f);
    const float BeforeUpgrade=State.Progress();
    State.Open(true);
    TestEqual(TEXT("Fast upgrade has no aperture jump"),State.Progress(),BeforeUpgrade);
    State.Advance(.1f);
    State.Open(true);
    State.Advance(.274f);
    TestTrue(TEXT("Upgraded opening remains locked just before completion"),State.IsOpening());
    State.Advance(.0011f);
    TestTrue(TEXT("Fast upgrade takes only remaining 0.375s"),State.IsOpen());
    State.Restore();
    State.Advance(.275f);
    State.Open(true);
    TestEqual(TEXT("Fast reopen retains half-open aperture"),State.Progress(),.5f);
    State.Advance(.25f);
    TestTrue(TEXT("Fast reopen completes remaining half in 0.25s"),State.IsOpen());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofClockSanitizesDelta,
    "GHS.WarehouseRoof.InvalidDeltaAndImmediateRestoreRemainStable", GHSWarehouseRoofTests::Flags)
bool FGHSRoofClockSanitizesDelta::RunTest(const FString&)
{
    FGHSWarehouseRoofTransition State;
    State.Open();
    State.Advance(.4f);
    State.Advance(-.1f);
    State.Advance(0.f);
    State.Advance(std::numeric_limits<float>::quiet_NaN());
    State.Advance(std::numeric_limits<float>::infinity());
    TestEqual(TEXT("Invalid opening deltas do not poison or advance progress"),State.Progress(),.5f);
    State.Restore();
    State.Advance(-.1f);
    State.Advance(std::numeric_limits<float>::quiet_NaN());
    State.Advance(-std::numeric_limits<float>::infinity());
    TestEqual(TEXT("Invalid closing deltas do not poison or advance progress"),State.Progress(),.5f);
    State.Restore(false);
    State.Advance(10.f);
    TestTrue(TEXT("Immediate initialization/teardown cancels pending transition"),State.IsClosed());
    TestEqual(TEXT("Immediate restore has zero progress"),State.Progress(),0.f);
    State.Open();
    State.Advance(std::numeric_limits<float>::max());
    TestTrue(TEXT("Largest finite opening frame completes without overshoot"),State.IsOpen());
    State.Restore();
    State.Advance(std::numeric_limits<float>::max());
    TestTrue(TEXT("Largest finite closing frame completes without overshoot"),State.IsClosed());
    State.Open();
    State.Restore();
    TestTrue(TEXT("Reset before the first opening frame is already closed"),State.IsClosed());
    State.Open(true);
    State.Advance(.5f);
    State.Restore();
    State.Open(true);
    TestTrue(TEXT("Reopen before the first closing frame is already open"),State.IsOpen());
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
    auto* Source=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/GHSZcoolSmartFactory/OfficeFacade/Materials/M_GHSFacade_Glass.M_GHSFacade_Glass"));
    TestNotNull(TEXT("User skylight material is available"),Source);
    auto* Original=Source?UMaterialInstanceDynamic::Create(Source,Roof):nullptr;
    const FLinearColor UserTint(.17f,.43f,.79f,1.f);
    if(Original)
    {
        Original->SetScalarParameterValue(TEXT("Roughness"),.37f);
        Original->SetVectorParameterValue(TEXT("SurfaceTint"),UserTint);
    }
    Mesh->SetMaterial(0,Original);
    AStaticMeshActor* Facade=World->SpawnActor<AStaticMeshActor>();
    Facade->Tags.Add(TEXT("GHS_OfficeFacade"));
    Facade->GetStaticMeshComponent()->SetStaticMesh(Mesh->GetStaticMesh());
    AActor* Owner=World->SpawnActor<AActor>();
    auto* Component=NewObject<UGHSWarehouseRoofComponent>(Owner);
    Owner->AddInstanceComponent(Component);
    Component->RegisterComponent();
    Component->InitializeRoof();
    Owner->DispatchBeginPlay();
    TestTrue(TEXT("Tagged roof found"),Component->HasRoof());
    TestFalse(TEXT("Closed state has no ticking cost"),Component->IsComponentTickEnabled());
    TestTrue(TEXT("Source component material preserved initially"),Mesh->GetMaterial(0)==Original);
    Component->OpenRoof();
    Component->RestoreRoof();
    TestTrue(TEXT("Reset before the first frame settles closed immediately"),Component->IsRoofClosed());
    TestFalse(TEXT("No idle tick after zero-travel reset"),Component->IsComponentTickEnabled());
    Component->OpenRoof();
    TestTrue(TEXT("Dissolve enables tick only while needed"),Component->IsComponentTickEnabled());
    TestFalse(TEXT("Interior stays locked during dissolve"),Component->IsInteriorAvailable());
    TestTrue(TEXT("Opening actually installs the dissolve material"),Mesh->GetMaterial(0)!=Original);
    if(Mesh->GetMaterial(0))
        TestTrue(TEXT("Dissolve uses masked shading, not translucent sorting"),Mesh->GetMaterial(0)->GetBlendMode()==BLEND_Masked);
    auto* Dissolve=Cast<UMaterialInstanceDynamic>(Mesh->GetMaterial(0));
    if(TestNotNull(TEXT("Opening material is a private dynamic instance"),Dissolve))
    {
        TestEqual(TEXT("User roughness override is retained"),Dissolve->K2_GetScalarParameterValue(TEXT("Roughness")),.37f);
        TestTrue(TEXT("User color override is retained"),Dissolve->K2_GetVectorParameterValue(TEXT("SurfaceTint")).Equals(UserTint));
    }
    Component->TickComponent(.4f,LEVELTICK_All,nullptr);
    TestEqual(TEXT("Component shares the manual clock"),Component->GetOpenProgress(),.5f);
    if(Dissolve) TestEqual(TEXT("Material follows the same aperture"),Dissolve->K2_GetScalarParameterValue(TEXT("RoofOpenProgress")),.5f);
    Component->RestoreRoof();
    TestTrue(TEXT("Animated reset reverses with tick enabled"),Component->IsClosing() && Component->IsComponentTickEnabled());
    TestEqual(TEXT("Animated reset preserves material progress"),Component->GetOpenProgress(),.5f);
    TestTrue(TEXT("Closing retains its material instead of flashing a solid roof"),Mesh->GetMaterial(0)==Dissolve);
    TestFalse(TEXT("Closing remains locked"),Component->IsInteriorAvailable());
    Component->TickComponent(.275f,LEVELTICK_All,nullptr);
    TestTrue(TEXT("Completed close restores exact user material override object"),Mesh->GetMaterial(0)==Original);
    TestFalse(TEXT("Completed close restores roof visibility"),Roof->IsHidden());
    TestFalse(TEXT("Completed close disables tick"),Component->IsComponentTickEnabled());
    Component->OpenRoof(true);
    Component->TickComponent(.5f,LEVELTICK_All,nullptr);
    TestTrue(TEXT("Completed opening hides the complete actor"),Roof->IsHidden());
    TestTrue(TEXT("Interior available only after hidden"),Component->IsInteriorAvailable());
    TestFalse(TEXT("Open state has no ticking cost"),Component->IsComponentTickEnabled());
    TestTrue(TEXT("Open idle restores exact user material object"),Mesh->GetMaterial(0)==Original);
    Component->RestoreRoof();
    TestFalse(TEXT("Closing from open unhides the actor for the reverse scan"),Roof->IsHidden());
    TestTrue(TEXT("Closing from open reinstalls the private material"),Mesh->GetMaterial(0)==Dissolve);
    if(Dissolve) TestEqual(TEXT("First reverse frame remains fully cut away"),Dissolve->K2_GetScalarParameterValue(TEXT("RoofOpenProgress")),1.f);
    Component->OpenRoof(true);
    TestTrue(TEXT("Zero-travel reopening immediately restores access"),Component->IsInteriorAvailable());
    TestTrue(TEXT("Zero-travel reopening leaves actor hidden"),Roof->IsHidden());
    TestFalse(TEXT("No idle tick after zero-travel reopening"),Component->IsComponentTickEnabled());
    Component->RestoreRoof(false);
    TestTrue(TEXT("Immediate restore still preserves the original material"),Mesh->GetMaterial(0)==Original);
    TestFalse(TEXT("Immediate restore disables tick"),Component->IsComponentTickEnabled());
    Component->SetBuildingVisible(false);
    Component->TickComponent(.2f,LEVELTICK_All,nullptr);
    TestFalse(TEXT("Shell remains visible during opening lock"),Facade->IsHidden());
    Component->SetBuildingVisible(true);
    Component->TickComponent(.6f,LEVELTICK_All,nullptr);
    TestFalse(TEXT("Last toggle wins over delayed shell hide"),Facade->IsHidden());
    TestTrue(TEXT("Showing shell does not reclose roof"),Component->IsInteriorAvailable());
    Component->SetBuildingVisible(false);
    TestTrue(TEXT("Open shell hides immediately"),Facade->IsHidden());
    Component->SetBuildingVisible(true);Component->RestoreRoof(false);
    TestFalse(TEXT("Overview restores shell"),Facade->IsHidden());
    TestTrue(TEXT("Overview closes roof"),Component->IsRoofClosed());
    Component->OpenRoof();
    Component->TickComponent(.3f,LEVELTICK_All,nullptr);
    Component->DestroyComponent();
    TestTrue(TEXT("EndPlay restores exact user material object immediately"),Mesh->GetMaterial(0)==Original);
    TestFalse(TEXT("EndPlay leaves roof visible"),Roof->IsHidden());
    GEngine->DestroyWorldContext(World);
    World->DestroyWorld(false);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofMissingMap,
    "GHS.WarehouseRoof.MissingRoofMapDoesNotLockInteriorOrTick", GHSWarehouseRoofTests::Flags)
bool FGHSRoofMissingMap::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("Fixture world"),World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    AActor* Owner=World->SpawnActor<AActor>();
    auto* Component=NewObject<UGHSWarehouseRoofComponent>(Owner);
    Owner->AddInstanceComponent(Component);
    Component->RegisterComponent();
    Component->InitializeRoof();
    TestFalse(TEXT("No unrelated actor is treated as a roof"),Component->HasRoof());
    TestTrue(TEXT("Interior remains available on maps without roof"),Component->IsInteriorAvailable());
    TestFalse(TEXT("Missing roof cannot start an opening"),Component->OpenRoof(true));
    Component->RestoreRoof();
    Component->SetBuildingVisible(false);
    TestFalse(TEXT("Missing roof cannot leave transition state"),Component->IsTransitioning());
    TestFalse(TEXT("Missing roof never enables tick"),Component->IsComponentTickEnabled());
    GEngine->DestroyWorldContext(World);
    World->DestroyWorld(false);
    return true;
}

#endif
