#include "MPRSorterSimulationActor.h"
#include "MPRCentralCadData.h"
#include "MPRCadWorkerData.h"
#include "MPRWorkerPoseComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"

namespace
{
constexpr double FeedSurface=103.5,TravelSurface=180.,ParcelHalf=2.8;
FVector Vec(const double* P){return FVector(P[0],P[1],P[2]);}
double Ease(double T){T=FMath::Clamp(T,0.,1.);return T*T*(3.-2.*T);}
double StationDistance(const MPRCentralGeometry::Bank& B,double Y,bool Right)
{
    const double H=B.HalfStraightCm,R=B.RadiusCm,L=4*H+2*PI*R;
    const double Along=FMath::Clamp(Y-B.Center.Y,-H,H);
    return (Right?Along+H:2*H+PI*R+H-Along)/L;
}
TArray<TSharedPtr<FJsonValue>> XYZ(const FVector& P)
{return {MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)};}
}

bool AMPRSorterSimulationActor::LoadCentralDistribution()
{
    DistributionBanks.Reset();NextCentralParcelId=1;FleetTimeRemainder=0;
    for(int32 BankIndex=0;BankIndex<2;++BankIndex)
    {
        FDistributionBank B;B.Id=BankIndex==0?TEXT("CAD64_Central"):TEXT("CAD120_Central");
        B.Profile=BankIndex==0?TEXT("cad64"):TEXT("cad120");
        B.Geometry.Center=Vec(BankIndex==0?MPRCentralCad::Center64:MPRCentralCad::Center120);
        B.Geometry.HalfStraightCm=BankIndex==0?MPRCentralCad::Half64:MPRCentralCad::Half120;
        B.Geometry.RadiusCm=BankIndex==0?MPRCentralCad::Radius64:MPRCentralCad::Radius120;
        MPRCentral::Config C;C.LoopLengthCm=4*B.Geometry.HalfStraightCm+2*PI*B.Geometry.RadiusCm;
        // Continuous circulation; hand actions and side transfers occur while
        // the shared chain moves. These are presentation timings, not PLC data.
        C.CarrierCount=BankIndex==0?96:24;C.SpeedCmS=90;C.LoadingSeconds=.9;
        C.TransferSeconds=.3;C.RecoverySeconds=.3;C.MaxPendingPerTarget=8;
        int32 SourceIndex=0;
        const char* FeedHandles[]={"2CCF63","2CCF64","2CCF65","2CCF69","2CCF67","2CCF68"};
        if(BankIndex==0)for(const auto& Source:MPRCentralCad::Workers)
        {
            FFeedStation S;S.Feet=Vec(Source.Feet);S.Yaw=Source.Yaw;
            const FVector Forward=FRotator(0,S.Yaw,0).Vector();
            // Personnel XY is surveyed. Reach/table geometry is a conservative
            // display fit; people never reach across the 1.5 m distributor gap.
            S.Drop=S.Feet+Forward*50.;S.Drop.Y=FMath::Lerp(S.Feet.Y,Source.Table[1],.4);S.Drop.Z=FeedSurface;
            // The workstation port stays fixed. Standing roots follow the
            // source torso projection, not the bounds of outstretched arms.
            for(const auto& Person:MPRCadWorkers::Workers)
                if(FCStringAnsi::Strcmp(Person.SourceHandle,FeedHandles[SourceIndex])==0)
                {S.Feet=Vec(Person.Feet);S.Yaw=Person.Yaw;break;}
            ++SourceIndex;
            S.Distance01=StationDistance(B.Geometry,S.Drop.Y,S.Feet.X>B.Geometry.Center.X);
            B.Stations.Add(S);C.FeedDistances01.push_back(S.Distance01);
        }
        else
        {
            // No people are drawn in this CAD block. Model an external belt
            // source at its end; do not invent four additional manual stations.
            FFeedStation S;S.bManual=false;S.Yaw=180;
            S.Drop=B.Geometry.Center+FVector(B.Geometry.RadiusCm+140,-B.Geometry.HalfStraightCm+55,FeedSurface);
            S.Feet=S.Drop+FVector(50,0,-FeedSurface);
            S.Distance01=StationDistance(B.Geometry,S.Drop.Y,true);
            B.Stations.Add(S);C.FeedDistances01.push_back(S.Distance01);
        }
        for(const auto& S:B.Stations)
        {
            double Heading;FVector Rail=MPRCentralGeometry::CentralPoint(B.Geometry,S.Distance01,Heading);Rail.Z=FeedSurface;
            MPRCentralGeometry::Belt Belt;Belt.Start=S.Drop;Belt.End=Rail;Belt.WidthCm=42;B.Belts.Add(Belt);
        }
        for(int32 Index=0;Index<Machines.Num();++Index)
        {
            auto& M=Machines[Index];if(M.Profile!=B.Profile)continue;
            double Heading;const FVector LoadLocal=PointOnLoop(M.LoadFraction,M.Half,M.Radius,Heading)+FVector(0,0,M.Simulation.GetConfig().LoadHeightCm);
            const FVector Load=M.World.TransformPosition(LoadLocal);
            const bool Right=Load.X>B.Geometry.Center.X;
            const double Distance=StationDistance(B.Geometry,Load.Y,Right);
            FVector Track=MPRCentralGeometry::CentralPoint(B.Geometry,Distance,Heading);Track.Z=Load.Z;
            const FVector Out=(Load-Track).GetSafeNormal();
            const FVector Handoff=Track+Out*29.;
            M.FeedStart=M.World.InverseTransformPosition(Handoff);
            M.Pickup=M.World.InverseTransformPosition(Load-Out*20.);
            M.Entry=LoadLocal;
            B.Targets.Add(Index);C.TargetDistances01.push_back(Distance);
            MPRCentralGeometry::Belt Belt;Belt.Start=Track+Out*20.;Belt.End=Load;Belt.WidthCm=BankIndex==0?50.:44.;B.Belts.Add(Belt);
        }
        std::string Message;
        if(B.Targets.Num()!=(BankIndex==0?18:4)||!B.Simulation.Initialize(C,Message))
        {Error=TEXT("中央分配装置与 CAD 机组不匹配: ")+FString(UTF8_TO_TCHAR(Message.c_str()));return false;}
        DistributionBanks.Add(MoveTemp(B));
    }
    return true;
}

void AMPRSorterSimulationActor::BuildCentralDistribution()
{
    for(auto* C:{CentralMetal.Get(),CentralWhite.Get(),CentralBlue.Get(),CentralBelt.Get(),CentralColumns.Get(),CentralTrays.Get(),CentralParcels.Get()})C->ClearInstances();
    auto Material=[this](const FString& SlotRole)->UMaterialInterface*
    {
        for(const auto& Slot:TowerMesh->GetStaticMaterials())if(Slot.MaterialSlotName.ToString().Contains(SlotRole))return Slot.MaterialInterface;
        for(const auto& Mesh:CartMeshes)if(Mesh)for(const auto& Slot:Mesh->GetStaticMaterials())
            if(Slot.MaterialSlotName.ToString().Contains(SlotRole))return Slot.MaterialInterface;
        return WorkerHelmetMaterial;
    };
    CentralMetal->SetMaterial(0,Material(TEXT("Metal")));CentralWhite->SetMaterial(0,Material(TEXT("Porcelain")));
    CentralBlue->SetMaterial(0,Material(TEXT("Cobalt")));CentralBelt->SetMaterial(0,Material(TEXT("Charcoal")));
    CentralColumns->SetStaticMesh(TowerMesh);CentralTrays->SetStaticMesh(TrayMesh);CentralParcels->SetMaterial(0,ParcelMaterial);
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    for(auto& B:DistributionBanks)
    {
        TArray<MPRCentralGeometry::Feed> Stations;
        for(const auto& S:B.Stations)if(S.bManual)
        {MPRCentralGeometry::Feed F;F.OperatorFeet=S.Feet;F.YawDegrees=S.Yaw;F.Drop=S.Drop;Stations.Add(F);}
        MPRCentralGeometry::Build(B.Geometry,B.Belts,Stations,CentralMetal,CentralWhite,CentralBlue,CentralBelt);
        B.CarrierOffset=CentralColumns->GetInstanceCount();
        for(int I=0;I<B.Simulation.GetConfig().CarrierCount;++I)
        {CentralColumns->AddInstance(Hidden);CentralTrays->AddInstance(Hidden);CentralParcels->AddInstance(Hidden);}
    }
}

void AMPRSorterSimulationActor::SuppressLegacySpines()
{
    // Only the 24 source-matched obsolete instances in the game world. The
    // editor map, other HISM instances and saved assets remain untouched.
    SuppressedSpineInstances=0;
    if(!GetWorld()||!GetWorld()->IsGameWorld())return;
    for(TActorIterator<AActor> It(GetWorld());It;++It)
    {
        TArray<UInstancedStaticMeshComponent*> Components;It->GetComponents(Components);
        for(auto* C:Components)
        {
            if(!C->GetStaticMesh()||C->GetStaticMesh()->GetName()!=TEXT("SM_MPR_Conveyor2m"))continue;
            for(int32 I=0;I<C->GetInstanceCount();++I)
            {
                FTransform T;if(!C->GetInstanceTransform(I,T,true))continue;const FVector P=T.GetLocation();bool Match=false;
                if(FMath::Abs(P.X+10430.)<.1)for(int32 K=0;K<19;++K)Match|=FMath::Abs(P.Y-(3010.301-190.*K))<.1;
                if(FMath::Abs(P.X+11152.)<.1)for(int32 K=0;K<5;++K)Match|=FMath::Abs(P.Y-(-1312.737-162.*K))<.1;
                if(Match&&T.GetScale3D().GetAbsMax()>0)
                {T.SetScale3D(FVector::ZeroVector);C->UpdateInstanceTransform(I,T,true,false,true);++SuppressedSpineInstances;}
            }
            C->MarkRenderStateDirty();
        }
    }
}

bool AMPRSorterSimulationActor::AdvanceCentralDistribution(double Seconds)
{
    for(auto& B:DistributionBanks)
    {
        B.Simulation.SetPlaying(Machines[0].Simulation.IsPlaying());
        auto CanAccept=[&](int I){return Machines[B.Targets[I]].Simulation.CanAcceptExternalParcel();};
        auto Accept=[&](int I,uint64_t Id){return Machines[B.Targets[I]].Simulation.EnqueueExternalParcel(Id);};
        if(!B.Simulation.Advance(Seconds,NextCentralParcelId,CanAccept,Accept))return false;
    }
    return true;
}

void AMPRSorterSimulationActor::SetCentralFeedingEnabled(bool bEnabled)
{
    for(auto& B:DistributionBanks)B.Simulation.SetFeedingEnabled(bEnabled);
}

double AMPRSorterSimulationActor::CentralLiftHeight(const MPRCentral::Carrier& C) const
{
    using P=MPRCentral::CarrierPhase;
    if(C.Phase==P::Loading)
    {
        if(C.Progress01<.18)return FMath::Lerp(TravelSurface,FeedSurface,Ease(C.Progress01/.18));
        return FMath::Lerp(FeedSurface,TravelSurface,Ease((C.Progress01-.8)/.2));
    }
    if(C.Phase==P::Recovering)return FMath::Lerp(FeedSurface,TravelSurface,Ease(C.Progress01));
    if(C.Phase==P::Discharging)return FMath::Lerp(TravelSurface,FeedSurface,Ease(C.Progress01/.4));
    if(C.Phase==P::Retracting)return FMath::Lerp(TravelSurface,FeedSurface,Ease((1.-C.Progress01)/.4));
    // Empty columns return at transport height, then lower before the next load.
    return TravelSurface;
}

FVector AMPRSorterSimulationActor::CentralParcelPoint(const FDistributionBank& B,const MPRCentral::Carrier& C) const
{
    using P=MPRCentral::CarrierPhase;
    double Heading;FVector Tray=MPRCentralGeometry::CentralPoint(B.Geometry,C.Distance01,Heading);Tray.Z=CentralLiftHeight(C)+ParcelHalf;
    if(C.Phase==P::Loading&&B.Stations.IsValidIndex(C.SourceStation))
    {
        const auto& S=B.Stations[C.SourceStation];const FVector Forward=FRotator(0,S.Yaw,0).Vector();
        // The person releases on the near workstation surface; the powered
        // belt covers the remaining reach to the fixed central handoff port.
        const FVector Drop=S.Drop-Forward*20.+FVector(0,0,ParcelHalf),Supply=Drop-Forward*20.;const double T=C.Progress01;
        // A visible arrival traverses the existing short workstation belt
        // before the worker grips it. Do not restore the user's deleted ramps.
        const FVector Side=FRotator(0,S.Yaw,0).RotateVector(FVector(0,1,0));
        if(T<.18)return FMath::Lerp(Supply-Side*20.,Supply,T/.18);
        if(T<.25)return Supply;
        if(T<.5)return FMath::Lerp(Supply,Drop,Ease((T-.25)/.25))+FVector(0,0,5*FMath::Sin(PI*(T-.25)/.25));
        if(T<.8){Tray.Z=FeedSurface+ParcelHalf;return FMath::Lerp(Drop,Tray,(T-.5)/.3);}
        return Tray;
    }
    if((C.Phase==P::Discharging||C.Phase==P::Retracting)&&B.Targets.IsValidIndex(C.TargetIndex))
    {
        const auto& M=Machines[B.Targets[C.TargetIndex]];
        const double T=C.Phase==P::Retracting?1.-C.Progress01:C.Progress01;
        if(T>.4)return FMath::Lerp(Tray,M.World.TransformPosition(FeedPoint(M,0)),(T-.4)/.6);
    }
    return Tray;
}

void AMPRSorterSimulationActor::UpdateCentralDistribution()
{
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    for(auto& B:DistributionBanks)
    {
        int32 I=B.CarrierOffset;
        std::vector<MPRCentral::Carrier> DisplayCarriers;
        DisplayCarriers.reserve(B.Simulation.GetCarriers().size());
        for(size_t Index=0;Index<B.Simulation.GetCarriers().size();++Index)
            DisplayCarriers.push_back(B.Simulation.GetPresentationCarrier(Index,FleetTimeRemainder));
        for(const auto& C:DisplayCarriers)
        {
            double Heading;FVector Point=MPRCentralGeometry::CentralPoint(B.Geometry,C.Distance01,Heading);
            const FQuat Turn(FVector::UpVector,Heading);
            CentralColumns->UpdateInstanceTransform(I,FTransform(Turn,Point,FVector(1.6,1.6,B.Geometry.FrameHeightCm/212.)),true,false,true);
            Point.Z=CentralLiftHeight(C);
            CentralTrays->UpdateInstanceTransform(I,FTransform(Turn,Point,FVector(1.6,1.6,1.)),true,false,true);
            CentralParcels->UpdateInstanceTransform(I,C.ParcelId?FTransform(Turn,CentralParcelPoint(B,C),FVector(.22,.16,.05)):Hidden,true,false,true);++I;
        }
        for(int32 SIndex=0;SIndex<B.Stations.Num();++SIndex)
        {
            const auto& S=B.Stations[SIndex];if(!S.bManual||!RuntimeWorkers.IsValidIndex(S.WorkerIndex))continue;
            const FQuat Turn=FRotator(0,S.Yaw,0).Quaternion();
            const FVector RelaxL=S.Feet+Turn.RotateVector(FVector(25,-18,107)),RelaxR=S.Feet+Turn.RotateVector(FVector(25,18,107));
            FMPRWorkerPoseInput Pose;Pose.BodyWorld=FTransform(Turn,S.Feet);Pose.LeftPalmWorld=RelaxL;Pose.RightPalmWorld=RelaxR;
            Pose.SimulationTime=B.Simulation.GetStats().SimTime+FleetTimeRemainder;Pose.TorsoLeanDegrees=3;
            for(const auto& C:DisplayCarriers)
            {
                if(C.Phase!=MPRCentral::CarrierPhase::Loading||C.SourceStation!=SIndex)continue;
                const double T=C.Progress01;const FVector Left=Turn.RotateVector(FVector(0,-1,0));
                FVector Hand=CentralParcelPoint(B,C);
                if(T>.5)Hand=S.Drop-Turn.RotateVector(FVector(20,0,0))+FVector(0,0,ParcelHalf);
                const double Contact=T<.25?Ease(T/.25):1.-Ease((T-.5)/.17);
                Pose.LeftPalmWorld=FMath::Lerp(RelaxL,Hand+Left*11.25,Contact);
                Pose.RightPalmWorld=FMath::Lerp(RelaxR,Hand-Left*11.25,Contact);
                Pose.GripAlpha=Contact;Pose.TorsoLeanDegrees=FMath::Lerp(3.,13.,Contact);break;
            }
            RuntimeWorkers[S.WorkerIndex]->ApplyWorkerPose(Pose);
        }
    }
    for(auto* C:{CentralColumns.Get(),CentralTrays.Get(),CentralParcels.Get()})C->MarkRenderStateDirty();
}

void AMPRSorterSimulationActor::AppendCentralReport(const TSharedPtr<FJsonObject>& Root) const
{
    uint64 Generated=0,Delivered=0;int32 InTransit=0;bool Unique=true;TSet<uint64> Owners;
    auto Own=[&](uint64 Id){if(!Id||Owners.Contains(Id))Unique=false;else Owners.Add(Id);};
    TArray<TSharedPtr<FJsonValue>> Banks;
    for(const auto& B:DistributionBanks)
    {
        const auto& S=B.Simulation.GetStats();Generated+=S.Generated;Delivered+=S.Delivered;InTransit+=S.Active;
        auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("id"),B.Id);Row->SetNumberField(TEXT("sim_time"),S.SimTime);
        Row->SetNumberField(TEXT("visual_time"),S.SimTime+FleetTimeRemainder);
        Row->SetNumberField(TEXT("visual_residual_seconds"),FleetTimeRemainder);
        Row->SetNumberField(TEXT("generated"),double(S.Generated));Row->SetNumberField(TEXT("delivered"),double(S.Delivered));Row->SetNumberField(TEXT("active"),S.Active);
        Row->SetBoolField(TEXT("stopped"),S.LoopStopped);Row->SetNumberField(TEXT("blocked_passes"),double(S.BlockedPasses));
        const auto& Config=B.Simulation.GetConfig();
        Row->SetNumberField(TEXT("loop_length_cm"),Config.LoopLengthCm);
        Row->SetNumberField(TEXT("speed_cm_s"),Config.SpeedCmS);
        Row->SetNumberField(TEXT("loop_phase01"),S.LoopPhase01);
        Row->SetNumberField(TEXT("loading_seconds"),Config.LoadingSeconds);
        Row->SetBoolField(TEXT("feeding_enabled"),B.Simulation.IsFeedingEnabled());
        TArray<TSharedPtr<FJsonValue>> Stations,Carriers,Links;
        int32 SourceIndex=0;
        for(const auto& Station:B.Stations)
        {
            auto Item=MakeShared<FJsonObject>();Item->SetBoolField(TEXT("manual"),Station.bManual);Item->SetArrayField(TEXT("feet_cm"),XYZ(Station.Feet));
            Item->SetNumberField(TEXT("worker_index"),Station.WorkerIndex);Item->SetArrayField(TEXT("drop_cm"),XYZ(Station.Drop));
            Item->SetNumberField(TEXT("yaw_deg"),Station.Yaw);
            Item->SetNumberField(TEXT("fed_count"),double(B.Simulation.GetFeedCounts()[SourceIndex++]));
            Stations.Add(MakeShared<FJsonValueObject>(Item));
        }
        for(int32 I=0;I<B.Targets.Num();++I)
        {
            const auto& M=Machines[B.Targets[I]];auto Item=MakeShared<FJsonObject>();Item->SetStringField(TEXT("machine"),M.Id);
            Item->SetArrayField(TEXT("handoff_cm"),XYZ(M.World.TransformPosition(FeedPoint(M,0))));
            Item->SetArrayField(TEXT("machine_entry_cm"),XYZ(M.World.TransformPosition(M.Entry)));
            Links.Add(MakeShared<FJsonValueObject>(Item));
        }
        for(size_t Index=0;Index<B.Simulation.GetCarriers().size();++Index)
        {
            const auto& C=B.Simulation.GetCarriers()[Index];
            const auto Display=B.Simulation.GetPresentationCarrier(Index,FleetTimeRemainder);
            if(C.ParcelId)Own(C.ParcelId);auto Item=MakeShared<FJsonObject>();double Heading;
            FVector Tray=MPRCentralGeometry::CentralPoint(B.Geometry,Display.Distance01,Heading);Tray.Z=CentralLiftHeight(Display);
            Item->SetNumberField(TEXT("parcel_id"),double(C.ParcelId));Item->SetNumberField(TEXT("state"),int32(C.Phase));Item->SetNumberField(TEXT("progress"),C.Progress01);
            Item->SetNumberField(TEXT("visual_distance01"),Display.Distance01);Item->SetNumberField(TEXT("visual_progress"),Display.Progress01);
            Item->SetNumberField(TEXT("distance01"),C.Distance01);Item->SetNumberField(TEXT("source_station"),C.SourceStation);
            Item->SetNumberField(TEXT("target_machine"),B.Targets.IsValidIndex(C.TargetIndex)?B.Targets[C.TargetIndex]:INDEX_NONE);
            Item->SetArrayField(TEXT("tray_cm"),XYZ(Tray));if(C.ParcelId)Item->SetArrayField(TEXT("parcel_cm"),XYZ(CentralParcelPoint(B,Display)));
            Carriers.Add(MakeShared<FJsonValueObject>(Item));
        }
        Row->SetArrayField(TEXT("stations"),Stations);Row->SetArrayField(TEXT("carriers"),Carriers);Row->SetArrayField(TEXT("connections"),Links);Banks.Add(MakeShared<FJsonValueObject>(Row));
    }
    uint64 Accepted=0;for(const auto& M:Machines)
    {
        Accepted+=M.Simulation.GetStats().Spawned;
        for(const auto& P:M.Simulation.GetInfeedQueue())Own(P.ParcelId);
        for(const auto& C:M.Simulation.GetCarriers())if(C.ParcelId)Own(C.ParcelId);
        for(const auto& B:M.Simulation.GetBins())for(uint64 Id:B.ParcelIds)Own(Id);
    }
    Root->SetArrayField(TEXT("distribution_banks"),Banks);Root->SetNumberField(TEXT("central_generated"),double(Generated));
    Root->SetNumberField(TEXT("central_delivered"),double(Delivered));Root->SetNumberField(TEXT("central_in_transit"),InTransit);
    Root->SetBoolField(TEXT("central_conserved"),Generated==Delivered+InTransit&&Delivered==Accepted);
    Root->SetBoolField(TEXT("global_unique_ownership"),Unique);Root->SetNumberField(TEXT("manual_feed_workers"),6);
    Root->SetNumberField(TEXT("suppressed_obsolete_spine_instances"),SuppressedSpineInstances);
    Root->SetStringField(TEXT("feed_topology"),TEXT("six_cad_operators_to_shared_loop_to_powered_connections_to_sorters"));
}
