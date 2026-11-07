#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRSorterSimulationActor.h"
#include "GHSAutomationTestFlags.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterLayoutValidation,"MPR.Sorter.LayoutValidation",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRSorterLayoutValidation::RunTest(const FString&)
{
    FString Original;
    const FString Path=FPaths::ProjectDir()/TEXT("SourceAssets/MPR/sorter_simulation/layout.json");
    if(!TestTrue(TEXT("Archived scene layout is readable"),FFileHelper::LoadFileToString(Original,*Path))
       ||!TestNotNull(TEXT("Engine is available for a temporary world"),GEngine))return false;

    // CreateWorld calls InitializeNewWorld with these lightweight settings.
    // No BeginPlay, game mode, UI, current map or editor world is involved.
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false)
        .ShouldSimulatePhysics(false).CreateNavigation(false).CreateAISystem(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if(!TestNotNull(TEXT("Disposable world created"),World))return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World);World->DestroyWorld(false); };
    auto Spawn=[World]()
    {
        FActorSpawnParameters Params;Params.ObjectFlags|=RF_Transient;
        Params.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        return World->SpawnActor<AMPRSorterSimulationActor>(FVector::ZeroVector,FRotator::ZeroRotator,Params);
    };
    auto* Valid=Spawn();if(!TestNotNull(TEXT("Layout actor spawned"),Valid))return false;
    TestFalse(TEXT("Fixture does not begin gameplay"),Valid->HasActorBegunPlay());
    Valid->LayoutJson=Original;
    if(!TestTrue(TEXT("Real archived layout is accepted"),Valid->LoadLayout()))return false;
    TestEqual(TEXT("Exactly 22 machines parsed"),Valid->Machines.Num(),22);
    int32 Bins=0,Count64=0,Count120=0;
    for(const auto& M:Valid->Machines)
    {Bins+=M.Bins.Num();Count64+=M.Profile==TEXT("cad64");Count120+=M.Profile==TEXT("cad120");}
    TestEqual(TEXT("Exactly 1632 scene bins parsed"),Bins,1632);
    TestEqual(TEXT("18 CAD64 machines retained"),Count64,18);
    TestEqual(TEXT("4 CAD120 machines retained"),Count120,4);

    const TCHAR* Names[]={TEXT("missing profiles"),TEXT("null final world transform"),TEXT("null CAD120 level"),TEXT("duplicate CAD120 bin")};
    for(int32 Case=0;Case<4;++Case)
    {
        TSharedPtr<FJsonObject> Root;
        if(!TestTrue(TEXT("Fresh fixture JSON parses"),FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Original),Root))||!Root)return false;
        if(Case==0)Root->RemoveField(TEXT("profiles"));
        else if(Case==1)Root->GetArrayField(TEXT("machines")).Last()->AsObject()->SetField(TEXT("world_transform"),MakeShared<FJsonValueNull>());
        else
        {
            const auto Profile=Root->GetObjectField(TEXT("profiles"))->GetObjectField(TEXT("cad120"));
            const TCHAR* Field=Case==2?TEXT("levels"):TEXT("bins");
            auto Values=Profile->GetArrayField(Field);
            if(Case==2)Values[0]=MakeShared<FJsonValueNull>();else Values.Last()=Values[0];
            Profile->SetArrayField(Field,Values);
        }
        FString Broken;
        if(!TestTrue(TEXT("Malformed fixture serializes"),FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Broken))))return false;
        auto* Invalid=Spawn();if(!TestNotNull(TEXT("Fresh malformed-layout actor spawned"),Invalid))return false;
        Invalid->LayoutJson=Broken;
        TestFalse(FString::Printf(TEXT("Reject %s without crashing"),Names[Case]),Invalid->LoadLayout());
        TestEqual(FString::Printf(TEXT("%s leaves no partial fleet"),Names[Case]),Invalid->Machines.Num(),0);
        TestFalse(FString::Printf(TEXT("%s reports an explanation"),Names[Case]),Invalid->Error.IsEmpty());
        TestFalse(TEXT("Malformed actor never begins play"),Invalid->HasActorBegunPlay());
        // A failure after many valid rows must also preserve an already parsed fleet.
        Valid->LayoutJson=Broken;
        TestFalse(FString::Printf(TEXT("Existing fleet rejects %s"),Names[Case]),Valid->LoadLayout());
        TestEqual(TEXT("Failed reparse preserves all previously valid machines"),Valid->Machines.Num(),22);
    }
    Valid->LayoutJson=Original;
    TestTrue(TEXT("Valid reparse still succeeds"),Valid->LoadLayout());
    TestEqual(TEXT("Successful reparse replaces instead of appending"),Valid->Machines.Num(),22);
    return true;
}
#endif
