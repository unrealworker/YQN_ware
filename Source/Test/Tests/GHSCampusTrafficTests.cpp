#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSCampusTrafficSimulation.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSCampusTrafficPoolTest,"GHS.Twin.Traffic.BoundedLifetimeAndHeadway",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSCampusTrafficPoolTest::RunTest(const FString&)
{
    GHSTraffic::Simulation Simulation;
    Simulation.Initialize({{80000,950},{80000,950},{60000,950},{60000,950},{100000,1800},{100000,1800}},17335);
    TestEqual(TEXT("All directions initially populated"),Simulation.ActiveCount(),12);
    bool Bounded=true,OnRoute=true;
    for(int Step=0;Step<72000;++Step)
    {
        Simulation.Advance(.05);
        Bounded&=Simulation.ActiveCount()<=GHSTraffic::Capacity;
        for(const auto& Vehicle:Simulation.Vehicles)if(Vehicle.Active)
            OnRoute&=Vehicle.Distance>=0&&Vehicle.Distance<Simulation.Routes[Vehicle.Route].Length&&std::isfinite(Vehicle.Distance);
    }
    TestTrue(TEXT("One hour of recycling keeps fixed capacity"),Bounded);
    TestTrue(TEXT("Every active centre stays on its route"),OnRoute);
    TestTrue(TEXT("Vehicles retire and respawn"),Simulation.Completed>100&&Simulation.Spawned>100);
    auto& Last=Simulation.Vehicles[0];Last.Active=true;Last.Route=0;Last.Distance=79999.99;Last.Speed=1000;
    Simulation.Advance(.05);
    TestFalse(TEXT("At road end the vehicle is retired"),Last.Active);
    TestTrue(TEXT("A retired vehicle waits before returning"),Last.Cooldown>0);
    return true;
}
#endif
