#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSTwinSceneData.h"
#include "../GHSDockTruckDataComponent.h"
#include "../GHSMannedForkliftDataComponent.h"
#include "../GHSMannedForkliftIdentityLibrary.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/AutomationTest.h"

namespace GHSTwinSceneCacheTests
{
constexpr uint32 Flags=EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter;
struct FFixture
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    FFixture() { if(World && GEngine) { GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World); World->InitializeActorsForPlay(FURL()); } }
    ~FFixture() { Destroy(); }
    void Destroy() { if(World) { if(GEngine) GEngine->DestroyWorldContext(World); World->DestroyWorld(false); World=nullptr; } }
    AStaticMeshActor* Device(const TCHAR* Id,FVector Position=FVector::ZeroVector)
    {
        FActorSpawnParameters P; P.ObjectFlags|=RF_Transient; P.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        auto* A=World->SpawnActor<AStaticMeshActor>(Position,FRotator::ZeroRotator,P);
        A->Tags={FName(Id)};
        A->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
        A->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        return A;
    }
    UInstancedStaticMeshComponent* Cargo(int32 Count)
    {
        auto* A=World->SpawnActor<AActor>();
        auto* C=NewObject<UInstancedStaticMeshComponent>(A);
        A->SetRootComponent(C); A->AddInstanceComponent(C);
        auto* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
        C->SetStaticMesh(DuplicateObject<UStaticMesh>(Cube,GetTransientPackage(),
            MakeUniqueObjectName(GetTransientPackage(),UStaticMesh::StaticClass(),TEXT("SM_GHS_Presentation_Cargo_CacheFixture"))));
        C->RegisterComponent();
        for(int32 I=0;I<Count;++I) C->AddInstance(FTransform(FVector(100+I*200,0,0)));
        return C;
    }
};
TSharedPtr<FJsonObject> Parse(const FString& Text)
{
    TSharedPtr<FJsonObject> Result; FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Result); return Result;
}
}

// Removing either the registered-world cache or snapshot change gate regresses this contract.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneWarmCache,"GHS.Twin.Scene.Cache.WarmRefreshDoesNoWorldScanOrSerialization",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneWarmCache::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture F; F.Device(TEXT("TwinId=GHS_AGV_07")); F.Cargo(300);
    FGHSTwinSceneData S; S.Refresh(F.World);
    FString Json;
    TestTrue(TEXT("First consumer receives a full snapshot"),S.BuildSnapshotIfChanged(TEXT(""),Json));
    const auto Before=S.GetCacheStats();
    const uint64 Revision=S.GetRevision();
    for(int32 I=0;I<8;++I)
    {
        S.Refresh(F.World); S.MaintainCache(32);
        TestFalse(TEXT("Unchanged state is not serialized or resent"),S.BuildSnapshotIfChanged(TEXT(""),Json));
    }
    const auto After=S.GetCacheStats();
    TestEqual(TEXT("Warm refresh does not enumerate the world again"),After.WorldScans,Before.WorldScans);
    TestEqual(TEXT("Warm refresh does not rebuild storage records"),After.StorageRecordsBuilt,Before.StorageRecordsBuilt);
    TestEqual(TEXT("Warm refresh does not serialize the catalogue again"),After.SnapshotSerializations,Before.SnapshotSerializations);
    TestTrue(TEXT("Verification still examines real instance data"),After.InstancesVerified>Before.InstancesVerified);
    TestEqual(TEXT("Unchanged refresh does not invalidate POI candidates"),S.GetRevision(),Revision);
    return true;
}

// No event is emitted for UpdateInstanceTransform(..., false, false); bounded verification must find it.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneSilentMove,"GHS.Twin.Scene.Cache.SameCountSilentMoveKeepsPickingAndRegionsCurrent",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneSilentMove::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture F; auto* C=F.Cargo(300);
    FGHSTwinSceneData S; S.Refresh(F.World);
    FString Id; TestTrue(TEXT("Real first pallet can be selected"),S.PickRay(FVector(-100,0,0),FVector::ForwardVector,Id));
    C->UpdateInstanceTransform(0,FTransform(FVector(-1000,0,0)),false,false,true);
    FVector Position,Extent;
    TestTrue(TEXT("Selected geometry resolves without waiting for cache maintenance"),S.Resolve(Id,Position,Extent));
    TestTrue(TEXT("Immediate selected position is real"),Position.Equals(FVector(-1000,0,0),.01));
    const auto Before=S.GetCacheStats();
    for(int32 I=0;I<24;++I)
    {
        const auto Prior=S.GetCacheStats(); S.MaintainCache(17); const auto Next=S.GetCacheStats();
        TestTrue(TEXT("Every maintenance call respects its instance budget"),Next.InstancesVerified-Prior.InstancesVerified<=17);
    }
    TestTrue(TEXT("Actual changed instance updates region"),S.RegionBounds(TEXT("floor"),Position,Extent));
    // Cube half-width 50. Minimum -1050, maximum 59950 => center 29450, extent 30500.
    TestTrue(TEXT("Region includes moved instance, with unchanged count and component transform"),Position.Equals(FVector(29450,0,0),.01));
    TestTrue(TEXT("Region exact extent is updated"),Extent.Equals(FVector(30500,50,50),.01));
    TestEqual(TEXT("Only the changed storage record is rebuilt"),S.GetCacheStats().StorageRecordsBuilt-Before.StorageRecordsBuilt,uint64(1));
    C->UpdateInstanceTransform(0,FTransform(FVector(200,0,0)),false,true,true);
    C->UpdateInstanceTransform(299,FTransform(FVector(500,0,0)),false,false,true);
    for(int32 I=0;I<24;++I) S.MaintainCache(17);
    TestTrue(TEXT("Region remains valid after both extreme instances move inward"),S.RegionBounds(TEXT("floor"),Position,Extent));
    TestTrue(TEXT("Cached region shrinks as well as expands"),Position.Equals(FVector(29950,0,0),.01) && Extent.Equals(FVector(29800,50,50),.01));
    return true;
}

// A spawn cache must not miss post-spawn tags, duplicate IDs, or surviving owners after deletion.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneRegistry,"GHS.Twin.Scene.Cache.DynamicIdentityAndDestroyRemainCorrect",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneRegistry::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture F; FGHSTwinSceneData S; S.Refresh(F.World);
    auto* A=F.Device(TEXT("TwinId=GHS_AGV_07"),FVector(700,0,0)); S.Refresh(F.World);
    FVector Position,Extent; TestTrue(TEXT("Post-spawn identity discovered"),S.Resolve(TEXT("AGV-07"),Position,Extent));
    auto* B=F.Device(TEXT("TwinId=GHS_AGV_07"),FVector(1700,0,0)); S.Refresh(F.World);
    TestFalse(TEXT("Duplicate ID excluded"),S.Resolve(TEXT("AGV-07"),Position,Extent));
    B->Tags={TEXT("TwinId=GHS_AGV_08")}; S.Refresh(F.World);
    TestTrue(TEXT("Tag-only edit restores the first owner"),S.Resolve(TEXT("AGV-07"),Position,Extent));
    TestTrue(TEXT("Tag-only edit discovers renamed owner"),S.Resolve(TEXT("AGV-08"),Position,Extent));
    A->Destroy(); S.Refresh(F.World);
    TestFalse(TEXT("Destroyed actor not resolved"),S.Resolve(TEXT("AGV-07"),Position,Extent));
    TestTrue(TEXT("Surviving actor remains resolvable"),S.Resolve(TEXT("AGV-08"),Position,Extent));
    TestEqual(TEXT("Spawn/edit/destroy use registry, not full rescans"),S.GetCacheStats().WorldScans,uint64(1));
    return true;
}

// Cached telemetry must reset when its source disappears and adopt a same-count replacement.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneTelemetryReplacement,"GHS.Twin.Scene.Cache.ComponentReplacementCannotKeepStaleTelemetry",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneTelemetryReplacement::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture F; auto* A=F.Device(TEXT("TwinId=GHS_DockTruck_059")); A->Tags.Add(TEXT("IndependentDockTruck")); A->Tags.Add(TEXT("Dock=60"));
    auto* D=NewObject<UGHSDockTruckDataComponent>(A); A->AddInstanceComponent(D); D->RegisterComponent(); D->InitializeFromActorTags();
    D->SetTelemetry(3,10,EGHSDockTruckStatus::Loading,TEXT("ORDER-A"),false);
    FGHSTwinSceneData S; S.Refresh(F.World);
    FString Json; S.BuildSnapshotIfChanged(TEXT("TRUCK-059"),Json);
    D->DestroyComponent();
    auto* Replacement=NewObject<UGHSDockTruckDataComponent>(A); A->AddInstanceComponent(Replacement); Replacement->RegisterComponent(); Replacement->InitializeFromActorTags();
    S.Refresh(F.World);
    TestTrue(TEXT("Source removal invalidates snapshot"),S.BuildSnapshotIfChanged(TEXT("TRUCK-059"),Json));
    auto Selected=Parse(Json)->GetObjectField(TEXT("selection"));
    TestFalse(TEXT("Replacement without telemetry cannot retain availability"),Selected->GetBoolField(TEXT("available")));
    TestTrue(TEXT("Old order cannot leak into replacement"),Selected->GetStringField(TEXT("taskId")).IsEmpty());
    Replacement->SetTelemetry(8,10,EGHSDockTruckStatus::Loading,TEXT("ORDER-B"),false); S.Refresh(F.World);
    TestTrue(TEXT("New telemetry invalidates snapshot"),S.BuildSnapshotIfChanged(TEXT("TRUCK-059"),Json));
    TestEqual(TEXT("New source is adopted"),Parse(Json)->GetObjectField(TEXT("selection"))->GetStringField(TEXT("taskId")),FString(TEXT("ORDER-B")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneSelectionSnapshot,"GHS.Twin.Scene.Cache.SelectionAndGeometryBypassSnapshotThrottle",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneSelectionSnapshot::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture F; auto* A=F.Device(TEXT("TwinId=GHS_AGV_07"),FVector(100,200,300));
    FGHSTwinSceneData S; S.Refresh(F.World); FString Json; S.BuildSnapshotIfChanged(TEXT(""),Json);
    TestTrue(TEXT("Explicit selection gets immediate full payload"),S.BuildSnapshotIfChanged(TEXT("AGV-07"),Json,true));
    A->SetActorLocation(FVector(500,600,700));
    TestTrue(TEXT("Transform change is visible without a world refresh"),S.BuildSnapshotIfChanged(TEXT("AGV-07"),Json));
    FVector Point; TestTrue(TEXT("POI position resolves"),S.ResolvePoint(TEXT("AGV-07"),Point));
    TestTrue(TEXT("POI uses live center plus actual top and 80cm"),Point.Equals(FVector(500,600,830),.01));
    S.ApplyLayers(false,true); TestTrue(TEXT("Layer visibility invalidates snapshot"),S.BuildSnapshotIfChanged(TEXT("AGV-07"),Json));
    TestFalse(TEXT("Hidden state reaches browser"),Parse(Json)->GetObjectField(TEXT("selection"))->GetBoolField(TEXT("visible")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneBootstrapCache,"GHS.Twin.Scene.Cache.CachedBootstrapRepairsIdentityAndLateMesh",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneBootstrapCache::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture F; auto* A=F.Device(TEXT("TwinId=GHS_DockTruck_059"));
    A->Tags.Add(TEXT("IndependentDockTruck")); A->Tags.Add(TEXT("Dock=60"));
    FGHSTwinSceneData S; S.Refresh(F.World,true);
    auto* Data=A->FindComponentByClass<UGHSDockTruckDataComponent>();
    if(!TestNotNull(TEXT("Cached bootstrap creates required legacy component"),Data)) return false;
    Data->SetTelemetry(3,10,EGHSDockTruckStatus::Loading,TEXT("KEEP-LIVE"),false);
    S.Refresh(F.World,true);
    const auto Before=S.GetCacheStats();
    S.Refresh(F.World,true);
    TestEqual(TEXT("Warm bootstrap does not scan world"),S.GetCacheStats().WorldScans,Before.WorldScans);
    TestEqual(TEXT("Warm bootstrap keeps one data source"),A->FindComponentByClass<UGHSDockTruckDataComponent>(),Data);
    Data->TruckId=TEXT("TRUCK-999"); Data->DockId=TEXT("DOCK-99");
    S.Refresh(F.World,true);
    TestEqual(TEXT("Direct identity edits are repaired from actor tags"),Data->TruckId,FString(TEXT("TRUCK-059")));
    TestEqual(TEXT("Dock identity is repaired too"),Data->DockId,FString(TEXT("DOCK-60")));
    TestEqual(TEXT("Repair preserves accepted live telemetry"),Data->OrderId,FString(TEXT("KEEP-LIVE")));
    auto* Late=F.Device(TEXT("TwinId=GHS_AGV_08"));
    UStaticMesh* Mesh=Late->GetStaticMeshComponent()->GetStaticMesh(); Late->GetStaticMeshComponent()->SetStaticMesh(nullptr);
    S.Refresh(F.World);
    FVector Position,Extent; TestFalse(TEXT("Meshless device has no invented bounds"),S.Resolve(TEXT("AGV-08"),Position,Extent));
    Late->GetStaticMeshComponent()->SetStaticMesh(Mesh); S.Refresh(F.World);
    TestTrue(TEXT("Mesh assigned to existing component is discovered"),S.Resolve(TEXT("AGV-08"),Position,Extent));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneWarmForkliftCopy,"GHS.Twin.Scene.Cache.WarmBootstrapReconcilesCopiedForkliftWithoutLosingLiveSource",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneWarmForkliftCopy::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture F;
    auto* Approved=LoadObject<UStaticMesh>(nullptr,UGHSMannedForkliftIdentityLibrary::GetApprovedMeshPath());
    if(!TestNotNull(TEXT("Approved imported forklift mesh"),Approved)) return false;
    auto* Source=F.Device(TEXT("TwinId=GHN_MannedForklift_07"));
    Source->Tags.Add(TEXT("NormalWarehouseMannedForklift")); Source->GetStaticMeshComponent()->SetStaticMesh(Approved);
    auto* Live=NewObject<UGHSMannedForkliftDataComponent>(Source);
    Source->AddInstanceComponent(Live); Live->RegisterComponent(); Live->InitializeFromActorTags();
    Live->SetTelemetry(1.25f,3.f,EGHSMannedForkliftStatus::Running,TEXT("REAL-OP"),TEXT("REAL-AREA"),TEXT("LIVE-TASK"),TEXT("LIVE"),false);
    FGHSTwinSceneData S; S.Refresh(F.World,true); S.Refresh(F.World,true);
    const auto Before=S.GetCacheStats();
    auto* Copy=F.Device(TEXT("TwinId=GHN_MannedForklift_07"),FVector(700,0,0));
    Copy->GetStaticMeshComponent()->SetStaticMesh(Approved); Copy->Tags=Source->Tags;
    auto* Copied=DuplicateObject<UGHSMannedForkliftDataComponent>(Live,Copy,TEXT("CopiedTelemetry"));
    Copy->AddInstanceComponent(Copied); Copied->RegisterComponent();
    TestFalse(TEXT("Duplicate does not inherit runtime ownership"),Copied->IsIdentityBoundToOwner());
    S.Refresh(F.World,true);
    TestEqual(TEXT("Warm discovery preserves original canonical identity"),Live->ForkliftId,FString(TEXT("FORK-07")));
    TestEqual(TEXT("Copy receives next independent identity"),Copied->ForkliftId,FString(TEXT("FORK-08")));
    TestTrue(TEXT("Source live measurements and ownership remain intact"),Live->HasTelemetry() && Live->IsIdentityBoundToOwner()
        && Live->LoadTonnes==1.25f && Live->SpeedKmh==3.f && Live->DriverId==TEXT("REAL-OP") && Live->TaskId==TEXT("LIVE-TASK") && !Live->bIsDemoData);
    TestTrue(TEXT("Copy cannot expose inherited live payload"),Copied->IsIdentityBoundToOwner() && !Copied->HasTelemetry()
        && Copied->TaskId.IsEmpty() && Copied->DriverId.IsEmpty() && Copied->Area.IsEmpty()
        && Copied->Status==EGHSMannedForkliftStatus::AwaitingData);
    FVector Position,Extent;
    TestTrue(TEXT("Original remains independently selectable"),S.Resolve(TEXT("FORK-07"),Position,Extent));
    TestTrue(TEXT("Copy is selectable by its new identity"),S.Resolve(TEXT("FORK-08"),Position,Extent));
    const auto CopySnapshot=Parse(S.SnapshotJson(TEXT("FORK-08")));
    if(!TestTrue(TEXT("Copy detail snapshot parses"),CopySnapshot.IsValid())) return false;
    TestFalse(TEXT("Browser cannot claim copied measurements are live"),CopySnapshot->GetObjectField(TEXT("selection"))->GetBoolField(TEXT("live")));
    S.Refresh(F.World,true);
    TestEqual(TEXT("Warm copy reconciliation does not enumerate world again"),S.GetCacheStats().WorldScans,Before.WorldScans);
    TestEqual(TEXT("Repeated refresh preserves accepted source order"),Live->TaskId,FString(TEXT("LIVE-TASK")));
    TestFalse(TEXT("Repeated refresh cannot seed the copy with demo data"),Copied->HasTelemetry() || Copied->bIsDemoData);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSceneWorldDelegateLifetime,"GHS.Twin.Scene.Cache.WorldSwitchAndDestructionDetachDelegates",GHSTwinSceneCacheTests::Flags)
bool FGHSTwinSceneWorldDelegateLifetime::RunTest(const FString&)
{
    using namespace GHSTwinSceneCacheTests;
    FFixture First,Second;
    auto* Original=First.Device(TEXT("TwinId=GHS_AGV_07")); auto* OldCargo=First.Cargo(2);
    Second.Device(TEXT("TwinId=GHS_AGV_08")); auto* NewCargo=Second.Cargo(2);
    const bool FirstLevelsBound=First.World->OnLevelsChanged().IsBound();
    const bool SecondLevelsBound=Second.World->OnLevelsChanged().IsBound();
    auto S=MakeUnique<FGHSTwinSceneData>(); S->Refresh(First.World); S->ApplyLayers(false,false);
    TestTrue(TEXT("First world's visibility is owned by active service"),Original->IsHidden());
    S->Refresh(Second.World);
    TestFalse(TEXT("World switch restores original visibility"),Original->IsHidden());
    TestEqual(TEXT("Old world's level delegate is detached"),First.World->OnLevelsChanged().IsBound(),FirstLevelsBound);
    FVector Position,Extent;
    TestFalse(TEXT("Old world identity cannot leak after switch"),S->Resolve(TEXT("AGV-07"),Position,Extent));
    TestTrue(TEXT("New world identity resolves"),S->Resolve(TEXT("AGV-08"),Position,Extent));
    const uint64 Revision=S->GetRevision(); const auto Before=S->GetCacheStats();
    // These real engine broadcasts must not reach the deleted first-world FImpl.
    auto* DetachedActor=First.Device(TEXT("TwinId=GHS_AGV_09"));
    First.World->NotifyPostRegisterAllActorComponents(DetachedActor);
    OldCargo->AddInstance(FTransform(FVector(900,0,0))); DetachedActor->Destroy();
    S->Refresh(Second.World);
    TestEqual(TEXT("Old world broadcasts do not invalidate current catalogue"),S->GetRevision(),Revision);
    TestEqual(TEXT("Old world broadcasts do not trigger a new world scan"),S->GetCacheStats().WorldScans,Before.WorldScans);
    S->Refresh(nullptr);
    TestEqual(TEXT("Explicit disconnect detaches current level delegate"),Second.World->OnLevelsChanged().IsBound(),SecondLevelsBound);
    NewCargo->AddInstance(FTransform(FVector(1200,0,0)));
    auto* DisconnectedActor=Second.Device(TEXT("TwinId=GHS_AGV_10")); DisconnectedActor->Destroy();
    TestEqual(TEXT("Disconnected service receives no registrations"),S->GetCacheStats().RegisteredActors,0);
    TestFalse(TEXT("Disconnected snapshot reports no live world"),Parse(S->SnapshotJson())->GetBoolField(TEXT("connected")));
    S->Refresh(Second.World);
    // World destruction can precede HUD destruction during travel/shutdown.
    Second.Destroy(); S.Reset();
    // Exercise global instance delegate plus spawn/register/destroy after service teardown.
    const int32 OldCount=OldCargo->GetInstanceCount(); OldCargo->AddInstance(FTransform(FVector(1500,0,0)));
    auto* AfterDestroy=First.Device(TEXT("TwinId=GHS_AGV_11"));
    First.World->NotifyPostRegisterAllActorComponents(AfterDestroy);
    TestTrue(TEXT("Actor lifecycle remains valid after service/world teardown"),AfterDestroy->Destroy());
    TestEqual(TEXT("Global instance update remains safe after service teardown"),OldCargo->GetInstanceCount(),OldCount+1);
    TestEqual(TEXT("No level delegate leaked into old world"),First.World->OnLevelsChanged().IsBound(),FirstLevelsBound);
    return true;
}
#endif
