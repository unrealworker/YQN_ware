#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSCampusTrafficSimulation.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSCampusTrafficPoolTest,"GHS.Twin.Traffic.BoundedLifetimeAndHeadway",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSCampusTrafficPoolTest::RunTest(const FString&)
{
    GHSTraffic::Simulation Simulation;
    Simulation.Initialize({{80000,950},{80000,950},{60000,950},{60000,950},{100000,1800},{100000,1800}},17335);
    TestEqual(TEXT("Traffic starts with twice the previous visible count"),Simulation.ActiveCount(),24);
    for(int Route=0;Route<6;++Route)
    {
        int Count=0;for(const auto& Vehicle:Simulation.Vehicles)Count+=Vehicle.Active&&Vehicle.Route==Route ? 1 : 0;
        TestEqual(TEXT("Each direction starts with four spaced vehicles"),Count,4);
    }
    bool Bounded=true,OnRoute=true,SafeHeadway=true,RouteDensityBounded=true;
    double ActiveTotal=0;
    int PeakActive=0;
    for(int Step=0;Step<72000;++Step)
    {
        Simulation.Advance(.05);
        Bounded&=Simulation.ActiveCount()<=GHSTraffic::Capacity;
        ActiveTotal+=Simulation.ActiveCount();
        PeakActive=std::max(PeakActive,Simulation.ActiveCount());
        for(int Route=0;Route<6;++Route)
        {
            int Count=0;for(const auto& Vehicle:Simulation.Vehicles)Count+=Vehicle.Active&&Vehicle.Route==Route ? 1 : 0;
            RouteDensityBounded&=Count<=GHSTraffic::MaxPerRoute;
        }
        for(const auto& Vehicle:Simulation.Vehicles)if(Vehicle.Active)
            OnRoute&=Vehicle.Distance>=0&&Vehicle.Distance<Simulation.Routes[Vehicle.Route].Length&&std::isfinite(Vehicle.Distance);
        for(size_t I=0;I<Simulation.Vehicles.size();++I)
            for(size_t J=I+1;J<Simulation.Vehicles.size();++J)
            {
                const auto& A=Simulation.Vehicles[I];const auto& B=Simulation.Vehicles[J];
                if(A.Active&&B.Active&&A.Route==B.Route)
                    SafeHeadway&=std::abs(A.Distance-B.Distance)-GHSTraffic::HalfLength(A.Kind)-GHSTraffic::HalfLength(B.Kind)>=99.99;
            }
    }
    TestTrue(TEXT("One hour of recycling keeps fixed capacity"),Bounded);
    TestTrue(TEXT("Every active centre stays on its route"),OnRoute);
    TestTrue(TEXT("Vehicles retain clearance even at the higher density"),SafeHeadway);
    TestTrue(TEXT("No direction exceeds its vehicle limit"),RouteDensityBounded);
    TestEqual(TEXT("Traffic can fill the expanded fixed pool"),PeakActive,32);
    TestTrue(TEXT("Average traffic remains above the initial twenty-four vehicles"),ActiveTotal/72000>24);
    TestTrue(TEXT("Vehicles retire and respawn"),Simulation.Completed>100&&Simulation.Spawned>100);
    auto& Last=Simulation.Vehicles[0];Last.Active=true;Last.Route=0;Last.Distance=79999.99;Last.Speed=1000;
    Simulation.Advance(.05);
    TestFalse(TEXT("At road end the vehicle is retired"),Last.Active);
    TestTrue(TEXT("A retired vehicle waits before returning"),Last.Cooldown>0);
    return true;
}
#endif
