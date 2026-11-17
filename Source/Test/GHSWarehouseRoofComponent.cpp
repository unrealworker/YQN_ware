#include "GHSWarehouseRoofComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Materials/MaterialInterface.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

namespace
{
constexpr const TCHAR* SourceNames[]={TEXT("M_GHSRoof_Roof"),TEXT("M_GHSRoof_Seams"),
    TEXT("M_GHSRoof_Blue"),TEXT("M_GHSRoof_Skylight"),TEXT("M_GHSRoof_Detail"),TEXT("M_GHSFacade_Glass")};
constexpr const TCHAR* MPRSourceNames[]={TEXT("M_MPR4_PBRSolid"),TEXT("M_MPR4_PBRTextured"),
    TEXT("M_MPRH_SolarCells"),TEXT("M_MPRH_SolarCellsLight"),TEXT("M_MPRH_SolarCellsShade"),TEXT("M_MPRH_SolarFrame")};

// SourceAssets/GHS/MainRoof/roof_manifest.json: exact CAD outline, including
// the southwest office extension and southeast diagonal. Mesh-local cm.
const FVector2D Outline[]={
    FVector2D(22665.055,-6049.019),FVector2D(-23958.385,-6049.019),
    FVector2D(-23958.385,7716.981),FVector2D(-19321.145,7716.981),
    FVector2D(-19321.145,5888.181),FVector2D(20158.2115,5888.181),
    FVector2D(22665.055,5193.3623)};

// SourceAssets/MPR/mpr_cad_layout.json, CAD metres mirrored to UE centimetres.
const FVector2D MPROutline[]={
    {-18193.004,-8369.038},{-16608.044,-8369.038},{-16608.044,-7454.638},
    {16678.656,-7454.638},{16678.656,-8358.878},{18261.076,-8358.878},
    {18261.076,2050.042},{16678.656,2050.042},{16678.656,5098.042},
    {15091.156,5098.042},{15091.156,6622.042},{13536.676,6622.042},
    {13536.676,8394.962},{-16608.044,8394.962},{-16608.044,9309.362},{-18193.004,9309.362}};

template <SIZE_T N>
bool ContainsPoint(const FVector2D& P,const FVector2D (&Points)[N])
{
    bool Inside=false;
    for(int32 I=0,J=N-1;I<N;J=I++)
    {
        const FVector2D A=Points[I],B=Points[J];
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
        DissolveTemplates.Add(TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(Path)));
    }
    for(const TCHAR* SourceName:MPRSourceNames)
    {
        const FString Name=FString(TEXT("M_Scan_"))+SourceName;
        const FString Path=FString(TEXT("/Game/MPRWarehouse/Roof/ScanReveal/"))+Name+TEXT(".")+Name;
        DissolveTemplates.Add(TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(Path)));
    }
}

void UGHSWarehouseRoofComponent::BeginPlay()
{
    Super::BeginPlay();
    if(!bDeferWorldInitialization)InitializeRoof();
}

void UGHSWarehouseRoofComponent::InitializeRoof()
{
    if(!GetWorld()) return;
    if(!bShellInitialized)
    {
        bShellInitialized=true;
        for(TActorIterator<AActor> It(GetWorld());It;++It)
        {
            if(It->ActorHasTag(TEXT("GHS_WarehouseRoof")) || It->ActorHasTag(TEXT("MPR_Roof"))) continue;
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
    RoofParts.Empty();RoofMesh=nullptr;bMPRRoof=false;
    bool bHasGHSRoof=false;
    for(TActorIterator<AActor> It(GetWorld());It;++It)
        bHasGHSRoof|=It->ActorHasTag(TEXT("GHS_WarehouseRoof"));
    // Existing performance captures intentionally exclude interaction and HUD setup.
    if(!bHasGHSRoof && FParse::Param(FCommandLine::Get(),TEXT("MPRProfile"))) return;
    bMPRRoof=!bHasGHSRoof;
    const FName Tag=bMPRRoof?TEXT("MPR_Roof"):TEXT("GHS_WarehouseRoof");
    for(TActorIterator<AActor> It(GetWorld());It;++It)
    {
        if(!It->ActorHasTag(Tag)) continue;
        TInlineComponentArray<UStaticMeshComponent*> Meshes(*It);
        for(UStaticMeshComponent* Mesh:Meshes)
        {
            if(!Mesh || !Mesh->GetStaticMesh()) continue;
            auto& Part=RoofParts.AddDefaulted_GetRef();
            Part.Actor=*It;Part.Mesh=Mesh;
            Part.bActorHidden=It->IsHidden();Part.bMeshVisible=Mesh->IsVisible();Part.bMeshHidden=Mesh->bHiddenInGame;
            Part.bCastShadow=Mesh->CastShadow;Part.bCastHiddenShadow=Mesh->bCastHiddenShadow;
            Part.bAffectDistanceFieldLighting=Mesh->bAffectDistanceFieldLighting;
            Part.bAffectDynamicIndirectLighting=Mesh->bAffectDynamicIndirectLighting;
            Part.bAffectIndirectLightingWhileHidden=Mesh->bAffectIndirectLightingWhileHidden;
            Part.bVisibleInRayTracing=Mesh->bVisibleInRayTracing;
            Part.ShadowCacheInvalidationBehavior=Mesh->ShadowCacheInvalidationBehavior;
            for(int32 Slot=0;Slot<Mesh->GetNumMaterials();++Slot) Part.SourceMaterials.Add(Mesh->GetMaterial(Slot));
            if(!bMPRRoof || Mesh->GetStaticMesh()->GetName()==TEXT("SM_MPR4_RoofSkin_00")) RoofMesh=Mesh;
        }
    }
    // A tagged roof device alone must not turn unrelated geometry into a building.
    if(!RoofMesh) {RoofParts.Empty();bMPRRoof=false;return;}
    RestoreRoof(false);
}

bool UGHSWarehouseRoofComponent::HasRoof() const
{
    return IsValid(RoofMesh) && RoofMesh->GetStaticMesh()!=nullptr && !RoofParts.IsEmpty();
}

void UGHSWarehouseRoofComponent::SetRoofHidden(bool bHidden)
{
    for(auto& Part:RoofParts) if(IsValid(Part.Actor) && IsValid(Part.Mesh))
    {
        Part.Actor->SetActorHiddenInGame(Part.bActorHidden || bHidden);
        Part.Mesh->SetVisibility(Part.bMeshVisible);
        Part.Mesh->SetHiddenInGame(Part.bMeshHidden);
    }
}

void UGHSWarehouseRoofComponent::UpdateRoofLighting()
{
    const bool bClosed=Transition.IsClosed();
    for(auto& Part:RoofParts) if(IsValid(Part.Mesh))
    {
        auto* Mesh=Part.Mesh.Get();
        // Distance fields and cached Lumen cards describe the uncut mesh, not
        // this frame's scan mask. Exclude only the roof from these occluders
        // until fully closed; normal raster shadows still follow the mask.
        Mesh->SetAffectDistanceFieldLighting(bClosed && Part.bAffectDistanceFieldLighting);
        Mesh->SetAffectDynamicIndirectLighting(bClosed && Part.bAffectDynamicIndirectLighting);
        Mesh->SetAffectIndirectLightingWhileHidden(bClosed && Part.bAffectIndirectLightingWhileHidden);
        Mesh->SetVisibleInRayTracing(bClosed && Part.bVisibleInRayTracing);
        Mesh->SetCastHiddenShadow(bClosed && Part.bCastHiddenShadow);
        Mesh->SetCastShadow(!Transition.IsOpen() && Part.bCastShadow);
        // Auto only knows transform/WPO changes. Our opacity-only MID scan
        // needs per-frame shadow invalidation during the short transition.
        const auto CacheBehavior=Transition.IsTransitioning()?EShadowCacheInvalidationBehavior::Always:
            Part.ShadowCacheInvalidationBehavior;
        if(Mesh->ShadowCacheInvalidationBehavior!=CacheBehavior)
        {
            Mesh->ShadowCacheInvalidationBehavior=CacheBehavior;
            Mesh->MarkRenderStateDirty();
        }
    }
}

bool UGHSWarehouseRoofComponent::OpenRoof(bool bFast)
{
    if(!HasRoof()) InitializeRoof();
    if(!HasRoof()) return false;
    if(Transition.IsOpen()) return true;
    // Do not start an MPR reveal with an unresolved material: that would leave
    // opaque pieces floating above the interior until the end of the animation.
    if(!ApplyDissolveMaterials()) return false;
    Transition.Open(bFast);
    UpdateRoofLighting();
    if(Transition.IsOpen())
    {
        SetRoofHidden(true);
        RestoreSourceMaterials();
        UpdateShellVisibility();
        SetComponentTickEnabled(false);
        return true;
    }
    UpdateDissolveMaterials();
    SetRoofHidden(false);
    UpdateShellVisibility();
    SetComponentTickEnabled(true);
    return true;
}

bool UGHSWarehouseRoofComponent::ApplyDissolveMaterials()
{
    if(!HasRoof()) return false;
    bool bComplete=true;
    for(auto& Part:RoofParts)
    {
        if(!IsValid(Part.Mesh)) continue;
        if(Part.DissolveInstances.IsEmpty())
        {
            for(UMaterialInterface* Source:Part.SourceMaterials)
            {
                UMaterialInterface* Template=nullptr;
                const FString SourceName=Source && Source->GetMaterial()?Source->GetMaterial()->GetName():FString();
                const FString TemplateName=TEXT("M_Scan_")+SourceName;
                FString TemplatePath=TemplateName;
                for(const auto& Candidate:DissolveTemplates)
                    if(Candidate.GetAssetName()==TemplateName)
                    {
                        TemplatePath=Candidate.ToSoftObjectPath().ToString();
                        Template=Candidate.LoadSynchronous();
                        break;
                    }
                if(!Template)
                    UE_LOG(LogTemp,Warning,TEXT("Roof reveal material unavailable: source='%s', template='%s'. Check the ScanReveal cook directories."),
                        *GetPathNameSafe(Source),*TemplatePath);
                Part.DissolveInstances.Add(Template?UMaterialInstanceDynamic::Create(Template,this):nullptr);
            }
        }
        for(UMaterialInstanceDynamic* Instance:Part.DissolveInstances) bComplete&=IsValid(Instance);
    }
    if(bMPRRoof && !bComplete)
    {
        UE_LOG(LogTemp,Warning,TEXT("MPR roof reveal requires all source-matched scan materials"));
        for(auto& Part:RoofParts) Part.DissolveInstances.Empty();
        return false;
    }
    for(auto& Part:RoofParts) if(IsValid(Part.Mesh))
        for(int32 Slot=0;Slot<Part.DissolveInstances.Num();++Slot)
        {
            UMaterialInstanceDynamic* Instance=Part.DissolveInstances[Slot];
            if(!Instance) continue;
            if(Part.SourceMaterials.IsValidIndex(Slot) && Part.SourceMaterials[Slot])
                Instance->CopyMaterialUniformParameters(Part.SourceMaterials[Slot]);
            Part.Mesh->SetMaterial(Slot,Instance);
        }
    return true;
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
    for(auto& Part:RoofParts) if(IsValid(Part.Mesh))
        for(int32 Slot=0;Slot<Part.SourceMaterials.Num();++Slot) Part.Mesh->SetMaterial(Slot,Part.SourceMaterials[Slot]);
}

void UGHSWarehouseRoofComponent::RestoreRoof(bool bAnimate)
{
    Transition.Restore(bAnimate && HasRoof());
    UpdateRoofLighting();
    UpdateShellVisibility();
    SetComponentTickEnabled(Transition.IsTransitioning());
    if(!HasRoof()) return;
    if(Transition.IsTransitioning())
    {
        ApplyDissolveMaterials();
        UpdateDissolveMaterials();
    }
    else RestoreSourceMaterials();
    SetRoofHidden(false);
}

void UGHSWarehouseRoofComponent::TickComponent(float DeltaTime,ELevelTick TickType,FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime,TickType,ThisTickFunction);
    if(!HasRoof()) { RestoreRoof(false); return; }
    if(!Transition.IsTransitioning()) { SetComponentTickEnabled(false); return; }
    Transition.Advance(DeltaTime);
    UpdateRoofLighting();
    UpdateDissolveMaterials();
    if(Transition.IsOpen())
    {
        SetRoofHidden(true);
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

FBox UGHSWarehouseRoofComponent::GetRoofWorldBounds() const
{
    FBox Bounds(ForceInit);
    for(const auto& Part:RoofParts) if(IsValid(Part.Mesh) && Part.Mesh->GetStaticMesh())
    {
        // Devices and solar panels must not shift the building label or scan axis.
        if(bMPRRoof && !Part.Mesh->GetStaticMesh()->GetName().StartsWith(TEXT("SM_MPR4_RoofSkin_"))) continue;
        Bounds+=Part.Mesh->GetStaticMesh()->GetBoundingBox().TransformBy(Part.Mesh->GetComponentTransform());
    }
    return Bounds;
}

void UGHSWarehouseRoofComponent::UpdateDissolveMaterials()
{
    if(!HasRoof()) return;
    const FBox Bounds=RoofMesh->GetStaticMesh()->GetBoundingBox();
    const FTransform Transform=RoofMesh->GetComponentTransform();
    const FVector LocalAxis=Bounds.GetExtent().X>=Bounds.GetExtent().Y?FVector::ForwardVector:FVector::RightVector;
    FVector Axis=Transform.TransformVector(LocalAxis).GetSafeNormal();
    double HalfExtent=Transform.TransformVector(LocalAxis*(Bounds.GetExtent()|LocalAxis)).Length();
    FVector Center=Transform.TransformPosition(Bounds.GetCenter());
    if(bMPRRoof)
    {
        const FBox Building=GetRoofWorldBounds();
        Axis=FVector::ForwardVector;HalfExtent=Building.GetExtent().X;Center=Building.GetCenter();
    }
    for(const auto& Part:RoofParts) for(UMaterialInstanceDynamic* Instance:Part.DissolveInstances)
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
    if(bMPRRoof)
    {
        const FBox Bounds=GetRoofWorldBounds();
        FVector Point=Bounds.GetCenter();Point.Z=Bounds.Max.Z+20.;return Point;
    }
    const FBox Bounds=RoofMesh->GetStaticMesh()->GetBoundingBox();
    FVector Point=Bounds.GetCenter();Point.Z=Bounds.Max.Z+20.;
    return RoofMesh->GetComponentTransform().TransformPosition(Point);
}

bool UGHSWarehouseRoofComponent::HitRoofRay(const FVector& Origin,const FVector& Direction) const
{
    if(!HasRoof() || Transition.IsOpen()) return false;
    return bMPRRoof?RayHitsMPRRoofFootprint(Origin,Direction,RoofMesh->GetComponentTransform()):
                    RayHitsRoofFootprint(Origin,Direction,RoofMesh->GetComponentTransform());
}

bool UGHSWarehouseRoofComponent::RayHitsMPRRoofFootprint(const FVector& Origin,const FVector& Direction,const FTransform& RoofTransform)
{
    if(Origin.ContainsNaN() || Direction.ContainsNaN() || Direction.IsNearlyZero()) return false;
    const FVector O=RoofTransform.InverseTransformPosition(Origin),D=RoofTransform.InverseTransformVector(Direction);
    if(FMath::Abs(D.Z)<UE_SMALL_NUMBER) return false;
    const double T=(1340.-O.Z)/D.Z;
    if(T<0. || !FMath::IsFinite(T)) return false;
    const FVector P=O+D*T;
    return ContainsPoint(FVector2D(P.X,P.Y),MPROutline);
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
        return P.Y>=MinY && P.Y<=MaxY && ContainsPoint(FVector2D(P.X,P.Y),Outline);
    };
    return HitPlane(Slope,1040.-Slope*RidgeY,LowY,RidgeY)
        || HitPlane(-Slope,1040.+Slope*RidgeY,RidgeY,HighY)
        || HitPlane(0.,976.,-DBL_MAX,LowY)
        || HitPlane(0.,976.,HighY,DBL_MAX);
}

void UGHSWarehouseRoofComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    ResetForWorld();
    Super::EndPlay(EndPlayReason);
}

void UGHSWarehouseRoofComponent::ResetForWorld()
{
    RestoreRoof(false);
    for(const auto& Entry:ShellActors) if(Entry.Actor.IsValid()) Entry.Actor->SetActorHiddenInGame(Entry.bOriginallyHidden);
    ShellActors.Empty();bShellInitialized=false;bBuildingVisible=true;
    RoofMesh=nullptr;RoofParts.Empty();bMPRRoof=false;
    Transition=FGHSWarehouseRoofTransition();SetComponentTickEnabled(false);
}

FGHSWarehouseRoofReplayState UGHSWarehouseRoofComponent::CaptureReplayState()
{
    FGHSWarehouseRoofReplayState Saved;Saved.Transition=Transition;Saved.TickEnabled=IsComponentTickEnabled();
    for(auto& Entry:ShellActors) if(Entry.Actor.IsValid())
    {
        // A visible building layer lets us distinguish a manual override from the layer's hide.
        if(bBuildingVisible) Entry.bOriginallyHidden=Entry.Actor->IsHidden();
        Saved.Shells.Add({Entry.Actor,Entry.Actor->IsHidden(),Entry.bOriginallyHidden});
    }
    Saved.HasRoofVisibility=HasRoof();
    for(const auto& Part:RoofParts) if(IsValid(Part.Actor) && IsValid(Part.Mesh))
        Saved.Roofs.Add({Part.Actor,Part.Mesh,Part.Actor->IsHidden(),Part.Mesh->IsVisible(),Part.Mesh->bHiddenInGame != 0});
    if(!Saved.Roofs.IsEmpty())
    {Saved.RoofHidden=Saved.Roofs[0].ActorHidden;Saved.MeshVisible=Saved.Roofs[0].MeshVisible;Saved.MeshHidden=Saved.Roofs[0].MeshHidden;}
    return Saved;
}

void UGHSWarehouseRoofComponent::RestoreReplayState(const FGHSWarehouseRoofReplayState& Saved,bool bSavedBuilding)
{
    Transition=Saved.Transition;bBuildingVisible=bSavedBuilding;
    if(HasRoof())
    {
        UpdateRoofLighting();
        SetRoofHidden(Transition.IsOpen());
        if(Transition.IsTransitioning()) {ApplyDissolveMaterials();UpdateDissolveMaterials();}
        else RestoreSourceMaterials();
        for(const auto& State:Saved.Roofs) if(State.Actor.IsValid() && State.Mesh.IsValid())
        {
            State.Actor->SetActorHiddenInGame(State.ActorHidden);
            State.Mesh->SetVisibility(State.MeshVisible);State.Mesh->SetHiddenInGame(State.MeshHidden);
        }
    }
    for(const auto& State:Saved.Shells) if(State.Actor.IsValid())
    {
        for(auto& Entry:ShellActors) if(Entry.Actor==State.Actor) {Entry.bOriginallyHidden=State.OriginalHidden;break;}
        State.Actor->SetActorHiddenInGame(State.Hidden);
    }
    SetComponentTickEnabled(Saved.TickEnabled);
}
