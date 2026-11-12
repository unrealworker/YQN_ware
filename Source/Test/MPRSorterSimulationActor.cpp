#include "MPRSorterSimulationActor.h"
#include "MPRSorterHUDWidget.h"
#include "MPRWorkerPoseComponent.h"
#include "MPRCadWorkerData.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/AnimSequence.h"
#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehouseRoofComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UObject/ConstructorHelpers.h"
#include "UObject/UObjectGlobals.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "Math/RotationMatrix.h"
#include "Materials/MaterialInterface.h"

namespace
{
constexpr int32 BinCapacity=3;
const FVector PackageSize(22,16,5);
FString PhaseName(MPRSorter::CarrierPhase Phase)
{
    switch(Phase)
    {
    case MPRSorter::CarrierPhase::Scan:return TEXT("上包识别");
    case MPRSorter::CarrierPhase::Induct:return TEXT("接驳带自动入机");
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
    case MPRSorter::BlockReason::FullBin:return TEXT("满车等待更换");
    case MPRSorter::BlockReason::Inducting:return TEXT("接驳带入机");
    case MPRSorter::BlockReason::CartExchange:return TEXT("停稳 / 整车更换");
    case MPRSorter::BlockReason::WaitingInfeed:return TEXT("等待来货");
    default:return TEXT("闭环运行");
    }
}
FString CartPhaseName(MPRSorter::CartPhase Phase)
{
    switch(Phase)
    {
    case MPRSorter::CartPhase::FullWaiting:return TEXT("满车待换");
    case MPRSorter::CartPhase::Withdrawing:return TEXT("满车退出");
    case MPRSorter::CartPhase::Outbound:return TEXT("满车转出");
    case MPRSorter::CartPhase::Handoff:return TEXT("满车交接 / 等待空车");
    case MPRSorter::CartPhase::EmptyArriving:return TEXT("空车入位");
    case MPRSorter::CartPhase::Docking:return TEXT("对位 / 确认");
    default:return TEXT("在位收货");
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
    InfeedParcels=MakeInstances(TEXT("InfeedParcels"));
    ActiveLights=MakeInstances(TEXT("ActiveCells"));FullLights=MakeInstances(TEXT("FullCells"));
    WorkerCloth=MakeInstances(TEXT("OperatorClothing"));WorkerSkin=MakeInstances(TEXT("OperatorSkin"));
    WorkerHelmet=MakeInstances(TEXT("OperatorHelmets"));WorkerBoots=MakeInstances(TEXT("OperatorBoots"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere"));
    for(auto* Component:{Parcels.Get(),InfeedParcels.Get(),BinParcels.Get(),ActiveLights.Get(),FullLights.Get(),WorkerCloth.Get(),WorkerBoots.Get()}) Component->SetStaticMesh(Cube.Object);
    WorkerSkin->SetStaticMesh(Sphere.Object);WorkerHelmet->SetStaticMesh(Sphere.Object);
    CentralMetal=MakeInstances(TEXT("CentralFrameMetal"));CentralWhite=MakeInstances(TEXT("CentralFrameWhite"));
    CentralBlue=MakeInstances(TEXT("CentralFrameBlue"));CentralBelt=MakeInstances(TEXT("CentralBelts"));
    CentralColumns=MakeInstances(TEXT("CentralMovingColumns"));CentralTrays=MakeInstances(TEXT("CentralLiftTrays"));
    CentralParcels=MakeInstances(TEXT("CentralParcels"));
    for(auto* C:{CentralMetal.Get(),CentralWhite.Get(),CentralBlue.Get(),CentralBelt.Get(),CentralParcels.Get()})C->SetStaticMesh(Cube.Object);
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Skin(TEXT("/Game/GHSNormalWarehouse/MannedForklift/Materials/M_MF_WorkerV3_Skin"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Navy(TEXT("/Game/GHSNormalWarehouse/MannedForklift/Materials/M_MF_WorkerV3_Navy"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Helmet(TEXT("/Game/GHSNormalWarehouse/MannedForklift/Materials/M_MF_WorkerV3_Helmet"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Rubber(TEXT("/Game/GHSNormalWarehouse/MannedForklift/Materials/M_MF_WorkerV3_Rubber"));
    WorkerClothMaterial=Navy.Object;WorkerSkinMaterial=Skin.Object;
    WorkerHelmetMaterial=Helmet.Object;WorkerBootMaterial=Rubber.Object;
    static ConstructorHelpers::FObjectFinder<USkeletalMesh> Manny(TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"));
    static ConstructorHelpers::FObjectFinder<UAnimSequence> Idle(TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle"));
    WorkerMesh=Manny.Object;WorkerIdle=Idle.Object;
    SetActorEnableCollision(false);
}

void AMPRSorterSimulationActor::ClearCartInstances()
{
    // Preview components are never serialized as scene instances. Destroy every
    // owned transient cart component as well as the tracked references, covering
    // editor reconstruction/PIE duplication where transient properties reset.
    TArray<UInstancedStaticMeshComponent*> Owned;
    GetComponents<UInstancedStaticMeshComponent>(Owned);
    for(auto* C:Owned)if(C&&C->GetFName().ToString().StartsWith(TEXT("RuntimeCart_"))&&C->HasAnyFlags(RF_Transient))
        C->DestroyComponent();
    RuntimeCartComponents.Reset();
}

#if WITH_EDITOR
void AMPRSorterSimulationActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    if(!GetWorld()||GetWorld()->IsGameWorld())return;
    ClearCartInstances();Machines.Reset();Error.Empty();bReady=false;
    // New actors and incremental property assignment legitimately have partial
    // inputs. Keep them silent and leave gameplay initialization to BeginPlay.
    if(LayoutJson.IsEmpty()||CartMeshes.IsEmpty())return;
    if(LoadLayout())BuildCartInstances(true);
    bReady=false;
}
#endif

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
    if(!Integer(Root,TEXT("schema_version"),Schema,2,2)||!Root->TryGetStringField(TEXT("units"),Units)||Units!=TEXT("UE cm")
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
        int32 InfeedSide;
        FVector PickupWorld,EntryWorld;
        if(!Integer(Row,TEXT("infeed_side_local_x"),InfeedSide,-1,1)||InfeedSide==0
           ||!Vector(Row,TEXT("pickup_ue_cm"),PickupWorld)||!Vector(Row,TEXT("entry_ue_cm"),EntryWorld))
            return Fail(TEXT("设备朝向或输送接驳点缺失"));
        M.InfeedSide=InfeedSide;M.LoadFraction=InfeedSide>0?0.:.5;
        M.Pickup=M.World.InverseTransformPosition(PickupWorld);M.Entry=M.World.InverseTransformPosition(EntryWorld);
        if(M.Pickup.GetAbsMax()>2000||M.Entry.GetAbsMax()>2000||(M.Pickup.X-M.Entry.X)*M.InfeedSide<20
           ||(M.Pickup-M.Entry).Size()>150)return Fail(TEXT("输送接驳点不符合当前设备范围"));
        M.FeedStart=M.Pickup-FVector(0,120,0);
        MPRSorter::Config C;int32 Levels,Sides,Capacity,TowerCount;
        if(!Number(P,TEXT("track_half_straight_cm"),M.Half)||!Number(P,TEXT("track_radius_cm"),M.Radius)
           ||M.Half<100||M.Half>500||M.Radius<20||M.Radius>50
           ||!Integer(P,TEXT("modeled_columns"),C.Columns,Is64?8:15,Is64?8:15)
           ||!Integer(P,TEXT("modeled_levels"),Levels,4,4)||!Integer(P,TEXT("sides"),Sides,2,2)
           ||!Integer(P,TEXT("modeled_capacity"),Capacity,Is64?64:120,Is64?64:120)
           ||!Integer(P,TEXT("tower_count"),TowerCount,4,4)||!Number(P,TEXT("infeed_height_cm"),C.LoadHeightCm)||C.LoadHeightCm<15||C.LoadHeightCm>190)
            return Fail(TEXT("设备轨道、层数或容量配置无效"));
        C.Levels=Levels;C.BinCapacity=BinCapacity;C.LoopLengthCm=4*M.Half+2*PI*M.Radius;
        C.CartColumns=Is64?4:5;C.InfeedCapacity=3;C.InfeedTravelSeconds=3.6;C.InfeedSpacingSeconds=1.2;
        C.InductSeconds=.65;C.ExternalInfeed=true;C.InfeedTravelSeconds=1.5;
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
            const double Physical=(Side==0?Quarter+M.Half-At:Quarter+2*M.Half+PI*M.Radius+At+M.Half)/C.LoopLengthCm;
            C.DestinationDistances01.push_back(FMath::Fmod(Physical-M.LoadFraction+1.,1.));
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
        const FArray* CartRows=nullptr;const FArray* Groups=nullptr;
        if(!Array(P,TEXT("cart_column_groups"),Groups)||Groups->Num()!=(Is64?2:3)
           ||!Array(P,TEXT("carts"),CartRows)||CartRows->Num()!=int32(M.Simulation.GetCarts().size()))
            return Fail(TEXT("独立料框车分组缺失"));
        for(const auto& Group:*Groups){double Width;if(!ValueNumber(Group,Width)||Width!=C.CartColumns)return Fail(TEXT("料框车分组不符合 CAD"));}
        for(int32 CartIndex=0;CartIndex<CartRows->Num();++CartIndex)
        {
            FObject Cart;FCartPoint Point;int32 Index;const FArray* Bounds=nullptr;
            if(!ValueObject((*CartRows)[CartIndex],Cart)||!Integer(Cart,TEXT("index"),Index,CartIndex,CartIndex)
               ||!Integer(Cart,TEXT("side"),Point.Side,0,1)||!Integer(Cart,TEXT("first_column"),Point.FirstColumn,0,C.Columns-1)
               ||!Integer(Cart,TEXT("column_count"),Point.ColumnCount,C.CartColumns,C.CartColumns)
               ||!Cart->TryGetStringField(TEXT("mesh"),Point.MeshPath)||!Point.MeshPath.StartsWith(TEXT("/Game/MPRWarehouse/"))
               ||!Vector(Cart,TEXT("local_origin_cm"),Point.Origin)||!Array(Cart,TEXT("bounds_cm"),Bounds)||Bounds->Num()!=2
               ||!Number(Cart,TEXT("retreat_distance_cm"),Point.Retreat)||!Number(Cart,TEXT("outbound_end_x_cm"),Point.OutboundEndX))
                return Fail(TEXT("独立料框车网格、位置或路线无效"));
            double V[6];for(int32 B=0;B<2;++B)
            {
                const FArray* Values=nullptr;
                if(!(*Bounds)[B]||!(*Bounds)[B]->TryGetArray(Values)||!Values||Values->Num()!=3)return Fail(TEXT("料框车包围盒无效"));
                for(int32 Axis=0;Axis<3;++Axis)if(!ValueNumber((*Values)[Axis],V[B*3+Axis]))return Fail(TEXT("料框车包围盒坐标无效"));
            }
            Point.BoundsMin=FVector(V[0],V[1],V[2]);Point.BoundsMax=FVector(V[3],V[4],V[5]);
            const auto& CoreCart=M.Simulation.GetCarts()[size_t(CartIndex)];
            if(Point.Side!=CoreCart.Side||Point.FirstColumn!=CoreCart.FirstColumn||Point.ColumnCount!=CoreCart.ColumnCount
               ||Point.Origin.GetAbsMax()>1000||FMath::Abs(Point.Origin.Z)>.1||Point.Retreat<30||Point.Retreat>100
               ||Point.OutboundEndX<M.Half||Point.OutboundEndX>2000||(Point.BoundsMax-Point.BoundsMin).GetMin()<=0)
                return Fail(TEXT("料框车索引、停靠或退出范围无效"));
            M.Carts.Add(MoveTemp(Point));
        }
        M.BinOffset=Offset;Offset+=M.Bins.Num();M.CachedBinState.Init(INDEX_NONE,M.Bins.Num());Parsed.Add(MoveTemp(M));
    }
    if(Count64!=18||Count120!=4||Offset!=1632)return Fail(TEXT("设备类型数量不符合已保存场景"));
    Machines=MoveTemp(Parsed);Error.Empty();return LoadCentralDistribution();
}

void AMPRSorterSimulationActor::BeginPlay()
{
    Super::BeginPlay();
    ClearCartInstances();
    // This actor is saved only in MPR; no registry or GHS default behavior changes.
    bReady=TowerMesh&&TrayMesh&&ParcelMaterial&&ActiveMaterial&&FullMaterial&&WorkerMesh&&WorkerIdle&&LoadLayout();
    if(!bReady) { Error=Error.IsEmpty()?TEXT("仿真资产或布局缺失"):Error;UE_LOG(LogTemp,Error,TEXT("MPR_SORTER: %s"),*Error);SetActorTickEnabled(false);return; }
    Towers->SetStaticMesh(TowerMesh);Trays->SetStaticMesh(TrayMesh);
    Parcels->SetMaterial(0,ParcelMaterial);InfeedParcels->SetMaterial(0,ParcelMaterial);BinParcels->SetMaterial(0,ParcelMaterial);
    ActiveLights->SetMaterial(0,ActiveMaterial);FullLights->SetMaterial(0,FullMaterial);
    // Retain serialized legacy components for map compatibility, but never draw
    // the old primitive workers alongside the official skeletal characters.
    for(auto* C:{WorkerCloth.Get(),WorkerSkin.Get(),WorkerHelmet.Get(),WorkerBoots.Get()})C->ClearInstances();
    ActiveLights->SetCastShadow(false);FullLights->SetCastShadow(false);
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    for(auto& M:Machines)
    {
        M.FeedOffset=InfeedParcels->GetInstanceCount();
        for(int32 I=0;I<M.Simulation.GetConfig().InfeedCapacity;++I)InfeedParcels->AddInstance(Hidden);
        for(int32 I=0;I<MPRSorter::CarrierCount;++I){Towers->AddInstance(Hidden);Trays->AddInstance(Hidden);Parcels->AddInstance(Hidden);}
        for(int32 I=0;I<M.Bins.Num();++I)
        {
            ActiveLights->AddInstance(Hidden);FullLights->AddInstance(Hidden);
            for(int32 J=0;J<BinCapacity;++J)BinParcels->AddInstance(Hidden);
        }
        M.Simulation.SetPlaying(bAutoStart);
    }
    if(!BuildCartInstances()||!BuildWorkers()){bReady=false;SetActorTickEnabled(false);UE_LOG(LogTemp,Error,TEXT("MPR_SORTER: %s"),*Error);return;}
    BuildCentralDistribution();SuppressLegacySpines();RefitCadWorktables();UpdateInstances();AttachPanel();
    UE_LOG(LogTemp,Display,TEXT("MPR_SORTER: ready, 22 machines, 96 removable carts, two shared distribution loops / six CAD operators, 1632 scene cells; demonstration data."));
}

bool AMPRSorterSimulationActor::BuildCartInstances(bool bEditorPreview)
{
    // Resolve the complete asset set before creating any components, so partial
    // editor property assignment cannot leave half a preview behind.
    TMap<FString,UStaticMesh*> Resolved;
    for(const auto& M:Machines)for(const auto& Cart:M.Carts)if(!Resolved.Contains(Cart.MeshPath))
    {
        UStaticMesh* Mesh=nullptr;
        for(const auto& Candidate:CartMeshes)if(Candidate)
        {
            const FString Path=Candidate->GetPathName();FString Package,Asset;Path.Split(TEXT("."),&Package,&Asset);
            if(Path==Cart.MeshPath||Package==Cart.MeshPath){Mesh=Candidate;break;}
        }
        if(!Mesh){Error=FString::Printf(TEXT("缺少料框车强引用：%s"),*Cart.MeshPath);return false;}
        Resolved.Add(Cart.MeshPath,Mesh);
    }
    TMap<FString,int32> Components;
    for(auto& M:Machines)for(auto& Cart:M.Carts)
    {
        int32 ComponentIndex=INDEX_NONE;
        if(const int32* Existing=Components.Find(Cart.MeshPath))ComponentIndex=*Existing;
        else
        {
            UStaticMesh* Mesh=Resolved.FindChecked(Cart.MeshPath);
            const FName BaseName(*FString::Printf(TEXT("RuntimeCart_%02d"),RuntimeCartComponents.Num()));
            const FName Name=MakeUniqueObjectName(this,UInstancedStaticMeshComponent::StaticClass(),BaseName);
            const EObjectFlags Flags=bEditorPreview?EObjectFlags(RF_Transient|RF_DuplicateTransient|RF_TextExportTransient):RF_Transient;
            auto* C=NewObject<UInstancedStaticMeshComponent>(this,Name,Flags);
            C->CreationMethod=EComponentCreationMethod::Instance;
            C->SetupAttachment(RootComponent);C->SetMobility(EComponentMobility::Movable);C->SetStaticMesh(Mesh);
            C->SetCollisionEnabled(ECollisionEnabled::NoCollision);C->SetGenerateOverlapEvents(false);
            C->SetCanEverAffectNavigation(false);C->bAffectDistanceFieldLighting=false;C->bAffectDynamicIndirectLighting=false;
            C->SetCastShadow(true);C->RegisterComponent();ComponentIndex=RuntimeCartComponents.Add(C);Components.Add(Cart.MeshPath,ComponentIndex);
        }
        Cart.ComponentIndex=ComponentIndex;
        Cart.InstanceIndex=RuntimeCartComponents[ComponentIndex]->AddInstance(FTransform(FQuat::Identity,Cart.Origin)*M.World,true);
    }
    return true;
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

FVector AMPRSorterSimulationActor::CartOffset(const FMachine& M,int32 Index) const
{
    const auto& C=M.Simulation.GetCarts()[size_t(Index)];const auto& P=M.Carts[Index];
    const double Side=P.Side==0?1.:-1.;const double T=FMath::Clamp(C.Progress01,0.,1.);
    const FVector Retreated(0,Side*P.Retreat,0),Exit(-M.InfeedSide*P.OutboundEndX-P.Origin.X,Side*P.Retreat,0);
    switch(C.State)
    {
    case MPRSorter::CartPhase::Withdrawing:return FMath::Lerp(FVector::ZeroVector,Retreated,T);
    case MPRSorter::CartPhase::Outbound:return FMath::Lerp(Retreated,Exit,T);
    case MPRSorter::CartPhase::Handoff:return Exit;
    case MPRSorter::CartPhase::EmptyArriving:return T<.7?FMath::Lerp(Exit,Retreated,T/.7):FMath::Lerp(Retreated,FVector::ZeroVector,(T-.7)/.3);
    default:return FVector::ZeroVector;
    }
}
FVector AMPRSorterSimulationActor::FeedPoint(const FMachine& M,double Progress) const
{return FMath::Lerp(M.FeedStart,M.Pickup,FMath::Clamp(Progress,0.,1.))+FVector(0,0,PackageSize.Z*.5+.3);}
FVector AMPRSorterSimulationActor::CarrierParcelPoint(const FMachine& M,const MPRSorter::Carrier& C,FQuat& Turn) const
{
    double Heading;FVector At=PointOnLoop(C.Distance01+M.LoadFraction,M.Half,M.Radius,Heading);At.Z=C.LiftHeightCm;
    Turn=FQuat(FVector::UpVector,Heading);
    FVector Parcel=At+FVector(0,0,PackageSize.Z*.5+.3);
    if(C.State==MPRSorter::CarrierPhase::Scan){Turn=FQuat(FVector::UpVector,M.InfeedSide*PI*.5);return FeedPoint(M,1);}
    if(C.State==MPRSorter::CarrierPhase::Induct)
    {
        const double T=FMath::Clamp(C.InductProgress,0.,1.);
        // The fixed powered connection supports the parcel throughout the
        // gap; the machine receives the same ID from the shared distributor.
        return FMath::Lerp(FeedPoint(M,1),Parcel,T);
    }
    if(C.State==MPRSorter::CarrierPhase::Unload)
    {
        const int32 Index=M.Simulation.BinIndex(C.Target);const auto& P=M.Bins[Index];
        const auto& B=M.Simulation.GetBins()[size_t(Index)];const double T=FMath::Clamp(C.UnloadProgress,0.,1.);
        const double Side=C.Target.Side==0?1.:-1.,Slope=FMath::DegreesToRadians(20.);
        const FVector Normal(0,Side*FMath::Sin(Slope),FMath::Cos(Slope));
        const FVector Entry=P.Entry+Normal*(PackageSize.Z*.5+.4),Outlet=P.Outlet+Normal*(PackageSize.Z*.5+.4);
        const FVector Above(P.Drop.X,P.Drop.Y,P.RimZ+PackageSize.Z*.5+1);
        const FVector Rest=P.Drop+FVector(0,0,PackageSize.Z*(B.Occupancy+.5)+.3);double Tilt=0;
        if(T<.35){const double F=T/.35;Tilt=F;Parcel=FMath::Lerp(Parcel,Entry,F)+FVector(0,0,1.5*FMath::Sin(PI*F));}
        else if(T<.65){Tilt=1;Parcel=FMath::Lerp(Entry,Outlet,(T-.35)/.30);}
        else if(T<.82){const double F=(T-.65)/.17;Tilt=1-F;Parcel=FMath::Lerp(Outlet,Above,F);}
        else Parcel=FMath::Lerp(Above,Rest,(T-.82)/.18);
        Turn=FQuat(FVector::ForwardVector,-Side*Slope*Tilt);
    }
    return Parcel;
}
void AMPRSorterSimulationActor::RefitCadWorktables()
{
    // The old GIE2 proxy used the complete CAD block bounds, including people
    // and floor symbols. Replace only source-matched game-world instances with
    // its two measured tabletops; preserve edited or unrelated worktables.
    RefittedCadWorktables=0;RefittedCadOperatorStations=0;
    if(!GetWorld()||!GetWorld()->IsGameWorld())return;
    TSet<int32> Matched,MatchedStations;
    for(TActorIterator<AActor> It(GetWorld());It;++It)
    {
        TArray<UInstancedStaticMeshComponent*> Components;It->GetComponents(Components);
        for(auto* C:Components)
        {
            if(!C->GetStaticMesh()||C->GetStaticMesh()->GetName()!=TEXT("SM_MPR_WorkTable"))continue;
            const int32 OriginalCount=C->GetInstanceCount();
            for(int32 I=0;I<OriginalCount;++I)
            {
                FTransform Old;if(!C->GetInstanceTransform(I,Old,true))continue;
                for(int32 J=0;J<UE_ARRAY_COUNT(MPRCadWorkers::WorkTables);++J)
                {
                    const auto& Table=MPRCadWorkers::WorkTables[J];
                    if(Matched.Contains(J)||!Old.GetLocation().Equals(FVector(Table.OldCenter[0],Table.OldCenter[1],Table.OldCenter[2]),.1)
                        ||!Old.GetScale3D().Equals(FVector(Table.OldScale[0],Table.OldScale[1],Table.OldScale[2]),.001)
                        ||FMath::Abs(FMath::FindDeltaAngleDegrees(Old.Rotator().Yaw,Table.OldYaw))>.01)continue;
                    for(int32 K=0;K<2;++K)
                    {
                        const FTransform Correct(FRotator(0,Table.Yaw[K],0),
                            FVector(Table.Centers[K][0],Table.Centers[K][1],Table.Centers[K][2]),
                            FVector(Table.SizeCm[0]/100.,Table.SizeCm[1]/120.,1.));
                        if(K==0)C->UpdateInstanceTransform(I,Correct,true,false,true);else C->AddInstance(Correct,true);
                    }
                    Matched.Add(J);++RefittedCadWorktables;break;
                }
                for(int32 J=0;J<UE_ARRAY_COUNT(MPRCadWorkers::OperatorStations);++J)
                {
                    const auto& Station=MPRCadWorkers::OperatorStations[J];
                    if(MatchedStations.Contains(J)||!Old.GetLocation().Equals(FVector(Station.OldCenter[0],Station.OldCenter[1],Station.OldCenter[2]),.1)
                        ||!Old.GetScale3D().Equals(FVector(Station.OldScale[0],Station.OldScale[1],Station.OldScale[2]),.001)
                        ||FMath::Abs(FMath::FindDeltaAngleDegrees(Old.Rotator().Yaw,Station.OldYaw))>.01)continue;
                    // PW_TG_96C_IN is L-shaped. Its enclosing block rectangle
                    // included the operator recess; only the side console is
                    // a desk. Preserve the CAD person's root and facing.
                    C->UpdateInstanceTransform(I,FTransform(FRotator(0,Station.ConsoleYaw,0),
                        FVector(Station.ConsoleCenter[0],Station.ConsoleCenter[1],Station.ConsoleCenter[2]),
                        FVector(Station.ConsoleSizeCm[0]/100.,Station.ConsoleSizeCm[1]/120.,1.)),true,false,true);
                    // The main envelope overlaps CAD hardware 2C9AE5/115C25,
                    // already represented by the distributor's return assembly.
                    // A second solid deck would cut through its moving columns.
                    MatchedStations.Add(J);++RefittedCadOperatorStations;break;
                }
            }
            C->MarkRenderStateDirty();
        }
    }
}

bool AMPRSorterSimulationActor::BuildWorkers()
{
    for(auto& C:RuntimeWorkers)if(C)C->DestroyComponent();
    RuntimeWorkers.Reset();CadWorkerIndices.Reset();
    auto AddWorker=[this]()
    {
        const FName Name(*FString::Printf(TEXT("MannyWorker_%02d"),RuntimeWorkers.Num()));
        auto* C=NewObject<UMPRWorkerPoseComponent>(this,Name,RF_Transient);
        C->CreationMethod=EComponentCreationMethod::Instance;C->SetupAttachment(RootComponent);
        C->RegisterComponent();RuntimeWorkers.Add(C);
        return C->InitializeWorker(WorkerMesh,WorkerIdle);
    };
    // One hidden exchange worker per machine; only the aisle owner is visible.
    // Six feed operators animate with the central loop; all other source CAD
    // personnel remain at their surveyed workstations, not at every sorter.
    for(auto& M:Machines){M.WorkerOffset=RuntimeWorkers.Num();if(!AddWorker())return false;}
    for(auto& B:DistributionBanks)for(auto& S:B.Stations)if(S.bManual)
    {S.WorkerIndex=RuntimeWorkers.Num();if(!AddWorker())return false;}
    for(const auto& Source:MPRCadWorkers::Workers)
    {
        if(Source.CentralFeed)
        {
            int32 Index=INDEX_NONE;
            for(const auto& B:DistributionBanks)for(const auto& S:B.Stations)
                if(S.bManual&&S.Feet.Equals(FVector(Source.Feet[0],Source.Feet[1],Source.Feet[2]),.1))Index=S.WorkerIndex;
            if(Index==INDEX_NONE){Error=TEXT("CAD 上料人员与中央工位不匹配");return false;}
            CadWorkerIndices.Add(Index);continue;
        }
        const int32 Index=RuntimeWorkers.Num();if(!AddWorker())return false;
        CadWorkerIndices.Add(Index);
        FMPRWorkerPoseInput Pose;
        const FVector Feet(Source.Feet[0],Source.Feet[1],Source.Feet[2]);
        const FQuat Turn=FRotator(0,Source.Yaw,0).Quaternion();
        Pose.BodyWorld=FTransform(Turn,Feet);Pose.GripAlpha=0;Pose.TorsoLeanDegrees=2;
        Pose.LeftPalmWorld=Feet+Turn.RotateVector(FVector(23,-18,103));
        Pose.RightPalmWorld=Feet+Turn.RotateVector(FVector(23,18,103));
        RuntimeWorkers[Index]->ApplyWorkerPose(Pose);
        // Fixed CAD staff do not need a per-frame bone solve.
        RuntimeWorkers[Index]->SetComponentTickEnabled(false);
    }
    return true;
}
void AMPRSorterSimulationActor::UpdateWorker(int32 Index,const FMachine& M,const FMPRWorkerPoseInput& Local)
{
    if(!RuntimeWorkers.IsValidIndex(Index))return;
    FMPRWorkerPoseInput World=Local;
    World.BodyWorld=Local.BodyWorld*M.World;
    World.LeftPalmWorld=M.World.TransformPosition(Local.LeftPalmWorld);
    World.RightPalmWorld=M.World.TransformPosition(Local.RightPalmWorld);
    World.MoveDirectionWorld=M.World.TransformVectorNoScale(Local.MoveDirectionWorld);
    World.SimulationTime=M.Simulation.GetStats().SimTime;
    RuntimeWorkers[Index]->ApplyWorkerPose(World);
}
void AMPRSorterSimulationActor::UpdateRingInstances()
{
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    TArray<FTransform> TowerTransforms,TrayTransforms,ParcelTransforms,InfeedTransforms;
    TArray<uint64> ParcelIds,InfeedIds;
    TowerTransforms.Reserve(Towers->GetInstanceCount());TrayTransforms.Reserve(Trays->GetInstanceCount());
    ParcelTransforms.Reserve(Parcels->GetInstanceCount());ParcelIds.Reserve(Parcels->GetInstanceCount());
    InfeedTransforms.Reserve(InfeedParcels->GetInstanceCount());InfeedIds.Reserve(InfeedParcels->GetInstanceCount());
    for(auto& M:Machines)
    {
        const auto& Queue=M.Simulation.GetInfeedQueue();
        check(InfeedTransforms.Num()==M.FeedOffset);
        for(int32 I=0;I<M.Simulation.GetConfig().InfeedCapacity;++I)
        {
            const auto Display=M.Simulation.GetPresentationInfeedParcel(size_t(I),FleetTimeRemainder);
            InfeedTransforms.Add(I<int32(Queue.size())?FTransform(FQuat(FVector::UpVector,M.InfeedSide*PI*.5),FeedPoint(M,Display.Progress01),PackageSize/100.)*M.World:Hidden);
            InfeedIds.Add(Display.ParcelId);
        }
        for(size_t I=0;I<M.Simulation.GetCarriers().size();++I)
        {
            const auto Carrier=M.Simulation.GetPresentationCarrier(I,FleetTimeRemainder);
            double Heading;FVector At=PointOnLoop(Carrier.Distance01+M.LoadFraction,M.Half,M.Radius,Heading);
            const FQuat Turn(FVector::UpVector,Heading);
            TowerTransforms.Add(FTransform(Turn,At)*M.World);
            At.Z=Carrier.LiftHeightCm;TrayTransforms.Add(FTransform(Turn,At)*M.World);
            if(Carrier.ParcelId)
            {
                FQuat ParcelTurn;const FVector Parcel=CarrierParcelPoint(M,Carrier,ParcelTurn);
                ParcelTransforms.Add(FTransform(ParcelTurn,Parcel,PackageSize/100.)*M.World);
            }
            else ParcelTransforms.Add(Hidden);
            ParcelIds.Add(Carrier.ParcelId);
        }
    }
    RingTowerHistory.Submit(Towers,TowerTransforms,GFrameCounter);
    RingTrayHistory.Submit(Trays,TrayTransforms,GFrameCounter);
    RingParcelHistory.Submit(Parcels,ParcelTransforms,GFrameCounter,ParcelIds);
    RingInfeedHistory.Submit(InfeedParcels,InfeedTransforms,GFrameCounter,InfeedIds);
}

void AMPRSorterSimulationActor::UpdateInstances()
{
    TRACE_CPUPROFILER_EVENT_SCOPE(MPRSorter_Presentation);
    UpdateRingInstances();
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    bool BinsChanged=false;
    for(auto& M:Machines)
    {
        const auto& Bins=M.Simulation.GetBins();const auto& Carts=M.Simulation.GetCarts();
        int32 MovingCart=INDEX_NONE;
        for(int32 I=0;I<M.Carts.Num();++I)
        {
            const auto& P=M.Carts[I];const auto& C=Carts[size_t(I)];const FVector Offset=CartOffset(M,I);
            const FVector CartScale=C.State==MPRSorter::CartPhase::Handoff?FVector::ZeroVector:FVector::OneVector;
            RuntimeCartComponents[P.ComponentIndex]->UpdateInstanceTransform(P.InstanceIndex,FTransform(FQuat::Identity,P.Origin+Offset,CartScale)*M.World,true,false,true);
            if(C.State!=MPRSorter::CartPhase::Receiving&&C.State!=MPRSorter::CartPhase::FullWaiting)MovingCart=I;
        }
        if(MovingCart==INDEX_NONE&&M.Simulation.IsExchangePermitted())for(int32 I=0;I<M.Carts.Num();++I)
            if(Carts[size_t(I)].State==MPRSorter::CartPhase::FullWaiting){MovingCart=I;break;}
        for(int32 I=0;I<M.Bins.Num();++I)
        {
            const auto& Bin=Bins[size_t(I)];const auto& Cart=Carts[size_t(Bin.CartId)];
            const int32 State=Bin.Occupancy+8*Bin.Reserved+256*int32(Cart.State);
            const bool Moving=Cart.State==MPRSorter::CartPhase::Withdrawing||Cart.State==MPRSorter::CartPhase::Outbound||Cart.State==MPRSorter::CartPhase::EmptyArriving;
            if(M.CachedBinState[I]==State&&!Moving)continue;
            M.CachedBinState[I]=State;BinsChanged=true;const int32 Slot=M.BinOffset+I;const auto& P=M.Bins[I];
            const FVector Offset=CartOffset(M,Bin.CartId);
            for(int32 J=0;J<BinCapacity;++J)
            {
                const FVector At=P.Drop+Offset+FVector(0,0,PackageSize.Z*(J+.5)+.3);
                BinParcels->UpdateInstanceTransform(Slot*BinCapacity+J,J<Bin.Occupancy&&Cart.State!=MPRSorter::CartPhase::Handoff?FTransform(FQuat::Identity,At,PackageSize/100.)*M.World:Hidden,true,false,true);
            }
            const FVector Signal=P.Outlet+FVector(0,0,3);const FTransform Light=FTransform(FQuat::Identity,Signal,FVector(.15,.04,.025))*M.World;
            const bool Docked=Cart.State==MPRSorter::CartPhase::Receiving||Cart.State==MPRSorter::CartPhase::FullWaiting;
            ActiveLights->UpdateInstanceTransform(Slot,Docked&&(Bin.Reserved>0||Bin.Occupancy>0)&&Bin.Occupancy<BinCapacity?Light:Hidden,true,false,true);
            FullLights->UpdateInstanceTransform(Slot,Bin.Occupancy>=BinCapacity?Light:Hidden,true,false,true);
        }
        auto Ease=[](double T){T=FMath::Clamp(T,0.,1.);return T*T*(3.-2.*T);};
        FMPRWorkerPoseInput Push;Push.bVisible=false;
        if(MovingCart!=INDEX_NONE&&Carts[size_t(MovingCart)].State!=MPRSorter::CartPhase::Handoff)
        {
            const auto& P=M.Carts[MovingCart];const auto& C=Carts[size_t(MovingCart)];const FVector Offset=CartOffset(M,MovingCart);
            const double Side=P.Side==0?1.:-1.,Outer=Side>0?P.BoundsMax.Y:-P.BoundsMin.Y;
            const FVector Body=P.Origin+Offset+FVector(0,Side*(Outer+20),0);
            const FVector Grip=P.Origin+Offset+FVector(0,Side*(Outer-2),105);
            Push.bVisible=true;Push.bPushGrip=true;Push.GripAlpha=1.;Push.TorsoLeanDegrees=8.;
            Push.BodyWorld=FTransform(FQuat(FVector::UpVector,-Side*PI*.5),Body);
            Push.LeftPalmWorld=Grip+FVector(-22*Side,0,0);Push.RightPalmWorld=Grip+FVector(22*Side,0,0);
            const double Along=FMath::Abs(-M.InfeedSide*P.OutboundEndX-P.Origin.X);
            if(C.State==MPRSorter::CartPhase::Withdrawing)
            {Push.bWalking=true;Push.TravelDistanceCm=P.Retreat*C.Progress01;Push.MoveDirectionWorld=FVector(0,Side,0);}
            else if(C.State==MPRSorter::CartPhase::Outbound)
            {Push.bWalking=true;Push.TravelDistanceCm=Along*C.Progress01;Push.MoveDirectionWorld=FVector(-M.InfeedSide,0,0);}
            else if(C.State==MPRSorter::CartPhase::EmptyArriving)
            {
                Push.bWalking=true;
                if(C.Progress01<.7){Push.TravelDistanceCm=Along*C.Progress01/.7;Push.MoveDirectionWorld=FVector(M.InfeedSide,0,0);}
                else{Push.TravelDistanceCm=P.Retreat*(C.Progress01-.7)/.3;Push.MoveDirectionWorld=FVector(0,-Side,0);}
            }
        }
        if(MovingCart!=INDEX_NONE)
        {
            const auto& Cart=Carts[size_t(MovingCart)];double T=Cart.Progress01;
            if(Cart.State==MPRSorter::CartPhase::EmptyArriving)T=T<.7?T/.7:(T-.7)/.3;
            Push.GaitBlend=Ease(T/.12)*Ease((1.-T)/.12);
        }
        UpdateWorker(M.WorkerOffset,M,Push);
    }
    UpdateCentralDistribution();
    for(auto& C:RuntimeCartComponents)C->MarkRenderStateDirty();
    if(BinsChanged)for(auto* C:{BinParcels.Get(),ActiveLights.Get(),FullLights.Get()})C->MarkRenderStateDirty();
}

void AMPRSorterSimulationActor::AttachPanel()
{
    if(Panel||!bReady)return;
    auto* PC=Cast<AGHSWarehousePlayerController>(UGameplayStatics::GetPlayerController(this,0));
    if(!PC||!PC->IsLocalController())return;
    Panel=CreateWidget<UMPRSorterHUDWidget>(PC,UMPRSorterHUDWidget::StaticClass());
    if(Panel){Panel->InitializeSorter(this);Panel->AddToViewport(80);Panel->SetDesiredSizeInViewport(FVector2D(360,390));Panel->SetPositionInViewport(FVector2D(20,80),false);}
}

void AMPRSorterSimulationActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);if(!bReady)return;
    AttachPanel();UpdateFocus();
    if(bAutomaticAdvance&&IsSimulationPlaying())
    { AdvanceFleet(DeltaSeconds);UpdateInstances(); }
    // A stopped presentation still submits a stationary frame, clearing the
    // last moving frame's velocity without advancing any simulation state.
    else {UpdateCentralDistribution();UpdateRingInstances();}
}
void AMPRSorterSimulationActor::ScheduleCartExchange()
{
    if(Machines.IsValidIndex(ExchangeOwner))
    {
        const auto& S=Machines[ExchangeOwner].Simulation;bool StillRequested=false;
        for(const auto& C:S.GetCarts())StillRequested|=(C.State!=MPRSorter::CartPhase::Receiving&&C.State!=MPRSorter::CartPhase::FullWaiting)
            ||(C.State==MPRSorter::CartPhase::FullWaiting&&(S.IsAutoCollectEnabled()||C.ExchangeRequested||C.Progress01>0));
        if(!StillRequested){NextExchangeMachine=(ExchangeOwner+1)%Machines.Num();ExchangeOwner=INDEX_NONE;}
    }
    if(Machines.IsValidIndex(ExchangeOwner)
       &&Machines[ExchangeOwner].Simulation.GetStats().ExchangedCarts!=OwnerCompletedExchanges)
    {
        NextExchangeMachine=(ExchangeOwner+1)%Machines.Num();ExchangeOwner=INDEX_NONE;
    }
    if(ExchangeOwner==INDEX_NONE)
    {
        for(int32 N=0;N<Machines.Num();++N)
        {
            const int32 Index=(NextExchangeMachine+N)%Machines.Num();const auto& S=Machines[Index].Simulation;
            bool Requested=false;for(const auto& C:S.GetCarts())
                Requested|=C.State==MPRSorter::CartPhase::FullWaiting&&(S.IsAutoCollectEnabled()||C.ExchangeRequested);
            if(Requested){ExchangeOwner=Index;OwnerCompletedExchanges=S.GetStats().ExchangedCarts;break;}
        }
    }
    // One entire cart trip owns the shared narrow aisle. Other machines may
    // continue receiving but cannot withdraw an opposing cart into this path.
    for(int32 I=0;I<Machines.Num();++I)Machines[I].Simulation.SetExchangePermit(I==ExchangeOwner);
}
bool AMPRSorterSimulationActor::AdvanceFleet(double WallSeconds)
{
    if(!FMath::IsFinite(WallSeconds)||WallSeconds<0||WallSeconds*GetSimulationRate()>86400)return false;
    // A common fixed simulation step keeps arrivals and machine acceptance
    // identical across frame rates and diagnostic fast-forward calls.
    if(!Machines[0].Simulation.IsPlaying())return true;
    constexpr double SimStep=MPRCentral::FleetStepSeconds;
    FleetTimeRemainder+=WallSeconds*GetSimulationRate();
    while(FleetTimeRemainder+1.e-10>=SimStep)
    {
        ScheduleCartExchange();
        for(auto& M:Machines)if(!M.Simulation.Advance(SimStep/M.Simulation.GetRate()))return false;
        if(!AdvanceCentralDistribution(SimStep))return false;
        FleetTimeRemainder=FMath::Max(0.,FleetTimeRemainder-SimStep);
    }
    ScheduleCartExchange();return true;
}
void AMPRSorterSimulationActor::EndPlay(const EEndPlayReason::Type Reason)
{ if(Panel){Panel->RemoveFromParent();Panel=nullptr;}Super::EndPlay(Reason); }
bool AMPRSorterSimulationActor::IsSimulationPlaying() const { return bReady&&Machines[0].Simulation.IsPlaying(); }
bool AMPRSorterSimulationActor::IsAutomaticCollection() const { return bReady&&Machines[0].Simulation.IsAutoCollectEnabled(); }
double AMPRSorterSimulationActor::GetSimulationRate() const { return bReady?Machines[0].Simulation.GetRate():1.; }
void AMPRSorterSimulationActor::SetSimulationPlaying(bool Playing) { for(auto& M:Machines)M.Simulation.SetPlaying(Playing);for(auto& B:DistributionBanks)B.Simulation.SetPlaying(Playing); }
void AMPRSorterSimulationActor::ResetSimulation()
{
    CentralColumnHistory.Reset();CentralTrayHistory.Reset();CentralParcelHistory.Reset();
    RingTowerHistory.Reset();RingTrayHistory.Reset();RingParcelHistory.Reset();RingInfeedHistory.Reset();
    FleetTimeRemainder=0;NextCentralParcelId=1;
    for(auto& B:DistributionBanks)B.Simulation.Reset();
    ExchangeOwner=INDEX_NONE;NextExchangeMachine=0;OwnerCompletedExchanges=0;
    for(auto& M:Machines){M.Simulation.Reset();M.CachedBinState.Init(INDEX_NONE,M.Bins.Num());}
    ScheduleCartExchange();if(bReady)UpdateInstances();
}
void AMPRSorterSimulationActor::SetSimulationRate(double Rate){for(auto& M:Machines)M.Simulation.SetRate(Rate);}
void AMPRSorterSimulationActor::SetAutomaticCollection(bool Enabled){for(auto& M:Machines)M.Simulation.SetAutoCollect(Enabled);}
void AMPRSorterSimulationActor::ClearFullBins()
{
    if(!Machines.IsValidIndex(SelectedMachine))return;
    auto& S=Machines[SelectedMachine].Simulation;
    for(const auto& C:S.GetCarts())if(C.State==MPRSorter::CartPhase::FullWaiting)S.RequestCartExchange(C.Index);
    if(bReady)UpdateInstances();
}
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
{if(!Diagnostics()||!bReady||!AdvanceFleet(Seconds))return false;UpdateInstances();return true;}
FString AMPRSorterSimulationActor::GetRingMotionDiagnostics() const
{
    if(!Diagnostics()||!bReady)return TEXT("{}");
    auto Root=MakeShared<FJsonObject>();
    Root->SetNumberField(TEXT("visual_residual_seconds"),FleetTimeRemainder);
    Root->SetNumberField(TEXT("sim_time"),Machines[0].Simulation.GetStats().SimTime);
    Root->SetNumberField(TEXT("visual_time"),Machines[0].Simulation.GetStats().SimTime+FleetTimeRemainder);
    TArray<TSharedPtr<FJsonValue>> Rows;
    for(int32 Index=0;Index<Machines.Num();++Index)
    {
        const auto& M=Machines[Index];const auto& Config=M.Simulation.GetConfig();const auto& Stats=M.Simulation.GetStats();
        auto Row=MakeShared<FJsonObject>();Row->SetNumberField(TEXT("index"),Index);Row->SetStringField(TEXT("id"),M.Id);
        Row->SetBoolField(TEXT("chain_stopped"),Stats.ChainStopped);Row->SetNumberField(TEXT("sim_time"),Stats.SimTime);
        Row->SetNumberField(TEXT("speed_cm_s"),Config.ChainSpeedCmS);Row->SetNumberField(TEXT("loop_length_cm"),Config.LoopLengthCm);
        Row->SetNumberField(TEXT("half_cm"),M.Half);Row->SetNumberField(TEXT("radius_cm"),M.Radius);Row->SetNumberField(TEXT("load_fraction"),M.LoadFraction);
        TArray<TSharedPtr<FJsonValue>> Carriers;
        for(size_t I=0;I<M.Simulation.GetCarriers().size();++I)
        {
            const auto& C=M.Simulation.GetCarriers()[I];const auto Display=M.Simulation.GetPresentationCarrier(I,FleetTimeRemainder);
            auto Item=MakeShared<FJsonObject>();Item->SetNumberField(TEXT("state_code"),int32(C.State));
            Item->SetNumberField(TEXT("distance01"),C.Distance01);Item->SetNumberField(TEXT("visual_distance01"),Display.Distance01);
            Item->SetNumberField(TEXT("visual_height_cm"),Display.LiftHeightCm);Item->SetNumberField(TEXT("parcel_id"),double(C.ParcelId));
            Item->SetNumberField(TEXT("target_distance01"),C.State==MPRSorter::CarrierPhase::EmptyReturn?0.:
                Config.DestinationDistances01[size_t(C.Target.Side*Config.Columns+C.Target.Column)]);
            Carriers.Add(MakeShared<FJsonValueObject>(Item));
        }
        Row->SetArrayField(TEXT("carriers"),Carriers);Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("machines"),Rows);
    FString Result;FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Result));return Result;
}
FString AMPRSorterSimulationActor::GetMachineTitle() const
{if(!bReady)return Error;return FString::Printf(TEXT("木马 %02d / %d · %d 格口 · %d 车"),SelectedMachine+1,Machines.Num(),Machines[SelectedMachine].Bins.Num(),Machines[SelectedMachine].Carts.Num());}
FString AMPRSorterSimulationActor::GetStatusText() const
{if(!bReady)return Error;return FString::Printf(TEXT("%s · %.0f× · %s"),IsSimulationPlaying()?TEXT("运行中"):TEXT("已暂停"),GetSimulationRate(),*ReasonName(Machines[SelectedMachine].Simulation.GetStats().Reason));}
FString AMPRSorterSimulationActor::GetProgressText() const
{
    if(!bReady)return TEXT("初始化中");const auto& S=Machines[SelectedMachine].Simulation.GetStats();int32 Occupied=0,Full=0;
    for(const auto& C:Machines[SelectedMachine].Simulation.GetCarts()){Occupied+=C.Occupancy;Full+=C.State==MPRSorter::CartPhase::FullWaiting;}
    return FString::Printf(TEXT("来货排队 %d   搬运中 %d   已入箱 %llu\n当前车载 %d   已转出 %llu   换车 %llu\n满车待换 %d   演示时间 %.1f s"),S.Queued,S.Active,static_cast<unsigned long long>(S.Completed),Occupied,static_cast<unsigned long long>(S.Collected),static_cast<unsigned long long>(S.ExchangedCarts),Full,S.SimTime);
}
FString AMPRSorterSimulationActor::GetCarrierText() const
{
    if(!bReady)return TEXT("");
    for(const auto& C:Machines[SelectedMachine].Simulation.GetCarts())if(C.State!=MPRSorter::CartPhase::Receiving)
        return FString::Printf(TEXT("%s侧 %d号料框车 · %s · %d/%d件"),C.Side==0?TEXT("A"):TEXT("B"),C.Index+1,*CartPhaseName(C.State),C.Occupancy,C.Capacity);
    for(const auto& C:Machines[SelectedMachine].Simulation.GetCarriers())if(C.ParcelId)
        return FString::Printf(TEXT("包裹 %04llu → %s侧 %02d列 %d层 · %s"),static_cast<unsigned long long>(C.ParcelId),C.Target.Side==0?TEXT("A"):TEXT("B"),C.Target.Column+1,C.Target.Level+1,*PhaseName(C.State));
    return TEXT("空载回环 · 等待上包");
}

FString AMPRSorterSimulationActor::GetSimulationReportJson() const
{
    auto Root=MakeShared<FJsonObject>();Root->SetBoolField(TEXT("ready"),bReady);Root->SetStringField(TEXT("error"),Error);
    Root->SetStringField(TEXT("data_mode"),TEXT("demonstration"));Root->SetNumberField(TEXT("schema_version"),2);
    Root->SetNumberField(TEXT("machine_count"),Machines.Num());Root->SetBoolField(TEXT("playing"),IsSimulationPlaying());
    Root->SetNumberField(TEXT("rate"),GetSimulationRate());Root->SetBoolField(TEXT("automatic_collection"),IsAutomaticCollection());
    Root->SetNumberField(TEXT("selected_machine"),SelectedMachine);Root->SetNumberField(TEXT("components"),18+RuntimeCartComponents.Num()+RuntimeWorkers.Num());
    Root->SetNumberField(TEXT("tower_instances"),Towers->GetInstanceCount());Root->SetNumberField(TEXT("tray_instances"),Trays->GetInstanceCount());
    Root->SetNumberField(TEXT("parcel_instances"),Parcels->GetInstanceCount());Root->SetNumberField(TEXT("infeed_instances"),InfeedParcels->GetInstanceCount());
    Root->SetNumberField(TEXT("worker_slots"),RuntimeWorkers.Num());Root->SetNumberField(TEXT("bin_parcel_instances"),BinParcels->GetInstanceCount());
    Root->SetNumberField(TEXT("cad_worker_count"),CadWorkerIndices.Num());
    Root->SetNumberField(TEXT("refitted_cad_worktables"),RefittedCadWorktables);
    Root->SetNumberField(TEXT("refitted_cad_operator_stations"),RefittedCadOperatorStations);
    Root->SetBoolField(TEXT("panel_attached"),Panel!=nullptr);
    auto Ids=[](const std::vector<uint64_t>& Values)
    {TArray<TSharedPtr<FJsonValue>> Result;for(uint64_t Id:Values)Result.Add(MakeShared<FJsonValueNumber>(double(Id)));return Result;};
    auto Transform=[](const FTransform& T)
    {
        auto Result=MakeShared<FJsonObject>();Result->SetArrayField(TEXT("translation_cm"),XYZ(T.GetLocation()));
        Result->SetArrayField(TEXT("scale"),XYZ(T.GetScale3D()));const FQuat Q=T.GetRotation();
        Result->SetArrayField(TEXT("rotation_xyzw"),{MakeShared<FJsonValueNumber>(Q.X),MakeShared<FJsonValueNumber>(Q.Y),MakeShared<FJsonValueNumber>(Q.Z),MakeShared<FJsonValueNumber>(Q.W)});return Result;
    };
    if(Diagnostics())
    {
        TArray<TSharedPtr<FJsonValue>> CadWorkers;
        for(int32 I=0;I<CadWorkerIndices.Num();++I)
        {
            const auto& Source=MPRCadWorkers::Workers[I];auto Row=MakeShared<FJsonObject>();
            Row->SetNumberField(TEXT("worker_index"),CadWorkerIndices[I]);
            Row->SetStringField(TEXT("source_handle"),UTF8_TO_TCHAR(Source.SourceHandle));
            Row->SetArrayField(TEXT("feet_cm"),XYZ(FVector(Source.Feet[0],Source.Feet[1],Source.Feet[2])));
            Row->SetNumberField(TEXT("yaw_deg"),Source.Yaw);Row->SetBoolField(TEXT("central_feed"),Source.CentralFeed);
            CadWorkers.Add(MakeShared<FJsonValueObject>(Row));
        }
        Root->SetArrayField(TEXT("cad_workers"),CadWorkers);
        TArray<TSharedPtr<FJsonValue>> Workers;
        for(int32 I=0;I<RuntimeWorkers.Num();++I)
        {
            const auto* C=RuntimeWorkers[I].Get();auto Row=MakeShared<FJsonObject>();
            Row->SetNumberField(TEXT("index"),I);Row->SetBoolField(TEXT("visible"),C->IsVisible());
            Row->SetBoolField(TEXT("ready"),C->IsWorkerPoseReady());Row->SetNumberField(TEXT("bone_count"),C->GetNumBones());
            Row->SetStringField(TEXT("mesh"),C->GetSkinnedAsset()->GetPathName());
            Row->SetObjectField(TEXT("transform"),Transform(C->GetComponentTransform()));
            Row->SetArrayField(TEXT("left_palm"),XYZ(C->GetPalmWorld(true)));Row->SetArrayField(TEXT("right_palm"),XYZ(C->GetPalmWorld(false)));
            Row->SetArrayField(TEXT("left_sole"),XYZ(C->GetFootSoleWorld(true)));Row->SetArrayField(TEXT("right_sole"),XYZ(C->GetFootSoleWorld(false)));
            Row->SetNumberField(TEXT("left_error_cm"),C->GetPalmContactErrorCm(true));Row->SetNumberField(TEXT("right_error_cm"),C->GetPalmContactErrorCm(false));
            Row->SetNumberField(TEXT("limb_length_error_cm"),C->GetMaximumLimbLengthErrorCm());
            Workers.Add(MakeShared<FJsonValueObject>(Row));
        }
        Root->SetArrayField(TEXT("skeletal_workers"),Workers);
        Root->SetNumberField(TEXT("legacy_worker_instances"),WorkerCloth->GetInstanceCount()+WorkerSkin->GetInstanceCount()+WorkerHelmet->GetInstanceCount()+WorkerBoots->GetInstanceCount());
    }
    TArray<TSharedPtr<FJsonValue>> Rows;uint64 Spawned=0,Completed=0,Collected=0,Exchanges=0;int32 Active=0,Occupancy=0,Queued=0,CartCount=0;
    bool Unique=true;int32 ActiveExchanges=0,WaitingExchanges=0;
    for(const auto& M:Machines)
    {
        const auto& S=M.Simulation.GetStats();auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("id"),M.Id);Row->SetStringField(TEXT("profile"),M.Profile);
        Row->SetNumberField(TEXT("sim_time"),S.SimTime);Row->SetNumberField(TEXT("last_induct_completed_time"),S.LastInductCompletedTime);Row->SetNumberField(TEXT("phase"),S.ChainPhase01);
        Row->SetNumberField(TEXT("visual_time"),S.SimTime+FleetTimeRemainder);Row->SetNumberField(TEXT("visual_residual_seconds"),FleetTimeRemainder);
        Row->SetNumberField(TEXT("spawned"),double(S.Spawned));Row->SetNumberField(TEXT("completed"),double(S.Completed));
        Row->SetNumberField(TEXT("collected"),double(S.Collected));Row->SetNumberField(TEXT("active"),S.Active);Row->SetNumberField(TEXT("queued"),S.Queued);
        Row->SetNumberField(TEXT("exchanged_carts"),double(S.ExchangedCarts));Row->SetNumberField(TEXT("load_fraction"),M.LoadFraction);
        Row->SetNumberField(TEXT("infeed_side_local_x"),M.InfeedSide);Row->SetArrayField(TEXT("pickup_world_cm"),XYZ(M.World.TransformPosition(M.Pickup)));
        Row->SetArrayField(TEXT("entry_world_cm"),XYZ(M.World.TransformPosition(M.Entry)));
        Row->SetStringField(TEXT("transfer_mode"),TEXT("central_distribution_powered_connection"));Row->SetStringField(TEXT("block_reason"),ReasonName(S.Reason));
        Row->SetBoolField(TEXT("chain_stopped"),S.ChainStopped);int32 Count=0,Full=0;TSet<uint64> Seen;
        Row->SetBoolField(TEXT("exchange_permitted"),M.Simulation.IsExchangePermitted());
        auto Own=[&Seen,&Unique](uint64 Id){if(!Id||Seen.Contains(Id))Unique=false;else Seen.Add(Id);};
        TArray<TSharedPtr<FJsonValue>> Feed;
        for(size_t FeedIndex=0;FeedIndex<M.Simulation.GetInfeedQueue().size();++FeedIndex)
        {
            const auto& P=M.Simulation.GetInfeedQueue()[FeedIndex];const auto Display=M.Simulation.GetPresentationInfeedParcel(FeedIndex,FleetTimeRemainder);
            Own(P.ParcelId);auto Item=MakeShared<FJsonObject>();Item->SetNumberField(TEXT("parcel_id"),double(P.ParcelId));
            Item->SetNumberField(TEXT("progress01"),P.Progress01);Item->SetNumberField(TEXT("visual_progress01"),Display.Progress01);
            Item->SetArrayField(TEXT("world_cm"),XYZ(M.World.TransformPosition(FeedPoint(M,Display.Progress01))));
            Feed.Add(MakeShared<FJsonValueObject>(Item));
        }
        Row->SetArrayField(TEXT("infeed"),Feed);
        TArray<TSharedPtr<FJsonValue>> Cells;
        for(const auto& B:M.Simulation.GetBins())
        {
            Count+=B.Occupancy;Full+=B.Occupancy>=B.Capacity;for(uint64 Id:B.ParcelIds)Own(Id);
            if(B.Occupancy||B.Reserved)
            {
                auto Cell=MakeShared<FJsonObject>();Cell->SetNumberField(TEXT("side"),B.Target.Side);Cell->SetNumberField(TEXT("column"),B.Target.Column);
                Cell->SetNumberField(TEXT("level"),B.Target.Level);Cell->SetNumberField(TEXT("cart_index"),B.CartId);
                Cell->SetNumberField(TEXT("occupancy"),B.Occupancy);Cell->SetNumberField(TEXT("reserved"),B.Reserved);Cell->SetArrayField(TEXT("parcel_ids"),Ids(B.ParcelIds));
                Cells.Add(MakeShared<FJsonValueObject>(Cell));
            }
        }
        Row->SetNumberField(TEXT("occupancy"),Count);Row->SetNumberField(TEXT("full_bins"),Full);Row->SetArrayField(TEXT("cells"),Cells);
        TArray<TSharedPtr<FJsonValue>> Carriers;
        for(size_t CarrierIndex=0;CarrierIndex<M.Simulation.GetCarriers().size();++CarrierIndex)
        {
            const auto& C=M.Simulation.GetCarriers()[CarrierIndex];const auto Display=M.Simulation.GetPresentationCarrier(CarrierIndex,FleetTimeRemainder);
            if(C.ParcelId)Own(C.ParcelId);auto Item=MakeShared<FJsonObject>();Item->SetNumberField(TEXT("parcel_id"),double(C.ParcelId));
            Item->SetStringField(TEXT("state"),PhaseName(C.State));Item->SetNumberField(TEXT("state_code"),int32(C.State));
            Item->SetNumberField(TEXT("distance01"),C.Distance01);Item->SetNumberField(TEXT("lift_cm"),C.LiftHeightCm);
            Item->SetNumberField(TEXT("visual_distance01"),Display.Distance01);Item->SetNumberField(TEXT("visual_height_cm"),Display.LiftHeightCm);
            Item->SetNumberField(TEXT("visual_scan_progress"),Display.ScanProgress);Item->SetNumberField(TEXT("visual_induct_progress"),Display.InductProgress);
            Item->SetNumberField(TEXT("visual_unload_progress"),Display.UnloadProgress);
            Item->SetNumberField(TEXT("scan_progress"),C.ScanProgress);Item->SetNumberField(TEXT("induct_progress"),C.InductProgress);
            Item->SetNumberField(TEXT("unload_progress"),C.UnloadProgress);Item->SetNumberField(TEXT("target_cart"),C.TargetCartIndex);
            Item->SetNumberField(TEXT("target_cart_generation"),double(C.TargetCartGeneration));
            Item->SetNumberField(TEXT("side"),C.Target.Side);Item->SetNumberField(TEXT("column"),C.Target.Column);Item->SetNumberField(TEXT("level"),C.Target.Level);
            double Heading;FVector Point=PointOnLoop(Display.Distance01+M.LoadFraction,M.Half,M.Radius,Heading);Point.Z=Display.LiftHeightCm;
            Item->SetArrayField(TEXT("tray_world_cm"),XYZ(M.World.TransformPosition(Point)));
            if(C.ParcelId){FQuat Turn;Item->SetArrayField(TEXT("parcel_world_cm"),XYZ(M.World.TransformPosition(CarrierParcelPoint(M,Display,Turn))));}
            Carriers.Add(MakeShared<FJsonValueObject>(Item));
        }
        Row->SetArrayField(TEXT("carriers"),Carriers);TArray<TSharedPtr<FJsonValue>> Carts;
        for(int32 I=0;I<M.Carts.Num();++I)
        {
            const auto& P=M.Carts[I];const auto& C=M.Simulation.GetCarts()[size_t(I)];auto Item=MakeShared<FJsonObject>();
            ActiveExchanges+=C.State!=MPRSorter::CartPhase::Receiving&&C.State!=MPRSorter::CartPhase::FullWaiting;
            WaitingExchanges+=C.State==MPRSorter::CartPhase::FullWaiting;
            Item->SetNumberField(TEXT("index"),C.Index);Item->SetNumberField(TEXT("side"),C.Side);Item->SetNumberField(TEXT("first_column"),C.FirstColumn);
            Item->SetNumberField(TEXT("column_count"),C.ColumnCount);Item->SetNumberField(TEXT("generation"),double(C.Generation));
            Item->SetStringField(TEXT("state"),CartPhaseName(C.State));Item->SetNumberField(TEXT("state_code"),int32(C.State));
            const bool Visible=C.State!=MPRSorter::CartPhase::Handoff;
            Item->SetBoolField(TEXT("visible"),Visible);
            Item->SetStringField(TEXT("physical_cart_id"),FString::Printf(TEXT("%s/cart-%d/generation-%llu"),*M.Id,C.Index,static_cast<unsigned long long>(C.Generation)));
            Item->SetNumberField(TEXT("progress01"),C.Progress01);Item->SetNumberField(TEXT("occupancy"),C.Occupancy);
            Item->SetNumberField(TEXT("capacity"),C.Capacity);Item->SetNumberField(TEXT("reserved"),C.Reserved);Item->SetNumberField(TEXT("collected"),double(C.Collected));
            Item->SetArrayField(TEXT("parcel_ids"),Ids(C.ParcelIds));Item->SetArrayField(TEXT("last_outbound_parcel_ids"),Ids(C.LastOutboundParcelIds));
            Item->SetStringField(TEXT("mesh"),P.MeshPath);Item->SetArrayField(TEXT("local_offset_cm"),XYZ(CartOffset(M,I)));
            Item->SetObjectField(TEXT("world_transform"),Transform(FTransform(FQuat::Identity,P.Origin+CartOffset(M,I))*M.World));
            Item->SetObjectField(TEXT("render_world_transform"),Transform(FTransform(FQuat::Identity,P.Origin+CartOffset(M,I),Visible?FVector::OneVector:FVector::ZeroVector)*M.World));
            Carts.Add(MakeShared<FJsonValueObject>(Item));
        }
        Row->SetArrayField(TEXT("carts"),Carts);Rows.Add(MakeShared<FJsonValueObject>(Row));CartCount+=M.Carts.Num();
        Spawned+=S.Spawned;Completed+=S.Completed;Collected+=S.Collected;Active+=S.Active;Occupancy+=Count;Queued+=S.Queued;Exchanges+=S.ExchangedCarts;
    }
    Root->SetArrayField(TEXT("machines"),Rows);Root->SetNumberField(TEXT("cart_count"),CartCount);Root->SetNumberField(TEXT("spawned"),double(Spawned));
    Root->SetNumberField(TEXT("completed"),double(Completed));Root->SetNumberField(TEXT("collected"),double(Collected));Root->SetNumberField(TEXT("active"),Active);
    Root->SetNumberField(TEXT("queued"),Queued);Root->SetNumberField(TEXT("occupancy"),Occupancy);Root->SetNumberField(TEXT("exchanged_carts"),double(Exchanges));
    Root->SetBoolField(TEXT("conserved"),Spawned==Completed+Active+Queued&&Completed==Collected+Occupancy);
    Root->SetBoolField(TEXT("unique_parcel_ownership"),Unique);
    Root->SetNumberField(TEXT("active_exchange_count"),ActiveExchanges);Root->SetNumberField(TEXT("waiting_exchange_count"),WaitingExchanges);
    Root->SetNumberField(TEXT("exchange_owner_machine"),ExchangeOwner);Root->SetBoolField(TEXT("shared_aisle_mutex_valid"),ActiveExchanges<=1);
    AppendCentralReport(Root);
    FString Result;FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Result));return Result;
}
