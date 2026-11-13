#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRSorterSimulationActor.h"
#include "GHSAutomationTestFlags.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Components/InstancedStaticMeshComponent.h"
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
    int32 Bins=0,Count64=0,Count120=0,Carts=0,PositiveInfeed=0,NegativeInfeed=0,ExternalInfeed=0;
    for(const auto& M:Valid->Machines)
    {
        Bins+=M.Bins.Num();Carts+=M.Carts.Num();Count64+=M.Profile==TEXT("cad64");Count120+=M.Profile==TEXT("cad120");
        PositiveInfeed+=M.InfeedSide>0;NegativeInfeed+=M.InfeedSide<0;
        const auto& C=M.Simulation.GetConfig();
        ExternalInfeed+=C.ExternalInfeed;
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
    TestEqual(TEXT("all 22 sorters receive original parcels from the shared distributor"),ExternalInfeed,22);
    TestEqual(TEXT("two independent CAD distributor banks parsed"),Valid->DistributionBanks.Num(),2);
    int32 ManualSources=0,ExternalSources=0;TSet<int32> ConnectedMachines;
    bool Connected=true,Continuous=true,FeedClear=true,BranchClear=true;
    UStaticMesh* TrayMesh=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/MPRWarehouse/SorterSimulation/Meshes/SM_MPR_SorterSimTray.SM_MPR_SorterSimTray"));
    if(!TestNotNull(TEXT("Production tray mesh supplies the independent clearance envelope"),TrayMesh))return false;
    const FBox TrayBounds=TrayMesh->GetBoundingBox();
    const double OutwardHalf=-TrayBounds.Min.Y;
    const double AlongHalf=FMath::Max(FMath::Abs(TrayBounds.Min.X),FMath::Abs(TrayBounds.Max.X));
    TestTrue(TEXT("The real tray asset has the expected outward carrying edge"),FMath::IsNearlyEqual(OutwardHalf,12.5,.02));
    for(const auto& B:Valid->DistributionBanks)
    {
        TestEqual(TEXT("each source and destination has a physical powered connection"),B.Belts.Num(),B.Stations.Num()+B.Targets.Num());
        TestEqual(TEXT("bank destination count matches its CAD profile"),B.Targets.Num(),B.Profile==TEXT("cad64")?18:4);
        for(int32 I=0;I<B.Stations.Num();++I)
        {
            const auto& Station=B.Stations[I];ManualSources+=Station.bManual;ExternalSources+=!Station.bManual;
            const auto& Belt=B.Belts[I];double Heading;
            FVector Rail=MPRCentralGeometry::CentralPoint(B.Geometry,Station.Distance01,Heading);Rail.Z=Belt.End.Z;
            const FVector Out=(Station.Drop-Rail).GetSafeNormal();
            const double Gap=FVector::DotProduct(Belt.End-Rail,Out)-OutwardHalf*1.6;
            FeedClear&=Gap>=1.9&&Gap<=2.1&&Belt.Start.Equals(Station.Drop,.001);
        }
        for(int32 I=0;I<B.Targets.Num();++I)
        {
            const int32 Target=B.Targets[I];Connected&=!ConnectedMachines.Contains(Target);ConnectedMachines.Add(Target);
            const auto& M=Valid->Machines[Target];const auto& Belt=B.Belts[B.Stations.Num()+I];
            const FVector Entry=M.World.TransformPosition(M.Entry),Handoff=M.World.TransformPosition(M.FeedStart);
            const FVector Pickup=M.World.TransformPosition(M.Pickup),Flow=(Belt.End-Belt.Start).GetSafeNormal();
            const double Length=(Belt.End-Belt.Start).Size(),Along=FVector::DotProduct(Handoff-Belt.Start,Flow);
            Connected&=Length>25&&Along>=0&&Along<Length
                &&Handoff.Equals(Belt.Start+Flow*Along,.001)&&FVector::DotProduct(Pickup-Handoff,Flow)>0
                &&FVector::DotProduct(Belt.End-Pickup,Flow)>0&&FVector::DotProduct(Entry-Belt.End,Flow)>0;
            double Heading;FVector Track=MPRCentralGeometry::CentralPoint(B.Geometry,
                B.Simulation.GetConfig().TargetDistances01[size_t(I)],Heading);Track.Z=Belt.Start.Z;
            const double CentralGap=FVector::DotProduct(Belt.Start-Track,Flow)-OutwardHalf*1.6;
            const double TurnSweep=FMath::Sqrt(FMath::Square(M.Radius+OutwardHalf)+FMath::Square(AlongHalf))-M.Radius;
            const double SorterGap=FVector::DotProduct(Entry-Belt.End,Flow)-TurnSweep;
            BranchClear&=CentralGap>=1.9&&CentralGap<=2.1&&SorterGap>=1.9&&SorterGap<=2.1;
            MPRCentral::Carrier Carrier;Carrier.Phase=MPRCentral::CarrierPhase::Discharging;
            Carrier.ParcelId=1;Carrier.TargetIndex=I;Carrier.Progress01=1;
            Carrier.Distance01=B.Simulation.GetConfig().TargetDistances01[size_t(I)];
            Continuous&=Valid->CentralParcelPoint(B,Carrier).Equals(M.World.TransformPosition(Valid->FeedPoint(M,0)),.001);
        }
    }
    TestEqual(TEXT("only the six CAD loading stations have manual operators"),ManualSources,6);
    TestEqual(TEXT("CAD120 bank uses one explicit external source"),ExternalSources,1);
    TestTrue(TEXT("all 22 powered branches connect distributor handoff through intake to the real sorter entry"),Connected&&ConnectedMachines.Num()==22);
    TestTrue(TEXT("central parcel and receiving queue meet at exactly the same handoff endpoint"),Continuous);
    TestTrue(TEXT("All seven induction belts stop 2 cm outside the real moving tray instead of entering its centre"),FeedClear);
    TestTrue(TEXT("All 22 branch belts clear the central tray and the receiving tray's complete curved corner sweep"),BranchClear);

    // Check the produced geometry as well as its nominal endpoints: a terminal
    // drive plate used to protrude 2 cm past End into the reserved clearance.
    bool SolidClear=true,TurnSolidClear=true;int32 TestedTrayPoses=0,TestedTurnPoses=0;
    UStaticMesh* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    if(!TestNotNull(TEXT("Native cube geometry is available"),Cube))return false;
    for(const auto& B:Valid->DistributionBanks)
    {
        TArray<UInstancedStaticMeshComponent*> Parts;
        for(int32 I=0;I<4;++I)
        {auto* Part=NewObject<UInstancedStaticMeshComponent>(Valid);Part->SetStaticMesh(Cube);Parts.Add(Part);}
        TArray<MPRCentralGeometry::Feed> Stations;
        for(const auto& S:B.Stations)if(S.bManual)
        {MPRCentralGeometry::Feed F;F.OperatorFeet=S.Feet;F.YawDegrees=S.Yaw;F.Drop=S.Drop;Stations.Add(F);}
        MPRCentralGeometry::Build(B.Geometry,B.Belts,Stations,Parts[0],Parts[1],Parts[2],Parts[3]);
        TArray<FBox> FixedBoxes;
        for(auto* Part:Parts)for(int32 I=0;I<Part->GetInstanceCount();++I)
        {FTransform T;Part->GetInstanceTransform(I,T,true);FixedBoxes.Add(Cube->GetBoundingBox().TransformBy(T));}
        for(const auto& Station:B.Stations)for(int32 Step=-16;Step<=16;++Step)
        {
            double Heading;
            const double Fraction=Station.Distance01+Step*3./B.Simulation.GetConfig().LoopLengthCm;
            FVector Point=MPRCentralGeometry::CentralPoint(B.Geometry,Fraction,Heading);Point.Z=103.5;
            // Deck, belt and side rails; the inboard carriage deliberately mates
            // with its moving column and is not part of the outward handoff.
            const FBox Deck(FVector(-AlongHalf,-OutwardHalf,-5.5),FVector(AlongHalf,OutwardHalf,3));
            const FBox Moving=Deck.TransformBy(FTransform(FQuat(FVector::UpVector,Heading),Point,FVector(1.6,1.6,1)));
            for(const FBox& Fixed:FixedBoxes)
            {
                const FVector Overlap=Moving.Max.ComponentMin(Fixed.Max)-Moving.Min.ComponentMax(Fixed.Min);
                SolidClear&=Overlap.GetMin()<=.03;
            }
            ++TestedTrayPoses;
        }
        for(int32 Target:B.Targets)for(int32 Step=-20;Step<=20;++Step)
        {
            const auto& M=Valid->Machines[Target];double Heading;
            FVector Point=AMPRSorterSimulationActor::PointOnLoop(M.LoadFraction+Step*.003,M.Half,M.Radius,Heading);
            Point.Z=M.Simulation.GetConfig().LoadHeightCm;
            const FBox Deck(FVector(-AlongHalf,-OutwardHalf,-5.5),FVector(AlongHalf,OutwardHalf,3));
            const FTransform Pose=FTransform(FQuat(FVector::UpVector,Heading),Point)*M.World;
            // Test actual oriented deck corners against a belt's half-space.
            // World AABBs would overestimate a rotating rectangle near a turn.
            const FVector Entry=M.World.TransformPosition(M.Entry);
            const auto& Branch=B.Belts[B.Stations.Num()+B.Targets.IndexOfByKey(Target)];
            const FVector Out=(Branch.Start-Entry).GetSafeNormal();
            const double FixedEdge=FVector::DotProduct(Branch.End-Entry,Out);
            for(int32 Corner=0;Corner<8;++Corner)
            {
                const FVector Local(Corner&1?Deck.Max.X:Deck.Min.X,Corner&2?Deck.Max.Y:Deck.Min.Y,Corner&4?Deck.Max.Z:Deck.Min.Z);
                TurnSolidClear&=FVector::DotProduct(Pose.TransformPosition(Local)-Entry,Out)<=FixedEdge-1.9;
            }
            ++TestedTurnPoses;
        }
    }
    TestTrue(TEXT("All generated fixed parts clear the moving tray across every source port, including both sides and terminal housings"),
        SolidClear&&TestedTrayPoses==7*33);
    TestTrue(TEXT("The real tray corners stay outside all 22 fixed receiving belts throughout their return bends"),
        TurnSolidClear&&TestedTurnPoses==22*41);

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
    auto SameFleet=[](const AMPRSorterSimulationActor* A,const AMPRSorterSimulationActor* B)
    {
        auto Near=[](double X,double Y){return FMath::Abs(X-Y)<1.e-7;};
        if(A->NextCentralParcelId!=B->NextCentralParcelId||!Near(A->FleetTimeRemainder,B->FleetTimeRemainder)
           ||A->ExchangeOwner!=B->ExchangeOwner||A->Machines.Num()!=B->Machines.Num()
           ||A->DistributionBanks.Num()!=B->DistributionBanks.Num())return false;
        for(int32 I=0;I<A->DistributionBanks.Num();++I)
        {
            const auto& X=A->DistributionBanks[I].Simulation;const auto& Y=B->DistributionBanks[I].Simulation;
            const auto& P=X.GetStats();const auto& Q=Y.GetStats();
            if(P.Generated!=Q.Generated||P.Delivered!=Q.Delivered||P.Active!=Q.Active||P.BlockedPasses!=Q.BlockedPasses
               ||P.LoopStopped!=Q.LoopStopped||!Near(P.SimTime,Q.SimTime)||!Near(P.LoopPhase01,Q.LoopPhase01)
               ||X.IsPlaying()!=Y.IsPlaying())return false;
            for(size_t J=0;J<X.GetCarriers().size();++J)
            {
                const auto& U=X.GetCarriers()[J];const auto& V=Y.GetCarriers()[J];
                if(U.Phase!=V.Phase||U.ParcelId!=V.ParcelId||U.SourceStation!=V.SourceStation||U.TargetIndex!=V.TargetIndex
                   ||!Near(U.Distance01,V.Distance01)||!Near(U.Progress01,V.Progress01))return false;
            }
        }
        for(int32 I=0;I<A->Machines.Num();++I)
        {
            const auto& X=A->Machines[I].Simulation;const auto& Y=B->Machines[I].Simulation;
            const auto& P=X.GetStats();const auto& Q=Y.GetStats();
            if(P.Spawned!=Q.Spawned||P.Completed!=Q.Completed||P.Collected!=Q.Collected||P.Queued!=Q.Queued||P.Active!=Q.Active
               ||P.ExchangedCarts!=Q.ExchangedCarts||P.Reason!=Q.Reason||!Near(P.SimTime,Q.SimTime)
               ||!Near(P.ChainPhase01,Q.ChainPhase01)||X.IsPlaying()!=Y.IsPlaying())return false;
            if(X.GetInfeedQueue().size()!=Y.GetInfeedQueue().size())return false;
            for(size_t J=0;J<X.GetInfeedQueue().size();++J)
                if(X.GetInfeedQueue()[J].ParcelId!=Y.GetInfeedQueue()[J].ParcelId
                   ||!Near(X.GetInfeedQueue()[J].Progress01,Y.GetInfeedQueue()[J].Progress01))return false;
            for(size_t J=0;J<X.GetCarts().size();++J)
            {
                const auto& U=X.GetCarts()[J];const auto& V=Y.GetCarts()[J];
                if(U.State!=V.State||U.Occupancy!=V.Occupancy||U.Reserved!=V.Reserved||U.Generation!=V.Generation
                   ||U.ParcelIds!=V.ParcelIds||U.LastOutboundParcelIds!=V.LastOutboundParcelIds)return false;
            }
        }
        return true;
    };
    auto* Framed=Spawn();if(!TestNotNull(TEXT("Frame comparison actor spawned"),Framed))return false;
    Framed->LayoutJson=Original;if(!TestTrue(TEXT("Frame comparison layout parsed"),Framed->LoadLayout()))return false;
    Valid->SetSimulationPlaying(true);Framed->SetSimulationPlaying(true);
    bool Advanced=Valid->AdvanceFleet(120);
    for(int32 Frame=0;Frame<7200;++Frame)Advanced&=Framed->AdvanceFleet(1./60.);
    TestTrue(TEXT("large advance and 60 Hz share central IDs, queue ownership, cart states and simulation clocks"),Advanced&&SameFleet(Valid,Framed));
    Valid->AdvanceFleet(.013);Framed->AdvanceFleet(.013);
    Valid->SetSimulationPlaying(false);Framed->SetSimulationPlaying(false);const uint64 BeforeId=Valid->NextCentralParcelId;
    Valid->AdvanceFleet(60);
    TestTrue(TEXT("pausing freezes both banks and all sorters without consuming fractional time or IDs"),SameFleet(Valid,Framed)
        &&Valid->NextCentralParcelId==BeforeId&&FMath::Abs(Valid->FleetTimeRemainder-.013)<1.e-7);
    // bReady remains false: ResetSimulation exercises real core/reset logic but
    // its presentation guard keeps this no-BeginPlay fixture free of instances.
    Valid->ResetSimulation();Framed->ResetSimulation();bool ResetClean=SameFleet(Valid,Framed)
        &&Valid->NextCentralParcelId==1&&Valid->FleetTimeRemainder==0;
    for(const auto& B:Valid->DistributionBanks)ResetClean&=!B.Simulation.IsPlaying()&&B.Simulation.GetStats().Generated==0
        &&B.Simulation.GetStats().Active==0&&B.Simulation.GetStats().SimTime==0;
    for(const auto& M:Valid->Machines)ResetClean&=!M.Simulation.IsPlaying()&&M.Simulation.GetStats().Spawned==0
        &&M.Simulation.GetStats().Active==0&&M.Simulation.GetStats().SimTime==0&&M.Simulation.GetRate()==1;
    TestTrue(TEXT("reset synchronously clears central and machine parcels, clocks, IDs and fractional time"),ResetClean);

    Valid->SetSimulationPlaying(true);
    bool SawHandoff=false,SawEmpty=false,SawDock=false,CycleComplete=false,AisleSafe=true,HandoffValid=true;
    bool ManifestPreserved=true;int32 WatchedMachine=INDEX_NONE,WatchedCart=INDEX_NONE;
    uint64 Exchanged=0,OriginalGeneration=0,ExchangesAtHandoff=0;std::vector<uint64_t> Manifest;
    // Central loading supplies the entire 22-machine fleet. Stop at the first
    // observed complete cart cycle; never replay a long run once per machine.
    for(int32 Second=0;Second<15000&&!CycleComplete;++Second)
    {
        if(!Valid->AdvanceFleet(1)){Advanced=false;break;}
        int32 ActiveExchanges=0;Exchanged=0;
        for(int32 Machine=0;Machine<Valid->Machines.Num();++Machine)
        {
            const auto& M=Valid->Machines[Machine];Exchanged+=M.Simulation.GetStats().ExchangedCarts;
            for(int32 I=0;I<M.Carts.Num();++I)
            {
                const auto& C=M.Simulation.GetCarts()[size_t(I)];
                ActiveExchanges+=C.State!=MPRSorter::CartPhase::Receiving&&C.State!=MPRSorter::CartPhase::FullWaiting;
                if(C.State!=MPRSorter::CartPhase::Handoff)continue;
                if(!SawHandoff)
                {
                    SawHandoff=true;WatchedMachine=Machine;WatchedCart=I;Manifest=C.ParcelIds;
                    OriginalGeneration=C.Generation;ExchangesAtHandoff=M.Simulation.GetStats().ExchangedCarts;
                }
                const auto& P=M.Carts[I];
                const FVector Expected(-M.InfeedSide*P.OutboundEndX-P.Origin.X,(P.Side==0?1.:-1.)*P.Retreat,0);
                HandoffValid&=Valid->CartOffset(M,I).Equals(Expected,.001)&&C.Occupancy==C.Capacity&&C.Reserved==0
                    &&C.ParcelIds.size()==size_t(C.Occupancy)&&M.Simulation.IsExchangePermitted()&&M.Simulation.GetStats().ChainStopped;
            }
        }
        AisleSafe&=ActiveExchanges<=1;
        if(SawHandoff)
        {
            const auto& M=Valid->Machines[WatchedMachine];const auto& C=M.Simulation.GetCarts()[size_t(WatchedCart)];
            if(C.State==MPRSorter::CartPhase::Handoff)ManifestPreserved&=C.ParcelIds==Manifest&&C.Generation==OriginalGeneration;
            if(C.State==MPRSorter::CartPhase::EmptyArriving||C.State==MPRSorter::CartPhase::Docking)
            {
                SawEmpty|=C.State==MPRSorter::CartPhase::EmptyArriving;SawDock|=C.State==MPRSorter::CartPhase::Docking;
                ManifestPreserved&=C.Occupancy==0&&C.ParcelIds.empty()&&C.LastOutboundParcelIds==Manifest&&C.Generation==OriginalGeneration+1;
            }
            CycleComplete=M.Simulation.GetStats().ExchangedCarts>ExchangesAtHandoff&&C.State==MPRSorter::CartPhase::Receiving;
            if(CycleComplete)ManifestPreserved&=C.LastOutboundParcelIds==Manifest&&C.Generation==OriginalGeneration+1;
        }
    }
    TestTrue(TEXT("shared aisle admits at most one moving cart throughout the first cycle"),Advanced&&AisleSafe);
    TestTrue(TEXT("central-fed fleet eventually exchanges a full cart within the bounded sample"),Exchanged>0&&CycleComplete);
    TestTrue(TEXT("handoff keeps the complete old load at the aisle exit until ownership transfers"),SawHandoff&&HandoffValid&&ManifestPreserved);
    TestTrue(TEXT("a distinct empty cart arrives and docks before the machine resumes"),SawEmpty&&SawDock&&CycleComplete);
    return true;
}
#endif
