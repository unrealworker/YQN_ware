#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSStackerDataComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Misc/AutomationTest.h"
#include <limits>

namespace GHSStackerDataTests
{
    constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;

    struct FFixture
    {
        UWorld* World = nullptr;
        AActor* Stacker = nullptr;
        UGHSStackerDataComponent* Data = nullptr;

        FFixture()
        {
            World = UWorld::CreateWorld(EWorldType::Game, false);
            if (!World || !GEngine) return;
            GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
            World->InitializeActorsForPlay(FURL());
            FActorSpawnParameters Spawn;
            Spawn.ObjectFlags |= RF_Transient;
            Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            Stacker = World->SpawnActor<AActor>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
            if (!Stacker) return;
            Stacker->Tags = {TEXT("NormalWarehouseFloorStacker"), TEXT("TwinId=GHN_FloorStacker_02")};
            Data = NewObject<UGHSStackerDataComponent>(Stacker);
            Stacker->AddInstanceComponent(Data);
            Data->RegisterComponent();
        }

        ~FFixture()
        {
            if (!World) return;
            if (GEngine) GEngine->DestroyWorldContext(World);
            World->DestroyWorld(false);
        }

        bool Check(FAutomationTestBase& Test) const
        {
            return Test.TestNotNull(TEXT("Transient game world"), World)
                && Test.TestNotNull(TEXT("Runtime stacker actor"), Stacker)
                && Test.TestNotNull(TEXT("Stacker data component"), Data);
        }
    };

    struct FSnapshot
    {
        float Battery;
        float Height;
        EGHSStackerStatus Status;
        FString Task;
        bool bDemo;
        float Timestamp;

        explicit FSnapshot(const UGHSStackerDataComponent& Data)
            : Battery(Data.BatteryPercent), Height(Data.ForkHeightCm), Status(Data.Status),
              Task(Data.TaskId), bDemo(Data.bIsDemoData), Timestamp(Data.LastUpdateSeconds) {}

        void CheckUnchanged(FAutomationTestBase& Test, const UGHSStackerDataComponent& Data) const
        {
            Test.TestEqual(TEXT("Rejected update preserves battery"), Data.BatteryPercent, Battery);
            Test.TestEqual(TEXT("Rejected update preserves fork height"), Data.ForkHeightCm, Height);
            Test.TestTrue(TEXT("Rejected update preserves status"), Data.Status == Status);
            Test.TestEqual(TEXT("Rejected update preserves task"), Data.TaskId, Task);
            Test.TestEqual(TEXT("Rejected update preserves provenance"), Data.bIsDemoData, bDemo);
            Test.TestEqual(TEXT("Rejected update preserves timestamp"), Data.LastUpdateSeconds, Timestamp);
        }
    };
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStackerRuntimeIdentity,
    "GHS.StackerHUD.Data.RuntimeIdentity", GHSStackerDataTests::Flags)

bool FGHSStackerRuntimeIdentity::RunTest(const FString& Parameters)
{
    GHSStackerDataTests::FFixture F;
    if (!F.Check(*this)) return false;
    TestTrue(TEXT("Runtime tags identify the stacker without an editor label"), F.Data->InitializeFromActorTags());
    TestEqual(TEXT("Display identity is normalized"), F.Data->StackerId, FString(TEXT("STACKER-02")));
    TestTrue(TEXT("Explicit identity supports runtime-spawned stackers"), F.Data->InitializeIdentity(TEXT("STACKER-003")));
    TestEqual(TEXT("Explicit leading zeros normalize"), F.Data->StackerId, FString(TEXT("STACKER-03")));
    TestTrue(TEXT("Large valid IDs are not truncated"), F.Data->InitializeIdentity(TEXT("STACKER-1024")));
    TestEqual(TEXT("Large identity retained"), F.Data->StackerId, FString(TEXT("STACKER-1024")));

    for (const FString Invalid : {TEXT(""), TEXT("STACKER-"), TEXT("STACKER-0"), TEXT("STACKER--2"),
        TEXT("STACKER-2x"), TEXT("STACKER-2147483648"), TEXT("OTHER-02"), TEXT(" STACKER-02")})
    {
        TestFalse(TEXT("Malformed explicit identity is rejected"), F.Data->InitializeIdentity(Invalid));
        TestEqual(TEXT("Rejected identity does not replace existing identity"), F.Data->StackerId, FString(TEXT("STACKER-1024")));
    }

    const TArray<TArray<FName>> InvalidTags = {
        {}, {TEXT("TwinId=GHN_FloorStacker_02")}, {TEXT("NormalWarehouseFloorStacker")},
        {TEXT("NormalWarehouseFloorStacker"), TEXT("TwinId=Other_02")},
        {TEXT("NormalWarehouseFloorStacker"), TEXT("TwinId=GHN_FloorStacker_0")},
        {TEXT("NormalWarehouseFloorStacker"), TEXT("TwinId=GHN_FloorStacker_02x")},
        {TEXT("NormalWarehouseFloorStacker"), TEXT("TwinId=GHN_FloorStacker_02"), TEXT("TwinId=GHN_FloorStacker_03")}
    };
    for (const TArray<FName>& Tags : InvalidTags)
    {
        F.Stacker->Tags = Tags;
        TestFalse(TEXT("Missing or ambiguous runtime identity is rejected"), F.Data->InitializeFromActorTags());
        TestEqual(TEXT("Rejected tags preserve identity"), F.Data->StackerId, FString(TEXT("STACKER-1024")));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStackerUnknownUntilSupplied,
    "GHS.StackerHUD.Data.UnknownUntilSupplied", GHSStackerDataTests::Flags)

bool FGHSStackerUnknownUntilSupplied::RunTest(const FString& Parameters)
{
    GHSStackerDataTests::FFixture F;
    if (!F.Check(*this)) return false;
    TestTrue(TEXT("Identity can be initialized before telemetry"), F.Data->InitializeFromActorTags());
    TestFalse(TEXT("Identity does not fabricate telemetry"), F.Data->HasTelemetry());
    TestTrue(TEXT("Initial status awaits data"), F.Data->Status == EGHSStackerStatus::AwaitingData);
    TestEqual(TEXT("Battery is unknown before supplied"), F.Data->BatteryPercent, -1.0f);
    TestEqual(TEXT("Fork height is unknown before supplied"), F.Data->ForkHeightCm, -1.0f);
    TestTrue(TEXT("Task is unknown before supplied"), F.Data->TaskId.IsEmpty());
    TestFalse(TEXT("Demo data is explicit"), F.Data->bIsDemoData);
    TestEqual(TEXT("No update timestamp is invented"), F.Data->LastUpdateSeconds, -1.0f);

    for (const EGHSStackerStatus State : {EGHSStackerStatus::Running, EGHSStackerStatus::Idle,
        EGHSStackerStatus::Warning, EGHSStackerStatus::Fault})
    {
        TestTrue(TEXT("Available states accept fractional measurements"), F.Data->SetTelemetry(82.5f, 150.5f, State, TEXT("TASK-42")));
        TestTrue(TEXT("Accepted measurements are available"), F.Data->HasTelemetry());
        TestEqual(TEXT("Battery precision is preserved"), F.Data->BatteryPercent, 82.5f);
        TestEqual(TEXT("Fork height remains in centimeters"), F.Data->ForkHeightCm, 150.5f);
        TestTrue(TEXT("Accepted update records world time"), F.Data->LastUpdateSeconds >= 0.0f);
    }
    TestTrue(TEXT("Empty battery and ground-level forks are valid"), F.Data->SetTelemetry(0, 0, EGHSStackerStatus::Idle, TEXT("")));
    TestTrue(TEXT("Fully charged battery is valid"), F.Data->SetTelemetry(100, 300, EGHSStackerStatus::Running, TEXT("TASK-43")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStackerRejectsInvalidTelemetryAtomically,
    "GHS.StackerHUD.Data.RejectsInvalidTelemetryAtomically", GHSStackerDataTests::Flags)

bool FGHSStackerRejectsInvalidTelemetryAtomically::RunTest(const FString& Parameters)
{
    GHSStackerDataTests::FFixture F;
    if (!F.Check(*this)) return false;
    TestTrue(TEXT("Seed valid telemetry"), F.Data->SetTelemetry(82, 180, EGHSStackerStatus::Running, TEXT("TASK-42"), true));
    const GHSStackerDataTests::FSnapshot Before(*F.Data);
    const float NaN = std::numeric_limits<float>::quiet_NaN();
    const float Inf = std::numeric_limits<float>::infinity();
    struct FUpdate { float Battery; float Height; EGHSStackerStatus Status; };
    const FUpdate InvalidUpdates[] = {
        {-1, 100, EGHSStackerStatus::Running}, {101, 100, EGHSStackerStatus::Idle},
        {50, -1, EGHSStackerStatus::Warning}, {-1, -1, EGHSStackerStatus::Fault},
        {NaN, 100, EGHSStackerStatus::Running}, {50, NaN, EGHSStackerStatus::Idle},
        {Inf, 100, EGHSStackerStatus::Warning}, {50, Inf, EGHSStackerStatus::Fault},
        {-2, -2, EGHSStackerStatus::Offline}, {-1, 100, EGHSStackerStatus::AwaitingData},
        {NaN, -1, EGHSStackerStatus::Offline}, {50, 100, static_cast<EGHSStackerStatus>(255)}
    };
    for (const FUpdate& Update : InvalidUpdates)
    {
        TestFalse(TEXT("Malformed telemetry is rejected"), F.Data->SetTelemetry(Update.Battery, Update.Height,
            Update.Status, TEXT("REJECTED"), false));
        Before.CheckUnchanged(*this, *F.Data);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStackerUnavailableClearsAndRecovers,
    "GHS.StackerHUD.Data.UnavailableClearsAndRecovers", GHSStackerDataTests::Flags)

bool FGHSStackerUnavailableClearsAndRecovers::RunTest(const FString& Parameters)
{
    GHSStackerDataTests::FFixture F;
    if (!F.Check(*this)) return false;
    for (const EGHSStackerStatus State : {EGHSStackerStatus::Offline, EGHSStackerStatus::AwaitingData})
    {
        TestTrue(TEXT("Seed live telemetry"), F.Data->SetTelemetry(78, 150, EGHSStackerStatus::Running, TEXT("TASK-42")));
        TestTrue(TEXT("Unavailable state accepts unknown metrics"), F.Data->SetTelemetry(-1, -1, State, TEXT("STALE")));
        TestTrue(TEXT("Unavailable state retained"), F.Data->Status == State);
        TestFalse(TEXT("Unavailable metrics cannot be displayed as current"), F.Data->HasTelemetry());
        TestEqual(TEXT("Stale battery is cleared"), F.Data->BatteryPercent, -1.0f);
        TestEqual(TEXT("Stale fork height is cleared"), F.Data->ForkHeightCm, -1.0f);
        TestTrue(TEXT("Stale task is cleared"), F.Data->TaskId.IsEmpty());
        TestTrue(TEXT("Unavailable state accepts and discards complete metrics"), F.Data->SetTelemetry(78, 150, State, TEXT("STALE")));
        TestEqual(TEXT("Even supplied battery is unavailable"), F.Data->BatteryPercent, -1.0f);
        TestEqual(TEXT("Even supplied height is unavailable"), F.Data->ForkHeightCm, -1.0f);
        TestTrue(TEXT("Even supplied task is unavailable"), F.Data->TaskId.IsEmpty());
    }
    TestTrue(TEXT("Live data recovers after offline"), F.Data->SetTelemetry(63, 90, EGHSStackerStatus::Running, TEXT("TASK-43")));
    TestTrue(TEXT("Recovered data is available"), F.Data->HasTelemetry());
    TestEqual(TEXT("Recovered task is current"), F.Data->TaskId, FString(TEXT("TASK-43")));
    TestFalse(TEXT("Real telemetry provenance is retained"), F.Data->bIsDemoData);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStackerDemoCoverageAndRealDataProtection,
    "GHS.StackerHUD.Data.DemoCoverageAndRealDataProtection", GHSStackerDataTests::Flags)

bool FGHSStackerDemoCoverageAndRealDataProtection::RunTest(const FString& Parameters)
{
    TSet<EGHSStackerStatus> States;
    for (int32 Index = 0; Index < 12; ++Index)
    {
        UGHSStackerDataComponent* Data = NewObject<UGHSStackerDataComponent>();
        TestTrue(TEXT("Pristine component accepts an explicit demo sample"), Data->ApplyDemoState(Index));
        States.Add(Data->Status);
        TestTrue(TEXT("Every demo sample is marked as demo"), Data->bIsDemoData);
        TestTrue(TEXT("Demo never masquerades as awaiting real data"), Data->Status != EGHSStackerStatus::AwaitingData);
        TestEqual(TEXT("Offline sample exposes no current measurements"), Data->HasTelemetry(), Data->Status != EGHSStackerStatus::Offline);
        const GHSStackerDataTests::FSnapshot Demo(*Data);
        TestFalse(TEXT("Repeated demo initialization cannot overwrite an existing sample"), Data->ApplyDemoState(Index + 1));
        Demo.CheckUnchanged(*this, *Data);
        TestTrue(TEXT("Real telemetry replaces demo immediately"), Data->SetTelemetry(57, 125, EGHSStackerStatus::Running, TEXT("LIVE-42")));
        TestFalse(TEXT("Live telemetry clears demo provenance"), Data->bIsDemoData);
        const GHSStackerDataTests::FSnapshot Live(*Data);
        TestFalse(TEXT("Demo initialization never overwrites real telemetry"), Data->ApplyDemoState(Index));
        Live.CheckUnchanged(*this, *Data);
    }
    TestEqual(TEXT("Twelve demos cover all five requested states"), States.Num(), 5);
    for (const EGHSStackerStatus State : {EGHSStackerStatus::Running, EGHSStackerStatus::Idle,
        EGHSStackerStatus::Warning, EGHSStackerStatus::Fault, EGHSStackerStatus::Offline})
        TestTrue(TEXT("Requested state appears in demo fleet"), States.Contains(State));

    UGHSStackerDataComponent* Offline = NewObject<UGHSStackerDataComponent>();
    TestFalse(TEXT("Negative demo index is rejected"), Offline->ApplyDemoState(-1));
    TestTrue(TEXT("Explicit offline is accepted without a world"), Offline->SetTelemetry(-1, -1, EGHSStackerStatus::Offline, TEXT("")));
    TestFalse(TEXT("Real offline state cannot be overwritten by demo even without a timestamp"), Offline->ApplyDemoState(0));
    TestTrue(TEXT("Real offline remains offline"), Offline->Status == EGHSStackerStatus::Offline);
    TestFalse(TEXT("Real offline provenance remains live"), Offline->bIsDemoData);
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
