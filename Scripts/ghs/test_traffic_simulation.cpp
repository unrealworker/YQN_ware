#include "../../Source/Test/GHSCampusTrafficSimulation.h"
#include <cassert>
#include <cstdio>
#include <cmath>
#include <chrono>

static bool SafeHeadway(const GHSTraffic::Simulation& s)
{
    for(size_t i=0;i<s.Vehicles.size();++i)
        for(size_t j=i+1;j<s.Vehicles.size();++j)
        {
            const auto& a=s.Vehicles[i];const auto& b=s.Vehicles[j];
            if(a.Active&&b.Active&&a.Route==b.Route
                && std::abs(a.Distance-b.Distance)-GHSTraffic::HalfLength(a.Kind)-GHSTraffic::HalfLength(b.Kind)<99.99)return false;
        }
    return true;
}

int main()
{
    using namespace GHSTraffic;
    Simulation s;
    s.Initialize({{80000,1000},{90000,1800},{76000,950},{82000,900},{100000,1800},{71000,950}},17335);
    assert(s.ActiveCount()==24);
    for(int route=0;route<6;++route)
    {
        int count=0;for(const auto& v:s.Vehicles)count+=v.Active&&v.Route==route;
        assert(count==4);
    }
    assert(SafeHeadway(s));
    int minimumActive=Capacity,maximumActive=0;
    double activeSum=0;
    const auto started=std::chrono::steady_clock::now();
    for(int step=0;step<72000;++step)
    {
        s.Advance(.05);
        assert(s.ActiveCount()<=Capacity);
        assert(SafeHeadway(s));
        minimumActive=std::min(minimumActive,s.ActiveCount());
        maximumActive=std::max(maximumActive,s.ActiveCount());
        activeSum+=s.ActiveCount();
        for(int route=0;route<6;++route)
        {
            int count=0;for(const auto& v:s.Vehicles)count+=v.Active&&v.Route==route;
            assert(count<=6);
        }
        for(const auto& v:s.Vehicles) if(v.Active)
        {
            assert(v.Route>=0 && v.Route<int(s.Routes.size()));
            assert(v.Distance>=0 && v.Distance<s.Routes[v.Route].Length);
            assert(std::isfinite(v.Distance));
        }
    }
    assert(maximumActive==32 && activeSum/72000>24);
    const double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
    std::printf("One-hour traffic: min=%d max=%d mean=%.2f; simulation plus safety checks=%.3fs\n",minimumActive,maximumActive,activeSum/72000,elapsed);
    assert(s.Completed>100 && s.Spawned>100);
    auto& end=s.Vehicles[0];end.Active=true;end.Route=0;end.Distance=s.Routes[0].Length-.01;end.Speed=1000;
    const auto before=s.Completed;s.Advance(.05);
    assert(!end.Active && end.Cooldown>0 && s.Completed==before+1);
    s.Initialize({{10000,1000}},8);
    for(auto& v:s.Vehicles){v.Active=false;v.Cooldown=100;}
    auto& lead=s.Vehicles[0];lead.Active=true;lead.Route=0;lead.Distance=5000;lead.Speed=0;
    auto& follower=s.Vehicles[1];follower.Active=true;follower.Route=0;follower.Distance=3000;follower.Speed=1200;
    s.Advance(.2);
    assert(follower.Distance < lead.Distance-HalfLength(lead.Kind)-HalfLength(follower.Kind)-99);
    const auto distance=follower.Distance;
    s.Advance(-1);s.Advance(NAN);
    assert(follower.Distance==distance);
    std::puts("PASS denser traffic: 24 initial vehicles, every direction covered, fixed 32-slot pool, 1 hour churn, route bounds, end retirement, all-pair headway and invalid delta");
}
