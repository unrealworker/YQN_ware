#include "GHSCampusTrafficActor.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/StaticMesh.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformTime.h"
#include "Math/RotationMatrix.h"
#include "UObject/ConstructorHelpers.h"

AGHSCampusTrafficActor::AGHSCampusTrafficActor()
{
    PrimaryActorTick.bCanEverTick=true;
    PrimaryActorTick.TickGroup=TG_PostUpdateWork;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("TrafficRoot")));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Truck(TEXT("/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_ClosedTruck"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sedan(TEXT("/Game/GHSZcoolSmartFactory/Traffic/Meshes/SM_GHSTraffic_Sedan"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> SUV(TEXT("/Game/GHSZcoolSmartFactory/Traffic/Meshes/SM_GHSTraffic_SUV"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> BlueSedan(TEXT("/Game/GHSZcoolSmartFactory/Traffic/Meshes/SM_GHSTraffic_BlueSedan"));
    UStaticMesh* Meshes[]={Truck.Object,Sedan.Object,SUV.Object,BlueSedan.Object};
    for(int32 Kind=0;Kind<4;++Kind)
    {
        auto* Mesh=CreateDefaultSubobject<UInstancedStaticMeshComponent>(*FString::Printf(TEXT("TrafficKind%d"),Kind));
        Mesh->SetupAttachment(RootComponent);
        Mesh->SetMobility(EComponentMobility::Movable);
        Mesh->SetStaticMesh(Meshes[Kind]);
        Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh->SetGenerateOverlapEvents(false);
        Mesh->SetCanEverAffectNavigation(false);
        Mesh->SetCastShadow(true);
        Mesh->bAffectDistanceFieldLighting=false;
        Mesh->bAffectDynamicIndirectLighting=false;
        VehicleMeshes.Add(Mesh);
    }
    SetActorEnableCollision(false);
}

bool AGHSCampusTrafficActor::LoadRoutes()
{
    FString Text;
    if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/campus-traffic-routes.json"))))return false;
    TSharedPtr<FJsonObject> Json;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Json)||!Json)return false;
    const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
    if(!Json->TryGetArrayField(TEXT("routes"),Rows)||Rows->Num()!=6)return false;
    for(const auto& Row:*Rows)
    {
        const TSharedPtr<FJsonObject>* Data=nullptr;
        if(!Row->TryGetObject(Data)||!Data||!Data->IsValid())return false;
        FRoute Route;
        if(!(*Data)->TryGetStringField(TEXT("id"),Route.Id)||!(*Data)->TryGetStringField(TEXT("corridor"),Route.Corridor)
            ||!(*Data)->TryGetNumberField(TEXT("max_speed_cm_s"),Route.MaxSpeed)||Route.MaxSpeed<=0||Route.MaxSpeed>3000)return false;
        const TArray<TSharedPtr<FJsonValue>>* Points=nullptr;
        if(!(*Data)->TryGetArrayField(TEXT("points_cm"),Points)||Points->Num()<2||Points->Num()>2048)return false;
        for(const auto& Value:*Points)
        {
            const TArray<TSharedPtr<FJsonValue>>* XYZ=nullptr;
            if(!Value->TryGetArray(XYZ)||XYZ->Num()!=3)return false;
            double X,Y,Z;
            if(!(*XYZ)[0]->TryGetNumber(X)||!(*XYZ)[1]->TryGetNumber(Y)||!(*XYZ)[2]->TryGetNumber(Z))return false;
            FVector Point(X,Y,Z);
            if(Point.ContainsNaN()||Point.GetAbsMax()>1000000)return false;
            if(Route.Points.Num())
            {
                const double Segment=FVector::Distance(Point,Route.Points.Last());
                if(Segment<.001)return false;
                Route.Length+=Segment;
            }
            Route.Points.Add(Point);Route.Distances.Add(Route.Length);
        }
        if(Route.Length<20000)return false;
        Routes.Add(MoveTemp(Route));
    }
    return Routes.Num()==6;
}

void AGHSCampusTrafficActor::BeginPlay()
{
    Super::BeginPlay();
    bReady=LoadRoutes();
    for(const auto& Mesh:VehicleMeshes)bReady&=Mesh&&Mesh->GetStaticMesh();
    if(!bReady)
    {
        UE_LOG(LogTemp,Error,TEXT("GHS_TRAFFIC: Missing/invalid traffic route data or meshes; disabled."));
        SetActorTickEnabled(false);return;
    }
    std::vector<GHSTraffic::Route> Config;
    for(const auto& Route:Routes)Config.push_back({Route.Length,Route.MaxSpeed});
    Simulation.Initialize(std::move(Config),FPlatformTime::Cycles());
    for(const auto& Mesh:VehicleMeshes)
    {
        const FBoxSphereBounds Bounds=Mesh->GetStaticMesh()->GetBounds();
        MeshOffsets.Add(FVector(Bounds.Origin.X,Bounds.Origin.Y,Bounds.Origin.Z-Bounds.BoxExtent.Z));
        for(int32 Slot=0;Slot<GHSTraffic::Capacity/4;++Slot)
            Mesh->AddInstance(FTransform(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector));
    }
    UpdateInstances();
    UE_LOG(LogTemp,Display,TEXT("GHS_TRAFFIC: Four corridors, six directions; capacity=%d, fixed ISMs=4, no collision."),GHSTraffic::Capacity);
}

FVector AGHSCampusTrafficActor::FRoute::At(double Distance) const
{
    Distance=FMath::Clamp(Distance,0.,Length);
    int32 Low=0,High=Distances.Num()-1;
    while(Low+1<High)
    {
        const int32 Mid=(Low+High)/2;
        if(Distances[Mid]<=Distance)Low=Mid;else High=Mid;
    }
    const double Alpha=(Distance-Distances[Low])/(Distances[High]-Distances[Low]);
    return FMath::Lerp(Points[Low],Points[High],Alpha);
}

void AGHSCampusTrafficActor::UpdateInstances()
{
    TArray<FTransform,TInlineAllocator<4>> Poses[4];
    for(const auto& Vehicle:Simulation.Vehicles)
    {
        const auto& Route=Routes[Vehicle.Route];
        FVector Position=Route.At(Vehicle.Distance);
        const FVector Direction=(Route.At(Vehicle.Distance+130)-Route.At(Vehicle.Distance-130)).GetSafeNormal();
        const FQuat Rotation=FRotationMatrix::MakeFromXZ(Direction,FVector::UpVector).ToQuat();
        // Existing truck has a rear-door origin. Centre every asset on the
        // route and place its actual tyre contact plane onto the road slope.
        Position-=Rotation.RotateVector(MeshOffsets[Vehicle.Kind]);
        Poses[Vehicle.Kind].Add(FTransform(Rotation,Position,Vehicle.Active ? FVector::OneVector : FVector::ZeroVector));
    }
    for(int32 Kind=0;Kind<4;++Kind)
    {
        // Stable instance indices: no component/Actor allocation, removal,
        // collision update or HISM tree rebuild occurs during traffic motion.
        for(int32 I=0;I<Poses[Kind].Num();++I)
            VehicleMeshes[Kind]->UpdateInstanceTransform(I,Poses[Kind][I],true,I==Poses[Kind].Num()-1,true);
    }
    PeakActive=FMath::Max(PeakActive,Simulation.ActiveCount());
}

void AGHSCampusTrafficActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if(!bReady)return;
    Simulation.Advance(DeltaSeconds);
    UpdateInstances();
}

FString AGHSCampusTrafficActor::GetTrafficReportJson() const
{
    auto Json=MakeShared<FJsonObject>();
    Json->SetBoolField(TEXT("ready"),bReady);
    Json->SetNumberField(TEXT("active"),Simulation.ActiveCount());
    Json->SetNumberField(TEXT("capacity"),GHSTraffic::Capacity);
    Json->SetNumberField(TEXT("peak_active"),PeakActive);
    Json->SetNumberField(TEXT("route_count"),Routes.Num());
    Json->SetNumberField(TEXT("component_count"),VehicleMeshes.Num());
    Json->SetNumberField(TEXT("completed"),double(Simulation.Completed));
    Json->SetNumberField(TEXT("spawned"),double(Simulation.Spawned));
    int32 Instances=0;
    for(const auto& Mesh:VehicleMeshes)if(Mesh)Instances+=Mesh->GetInstanceCount();
    Json->SetNumberField(TEXT("fixed_instances"),Instances);
    Json->SetBoolField(TEXT("collision"),GetActorEnableCollision());
    FString Text;FJsonSerializer::Serialize(Json,TJsonWriterFactory<>::Create(&Text));return Text;
}
