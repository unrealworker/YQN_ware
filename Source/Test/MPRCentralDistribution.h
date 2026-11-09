#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

// Demonstration scheduling for the shared CAD distribution loop, not vendor PLC
// timing. UE geometry maps the normalized distances to its actual conveyor path.
namespace MPRCentral
{
enum class CarrierPhase : uint8_t { Loading,Travel,Discharging,EmptyReturn,Retracting,Recovering };

struct Config
{
    double LoopLengthCm=0,SpeedCmS=100,LoadingSeconds=1.2,TransferSeconds=1.,RecoverySeconds=1.;
    // Loading starts upstream so the moving tray meets the fixed feed port at
    // this fraction. Discharge reaches its fixed port at transfer completion.
    double FeedHandoffProgress=.8;
    int MaxPendingPerTarget=4;
    int CarrierCount=1;
    std::vector<double> FeedDistances01;
    // Array index identifies the destination sorter in this bank.
    std::vector<double> TargetDistances01;
};

struct Carrier
{
    CarrierPhase Phase=CarrierPhase::EmptyReturn;
    double Distance01=0,Progress01=0;
    uint64_t ParcelId=0;
    // Recovering has no parcel but retains its station until the empty tray
    // finishes lifting from transfer height to circulation height.
    int SourceStation=-1,TargetIndex=-1;
};

struct Stats
{
    double SimTime=0,LoopPhase01=0;
    uint64_t Generated=0,Delivered=0,BlockedPasses=0;
    int Active=0;
    bool LoopStopped=false;
};

class Simulation
{
public:
    using CanAcceptCallback=std::function<bool(int)>;
    using AcceptCallback=std::function<bool(int,uint64_t)>;
    bool Initialize(const Config& InConfig,std::string& Error);
    // The owner resets the shared global ID counter only when all banks reset.
    void Reset();
    void SetPlaying(bool Value) { Playing=Ready&&Value;Totals.LoopStopped=!Playing; }
    void SetFeedingEnabled(bool Value) { FeedingEnabled=Value; }
    bool IsFeedingEnabled() const { return FeedingEnabled; }
    bool IsPlaying() const { return Playing; }
    bool IsReady() const { return Ready; }
    // Delta is already simulation time: the actor applies the common rate once.
    // Failed acceptance retracts the parcel onto its carrier before another lap.
    bool Advance(double SimDeltaSeconds,uint64_t& NextGlobalParcelId,
        const CanAcceptCallback& CanAccept,const AcceptCallback& Accept);
    const Config& GetConfig() const { return Settings; }
    const std::vector<Carrier>& GetCarriers() const { return Carriers; }
    const Stats& GetStats() const { return Totals; }
    const std::vector<uint64_t>& GetFeedCounts() const { return FeedCounts; }

private:
    struct Stop { double Distance01=0;int SourceStation=-1,TargetIndex=-1; };
    void SettleEvents(uint64_t& NextGlobalParcelId,const CanAcceptCallback& CanAccept,const AcceptCallback& Accept);
    void Integrate(double Seconds);
    double NextEventSeconds() const;
    int FindTarget(const Carrier& Incoming,const CanAcceptCallback& CanAccept) const;
    double EarliestHandoffSeconds(size_t CarrierIndex,int Target) const;
    bool IsOldestForTarget(const Carrier& C) const;
    bool CanFeedAt(int Source) const;
    Config Settings;
    std::vector<Carrier> Carriers;
    std::vector<Stop> Stops;
    std::vector<size_t> NextStops;
    std::vector<double> Elapsed;
    std::vector<uint64_t> FeedCounts;
    Stats Totals;
    int NextTarget=0;
    bool Ready=false,Playing=false,FeedingEnabled=true;
};
}
