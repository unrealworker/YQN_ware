#include "GHSWarehouseRoofComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Materials/MaterialInterface.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
constexpr const TCHAR* SourceNames[]={TEXT("M_GHSRoof_Roof"),TEXT("M_GHSRoof_Seams"),
    TEXT("M_GHSRoof_Blue"),TEXT("M_GHSRoof_Skylight"),TEXT("M_GHSRoof_Detail"),TEXT("M_GHSFacade_Glass")};

// SourceAssets/GHS/MainRoof/roof_manifest.json: exact CAD outline, including
// the southwest office extension and southeast diagonal. Mesh-local cm.
const FVector2D Outline[]={
    FVector2D(22665.055,-6049.019),FVector2D(-23958.385,-6049.019),
    FVector2D(-23958.385,7716.981),FVector2D(-19321.145,7716.981),
    FVector2D(-19321.145,5888.181),FVector2D(20158.2115,5888.181),
    FVector2D(22665.055,5193.3623)};

bool ContainsRoofPoint(const FVector2D& P)
{
    bool Inside=false;
    for(int32 I=0,J=UE_ARRAY_COUNT(Outline)-1;I<UE_ARRAY_COUNT(Outline);J=I++)
    {
        const FVector2D A=Outline[I],B=Outline[J];
        if((A.Y>P.Y)!=(B.Y>P.Y) && P.X<(B.X-A.X)*(P.Y-A.Y)/(B.Y-A.Y)+A.X) Inside=!Inside;
    }
    return Inside;
}
}

UGHSWarehouseRoofComponent::UGHSWarehouseRoofComponent()
{
    PrimaryComponentTick.bCanEverTick=true;
    PrimaryComponentTick.bStartWithTickEnabled=false;
    for(const TCHAR* SourceName:SourceNames)
    {
        const FString Name=FString(TEXT("M_Scan_"))+SourceName;
        const FString Path=FString(TEXT("/Game/GHSZcoolSmartFactory/Roof/ScanReveal/"))+Name+TEXT(".")+Name;
        ConstructorHelpers::FObjectFinderOptional<UMaterialInterface> Material(*Path);
        DissolveTemplates.Add(Material.Get());
    }
}

void UGHSWarehouseRoofComponent::BeginPlay()
{
    Super::BeginPlay();
    InitializeRoof();
}

void UGHSWarehouseRoofComponent::InitializeRoof()
{
    if(!GetWorld()) return;
    if(!bShellInitialized)
    {
        bShellInitialized=true;
        for(TActorIterator<AActor> It(GetWorld());It;++It)
        {
            if(It->ActorHasTag(TEXT("GHS_WarehouseRoof"))) continue;
            bool bShell=It->ActorHasTag(TEXT("GHS_OfficeFacade")) || It->ActorHasTag(TEXT("ZcoolSequentialDockNumber"));
            TInlineComponentArray<UStaticMeshComponent*> Meshes(*It);
            for(auto* Mesh:Meshes) if(Mesh->GetStaticMesh())
            {
                const FString Name=Mesh->GetStaticMesh()->GetName();
                bShell|=Name.StartsWith(TEXT("SM_GHS_V2Exterior")) || Name==TEXT("SM_GHS_V2DockDoor");
            }
            if(bShell) ShellActors.Add({*It,It->IsHidden()});
        }
    }
    if(HasRoof()) return;
    for(TActorIterator<AActor> It(GetWorld());It;++It)
    {
        if(!It->ActorHasTag(TEXT("GHS_WarehouseRoof"))) continue;
        UStaticMeshComponent* Mesh=It->FindComponentByClass<UStaticMeshComponent>();
        if(!Mesh || !Mesh->GetStaticMesh()) continue;
        RoofActor=*It;
        RoofMesh=Mesh;
        SourceMaterials.Reset();
        DissolveInstances.Reset();
        for(int32 Slot=0;Slot<Mesh->GetNumMaterials();++Slot) SourceMaterials.Add(Mesh->GetMaterial(Slot));
        RestoreRoof(false);
        return;
    }
}

bool UGHSWarehouseRoofComponent::HasRoof() const
{
    return IsValid(RoofActor) && IsValid(RoofMesh) && RoofMesh->GetStaticMesh()!=nullptr;
}

bool UGHSWarehouseRoofComponent::OpenRoof(bool bFast)
{
    if(!HasRoof()) InitializeRoof();
    if(!HasRoof()) return false;
    if(Transition.IsOpen()) return true;
    Transition.Open(bFast);
    if(Transition.IsOpen())
    {
        RoofActor->SetActorHiddenInGame(true);
        RestoreSourceMaterials();
        UpdateShellVisibility();
        SetComponentTickEnabled(false);
        return true;
    }
    ApplyDissolveMaterials();
    UpdateDissolveMaterials();
    RoofActor->SetActorHiddenInGame(false);
    RoofMesh->SetVisibility(true,true);
    UpdateShellVisibility();
    SetComponentTickEnabled(true);
    return true;
}

void UGHSWarehouseRoofComponent::ApplyDissolveMaterials()
{
    if(!HasRoof()) return;
    if(DissolveInstances.IsEmpty())
    {
        for(UMaterialInterface* Source:SourceMaterials)
        {
            UMaterialInterface* Template=nullptr;
            const FString SourceName=Source && Source->GetMaterial()?Source->GetMaterial()->GetName():FString();
            for(int32 I=0;I<UE_ARRAY_COUNT(SourceNames);++I)
                if(SourceName==SourceNames[I] && DissolveTemplates.IsValidIndex(I)) Template=DissolveTemplates[I];
            UMaterialInstanceDynamic* Instance=Template?UMaterialInstanceDynamic::Create(Template,this):nullptr;
            DissolveInstances.Add(Instance);
        }
    }
    for(int32 Slot=0;Slot<DissolveInstances.Num();++Slot)
    {
        UMaterialInstanceDynamic* Instance=DissolveInstances[Slot];
        if(!Instance) continue;
        if(SourceMaterials.IsValidIndex(Slot) && SourceMaterials[Slot])
            Instance->CopyMaterialUniformParameters(SourceMaterials[Slot]);
        RoofMesh->SetMaterial(Slot,Instance);
    }
}

void UGHSWarehouseRoofComponent::SetBuildingVisible(bool bVisible)
{
    bBuildingVisible=bVisible;
    if(!bShellInitialized) InitializeRoof();
    if(!bVisible) OpenRoof();
    UpdateShellVisibility();
}
void UGHSWarehouseRoofComponent::UpdateShellVisibility()
{
    const bool bHide=!bBuildingVisible && IsInteriorAvailable();
    for(const auto& Entry:ShellActors) if(Entry.Actor.IsValid())
        Entry.Actor->SetActorHiddenInGame(Entry.bOriginallyHidden || bHide);
}

void UGHSWarehouseRoofComponent::RestoreSourceMaterials()
{
    if(!RoofMesh) return;
    for(int32 Slot=0;Slot<SourceMaterials.Num();++Slot) RoofMesh->SetMaterial(Slot,SourceMaterials[Slot]);
}

void UGHSWarehouseRoofComponent::RestoreRoof(bool bAnimate)
{
    Transition.Restore(bAnimate && HasRoof());
    UpdateShellVisibility();
    SetComponentTickEnabled(Transition.IsTransitioning());
    if(!HasRoof()) return;
    if(Transition.IsTransitioning())
    {
        ApplyDissolveMaterials();
        UpdateDissolveMaterials();
    }
    else RestoreSourceMaterials();
    RoofActor->SetActorHiddenInGame(false);
    RoofMesh->SetVisibility(true,true);
}

void UGHSWarehouseRoofComponent::TickComponent(float DeltaTime,ELevelTick TickType,FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime,TickType,ThisTickFunction);
    if(!HasRoof()) { RestoreRoof(false); return; }
    if(!Transition.IsTransitioning()) { SetComponentTickEnabled(false); return; }
    Transition.Advance(DeltaTime);
    UpdateDissolveMaterials();
    if(Transition.IsOpen())
    {
        RoofActor->SetActorHiddenInGame(true);
        UpdateShellVisibility();
        RestoreSourceMaterials();
        SetComponentTickEnabled(false);
    }
    else if(Transition.IsClosed())
    {
        RestoreSourceMaterials();
        UpdateShellVisibility();
        SetComponentTickEnabled(false);
    }
}

void UGHSWarehouseRoofComponent::UpdateDissolveMaterials()
{
    if(!HasRoof()) return;
    const FBox Bounds=RoofMesh->GetStaticMesh()->GetBoundingBox();
    const FTransform Transform=RoofMesh->GetComponentTransform();
    const FVector LocalAxis=Bounds.GetExtent().X>=Bounds.GetExtent().Y?FVector::ForwardVector:FVector::RightVector;
    const FVector Axis=Transform.TransformVector(LocalAxis).GetSafeNormal();
    const double HalfExtent=Transform.TransformVector(LocalAxis*(Bounds.GetExtent()|LocalAxis)).Length();
    const FVector Center=Transform.TransformPosition(Bounds.GetCenter());
    for(UMaterialInstanceDynamic* Instance:DissolveInstances)
    {
        if(!Instance) continue;
        Instance->SetScalarParameterValue(TEXT("RoofOpenProgress"),Transition.Progress());
        Instance->SetVectorParameterValue(TEXT("RoofCenter"),FLinearColor(Center.X,Center.Y,Center.Z,0));
        Instance->SetVectorParameterValue(TEXT("RoofAxisInvExtent"),FLinearColor(Axis.X,Axis.Y,Axis.Z,1.f/FMath::Max(1.,HalfExtent)));
    }
}

FVector UGHSWarehouseRoofComponent::GetPOIWorldLocation() const
{
    if(!HasRoof()) return FVector::ZeroVector;
    const FBox Bounds=RoofMesh->GetStaticMesh()->GetBoundingBox();
    FVector Point=Bounds.GetCenter();Point.Z=Bounds.Max.Z+20.;
    return RoofMesh->GetComponentTransform().TransformPosition(Point);
}

bool UGHSWarehouseRoofComponent::HitRoofRay(const FVector& Origin,const FVector& Direction) const
{
    return HasRoof() && !Transition.IsOpen() && RayHitsRoofFootprint(Origin,Direction,RoofMesh->GetComponentTransform());
}

bool UGHSWarehouseRoofComponent::RayHitsRoofFootprint(const FVector& Origin,const FVector& Direction,const FTransform& RoofTransform)
{
    if(Origin.ContainsNaN() || Direction.ContainsNaN() || Direction.IsNearlyZero()) return false;
    const FVector O=RoofTransform.InverseTransformPosition(Origin);
    const FVector D=RoofTransform.InverseTransformVector(Direction);
    // Intersect the actual two pitched planes plus flat office/overhang
    // surfaces, using the exact outline rather than its rectangular bounds.
    constexpr double RidgeY=-80.419, LowY=-6024.019, HighY=5863.181;
    constexpr double Slope=64./5943.6;
    const auto HitPlane=[&](double A,double B,double MinY,double MaxY)
    {
        // Roof plane Z = A * Y + B; D is deliberately not renormalized after
        // inverse transform, so nonuniform actor scaling preserves the ray.
        const double Denom=D.Z-A*D.Y;
        if(FMath::Abs(Denom)<UE_SMALL_NUMBER) return false;
        const double T=(A*O.Y+B-O.Z)/Denom;
        if(T<0. || !FMath::IsFinite(T)) return false;
        const FVector P=O+D*T;
        return P.Y>=MinY && P.Y<=MaxY && ContainsRoofPoint(FVector2D(P.X,P.Y));
    };
    return HitPlane(Slope,1040.-Slope*RidgeY,LowY,RidgeY)
        || HitPlane(-Slope,1040.+Slope*RidgeY,RidgeY,HighY)
        || HitPlane(0.,976.,-DBL_MAX,LowY)
        || HitPlane(0.,976.,HighY,DBL_MAX);
}

void UGHSWarehouseRoofComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    RestoreRoof(false);
    for(const auto& Entry:ShellActors) if(Entry.Actor.IsValid()) Entry.Actor->SetActorHiddenInGame(Entry.bOriginallyHidden);
    Super::EndPlay(EndPlayReason);
}
