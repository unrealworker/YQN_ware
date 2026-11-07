#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

/** Deterministic demonstration scheduling, not vendor PLC logic or live orders.
 * Distances/heights are centimetres. Plan stations come from the scene profile.
 * No actor, physics, wall clock, random generator or asset mutation is involved.
 */
namespace MPRSorter
{
constexpr int CarrierCount=4;
enum class CarrierPhase : uint8_t { EmptyReturn,Scan,LoadedTravel,Lift,Unload };
enum class BlockReason : uint8_t { None,Scanning,Lifting,Unloading,FullBin };

struct Destination
{
    int Side=0,Column=0,Level=0; // Side 0 = local +Y, side 1 = local -Y.
    bool operator==(const Destination& Other) const
    { return Side==Other.Side&&Column==Other.Column&&Level==Other.Level; }
};

struct Config
{
    int Columns=8,Levels=4,BinCapacity=3;
    double LoopLengthCm=0,ChainSpeedCmS=40;
    double LoadHeightCm=103.5,LiftSpeedCmS=55;
    std::vector<double> LevelHeightsCm;
    // Arc-length fraction from +X load point. Index = Side*Columns+Column.
    std::vector<double> DestinationDistances01;
    double ScanSeconds=.5,UnloadSeconds=1.2,CollectSeconds=12;
    bool AutoCollect=true;
    // Empty means a repeatable sweep of both sides, all levels and columns.
    // Explicit sequences are demonstrations too; no real order access is used.
    std::vector<Destination> OrderSequence;
};

struct Carrier
{
    CarrierPhase State=CarrierPhase::EmptyReturn;
    double Distance01=0,LiftHeightCm=0,ScanProgress=0,UnloadProgress=0;
    uint64_t ParcelId=0; // Unique within one machine/reset epoch; qualify with machine ID.
    Destination Target;
};

struct Bin
{
    Destination Target;
    int Occupancy=0,Reserved=0,Capacity=0;
    uint64_t Delivered=0,Collected=0;
    double CollectionRemaining=0;
};

struct Stats
{
    uint64_t Spawned=0,Completed=0,Collected=0;
    int Active=0;
    double SimTime=0,ChainPhase01=0,BlockedSeconds=0;
    bool ChainStopped=false;
    BlockReason Reason=BlockReason::None;
};

class Simulation
{
public:
    // Invalid configuration leaves the previous initialized simulation intact.
    bool Initialize(const Config& InConfig,std::string& Error);
    // Reset keeps the profile; clears parcels, cells and totals; pauses at 1x.
    void Reset();
    void SetPlaying(bool Value) { Playing=Ready&&Value; }
    bool IsPlaying() const { return Playing; }
    bool IsReady() const { return Ready; }
    bool SetRate(double Value);
    double GetRate() const { return Rate; }
    void SetAutoCollect(bool Value);
    bool IsAutoCollectEnabled() const { return AutoCollect; }
    bool ClearBin(Destination Target);
    // Accepted deltas are fully processed, including all boundary events.
    // NaN, negative, and >86400 simulation seconds are rejected without mutation.
    bool Advance(double WallDeltaSeconds);
    const Config& GetConfig() const { return Settings; }
    const std::array<Carrier,CarrierCount>& GetCarriers() const { return Carriers; }
    // Flattened index = (Side*Columns+Column)*Levels+Level.
    const std::vector<Bin>& GetBins() const { return Bins; }
    const Stats& GetStats() const { return Totals; }
    int BinIndex(Destination Target) const;

private:
    void SettleEvents();
    void RefreshStatus();
    void Integrate(double Seconds,bool MoveChain);
    double NextEventSeconds(bool MoveChain) const;
    double TargetHeight(const Carrier& Item) const;
    double TargetDistance(const Carrier& Item) const;
    Destination NextDestination();
    bool AtLoad(const Carrier& Item) const;
    Config Settings;
    std::array<Carrier,CarrierCount> Carriers{};
    std::array<double,CarrierCount> PhaseElapsed{};
    std::vector<Bin> Bins;
    Stats Totals;
    uint64_t NextParcelId=1,NextOrder=0;
    double Rate=1;
    bool Ready=false,Playing=false,AutoCollect=true;
};
}
