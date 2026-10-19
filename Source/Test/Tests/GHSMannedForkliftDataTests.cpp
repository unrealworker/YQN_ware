#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSMannedForkliftDataComponent.h"
#include "../GHSMannedForkliftIdentityLibrary.h"
#include "../GHSTruckHUDLayout.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/WorldSettings.h"
#include "Misc/AutomationTest.h"
#include <limits>

namespace GHSMannedForkliftTests
{
    constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
    struct FFixture
    {
        UWorld* World = nullptr;
        AActor* Actor = nullptr;
        UGHSMannedForkliftDataComponent* Data = nullptr;
        FFixture()
        {
            World = UWorld::CreateWorld(EWorldType::Game, false);
            if (!World || !GEngine) return;
            GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
            World->InitializeActorsForPlay(FURL());
            FActorSpawnParameters Spawn;
            Spawn.ObjectFlags |= RF_Transient;
            Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            Actor = World->SpawnActor<AActor>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
            if (!Actor) return;
            Actor->Tags = {TEXT("NormalWarehouseMannedForklift"), TEXT("TwinId=GHN_MannedForklift_02")};
            Data = NewObject<UGHSMannedForkliftDataComponent>(Actor);
            Actor->AddInstanceComponent(Data);
            Data->RegisterComponent();
        }
        ~FFixture()
        {
            if (!World) return;
            if (GEngine) GEngine->DestroyWorldContext(World);
            World->DestroyWorld(false);
        }
    };

    struct FFleetFixture : FFixture
    {
        UStaticMesh* Mesh=nullptr;
        FFleetFixture()
        {
            if (Actor) Actor->Tags.Reset();
            Mesh=LoadObject<UStaticMesh>(nullptr,UGHSMannedForkliftIdentityLibrary::GetApprovedMeshPath());
        }
        AStaticMeshActor* Vehicle(const TCHAR* ObjectName)
        {
            if (!World || !Mesh) return nullptr;
            FActorSpawnParameters Spawn;
            Spawn.Name=FName(ObjectName);
            Spawn.ObjectFlags|=RF_Transient;
            Spawn.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            auto* Vehicle=World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector,FRotator::ZeroRotator,Spawn);
            if (Vehicle)
            {
                Vehicle->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
                Vehicle->GetStaticMeshComponent()->SetStaticMesh(Mesh);
            }
            return Vehicle;
        }
    };
    bool HasNumber(AActor* Actor,int32 Number)
    {
        return Actor && Actor->ActorHasTag(FName(*FString::Printf(TEXT("TwinId=GHN_MannedForklift_%02d"),Number)));
    }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftIdentity,
    "GHS.MannedForkliftHUD.Data.RuntimeIdentity", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftIdentity::RunTest(const FString& Parameters)
{
    GHSMannedForkliftTests::FFixture F;
    if (!TestNotNull(TEXT("Runtime component"), F.Data)) return false;
    TestTrue(TEXT("Identity comes from persistent tags"), F.Data->InitializeFromActorTags());
    TestEqual(TEXT("Normalized identity"), F.Data->ForkliftId, FString(TEXT("FORK-02")));
    TestTrue(TEXT("Explicit identity supports runtime vehicles"), F.Data->InitializeIdentity(TEXT("FORK-003")));
    for (const FString Invalid : {TEXT(""), TEXT("FORK-0"), TEXT("FORK--2"), TEXT("FORK-2x"),
        TEXT("FORK-2147483648"), TEXT("STACKER-02"), TEXT(" FORK-02")})
    {
        TestFalse(TEXT("Reject malformed identity"), F.Data->InitializeIdentity(Invalid));
        TestEqual(TEXT("Preserve prior identity"), F.Data->ForkliftId, FString(TEXT("FORK-03")));
    }
    F.Actor->Tags.Add(TEXT("TwinId=GHN_MannedForklift_03"));
    TestFalse(TEXT("Reject duplicate TwinId tags"), F.Data->InitializeFromActorTags());
    F.Actor->Tags = {TEXT("TwinId=GHN_MannedForklift_02")};
    TestFalse(TEXT("Type tag is required"), F.Data->InitializeFromActorTags());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftTelemetry,
    "GHS.MannedForkliftHUD.Data.ValidAndAtomicInvalidUpdates", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftTelemetry::RunTest(const FString& Parameters)
{
    auto* Data = NewObject<UGHSMannedForkliftDataComponent>();
    TestFalse(TEXT("No invented initial telemetry"), Data->HasTelemetry());
    TestTrue(TEXT("Accept live supplied measurements"), Data->SetTelemetry(1.2f, 5.f,
        EGHSMannedForkliftStatus::Running, TEXT("OP-07"), TEXT("A"), TEXT("TASK-1"), TEXT("")));
    TestTrue(TEXT("Live measurements available"), Data->HasTelemetry());
    TestTrue(TEXT("Identity rediscovery is independent of telemetry"), Data->InitializeIdentity(TEXT("FORK-01")));
    TestEqual(TEXT("Identity initialization preserves telemetry"), Data->LoadTonnes,1.2f);
    const float NaN = std::numeric_limits<float>::quiet_NaN();
    const float Inf = std::numeric_limits<float>::infinity();
    const TArray<FVector2D> Invalid = {{-1,5},{1,-1},{-2,5},{NaN,5},{1,NaN},{Inf,5},{1,Inf}};
    for (const FVector2D& Pair : Invalid)
    {
        TestFalse(TEXT("Invalid update rejected"), Data->SetTelemetry(Pair.X, Pair.Y,
            EGHSMannedForkliftStatus::Warning, TEXT("OTHER"), TEXT("B"), TEXT("BAD"), TEXT("BAD"), true));
        TestEqual(TEXT("Preserve load"), Data->LoadTonnes, 1.2f);
        TestEqual(TEXT("Preserve speed"), Data->SpeedKmh, 5.f);
        TestEqual(TEXT("Preserve driver"), Data->DriverId, FString(TEXT("OP-07")));
        TestEqual(TEXT("Preserve area"), Data->Area, FString(TEXT("A")));
        TestEqual(TEXT("Preserve task"), Data->TaskId, FString(TEXT("TASK-1")));
        TestTrue(TEXT("Preserve status and provenance"), Data->Status == EGHSMannedForkliftStatus::Running && !Data->bIsDemoData);
        TestTrue(TEXT("Preserve reason"), Data->Reason.IsEmpty());
    }
    TestFalse(TEXT("Unknown enum rejected"), Data->SetTelemetry(0,0,static_cast<EGHSMannedForkliftStatus>(255),TEXT(""),TEXT(""),TEXT(""),TEXT("")));
    TestTrue(TEXT("Zero load and speed are valid"), Data->SetTelemetry(0,0,EGHSMannedForkliftStatus::Idle,TEXT(""),TEXT("A"),TEXT(""),TEXT("")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftUnavailable,
    "GHS.MannedForkliftHUD.Data.FaultOfflineAndRecovery", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftUnavailable::RunTest(const FString& Parameters)
{
    GHSMannedForkliftTests::FFixture F;
    if (!TestNotNull(TEXT("Runtime component"), F.Data)) return false;
    auto* Data = F.Data;
    TestEqual(TEXT("No fictitious last-online timestamp"), Data->LastOnlineSeconds, -1.f);
    Data->SetTelemetry(1,3,EGHSMannedForkliftStatus::Running,TEXT("OP-1"),TEXT("A"),TEXT("T1"),TEXT(""));
    TestTrue(TEXT("Online updates timestamp"), Data->LastOnlineSeconds >= 0);
    TestTrue(TEXT("Fault accepts unknown measurements"), Data->SetTelemetry(-1,-1,EGHSMannedForkliftStatus::Fault,
        TEXT("OP-1"),TEXT("A"),TEXT("T1"),TEXT("Hydraulic fault")));
    TestFalse(TEXT("Fault measurements are unknown"), Data->HasTelemetry());
    TestEqual(TEXT("Fault clears load"), Data->LoadTonnes,-1.f);
    TestEqual(TEXT("Fault clears speed"), Data->SpeedKmh,-1.f);
    TestEqual(TEXT("Fault preserves explicitly supplied reason"), Data->Reason,FString(TEXT("Hydraulic fault")));
    const float LastOnline = Data->LastOnlineSeconds;
    TestTrue(TEXT("Disconnect accepted"), Data->SetTelemetry(-1,-1,EGHSMannedForkliftStatus::Offline,
        TEXT("STALE"),TEXT("STALE"),TEXT("STALE"),TEXT("Disconnected")));
    TestTrue(TEXT("Offline clears stale actor metadata"), Data->DriverId.IsEmpty() && Data->Area.IsEmpty() && Data->TaskId.IsEmpty());
    TestEqual(TEXT("Offline retains actual last-online timestamp"), Data->LastOnlineSeconds,LastOnline);
    TestTrue(TEXT("Live recovery accepted"), Data->SetTelemetry(.8f,2,EGHSMannedForkliftStatus::Running,
        TEXT("OP-2"),TEXT("B"),TEXT("T2"),TEXT("")));
    TestTrue(TEXT("Recovery measurements available"), Data->HasTelemetry());
    TestTrue(TEXT("Awaiting data clears supplied metrics too"), Data->SetTelemetry(1,2,EGHSMannedForkliftStatus::AwaitingData,
        TEXT("STALE"),TEXT("STALE"),TEXT("STALE"),TEXT("")));
    TestTrue(TEXT("Awaiting data has no stale content"), !Data->HasTelemetry() && Data->DriverId.IsEmpty() && Data->Area.IsEmpty() && Data->TaskId.IsEmpty());
    const float NaN=std::numeric_limits<float>::quiet_NaN();
    TestFalse(TEXT("Offline NaN is never treated as the unknown sentinel"), Data->SetTelemetry(NaN,-1,
        EGHSMannedForkliftStatus::Offline,TEXT(""),TEXT(""),TEXT(""),TEXT("")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftDemo,
    "GHS.MannedForkliftHUD.Data.DemoIsExplicitAndNeverOverwritesLiveData", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftDemo::RunTest(const FString& Parameters)
{
    TSet<EGHSMannedForkliftStatus> States;
    for (int32 Index=0; Index<8; ++Index)
    {
        auto* Data = NewObject<UGHSMannedForkliftDataComponent>();
        TestTrue(TEXT("Seed deterministic example once"), Data->ApplyDemoState(Index));
        States.Add(Data->Status);
        TestTrue(TEXT("Example provenance is explicit"), Data->bIsDemoData);
        TestFalse(TEXT("Rediscovery cannot reseed demo"), Data->ApplyDemoState(Index+1));
        TestTrue(TEXT("Live update replaces demo"), Data->SetTelemetry(.5f,2,EGHSMannedForkliftStatus::Running,
            TEXT("REAL-1"),TEXT("A"),TEXT("LIVE"),TEXT("")));
        TestFalse(TEXT("Demo cannot overwrite live data"), Data->ApplyDemoState(Index));
        TestTrue(TEXT("Live data retained"), !Data->bIsDemoData && Data->DriverId==TEXT("REAL-1") && Data->LoadTonnes==.5f);
    }
    for (const auto Status : {EGHSMannedForkliftStatus::Running,EGHSMannedForkliftStatus::Idle,
        EGHSMannedForkliftStatus::Warning,EGHSMannedForkliftStatus::Fault,EGHSMannedForkliftStatus::Offline})
        TestTrue(TEXT("All five designed states covered"), States.Contains(Status));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftSeparateTypes,
    "GHS.MannedForkliftHUD.Clustering.ThreeIndependentEquipmentTypes", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftSeparateTypes::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayout;
    FClusterer Clusterer;
    TArray<FItem> Items;
    for (int32 Cell=0; Cell<4; ++Cell)
    for (const FString Type : {FString(TEXT("DockTruck")),FString(TEXT("MannedForklift")),FString(TEXT("Stacker"))})
    for (int32 Member=0; Member<2; ++Member)
        Items.Add({FString::Printf(TEXT("%s-%d-%d"),*Type,Cell,Member),FVector2D(300+Cell%2*960,200+Cell/2*540),FVector2D(190,34),Type});
    const auto& Groups=Clusterer.Update(Items,FVector2D(1920,1080),0,true);
    TestEqual(TEXT("Four groups per type, twelve total"),Groups.Num(),12);
    for (const auto& Group : Groups)
    {
        TestEqual(TEXT("All same-cell same-type members retained"),Group.Members.Num(),2);
        for (const FString& Id : Group.Members)
            TestTrue(TEXT("No cross-type aggregation"),Id.StartsWith(Group.EquipmentType+TEXT("-")));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftDragInIdentity,
    "GHS.MannedForkliftHUD.Identity.UntaggedMeshAndForeignAssetBoundaries", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftDragInIdentity::RunTest(const FString& Parameters)
{
    using namespace GHSMannedForkliftTests;
    FFleetFixture F;
    if (!TestNotNull(TEXT("Approved imported forklift mesh"),F.Mesh)) return false;
    auto* NewVehicle=F.Vehicle(TEXT("DraggedForklift"));
    auto* Foreign=F.Vehicle(TEXT("ForeignBusinessIdentity"));
    auto* OtherMesh=F.Vehicle(TEXT("WrongAsset"));
    if (!NewVehicle || !Foreign || !OtherMesh) return false;
    Foreign->Tags={TEXT("TwinId=BusinessForklift_25"),TEXT("ExternalTelemetry")};
    UStaticMesh* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!TestNotNull(TEXT("Wrong asset fixture"),Cube)) return false;
    OtherMesh->GetStaticMeshComponent()->SetStaticMesh(Cube);
    const TArray<FName> ForeignTags=Foreign->Tags;
    auto* HISM=NewObject<UHierarchicalInstancedStaticMeshComponent>(F.Actor);
    F.Actor->AddInstanceComponent(HISM); HISM->SetStaticMesh(F.Mesh); HISM->RegisterComponent();
    HISM->AddInstance(FTransform::Identity);
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{Foreign,OtherMesh,F.Actor,NewVehicle});
    TestTrue(TEXT("Dragged approved mesh gains a unique identity"),HasNumber(NewVehicle,1));
    TestTrue(TEXT("Dragged approved mesh gains HUD type tag"),NewVehicle->ActorHasTag(TEXT("NormalWarehouseMannedForklift")));
    TestTrue(TEXT("External identity remains byte-for-byte unchanged"),Foreign->Tags==ForeignTags);
    TestTrue(TEXT("Wrong mesh is not registered"),OtherMesh->Tags.IsEmpty());
    TestFalse(TEXT("HUD rejects wrong mesh even with stale manual tags"),UGHSMannedForkliftIdentityLibrary::IsSupportedActor(OtherMesh));
    TestTrue(TEXT("HISM host is not interpreted as one forklift"),F.Actor->Tags.IsEmpty());
    TestEqual(TEXT("Repeated reconciliation is idempotent"),UGHSMannedForkliftIdentityLibrary::ReconcileWorld(F.World),0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftReserveBeforeAllocate,
    "GHS.MannedForkliftHUD.Identity.ReservesOldIdsBeforeAllocatingInStableObjectOrder", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftReserveBeforeAllocate::RunTest(const FString& Parameters)
{
    using namespace GHSMannedForkliftTests;
    FFleetFixture F;
    auto* Alpha=F.Vehicle(TEXT("AlphaNew"));
    auto* Zulu=F.Vehicle(TEXT("ZuluNew"));
    auto* Existing=F.Vehicle(TEXT("ZZZExisting"));
    if (!TestNotNull(TEXT("Approved mesh and actor fixture"),Existing) || !Alpha || !Zulu) return false;
    Existing->Tags={TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_0800"),TEXT("KeepMe")};
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{Zulu,Alpha,Existing});
    TestTrue(TEXT("Existing valid identity spelling is not rewritten"),Existing->ActorHasTag(TEXT("TwinId=GHN_MannedForklift_0800")));
    TestTrue(TEXT("Unrelated tags remain"),Existing->ActorHasTag(TEXT("KeepMe")));
    TestTrue(TEXT("First new object appends after every preexisting number"),HasNumber(Alpha,801));
    TestTrue(TEXT("Second new object assigned deterministically"),HasNumber(Zulu,802));
    TestEqual(TEXT("Reversed discovery order preserves every assignment"),
        UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{Existing,Alpha,Zulu}),0);
    TestTrue(TEXT("Stable assignments survive rediscovery"),HasNumber(Alpha,801) && HasNumber(Zulu,802));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftDuplicateTelemetry,
    "GHS.MannedForkliftHUD.Identity.DuplicateGetsNewIdWithoutStealingLiveOriginal", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftDuplicateTelemetry::RunTest(const FString& Parameters)
{
    using namespace GHSMannedForkliftTests;
    FFleetFixture F;
    auto* Original=F.Vehicle(TEXT("ZuluOriginal"));
    auto* Copy=F.Vehicle(TEXT("AlphaCopy"));
    if (!TestNotNull(TEXT("Original fixture"),Original) || !Copy) return false;
    Original->Tags={TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_07")};
    auto* Live=NewObject<UGHSMannedForkliftDataComponent>(Original);
    Original->AddInstanceComponent(Live); Live->RegisterComponent();
    Live->InitializeFromActorTags();
    Live->SetTelemetry(1.25f,3.f,EGHSMannedForkliftStatus::Running,TEXT("REAL-OP"),TEXT("REAL-AREA"),TEXT("LIVE-TASK"),TEXT("LIVE"));
    Copy->Tags=Original->Tags;
    auto* CopiedData=DuplicateObject<UGHSMannedForkliftDataComponent>(Live,Copy,TEXT("CopiedTelemetry"));
    Copy->AddInstanceComponent(CopiedData); CopiedData->RegisterComponent();
    TestFalse(TEXT("Duplicating a component does not inherit runtime ownership"),CopiedData->IsIdentityBoundToOwner());
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{Copy,Original});
    TestTrue(TEXT("Bound original keeps identity even when discovered last"),HasNumber(Original,7));
    TestTrue(TEXT("Copy gets appended identity"),HasNumber(Copy,8));
    TestTrue(TEXT("Original live telemetry and provenance preserved"),Live->LoadTonnes==1.25f && Live->SpeedKmh==3.f
        && Live->DriverId==TEXT("REAL-OP") && Live->TaskId==TEXT("LIVE-TASK") && !Live->bIsDemoData);
    TestEqual(TEXT("Copy component follows its own identity"),CopiedData->ForkliftId,FString(TEXT("FORK-08")));
    TestTrue(TEXT("Copy loses stale measurements and driver assignment"),!CopiedData->HasTelemetry()
        && CopiedData->DriverId.IsEmpty() && CopiedData->TaskId.IsEmpty() && CopiedData->Area.IsEmpty());
    TestTrue(TEXT("Copy awaits its own telemetry"),CopiedData->Status==EGHSMannedForkliftStatus::AwaitingData);
    TestFalse(TEXT("Rediscovery cannot fill the copy with recycled demo telemetry"),CopiedData->ApplyDemoState(7));
    TestEqual(TEXT("Live original stable over next discovery"),UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{Original,Copy}),0);
    auto* RetaggedCopy=F.Vehicle(TEXT("RetaggedCopy"));
    if (!TestNotNull(TEXT("Retagged duplicate fixture"),RetaggedCopy)) return false;
    RetaggedCopy->Tags={TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_09"),
        TEXT("GHSManualIdentityOwner=ZuluOriginal")};
    auto* RetaggedData=DuplicateObject<UGHSMannedForkliftDataComponent>(Live,RetaggedCopy,TEXT("RetaggedTelemetry"));
    RetaggedCopy->AddInstanceComponent(RetaggedData); RetaggedData->RegisterComponent();
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{RetaggedCopy,Original,Copy});
    TestTrue(TEXT("Manually fixed unique tag remains unchanged"),HasNumber(RetaggedCopy,9));
    TestEqual(TEXT("Retagged clone component uses its own identity"),RetaggedData->ForkliftId,FString(TEXT("FORK-09")));
    TestTrue(TEXT("Retagged clone loses source live data despite having a unique tag"),!RetaggedData->HasTelemetry()
        && RetaggedData->DriverId.IsEmpty() && RetaggedData->TaskId.IsEmpty() && RetaggedData->LastOnlineSeconds==-1.f);
    auto* MatchingIdCopy=F.Vehicle(TEXT("MatchingIdCopy"));
    if (!TestNotNull(TEXT("Matching-ID copied telemetry fixture"),MatchingIdCopy)) return false;
    MatchingIdCopy->Tags={TEXT("NormalWarehouseMannedForklift"),TEXT("TwinId=GHN_MannedForklift_10"),
        TEXT("GHSManualIdentityOwner=ZuluOriginal")};
    auto* MatchingData=DuplicateObject<UGHSMannedForkliftDataComponent>(Live,MatchingIdCopy,TEXT("MatchingTelemetry"));
    MatchingIdCopy->AddInstanceComponent(MatchingData); MatchingData->RegisterComponent();
    MatchingData->ForkliftId=TEXT("FORK-10");
    TestFalse(TEXT("UE duplication resets the transient accepted-update flag"),MatchingData->HasAcceptedTelemetry());
    TestFalse(TEXT("UE duplication resets transient owner binding"),MatchingData->IsIdentityBoundToOwner());
    TestTrue(TEXT("UE duplication still carries nontransient live payload"),MatchingData->HasTelemetry()
        && MatchingData->DriverId==TEXT("REAL-OP"));
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{MatchingIdCopy,RetaggedCopy,Original,Copy});
    TestTrue(TEXT("Copied owner with matching edited ID still clears inherited telemetry"),HasNumber(MatchingIdCopy,10)
        && !MatchingData->HasTelemetry() && MatchingData->DriverId.IsEmpty());
    TestTrue(TEXT("Original live data remains intact after both pre-tagged-copy cases"),Live->LoadTonnes==1.25f
        && Live->SpeedKmh==3.f && Live->DriverId==TEXT("REAL-OP") && Live->TaskId==TEXT("LIVE-TASK") && !Live->bIsDemoData);
    TestEqual(TEXT("Repaired pre-tagged copies remain stable"),
        UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{Original,Copy,RetaggedCopy,MatchingIdCopy}),0);
    auto* EarlyLiveVehicle=F.Vehicle(TEXT("EarlyLiveBeforeIdentity"));
    if (!TestNotNull(TEXT("First-frame live vehicle fixture"),EarlyLiveVehicle)) return false;
    auto* EarlyLive=NewObject<UGHSMannedForkliftDataComponent>(EarlyLiveVehicle);
    EarlyLiveVehicle->AddInstanceComponent(EarlyLive); EarlyLive->RegisterComponent();
    EarlyLive->SetTelemetry(.6f,2.5f,EGHSMannedForkliftStatus::Running,TEXT("EARLY-OP"),TEXT("EARLY-AREA"),TEXT("EARLY-TASK"),TEXT("First frame"));
    TestTrue(TEXT("Telemetry can precede identity assignment"),EarlyLive->ForkliftId.IsEmpty() && EarlyLive->HasAcceptedTelemetry());
    const float EarlyUpdate=EarlyLive->LastUpdateSeconds,EarlyOnline=EarlyLive->LastOnlineSeconds;
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{EarlyLiveVehicle,Original,Copy,RetaggedCopy,MatchingIdCopy});
    TestTrue(TEXT("First-frame vehicle receives appended identity"),HasNumber(EarlyLiveVehicle,11));
    TestTrue(TEXT("First-frame real telemetry survives initial identity binding"),EarlyLive->ForkliftId==TEXT("FORK-11")
        && EarlyLive->HasTelemetry() && EarlyLive->LoadTonnes==.6f && EarlyLive->SpeedKmh==2.5f
        && EarlyLive->DriverId==TEXT("EARLY-OP") && EarlyLive->Area==TEXT("EARLY-AREA")
        && EarlyLive->TaskId==TEXT("EARLY-TASK") && !EarlyLive->bIsDemoData);
    TestTrue(TEXT("First-frame timestamps survive initial identity binding"),
        EarlyLive->LastUpdateSeconds==EarlyUpdate && EarlyLive->LastOnlineSeconds==EarlyOnline);
    TestFalse(TEXT("First-frame accepted data cannot later be replaced by demo"),EarlyLive->ApplyDemoState(0));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftDuplicateOwner,
    "GHS.MannedForkliftHUD.Identity.PersistedOwnerAndLegacyFallbackAreOrderIndependent", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftDuplicateOwner::RunTest(const FString& Parameters)
{
    using namespace GHSMannedForkliftTests;
    FFleetFixture F;
    auto* Original=F.Vehicle(TEXT("ZuluOwner"));
    auto* Copy=F.Vehicle(TEXT("AlphaCopy"));
    auto* LegacyA=F.Vehicle(TEXT("LegacyAlpha"));
    auto* LegacyZ=F.Vehicle(TEXT("LegacyZulu"));
    if (!TestNotNull(TEXT("Owner fixture"),Original) || !Copy || !LegacyA || !LegacyZ) return false;
    Original->Tags={TEXT("TwinId=GHN_MannedForklift_03"),TEXT("GHSManualIdentityOwner=ZuluOwner")};
    Copy->Tags=Original->Tags;
    LegacyA->Tags={TEXT("TwinId=GHN_MannedForklift_09")};
    LegacyZ->Tags=LegacyA->Tags;
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{LegacyZ,Copy,LegacyA,Original});
    TestTrue(TEXT("Persisted owner wins over earlier sorted copy"),HasNumber(Original,3));
    TestTrue(TEXT("Ownerless legacy duplicates use stable object path fallback"),HasNumber(LegacyA,9));
    TestTrue(TEXT("Other legacy copy is given a new ID"),!HasNumber(LegacyZ,9));
    TestTrue(TEXT("Copied owner marker is replaced with its new owning object"),Copy->ActorHasTag(TEXT("GHSManualIdentityOwner=AlphaCopy")));
    const TArray<FName> CopyTags=Copy->Tags,LegacyTags=LegacyZ->Tags;
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(F.World,{Original,LegacyA,Copy,LegacyZ});
    TestTrue(TEXT("Reversing discovery cannot reassign either copy"),Copy->Tags==CopyTags && LegacyZ->Tags==LegacyTags);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSMannedForkliftHighWater,
    "GHS.MannedForkliftHUD.Identity.DeletedIdsAreNotReusedAndHighWaterPersists", GHSMannedForkliftTests::Flags)
bool FGHSMannedForkliftHighWater::RunTest(const FString& Parameters)
{
    using namespace GHSMannedForkliftTests;
    FFleetFixture F;
    auto* Old=F.Vehicle(TEXT("OldVehicle"));
    if (!TestNotNull(TEXT("Old vehicle fixture"),Old)) return false;
    Old->Tags={TEXT("TwinId=GHN_MannedForklift_40")};
    UGHSMannedForkliftIdentityLibrary::ReconcileWorld(F.World);
    F.World->DestroyActor(Old);
    auto* New=F.Vehicle(TEXT("NewVehicle"));
    UGHSMannedForkliftIdentityLibrary::ReconcileWorld(F.World);
    TestTrue(TEXT("Deletion does not recycle old vehicle number"),HasNumber(New,41));
    AWorldSettings* Settings=F.World->GetWorldSettings();
    if (!TestNotNull(TEXT("Persistable world identity metadata"),Settings)) return false;
    TestTrue(TEXT("High-water mark stored on the map"),Settings->ActorHasTag(TEXT("GHSManualIdentityHighWater=41")));
    FFleetFixture Reopened;
    Reopened.World->GetWorldSettings()->Tags=Settings->Tags;
    auto* AfterReload=Reopened.Vehicle(TEXT("NewAfterReload"));
    UGHSMannedForkliftIdentityLibrary::ReconcileWorld(Reopened.World);
    TestTrue(TEXT("Fresh runtime world recovers saved high-water mark"),HasNumber(AfterReload,42));
    return true;
}

#endif
