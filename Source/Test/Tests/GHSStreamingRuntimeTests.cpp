#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSStreamingRuntime.h"
#include "HAL/IConsoleManager.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStreamingValidBudgetTest,"GHS.Streaming.Runtime.AcceptsFiniteOrderedBudget",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSStreamingValidBudgetTest::RunTest(const FString&)
{
    GHSStreamingRuntime::FBudget Budget; FString Error;
    TestTrue(TEXT("Accept launcher budget"),GHSStreamingRuntime::ParseBudget(TEXT("{\"version\":1,\"sequence\":7,\"fps\":42,\"minBitrateMbps\":8,\"startBitrateMbps\":20,\"maxBitrateMbps\":50}"),Budget,Error));
    TestEqual(TEXT("Acknowledged sequence"),Budget.Sequence,int64(7));
    TestEqual(TEXT("Frame budget"),Budget.FPS,42);
    TestEqual(TEXT("Min bitrate"),Budget.MinBitrateMbps,8.);
    TestEqual(TEXT("Max bitrate"),Budget.MaxBitrateMbps,50.);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStreamingRejectBudgetTest,"GHS.Streaming.Runtime.RejectsCommandsAndInvalidNumbersWithoutMutation",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSStreamingRejectBudgetTest::RunTest(const FString&)
{
    const FString Base=TEXT("{\"version\":1,\"sequence\":1,\"fps\":60,\"minBitrateMbps\":8,\"maxBitrateMbps\":50");
    TArray<FString> Invalid={Base+TEXT(",\"command\":\"quit\"}"),Base+TEXT(",\"startBitrateMbps\":100}"),TEXT("[]"),TEXT("{}"),TEXT("{\"version\":1"),Base+TEXT(",\"fps\":1e100}")};
    Invalid.Add(Base.Replace(TEXT("\"fps\":60"),TEXT("\"fps\":0"))+TEXT("}"));
    Invalid.Add(Base.Replace(TEXT("\"fps\":60"),TEXT("\"fps\":60.5"))+TEXT("}"));
    Invalid.Add(Base.Replace(TEXT("\"sequence\":1"),TEXT("\"sequence\":0"))+TEXT("}"));
    Invalid.Add(Base.Replace(TEXT("\"sequence\":1"),TEXT("\"sequence\":9007199254740992"))+TEXT("}"));
    Invalid.Add(Base.Replace(TEXT("\"minBitrateMbps\":8"),TEXT("\"minBitrateMbps\":80"))+TEXT("}"));
    Invalid.Add(Base.Replace(TEXT("\"version\":1"),TEXT("\"version\":2"))+TEXT("}"));
    Invalid.Add(Base.Replace(TEXT("\"fps\":60"),TEXT("\"fps\":\"60\""))+TEXT("}"));
    for(const FString& Json:Invalid)
    {
        GHSStreamingRuntime::FBudget Budget; Budget.FPS=37; Budget.Sequence=9; FString Error;
        TestFalse(TEXT("Reject invalid or unrecognized input"),GHSStreamingRuntime::ParseBudget(Json,Budget,Error));
        TestEqual(TEXT("Preserve prior frame limit"),Budget.FPS,37);
        TestEqual(TEXT("Preserve prior sequence"),Budget.Sequence,int64(9));
        TestFalse(TEXT("Explain rejection"),Error.IsEmpty());
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStreamingLiveBudgetTest,"GHS.Streaming.Runtime.AppliesLiveFrameBudgetAndRejectsReplay",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSStreamingLiveBudgetTest::RunTest(const FString&)
{
    const TCHAR* Names[]={TEXT("t.MaxFPS"),TEXT("PixelStreaming.WebRTC.Fps"),TEXT("PixelStreaming.WebRTC.MinBitrate"),TEXT("PixelStreaming.WebRTC.MaxBitrate")};
    TArray<FString> Previous;
    for(const TCHAR* Name:Names)
    {
        auto* Var=IConsoleManager::Get().FindConsoleVariable(Name);
        if(!TestNotNull(Name,Var)) return false;
        Previous.Add(Var->GetString());
    }
    GHSStreamingRuntime::FBudget Budget; Budget.Sequence=1; Budget.FPS=37; Budget.MinBitrateMbps=4; Budget.MaxBitrateMbps=44;
    int64 Sequence=0; FString Error;
    IConsoleManager::Get().FindConsoleVariable(Names[1])->Set(60,ECVF_SetByConsole);
    TestTrue(TEXT("Apply without restarting UE"),GHSStreamingRuntime::ApplyBudget(Budget,Sequence,Error));
    TestEqual(TEXT("Rendering workload throttled"),IConsoleManager::Get().FindConsoleVariable(Names[0])->GetInt(),37);
    TestEqual(TEXT("Negotiated RTP ceiling must remain at full capacity"),IConsoleManager::Get().FindConsoleVariable(Names[1])->GetInt(),60);
    TestEqual(TEXT("Acknowledged only after apply"),Sequence,int64(1));
    Budget.FPS=12;
    TestFalse(TEXT("An old sequence cannot replace the live budget"),GHSStreamingRuntime::ApplyBudget(Budget,Sequence,Error));
    TestEqual(TEXT("Replay leaves live rendering unchanged"),IConsoleManager::Get().FindConsoleVariable(Names[0])->GetInt(),37);
    Budget.Sequence=2; Budget.FPS=60;
    TestTrue(TEXT("Disconnect can immediately restore frame capacity"),GHSStreamingRuntime::ApplyBudget(Budget,Sequence,Error));
    TestEqual(TEXT("Restored FPS"),IConsoleManager::Get().FindConsoleVariable(Names[0])->GetInt(),60);
    TestEqual(TEXT("Existing RTP stream permits full restored capacity"),IConsoleManager::Get().FindConsoleVariable(Names[1])->GetInt(),60);
    for(int32 Index=0;Index<UE_ARRAY_COUNT(Names);++Index) IConsoleManager::Get().FindConsoleVariable(Names[Index])->Set(*Previous[Index],ECVF_SetByConsole);
    return true;
}
#endif
