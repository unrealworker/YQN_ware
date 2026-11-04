#if WITH_DEV_AUTOMATION_TESTS
#include "../EnvironmentRenderProfileLease.h"
#include "GHSAutomationTestFlags.h"
#include <limits>

namespace
{
using EnvironmentRenderProfilePrivate::FConsoleFloatLease;

struct FLeaseFixture
{
    IConsoleVariable* Variable;
    TUniquePtr<FConsoleFloatLease> Lease;

    FLeaseFixture()
    {
        Variable = IConsoleManager::Get().RegisterConsoleVariable(
            TEXT("test.EnvironmentRenderProfile.Lease"), 1200.f, TEXT("Automation-only lease target"), ECVF_Default);
        Lease = MakeUnique<FConsoleFloatLease>(*Variable);
    }
    ~FLeaseFixture()
    {
        Lease.Reset();
        IConsoleManager::Get().UnregisterConsoleObject(Variable, false);
    }
};
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnvironmentProfileMaxLease,
    "Environment.RenderProfile.MaxLeaseAndRestore",
    GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FEnvironmentProfileMaxLease::RunTest(const FString&)
{
    FLeaseFixture F;
    int EditorActor = 0, PIEActor = 0;
    const EConsoleVariableFlags PriorFlags = F.Variable->GetFlags();
    TestTrue(TEXT("First world acquires"), F.Lease->Set(&EditorActor, 5000.f));
    TestEqual(TEXT("Editor extent"), F.Variable->GetFloat(), 5000.f);
    TestTrue(TEXT("Constructor priority is never replaced by SETBY_ERROR"), F.Variable->GetFlags() == PriorFlags);
    F.Lease->Set(&PIEActor, 6500.f);
    TestEqual(TEXT("Simultaneous worlds use maximum"), F.Variable->GetFloat(), 6500.f);
    F.Lease->Set(&PIEActor, 4000.f);
    TestEqual(TEXT("Changing one owner recomputes maximum"), F.Variable->GetFloat(), 5000.f);
    F.Lease->Release(&EditorActor);
    TestEqual(TEXT("Unloading one world retains the other"), F.Variable->GetFloat(), 4000.f);
    F.Lease->Release(&EditorActor);
    TestEqual(TEXT("Double release is inert"), F.Variable->GetFloat(), 4000.f);
    F.Lease->Release(&PIEActor);
    TestEqual(TEXT("Final unload restores prior value"), F.Variable->GetFloat(), 1200.f);
    TestTrue(TEXT("Priority and flags are unchanged"), F.Variable->GetFlags() == PriorFlags);
    F.Variable->Set(TEXT("1234.56738"));
    const float PrecisePrior = F.Variable->GetFloat();
    F.Lease->Set(&EditorActor, 5000.f);
    F.Lease->Release(&EditorActor);
    TestEqual(TEXT("Prior float also round-trips without GetString truncation"), F.Variable->GetFloat(), PrecisePrior);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnvironmentProfileExternalLease,
    "Environment.RenderProfile.ExternalChangesWin",
    GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FEnvironmentProfileExternalLease::RunTest(const FString&)
{
    FLeaseFixture F;
    int A = 0, B = 0;
    F.Lease->Set(&A, 5000.f);
    F.Variable->Set(7200.f, ECVF_SetByConsole);
    F.Lease->Set(&B, 9000.f);
    TestEqual(TEXT("A new actor does not fight an external console change"), F.Variable->GetFloat(), 7200.f);
    F.Lease->Release(&A);
    F.Lease->Release(&B);
    TestEqual(TEXT("Unload does not restore stale prior value"), F.Variable->GetFloat(), 7200.f);
    TestTrue(TEXT("External priority is preserved"), (F.Variable->GetFlags() & ECVF_SetByMask) == ECVF_SetByConsole);
    F.Lease->Set(&A, 5000.f);
    F.Lease->Release(&A);
    TestEqual(TEXT("Next lease session captures the latest external baseline"), F.Variable->GetFloat(), 7200.f);
    F.Lease->Set(&A, 5000.f);
    F.Variable->Set(5000.f, ECVF_SetByConsole);
    F.Lease->Release(&A);
    TestEqual(TEXT("Same-value external intent is also preserved"), F.Variable->GetFloat(), 5000.f);
    bool bWriteOnce = true;
    const FDelegateHandle Reentrant = F.Variable->OnChangedDelegate().AddLambda(
        [&bWriteOnce](IConsoleVariable* Variable)
        {
            if (bWriteOnce)
            {
                bWriteOnce = false;
                Variable->Set(6500.f, ECVF_SetByConsole);
            }
        });
    F.Lease->Set(&A, 6500.f);
    F.Lease->Release(&A);
    TestEqual(TEXT("A reentrant same-value observer still wins"), F.Variable->GetFloat(), 6500.f);
    F.Variable->OnChangedDelegate().Remove(Reentrant);
    F.Lease->Set(&A, 5000.f);
    F.Variable->Set(7300.f, static_cast<EConsoleVariableFlags>(ECVF_SetByConsole | ECVF_Set_SetOnly_Unsafe));
    F.Lease->Release(&A);
    TestEqual(TEXT("An unsafe silent external write is still preserved"), F.Variable->GetFloat(), 7300.f);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnvironmentProfileInvalidLease,
    "Environment.RenderProfile.InvalidRequestsAndCleanup",
    GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FEnvironmentProfileInvalidLease::RunTest(const FString&)
{
    FLeaseFixture F;
    int Owner = 0, OtherCallbackCount = 0;
    const FDelegateHandle OtherHandle = F.Variable->OnChangedDelegate().AddLambda(
        [&OtherCallbackCount](IConsoleVariable*) { ++OtherCallbackCount; });
    TestFalse(TEXT("Null owner rejected"), F.Lease->Set(nullptr, 5000.f));
    TestFalse(TEXT("Nonfinite extent rejected"), F.Lease->Set(&Owner, std::numeric_limits<float>::quiet_NaN()));
    TestFalse(TEXT("Nonpositive extent rejected"), F.Lease->Set(&Owner, 0.f));
    TestEqual(TEXT("Invalid request leaves CVar unchanged"), F.Variable->GetFloat(), 1200.f);
    F.Lease->Set(&Owner, 5123.45654f);
    TestEqual(TEXT("Float is not truncated to six significant digits"), F.Variable->GetFloat(), 5123.45654f);
    F.Lease.Reset();
    TestEqual(TEXT("RAII cleanup restores leaked active lease"), F.Variable->GetFloat(), 1200.f);
    TestTrue(TEXT("Other CVar observers remain installed"), OtherCallbackCount >= 2);
    F.Variable->Set(1400.f);
    TestTrue(TEXT("Our cleanup did not remove another observer"), OtherCallbackCount >= 3);
    F.Variable->OnChangedDelegate().Remove(OtherHandle);
    return true;
}
#endif
