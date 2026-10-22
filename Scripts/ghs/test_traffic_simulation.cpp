#include "../../Source/Test/GHSCampusTrafficSimulation.h"
#include <cassert>
#include <cstdio>
#include <cmath>
int main()
{
    using namespace GHSTraffic;
    Simulation s;
    s.Initialize({{80000,1000},{90000,1800},{76000,950},{82000,900},{100000,1800},{71000,950}},17335);
    assert(s.ActiveCount()>=6 && s.ActiveCount()<=Capacity);
    for(int step=0;step<72000;++step)
    {
        s.Advance(.05);
        assert(s.ActiveCount()<=Capacity);
        for(const auto& v:s.Vehicles) if(v.Active)
        {
            assert(v.Route>=0 && v.Route<int(s.Routes.size()));
            assert(v.Distance>=0 && v.Distance<s.Routes[v.Route].Length);
            assert(std::isfinite(v.Distance));
        }
    }
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
    std::puts("PASS traffic fixed pool, 1 hour churn, route bounds, end retirement, headway and invalid delta");
}
