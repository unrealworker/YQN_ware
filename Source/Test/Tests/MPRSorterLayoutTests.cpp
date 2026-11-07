#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRSorterSimulationActor.h"
#include "GHSAutomationTestFlags.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterLayoutValidation,"MPR.Sorter.LayoutValidation",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRSorterLayoutValidation::RunTest(const FString&)
{
    FString Original;
    const FString Path=FPaths::ProjectDir()/TEXT("SourceAssets/MPR/sorter_simulation/layout.json");
    if(!TestTrue(TEXT("Archived scene layout is readable"),FFileHelper::LoadFileToString(Original,*Path))
       ||!TestNotNull(TEXT("Engine is available for a temporary world"),GEngine))return false;

    // CreateWorld calls InitializeNewWorld with these lightweight settings.
    // No BeginPlay, game mode, UI, current map or editor world is involved.
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false)
        .ShouldSimulatePhysics(false).CreateNavigation(false).CreateAISystem(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if(!TestNotNull(TEXT("Disposable world created"),World))return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World);World->DestroyWorld(false); };
    auto Spawn=[World]()
    {
        FActorSpawnParameters Params;Params.ObjectFlags|=RF_Transient;
        Params.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        return World->SpawnActor<AMPRSorterSimulationActor>(FVector::ZeroVector,FRotator::ZeroRotator,Params);
    };
    auto* Valid=Spawn();if(!TestNotNull(TEXT("Layout actor spawned"),Valid))return false;
    TestFalse(TEXT("Fixture does not begin gameplay"),Valid->HasActorBegunPlay());
    Valid->LayoutJson=Original;
    if(!TestTrue(TEXT("Real archived layout is accepted"),Valid->LoadLayout()))return false;
    TestEqual(TEXT("Exactly 22 machines parsed"),Valid->Machines.Num(),22);
    int32 Bins=0,Count64=0,Count120=0,Carts=0,PositiveInfeed=0,NegativeInfeed=0;
    for(const auto& M:Valid->Machines)
    {
        Bins+=M.Bins.Num();Carts+=M.Carts.Num();Count64+=M.Profile==TEXT("cad64");Count120+=M.Profile==TEXT("cad120");
        PositiveInfeed+=M.InfeedSide>0;NegativeInfeed+=M.InfeedSide<0;
        TestTrue(TEXT("loading point faces the shared conveyor"),(M.Pickup.X-M.Entry.X)*M.InfeedSide>20);
        const auto& C=M.Simulation.GetConfig();
        TestEqual(TEXT("CAD cart grouping is explicit"),C.CartColumns,M.Profile==TEXT("cad64")?4:5);
        for(int32 Side=0;Side<2;++Side)for(int32 Column=0;Column<C.Columns;++Column)
        {
            double Heading;const FVector At=AMPRSorterSimulationActor::PointOnLoop(C.DestinationDistances01[size_t(Side*C.Columns+Column)]+M.LoadFraction,M.Half,M.Radius,Heading);
            const auto& Bin=M.Bins[(Side*C.Columns+Column)*C.Levels];
            TestTrue(TEXT("load phase rebase preserves the physical target column and side"),FMath::Abs(At.X-Bin.Entry.X)<.01&&(Side==0?At.Y>0:At.Y<0));
        }
    }
    TestEqual(TEXT("Exactly 1632 scene bins parsed"),Bins,1632);
    TestEqual(TEXT("18 CAD64 machines retained"),Count64,18);
    TestEqual(TEXT("4 CAD120 machines retained"),Count120,4);
    TestEqual(TEXT("96 independent carts parsed"),Carts,96);
    TestEqual(TEXT("eleven positive-X loading ends"),PositiveInfeed,11);
    TestEqual(TEXT("eleven negative-X loading ends"),NegativeInfeed,11);

    const TCHAR* Names[]={TEXT("missing profiles"),TEXT("null final world transform"),TEXT("null CAD120 level"),TEXT("duplicate CAD120 bin"),TEXT("missing cart mesh"),TEXT("wrong cart grouping"),TEXT("invalid infeed side")};
    for(int32 Case=0;Case<7;++Case)
    {
        TSharedPtr<FJsonObject> Root;
        if(!TestTrue(TEXT("Fresh fixture JSON parses"),FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Original),Root))||!Root)return false;
        if(Case==0)Root->RemoveField(TEXT("profiles"));
        else if(Case==1)Root->GetArrayField(TEXT("machines")).Last()->AsObject()->SetField(TEXT("world_transform"),MakeShared<FJsonValueNull>());
        else if(Case==6)Root->GetArrayField(TEXT("machines"))[0]->AsObject()->SetNumberField(TEXT("infeed_side_local_x"),0);
        else if(Case==4)Root->GetObjectField(TEXT("profiles"))->GetObjectField(TEXT("cad120"))->GetArrayField(TEXT("carts"))[0]->AsObject()->RemoveField(TEXT("mesh"));
        else if(Case==5)Root->GetObjectField(TEXT("profiles"))->GetObjectField(TEXT("cad64"))->SetArrayField(TEXT("cart_column_groups"),{MakeShared<FJsonValueNumber>(3),MakeShared<FJsonValueNumber>(5)});
        else
        {
            const auto Profile=Root->GetObjectField(TEXT("profiles"))->GetObjectField(TEXT("cad120"));
            const TCHAR* Field=Case==2?TEXT("levels"):TEXT("bins");
            auto Values=Profile->GetArrayField(Field);
            if(Case==2)Values[0]=MakeShared<FJsonValueNull>();else Values.Last()=Values[0];
            Profile->SetArrayField(Field,Values);
        }
        FString Broken;
        if(!TestTrue(TEXT("Malformed fixture serializes"),FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Broken))))return false;
        auto* Invalid=Spawn();if(!TestNotNull(TEXT("Fresh malformed-layout actor spawned"),Invalid))return false;
        Invalid->LayoutJson=Broken;
        TestFalse(FString::Printf(TEXT("Reject %s without crashing"),Names[Case]),Invalid->LoadLayout());
        TestEqual(FString::Printf(TEXT("%s leaves no partial fleet"),Names[Case]),Invalid->Machines.Num(),0);
        TestFalse(FString::Printf(TEXT("%s reports an explanation"),Names[Case]),Invalid->Error.IsEmpty());
        TestFalse(TEXT("Malformed actor never begins play"),Invalid->HasActorBegunPlay());
        // A failure after many valid rows must also preserve an already parsed fleet.
        Valid->LayoutJson=Broken;
        TestFalse(FString::Printf(TEXT("Existing fleet rejects %s"),Names[Case]),Valid->LoadLayout());
        TestEqual(TEXT("Failed reparse preserves all previously valid machines"),Valid->Machines.Num(),22);
    }
    Valid->LayoutJson=Original;
    TestTrue(TEXT("Valid reparse still succeeds"),Valid->LoadLayout());
    TestEqual(TEXT("Successful reparse replaces instead of appending"),Valid->Machines.Num(),22);
    // The native large-delta entry point and a frame-driven fleet must share
    // one aisle coordinator, rather than advancing each machine an entire run.
    for(auto& M:Valid->Machines)M.Simulation.SetPlaying(true);
    TestTrue(TEXT("fleet advances a full deterministic sample"),Valid->AdvanceFleet(800));
    int32 ActiveExchanges=0;uint64 Exchanged=0;
    for(const auto& M:Valid->Machines)
    {
        Exchanged+=M.Simulation.GetStats().ExchangedCarts;
        for(const auto& C:M.Simulation.GetCarts())ActiveExchanges+=C.State!=MPRSorter::CartPhase::Receiving&&C.State!=MPRSorter::CartPhase::FullWaiting;
    }
    TestTrue(TEXT("shared aisle admits at most one moving cart"),ActiveExchanges<=1);
    TestTrue(TEXT("shared aisle eventually releases complete cart exchanges"),Exchanged>0);
    bool SawHandoff=false;
    for(int32 Step=0;Step<1600&&!SawHandoff;++Step)
    {
        Valid->AdvanceFleet(.05);
        for(const auto& M:Valid->Machines)for(int32 I=0;I<M.Carts.Num();++I)
        {
            const auto& C=M.Simulation.GetCarts()[size_t(I)];
            if(C.State!=MPRSorter::CartPhase::Handoff)continue;
            SawHandoff=true;const auto& P=M.Carts[I];
            const FVector Expected(-M.InfeedSide*P.OutboundEndX-P.Origin.X,(P.Side==0?1.:-1.)*P.Retreat,0);
            TestTrue(TEXT("hidden handoff retains the exit location instead of snapping back to dock"),Valid->CartOffset(M,I).Equals(Expected,.001));
            TestTrue(TEXT("handoff retains the complete old cart load with no reserved deliveries"),C.Occupancy==C.Capacity&&C.Reserved==0&&C.ParcelIds.size()==size_t(C.Occupancy));
            TestTrue(TEXT("handoff still owns the shared aisle"),M.Simulation.IsExchangePermitted()&&M.Simulation.GetStats().ChainStopped);
        }
    }
    TestTrue(TEXT("fleet presents a separate whole-cart handoff interval"),SawHandoff);
    return true;
}
#endif
