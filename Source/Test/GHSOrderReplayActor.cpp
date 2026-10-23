#include "GHSOrderReplayActor.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/DecalComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

namespace
{
FVector V(const GHSReplay::Vec& P){return FVector(P.X,P.Y,P.Z);}
FString S(const std::string& Text){return UTF8_TO_TCHAR(Text.c_str());}
std::string N(const FString& Text){return TCHAR_TO_UTF8(*Text);}
FString Write(const TSharedRef<FJsonObject>& Json){FString Text;FJsonSerializer::Serialize(Json,TJsonWriterFactory<>::Create(&Text));return Text;}
GHSReplay::Vec ReadVec(const TArray<TSharedPtr<FJsonValue>>& Row){return {Row[0]->AsNumber(),Row[1]->AsNumber(),Row[2]->AsNumber()};}
TArray<TSharedPtr<FJsonValue>> JsonVec(const FVector& P){return {MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)};}
}

AGHSOrderReplayActor::AGHSOrderReplayActor()
{
    PrimaryActorTick.bCanEverTick=false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("ReplayRoot")));
    SetActorEnableCollision(false);
}

UStaticMeshComponent* AGHSOrderReplayActor::AddMesh(const FString& Name,const FString& Path)
{
    UStaticMesh* Mesh=LoadObject<UStaticMesh>(nullptr,*Path);
    if(!Mesh){Error=TEXT("回放模型尚未就绪：")+Path;return nullptr;}
    auto* C=NewObject<UStaticMeshComponent>(this,*Name);AddInstanceComponent(C);C->SetupAttachment(RootComponent);
    C->SetMobility(EComponentMobility::Movable);C->SetStaticMesh(Mesh);C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    C->SetGenerateOverlapEvents(false);C->SetCanEverAffectNavigation(false);C->bAffectDistanceFieldLighting=false;C->SetCastShadow(true);
    C->SetReceivesDecals(false);
    C->RegisterComponent();return C;
}

bool AGHSOrderReplayActor::LoadData()
{
    FString Text;
    if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/order-replay.json")))){Error=TEXT("回放测试数据缺失");return false;}
    TSharedPtr<FJsonObject> Json;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Json)||!Json){Error=TEXT("回放测试数据格式错误");return false;}
    const TArray<TSharedPtr<FJsonValue>>* Tracks=nullptr;
    if(!Json->TryGetNumberField(TEXT("cycleDuration"),Simulation.CycleDuration)||!Json->TryGetArrayField(TEXT("tracks"),Tracks)||Tracks->Num()!=GHSReplay::EntityCount){Error=TEXT("回放设备数据不完整");return false;}
    for(int32 I=0;I<Tracks->Num();++I)
    {
        const auto R=(*Tracks)[I]->AsObject();if(!R)return false;
        auto& T=Simulation.Tracks[I];T.Id=N(R->GetStringField(TEXT("id")));T.Name=N(R->GetStringField(TEXT("name")));T.Kind=N(R->GetStringField(TEXT("kind")));T.Mesh=N(R->GetStringField(TEXT("mesh")));
        T.Scale=ReadVec(R->GetArrayField(TEXT("scale")));
        const auto& Keys=R->GetArrayField(TEXT("keys"));
        for(const auto& Value:Keys)
        {
            const auto& K=Value->AsArray();if(K.Num()!=10){Error=TEXT("回放关键帧格式错误");return false;}
            GHSReplay::Key Key;Key.Time=K[0]->AsNumber();Key.Position=ReadVec(K[1]->AsArray());Key.Yaw=K[2]->AsNumber();Key.Lift=K[3]->AsNumber();Key.Door=K[4]->AsNumber();Key.Visible=K[5]->AsBool();Key.Owner=int(K[6]->AsNumber());Key.Status=N(K[7]->AsString());
            // Reserved fields carry task/phase metadata without changing the pose format.
            T.Keys.push_back(std::move(Key));
        }
        const TArray<TSharedPtr<FJsonValue>>* Route=nullptr;
        if(R->TryGetArrayField(TEXT("route"),Route))for(const auto& P:*Route)T.Route.push_back(ReadVec(P->AsArray()));
    }
    const TArray<TSharedPtr<FJsonValue>>* Events=nullptr;
    if(Json->TryGetArrayField(TEXT("events"),Events))for(const auto& Value:*Events)
    {
        const auto E=Value->AsObject();Simulation.Events.push_back({E->GetNumberField(TEXT("time")),N(E->GetStringField(TEXT("id"))),N(E->GetStringField(TEXT("deviceId"))),N(E->GetStringField(TEXT("kind"))),N(E->GetStringField(TEXT("text")))});
    }
    std::string Problem;if(!Simulation.Validate(Problem)){Error=S(Problem);return false;}
    const auto& Sources=Json->GetArrayField(TEXT("sourceInstances"));FJsonSerializer::Serialize(Sources,TJsonWriterFactory<>::Create(&SourceInstancesJson));
    const auto& Doors=Json->GetArrayField(TEXT("doors"));
    for(int32 I=0;I<Doors.Num();++I)
    {
        const auto D=Doors[I]->AsObject();auto* C=AddMesh(FString::Printf(TEXT("OpenDockDoor%d"),I),TEXT("/Game/GHSOrderReplay/Meshes/SM_Replay_DockDoorOpen"));if(!C)return false;
        C->SetWorldTransform(FTransform(FRotator(0,D->GetNumberField(TEXT("yaw")),0),V(ReadVec(D->GetArrayField(TEXT("position"))))));Fixtures.Add(C);
    }
    return true;
}

bool AGHSOrderReplayActor::InitializeReplay()
{
    if(bReady)return true;
    if(!LoadData())return false;
    for(int I=0;I<GHSReplay::EntityCount;++I)
    {
        auto* Body=AddMesh(TEXT("Body_")+S(Simulation.Tracks[I].Id),S(Simulation.Tracks[I].Mesh));if(!Body)return false;Bodies.Add(Body);
        if(I>=GHSReplay::DeviceCount)Body->SetForcedLodModel(1);
        if(I<GHSReplay::ForkCount)
        {
            auto* Fork=AddMesh(FString::Printf(TEXT("Carriage%d"),I),TEXT("/Game/GHSOrderReplay/Meshes/SM_Replay_ForkliftCarriage"));
            auto* Mast=AddMesh(FString::Printf(TEXT("Mast%d"),I),TEXT("/Game/GHSOrderReplay/Meshes/SM_Replay_ForkliftMast"));
            if(!Fork||!Mast)return false;Carriages.Add(Fork);Masts.Add(Mast);
        }
        if(I>=GHSReplay::ForkCount&&I<GHSReplay::DeviceCount)
        {
            auto* L=AddMesh(FString::Printf(TEXT("TruckDoorL%d"),I),TEXT("/Game/GHSOrderReplay/Meshes/SM_Replay_TruckDoorLeft"));
            auto* R=AddMesh(FString::Printf(TEXT("TruckDoorR%d"),I),TEXT("/Game/GHSOrderReplay/Meshes/SM_Replay_TruckDoorRight"));
            if(!L||!R)return false;DoorLeft.Add(L);DoorRight.Add(R);
        }
    }
    UStaticMesh* Plane=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Plane.Plane"));
    auto* Material=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/GHSOrderReplay/Materials/M_ReplayTrail"));
    auto* RippleMaterial=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/GHSOrderReplay/Materials/M_ReplayGroundRipple"));
    if(!Plane||!Material||!RippleMaterial){Error=TEXT("回放轨迹材质尚未就绪");return false;}
    for(int I=0;I<GHSReplay::ForkCount;++I)
    {
        auto* Trail=NewObject<UInstancedStaticMeshComponent>(this,*FString::Printf(TEXT("Trail%d"),I));AddInstanceComponent(Trail);Trail->SetupAttachment(RootComponent);Trail->SetStaticMesh(Plane);Trail->SetMobility(EComponentMobility::Movable);Trail->SetCollisionEnabled(ECollisionEnabled::NoCollision);Trail->SetCastShadow(false);Trail->SetCanEverAffectNavigation(false);Trail->SetGenerateOverlapEvents(false);
        // Metres along the whole route, not one repeating UV cycle per short chord.
        Trail->SetNumCustomDataFloats(6);
        const auto Tint=FLinearColor::FromSRGBColor(FColor::FromHex(UTF8_TO_TCHAR(GHSReplay::TrailColor(I))));
        auto* MID=UMaterialInstanceDynamic::Create(Material,this);MID->SetVectorParameterValue(TEXT("Tint"),Tint);
        Trail->SetMaterial(0,MID);Trail->RegisterComponent();Trails.Add(Trail);TrailMaterials.Add(MID);
        const auto Segments=GHSReplay::BuildTrailSegments(Simulation.Tracks[I]);
        for(const auto& Segment:Segments)
        {
            FVector A=V(Segment.A),B=V(Segment.B);A.Z+=3;B.Z+=3;const FVector Delta=B-A;
            const double LengthMeters=Segment.LengthMeters;
            // Exact adjoining lengths avoid dark/bright stripes from alpha overlap.
            FTransform Transform(FRotator(0,Delta.Rotation().Yaw,0),(A+B)*.5,FVector(LengthMeters,GHSReplay::TrailWidthCm/100.,1));
            const int32 Instance=Trail->AddInstance(Transform);
            Trail->SetCustomDataValue(Instance,0,float(Segment.StartMeters),false);
            Trail->SetCustomDataValue(Instance,1,float(Segment.FlowDeltaMeters),false);
            Trail->SetCustomDataValue(Instance,2,float(Segment.StartShearCm),false);
            Trail->SetCustomDataValue(Instance,3,float(Segment.EndShearCm),false);
            Trail->SetCustomDataValue(Instance,4,float(Segment.StartHalfWidthCm),false);
            Trail->SetCustomDataValue(Instance,5,float(Segment.EndHalfWidthCm),false);
        }
        Trail->MarkRenderStateDirty();
        auto* Ripple=NewObject<UDecalComponent>(this,*FString::Printf(TEXT("GroundRipple%d"),I));
        AddInstanceComponent(Ripple);Ripple->SetupAttachment(RootComponent);Ripple->SetMobility(EComponentMobility::Movable);
        Ripple->DecalSize=FVector(3.,165.,165.);Ripple->SetFadeScreenSize(0);Ripple->SetSortOrder(30);
        auto* RippleMID=UMaterialInstanceDynamic::Create(RippleMaterial,this);
        RippleMID->SetVectorParameterValue(TEXT("Tint"),Tint);RippleMID->SetScalarParameterValue(TEXT("Phase"),I*.173f);
        Ripple->SetDecalMaterial(RippleMID);Ripple->RegisterComponent();GroundRipples.Add(Ripple);RippleMaterials.Add(RippleMID);
    }
    bReady=true;EvaluateAt(0);SetTrailMode(TrailMode,SelectedId);return true;
}

void AGHSOrderReplayActor::EvaluateAt(double Time)
{
    if(!bReady)return;CurrentTime=FMath::Max(0.,FMath::IsFinite(Time)?Time:0.);Simulation.Evaluate(CurrentTime);
    for(int I=0;I<GHSReplay::EntityCount;++I)
    {
        const auto& P=Simulation.Poses[I];const FTransform Transform(FRotator(0,P.Yaw,0),V(P.Position),V(Simulation.Tracks[I].Scale));
        Bodies[I]->SetWorldTransform(Transform,false,nullptr,ETeleportType::TeleportPhysics);Bodies[I]->SetVisibility(P.Visible);
        if(I<GHSReplay::ForkCount)
        {
            auto Fork=Transform;Fork.AddToTranslation(FVector(0,0,P.Lift));Carriages[I]->SetWorldTransform(Fork);Carriages[I]->SetVisibility(P.Visible);
            auto Mast=Transform;Mast.AddToTranslation(FVector(0,0,FMath::Max(0.,P.Lift-70.)*.5));Masts[I]->SetWorldTransform(Mast);Masts[I]->SetVisibility(P.Visible);
            GroundRipples[I]->SetWorldLocationAndRotation(FVector(P.Position.X,P.Position.Y,1.5),FRotator(-90,P.Yaw,0));
            GroundRipples[I]->SetVisibility(P.Visible&&TrailMode!=TEXT("off")&&(TrailMode!=TEXT("selected")||SelectedId==S(Simulation.Tracks[I].Id)));
        }
        if(I>=GHSReplay::ForkCount&&I<GHSReplay::DeviceCount)
        {
            const int T=I-GHSReplay::ForkCount;
            // Hinges remain at the two rear jambs; the rear panels swing outwards.
            const FTransform Left(FRotator(0,100.*P.Door,0),FVector(0,-122,0));
            const FTransform Right(FRotator(0,-100.*P.Door,0),FVector(0,122,0));
            DoorLeft[T]->SetWorldTransform(Left*Transform);DoorRight[T]->SetWorldTransform(Right*Transform);DoorLeft[T]->SetVisibility(P.Visible);DoorRight[T]->SetVisibility(P.Visible);
        }
    }
    for(UMaterialInstanceDynamic* Material:TrailMaterials)if(Material)Material->SetScalarParameterValue(TEXT("ReplayTime"),float(FMath::Fmod(CurrentTime,10000.)));
    for(UMaterialInstanceDynamic* Material:RippleMaterials)if(Material)Material->SetScalarParameterValue(TEXT("ReplayTime"),float(FMath::Fmod(CurrentTime,10000.)));
}

void AGHSOrderReplayActor::SetTrailMode(const FString& Mode,const FString& Id)
{
    TrailMode=Mode==TEXT("selected")||Mode==TEXT("off")?Mode:TEXT("all");SelectedId=Id;UpdateTrails();
}
void AGHSOrderReplayActor::UpdateTrails()
{
    for(int32 I=0;I<Trails.Num();++I)
    {
        const bool Visible=TrailMode==TEXT("all")||(TrailMode==TEXT("selected")&&S(Simulation.Tracks[I].Id)==SelectedId);
        Trails[I]->SetVisibility(Visible);
        GroundRipples[I]->SetVisibility(Visible&&Simulation.Poses[I].Visible);
    }
}
FString AGHSOrderReplayActor::GetSourceInstancesJson() const {return SourceInstancesJson;}
bool AGHSOrderReplayActor::ResolveDevice(const FString& Id,FVector& Location,FRotator& Rotation,FVector& Extent) const
{
    if(!bReady)return false;
    for(int I=0;I<GHSReplay::DeviceCount;++I)if(Id==S(Simulation.Tracks[I].Id)&&Simulation.Poses[I].Visible)
    {const auto B=Bodies[I]->Bounds;Location=B.Origin;Rotation=FRotator(0,Simulation.Poses[I].Yaw,0);Extent=B.BoxExtent;return true;}
    return false;
}
bool AGHSOrderReplayActor::PickRay(const FVector& Origin,const FVector& Direction,FString& Id) const
{
    if(!bReady)return false;double Nearest=TNumericLimits<double>::Max();
    for(int I=0;I<GHSReplay::DeviceCount;++I)
    {
        if(!Simulation.Poses[I].Visible)continue;const FTransform T(FRotator(0,Simulation.Poses[I].Yaw,0),V(Simulation.Poses[I].Position));
        const FVector O=T.InverseTransformPosition(Origin),D=T.InverseTransformVectorNoScale(Direction.GetSafeNormal());
        const FBox Box=I<5?FBox(FVector(-140,-80,0),FVector(235,80,270)):FBox(FVector(-25,-160,0),FVector(1480,160,385));
        double Enter=0,Exit=1.e9;bool Hit=true;
        for(int Axis=0;Axis<3;++Axis)
        {
            if(FMath::Abs(D[Axis])<1.e-9){if(O[Axis]<Box.Min[Axis]||O[Axis]>Box.Max[Axis])Hit=false;continue;}
            double A=(Box.Min[Axis]-O[Axis])/D[Axis],B=(Box.Max[Axis]-O[Axis])/D[Axis];if(A>B)Swap(A,B);Enter=FMath::Max(Enter,A);Exit=FMath::Min(Exit,B);
        }
        if(Hit&&Enter<=Exit&&Exit>=0&&Enter<Nearest){Nearest=Enter;Id=S(Simulation.Tracks[I].Id);}
    }
    return Nearest<TNumericLimits<double>::Max();
}
FString AGHSOrderReplayActor::GetEventsJson(double Start,double End,int32 Limit) const
{
    TArray<TSharedPtr<FJsonValue>> Rows;
    for(const auto& O:Simulation.EventsIn(Start,End,Limit))
    {
        auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("id"),S(O.Source->Id)+FString::Printf(TEXT("-%lld"),O.Cycle));R->SetStringField(TEXT("deviceId"),S(O.Source->DeviceId));R->SetStringField(TEXT("kind"),S(O.Source->Kind));R->SetStringField(TEXT("type"),S(O.Source->Kind));R->SetStringField(TEXT("text"),S(O.Source->Text));R->SetStringField(TEXT("title"),S(O.Source->Text));R->SetNumberField(TEXT("time"),O.Time);Rows.Add(MakeShared<FJsonValueObject>(R));
    }
    FString Text;FJsonSerializer::Serialize(Rows,TJsonWriterFactory<>::Create(&Text));return Text;
}
FString AGHSOrderReplayActor::GetSnapshotJson() const
{
    auto Json=MakeShared<FJsonObject>();Json->SetBoolField(TEXT("ready"),bReady);Json->SetNumberField(TEXT("time"),CurrentTime);Json->SetNumberField(TEXT("cycleDuration"),Simulation.CycleDuration);Json->SetNumberField(TEXT("fixedEntities"),GHSReplay::EntityCount);Json->SetStringField(TEXT("error"),Error);
    Json->SetNumberField(TEXT("trailComponents"),Trails.Num());Json->SetNumberField(TEXT("rippleComponents"),GroundRipples.Num());
    TArray<TSharedPtr<FJsonValue>> Devices;
    for(int I=0;I<GHSReplay::DeviceCount;++I)
    {
        const auto& T=Simulation.Tracks[I];const auto& P=Simulation.Poses[I];auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("id"),S(T.Id));R->SetStringField(TEXT("name"),S(T.Name));R->SetStringField(TEXT("title"),S(T.Name));R->SetStringField(TEXT("kind"),S(T.Kind));R->SetStringField(TEXT("type"),I<5?TEXT("forklift"):TEXT("truck"));R->SetStringField(TEXT("trailColor"),UTF8_TO_TCHAR(GHSReplay::TrailColor(I)));R->SetStringField(TEXT("status"),P.Status?S(*P.Status):TEXT("准备中"));R->SetStringField(TEXT("state"),P.Status?S(*P.Status):TEXT("准备中"));R->SetBoolField(TEXT("visible"),P.Visible);R->SetArrayField(TEXT("position"),JsonVec(V(P.Position)));R->SetNumberField(TEXT("yaw"),P.Yaw);R->SetNumberField(TEXT("lift"),P.Lift);int Load=0;for(int C=8;C<18;++C)if(Simulation.Poses[C].Owner==I)++Load;R->SetNumberField(TEXT("cargoCount"),Load);R->SetNumberField(TEXT("load"),Load);R->SetBoolField(TEXT("loaded"),Load>0);R->SetNumberField(TEXT("capacity"),I<5?1:(I==6?2:4));R->SetNumberField(TEXT("trip"),Simulation.CycleDuration>0?FMath::FloorToDouble(CurrentTime/Simulation.CycleDuration)+1:1);Devices.Add(MakeShared<FJsonValueObject>(R));
    }
    Json->SetArrayField(TEXT("devices"),Devices);return Write(Json);
}
