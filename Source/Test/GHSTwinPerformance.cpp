#include "GHSTwinPerformance.h"

#if !UE_BUILD_SHIPPING
#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehousePlayerController.h"
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
    FString Label, Directory, CsvPath, Error;
    double Created=FPlatformTime::Seconds(), PhaseStart=0, RouteStart=0, Duration=90, Warmup=15;
    double PreviousRouteTime=0;
    int32 Stage=0, NextAction=0, Cycle=0, CompletedActions=0, CargoClicks=0;
    bool bTrace=false, bFinished=false, bFinalReportsCollected=false;
    TWeakObjectPtr<AGHSWarehousePlayerController> Controller;
    TWeakObjectPtr<AGHSWarehouseCameraPawn> Camera;
    TWeakObjectPtr<UGHSTwinHUDWidget> Widget;
    TArray<FVector> CargoPoints;
    TMap<FString,FString> OriginalCVars;
    TSharedRef<FJsonObject> Report=MakeShared<FJsonObject>();
    TArray<TSharedPtr<FJsonValue>> Segments;
    TSharedFuture<FString> CsvComplete;

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
        for(const auto& Entry:OriginalCVars) Console(Entry.Key+TEXT(" ")+Entry.Value);
        OriginalCVars.Empty();
    }
    void Finish(const FString& Failure=FString())
    {
        if(bFinished) return;
        if(!Failure.IsEmpty()) Error=Failure;
        if(FCsvProfiler::Get()->IsCapturing()) FCsvProfiler::Get()->EndCapture();
        if(bTrace) Console(TEXT("Trace.Stop"));
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
        FString Text;
        if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/rack-slots.json")))) return false;
        auto Root=ParseJson(Text); if(!Root) return false;
        const TArray<TSharedPtr<FJsonValue>>* Models=nullptr;
        if(!Root->TryGetArrayField(TEXT("meshes"),Models)) return false;
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
                    return true;
                }
            }
        }
        return false;
    }
    void BeginWarmup()
    {
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
        FCsvProfiler::Get()->BeginCapture(-1,FPaths::GetPath(CsvPath),FPaths::GetCleanFilename(CsvPath));
        if(bTrace) Console(FString::Printf(TEXT("Trace.File \"%s\" cpu,gpu,frame,bookmark,task,loadtime"),*(Directory/TEXT("trace.utrace"))));
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
            else Finish();
            return false;
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
    FParse::Value(FCommandLine::Get(),TEXT("TwinPerfDuration="),Run->Duration);
    FParse::Value(FCommandLine::Get(),TEXT("TwinPerfWarmup="),Run->Warmup);
    Run->Duration=FMath::Clamp(Run->Duration,90.,7200.); Run->Warmup=FMath::Clamp(Run->Warmup,15.,300.);
    Run->bTrace=FParse::Param(FCommandLine::Get(),TEXT("TwinPerfTrace"));
    FString OutputRoot=FPaths::ProjectSavedDir()/TEXT("TwinPerf");
    FParse::Value(FCommandLine::Get(),TEXT("TwinPerfOutput="),OutputRoot);
    Run->Directory=FPaths::ConvertRelativePathToFull(OutputRoot/(Label+TEXT("_")+FDateTime::UtcNow().ToString(TEXT("%Y%m%d_%H%M%S"))));
    IFileManager::Get().MakeDirectory(*Run->Directory,true);
    Run->Report->SetStringField(TEXT("label"),Label); Run->Report->SetNumberField(TEXT("route_version"),2);
    Run->Report->SetStringField(TEXT("runtime"),WITH_EDITOR?TEXT("editor-game"):TEXT("packaged"));
    Run->Report->SetStringField(TEXT("build_configuration"),LexToString(FApp::GetBuildConfiguration()));
    Run->Report->SetBoolField(TEXT("render_offscreen"),FParse::Param(FCommandLine::Get(),TEXT("RenderOffscreen")));
    Run->Report->SetStringField(TEXT("engine_version"),FEngineVersion::Current().ToString());
    Run->Report->SetStringField(TEXT("cpu"),FPlatformMisc::GetCPUBrand());
    Run->Report->SetStringField(TEXT("gpu"),FPlatformMisc::GetPrimaryGPUBrand());
    Run->Report->SetNumberField(TEXT("duration_seconds"),Run->Duration); Run->Report->SetNumberField(TEXT("warmup_seconds"),Run->Warmup);
    Run->Report->SetNumberField(TEXT("route_cycle_seconds"),CycleSeconds); Run->Report->SetBoolField(TEXT("trace_enabled"),Run->bTrace);
    Run->Report->SetBoolField(TEXT("assets_saved"),false);
    Run->Report->SetStringField(TEXT("input_scope"),TEXT("Native HUD/camera public APIs; material hit uses real screen projection. Not OS input latency."));
    Run->Report->SetStringField(TEXT("poi_mode"),TEXT("all; production layout cap remains 32"));
    Run->Write(TEXT("discovering"));
    Handle=FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float Delta){return Run && Run->Tick(Delta);}));
}
void Shutdown()
{
    if(Handle.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(Handle); Handle.Reset(); }
    if(Run) Run->Restore();
    Run.Reset();
}
}
#else
namespace GHSTwinPerformance { void Startup() {} void Shutdown() {} }
#endif
#else
namespace GHSTwinPerformance { void Startup() {} void Shutdown() {} }
#endif
