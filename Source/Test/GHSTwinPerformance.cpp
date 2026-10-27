#include "GHSTwinPerformance.h"

#if !UE_BUILD_SHIPPING
#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehousePlayerController.h"
#include "GHSStorageCapacityComponent.h"
#include "GHSCampusTrafficActor.h"
#include "GHSTwinHUDWidget.h"
#include "Camera/CameraComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProcess.h"
#include "HardwareInfo.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "ProfilingDebugging/CsvProfiler.h"
#include "ProfilingDebugging/MiscTrace.h"
#include "ProfilingDebugging/TraceAuxiliary.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UnrealClient.h"

#if CSV_PROFILER
namespace GHSTwinPerformance
{
namespace
{
constexpr double CycleSeconds=45.;
struct FAction { double At; const TCHAR* Name; };
const FAction Actions[]={{0,TEXT("overview")},{1,TEXT("all_poi")},{4,TEXT("orbit")},
    {12,TEXT("agv")},{16,TEXT("forklift")},{20,TEXT("racks")},{24,TEXT("cargo_focus")},
    {26,TEXT("cargo_click")},{28,TEXT("panel_close")},{29,TEXT("panel_open")},
    {30,TEXT("page_devices")},{31,TEXT("page_orders")},{32,TEXT("page_inventory")},
    {33,TEXT("page_alerts")},{34,TEXT("page_trace")},{35,TEXT("page_settings")},
    {36,TEXT("page_overview")},{38,TEXT("overview")},{40,TEXT("all_poi")}};

TSharedPtr<FJsonObject> ParseJson(const FString& Text)
{
    TSharedPtr<FJsonObject> Value;
    FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Value);
    return Value;
}
FString CVar(const TCHAR* Name)
{
    const auto* Variable=IConsoleManager::Get().FindConsoleVariable(Name);
    return Variable?Variable->GetString():TEXT("unavailable");
}

class FRun
{
public:
    FString Label, Directory, CsvPath, TracePath, Error, Variant=TEXT("baseline");
    double Created=FPlatformTime::Seconds(), PhaseStart=0, RouteStart=0, Duration=90, Warmup=15;
    double PreviousRouteTime=0;
    int32 Stage=0, NextAction=0, Cycle=0, CompletedActions=0, CargoClicks=0;
    bool bTrace=false, bTraceStarted=false, bTraceStopRequested=false, bTraceFinalized=false, bFinished=false, bFinalReportsCollected=false;
    TWeakObjectPtr<AGHSWarehousePlayerController> Controller;
    TWeakObjectPtr<AGHSWarehouseCameraPawn> Camera;
    TWeakObjectPtr<UGHSTwinHUDWidget> Widget;
    TArray<FVector> CargoPoints;
    TMap<FString,FString> OriginalCVars;
    TSharedRef<FJsonObject> Report=MakeShared<FJsonObject>();
    TArray<TSharedPtr<FJsonValue>> Segments;
    TSharedFuture<FString> CsvComplete;
    struct FStorageOriginal
    {
        TWeakObjectPtr<UInstancedStaticMeshComponent> Component;
        EShadowCacheInvalidationBehavior ShadowCache;
        bool bCastShadow;
    };
    TArray<FStorageOriginal> OriginalStorage;
    TWeakObjectPtr<AActor> OriginalTraffic;
    bool bTrafficTick=true,bTrafficHidden=false,bTrafficChanged=false,bVariantPrepared=false;

    static TSharedRef<FJsonObject> StorageProperties(const UInstancedStaticMeshComponent* Component)
    {
        const auto Properties=MakeShared<FJsonObject>();
        const auto Cache=Component->ShadowCacheInvalidationBehavior;
        Properties->SetStringField(TEXT("shadow_cache_invalidation"),Cache==EShadowCacheInvalidationBehavior::Auto?TEXT("Auto"):
            Cache==EShadowCacheInvalidationBehavior::Always?TEXT("Always"):Cache==EShadowCacheInvalidationBehavior::Rigid?TEXT("Rigid"):TEXT("Static"));
        Properties->SetBoolField(TEXT("cast_shadow"),Component->CastShadow);
        Properties->SetNumberField(TEXT("collision_mode"),int32(Component->GetCollisionEnabled()));
        return Properties;
    }
    bool ApplyVariant()
    {
        const auto Manifest=MakeShared<FJsonObject>();
        Report->SetObjectField(TEXT("variant_setup"),Manifest);
        Manifest->SetStringField(TEXT("name"),Variant);
        Manifest->SetStringField(TEXT("implementation"),TEXT("native-runtime-v1"));
        Manifest->SetBoolField(TEXT("applied_before_warmup"),true);
        Manifest->SetBoolField(TEXT("success"),false);
        auto Fail=[&](const FString& Message) { Manifest->SetStringField(TEXT("error"),Message);return false; };
        if(bVariantPrepared) return Fail(TEXT("Variant setup was already applied"));
        if(Variant!=TEXT("baseline") && Variant!=TEXT("shadow-auto") && Variant!=TEXT("shadow-off")
            && Variant!=TEXT("traffic-off") && Variant!=TEXT("traffic-hidden")) return Fail(TEXT("Unknown TwinPerfVariant"));
        FString Text;
        if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/storage-capacity.json"))))
            return Fail(TEXT("Variant requires storage-capacity.json"));
        const auto Root=ParseJson(Text);const TArray<TSharedPtr<FJsonValue>>* Groups=nullptr;
        if(!Root || !Root->TryGetArrayField(TEXT("groups"),Groups) || Groups->Num()!=13)
            return Fail(TEXT("Expected exactly 13 storage definitions"));
        TMap<FName,TSharedPtr<FJsonObject>> Definitions;
        for(const auto& Value:*Groups)
        {
            const auto Definition=Value->AsObject();FString ActorName,Mesh,Kind;double Count=0;
            if(!Definition || !Definition->TryGetStringField(TEXT("actor"),ActorName) || ActorName.IsEmpty()
                || !Definition->TryGetStringField(TEXT("mesh"),Mesh) || Mesh.IsEmpty()
                || !Definition->TryGetStringField(TEXT("kind"),Kind) || (Kind!=TEXT("rack") && Kind!=TEXT("floor"))
                || !Definition->TryGetNumberField(TEXT("count"),Count) || !FMath::IsFinite(Count)
                || Count<1 || Count>MAX_int32 || Count!=FMath::FloorToDouble(Count)) return Fail(TEXT("Invalid storage group definition"));
            const FName Tag(*(TEXT("GHSStorageGroup:")+ActorName));
            if(Definitions.Contains(Tag)) return Fail(TEXT("Duplicate storage definition: ")+ActorName);
            Definitions.Add(Tag,Definition);
        }
        const auto Capacity=Controller->StorageCapacity?ParseJson(Controller->StorageCapacity->GetReportJson()):nullptr;
        bool Initialized=false;double Registered=0;FString CapacityError;
        if(!Capacity || !Capacity->TryGetBoolField(TEXT("initialized"),Initialized) || !Initialized
            || !Capacity->TryGetNumberField(TEXT("registered_components"),Registered) || Registered!=13
            || !Capacity->TryGetStringField(TEXT("error"),CapacityError) || !CapacityError.IsEmpty())
            return Fail(TEXT("Storage capacity registration is incomplete"));
        struct FGroupInstance { UInstancedStaticMeshComponent* Component;FName Tag;TSharedPtr<FJsonObject> Definition; };
        TArray<FGroupInstance> Inventory;TSet<FName> Seen;
        TArray<AActor*> Actors;for(TActorIterator<AActor> It(Controller->GetWorld());It;++It) Actors.Add(*It);
        Actors.Sort([](const AActor& A,const AActor& B){return A.GetName()<B.GetName();});
        for(AActor* Actor:Actors)
        {
            TInlineComponentArray<UInstancedStaticMeshComponent*> Components;Actor->GetComponents(Components);
            Components.Sort([](const UInstancedStaticMeshComponent& A,const UInstancedStaticMeshComponent& B){return A.GetName()<B.GetName();});
            for(auto* Component:Components)
            {
                TSharedPtr<FJsonObject> Definition;FName GroupTag;
                for(const FName& Tag:Component->ComponentTags)
                    if(const auto* Found=Definitions.Find(Tag))
                    {
                        if(Definition) return Fail(TEXT("Multiple storage tags on ")+Component->GetPathName());
                        Definition=*Found;GroupTag=Tag;
                    }
                if(!Definition) continue;
                if(Seen.Contains(GroupTag)) return Fail(TEXT("Duplicate runtime storage group: ")+GroupTag.ToString());
                if(!IsValid(Component) || Component->GetOwner()!=Actor || Component->GetWorld()!=Controller->GetWorld()
                    || !Component->GetStaticMesh() || Component->GetStaticMesh()->GetName()!=Definition->GetStringField(TEXT("mesh"))
                    || Component->GetInstanceCount()!=Definition->GetIntegerField(TEXT("count")))
                    return Fail(TEXT("Runtime storage mesh/count mismatch: ")+GroupTag.ToString());
                Seen.Add(GroupTag);Inventory.Add({Component,GroupTag,Definition});
            }
        }
        if(Seen.Num()!=13) return Fail(TEXT("Missing runtime storage group"));
        AActor* Traffic=Controller->CampusTraffic;
        if(!IsValid(Traffic) || Traffic->GetWorld()!=Controller->GetWorld()) return Fail(TEXT("Campus traffic is not initialized in the owned world"));
        const auto TrafficRuntime=ParseJson(Controller->CampusTraffic->GetTrafficReportJson());
        bool TrafficReady=false;double TrafficComponents=0,TrafficInstances=0;
        if(!TrafficRuntime || !TrafficRuntime->TryGetBoolField(TEXT("ready"),TrafficReady) || !TrafficReady
            || !TrafficRuntime->TryGetNumberField(TEXT("component_count"),TrafficComponents) || TrafficComponents!=4
            || !TrafficRuntime->TryGetNumberField(TEXT("fixed_instances"),TrafficInstances) || TrafficInstances!=32)
            return Fail(TEXT("Campus traffic fixture is incomplete"));
        const bool BeforeTick=Traffic->IsActorTickEnabled(),BeforeHidden=Traffic->IsHidden();
        const auto TrafficState=MakeShared<FJsonObject>();
        TrafficState->SetObjectField(TEXT("runtime_before"),TrafficRuntime);
        TrafficState->SetBoolField(TEXT("tick_before"),BeforeTick);TrafficState->SetBoolField(TEXT("hidden_before"),BeforeHidden);
        TArray<TSharedPtr<FJsonValue>> Rows;int32 InstanceCount=0;
        // Direct runtime writes deliberately avoid editor property setters and PostEditChange.
        for(const auto& Group:Inventory)
        {
            auto* Component=Group.Component;AActor* Owner=Component->GetOwner();
            const auto Row=MakeShared<FJsonObject>();Rows.Add(MakeShared<FJsonValueObject>(Row));
            Manifest->SetArrayField(TEXT("groups"),Rows);
            Row->SetStringField(TEXT("actor"),Owner->GetName());Row->SetStringField(TEXT("component"),Component->GetName());
            Row->SetStringField(TEXT("tag"),Group.Tag.ToString());Row->SetStringField(TEXT("mesh"),Component->GetStaticMesh()->GetName());
            Row->SetStringField(TEXT("kind"),Group.Definition->GetStringField(TEXT("kind")));
            Row->SetNumberField(TEXT("instances"),Component->GetInstanceCount());
            Row->SetObjectField(TEXT("before"),StorageProperties(Component));
            const auto CacheBefore=Component->ShadowCacheInvalidationBehavior;const bool ShadowBefore=Component->CastShadow;
            const auto CollisionBefore=Component->GetCollisionEnabled();
            if(Variant==TEXT("shadow-auto") || Variant==TEXT("shadow-off"))
            {
                OriginalStorage.Add({Component,CacheBefore,ShadowBefore});
                if(Variant==TEXT("shadow-auto")) Component->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Auto;
                else Component->CastShadow=false;
                Component->MarkRenderStateDirty();
            }
            if(!IsValid(Component) || Component->GetOwner()!=Owner || !Component->GetStaticMesh()
                || Component->GetStaticMesh()->GetName()!=Group.Definition->GetStringField(TEXT("mesh"))
                || Component->GetInstanceCount()!=Group.Definition->GetIntegerField(TEXT("count"))
                || Component->GetCollisionEnabled()!=CollisionBefore
                || Component->ShadowCacheInvalidationBehavior!=(Variant==TEXT("shadow-auto")?EShadowCacheInvalidationBehavior::Auto:CacheBefore)
                || bool(Component->CastShadow)!=(Variant==TEXT("shadow-off")?false:ShadowBefore))
                return Fail(TEXT("Variant storage readback failed: ")+Group.Tag.ToString());
            Row->SetObjectField(TEXT("after"),StorageProperties(Component));
            InstanceCount+=Component->GetInstanceCount();
        }
        if(Variant==TEXT("traffic-off") || Variant==TEXT("traffic-hidden"))
        {
            OriginalTraffic=Traffic;bTrafficTick=BeforeTick;bTrafficHidden=BeforeHidden;bTrafficChanged=true;
            Traffic->SetActorTickEnabled(false);
            if(Variant==TEXT("traffic-hidden")) Traffic->SetActorHiddenInGame(true);
        }
        const bool ExpectedTick=Variant==TEXT("traffic-off") || Variant==TEXT("traffic-hidden")?false:BeforeTick;
        const bool ExpectedHidden=Variant==TEXT("traffic-hidden")?true:BeforeHidden;
        if(Traffic->IsActorTickEnabled()!=ExpectedTick || Traffic->IsHidden()!=ExpectedHidden)
            return Fail(TEXT("Variant traffic readback failed"));
        TrafficState->SetBoolField(TEXT("tick_after"),Traffic->IsActorTickEnabled());TrafficState->SetBoolField(TEXT("hidden_after"),Traffic->IsHidden());
        Manifest->SetObjectField(TEXT("traffic"),TrafficState);Manifest->SetObjectField(TEXT("capacity"),Capacity);
        Manifest->SetNumberField(TEXT("group_count"),Inventory.Num());Manifest->SetNumberField(TEXT("instance_count"),InstanceCount);
        Manifest->SetBoolField(TEXT("success"),true);bVariantPrepared=true;
        return true;
    }
    void RestoreVariant()
    {
        if(Report->HasField(TEXT("variant_restored"))) return;
        if(OriginalStorage.IsEmpty() && !bTrafficChanged)
        { if(bVariantPrepared) Report->SetBoolField(TEXT("variant_restored"),true);return; }
        bool Restored=true;
        for(const auto& Original:OriginalStorage)
        {
            auto* Component=Original.Component.Get();
            if(!Component) { Restored=false;continue; }
            Component->ShadowCacheInvalidationBehavior=Original.ShadowCache;
            Component->CastShadow=Original.bCastShadow;
            Component->MarkRenderStateDirty();
            Restored=Restored && Component->ShadowCacheInvalidationBehavior==Original.ShadowCache && bool(Component->CastShadow)==Original.bCastShadow;
        }
        OriginalStorage.Empty();
        if(bTrafficChanged)
        {
            if(auto* Traffic=OriginalTraffic.Get())
            {
                Traffic->SetActorTickEnabled(bTrafficTick);Traffic->SetActorHiddenInGame(bTrafficHidden);
                Restored=Restored && Traffic->IsActorTickEnabled()==bTrafficTick && Traffic->IsHidden()==bTrafficHidden;
            }
            else Restored=false;
        }
        OriginalTraffic.Reset();bTrafficChanged=false;Report->SetBoolField(TEXT("variant_restored"),Restored);
        if(!Restored && Error.IsEmpty()) Error=TEXT("Diagnostic variant restoration failed");
    }
    bool TraceConnected() const
    {
        return FTraceAuxiliary::IsConnected() && FTraceAuxiliary::GetConnectionType()==FTraceAuxiliary::EConnectionType::File
            && FPaths::IsSamePath(TracePath,FTraceAuxiliary::GetTraceDestinationString());
    }
    bool RequestTraceStop()
    {
        if(bTraceStopRequested) return true;
        const bool Connected=bTraceStarted && TraceConnected();
        // Do not stop a session whose destination changed after our recording began.
        const bool Stopped=Connected && FTraceAuxiliary::Stop();
        Report->SetBoolField(TEXT("trace_connected_before_stop"),Connected);
        Report->SetBoolField(TEXT("trace_stop_succeeded"),Stopped);
        bTraceStopRequested=Stopped;
        if(!Stopped && Error.IsEmpty()) Error=TEXT("Trace recording lost its owned file connection");
        return Stopped;
    }
    void FinalizeTraceFile(bool Closed)
    {
        bTraceFinalized=true;bTraceStarted=false;
        const int64 Bytes=TracePath.IsEmpty()?-1:IFileManager::Get().FileSize(*TracePath);
        Report->SetBoolField(TEXT("trace_connection_closed"),Closed);
        Report->SetBoolField(TEXT("trace_file_exists"),Bytes>=0);
        Report->SetNumberField(TEXT("trace_file_bytes"),double(Bytes));
        if((!Closed || !bTraceStopRequested || Bytes<=0) && Error.IsEmpty()) Error=TEXT("Trace recording did not produce a closed, nonempty file");
    }
    void StopTraceAndVerify()
    {
        if(!bTrace || bTraceFinalized) return;
        RequestTraceStop();
        // Failure/early-shutdown cleanup must never call a pending trace complete.
        // Successful captures use stage 6 to await the writer's actual close first.
        FinalizeTraceFile(bTraceStopRequested && !FTraceAuxiliary::IsConnected());
    }

    void Console(const FString& Text)
    {
        if(Controller.IsValid()) Controller->ConsoleCommand(Text,false);
    }
    void Command(const FString& Text) { Widget->Command(Text); }
    void Write(const TCHAR* Status)
    {
        Report->SetStringField(TEXT("status"),Status);
        Report->SetBoolField(TEXT("success"),bFinished && Error.IsEmpty());
        Report->SetStringField(TEXT("error"),Error);
        Report->SetStringField(TEXT("csv"),CsvPath);
        Report->SetNumberField(TEXT("elapsed_seconds"),FPlatformTime::Seconds()-Created);
        Report->SetNumberField(TEXT("completed_actions"),CompletedActions);
        Report->SetNumberField(TEXT("cargo_clicks"),CargoClicks);
        Report->SetArrayField(TEXT("segments"),Segments);
        FString Json; FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Json));
        FFileHelper::SaveStringToFile(Json,*(Directory/TEXT("run.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    }
    void Restore()
    {
        RestoreVariant();
        for(const auto& Entry:OriginalCVars) Console(Entry.Key+TEXT(" ")+Entry.Value);
        OriginalCVars.Empty();
    }
    void Finish(const FString& Failure=FString())
    {
        if(bFinished) return;
        if(!Failure.IsEmpty()) Error=Failure;
        if(FCsvProfiler::Get()->IsCapturing()) FCsvProfiler::Get()->EndCapture();
        StopTraceAndVerify();
        Restore(); bFinished=true;
        Write(Error.IsEmpty()?TEXT("complete"):TEXT("failed"));
        UE_LOG(LogTemp,Display,TEXT("GHS_TWIN_PERF_%s %s %s"),Error.IsEmpty()?TEXT("COMPLETE"):TEXT("FAILED"),*Directory,*Error);
        // This instance exists only in an explicitly requested standalone benchmark process.
        FPlatformMisc::RequestExitWithStatus(false,Error.IsEmpty()?0:1);
    }
    bool Discover()
    {
        if(!GEngine) return false;
        for(const auto& Context:GEngine->GetWorldContexts())
        {
            UWorld* World=Context.World();
            if(!World || Context.WorldType!=EWorldType::Game) continue;
            auto* PC=Cast<AGHSWarehousePlayerController>(World->GetFirstPlayerController());
            if(!PC || !PC->TwinHUDWidget || !PC->TwinHUDWidget->bBrowserReady) continue;
            auto* Pawn=Cast<AGHSWarehouseCameraPawn>(PC->GetPawn());
            if(!Pawn) continue;
            Controller=PC; Camera=Pawn; Widget=PC->TwinHUDWidget;
            if(!World->GetMapName().Contains(TEXT("ZcoolSmartFactory"))) { Finish(TEXT("Expected the Zcool warehouse map")); return false; }
            int32 X=0,Y=0; PC->GetViewportSize(X,Y);
            if(X!=1920 || Y!=1080) { Finish(TEXT("Benchmark requires an actual 1920x1080 viewport")); return false; }
            auto* ViewportClient=World->GetGameViewport();
            if(!ViewportClient || !ViewportClient->Viewport) return false;
            const FString RHI=FHardwareInfo::GetHardwareInfo(NAME_RHI);
            if(RHI.IsEmpty()) { Finish(TEXT("Active RHI metadata is unavailable")); return false; }
            const EWindowMode::Type WindowMode=ViewportClient->Viewport->GetWindowMode();
            Report->SetStringField(TEXT("rhi"),RHI);
            Report->SetStringField(TEXT("window_mode"),WindowMode==EWindowMode::Windowed?TEXT("windowed"):
                WindowMode==EWindowMode::WindowedFullscreen?TEXT("windowed_fullscreen"):TEXT("fullscreen"));
            Report->SetStringField(TEXT("map"),World->GetMapName());
            Report->SetArrayField(TEXT("viewport"),{MakeShared<FJsonValueNumber>(X),MakeShared<FJsonValueNumber>(Y)});
            auto Snapshot=ParseJson(Widget->GetSnapshot());
            const TArray<TSharedPtr<FJsonValue>>* Equipment=nullptr;
            const TArray<TSharedPtr<FJsonValue>>* Facilities=nullptr;
            if(!Snapshot || !Snapshot->TryGetArrayField(TEXT("equipment"),Equipment) || !Snapshot->TryGetArrayField(TEXT("facilities"),Facilities)
                || Equipment->Num()!=106 || Facilities->Num()!=56)
            { Finish(TEXT("Unexpected warehouse scene data counts")); return false; }
            Report->SetNumberField(TEXT("equipment_count"),Equipment->Num());
            Report->SetNumberField(TEXT("facility_count"),Facilities->Num());
            return true;
        }
        return false;
    }
    bool FindCargoFixture()
    {
        Report->SetNumberField(TEXT("cargo_fixture_version"),2);
        FString Text;
        if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/rack-slots.json")))) return false;
        auto Root=ParseJson(Text); if(!Root) return false;
        const TArray<TSharedPtr<FJsonValue>>* Models=nullptr;
        if(!Root->TryGetArrayField(TEXT("meshes"),Models)) return false;
        const FString CapacityPath=FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/storage-capacity.json");
        TSharedPtr<FJsonObject> CapacityRoot;
        const TArray<TSharedPtr<FJsonValue>>* CapacityModels=nullptr;
        const TArray<TSharedPtr<FJsonValue>>* CapacityGroups=nullptr;
        bool bCapacityValidated=false;
        if(FPaths::FileExists(CapacityPath))
        {
            if(!FFileHelper::LoadFileToString(Text,*CapacityPath) || !(CapacityRoot=ParseJson(Text))
                || !CapacityRoot->TryGetArrayField(TEXT("meshes"),CapacityModels)
                || !CapacityRoot->TryGetArrayField(TEXT("groups"),CapacityGroups)) return false;
        }
        auto Invalid=[this](const FString& Message)
        { Report->SetStringField(TEXT("cargo_fixture_error"),Message);return false; };
        // Actor/component ordering is stable across launches and identical for both builds.
        TArray<AActor*> Actors;
        for(TActorIterator<AActor> It(Controller->GetWorld());It;++It) Actors.Add(*It);
        Actors.Sort([](const AActor& A,const AActor& B){return A.GetName()<B.GetName();});
        for(AActor* Actor:Actors)
        {
            TInlineComponentArray<UInstancedStaticMeshComponent*> Components; Actor->GetComponents(Components);
            Components.Sort([](const UInstancedStaticMeshComponent& A,const UInstancedStaticMeshComponent& B){return A.GetName()<B.GetName();});
            for(auto* Component:Components)
            {
                if(!Component->GetStaticMesh() || Component->GetInstanceCount()==0) continue;
                const FString Name=Component->GetStaticMesh()->GetName();
                if(!Name.StartsWith(TEXT("SM_GHS_V2Rack_"))) continue;
                if(Name.EndsWith(TEXT("_Capacity")))
                {
                    if(!CapacityModels || !CapacityGroups || !Controller->StorageCapacity)
                        return Invalid(TEXT("Capacity rack requires current capacity metadata/component"));
                    if(!bCapacityValidated)
                    {
                        const auto State=ParseJson(Controller->StorageCapacity->GetReportJson());
                        bool Initialized=false,Visible=false;FString InitializationError;double Registered=0;
                        if(!State || !State->TryGetBoolField(TEXT("initialized"),Initialized) || !Initialized
                            || !State->TryGetBoolField(TEXT("storage_visible"),Visible) || !Visible
                            || !State->TryGetStringField(TEXT("error"),InitializationError) || !InitializationError.IsEmpty()
                            || !State->TryGetNumberField(TEXT("registered_components"),Registered) || Registered!=CapacityGroups->Num())
                            return Invalid(TEXT("Capacity groups are incomplete or not visible"));
                        Report->SetObjectField(TEXT("cargo_fixture_capacity"),State);
                        bCapacityValidated=true;
                    }
                    if(Actor->IsHidden() || !Component->IsVisible() || Component->bHiddenInGame) continue;
                    TSharedPtr<FJsonObject> Group,Model;
                    for(const auto& Value:*CapacityGroups)
                    {
                        const auto Candidate=Value->AsObject();FString ActorName;
                        if(Candidate && Candidate->TryGetStringField(TEXT("actor"),ActorName)
                            && Component->ComponentTags.Contains(FName(*(TEXT("GHSStorageGroup:")+ActorName))))
                        {
                            if(Group) return Invalid(TEXT("Duplicate capacity group tag: ")+Name);
                            Group=Candidate;
                        }
                    }
                    FString GroupMesh,Kind;double Count=0,SlotsPerInstance=0;
                    if(!Group || !Group->TryGetStringField(TEXT("mesh"),GroupMesh) || GroupMesh!=Name
                        || !Group->TryGetStringField(TEXT("kind"),Kind) || Kind!=TEXT("rack")
                        || !Group->TryGetNumberField(TEXT("count"),Count) || Count!=Component->GetInstanceCount()
                        || !Group->TryGetNumberField(TEXT("slots_per_instance"),SlotsPerInstance)
                        || !FMath::IsFinite(SlotsPerInstance) || SlotsPerInstance<1 || SlotsPerInstance>10000
                        || SlotsPerInstance!=FMath::FloorToDouble(SlotsPerInstance))
                        return Invalid(TEXT("Capacity rack mesh/count/tag mismatch: ")+Name);
                    for(const auto& Value:*CapacityModels)
                    {
                        const auto Candidate=Value->AsObject();FString ModelName;
                        if(Candidate && Candidate->TryGetStringField(TEXT("name"),ModelName) && ModelName==Name)
                        { if(Model) return Invalid(TEXT("Duplicate capacity model: ")+Name);Model=Candidate; }
                    }
                    const TArray<TSharedPtr<FJsonValue>>* Definitions=nullptr;
                    if(!Model || !Model->TryGetArrayField(TEXT("slots"),Definitions) || Definitions->Num()!=int32(SlotsPerInstance))
                        return Invalid(TEXT("Incomplete capacity slot bounds: ")+Name);
                    struct FFixtureSlot {FVector Center;double Top;int32 Index;};
                    TArray<FFixtureSlot> Slots;TSet<int32> Seen;
                    auto ReadVector=[](const TSharedPtr<FJsonObject>& Object,const TCHAR* Key,FVector& Out)
                    {
                        const TArray<TSharedPtr<FJsonValue>>* Values=nullptr;
                        if(!Object->TryGetArrayField(Key,Values) || Values->Num()!=3) return false;
                        for(int32 I=0;I<3;++I) if(!(*Values)[I]->TryGetNumber(Out[I]) || !FMath::IsFinite(Out[I])) return false;
                        return true;
                    };
                    for(const auto& Value:*Definitions)
                    {
                        const auto Slot=Value->AsObject();FVector Min,Max;double Index=0,Level=0,Column=0;
                        if(!Slot || !ReadVector(Slot,TEXT("min_cm"),Min) || !ReadVector(Slot,TEXT("max_cm"),Max)
                            || Min.X>=Max.X || Min.Y>=Max.Y || Min.Z>=Max.Z
                            || !Slot->TryGetNumberField(TEXT("index"),Index) || !FMath::IsFinite(Index)
                            || Index<0 || Index>=SlotsPerInstance || Index!=FMath::FloorToDouble(Index)
                            || !Slot->TryGetNumberField(TEXT("level"),Level) || !FMath::IsFinite(Level) || Level<1 || Level!=FMath::FloorToDouble(Level)
                            || !Slot->TryGetNumberField(TEXT("column"),Column) || !FMath::IsFinite(Column) || Column<1 || Column!=FMath::FloorToDouble(Column)
                            || Seen.Contains(int32(Index))) return Invalid(TEXT("Invalid capacity slot: ")+Name);
                        Seen.Add(int32(Index));Slots.Add({(Min+Max)*.5,Max.Z,int32(Index)});
                    }
                    Slots.Sort([](const FFixtureSlot& A,const FFixtureSlot& B){return A.Top!=B.Top?A.Top>B.Top:A.Index<B.Index;});
                    for(int32 Instance=0;Instance<Component->GetInstanceCount();++Instance)
                    {
                        FTransform Transform;if(!Component->GetInstanceTransform(Instance,Transform,true) || Transform.ContainsNaN())
                            return Invalid(TEXT("Invalid capacity instance transform: ")+Name);
                        TArray<FVector> VisiblePoints;
                        for(const auto& Slot:Slots)
                        {
                            const FVector Point=Transform.TransformPosition(Slot.Center);
                            if(Controller->StorageCapacity->IsStorageHitVisible(Component,Instance,Point)) VisiblePoints.Add(Point);
                        }
                        if(VisiblePoints.IsEmpty()) continue;
                        CargoPoints=MoveTemp(VisiblePoints);
                        Report->SetStringField(TEXT("cargo_fixture"),Actor->GetName()+TEXT("/")+Component->GetName()+TEXT("/")+FString::FromInt(Instance)+TEXT("/")+Name+TEXT("/capacity-slots-v2"));
                        Report->SetStringField(TEXT("cargo_fixture_metadata"),TEXT("storage-capacity.json"));
                        Report->SetNumberField(TEXT("cargo_fixture_instance_count"),Component->GetInstanceCount());
                        Report->SetNumberField(TEXT("cargo_fixture_slot_count"),Slots.Num());
                        Report->SetNumberField(TEXT("cargo_fixture_visible_candidates"),CargoPoints.Num());
                        return true;
                    }
                    continue; // Zero capacity is not a usable click fixture; try the next rack.
                }
                for(const auto& Value:*Models)
                {
                    auto Model=Value->AsObject(); const TArray<TSharedPtr<FJsonValue>>* Slots=nullptr;
                    if(!Model || Model->GetStringField(TEXT("name"))!=Name || !Model->TryGetArrayField(TEXT("cargo_stacks"),Slots) || Slots->IsEmpty()) continue;
                    FTransform Transform; Component->GetInstanceTransform(0,Transform,true);
                    TArray<TSharedPtr<FJsonValue>> Sorted=*Slots;
                    Sorted.Sort([](const TSharedPtr<FJsonValue>& A,const TSharedPtr<FJsonValue>& B){return A->AsObject()->GetNumberField(TEXT("stack_top_z_m"))>B->AsObject()->GetNumberField(TEXT("stack_top_z_m"));});
                    for(const auto& SlotValue:Sorted)
                    {
                        auto Slot=SlotValue->AsObject();
                        CargoPoints.Add(Transform.TransformPosition(FVector(Slot->GetNumberField(TEXT("pallet_center_x_m"))*100,0,
                            (Slot->GetNumberField(TEXT("base_z_m"))+Slot->GetNumberField(TEXT("stack_top_z_m")))*50)));
                    }
                    Report->SetStringField(TEXT("cargo_fixture"),Actor->GetName()+TEXT("/")+Component->GetName()+TEXT("/0/")+Name);
                    Report->SetStringField(TEXT("cargo_fixture_metadata"),TEXT("rack-slots.json"));
                    Report->SetNumberField(TEXT("cargo_fixture_instance_count"),Component->GetInstanceCount());
                    Report->SetNumberField(TEXT("cargo_fixture_slot_count"),Sorted.Num());
                    Report->SetNumberField(TEXT("cargo_fixture_visible_candidates"),CargoPoints.Num());
                    return true;
                }
            }
        }
        return false;
    }
    void BeginWarmup()
    {
        if(!ApplyVariant()) { Finish(TEXT("Diagnostic variant setup failed")); return; }
        if(!FindCargoFixture()) { Finish(TEXT("No actual rack cargo fixture")); return; }
        const TMap<FString,FString> Temporary={{TEXT("r.GPUStatsEnabled"),TEXT("1")},{TEXT("r.GPUCsvStatsEnabled"),TEXT("1")},
            {TEXT("csv.CompressionMode"),TEXT("0")},{TEXT("t.MaxFPS"),TEXT("0")},{TEXT("r.VSync"),TEXT("0")},
            {TEXT("r.VSyncEditor"),TEXT("0")},{TEXT("t.IdleWhenNotForeground"),TEXT("0")},{TEXT("Slate.bAllowThrottling"),TEXT("0")},
            {TEXT("r.DynamicRes.OperationMode"),TEXT("0")},{TEXT("r.ScreenPercentage"),TEXT("100")}};
        auto Before=MakeShared<FJsonObject>();
        for(const auto& Entry:Temporary)
        {
            const FString Old=CVar(*Entry.Key); Before->SetStringField(Entry.Key,Old);
            if(Old!=TEXT("unavailable")) { OriginalCVars.Add(Entry.Key,Old); Console(Entry.Key+TEXT(" ")+Entry.Value); }
        }
        Report->SetObjectField(TEXT("original_cvars"),Before);
        auto Observed=MakeShared<FJsonObject>();
        for(const TCHAR* Name:{TEXT("r.ScreenPercentage"),TEXT("r.DynamicRes.OperationMode"),TEXT("r.AntiAliasingMethod"),TEXT("r.Shadow.Virtual.Enable"),
            TEXT("r.DynamicGlobalIlluminationMethod"),TEXT("r.ReflectionMethod"),TEXT("sg.ShadowQuality"),TEXT("sg.PostProcessQuality"),
            TEXT("sg.EffectsQuality"),TEXT("sg.ViewDistanceQuality"),TEXT("sg.TextureQuality"),TEXT("t.MaxFPS"),TEXT("r.VSync"),TEXT("r.GPUCsvStatsEnabled")})
            Observed->SetStringField(Name,CVar(Name));
        Report->SetObjectField(TEXT("observed_cvars"),Observed);
        Report->SetStringField(TEXT("post_process_note"),TEXT("Console GI/reflection values are project defaults, not final view PP overrides. Inspect final view in GPU capture before assigning Lumen cost."));
        Command(TEXT("{\"action\":\"overview\"}"));
        Widget->Navigate(TEXT("overview"));
        Command(TEXT("{\"action\":\"layers\",\"equipment\":true,\"racks\":true,\"pois\":true}"));
        PhaseStart=FPlatformTime::Seconds(); Stage=1; Write(TEXT("warmup"));
    }
    void StartCapture()
    {
        CsvPath=Directory/TEXT("frames.csv");
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(CsvPath),true);
        if(FCsvProfiler::Get()->IsCapturing()) { Finish(TEXT("Another CSV capture is already active")); return; }
        if(bTrace)
        {
            TracePath=Directory/TEXT("trace.utrace");
            Report->SetStringField(TEXT("trace_path"),TracePath);
            if(FTraceAuxiliary::IsConnected()) { Finish(TEXT("Another trace recording is already active")); return; }
            bTraceStarted=FTraceAuxiliary::Start(FTraceAuxiliary::EConnectionType::File,*TracePath,TEXT("cpu,gpu,frame,bookmark,task,loadtime"));
            Report->SetBoolField(TEXT("trace_start_succeeded"),bTraceStarted);
            if(!bTraceStarted) { Finish(TEXT("Trace file recording could not start")); return; }
        }
        FCsvProfiler::Get()->BeginCapture(-1,FPaths::GetPath(CsvPath),FPaths::GetCleanFilename(CsvPath));
        Stage=2; PhaseStart=FPlatformTime::Seconds(); Write(TEXT("starting_capture"));
    }
    void Mark(const FString& Name,double Planned,double Actual)
    {
        TRACE_BOOKMARK(TEXT("TwinPerf:%s"),*Name);
        CSV_EVENT_GLOBAL(TEXT("TwinPerf:%s"),*Name);
        auto Segment=MakeShared<FJsonObject>();
        Segment->SetStringField(TEXT("name"),Name); Segment->SetNumberField(TEXT("planned_seconds"),Planned);
        Segment->SetNumberField(TEXT("actual_seconds"),Actual); Segment->SetNumberField(TEXT("csv_frame"),FCsvProfiler::Get()->GetCaptureFrameNumber());
        Segments.Add(MakeShared<FJsonValueObject>(Segment));
    }
    void Act(const FAction& Action,double At)
    {
        TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinPerfAction);
        const FString Name(Action.Name); Mark(Name,Cycle*CycleSeconds+Action.At,At);
        ++CompletedActions;
        if(Name==TEXT("overview")) Command(TEXT("{\"action\":\"overview\"}"));
        else if(Name==TEXT("all_poi")) Command(TEXT("{\"action\":\"poiDensity\",\"value\":\"all\"}"));
        else if(Name==TEXT("agv") || Name==TEXT("forklift"))
        {
            const FString Id=Name==TEXT("agv")?TEXT("AGV-07"):TEXT("FORK-01");
            if(!Widget->SelectObject(Id,true)) Finish(TEXT("Equipment selection fixture missing: ")+Id);
        }
        else if(Name==TEXT("racks")) Command(TEXT("{\"action\":\"preset\",\"value\":\"racks\"}"));
        else if(Name==TEXT("cargo_focus"))
        {
            Command(TEXT("{\"action\":\"layers\",\"equipment\":true,\"racks\":true,\"pois\":false}"));
            const FVector2D Center(Widget->GetPanelPosition().X*.5,572);
            Camera->FocusOnTarget(CargoPoints[0],2800,FRotator(-65,-90,0),FVector2D(1920,1080),Center,.85f);
        }
        else if(Name==TEXT("cargo_click"))
        {
            bool Found=false;
            for(const auto& Point:CargoPoints)
            {
                FVector2D Screen;
                if(Controller->ProjectWorldLocationToScreen(Point,Screen) && Widget->IsScenePoint(Screen))
                {
                    Widget->HandleSceneClick(Screen);
                    if(Widget->SelectedId.StartsWith(TEXT("MATERIAL:"))) { Found=true; ++CargoClicks; break; }
                }
            }
            if(!Found) { Finish(TEXT("Projected actual cargo could not be selected")); return; }
            Command(TEXT("{\"action\":\"layers\",\"equipment\":true,\"racks\":true,\"pois\":true}"));
        }
        else if(Name.StartsWith(TEXT("panel_"))) Widget->HandleChromeClick(FVector2D(1890,25));
        else if(Name.StartsWith(TEXT("page_"))) Widget->Navigate(Name.Mid(5));
    }
    bool Tick(float DeltaSeconds)
    {
        TRACE_CPUPROFILER_EVENT_SCOPE(GHSTwinPerfDriver);
        if(bFinished) return false;
        const double Now=FPlatformTime::Seconds();
        if(Now-Created>Duration+Warmup+180) { Finish(TEXT("Benchmark deadline exceeded")); return false; }
        if(Stage==0) { if(Discover()) BeginWarmup(); return !bFinished; }
        if(!Controller.IsValid() || !Widget.IsValid() || !Camera.IsValid()) { Finish(TEXT("Benchmark world or UI disappeared")); return false; }
        if(Stage==1) { if(Now-PhaseStart>=Warmup) StartCapture(); return !bFinished; }
        if(Stage==2)
        {
            if(bTrace)
            {
                if(!TraceConnected())
                {
                    if(Now-PhaseStart>5.) Finish(TEXT("Trace did not connect to the requested file"));
                    return !bFinished;
                }
                Report->SetBoolField(TEXT("trace_connected"),true);
                Report->SetStringField(TEXT("trace_destination"),FTraceAuxiliary::GetTraceDestinationString());
            }
            // CoreTicker runs after this frame's scene and Slate work. This frame
            // is setup; the analyzer starts with the following complete frame.
            if(FCsvProfiler::Get()->IsCapturing()) { RouteStart=Now; PreviousRouteTime=0; Stage=3; Mark(TEXT("capture_begin"),0,0); }
            return true;
        }
        if(Stage==3)
        {
            int32 X=0,Y=0; Controller->GetViewportSize(X,Y);
            if(X!=1920 || Y!=1080) { Finish(TEXT("Viewport resized during benchmark")); return false; }
            const double Elapsed=Now-RouteStart;
            // Integrate the part of elapsed wall time inside the fixed orbit interval.
            // Finish the old orbit before issuing the next focus, otherwise its last
            // delta would cancel the newly started camera flight on the boundary frame.
            const int32 CurrentCycle=int32(Elapsed/CycleSeconds);
            for(int32 C=FMath::Max(0,CurrentCycle-1);C<=CurrentCycle;++C)
            {
                const double A=FMath::Max(PreviousRouteTime,C*CycleSeconds+4.);
                const double B=FMath::Min(Elapsed,C*CycleSeconds+12.);
                if(B>A) Camera->OrbitPixels(FVector2D((B-A)*45.,0));
            }
            PreviousRouteTime=Elapsed;
            while(Cycle*CycleSeconds+Actions[NextAction].At<=FMath::Min(Elapsed,Duration-.001))
            {
                Act(Actions[NextAction],Elapsed); if(bFinished) return false;
                if(++NextAction==UE_ARRAY_COUNT(Actions)) { NextAction=0; ++Cycle; }
            }
            if(Elapsed>=Duration)
            {
                Mark(TEXT("capture_end"),Duration,Elapsed);
                Report->SetNumberField(TEXT("measured_seconds"),Elapsed);
                // Include this frame: its scene/Slate work can contain the hitch
                // that crossed Duration. Defer report construction until next tick.
                Stage=4; PhaseStart=Now;
            }
            return true;
        }
        if(Stage==4)
        {
            if(!bFinalReportsCollected)
            {
                Report->SetStringField(TEXT("final_browser_report"),Widget->LastBrowserReport);
                Report->SetStringField(TEXT("final_poi_report"),Widget->GetPOIReport());
                bFinalReportsCollected=true;
            }
            // GPU query drain and final reports are after the inclusive end frame.
            if(Now-PhaseStart>=1.) { CsvComplete=FCsvProfiler::Get()->EndCapture(); Stage=5; PhaseStart=Now; }
            return true;
        }
        if(Stage==5 && CsvComplete.IsValid() && CsvComplete.IsReady())
        {
            CsvPath=CsvComplete.Get();
            if(CsvPath.IsEmpty() || IFileManager::Get().FileSize(*CsvPath)<=0) Finish(TEXT("CSV capture did not produce a file"));
            else if(bTrace)
            {
                if(!RequestTraceStop()) { Finish(TEXT("Trace stop request failed")); return false; }
                Stage=6;PhaseStart=Now;return true;
            }
            else Finish();
            return false;
        }
        if(Stage==6)
        {
            // Trace Stop queues a worker close. IsConnected stays true while either
            // the live or pending data handle exists; false follows flush + IoClose.
            if(FTraceAuxiliary::IsConnected())
            {
                if(Now-PhaseStart>5.) Finish(TEXT("Trace writer did not finish closing"));
                return !bFinished;
            }
            FinalizeTraceFile(true);Finish();return false;
        }
        return true;
    }
};
TUniquePtr<FRun> Run;
FTSTicker::FDelegateHandle Handle;
}

void Startup()
{
    FString Label;
    if(!FParse::Value(FCommandLine::Get(),TEXT("TwinPerf="),Label)) return;
    // Refuse PIE/editor sessions: benchmark completion must never close the user's editor.
#if WITH_EDITOR
    if(!FParse::Param(FCommandLine::Get(),TEXT("game"))) { UE_LOG(LogTemp,Error,TEXT("TwinPerf editor binary requires explicit -game")); return; }
#endif
    if(!FApp::IsGame()) { UE_LOG(LogTemp,Error,TEXT("TwinPerf requires standalone -game or a packaged game")); return; }
    bool bSafeLabel=!Label.IsEmpty() && Label.Len()<=64;
    for(TCHAR C:Label) bSafeLabel=bSafeLabel && (FChar::IsAlnum(C)||C==TEXT('_')||C==TEXT('-'));
    if(!bSafeLabel)
    { UE_LOG(LogTemp,Error,TEXT("TwinPerf label must contain only letters, digits, _ or -")); return; }
    Run=MakeUnique<FRun>(); Run->Label=Label;
    FParse::Value(FCommandLine::Get(),TEXT("TwinPerfVariant="),Run->Variant);
    if(Run->Variant.IsEmpty()) Run->Variant=TEXT("baseline");
    FParse::Value(FCommandLine::Get(),TEXT("TwinPerfDuration="),Run->Duration);
    FParse::Value(FCommandLine::Get(),TEXT("TwinPerfWarmup="),Run->Warmup);
    Run->Duration=FMath::Clamp(Run->Duration,90.,7200.); Run->Warmup=FMath::Clamp(Run->Warmup,15.,300.);
    Run->bTrace=FParse::Param(FCommandLine::Get(),TEXT("TwinPerfTrace"));
    FString OutputRoot=FPaths::ProjectSavedDir()/TEXT("TwinPerf");
    FParse::Value(FCommandLine::Get(),TEXT("TwinPerfOutput="),OutputRoot);
    Run->Directory=FPaths::ConvertRelativePathToFull(OutputRoot/(Label+TEXT("_")+FDateTime::UtcNow().ToString(TEXT("%Y%m%d_%H%M%S"))));
    IFileManager::Get().MakeDirectory(*Run->Directory,true);
    Run->Report->SetStringField(TEXT("label"),Label); Run->Report->SetNumberField(TEXT("route_version"),2);
    Run->Report->SetNumberField(TEXT("process_id"),FPlatformProcess::GetCurrentProcessId());
    Run->Report->SetStringField(TEXT("variant"),Run->Variant);
    Run->Report->SetStringField(TEXT("runtime"),WITH_EDITOR?TEXT("editor-game"):TEXT("packaged"));
    Run->Report->SetStringField(TEXT("build_configuration"),LexToString(FApp::GetBuildConfiguration()));
    Run->Report->SetBoolField(TEXT("render_offscreen"),FParse::Param(FCommandLine::Get(),TEXT("RenderOffscreen")));
    Run->Report->SetStringField(TEXT("engine_version"),FEngineVersion::Current().ToString());
    Run->Report->SetStringField(TEXT("cpu"),FPlatformMisc::GetCPUBrand());
    Run->Report->SetStringField(TEXT("gpu"),FPlatformMisc::GetPrimaryGPUBrand());
    Run->Report->SetNumberField(TEXT("duration_seconds"),Run->Duration); Run->Report->SetNumberField(TEXT("warmup_seconds"),Run->Warmup);
    Run->Report->SetNumberField(TEXT("route_cycle_seconds"),CycleSeconds); Run->Report->SetBoolField(TEXT("trace_enabled"),Run->bTrace);
    Run->Report->SetBoolField(TEXT("trace_connected"),false);
    Run->Report->SetBoolField(TEXT("trace_start_succeeded"),false);
    Run->Report->SetBoolField(TEXT("assets_saved"),false);
    Run->Report->SetStringField(TEXT("input_scope"),TEXT("Native HUD/camera public APIs; material hit uses real screen projection. Not OS input latency."));
    Run->Report->SetStringField(TEXT("poi_mode"),TEXT("all; production layout cap remains 32"));
    Run->Write(TEXT("discovering"));
    Handle=FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float Delta){return Run && Run->Tick(Delta);}));
}
void Shutdown()
{
    if(Handle.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(Handle); Handle.Reset(); }
    if(Run) { Run->StopTraceAndVerify();Run->Restore(); }
    Run.Reset();
}
}
#else
namespace GHSTwinPerformance { void Startup() {} void Shutdown() {} }
#endif
#else
namespace GHSTwinPerformance { void Startup() {} void Shutdown() {} }
#endif
