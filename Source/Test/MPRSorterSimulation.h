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
enum class CarrierPhase : uint8_t { EmptyReturn,Scan,LoadedTravel,Lift,Unload,Induct };
enum class BlockReason : uint8_t { None,Scanning,Lifting,Unloading,FullBin,Inducting,CartExchange,WaitingInfeed };
enum class CartPhase : uint8_t { Receiving,FullWaiting,Withdrawing,Outbound,EmptyArriving,Docking,Handoff };

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
    // Explicit CAD groups may use different widths. Only the supplied 96-chute
    // manual documents eight 3-column x 4-level carts; fallback tails are demo.
    int CartColumns=3,InfeedCapacity=8;
    double InfeedTravelSeconds=4,InfeedSpacingSeconds=1,InductSeconds=.8;
    double CartWithdrawSeconds=4,CartOutboundSeconds=5,CartEmptyArrivalSeconds=4,CartDockSeconds=2,CartHandoffSeconds=2;
    // Empty means a repeatable sweep of both sides, all levels and columns.
    // Explicit sequences are demonstrations too; no real order access is used.
    std::vector<Destination> OrderSequence;
};

struct Carrier
{
    CarrierPhase State=CarrierPhase::EmptyReturn;
    double Distance01=0,LiftHeightCm=0,ScanProgress=0,UnloadProgress=0,InductProgress=0;
    uint64_t ParcelId=0; // Unique within one machine/reset epoch; qualify with machine ID.
    Destination Target;
    int TargetCartIndex=-1;
    uint64_t TargetCartGeneration=0;
};

struct Bin
{
    Destination Target;
    int Occupancy=0,Reserved=0,Capacity=0;
    uint64_t Delivered=0,Collected=0;
    double CollectionRemaining=0;
    int CartId=-1;
    std::vector<uint64_t> ParcelIds;
};

struct InfeedParcel { uint64_t ParcelId=0; double Progress01=0; };
struct Cart
{
    int Index=0,Side=0,FirstColumn=0,ColumnCount=0,Levels=0,Capacity=0,Occupancy=0,Reserved=0;
    CartPhase State=CartPhase::Receiving;
    double Progress01=0;
    uint64_t Generation=1,Collected=0;
    // ParcelIds is a cart manifest indexing the bin-owned parcels, not a second
    // owner. It remains loaded through Outbound and the off-machine handoff.
    // Generation changes when a distinct empty replacement starts arriving.
    // History is bounded to one trip.
    std::vector<uint64_t> ParcelIds,LastOutboundParcelIds;
    bool ExchangeRequested=false;
};

struct Stats
{
    uint64_t Spawned=0,Completed=0,Collected=0;
    int Active=0;
    double SimTime=0,ChainPhase01=0,BlockedSeconds=0;
    bool ChainStopped=false;
    BlockReason Reason=BlockReason::None;
    int Queued=0;
    uint64_t InfeedReceived=0,ExchangedCarts=0;
    bool WaitingForCart=false;
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
    // Compatibility ClearBin requests the complete full cart; never clears a bin.
    bool RequestCartExchange(int Index);
    // Shared-aisle presentation coordinator may hold a full cart in place.
    // This never changes the user's automatic/manual collection preference.
    void SetExchangePermit(bool Value);
    bool IsExchangePermitted() const { return ExchangePermit; }
    int CartIndex(Destination Target) const;
    // Accepted deltas are fully processed, including all boundary events.
    // NaN, negative, and >86400 simulation seconds are rejected without mutation.
    bool Advance(double WallDeltaSeconds);
    const Config& GetConfig() const { return Settings; }
    const std::array<Carrier,CarrierCount>& GetCarriers() const { return Carriers; }
    // Flattened index = (Side*Columns+Column)*Levels+Level.
    const std::vector<Bin>& GetBins() const { return Bins; }
    const Stats& GetStats() const { return Totals; }
    const std::vector<Cart>& GetCarts() const { return Carts; }
    const std::vector<InfeedParcel>& GetInfeedQueue() const { return Infeed; }
    int BinIndex(Destination Target) const;

private:
    void SettleEvents();
    void RefreshStatus();
    void Integrate(double Seconds,bool MoveChain);
    double NextEventSeconds(bool MoveChain) const;
    double TargetHeight(const Carrier& Item) const;
    double TargetDistance(const Carrier& Item) const;
    bool FindDestination(Destination& Result) const;
    bool ExchangePending() const;
    bool HasCarrierCargo() const;
    bool FeedEnabled() const;
    double FeedFrontLimit() const;
    double CartDuration(CartPhase Phase) const;
    bool AtLoad(const Carrier& Item) const;
    Config Settings;
    std::array<Carrier,CarrierCount> Carriers{};
    std::array<double,CarrierCount> PhaseElapsed{};
    std::vector<Bin> Bins;
    std::vector<Cart> Carts;
    std::vector<InfeedParcel> Infeed;
    Stats Totals;
    uint64_t NextParcelId=1,NextOrder=0;
    double Rate=1;
    double ArrivalRemaining=0,CartElapsed=0;
    int ActiveCart=-1,PreferredCart=0;
    bool Ready=false,Playing=false,AutoCollect=true;
    bool ExchangePermit=true;
};
}
