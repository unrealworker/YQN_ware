#include "GHSMannedForkliftIdentityLibrary.h"
#include "GHSMannedForkliftDataComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/WorldSettings.h"

namespace
{
    const TCHAR* TypeTag=TEXT("NormalWarehouseMannedForklift");
    const FString TwinPrefix=TEXT("TwinId=GHN_MannedForklift_");
    const FString OwnerPrefix=TEXT("GHSManualIdentityOwner=");
    const FString HighWaterPrefix=TEXT("GHSManualIdentityHighWater=");

    bool ParseNumber(const FString& Text,int32& Number)
    {
        if (Text.IsEmpty()) return false;
        int32 Value=0;
        for (const TCHAR C : Text)
        {
            if (C<TEXT('0') || C>TEXT('9')) return false;
            const int32 Digit=C-TEXT('0');
            if (Value>(MAX_int32-Digit)/10) return false;
            Value=Value*10+Digit;
        }
        if (Value<1) return false;
        Number=Value;
        return true;
    }
    struct FWorldIdentityState
    {
        int32 HighWater=0;
        TMap<int32,TWeakObjectPtr<AActor>> Owners;
    };
    TMap<TWeakObjectPtr<UWorld>,FWorldIdentityState> WorldStates;
    struct FCandidate
    {
        AActor* Actor=nullptr;
        UGHSMannedForkliftDataComponent* Data=nullptr;
        int32 Number=0;
        bool bOwnerMatches=false;
        bool bCopiedOwnerMarker=false;
        bool bBoundComponent=false;
    };

    bool IsApprovedActor(AActor* Actor)
    {
        // An ISM/HISM host or another assembly is never one logical vehicle.
        const auto* StaticActor=Cast<AStaticMeshActor>(Actor);
        const auto* Component=StaticActor?StaticActor->GetStaticMeshComponent():nullptr;
        const UStaticMesh* Mesh=Component?Component->GetStaticMesh().Get():nullptr;
        return IsValid(Actor) && !Actor->IsActorBeingDestroyed() && Mesh
            && Mesh->GetPathName()==UGHSMannedForkliftIdentityLibrary::GetApprovedMeshPath();
    }
    void MarkChanged(AActor* Actor,UWorld* World)
    {
        if (World->WorldType==EWorldType::Editor)
        {
            Actor->Modify();
            Actor->MarkPackageDirty();
        }
    }
}

const TCHAR* UGHSMannedForkliftIdentityLibrary::GetApprovedMeshPath()
{
    return TEXT("/Game/GHSNormalWarehouse/MannedForklift/Meshes/SM_GHN_MannedForklift50k.SM_GHN_MannedForklift50k");
}

bool UGHSMannedForkliftIdentityLibrary::IsSupportedActor(AActor* Actor)
{
    return IsApprovedActor(Actor);
}

int32 UGHSMannedForkliftIdentityLibrary::ReconcileWorld(UObject* WorldContextObject)
{
    UWorld* World=WorldContextObject?WorldContextObject->GetWorld():nullptr;
    if (!World) return 0;
    TArray<AActor*> Actors;
    for (TActorIterator<AActor> It(World); It; ++It) Actors.Add(*It);
    return ReconcileActors(World,Actors);
}

int32 UGHSMannedForkliftIdentityLibrary::ReconcileActors(UWorld* World,const TArray<AActor*>& Actors)
{
    if (!World) return 0;
    for (auto It=WorldStates.CreateIterator(); It; ++It)
        if (!It.Key().IsValid()) It.RemoveCurrent();
    FWorldIdentityState& State=WorldStates.FindOrAdd(World);
    AWorldSettings* Settings=World->GetWorldSettings();
    if (Settings)
        for (const FName Tag : Settings->Tags)
        {
            const FString Text=Tag.ToString();
            int32 Number=0;
            if (Text.StartsWith(HighWaterPrefix,ESearchCase::CaseSensitive)
                && ParseNumber(Text.Mid(HighWaterPrefix.Len()),Number)) State.HighWater=FMath::Max(State.HighWater,Number);
        }

    TArray<FCandidate> Candidates;
    TSet<AActor*> Seen;
    // First reserve every legitimate own-prefix identity, independent of discovery order.
    for (AActor* Actor : Actors)
    {
        if (!IsValid(Actor) || Actor->GetWorld()!=World || Seen.Contains(Actor)) continue;
        Seen.Add(Actor);
        bool bForeignIdentity=false;
        int32 OwnTagCount=0,Number=0;
        for (const FName Tag : Actor->Tags)
        {
            const FString Text=Tag.ToString();
            if (!Text.StartsWith(TEXT("TwinId="),ESearchCase::CaseSensitive)) continue;
            if (!Text.StartsWith(TwinPrefix,ESearchCase::CaseSensitive)) { bForeignIdentity=true; continue; }
            ++OwnTagCount;
            int32 Parsed=0;
            if (ParseNumber(Text.Mid(TwinPrefix.Len()),Parsed))
            {
                State.HighWater=FMath::Max(State.HighWater,Parsed);
                Number=Parsed;
            }
        }
        if (!IsApprovedActor(Actor) || bForeignIdentity) continue;
        FCandidate& Candidate=Candidates.AddDefaulted_GetRef();
        Candidate.Actor=Actor;
        Candidate.Number=OwnTagCount==1?Number:0;
        Candidate.Data=Actor->FindComponentByClass<UGHSMannedForkliftDataComponent>();
        Candidate.bOwnerMatches=Actor->Tags.Contains(FName(*(OwnerPrefix+Actor->GetName())));
        Candidate.bCopiedOwnerMarker=!Candidate.bOwnerMatches && Actor->Tags.ContainsByPredicate(
            [](const FName Tag) { return Tag.ToString().StartsWith(OwnerPrefix,ESearchCase::CaseSensitive); });
        if (Candidate.Data && Candidate.Number>0)
        {
            const FString Id=FString::Printf(TEXT("FORK-%02d"),Candidate.Number);
            Candidate.bBoundComponent=Candidate.Data->IsIdentityBoundToOwner() && Candidate.Data->ForkliftId==Id;
        }
    }
    Candidates.Sort([](const FCandidate& A,const FCandidate& B)
        { return A.Actor->GetPathName().Compare(B.Actor->GetPathName(),ESearchCase::CaseSensitive)<0; });

    TMap<int32,int32> Winners;
    auto Rank=[&](const FCandidate& C)
    {
        const auto* Bound=State.Owners.Find(C.Number);
        if (Bound && Bound->IsValid() && Bound->Get()==C.Actor) return 3;
        if (C.bBoundComponent) return 2;
        if (C.bOwnerMatches) return 1;
        return 0;
    };
    for (int32 Index=0; Index<Candidates.Num(); ++Index)
    {
        const FCandidate& Candidate=Candidates[Index];
        if (Candidate.Number<=0) continue;
        int32* Winner=Winners.Find(Candidate.Number);
        if (!Winner) Winners.Add(Candidate.Number,Index);
        else if (Rank(Candidate)>Rank(Candidates[*Winner])) *Winner=Index;
    }

    int32 ChangedActors=0;
    for (int32 Index=0; Index<Candidates.Num(); ++Index)
    {
        FCandidate& Candidate=Candidates[Index];
        const int32* Winner=Winners.Find(Candidate.Number);
        const bool bNeedsNewIdentity=Candidate.Number<=0 || !Winner || *Winner!=Index;
        if (bNeedsNewIdentity)
        {
            if (State.HighWater==MAX_int32)
            {
                UE_LOG(LogTemp,Warning,TEXT("Manual forklift ID space exhausted; leaving %s unchanged"),*Candidate.Actor->GetPathName());
                continue;
            }
            Candidate.Number=++State.HighWater;
        }
        AActor* Actor=Candidate.Actor;
        TArray<FName> UpdatedTags=Actor->Tags;
        if (bNeedsNewIdentity)
        {
            UpdatedTags.RemoveAll([](const FName Tag) { return Tag.ToString().StartsWith(TwinPrefix,ESearchCase::CaseSensitive); });
            UpdatedTags.Add(FName(*FString::Printf(TEXT("TwinId=GHN_MannedForklift_%02d"),Candidate.Number)));
        }
        UpdatedTags.AddUnique(FName(TypeTag));
        UpdatedTags.RemoveAll([](const FName Tag) { return Tag.ToString().StartsWith(OwnerPrefix,ESearchCase::CaseSensitive); });
        UpdatedTags.Add(FName(*(OwnerPrefix+Actor->GetName())));
        const bool bTagsChanged=UpdatedTags!=Actor->Tags;
        if (bTagsChanged)
        {
            MarkChanged(Actor,World);
            Actor->Tags=MoveTemp(UpdatedTags);
            ++ChangedActors;
        }
        const FString CanonicalId=FString::Printf(TEXT("FORK-%02d"),Candidate.Number);
        // A user may already have fixed a clone's tag before discovery. Its component can
        // still contain the source vehicle's identity and accepted live telemetry.
        const bool bHasComponentIdentity=Candidate.Data && !Candidate.Data->ForkliftId.IsEmpty();
        const bool bStaleComponentIdentity=bHasComponentIdentity && Candidate.Data->ForkliftId!=CanonicalId;
        // UE duplication clears Transient acceptance/ownership flags but retains the public
        // telemetry payload. The copied nonempty identity plus foreign owner marker is the
        // reliable signal; do not rely on bHasAcceptedUpdate surviving serialization.
        const bool bCopiedTelemetry=bHasComponentIdentity && Candidate.bCopiedOwnerMarker
            && !Candidate.Data->IsIdentityBoundToOwner();
        if (Candidate.Data && ((bNeedsNewIdentity && bHasComponentIdentity) || bStaleComponentIdentity || bCopiedTelemetry))
        {
            if (!bTagsChanged) { MarkChanged(Actor,World); ++ChangedActors; }
            if (World->WorldType==EWorldType::Editor) Candidate.Data->Modify();
            Candidate.Data->ResetForReassignedIdentity(CanonicalId);
        }
        else if (Candidate.Data)
        {
            // A real update can arrive before first discovery assigns this vehicle an ID.
            // Binding that initially empty identity must not erase its accepted telemetry.
            if (Candidate.Data->ForkliftId!=CanonicalId)
            {
                if (!bTagsChanged) { MarkChanged(Actor,World); ++ChangedActors; }
                if (World->WorldType==EWorldType::Editor) Candidate.Data->Modify();
            }
            Candidate.Data->InitializeIdentity(CanonicalId);
        }
        State.Owners.Add(Candidate.Number,Actor);
    }
    if (Settings && State.HighWater>0)
    {
        TArray<FName> Updated=Settings->Tags;
        Updated.RemoveAll([](const FName Tag) { return Tag.ToString().StartsWith(HighWaterPrefix,ESearchCase::CaseSensitive); });
        Updated.Add(FName(*FString::Printf(TEXT("GHSManualIdentityHighWater=%d"),State.HighWater)));
        if (Updated!=Settings->Tags)
        {
            MarkChanged(Settings,World);
            Settings->Tags=MoveTemp(Updated);
        }
    }
    return ChangedActors;
}
