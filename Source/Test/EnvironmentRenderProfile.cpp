#include "EnvironmentRenderProfile.h"
#include "EnvironmentRenderProfileLease.h"
#include "Components/SceneComponent.h"
#include "CoreGlobals.h"
#include "Engine/World.h"
#include "Misc/App.h"

namespace
{
using EnvironmentRenderProfilePrivate::FConsoleFloatLease;

FConsoleFloatLease* LumenExtentLease()
{
    // Created only for an eligible registered actor, never during CDO creation.
    // A missing renderer CVar (e.g. a server process) is not cached permanently.
    static TUniquePtr<FConsoleFloatLease> Lease;
    if (!Lease)
    {
        if (IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(TEXT("r.LumenScene.GlobalSDF.ClipmapExtent")))
        {
            Lease = MakeUnique<FConsoleFloatLease>(*Variable);
        }
    }
    return Lease.Get();
}
}

AEnvironmentRenderProfile::AEnvironmentRenderProfile()
{
    PrimaryActorTick.bCanEverTick = false;
    SetActorEnableCollision(false);
    SetCanBeDamaged(false);
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("ProfileRoot"));
}

void AEnvironmentRenderProfile::SetLumenClipmapExtent(float NewExtent)
{
    if (FMath::IsFinite(NewExtent) && NewExtent >= 1.f)
    {
        LumenClipmapExtent = NewExtent;
        RefreshProfile();
    }
}

void AEnvironmentRenderProfile::RefreshProfile()
{
    UWorld* World = GetWorld();
    const bool bSupportedWorld = World && (World->WorldType == EWorldType::Editor ||
        World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
    if (IsTemplate() || HasAnyFlags(RF_BeginDestroyed | RF_FinishDestroyed) || IsActorBeingDestroyed() ||
        !HasActorRegisteredAllComponents() || !bSupportedWorld || bEndedPlay || bWorldCleanupStarted ||
        World->bIsTearingDown || World->IsBeingCleanedUp() || IsRunningCookCommandlet() ||
        !FApp::CanEverRender() || !FMath::IsFinite(LumenClipmapExtent) || LumenClipmapExtent < 1.f)
    {
        ReleaseProfile();
        return;
    }
    if (FConsoleFloatLease* Lease = LumenExtentLease())
    {
        bOwnsLease = Lease->Set(this, LumenClipmapExtent);
        if (bOwnsLease && !WorldCleanupHandle.IsValid())
        {
            WorldCleanupHandle = FWorldDelegates::OnWorldCleanup.AddUObject(this, &AEnvironmentRenderProfile::OnWorldCleanup);
        }
    }
}

void AEnvironmentRenderProfile::ReleaseProfile()
{
    if (bOwnsLease)
    {
        if (FConsoleFloatLease* Lease = LumenExtentLease())
        {
            Lease->Release(this);
        }
        bOwnsLease = false;
    }
    if (WorldCleanupHandle.IsValid())
    {
        FWorldDelegates::OnWorldCleanup.Remove(WorldCleanupHandle);
        WorldCleanupHandle.Reset();
    }
}

void AEnvironmentRenderProfile::PostRegisterAllComponents()
{
    Super::PostRegisterAllComponents();
    RefreshProfile();
}

void AEnvironmentRenderProfile::PostUnregisterAllComponents()
{
    ReleaseProfile();
    Super::PostUnregisterAllComponents();
}

void AEnvironmentRenderProfile::BeginPlay()
{
    Super::BeginPlay();
    bEndedPlay = false;
    RefreshProfile();
}

void AEnvironmentRenderProfile::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    bEndedPlay = true;
    ReleaseProfile();
    Super::EndPlay(EndPlayReason);
}

void AEnvironmentRenderProfile::Destroyed()
{
    ReleaseProfile();
    Super::Destroyed();
}

void AEnvironmentRenderProfile::BeginDestroy()
{
    ReleaseProfile();
    Super::BeginDestroy();
}

void AEnvironmentRenderProfile::OnWorldCleanup(UWorld* World, bool, bool)
{
    if (GetWorld() == World)
    {
        bWorldCleanupStarted = true;
        ReleaseProfile();
    }
}

#if WITH_EDITOR
void AEnvironmentRenderProfile::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
    Super::PostEditChangeProperty(PropertyChangedEvent);
    RefreshProfile();
}

void AEnvironmentRenderProfile::PostEditUndo()
{
    Super::PostEditUndo();
    RefreshProfile();
}
#endif
