#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "../GHSTwinHUDWidget.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinRoofHUDFades,
    "GHS.TwinHUD.RoofActivationAndInteriorLabelFades", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FGHSTwinRoofHUDFades::RunTest(const FString&)
{
    FGHSTwinRoofHUDMotion Motion;
    Motion.Advance(true,false,false,1.f);
    TestEqual(TEXT("Closed roof keeps its entrance fully visible"),Motion.WarehouseOpacity(),1.f);
    TestEqual(TEXT("Closed roof has no internal labels"),Motion.InteriorOpacity(),0.f);
    Motion.Advance(false,true,false,.05f);
    // Optimized float division/easing can differ by one ULP; opacity timing does not require bit equality.
    TestNearlyEqual(TEXT("Entrance is half faded after 50ms activation"),Motion.WarehouseOpacity(),.5f,1.e-6f);
    TestEqual(TEXT("Opening never reveals internal labels"),Motion.InteriorOpacity(),0.f);
    Motion.Advance(false,true,false,.05f);
    TestEqual(TEXT("Entrance is gone after 100ms, independent of roof speed"),Motion.WarehouseOpacity(),0.f);
    Motion.Advance(false,true,false,.3f);
    TestEqual(TEXT("Repeated opening updates cannot revive the entrance"),Motion.WarehouseOpacity(),0.f);
    Motion.Advance(false,false,true,.08f);
    TestNearlyEqual(TEXT("Internal labels fade only after full opening"),Motion.InteriorOpacity(),.5f,1.e-6f);
    Motion.Advance(false,false,true,.08f);
    TestEqual(TEXT("Internal labels finish at 160ms"),Motion.InteriorOpacity(),1.f);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinRoofHUDReversal,
    "GHS.TwinHUD.RoofReversalHidesLabelsAndDoesNotReviveEntrance", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FGHSTwinRoofHUDReversal::RunTest(const FString&)
{
    FGHSTwinRoofHUDMotion Motion;
    Motion.Advance(false,true,false,.04f);
    Motion.Advance(false,false,false,.01f);
    TestEqual(TEXT("Closing removes entrance during an interrupted activation"),Motion.WarehouseOpacity(),0.f);
    Motion.Advance(false,true,false,.01f);
    TestEqual(TEXT("Reopening does not bring an already dismissed entrance back"),Motion.WarehouseOpacity(),0.f);
    Motion.Advance(false,false,true,.16f);
    Motion.Advance(false,false,false,.01f);
    TestEqual(TEXT("Closing locks and removes internal labels immediately"),Motion.InteriorOpacity(),0.f);
    Motion.Advance(true,false,false,.01f);
    TestEqual(TEXT("Entrance returns only after restoration finishes"),Motion.WarehouseOpacity(),1.f);
    Motion.Advance(false,true,false,.05f);
    TestNearlyEqual(TEXT("Next fresh opening receives a fresh activation fade"),Motion.WarehouseOpacity(),.5f,1.e-6f);
    const float BeforeInvalidDelta=Motion.WarehouseOpacity();
    Motion.Advance(false,true,false,std::numeric_limits<float>::quiet_NaN());
    Motion.Advance(false,true,false,std::numeric_limits<float>::infinity());
    Motion.Advance(false,true,false,-1.f);
    TestEqual(TEXT("Invalid delta does not contaminate the fade"),Motion.WarehouseOpacity(),BeforeInvalidDelta,0.f);
    return true;
}
#endif
