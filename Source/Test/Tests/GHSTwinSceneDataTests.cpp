#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSTwinSceneData.h"
#include "../GHSDockTruckDataComponent.h"
#include "../GHSMannedForkliftDataComponent.h"
#include "../GHSMannedForkliftIdentityLibrary.h"
#include "../GHSStackerDataComponent.h"
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
#include <limits>

namespace GHSTwinSceneDataTests
{
    constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
    TSharedPtr<FJsonObject> Parse(const FString& Text)
    {
        TSharedPtr<FJsonObject> Result;
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Result);
        return Result;
    }
    struct FFixture
    {
        UWorld* World = nullptr;
        FFixture()
        {
            World = UWorld::CreateWorld(EWorldType::Game, false);
            if (World && GEngine)
            {
                GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
                World->InitializeActorsForPlay(FURL());
            }
        }
        ~FFixture()
        {
            if (!World) return;
            if (GEngine) GEngine->DestroyWorldContext(World);
            World->DestroyWorld(false);
        }
        AStaticMeshActor* Device(const TArray<FName>& Tags, const FVector& Location)
        {
            if (!World) return nullptr;
            FActorSpawnParameters Params;
            Params.ObjectFlags |= RF_Transient;
            Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            AStaticMeshActor* Actor = World->SpawnActor<AStaticMeshActor>(Location, FRotator::ZeroRotator, Params);
            if (Actor)
            {
                Actor->Tags = Tags;
                Actor->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
                Actor->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            }
            return Actor;
        }
    };
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinTagIdentity,
    "GHS.Twin.Scene.IdentityUsesTagsAndIndependentDock", GHSTwinSceneDataTests::Flags)
bool FGHSTwinTagIdentity::RunTest(const FString& Parameters)
{
    GHSTwinSelection::FIdentity Identity;
    TestTrue(TEXT("AGV sparse number is preserved"), GHSTwinSelection::Identify({TEXT("TwinId=GHS_AGV_034")}, Identity));
    TestEqual(TEXT("AGV is not renumbered by list position"), Identity.Id, FString(TEXT("AGV-34")));
    TestEqual(TEXT("AGV classifier"), Identity.Type, FString(TEXT("agv")));
    TestTrue(TEXT("Independent truck identity"), GHSTwinSelection::Identify({TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_059"), TEXT("Dock=60")}, Identity));
    TestEqual(TEXT("Truck ID"), Identity.Id, FString(TEXT("TRUCK-059")));
    TestEqual(TEXT("Dock comes from its own tag"), Identity.DockId, FString(TEXT("DOCK-60")));
    TestTrue(TEXT("Charger retains facility namespace"), GHSTwinSelection::Identify({TEXT("TwinId=GHS_CH_07")}, Identity));
    TestEqual(TEXT("Charger ID"), Identity.Id, FString(TEXT("CH-07")));
    for (const TArray<FName>& Tags : TArray<TArray<FName>>{
        {TEXT("TwinId=GHS_AGV_0")}, {TEXT("TwinId=GHS_AGV_12x")},
        {TEXT("TwinId=GHS_AGV_-1")}, {TEXT("TwinId=GHS_AGV_2147483648")},
        {TEXT("TwinId=GHS_AGV_12"), TEXT("TwinId=GHS_AGV_13")},
        {TEXT("TwinId=GHN_MannedForklift_01")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_02"), TEXT("Dock=2"), TEXT("Dock=3")}})
    {
        TestFalse(TEXT("Malformed or ambiguous identity rejected"), GHSTwinSelection::Identify(Tags, Identity));
        TestTrue(TEXT("Rejected identity cannot leak previous selected ID"), Identity.Id.IsEmpty());
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinRayBounds,
    "GHS.Twin.Scene.NoCollisionRayUsesRotatedScaledInstance", GHSTwinSceneDataTests::Flags)
bool FGHSTwinRayBounds::RunTest(const FString& Parameters)
{
    const FBox Box(FVector(-1,-2,0), FVector(1,2,4));
    const FTransform Instance(FRotator(0,90,0), FVector(100,20,0), FVector(2,3,1));
    double Distance = -1;
    FVector Hit;
    TestTrue(TEXT("Ray intersects oriented instance"), GHSTwinSelection::IntersectBox(
        FVector(100,0,2), FVector(0,1,0), Instance, Box, Distance, &Hit));
    TestTrue(TEXT("Entry uses actual rotated scale in world units"), FMath::IsNearlyEqual(Distance,18.0,0.001));
    TestTrue(TEXT("Hit is converted into instance local coordinates"), Hit.Equals(FVector(-1,0,2),0.001));
    TestFalse(TEXT("Nearby ray outside narrow rotated side must miss"), GHSTwinSelection::IntersectBox(
        FVector(107,0,2), FVector(0,1,0), Instance, Box, Distance));
    TestFalse(TEXT("Geometry behind cursor ray is ignored"), GHSTwinSelection::IntersectBox(
        FVector(100,0,2), FVector(0,-1,0), Instance, Box, Distance));
    TestFalse(TEXT("Zero direction is not a pick"), GHSTwinSelection::IntersectBox(
        FVector(100,0,2), FVector::ZeroVector, Instance, Box, Distance));
    TestFalse(TEXT("Nonfinite ray is rejected"), GHSTwinSelection::IntersectBox(
        FVector(std::numeric_limits<double>::quiet_NaN(),0,2), FVector(0,1,0), Instance, Box, Distance));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSnapshotProvenance,
    "GHS.Twin.Scene.RefreshPreservesTelemetryAndUnknownSources", GHSTwinSceneDataTests::Flags)
bool FGHSTwinSnapshotProvenance::RunTest(const FString& Parameters)
{
    using namespace GHSTwinSceneDataTests;
    FFixture Fixture;
    AStaticMeshActor* Truck = Fixture.Device({TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_059"), TEXT("Dock=60")}, FVector(100,200,0));
    AStaticMeshActor* AGV = Fixture.Device({TEXT("TwinId=GHS_AGV_34")}, FVector(300,200,0));
    if (!TestNotNull(TEXT("Truck"), Truck) || !TestNotNull(TEXT("AGV"), AGV)) return false;
    auto* Data = NewObject<UGHSDockTruckDataComponent>(Truck);
    Truck->AddInstanceComponent(Data);
    Data->RegisterComponent();
    TestTrue(TEXT("Truck tags initialize existing component"), Data->InitializeFromActorTags());
    TestTrue(TEXT("Explicit live update"), Data->SetTelemetry(7,20,EGHSDockTruckStatus::Loading,TEXT("LIVE-ORDER"),false));
    const int32 AGVComponents = AGV->GetComponents().Num();
    FGHSTwinSceneData Service;
    Service.Refresh(Fixture.World);
    Service.Refresh(Fixture.World);
    const TSharedPtr<FJsonObject> Snapshot = Parse(Service.SnapshotJson(TEXT("TRUCK-059")));
    if (!TestTrue(TEXT("Snapshot is valid JSON"), Snapshot.IsValid())) return false;
    TestEqual(TEXT("Only tagged devices included"), Snapshot->GetArrayField(TEXT("equipment")).Num(), 2);
    const auto Selection = Snapshot->GetObjectField(TEXT("selection"));
    TestTrue(TEXT("Existing live source survives refresh"), Selection->GetBoolField(TEXT("live")));
    TestFalse(TEXT("Live source is not replaced with demo"), Selection->GetBoolField(TEXT("demo")));
    TestEqual(TEXT("Accepted order survives refresh"), Selection->GetStringField(TEXT("taskId")), FString(TEXT("LIVE-ORDER")));
    TestEqual(TEXT("Refresh creates no component"), AGV->GetComponents().Num(), AGVComponents);
    TestEqual(TEXT("Refresh leaves accepted telemetry intact"), Data->LoadedPallets, 7);
    const auto Unknown = Parse(Service.SnapshotJson(TEXT("AGV-34")))->GetObjectField(TEXT("selection"));
    TestFalse(TEXT("AGV with no source cannot claim live telemetry"), Unknown->GetBoolField(TEXT("live")));
    TestFalse(TEXT("AGV with no source cannot claim measurements"), Unknown->GetBoolField(TEXT("available")));
    TestEqual(TEXT("AGV defaults to explicit unknown state"), Unknown->GetStringField(TEXT("status")), FString(TEXT("unknown")));
    FVector Location, Extent;
    TestTrue(TEXT("Resolve uses actual Actor geometry"), Service.Resolve(TEXT("AGV-34"),Location,Extent));
    TestTrue(TEXT("Resolved location tracks the real Actor"), Location.Equals(FVector(300,200,0),1));
    TestFalse(TEXT("Missing sparse AGV cannot resolve"), Service.Resolve(TEXT("AGV-32"),Location,Extent));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinLayerRestore,
    "GHS.Twin.Scene.LayerRestoresOriginalHiddenState", GHSTwinSceneDataTests::Flags)
bool FGHSTwinLayerRestore::RunTest(const FString& Parameters)
{
    GHSTwinSceneDataTests::FFixture Fixture;
    auto* Visible = Fixture.Device({TEXT("TwinId=GHS_AGV_01")}, FVector::ZeroVector);
    auto* OriginallyHidden = Fixture.Device({TEXT("TwinId=GHS_AGV_02")}, FVector(200,0,0));
    if (!Visible || !OriginallyHidden) return false;
    OriginallyHidden->SetActorHiddenInGame(true);
    {
        FGHSTwinSceneData Service;
        Service.Refresh(Fixture.World);
        Service.ApplyLayers(false,true);
        TestTrue(TEXT("Layer toggle hides equipment"), Visible->IsHidden());
        Service.Refresh(Fixture.World);
        Service.ApplyLayers(true,true);
        TestFalse(TEXT("Original visible actor restored after refresh"), Visible->IsHidden());
        TestTrue(TEXT("Pre-existing hidden actor stays hidden"), OriginallyHidden->IsHidden());
        Service.ApplyLayers(false,true);
    }
    TestFalse(TEXT("Service destruction restores runtime hide change"), Visible->IsHidden());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinInstancePick,
    "GHS.Twin.Scene.PicksActualInstanceAndNearestDeviceWithoutCollision", GHSTwinSceneDataTests::Flags)
bool FGHSTwinInstancePick::RunTest(const FString& Parameters)
{
    using namespace GHSTwinSceneDataTests;
    FFixture Fixture;
    if (!TestNotNull(TEXT("World"),Fixture.World)) return false;
    AActor* Host=Fixture.World->SpawnActor<AActor>();
    auto* Instances=NewObject<UInstancedStaticMeshComponent>(Host);
    Host->SetRootComponent(Instances);
    Host->AddInstanceComponent(Instances);
    UStaticMesh* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!TestNotNull(TEXT("Real cube mesh for an isolated pallet fixture"),Cube)) return false;
    UStaticMesh* RackMesh=DuplicateObject<UStaticMesh>(Cube,GetTransientPackage(),
        MakeUniqueObjectName(GetTransientPackage(),UStaticMesh::StaticClass(),TEXT("SM_GHS_Presentation_Cargo_SelectionFixture")));
    Instances->SetStaticMesh(RackMesh);
    Instances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Instances->RegisterComponent();
    Instances->AddInstance(FTransform(FVector(100,200,0)));
    Instances->AddInstance(FTransform(FVector(400,0,0)));

    FGHSTwinSceneData Service;
    Service.Refresh(Fixture.World);
    FString Selected;
    TestTrue(TEXT("NoCollision instance remains selectable"),Service.PickRay(FVector::ZeroVector,FVector::ForwardVector,Selected));
    const FString StableId=Selected;
    const auto Snapshot=Parse(Service.SnapshotJson(Selected));
    if (!TestTrue(TEXT("Actual instance selection exists"),Snapshot.IsValid())) return false;
    const auto Selection=Snapshot->GetObjectField(TEXT("selection"));
    TestEqual(TEXT("Ray selects the second instance, not host Actor or index zero"),Selection->GetIntegerField(TEXT("instanceIndex")),1);
    TestEqual(TEXT("Unbound cargo remains material"),Selection->GetStringField(TEXT("kind")),FString(TEXT("material")));
    TestFalse(TEXT("Selecting arbitrary cargo does not invent business binding"),Selection->GetBoolField(TEXT("businessBound")));
    TestFalse(TEXT("No fabricated SKU on actual scene selection"),Selection->HasField(TEXT("sku")));
    Service.Refresh(Fixture.World);
    Service.PickRay(FVector::ZeroVector,FVector::ForwardVector,Selected);
    TestEqual(TEXT("Cached refresh preserves instance ID"),Selected,StableId);
    Instances->UpdateInstanceTransform(1,FTransform(FVector(600,0,0)),false,true,true);
    FVector Location,Extent;
    TestTrue(TEXT("Selected instance still resolves after a move"),Service.Resolve(StableId,Location,Extent));
    TestTrue(TEXT("Resolve reads current transform even before cache invalidation"),Location.Equals(FVector(600,0,0),.01));

    AActor* RackHost=Fixture.World->SpawnActor<AActor>();
    auto* Structure=NewObject<UInstancedStaticMeshComponent>(RackHost);
    RackHost->SetRootComponent(Structure); RackHost->AddInstanceComponent(Structure);
    auto* StructureMesh=DuplicateObject<UStaticMesh>(Cube,GetTransientPackage(),
        MakeUniqueObjectName(GetTransientPackage(),UStaticMesh::StaticClass(),TEXT("SM_GHS_V2Rack_EmptyStructureFixture")));
    Structure->SetStaticMesh(StructureMesh); Structure->RegisterComponent();
    Structure->AddInstance(FTransform(FVector(0,800,0)));
    Service.Refresh(Fixture.World);
    TestFalse(TEXT("Bare rack structure is no longer a selectable object"),Service.PickRay(FVector::ZeroVector,FVector::RightVector,Selected));
    TestTrue(TEXT("Rack area remains locatable without selecting an instance"),Service.RegionBounds(TEXT("racks"),Location,Extent));
    TestTrue(TEXT("Rack area matches actual geometry"),Location.Equals(FVector(0,800,0),.01));
    TestTrue(TEXT("Floor area has independent actual bounds"),Service.RegionBounds(TEXT("floor"),Location,Extent));
    TestFalse(TEXT("Legacy dock preset cannot alias a storage region"),Service.RegionBounds(TEXT("inbound"),Location,Extent));
    TestFalse(TEXT("No per-instance rack POI remains"),Service.Points().ContainsByPredicate([](const FGHSTwinPoint& P){return P.Id.StartsWith(TEXT("RACK:"));}));

    auto* Device=Fixture.Device({TEXT("TwinId=GHS_AGV_07")},FVector(200,0,0));
    if (!TestNotNull(TEXT("Nearer device"),Device)) return false;
    Service.Refresh(Fixture.World);
    TestTrue(TEXT("Both device and rack are hit"),Service.PickRay(FVector::ZeroVector,FVector::ForwardVector,Selected));
    TestEqual(TEXT("Nearest actual geometry wins"),Selected,FString(TEXT("AGV-07")));
    auto* Duplicate=Fixture.Device({TEXT("TwinId=GHS_AGV_07")},FVector(200,1000,0));
    if (!Duplicate) return false;
    Service.Refresh(Fixture.World);
    TestFalse(TEXT("Duplicate business ID never resolves to an arbitrary actor"),Service.Resolve(TEXT("AGV-07"),Location,Extent));
    FFixture EmptyWorld;
    Service.Refresh(EmptyWorld.World);
    TestFalse(TEXT("Switching worlds clears the previous rack region"),Service.RegionBounds(TEXT("racks"),Location,Extent));
    TestFalse(TEXT("Switching worlds clears the previous floor region"),Service.RegionBounds(TEXT("floor"),Location,Extent));
    TestFalse(TEXT("Empty world has no stale region POI"),Service.Points().ContainsByPredicate([](const FGHSTwinPoint& Point){return Point.Id.StartsWith(TEXT("REGION:"));}));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinCopiedTelemetry,
    "GHS.Twin.Scene.UnreconciledCopyCannotClaimAnotherVehiclesTelemetry", GHSTwinSceneDataTests::Flags)
bool FGHSTwinCopiedTelemetry::RunTest(const FString& Parameters)
{
    using namespace GHSTwinSceneDataTests;
    FFixture Fixture;
    auto* Source=Fixture.Device({TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_01")},FVector::ZeroVector);
    auto* Copy=Fixture.Device({TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_01")},FVector(300,0,0));
    if (!Source || !Copy) return false;
    const FName OwnerMarker(*(TEXT("GHSManualIdentityOwner=")+Source->GetName()));
    Source->Tags.Add(OwnerMarker); Copy->Tags.Add(OwnerMarker);
    auto* SourceData=NewObject<UGHSMannedForkliftDataComponent>(Source);
    Source->AddInstanceComponent(SourceData); SourceData->RegisterComponent();
    SourceData->InitializeFromActorTags();
    SourceData->SetTelemetry(1.2f,3.f,EGHSMannedForkliftStatus::Running,TEXT("OP-LIVE"),TEXT("Live Area"),TEXT("LIVE-TASK"),TEXT("Live"),false);
    auto* CopiedData=DuplicateObject<UGHSMannedForkliftDataComponent>(SourceData,Copy);
    Copy->AddInstanceComponent(CopiedData); CopiedData->RegisterComponent();
    TestFalse(TEXT("Copied component is not bound to new owner"),CopiedData->IsIdentityBoundToOwner());
    Source->Destroy();
    FGHSTwinSceneData Service;
    Service.Refresh(Fixture.World);
    const auto Snapshot=Parse(Service.SnapshotJson(TEXT("FORK-01")));
    if (!TestTrue(TEXT("Snapshot parses"),Snapshot.IsValid())) return false;
    const auto Selection=Snapshot->GetObjectField(TEXT("selection"));
    TestFalse(TEXT("Even a unique copied ID cannot claim inherited live data"),Selection->GetBoolField(TEXT("live")));
    TestFalse(TEXT("Copied measurements are unavailable pending identity reconciliation"),Selection->GetBoolField(TEXT("available")));
    TestTrue(TEXT("Original task does not leak into clone detail"),Selection->GetStringField(TEXT("taskId")).IsEmpty());
    TestEqual(TEXT("Read-only service does not rewrite copied component"),CopiedData->TaskId,FString(TEXT("LIVE-TASK")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinBootstrapNew,
    "GHS.Twin.Scene.BootstrapAddsMissingLegacyComponentsOnce", GHSTwinSceneDataTests::Flags)
bool FGHSTwinBootstrapNew::RunTest(const FString& Parameters)
{
    using namespace GHSTwinSceneDataTests;
    FFixture Fixture;
    auto* Forklift=Fixture.Device({TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_01")},FVector::ZeroVector);
    auto* Stacker=Fixture.Device({TEXT("NormalWarehouseFloorStacker"),TEXT("TwinId=GHN_FloorStacker_01")},FVector(300,0,0));
    auto* Truck=Fixture.Device({TEXT("IndependentDockTruck"),TEXT("TwinId=GHS_DockTruck_059"),TEXT("Dock=60")},FVector(600,0,0));
    auto* AGV=Fixture.Device({TEXT("TwinId=GHS_AGV_07")},FVector(900,0,0));
    UStaticMesh* Approved=LoadObject<UStaticMesh>(nullptr,UGHSMannedForkliftIdentityLibrary::GetApprovedMeshPath());
    if (!Forklift || !Stacker || !Truck || !AGV || !TestNotNull(TEXT("Approved forklift mesh"),Approved)) return false;
    Forklift->GetStaticMeshComponent()->SetStaticMesh(Approved);
    const int32 Before=Forklift->GetComponents().Num()+Stacker->GetComponents().Num()+Truck->GetComponents().Num()+AGV->GetComponents().Num();
    TestEqual(TEXT("One missing legacy data component per supported device"),GHSTwinSelection::BootstrapComponents(Fixture.World),3);
    const auto* ForkData=Forklift->FindComponentByClass<UGHSMannedForkliftDataComponent>();
    const auto* StackData=Stacker->FindComponentByClass<UGHSStackerDataComponent>();
    const auto* TruckData=Truck->FindComponentByClass<UGHSDockTruckDataComponent>();
    if (!TestNotNull(TEXT("Forklift component"),ForkData) || !TestNotNull(TEXT("Stacker component"),StackData)
        || !TestNotNull(TEXT("Truck component"),TruckData)) return false;
    TestTrue(TEXT("New forklift sample remains explicitly demo"),ForkData->bIsDemoData);
    TestTrue(TEXT("New stacker sample remains explicitly demo"),StackData->bIsDemoData);
    TestTrue(TEXT("Legacy forklift demonstration remains available"),ForkData->HasTelemetry());
    TestTrue(TEXT("Legacy stacker demonstration remains available"),StackData->HasTelemetry());
    TestFalse(TEXT("Truck has no invented demonstration sample"),TruckData->bIsDemoData);
    TestTrue(TEXT("Truck stays awaiting explicit data"),TruckData->Status==EGHSDockTruckStatus::AwaitingData);
    TestEqual(TEXT("Truck independent dock tag retained"),TruckData->DockId,FString(TEXT("DOCK-60")));
    TestEqual(TEXT("Exactly three components were registered"),Forklift->GetComponents().Num()+Stacker->GetComponents().Num()+Truck->GetComponents().Num()+AGV->GetComponents().Num(),Before+3);
    TestEqual(TEXT("Repeated two-second discovery creates nothing"),GHSTwinSelection::BootstrapComponents(Fixture.World),0);
    TestEqual(TEXT("Repeated initialization cannot multiply components"),Forklift->GetComponents().Num()+Stacker->GetComponents().Num()+Truck->GetComponents().Num()+AGV->GetComponents().Num(),Before+3);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinBootstrapLive,
    "GHS.Twin.Scene.BootstrapNeverReplacesAcceptedLiveTelemetry", GHSTwinSceneDataTests::Flags)
bool FGHSTwinBootstrapLive::RunTest(const FString& Parameters)
{
    using namespace GHSTwinSceneDataTests;
    FFixture Fixture;
    auto* Forklift=Fixture.Device({TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_01")},FVector::ZeroVector);
    auto* Stacker=Fixture.Device({TEXT("NormalWarehouseFloorStacker"),TEXT("TwinId=GHN_FloorStacker_01")},FVector(300,0,0));
    auto* Truck=Fixture.Device({TEXT("IndependentDockTruck"),TEXT("TwinId=GHS_DockTruck_059"),TEXT("Dock=60")},FVector(600,0,0));
    UStaticMesh* Approved=LoadObject<UStaticMesh>(nullptr,UGHSMannedForkliftIdentityLibrary::GetApprovedMeshPath());
    if (!Forklift || !Stacker || !Truck || !Approved) return false;
    Forklift->GetStaticMeshComponent()->SetStaticMesh(Approved);
    auto* ForkData=NewObject<UGHSMannedForkliftDataComponent>(Forklift);
    Forklift->AddInstanceComponent(ForkData); ForkData->RegisterComponent();
    auto* StackData=NewObject<UGHSStackerDataComponent>(Stacker);
    Stacker->AddInstanceComponent(StackData); StackData->RegisterComponent();
    auto* TruckData=NewObject<UGHSDockTruckDataComponent>(Truck);
    Truck->AddInstanceComponent(TruckData); TruckData->RegisterComponent();
    // Data may arrive before identity discovery. Initialization must preserve even these updates.
    ForkData->SetTelemetry(2.7f,7.f,EGHSMannedForkliftStatus::Running,TEXT("OP-REAL"),TEXT("REAL AREA"),TEXT("LIVE-FORK"),TEXT("LIVE"),false);
    StackData->SetTelemetry(51.f,37.f,EGHSStackerStatus::Running,TEXT("LIVE-STACK"),false);
    TruckData->SetTelemetry(9,11,EGHSDockTruckStatus::Loading,TEXT("LIVE-TRUCK"),false);
    TestEqual(TEXT("Existing components require no registration"),GHSTwinSelection::BootstrapComponents(Fixture.World),0);
    TestEqual(TEXT("Repeated discovery creates no components"),GHSTwinSelection::BootstrapComponents(Fixture.World),0);
    TestEqual(TEXT("Initial empty forklift identity gets bound"),ForkData->ForkliftId,FString(TEXT("FORK-01")));
    TestEqual(TEXT("Forklift live measurement retained"),ForkData->LoadTonnes,2.7f);
    TestEqual(TEXT("Forklift live task retained"),ForkData->TaskId,FString(TEXT("LIVE-FORK")));
    TestEqual(TEXT("Stacker live measurement retained"),StackData->BatteryPercent,51.f);
    TestEqual(TEXT("Stacker live task retained"),StackData->TaskId,FString(TEXT("LIVE-STACK")));
    TestEqual(TEXT("Truck live progress retained"),TruckData->LoadedPallets,9);
    TestEqual(TEXT("Truck live order retained"),TruckData->OrderId,FString(TEXT("LIVE-TRUCK")));
    TestFalse(TEXT("Forklift live source stays live"),ForkData->bIsDemoData);
    TestFalse(TEXT("Stacker live source stays live"),StackData->bIsDemoData);
    TestFalse(TEXT("Truck live source stays live"),TruckData->bIsDemoData);
    FGHSTwinSceneData Service;
    Service.Refresh(Fixture.World);
    const auto Snapshot=Parse(Service.SnapshotJson());
    if (!Snapshot.IsValid()) return false;
    TestEqual(TEXT("All three adopted devices are represented"),Snapshot->GetArrayField(TEXT("equipment")).Num(),3);
    for (const auto& Value : Snapshot->GetArrayField(TEXT("equipment")))
        TestTrue(TEXT("Snapshot preserves live provenance after bootstrap"),Value->AsObject()->GetBoolField(TEXT("live")));
    return true;
}

#endif
