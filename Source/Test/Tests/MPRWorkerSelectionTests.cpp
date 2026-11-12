#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRSorterSimulationActor.h"
#include "../MPRWorkerPoseComponent.h"
#include "../MPRCadWorkerData.h"
#include "../MPRWorkerPresentationPolicy.h"
#include "GHSAutomationTestFlags.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "UObject/UObjectHash.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterWorkerSelectionValidation,"MPR.Worker.SorterOnlyCADSelection",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRSorterWorkerSelectionValidation::RunTest(const FString&)
{
    FString Layout;
    if(!TestNotNull(TEXT("Engine available"),GEngine)
       ||!TestTrue(TEXT("Original sorter layout is readable"),FFileHelper::LoadFileToString(Layout,
           *(FPaths::ProjectDir()/TEXT("SourceAssets/MPR/sorter_simulation/layout.json")))))return false;
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false)
        .ShouldSimulatePhysics(false).CreateNavigation(false).CreateAISystem(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if(!TestNotNull(TEXT("Disposable worker selection world"),World))return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World);World->DestroyWorld(false); };
    FActorSpawnParameters Params;Params.ObjectFlags|=RF_Transient;
    Params.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Actor=World->SpawnActor<AMPRSorterSimulationActor>(FVector::ZeroVector,FRotator::ZeroRotator,Params);
    if(!TestNotNull(TEXT("Real sorter actor created without starting gameplay"),Actor))return false;
    Actor->LayoutJson=Layout;
    if(!TestTrue(TEXT("All original machines and feed stations load"),Actor->LoadLayout())
       ||!TestTrue(TEXT("Retained workers instantiate on the original layout"),Actor->BuildWorkers()))return false;
    TestEqual(TEXT("Complete original CAD personnel remain in source data"),int32(UE_ARRAY_COUNT(MPRCadWorkers::Workers)),256);
    TestEqual(TEXT("Only 29 runtime worker components are created"),Actor->RuntimeWorkers.Num(),29);
    TestEqual(TEXT("Only seven CAD workers have runtime mappings"),Actor->CadWorkerIndices.Num(),7);
    TestEqual(TEXT("Each runtime mapping keeps an explicit original source index"),Actor->CadWorkerSourceIndices.Num(),7);
    TSet<int32> UsedWorkerIndices;TSet<FString> RetainedHandles;
    int32 FeedCount=0,ConsoleCount=0;
    for(const auto& Machine:Actor->Machines)
    {
        TestTrue(TEXT("Each of the 22 machines retains its independent exchange slot"),Actor->RuntimeWorkers.IsValidIndex(Machine.WorkerOffset));
        UsedWorkerIndices.Add(Machine.WorkerOffset);
    }
    TestEqual(TEXT("Exchange slots remain unique"),UsedWorkerIndices.Num(),22);
    for(int32 I=0;I<Actor->CadWorkerIndices.Num();++I)
    {
        const int32 SourceIndex=Actor->CadWorkerSourceIndices[I],WorkerIndex=Actor->CadWorkerIndices[I];
        if(!TestTrue(TEXT("Source mapping is in the complete CAD list"),SourceIndex>=0&&SourceIndex<int32(UE_ARRAY_COUNT(MPRCadWorkers::Workers))))return false;
        const auto& Source=MPRCadWorkers::Workers[SourceIndex];
        const auto* Policy=MPRWorkerPresentation::Find(Source.SourceHandle);
        if(!TestNotNull(TEXT("Every spawned CAD worker is explicitly retained"),Policy))return false;
        TestTrue(TEXT("Each retained worker owns one valid runtime component"),Actor->RuntimeWorkers.IsValidIndex(WorkerIndex));
        TestFalse(TEXT("Retained workers do not duplicate other workers or exchange slots"),UsedWorkerIndices.Contains(WorkerIndex));
        UsedWorkerIndices.Add(WorkerIndex);RetainedHandles.Add(UTF8_TO_TCHAR(Source.SourceHandle));
        if(Source.CentralFeed)
        {
            ++FeedCount;TestEqual(TEXT("Feed role remains explicit"),FString(UTF8_TO_TCHAR(Policy->Role)),FString(TEXT("central_feed")));
            int32 Matched=0;
            for(const auto& Bank:Actor->DistributionBanks)for(const auto& Station:Bank.Stations)
                if(Station.bManual&&Station.WorkerIndex==WorkerIndex)
                {
                    ++Matched;
                    TestTrue(TEXT("Filtering preserves original feed feet and motion binding"),
                        Station.Feet.Equals(FVector(Source.Feet[0],Source.Feet[1],Source.Feet[2]),.1));
                }
            TestEqual(TEXT("Each retained feed worker stays bound to exactly one active station"),Matched,1);
        }
        else
        {
            ++ConsoleCount;TestEqual(TEXT("The retained console operator is the audited 2CCF61"),FString(UTF8_TO_TCHAR(Source.SourceHandle)),FString(TEXT("2CCF61")));
            TestEqual(TEXT("Console role remains explicit"),FString(UTF8_TO_TCHAR(Policy->Role)),FString(TEXT("sorter_console")));
            TestEqual(TEXT("Console uses its original stationary pose only once"),Actor->RuntimeWorkers[WorkerIndex]->GetPoseRevision(),1);
        }
    }
    TestEqual(TEXT("All six original manual feed operators remain"),FeedCount,6);
    TestEqual(TEXT("One audited sorter end-console operator remains"),ConsoleCount,1);
    TestEqual(TEXT("No unused or omitted worker components are allocated"),UsedWorkerIndices.Num(),Actor->RuntimeWorkers.Num());
    int32 Omitted=0;
    for(const auto& Source:MPRCadWorkers::Workers)
        if(!MPRWorkerPresentation::Find(Source.SourceHandle))
        {++Omitted;TestFalse(TEXT("Omitted CAD personnel have no spawned representation"),RetainedHandles.Contains(UTF8_TO_TCHAR(Source.SourceHandle)));}
    TestEqual(TEXT("249 personnel outside sorter equipment are omitted"),Omitted,249);
    const auto BeforeSources=Actor->CadWorkerSourceIndices,BeforeWorkers=Actor->CadWorkerIndices;
    // UE's named NewObject replacement preserves the old address, UObject index
    // and serial number (StaticAllocateObject). Old weak references can therefore
    // resolve to the rebuilt component. Audit actual ownership/registration and
    // attachment sets instead of treating weak-pointer survival as a leak.
    for(int32 Rebuild=0;Rebuild<3;++Rebuild)
    {
        if(!TestTrue(TEXT("Rebuilding workers remains safe"),Actor->BuildWorkers()))return false;
        TestEqual(TEXT("Rebuild cannot restore omitted CAD staff"),Actor->RuntimeWorkers.Num(),29);
        TestTrue(TEXT("Source and runtime identities survive rebuilding"),Actor->CadWorkerSourceIndices==BeforeSources&&Actor->CadWorkerIndices==BeforeWorkers);
        TSet<UMPRWorkerPoseComponent*> Tracked;
        for(const auto& Worker:Actor->RuntimeWorkers)
        {
            TestNotNull(TEXT("Every rebuilt runtime slot contains a component"),Worker.Get());
            if(!Worker)return false;
            TestTrue(TEXT("Every tracked worker is registered"),Worker->IsRegistered());
            TestTrue(TEXT("Every tracked worker is owned by the sorter actor"),Worker->GetOwner()==Actor);
            TestTrue(TEXT("Every tracked worker is attached to the sorter root"),Worker->GetAttachParent()==Actor->GetRootComponent());
            Tracked.Add(Worker.Get());
        }
        TestEqual(TEXT("Runtime slots contain 29 distinct workers"),Tracked.Num(),29);

        TArray<UMPRWorkerPoseComponent*> Owned;
        Actor->GetComponents(Owned);
        TestEqual(TEXT("Owner component registry contains no leftover workers"),Owned.Num(),29);
        for(auto* Worker:Owned)TestTrue(TEXT("Every owned worker is tracked exactly once"),Tracked.Contains(Worker));

        // Independently scan all direct UObject children: a stale registered
        // component omitted from Actor::GetComponents must also fail this test.
        TArray<UObject*> Children;
        GetObjectsWithOuter(Actor,Children,EGetObjectsFlags::None);
        int32 Registered=0;
        for(auto* Child:Children)if(auto* Worker=Cast<UMPRWorkerPoseComponent>(Child))
        {
            if(Worker->IsRegistered())
            {
                ++Registered;
                TestTrue(TEXT("No untracked registered worker survives a rebuild"),Tracked.Contains(Worker));
            }
        }
        TestEqual(TEXT("Exactly 29 worker objects remain registered after each rebuild"),Registered,29);
        int32 Attached=0;
        for(const auto& Child:Actor->GetRootComponent()->GetAttachChildren())if(auto* Worker=Cast<UMPRWorkerPoseComponent>(Child.Get()))
        {
            ++Attached;
            TestTrue(TEXT("Root attachment list contains only current workers"),Tracked.Contains(Worker));
        }
        TestEqual(TEXT("No duplicate or stale worker attachments remain"),Attached,29);
    }
    return true;
}
#endif
