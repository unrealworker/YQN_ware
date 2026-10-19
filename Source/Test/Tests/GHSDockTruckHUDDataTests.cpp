#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSDockTruckDataComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Misc/AutomationTest.h"

namespace GHSDockTruckHUDDataTests
{
    constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;

    // Use a real runtime actor: identifying trucks must not depend on editor labels.
    struct FFixture
    {
        UWorld* World = nullptr;
        AActor* Truck = nullptr;
        UGHSDockTruckDataComponent* Data = nullptr;

        FFixture()
        {
            World = UWorld::CreateWorld(EWorldType::Game, false);
            if (!World || !GEngine) return;
            GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
            World->InitializeActorsForPlay(FURL());

            FActorSpawnParameters Spawn;
            Spawn.ObjectFlags |= RF_Transient;
            Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            Truck = World->SpawnActor<AActor>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
            if (Truck)
            {
                Truck->Tags = {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_002"), TEXT("Dock=2")};
                Data = NewObject<UGHSDockTruckDataComponent>(Truck);
                Truck->AddInstanceComponent(Data);
                Data->RegisterComponent();
            }
        }

        ~FFixture()
        {
            if (World)
            {
                if (GEngine) GEngine->DestroyWorldContext(World);
                World->DestroyWorld(false);
            }
        }

        bool Check(FAutomationTestBase& Test) const
        {
            return Test.TestNotNull(TEXT("Transient game world"), World)
                && Test.TestNotNull(TEXT("Runtime truck actor"), Truck)
                && Test.TestNotNull(TEXT("Truck data component"), Data);
        }
    };

    struct FTelemetrySnapshot
    {
        int32 Loaded;
        int32 Total;
        EGHSDockTruckStatus Status;
        FString Order;
        bool bDemo;
        float LastUpdate;

        explicit FTelemetrySnapshot(const UGHSDockTruckDataComponent& Data)
            : Loaded(Data.LoadedPallets), Total(Data.TotalPallets), Status(Data.Status),
              Order(Data.OrderId), bDemo(Data.bIsDemoData), LastUpdate(Data.LastUpdateSeconds) {}

        void CheckUnchanged(FAutomationTestBase& Test, const UGHSDockTruckDataComponent& Data) const
        {
            Test.TestEqual(TEXT("Rejected update preserves loaded count"), Data.LoadedPallets, Loaded);
            Test.TestEqual(TEXT("Rejected update preserves total count"), Data.TotalPallets, Total);
            Test.TestTrue(TEXT("Rejected update preserves status"), Data.Status == Status);
            Test.TestEqual(TEXT("Rejected update preserves order"), Data.OrderId, Order);
            Test.TestEqual(TEXT("Rejected update preserves demo flag"), Data.bIsDemoData, bDemo);
            Test.TestEqual(TEXT("Rejected update preserves timestamp"), Data.LastUpdateSeconds, LastUpdate);
        }
    };
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDockTruckIdentityFromRuntimeTags,
    "GHS.DockTruckHUD.Data.IdentityFromRuntimeTags", GHSDockTruckHUDDataTests::Flags)

bool FGHSDockTruckIdentityFromRuntimeTags::RunTest(const FString& Parameters)
{
    GHSDockTruckHUDDataTests::FFixture F;
    if (!F.Check(*this)) return false;

    TestTrue(TEXT("Runtime tags initialize identity"), F.Data->InitializeFromActorTags());
    TestEqual(TEXT("Twin ID becomes truck number"), F.Data->TruckId, FString(TEXT("TRUCK-002")));
    TestEqual(TEXT("Dock number is padded for display"), F.Data->DockId, FString(TEXT("DOCK-02")));

    F.Truck->Tags = {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_1002"), TEXT("Dock=123")};
    TestTrue(TEXT("Large valid identifiers initialize"), F.Data->InitializeFromActorTags());
    TestEqual(TEXT("Truck numbers are not truncated"), F.Data->TruckId, FString(TEXT("TRUCK-1002")));
    TestEqual(TEXT("Dock numbers are not truncated"), F.Data->DockId, FString(TEXT("DOCK-123")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDockTruckRejectsMalformedIdentity,
    "GHS.DockTruckHUD.Data.RejectsMissingOrMalformedTags", GHSDockTruckHUDDataTests::Flags)

bool FGHSDockTruckRejectsMalformedIdentity::RunTest(const FString& Parameters)
{
    GHSDockTruckHUDDataTests::FFixture F;
    if (!F.Check(*this)) return false;
    TestTrue(TEXT("Initial identity succeeds"), F.Data->InitializeFromActorTags());

    const TArray<TArray<FName>> InvalidTags = {
        {},
        {TEXT("TwinId=GHS_DockTruck_003"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=Other_003"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_3x"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_-3"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_0"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_2147483648"), TEXT("Dock=3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003"), TEXT("Dock=")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003"), TEXT("Dock=3x")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003"), TEXT("Dock=-3")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003"), TEXT("Dock=0")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003"), TEXT("Dock=2147483648")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003"), TEXT("Dock=3"), TEXT("Dock=4")},
        {TEXT("IndependentDockTruck"), TEXT("TwinId=GHS_DockTruck_003"), TEXT("TwinId=GHS_DockTruck_004"), TEXT("Dock=3")}
    };
    for (int32 Index = 0; Index < InvalidTags.Num(); ++Index)
    {
        F.Truck->Tags = InvalidTags[Index];
        TestFalse(FString::Printf(TEXT("Invalid tag set %d is rejected"), Index), F.Data->InitializeFromActorTags());
        TestEqual(TEXT("Invalid identity does not partially replace truck"), F.Data->TruckId, FString(TEXT("TRUCK-002")));
        TestEqual(TEXT("Invalid identity does not partially replace dock"), F.Data->DockId, FString(TEXT("DOCK-02")));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDockTruckDefaultsToUnknownData,
    "GHS.DockTruckHUD.Data.DefaultsToUnknown", GHSDockTruckHUDDataTests::Flags)

bool FGHSDockTruckDefaultsToUnknownData::RunTest(const FString& Parameters)
{
    GHSDockTruckHUDDataTests::FFixture F;
    if (!F.Check(*this)) return false;
    TestTrue(TEXT("Identity can initialize without telemetry"), F.Data->InitializeFromActorTags());
    TestFalse(TEXT("Identity alone does not invent telemetry"), F.Data->HasTelemetry());
    TestTrue(TEXT("Initial state awaits data"), F.Data->Status == EGHSDockTruckStatus::AwaitingData);
    TestEqual(TEXT("Loaded count is unknown"), F.Data->LoadedPallets, -1);
    TestEqual(TEXT("Total count is unknown"), F.Data->TotalPallets, -1);
    TestEqual(TEXT("Remaining count is unknown"), F.Data->GetRemainingPallets(), -1);
    TestEqual(TEXT("Unknown progress is zero"), F.Data->GetLoadingProgress(), 0.0f);
    TestTrue(TEXT("Order is empty"), F.Data->OrderId.IsEmpty());
    TestFalse(TEXT("Demo mode is opt-in"), F.Data->bIsDemoData);
    TestEqual(TEXT("No telemetry timestamp is invented"), F.Data->LastUpdateSeconds, -1.0f);
    TestFalse(TEXT("Data component requires no per-frame tick"), F.Data->PrimaryComponentTick.bCanEverTick);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDockTruckRejectsInvalidTelemetryAtomically,
    "GHS.DockTruckHUD.Data.RejectsInvalidTelemetryAtomically", GHSDockTruckHUDDataTests::Flags)

bool FGHSDockTruckRejectsInvalidTelemetryAtomically::RunTest(const FString& Parameters)
{
    GHSDockTruckHUDDataTests::FFixture F;
    if (!F.Check(*this)) return false;
    TestTrue(TEXT("Valid telemetry accepted"), F.Data->SetTelemetry(18, 24, EGHSDockTruckStatus::Loading, TEXT("ORDER-42"), true));
    const GHSDockTruckHUDDataTests::FTelemetrySnapshot Before(*F.Data);

    struct FInvalidUpdate { int32 Loaded; int32 Total; EGHSDockTruckStatus Status; };
    const FInvalidUpdate InvalidUpdates[] = {
        {-1, 24, EGHSDockTruckStatus::Loading},
        {25, 24, EGHSDockTruckStatus::Loading},
        {0, 0, EGHSDockTruckStatus::Docked},
        {0, -1, EGHSDockTruckStatus::Warning},
        {-1, -1, EGHSDockTruckStatus::Fault},
        {-2, -2, EGHSDockTruckStatus::Offline},
        {-1, 24, EGHSDockTruckStatus::AwaitingData},
        {1, 24, static_cast<EGHSDockTruckStatus>(255)}
    };
    for (const FInvalidUpdate& Update : InvalidUpdates)
    {
        TestFalse(TEXT("Invalid update rejected"), F.Data->SetTelemetry(Update.Loaded, Update.Total, Update.Status, TEXT("REJECTED"), false));
        Before.CheckUnchanged(*this, *F.Data);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDockTruckUnavailableClearsStaleTelemetry,
    "GHS.DockTruckHUD.Data.UnavailableClearsStaleTelemetry", GHSDockTruckHUDDataTests::Flags)

bool FGHSDockTruckUnavailableClearsStaleTelemetry::RunTest(const FString& Parameters)
{
    GHSDockTruckHUDDataTests::FFixture F;
    if (!F.Check(*this)) return false;

    for (const EGHSDockTruckStatus Unavailable : {EGHSDockTruckStatus::Offline, EGHSDockTruckStatus::AwaitingData})
    {
        TestTrue(TEXT("Seed live telemetry"), F.Data->SetTelemetry(18, 24, EGHSDockTruckStatus::Loading, TEXT("ORDER-42")));
        TestTrue(TEXT("Unavailable state accepts unknown counts"), F.Data->SetTelemetry(-1, -1, Unavailable, TEXT("STALE-ORDER")));
        TestTrue(TEXT("Unavailable status retained"), F.Data->Status == Unavailable);
        TestFalse(TEXT("Unavailable data is not live telemetry"), F.Data->HasTelemetry());
        TestEqual(TEXT("Unavailable clears loaded count"), F.Data->LoadedPallets, -1);
        TestEqual(TEXT("Unavailable clears total count"), F.Data->TotalPallets, -1);
        TestEqual(TEXT("Unavailable remaining is unknown"), F.Data->GetRemainingPallets(), -1);
        TestEqual(TEXT("Unavailable progress is zero"), F.Data->GetLoadingProgress(), 0.0f);
        TestTrue(TEXT("Unavailable clears stale order"), F.Data->OrderId.IsEmpty());

        TestTrue(TEXT("Unavailable state accepts valid count input"), F.Data->SetTelemetry(18, 24, Unavailable, TEXT("STALE-ORDER")));
        TestEqual(TEXT("Unavailable discards even valid loaded input"), F.Data->LoadedPallets, -1);
        TestEqual(TEXT("Unavailable discards even valid total input"), F.Data->TotalPallets, -1);
        TestTrue(TEXT("Unavailable discards supplied order"), F.Data->OrderId.IsEmpty());
    }
    TestTrue(TEXT("Telemetry can recover after offline"), F.Data->SetTelemetry(6, 24, EGHSDockTruckStatus::Loading, TEXT("ORDER-43")));
    TestTrue(TEXT("Recovered telemetry is available"), F.Data->HasTelemetry());
    TestEqual(TEXT("Recovered order shown"), F.Data->OrderId, FString(TEXT("ORDER-43")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDockTruckProgressAndDemoProvenance,
    "GHS.DockTruckHUD.Data.ProgressAndDemoProvenance", GHSDockTruckHUDDataTests::Flags)

bool FGHSDockTruckProgressAndDemoProvenance::RunTest(const FString& Parameters)
{
    GHSDockTruckHUDDataTests::FFixture F;
    if (!F.Check(*this)) return false;

    for (const EGHSDockTruckStatus Available : {EGHSDockTruckStatus::Docked, EGHSDockTruckStatus::Loading,
        EGHSDockTruckStatus::Warning, EGHSDockTruckStatus::Fault})
    {
        TestTrue(TEXT("Operational status accepts valid counts"), F.Data->SetTelemetry(18, 24, Available, TEXT("DEMO-42"), true));
        TestTrue(TEXT("Valid counts are available"), F.Data->HasTelemetry());
        TestEqual(TEXT("Six pallets remain"), F.Data->GetRemainingPallets(), 6);
        TestEqual(TEXT("Progress is three quarters"), F.Data->GetLoadingProgress(), 0.75f);
        TestTrue(TEXT("Demo provenance is explicit"), F.Data->bIsDemoData);
        TestTrue(TEXT("Accepted update records world timestamp"), F.Data->LastUpdateSeconds >= 0.0f);
    }
    TestTrue(TEXT("Empty load is accepted"), F.Data->SetTelemetry(0, 24, EGHSDockTruckStatus::Docked, TEXT("ORDER-44")));
    TestEqual(TEXT("Empty load has zero progress"), F.Data->GetLoadingProgress(), 0.0f);
    TestEqual(TEXT("All pallets remain"), F.Data->GetRemainingPallets(), 24);
    TestFalse(TEXT("Real update clears demo provenance"), F.Data->bIsDemoData);
    TestTrue(TEXT("Full load is accepted"), F.Data->SetTelemetry(24, 24, EGHSDockTruckStatus::Loading, TEXT("ORDER-44")));
    TestEqual(TEXT("Full load has full progress"), F.Data->GetLoadingProgress(), 1.0f);
    TestEqual(TEXT("Nothing remains"), F.Data->GetRemainingPallets(), 0);
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
