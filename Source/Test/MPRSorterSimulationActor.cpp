#include "MPRSorterSimulationActor.h"
#include "MPRSorterHUDWidget.h"
#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehouseRoofComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/StaticMesh.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UObject/ConstructorHelpers.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"

namespace
{
constexpr int32 BinCapacity=3;
const FVector PackageSize(22,16,5);
FString PhaseName(MPRSorter::CarrierPhase Phase)
{
    switch(Phase)
    {
    case MPRSorter::CarrierPhase::Scan:return TEXT("上包识别");
    case MPRSorter::CarrierPhase::LoadedTravel:return TEXT("行走 / 升降");
    case MPRSorter::CarrierPhase::Lift:return TEXT("格口就位");
    case MPRSorter::CarrierPhase::Unload:return TEXT("侧向投料");
    default:return TEXT("空载回环");
    }
}
FString ReasonName(MPRSorter::BlockReason Reason)
{
    switch(Reason)
    {
    case MPRSorter::BlockReason::Scanning:return TEXT("上包识别");
    case MPRSorter::BlockReason::Lifting:return TEXT("等待托盘就位");
    case MPRSorter::BlockReason::Unloading:return TEXT("侧向投料");
    case MPRSorter::BlockReason::FullBin:return TEXT("满格等待取箱");
    default:return TEXT("闭环运行");
    }
}
TArray<TSharedPtr<FJsonValue>> XYZ(const FVector& P)
{ return {MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)}; }
bool Diagnostics() { return FParse::Param(FCommandLine::Get(),TEXT("TwinDiagnostics")); }
}

AMPRSorterSimulationActor::AMPRSorterSimulationActor()
{
    PrimaryActorTick.bCanEverTick=true;
    PrimaryActorTick.TickGroup=TG_PostUpdateWork;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("SorterSimulationRoot")));
    Towers=MakeInstances(TEXT("MovingColumns"));Trays=MakeInstances(TEXT("LiftTrays"));
    Parcels=MakeInstances(TEXT("MovingParcels"));BinParcels=MakeInstances(TEXT("CollectedParcels"));
    ActiveLights=MakeInstances(TEXT("ActiveCells"));FullLights=MakeInstances(TEXT("FullCells"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube"));
    for(auto* Component:{Parcels.Get(),BinParcels.Get(),ActiveLights.Get(),FullLights.Get()}) Component->SetStaticMesh(Cube.Object);
    SetActorEnableCollision(false);
}

UInstancedStaticMeshComponent* AMPRSorterSimulationActor::MakeInstances(const TCHAR* Name)
{
    auto* C=CreateDefaultSubobject<UInstancedStaticMeshComponent>(Name);
    C->SetupAttachment(RootComponent);C->SetMobility(EComponentMobility::Movable);
    C->SetCollisionProfileName(TEXT("NoCollision"));C->SetCollisionEnabled(ECollisionEnabled::NoCollision);C->SetGenerateOverlapEvents(false);
    C->SetCanEverAffectNavigation(false);C->bAffectDistanceFieldLighting=false;
    C->bAffectDynamicIndirectLighting=false;C->SetCastShadow(true);
    return C;
}

bool AMPRSorterSimulationActor::LoadLayout()
{
    using FObject=TSharedPtr<FJsonObject>;
    using FArray=TArray<TSharedPtr<FJsonValue>>;
    auto Fail=[this](const TCHAR* Message){Error=Message;return false;};
    auto Object=[](const FObject& Parent,const TCHAR* Key,FObject& Out)
    {
        const FObject* Value=nullptr;
        if(!Parent||!Parent->TryGetObjectField(Key,Value)||!Value||!Value->IsValid())return false;
        Out=*Value;return true;
    };
    auto ValueObject=[](const TSharedPtr<FJsonValue>& Value,FObject& Out)
    {
        const FObject* Child=nullptr;
        if(!Value||!Value->TryGetObject(Child)||!Child||!Child->IsValid())return false;
        Out=*Child;return true;
    };
    auto Array=[](const FObject& Parent,const TCHAR* Key,const FArray*& Out)
    {return Parent&&Parent->TryGetArrayField(Key,Out)&&Out;};
    auto ValueNumber=[](const TSharedPtr<FJsonValue>& Value,double& Out)
    {return Value&&Value->Type==EJson::Number&&Value->TryGetNumber(Out)&&FMath::IsFinite(Out);};
    auto Number=[&ValueNumber](const FObject& Parent,const TCHAR* Key,double& Out)
    {
        if(!Parent)return false;
        const auto* Value=Parent->Values.Find(Key);return Value&&ValueNumber(*Value,Out);
    };
    auto Integer=[&Number](const FObject& Parent,const TCHAR* Key,int32& Out,int32 Min,int32 Max)
    {
        double Value;if(!Number(Parent,Key,Value)||Value<Min||Value>Max||Value!=FMath::FloorToDouble(Value))return false;
        Out=int32(Value);return true;
    };
    auto Vector=[&Array,&ValueNumber](const FObject& Parent,const TCHAR* Key,FVector& Out)
    {
        const FArray* Values=nullptr;double X,Y,Z;
        if(!Array(Parent,Key,Values)||Values->Num()!=3||!ValueNumber((*Values)[0],X)||!ValueNumber((*Values)[1],Y)||!ValueNumber((*Values)[2],Z))return false;
        Out=FVector(X,Y,Z);return true;
    };
    TSharedPtr<FJsonObject> Root;
    if(LayoutJson.Len()>2000000||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(LayoutJson),Root)||!Root)
        return Fail(TEXT("设备布局数据无效"));
    int32 Schema;FString Units;FObject Profiles;const FArray* Rows=nullptr;
    if(!Integer(Root,TEXT("schema_version"),Schema,1,1)||!Root->TryGetStringField(TEXT("units"),Units)||Units!=TEXT("UE cm")
       ||!Object(Root,TEXT("profiles"),Profiles)||!Array(Root,TEXT("machines"),Rows)||Rows->Num()!=22)
        return Fail(TEXT("设备布局版本、单位或设备清单无效"));
    // Parse transactionally: malformed editable JSON must not leave a partial fleet.
    TArray<FMachine> Parsed;int32 Offset=0,Count64=0,Count120=0;TSet<FString> Ids;
    for(const auto& Value:*Rows)
    {
        FObject Row,P,T;FMachine M;
        if(!ValueObject(Value,Row)||!Row->TryGetStringField(TEXT("id"),M.Id)||M.Id.IsEmpty()||M.Id.Len()>128
           ||!Row->TryGetStringField(TEXT("profile"),M.Profile)||Ids.Contains(M.Id)
           ||(M.Profile!=TEXT("cad64")&&M.Profile!=TEXT("cad120"))
           ||!Object(Profiles,*M.Profile,P)||!Object(Row,TEXT("world_transform"),T))
            return Fail(TEXT("设备标识、类型或变换缺失"));
        Ids.Add(M.Id);
        const bool Is64=M.Profile==TEXT("cad64");if(Is64)++Count64;else ++Count120;
        FVector Location,Scale;const FArray* Q=nullptr;double Qx,Qy,Qz,Qw;
        if(!Vector(T,TEXT("translation_cm"),Location)||!Vector(T,TEXT("scale"),Scale)
           ||!Array(T,TEXT("rotation_xyzw"),Q)||Q->Num()!=4
           ||!ValueNumber((*Q)[0],Qx)||!ValueNumber((*Q)[1],Qy)||!ValueNumber((*Q)[2],Qz)||!ValueNumber((*Q)[3],Qw))
            return Fail(TEXT("设备变换坐标无效"));
        FQuat Rotation(Qx,Qy,Qz,Qw);
        if(Location.GetAbsMax()>1.e8||Scale.GetMin()<=0||Scale.GetMax()>100||!Rotation.IsNormalized())return Fail(TEXT("设备变换范围无效"));
        M.World=FTransform(Rotation,Location,Scale);
        MPRSorter::Config C;int32 Levels,Sides,Capacity,TowerCount;
        if(!Number(P,TEXT("track_half_straight_cm"),M.Half)||!Number(P,TEXT("track_radius_cm"),M.Radius)
           ||M.Half<100||M.Half>500||M.Radius<20||M.Radius>50
           ||!Integer(P,TEXT("modeled_columns"),C.Columns,Is64?8:15,Is64?8:15)
           ||!Integer(P,TEXT("modeled_levels"),Levels,4,4)||!Integer(P,TEXT("sides"),Sides,2,2)
           ||!Integer(P,TEXT("modeled_capacity"),Capacity,Is64?64:120,Is64?64:120)
           ||!Integer(P,TEXT("tower_count"),TowerCount,4,4)||!Number(P,TEXT("infeed_height_cm"),C.LoadHeightCm)||C.LoadHeightCm<15||C.LoadHeightCm>190)
            return Fail(TEXT("设备轨道、层数或容量配置无效"));
        C.Levels=Levels;C.BinCapacity=BinCapacity;C.LoopLengthCm=4*M.Half+2*PI*M.Radius;
        C.ChainSpeedCmS=40;C.LiftSpeedCmS=55;C.ScanSeconds=.5;C.UnloadSeconds=1.2;C.CollectSeconds=12;C.AutoCollect=true;
        const FArray* LevelRows=nullptr;const FArray* Columns=nullptr;const FArray* BinRows=nullptr;
        if(!Array(P,TEXT("levels"),LevelRows)||LevelRows->Num()!=4||!Array(P,TEXT("column_x_cm"),Columns)||Columns->Num()!=C.Columns
           ||!Array(P,TEXT("bins"),BinRows)||BinRows->Num()!=Capacity)return Fail(TEXT("设备层高、列或格口清单缺失"));
        for(int32 I=0;I<LevelRows->Num();++I)
        {
            FObject L;int32 Level;double Height;
            if(!ValueObject((*LevelRows)[I],L)||!Integer(L,TEXT("level"),Level,I,I)||!Number(L,TEXT("tray_carry_z_cm"),Height)
               ||Height<15||Height>190||(I>0&&Height<=C.LevelHeightsCm.back()))return Fail(TEXT("设备层高顺序或数值无效"));
            C.LevelHeightsCm.push_back(Height);
        }
        const double Quarter=PI*M.Radius*.5;
        TArray<double> ColumnPositions;
        for(const auto& X:*Columns)
        {
            double At;if(!ValueNumber(X,At)||FMath::Abs(At)>M.Half||(!ColumnPositions.IsEmpty()&&At<=ColumnPositions.Last()))return Fail(TEXT("设备列坐标无效"));
            ColumnPositions.Add(At);
        }
        for(int32 Side=0;Side<2;++Side)for(double At:ColumnPositions)
        {
            C.DestinationDistances01.push_back((Side==0?Quarter+M.Half-At:Quarter+2*M.Half+PI*M.Radius+At+M.Half)/C.LoopLengthCm);
        }
        M.Bins.SetNum(2*C.Columns*C.Levels);TSet<int32> BinKeys;
        for(const auto& V:*BinRows)
        {
            FObject B;int32 Side,Column,Level;
            if(!ValueObject(V,B)||!Integer(B,TEXT("side"),Side,0,1)||!Integer(B,TEXT("column"),Column,0,C.Columns-1)
               ||!Integer(B,TEXT("level"),Level,0,3))return Fail(TEXT("格口索引无效"));
            const int32 Index=(Side*C.Columns+Column)*C.Levels+Level;if(BinKeys.Contains(Index))return Fail(TEXT("格口索引重复"));
            BinKeys.Add(Index);auto& Point=M.Bins[Index];
            if(!Vector(B,TEXT("chute_entry_cm"),Point.Entry)||!Vector(B,TEXT("chute_outlet_cm"),Point.Outlet)
               ||!Vector(B,TEXT("bin_drop_cm"),Point.Drop)||!Number(B,TEXT("bin_rim_z_cm"),Point.RimZ)
               ||Point.Entry.GetAbsMax()>1000||Point.Outlet.GetAbsMax()>1000||Point.Drop.GetAbsMax()>1000
               ||FMath::Abs(Point.Entry.X-ColumnPositions[Column])>.1||FMath::Abs(Point.Drop.X-Point.Entry.X)>.1
               ||Point.Drop.Z<0||Point.RimZ<Point.Drop.Z+PackageSize.Z*BinCapacity+.3
               ||Point.Entry.Z<=Point.Outlet.Z||Point.Outlet.Z<=Point.RimZ
               ||FMath::Abs(C.LevelHeightsCm[Level]-Point.Entry.Z-1.5)>.1
               ||(Side==0?!(Point.Entry.Y>M.Radius&&Point.Outlet.Y>Point.Entry.Y&&Point.Drop.Y>Point.Outlet.Y)
                          :!(Point.Entry.Y<-M.Radius&&Point.Outlet.Y<Point.Entry.Y&&Point.Drop.Y<Point.Outlet.Y)))
                return Fail(TEXT("格口滑槽或箱体坐标无效"));
        }
        if(BinKeys.Num()!=M.Bins.Num())return Fail(TEXT("格口清单不完整"));
        std::string Message;if(!M.Simulation.Initialize(C,Message)) { Error=UTF8_TO_TCHAR(Message.c_str());return false; }
        M.BinOffset=Offset;Offset+=M.Bins.Num();M.CachedBinState.Init(INDEX_NONE,M.Bins.Num());Parsed.Add(MoveTemp(M));
    }
    if(Count64!=18||Count120!=4||Offset!=1632)return Fail(TEXT("设备类型数量不符合已保存场景"));
    Machines=MoveTemp(Parsed);Error.Empty();return true;
}

void AMPRSorterSimulationActor::BeginPlay()
{
    Super::BeginPlay();
    // This actor is saved only in MPR; no registry or GHS default behavior changes.
    bReady=TowerMesh&&TrayMesh&&ParcelMaterial&&ActiveMaterial&&FullMaterial&&LoadLayout();
    if(!bReady) { Error=Error.IsEmpty()?TEXT("仿真资产或布局缺失"):Error;UE_LOG(LogTemp,Error,TEXT("MPR_SORTER: %s"),*Error);SetActorTickEnabled(false);return; }
    Towers->SetStaticMesh(TowerMesh);Trays->SetStaticMesh(TrayMesh);
    Parcels->SetMaterial(0,ParcelMaterial);BinParcels->SetMaterial(0,ParcelMaterial);
    ActiveLights->SetMaterial(0,ActiveMaterial);FullLights->SetMaterial(0,FullMaterial);
    ActiveLights->SetCastShadow(false);FullLights->SetCastShadow(false);
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    for(auto& M:Machines)
    {
        for(int32 I=0;I<MPRSorter::CarrierCount;++I){Towers->AddInstance(Hidden);Trays->AddInstance(Hidden);Parcels->AddInstance(Hidden);}
        for(int32 I=0;I<M.Bins.Num();++I)
        {
            ActiveLights->AddInstance(Hidden);FullLights->AddInstance(Hidden);
            for(int32 J=0;J<BinCapacity;++J)BinParcels->AddInstance(Hidden);
        }
        M.Simulation.SetPlaying(bAutoStart);
    }
    UpdateInstances();AttachPanel();
    UE_LOG(LogTemp,Display,TEXT("MPR_SORTER: ready, 22 machines, 88 circulating lift carriers, 1632 scene cells; demonstration data."));
}

FVector AMPRSorterSimulationActor::PointOnLoop(double Fraction,double H,double R,double& Heading)
{
    const double Q=PI*R*.5,L=4*H+2*PI*R;
    double S=FMath::Fmod(Fraction,1.0)*L;if(S<0)S+=L;
    if(S<Q){const double A=S/R;Heading=A+PI*.5;return FVector(H+R*FMath::Cos(A),R*FMath::Sin(A),0);}
    S-=Q;if(S<2*H){Heading=PI;return FVector(H-S,R,0);}
    S-=2*H;if(S<PI*R){const double A=PI*.5+S/R;Heading=A+PI*.5;return FVector(-H+R*FMath::Cos(A),R*FMath::Sin(A),0);}
    S-=PI*R;if(S<2*H){Heading=0;return FVector(-H+S,-R,0);}
    S-=2*H;const double A=PI*1.5+S/R;Heading=A+PI*.5;return FVector(H+R*FMath::Cos(A),R*FMath::Sin(A),0);
}

void AMPRSorterSimulationActor::UpdateInstances()
{
    TRACE_CPUPROFILER_EVENT_SCOPE(MPRSorter_Presentation);
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    int32 CarrierIndex=0;bool BinsChanged=false;
    for(auto& M:Machines)
    {
        const auto& Bins=M.Simulation.GetBins();
        for(const auto& Carrier:M.Simulation.GetCarriers())
        {
            double Heading;FVector At=PointOnLoop(Carrier.Distance01,M.Half,M.Radius,Heading);
            const FQuat Turn(FVector::UpVector,Heading);
            Towers->UpdateInstanceTransform(CarrierIndex,FTransform(Turn,At)*M.World,true,false,true);
            At.Z=Carrier.LiftHeightCm;
            Trays->UpdateInstanceTransform(CarrierIndex,FTransform(Turn,At)*M.World,true,false,true);
            if(Carrier.ParcelId)
            {
                FVector Parcel=At+FVector(0,0,PackageSize.Z*.5+.3);FQuat ParcelTurn=Turn;
                if(Carrier.State==MPRSorter::CarrierPhase::Unload)
                {
                    const int32 Bin=M.Simulation.BinIndex(Carrier.Target);const auto& P=M.Bins[Bin];
                    const double T=FMath::Clamp(Carrier.UnloadProgress,0.,1.);
                    const double Side=Carrier.Target.Side==0?1.:-1.;
                    const double Slope=FMath::DegreesToRadians(20.);
                    const FVector Normal(0,Side*FMath::Sin(Slope),FMath::Cos(Slope));
                    const FVector Entry=P.Entry+Normal*(PackageSize.Z*.5+.4);
                    const FVector Outlet=P.Outlet+Normal*(PackageSize.Z*.5+.4);
                    // Cross the chute above the real bin rim before settling into it.
                    const FVector Above(P.Drop.X,P.Drop.Y,P.RimZ+PackageSize.Z*.5+1);
                    const FVector Rest=P.Drop+FVector(0,0,PackageSize.Z*(Bins[Bin].Occupancy+.5)+.3);
                    double Tilt=0;
                    if(T<.35)
                    {
                        const double F=T/.35;Tilt=F;
                        Parcel=FMath::Lerp(Parcel,Entry,F)+FVector(0,0,1.5*FMath::Sin(PI*F));
                    }
                    else if(T<.65){Tilt=1;Parcel=FMath::Lerp(Entry,Outlet,(T-.35)/.30);}
                    else if(T<.82){const double F=(T-.65)/.17;Tilt=1-F;Parcel=FMath::Lerp(Outlet,Above,F);}
                    else Parcel=FMath::Lerp(Above,Rest,(T-.82)/.18);
                    // Follow the actual 20-degree chute. The short handoff arc clears
                    // the tray lip while the parcel rotates continuously onto it.
                    ParcelTurn=FQuat(FVector::ForwardVector,-Side*Slope*Tilt);
                }
                Parcels->UpdateInstanceTransform(CarrierIndex,FTransform(ParcelTurn,Parcel,PackageSize/100)*M.World,true,false,true);
            }
            else Parcels->UpdateInstanceTransform(CarrierIndex,Hidden,true,false,true);
            ++CarrierIndex;
        }
        for(int32 I=0;I<M.Bins.Num();++I)
        {
            const auto& Bin=Bins[I];const int32 State=Bin.Occupancy+8*Bin.Reserved;
            if(M.CachedBinState[I]==State)continue;
            M.CachedBinState[I]=State;BinsChanged=true;
            const int32 Slot=M.BinOffset+I;const auto& P=M.Bins[I];
            for(int32 J=0;J<BinCapacity;++J)
            {
                const FVector At=P.Drop+FVector(0,0,PackageSize.Z*(J+.5)+.3);
                BinParcels->UpdateInstanceTransform(Slot*BinCapacity+J,J<Bin.Occupancy?FTransform(FQuat::Identity,At,PackageSize/100)*M.World:Hidden,true,false,true);
            }
            const FVector Signal=P.Outlet+FVector(0,0,3);
            const FTransform Light=FTransform(FQuat::Identity,Signal,FVector(.15,.04,.025))*M.World;
            ActiveLights->UpdateInstanceTransform(Slot,(Bin.Reserved>0||Bin.Occupancy>0)&&Bin.Occupancy<BinCapacity?Light:Hidden,true,false,true);
            FullLights->UpdateInstanceTransform(Slot,Bin.Occupancy>=BinCapacity?Light:Hidden,true,false,true);
        }
    }
    for(auto* C:{Towers.Get(),Trays.Get(),Parcels.Get()})C->MarkRenderStateDirty();
    if(BinsChanged)for(auto* C:{BinParcels.Get(),ActiveLights.Get(),FullLights.Get()})C->MarkRenderStateDirty();
}

void AMPRSorterSimulationActor::AttachPanel()
{
    if(Panel||!bReady)return;
    auto* PC=Cast<AGHSWarehousePlayerController>(UGameplayStatics::GetPlayerController(this,0));
    if(!PC||!PC->IsLocalController())return;
    Panel=CreateWidget<UMPRSorterHUDWidget>(PC,UMPRSorterHUDWidget::StaticClass());
    if(Panel){Panel->InitializeSorter(this);Panel->AddToViewport(80);Panel->SetDesiredSizeInViewport(FVector2D(360,350));Panel->SetPositionInViewport(FVector2D(20,80),false);}
}

void AMPRSorterSimulationActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);if(!bReady)return;
    AttachPanel();UpdateFocus();
    if(bAutomaticAdvance&&IsSimulationPlaying())
    { for(auto& M:Machines)M.Simulation.Advance(DeltaSeconds);UpdateInstances(); }
}
void AMPRSorterSimulationActor::EndPlay(const EEndPlayReason::Type Reason)
{ if(Panel){Panel->RemoveFromParent();Panel=nullptr;}Super::EndPlay(Reason); }
bool AMPRSorterSimulationActor::IsSimulationPlaying() const { return bReady&&Machines[0].Simulation.IsPlaying(); }
bool AMPRSorterSimulationActor::IsAutomaticCollection() const { return bReady&&Machines[0].Simulation.IsAutoCollectEnabled(); }
double AMPRSorterSimulationActor::GetSimulationRate() const { return bReady?Machines[0].Simulation.GetRate():1.; }
void AMPRSorterSimulationActor::SetSimulationPlaying(bool Playing) { for(auto& M:Machines)M.Simulation.SetPlaying(Playing); }
void AMPRSorterSimulationActor::ResetSimulation(){for(auto& M:Machines){M.Simulation.Reset();M.CachedBinState.Init(INDEX_NONE,M.Bins.Num());}if(bReady)UpdateInstances();}
void AMPRSorterSimulationActor::SetSimulationRate(double Rate){for(auto& M:Machines)M.Simulation.SetRate(Rate);}
void AMPRSorterSimulationActor::SetAutomaticCollection(bool Enabled){for(auto& M:Machines)M.Simulation.SetAutoCollect(Enabled);}
void AMPRSorterSimulationActor::ClearFullBins()
{for(auto& M:Machines){const auto Copy=M.Simulation.GetBins();for(const auto& B:Copy)if(B.Occupancy>=B.Capacity)M.Simulation.ClearBin(B.Target);}if(bReady)UpdateInstances();}
void AMPRSorterSimulationActor::FocusMachine(int32 Index)
{
    if(!Machines.IsValidIndex(Index))return;SelectedMachine=Index;PendingFocus=Index;
    auto* PC=Cast<AGHSWarehousePlayerController>(UGameplayStatics::GetPlayerController(this,0));
    if(PC){PC->CancelCameraDrag();if(PC->WarehouseRoof)PC->WarehouseRoof->OpenRoof(true);}
    UpdateFocus();
}
void AMPRSorterSimulationActor::UpdateFocus()
{
    if(!Machines.IsValidIndex(PendingFocus))return;
    auto* PC=Cast<AGHSWarehousePlayerController>(UGameplayStatics::GetPlayerController(this,0));
    if(!PC||!PC->WarehouseRoof||!PC->WarehouseRoof->IsInteriorAvailable())return;
    auto* Camera=Cast<AGHSWarehouseCameraPawn>(PC->GetPawn());if(!Camera)return;
    int32 Width,Height;PC->GetViewportSize(Width,Height);if(Width<10||Height<10)return;
    const auto& M=Machines[PendingFocus];const float Yaw=M.World.Rotator().Yaw-65.f;
    Camera->FocusOnTarget(M.World.TransformPosition(FVector(0,0,105)),float((M.Half+M.Radius)*3.7),FRotator(-32,Yaw,0),FVector2D(Width,Height),FVector2D(Width*.61,Height*.53),.8f);
    PendingFocus=INDEX_NONE;
}
void AMPRSorterSimulationActor::SetPanelVisible(bool Visible){if(Panel)Panel->SetVisibility(Visible?ESlateVisibility::SelfHitTestInvisible:ESlateVisibility::Collapsed);}
void AMPRSorterSimulationActor::SetAutomaticAdvanceForDiagnostics(bool Enabled){if(Diagnostics())bAutomaticAdvance=Enabled;}
bool AMPRSorterSimulationActor::AdvanceSimulationForDiagnostics(double Seconds)
{if(!Diagnostics()||!bReady||!FMath::IsFinite(Seconds)||Seconds<0||Seconds*GetSimulationRate()>86400)return false;for(auto& M:Machines)if(!M.Simulation.Advance(Seconds))return false;UpdateInstances();return true;}
FString AMPRSorterSimulationActor::GetMachineTitle() const
{if(!bReady)return Error;return FString::Printf(TEXT("木马 %02d / %d · 场景格口 %d"),SelectedMachine+1,Machines.Num(),Machines[SelectedMachine].Bins.Num());}
FString AMPRSorterSimulationActor::GetStatusText() const
{if(!bReady)return Error;return FString::Printf(TEXT("%s · %.0f× · %s"),IsSimulationPlaying()?TEXT("运行中"):TEXT("已暂停"),GetSimulationRate(),*ReasonName(Machines[SelectedMachine].Simulation.GetStats().Reason));}
FString AMPRSorterSimulationActor::GetProgressText() const
{
    if(!bReady)return TEXT("初始化中");const auto& S=Machines[SelectedMachine].Simulation.GetStats();int32 Occupied=0,Full=0;
    for(const auto& B:Machines[SelectedMachine].Simulation.GetBins()){Occupied+=B.Occupancy;Full+=B.Occupancy>=B.Capacity;}
    return FString::Printf(TEXT("已投 %llu   在途 %d   待取 %d\n已取 %llu   满格 %d   仿真 %.1f s"),static_cast<unsigned long long>(S.Completed),S.Active,Occupied,static_cast<unsigned long long>(S.Collected),Full,S.SimTime);
}
FString AMPRSorterSimulationActor::GetCarrierText() const
{
    if(!bReady)return TEXT("");
    for(const auto& C:Machines[SelectedMachine].Simulation.GetCarriers())if(C.ParcelId)
        return FString::Printf(TEXT("包裹 %04llu → %s侧 %02d列 %d层 · %s"),static_cast<unsigned long long>(C.ParcelId),C.Target.Side==0?TEXT("A"):TEXT("B"),C.Target.Column+1,C.Target.Level+1,*PhaseName(C.State));
    return TEXT("空载回环 · 等待上包");
}

FString AMPRSorterSimulationActor::GetSimulationReportJson() const
{
    auto Root=MakeShared<FJsonObject>();Root->SetBoolField(TEXT("ready"),bReady);Root->SetStringField(TEXT("error"),Error);
    Root->SetStringField(TEXT("data_mode"),TEXT("demonstration"));Root->SetNumberField(TEXT("machine_count"),Machines.Num());
    Root->SetBoolField(TEXT("playing"),IsSimulationPlaying());Root->SetNumberField(TEXT("rate"),GetSimulationRate());
    Root->SetBoolField(TEXT("automatic_collection"),IsAutomaticCollection());Root->SetNumberField(TEXT("selected_machine"),SelectedMachine);
    Root->SetNumberField(TEXT("components"),6);Root->SetNumberField(TEXT("tower_instances"),Towers->GetInstanceCount());
    Root->SetNumberField(TEXT("tray_instances"),Trays->GetInstanceCount());Root->SetNumberField(TEXT("parcel_instances"),Parcels->GetInstanceCount());
    Root->SetNumberField(TEXT("bin_parcel_instances"),BinParcels->GetInstanceCount());Root->SetBoolField(TEXT("panel_attached"),Panel!=nullptr);
    TArray<TSharedPtr<FJsonValue>> Rows;uint64 Spawned=0,Completed=0,Collected=0;int32 Active=0,Occupancy=0;
    for(const auto& M:Machines)
    {
        const auto& S=M.Simulation.GetStats();auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("id"),M.Id);Row->SetStringField(TEXT("profile"),M.Profile);
        Row->SetNumberField(TEXT("sim_time"),S.SimTime);Row->SetNumberField(TEXT("phase"),S.ChainPhase01);
        Row->SetNumberField(TEXT("spawned"),double(S.Spawned));Row->SetNumberField(TEXT("completed"),double(S.Completed));Row->SetNumberField(TEXT("collected"),double(S.Collected));Row->SetNumberField(TEXT("active"),S.Active);
        Row->SetStringField(TEXT("block_reason"),ReasonName(S.Reason));int32 Count=0,Full=0;
        TArray<TSharedPtr<FJsonValue>> Cells;
        for(const auto& B:M.Simulation.GetBins())
        {Count+=B.Occupancy;Full+=B.Occupancy>=B.Capacity;if(B.Occupancy||B.Reserved){auto Cell=MakeShared<FJsonObject>();Cell->SetNumberField(TEXT("side"),B.Target.Side);Cell->SetNumberField(TEXT("column"),B.Target.Column);Cell->SetNumberField(TEXT("level"),B.Target.Level);Cell->SetNumberField(TEXT("occupancy"),B.Occupancy);Cell->SetNumberField(TEXT("reserved"),B.Reserved);Cells.Add(MakeShared<FJsonValueObject>(Cell));}}
        Row->SetNumberField(TEXT("occupancy"),Count);Row->SetNumberField(TEXT("full_bins"),Full);Row->SetArrayField(TEXT("cells"),Cells);
        TArray<TSharedPtr<FJsonValue>> Carriers;
        for(const auto& C:M.Simulation.GetCarriers())
        {
            auto Item=MakeShared<FJsonObject>();Item->SetNumberField(TEXT("parcel_id"),double(C.ParcelId));Item->SetStringField(TEXT("state"),PhaseName(C.State));
            Item->SetNumberField(TEXT("distance01"),C.Distance01);Item->SetNumberField(TEXT("lift_cm"),C.LiftHeightCm);Item->SetNumberField(TEXT("unload_progress"),C.UnloadProgress);
            Item->SetNumberField(TEXT("side"),C.Target.Side);Item->SetNumberField(TEXT("column"),C.Target.Column);Item->SetNumberField(TEXT("level"),C.Target.Level);
            double Heading;FVector Point=PointOnLoop(C.Distance01,M.Half,M.Radius,Heading);Point.Z=C.LiftHeightCm;
            Item->SetArrayField(TEXT("tray_world_cm"),XYZ(M.World.TransformPosition(Point)));Carriers.Add(MakeShared<FJsonValueObject>(Item));
        }
        Row->SetArrayField(TEXT("carriers"),Carriers);Rows.Add(MakeShared<FJsonValueObject>(Row));
        Spawned+=S.Spawned;Completed+=S.Completed;Collected+=S.Collected;Active+=S.Active;Occupancy+=Count;
    }
    Root->SetArrayField(TEXT("machines"),Rows);Root->SetNumberField(TEXT("spawned"),double(Spawned));Root->SetNumberField(TEXT("completed"),double(Completed));Root->SetNumberField(TEXT("collected"),double(Collected));Root->SetNumberField(TEXT("active"),Active);Root->SetNumberField(TEXT("occupancy"),Occupancy);
    Root->SetBoolField(TEXT("conserved"),Spawned==Completed+Active&&Completed==Collected+Occupancy);
    FString Result;FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Result));return Result;
}
