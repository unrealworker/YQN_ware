#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseRoofComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "GHSAutomationTestFlags.h"
#include <limits>

namespace GHSWarehouseRoofTests
{
constexpr auto Flags = GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
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

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRRoofRayShape,
    "GHS.WarehouseRoof.MPRPickingPreservesSteppedFootprint", GHSWarehouseRoofTests::Flags)
bool FMPRRoofRayShape::RunTest(const FString&)
{
    const auto Hit=[](double X,double Y)
    { return UGHSWarehouseRoofComponent::RayHitsMPRRoofFootprint(FVector(X,Y,5000),FVector(0,0,-1),FTransform::Identity); };
    TestTrue(TEXT("Main roof is clickable without physics"),Hit(0,0));
    TestTrue(TEXT("Northwest projecting corner included"),Hit(-17500,-8000));
    TestFalse(TEXT("North central setback excluded"),Hit(0,-8000));
    TestTrue(TEXT("Eastern first tier included"),Hit(17500,1000));
    TestFalse(TEXT("Outside eastern first step excluded"),Hit(17500,3000));
    TestTrue(TEXT("Eastern middle tier included"),Hit(16000,4000));
    TestFalse(TEXT("Outside middle step excluded"),Hit(16000,6000));
    TestTrue(TEXT("Eastern lower tier included"),Hit(14500,6000));
    TestFalse(TEXT("Outside lowest step excluded"),Hit(14500,7500));
    TestTrue(TEXT("Southwest projecting corner included"),Hit(-17500,9000));
    TestFalse(TEXT("Southern apron excluded"),Hit(0,9000));
    TestFalse(TEXT("Background warehouse excluded"),Hit(0,-20000));
    TestFalse(TEXT("Upward ray is not a hit"),UGHSWarehouseRoofComponent::RayHitsMPRRoofFootprint(
        FVector(0,0,5000),FVector(0,0,1),FTransform::Identity));
    TestFalse(TEXT("Parallel ray is not a hit"),UGHSWarehouseRoofComponent::RayHitsMPRRoofFootprint(
        FVector(0,0,5000),FVector(1,0,0),FTransform::Identity));
    const FTransform Moved(FRotator(0,37,0),FVector(400,-600,170),FVector(1.2,.8,1.1));
    TestTrue(TEXT("MPR click plane follows placement transform"),UGHSWarehouseRoofComponent::RayHitsMPRRoofFootprint(
        Moved.TransformPosition(FVector(0,0,5000)),Moved.TransformVector(FVector(0,0,-1)).GetSafeNormal(),Moved));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRRoofMultiPartLifecycle,
    "GHS.WarehouseRoof.MPRSkinsSolarAndInstancedLightsShareRevealAndRestore", GHSWarehouseRoofTests::Flags)
bool FMPRRoofMultiPartLifecycle::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("Fixture world"),World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    auto* Skin=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/MPRWarehouse/ReferenceV4/Architecture/Meshes/SM_MPR4_RoofSkin_00.SM_MPR4_RoofSkin_00"));
    auto* Solar=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/MPRWarehouse/SolarUnits20261106/Meshes/SM_MPRSU_SolarBank_00_0.SM_MPRSU_SolarBank_00_0"));
    auto* Light=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/MPRWarehouse/ReferenceV4/Architecture/Meshes/SM_MPR4_RoofLight.SM_MPR4_RoofLight"));
    TestNotNull(TEXT("Real MPR skin asset"),Skin);TestNotNull(TEXT("Real MPR photovoltaic asset"),Solar);TestNotNull(TEXT("Real MPR roof light asset"),Light);
    AStaticMeshActor* Main=World->SpawnActor<AStaticMeshActor>();Main->Tags.Add(TEXT("MPR_Roof"));
    Main->GetStaticMeshComponent()->SetStaticMesh(Skin);
    AStaticMeshActor* PV=World->SpawnActor<AStaticMeshActor>();PV->Tags.Add(TEXT("MPR_Roof"));
    PV->GetStaticMeshComponent()->SetStaticMesh(Solar);
    AStaticMeshActor* HiddenPV=World->SpawnActor<AStaticMeshActor>();HiddenPV->Tags.Add(TEXT("MPR_Roof"));
    HiddenPV->GetStaticMeshComponent()->SetStaticMesh(Solar);
    HiddenPV->SetActorHiddenInGame(true);HiddenPV->GetStaticMeshComponent()->SetVisibility(false);
    HiddenPV->GetStaticMeshComponent()->SetHiddenInGame(true);
    AActor* Lights=World->SpawnActor<AActor>();Lights->Tags.Add(TEXT("MPR_Roof"));
    auto* Instances=NewObject<UHierarchicalInstancedStaticMeshComponent>(Lights);
    Lights->AddInstanceComponent(Instances);Lights->SetRootComponent(Instances);
    Instances->SetStaticMesh(Light);Instances->RegisterComponent();
    Instances->AddInstance(FTransform(FVector(-12000,1000,1340)));
    Instances->AddInstance(FTransform(FVector(-10000,2000,1340)));
    AStaticMeshActor* Context=World->SpawnActor<AStaticMeshActor>();
    Context->GetStaticMeshComponent()->SetStaticMesh(Skin);
    // Unrelated, untagged background buildings must not share the reveal.
    auto* Source=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/MPRWarehouse/SiteComplete/Materials/MI_SC_MPR4_RoofMembrane.MI_SC_MPR4_RoofMembrane"));
    TestNotNull(TEXT("MPR material override source"),Source);
    auto* Original=Source?UMaterialInstanceDynamic::Create(Source,Main):nullptr;
    const FLinearColor UserTint(.41f,.63f,.71f,1.f);
    if(Original) {Original->SetVectorParameterValue(TEXT("Tint"),UserTint);Original->SetScalarParameterValue(TEXT("Roughness"),.37f);}
    Main->GetStaticMeshComponent()->SetMaterial(0,Original);
    const TArray<UStaticMeshComponent*> Meshes={Main->GetStaticMeshComponent(),PV->GetStaticMeshComponent(),Instances,HiddenPV->GetStaticMeshComponent()};
    TArray<TArray<UMaterialInterface*>> Sources;
    for(auto* Mesh:Meshes)
    {
        TArray<UMaterialInterface*> Row;
        for(int32 Slot=0;Slot<Mesh->GetNumMaterials();++Slot) Row.Add(Mesh->GetMaterial(Slot));
        Sources.Add(Row);
    }
    AActor* Owner=World->SpawnActor<AActor>();
    auto* Component=NewObject<UGHSWarehouseRoofComponent>(Owner);
    Owner->AddInstanceComponent(Component);Component->RegisterComponent();Component->InitializeRoof();Owner->DispatchBeginPlay();
    TestTrue(TEXT("MPR roof group discovered"),Component->HasRoof());
    TestTrue(TEXT("MPR opening resolves every material template"),Component->OpenRoof());
    Component->TickComponent(.4f,LEVELTICK_All,nullptr);
    FVector4 FirstCenter(0,0,0,0),FirstAxis(0,0,0,0);bool bFirst=true;
    for(auto* Mesh:Meshes) for(int32 Slot=0;Slot<Mesh->GetNumMaterials();++Slot)
    {
        auto* MID=Cast<UMaterialInstanceDynamic>(Mesh->GetMaterial(Slot));
        if(!TestNotNull(TEXT("Every skin, photovoltaic and HISM slot has a private reveal"),MID)) continue;
        TestTrue(TEXT("Every MPR reveal is masked"),MID->GetBlendMode()==BLEND_Masked);
        TestEqual(TEXT("Every slot shares the same clock"),MID->K2_GetScalarParameterValue(TEXT("RoofOpenProgress")),.5f);
        const auto Center=MID->K2_GetVectorParameterValue(TEXT("RoofCenter"));
        const auto Axis=MID->K2_GetVectorParameterValue(TEXT("RoofAxisInvExtent"));
        if(bFirst) {FirstCenter=FVector4(Center.R,Center.G,Center.B,Center.A);FirstAxis=FVector4(Axis.R,Axis.G,Axis.B,Axis.A);bFirst=false;}
        TestTrue(TEXT("Separate pieces use the same scan center"),FVector4(Center.R,Center.G,Center.B,Center.A).Equals(FirstCenter));
        TestTrue(TEXT("Separate pieces use the same scan axis and extent"),FVector4(Axis.R,Axis.G,Axis.B,Axis.A).Equals(FirstAxis));
    }
    if(auto* MID=Cast<UMaterialInstanceDynamic>(Main->GetStaticMeshComponent()->GetMaterial(0)))
        TestTrue(TEXT("MPR private material preserves the user tint"),MID->K2_GetVectorParameterValue(TEXT("Tint")).Equals(UserTint));
    const auto Saved=Component->CaptureReplayState();
    Component->TickComponent(.4f,LEVELTICK_All,nullptr);
    TestTrue(TEXT("All three roof actors hide at the same endpoint"),Main->IsHidden() && PV->IsHidden() && Lights->IsHidden());
    TestFalse(TEXT("Background warehouse stays visible"),Context->IsHidden());
    TestFalse(TEXT("Opened group does not tick"),Component->IsComponentTickEnabled());
    TestEqual(TEXT("HISM instances are preserved"),Instances->GetInstanceCount(),2);
    Component->RestoreReplayState(Saved,true);
    TestEqual(TEXT("Replay restores partial reveal"),Component->GetOpenProgress(),.5f);
    TestTrue(TEXT("Replay restores every roof actor visibility"),!Main->IsHidden() && !PV->IsHidden() && !Lights->IsHidden());
    Component->RestoreRoof();Component->TickComponent(.275f,LEVELTICK_All,nullptr);
    TestTrue(TEXT("Animated close completes"),Component->IsRoofClosed());
    for(int32 I=0;I<Meshes.Num();++I) for(int32 Slot=0;Slot<Sources[I].Num();++Slot)
        TestTrue(TEXT("Close restores each original material object"),Meshes[I]->GetMaterial(Slot)==Sources[I][Slot]);
    Component->OpenRoof();Component->TickComponent(.2f,LEVELTICK_All,nullptr);Component->ResetForWorld();
    TestFalse(TEXT("World teardown detaches the whole group"),Component->HasRoof());
    TestFalse(TEXT("World teardown stops ticking"),Component->IsComponentTickEnabled());
    for(int32 I=0;I<Meshes.Num();++I) for(int32 Slot=0;Slot<Sources[I].Num();++Slot)
        TestTrue(TEXT("Teardown restores each original material object"),Meshes[I]->GetMaterial(Slot)==Sources[I][Slot]);
    TestTrue(TEXT("Teardown restores every actor"),!Main->IsHidden() && !PV->IsHidden() && !Lights->IsHidden());
    TestTrue(TEXT("Teardown preserves authored hidden and invisible parts"),HiddenPV->IsHidden() &&
        !HiddenPV->GetStaticMeshComponent()->IsVisible() && HiddenPV->GetStaticMeshComponent()->bHiddenInGame);
    GEngine->DestroyWorldContext(World);World->DestroyWorld(false);
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

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSRoofLightingLifecycle,
    "GHS.WarehouseRoof.ScanReleasesOcclusionAndRestoresAuthoredLighting", GHSWarehouseRoofTests::Flags)
bool FGHSRoofLightingLifecycle::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("Fixture world"),World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    TArray<UStaticMeshComponent*> Meshes;
    for(int32 I=0;I<2;++I)
    {
        auto* Actor=World->SpawnActor<AStaticMeshActor>();
        Actor->Tags.Add(TEXT("GHS_WarehouseRoof"));
        auto* Mesh=Actor->GetStaticMeshComponent();
        Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
        Mesh->SetMaterial(0,LoadObject<UMaterialInterface>(nullptr,
            TEXT("/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_Roof.M_GHSRoof_Roof")));
        // Mixed authored settings catch a blanket enable-on-restore regression.
        Mesh->SetCastShadow(I==0);Mesh->SetCastHiddenShadow(I==0);
        Mesh->SetAffectDistanceFieldLighting(I==0);Mesh->SetAffectDynamicIndirectLighting(I==0);
        Mesh->SetAffectIndirectLightingWhileHidden(I==0);Mesh->SetVisibleInRayTracing(I==0);
        Mesh->ShadowCacheInvalidationBehavior=I==0?EShadowCacheInvalidationBehavior::Rigid:EShadowCacheInvalidationBehavior::Static;
        Meshes.Add(Mesh);
    }
    auto* Owner=World->SpawnActor<AActor>();
    auto* Component=NewObject<UGHSWarehouseRoofComponent>(Owner);
    Owner->AddInstanceComponent(Component);Component->RegisterComponent();Component->InitializeRoof();Owner->DispatchBeginPlay();
    const auto CheckRestored=[&]()
    {
        for(int32 I=0;I<Meshes.Num();++I)
        {
            const auto* Mesh=Meshes[I];const bool Expected=I==0;
            TestEqual(TEXT("Authored shadow setting restored"),bool(Mesh->CastShadow),Expected);
            TestEqual(TEXT("Authored hidden shadow restored"),bool(Mesh->bCastHiddenShadow),Expected);
            TestEqual(TEXT("Authored distance field lighting restored"),bool(Mesh->bAffectDistanceFieldLighting),Expected);
            TestEqual(TEXT("Authored dynamic indirect lighting restored"),bool(Mesh->bAffectDynamicIndirectLighting),Expected);
            TestEqual(TEXT("Authored hidden indirect lighting restored"),bool(Mesh->bAffectIndirectLightingWhileHidden),Expected);
            TestEqual(TEXT("Authored ray tracing visibility restored"),bool(Mesh->bVisibleInRayTracing),Expected);
            TestTrue(TEXT("Authored shadow cache behavior restored"),Mesh->ShadowCacheInvalidationBehavior==
                (Expected?EShadowCacheInvalidationBehavior::Rigid:EShadowCacheInvalidationBehavior::Static));
        }
    };
    const auto CheckReveal=[&](bool bOpen)
    {
        for(int32 I=0;I<Meshes.Num();++I)
        {
            const auto* Mesh=Meshes[I];
            TestFalse(TEXT("A revealed roof cannot occlude distance field light"),Mesh->bAffectDistanceFieldLighting);
            TestFalse(TEXT("A revealed roof cannot occlude Lumen indirect light"),Mesh->bAffectDynamicIndirectLighting);
            TestFalse(TEXT("A revealed roof cannot remain in hidden GI"),Mesh->bAffectIndirectLightingWhileHidden);
            TestFalse(TEXT("A revealed roof cannot remain opaque in ray tracing"),Mesh->bVisibleInRayTracing);
            TestFalse(TEXT("A revealed roof cannot cast hidden shadows"),Mesh->bCastHiddenShadow);
            TestEqual(TEXT("Masked shadow remains during scan, but is absent after opening"),bool(Mesh->CastShadow),!bOpen && I==0);
            if(!bOpen) TestTrue(TEXT("Opacity-only animation invalidates VSM every frame"),
                Mesh->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Always);
        }
    };
    CheckRestored();
    const auto Closed=Component->CaptureReplayState();
    TestTrue(TEXT("Opening succeeds"),Component->OpenRoof());CheckReveal(false);
    Component->TickComponent(.4f,LEVELTICK_All,nullptr);CheckReveal(false);
    const auto HalfOpen=Component->CaptureReplayState();
    Component->RestoreRoof();CheckReveal(false);
    Component->TickComponent(.275f,LEVELTICK_All,nullptr);CheckRestored();
    Component->RestoreReplayState(HalfOpen,true);CheckReveal(false);
    Component->TickComponent(.4f,LEVELTICK_All,nullptr);CheckReveal(true);
    TestFalse(TEXT("Open roof has no continuous shadow invalidation tick"),Component->IsComponentTickEnabled());
    const auto Open=Component->CaptureReplayState();
    Component->RestoreRoof(false);CheckRestored();
    Component->RestoreReplayState(Open,true);CheckReveal(true);
    Component->RestoreRoof();CheckReveal(false);
    Component->TickComponent(.55f,LEVELTICK_All,nullptr);CheckRestored();
    Component->RestoreReplayState(HalfOpen,true);CheckReveal(false);
    Component->RestoreReplayState(Closed,true);CheckRestored();
    Component->OpenRoof();CheckReveal(false);Component->ResetForWorld();CheckRestored();
    TestFalse(TEXT("World teardown leaves no lighting update tick"),Component->IsComponentTickEnabled());
    GEngine->DestroyWorldContext(World);World->DestroyWorld(false);
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
