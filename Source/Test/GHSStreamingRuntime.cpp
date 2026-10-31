#include "GHSStreamingRuntime.h"
#include "Async/Async.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "DynamicRHI.h"
#include "EngineGlobals.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "Misc/CommandLine.h"
#include "Misc/CoreDelegates.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PipelineStateCache.h"
#include "RenderTimer.h"
#include "NVENC.h"
#include "IPixelStreaming2Module.h"
#include "PixelStreaming2Delegates.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#endif

namespace GHSStreamingRuntime
{
namespace
{
FStartupOptions StartupOptions;
FDelegateHandle EngineReadyHandle,SoftwareFallbackHandle;
bool bNVENCValidated=false;
bool bStartupRejected=false;
bool bStandbyLeased=false;
FString StandbyMode=TEXT("active");

void RejectStartup(const FString& Reason)
{
    if(bStartupRejected) return;
    bStartupRejected=true;
    UE_LOG(LogTemp,Error,TEXT("GHS_PS2_CONFIGURATION_REJECTED %s"),*Reason);
    // Explicit NVIDIA selection must never silently turn into software encoding.
    if(IPixelStreaming2Module::IsAvailable()) IPixelStreaming2Module::Get().StopStreaming();
    FPlatformMisc::RequestExitWithStatus(false,1);
}

void ValidateEncoder()
{
    if(bStartupRejected) return;
    if(StartupOptions.Encoder==TEXT("NVIDIA"))
    {
        const auto* Codec=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.Encoder.Codec"));
        const auto* Negotiate=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.WebRTC.NegotiateCodecs"));
        FString Error;
        // PS2 can fall back during OnReady, before engine initialization completes.
        // Re-read the effective codec as well as the NVENC API after its factory setup.
        bNVENCValidated=ValidateNvidiaPolicy(GDynamicRHI && IsRHIDeviceNVIDIA(),FAPI::Get<FNVENC>().IsValid(),
            Codec?Codec->GetString():FString(),!Negotiate || Negotiate->GetBool(),Error);
        if(!bNVENCValidated)
        {
            RejectStartup(Error);
            return;
        }
    }
    auto* Decouple=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.DecoupleFramerate"));
    auto* CaptureFPS=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.WebRTC.Fps"));
    UE_LOG(LogTemp,Display,TEXT("GHS_PS2_CONFIG encoder=%s nvencApiValidated=%d fixedTargetFps=%d captureFps=%d decoupledCapture=%d fixedSimulationDelta=0"),
        *StartupOptions.Encoder,int32(bNVENCValidated),StartupOptions.FixedFPS,CaptureFPS?CaptureFPS->GetInt():-1,Decouple?Decouple->GetInt():-1);
}

bool ValidBudget(const FBudget& Budget)
{
    return Budget.Sequence>0 && Budget.Sequence<=9007199254740991LL && (Budget.FPS==0 || (Budget.FPS>=5 && Budget.FPS<=120))
        && FMath::IsFinite(Budget.MinBitrateMbps) && FMath::IsFinite(Budget.MaxBitrateMbps)
        && Budget.MinBitrateMbps>=1 && Budget.MaxBitrateMbps<=200 && Budget.MinBitrateMbps<=Budget.MaxBitrateMbps
        && (Budget.Mode==TEXT("active") || Budget.Mode==TEXT("warming") || Budget.Mode==TEXT("standby"));
}

bool AtomicWrite(const FString& Destination,const FString& Json)
{
    const FString Temporary=Destination+FString::Printf(TEXT(".tmp-%u"),FPlatformProcess::GetCurrentProcessId());
    if(!FFileHelper::SaveStringToFile(Json,*Temporary,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)) return false;
#if PLATFORM_WINDOWS
    // MoveFileEx replaces in one filesystem operation, so readers never observe partial JSON.
    return !!::MoveFileExW(*Temporary,*Destination,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
#else
    return IFileManager::Get().Move(*Destination,*Temporary,true,true,false,true);
#endif
}

class FBridge
{
public:
    explicit FBridge(const FString& InDirectory):Directory(InDirectory),PreviousTime(FPlatformTime::Seconds()),PreviousFrame(GFrameCounter) {}

    bool Tick(float)
    {
        const FString BudgetPath=Directory/TEXT("budget.json");
        const int64 Size=IFileManager::Get().FileSize(*BudgetPath);
        FString NextError;
        if(Size>0 && Size<=16384)
        {
            FString Json;
            if(FFileHelper::LoadFileToString(Json,*BudgetPath))
            {
                FBudget Budget;
                if(ParseBudget(Json,Budget,NextError))
                {
                    if(Budget.Sequence>Sequence)
                    {
                        if(ApplyBudget(Budget,Sequence,NextError))
                            UE_LOG(LogTemp,Display,TEXT("GHS_STREAM_BUDGET_APPLIED sequence=%lld fps=%d bitrate=%.1f..%.1f"),Sequence,Budget.FPS,Budget.MinBitrateMbps,Budget.MaxBitrateMbps);
                    }
                    else if(Budget.Sequence<Sequence) NextError=TEXT("Budget sequence is older than the acknowledged sequence");
                }
            }
            else NextError=TEXT("Budget file could not be read; previous budget retained");
        }
        else if(Size>16384) NextError=TEXT("Budget file exceeds 16384 bytes");
        else if(Size==0) NextError=TEXT("Budget file is empty; previous budget retained");
        if(!NextError.IsEmpty() && NextError!=Error) UE_LOG(LogTemp,Warning,TEXT("GHS_STREAM_BUDGET_REJECTED %s"),*NextError);
        Error=NextError;

        const double GPUms=GDynamicRHI ? FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles()) : 0.;
        if(FMath::IsFinite(GPUms) && GPUms>0 && GPUms<10000) { GPUTimeSum+=GPUms; ++GPUSamples; }
        // Sample engine thread timings with the existing 4 Hz budget tick;
        // these are diagnostics, not additional per-frame file writes.
        const uint32 ThreadCycles[]={GGameThreadTime,GRenderThreadTime,GRHIThreadTime};
        for(int32 Index=0;Index<3;++Index)
        {
            const double Milliseconds=FPlatformTime::ToMilliseconds(ThreadCycles[Index]);
            if(FMath::IsFinite(Milliseconds) && Milliseconds>0 && Milliseconds<10000)
            { ThreadTimeSums[Index]+=Milliseconds; ++ThreadSamples[Index]; }
        }
        const double Now=FPlatformTime::Seconds();
        if(Now-PreviousTime>=1.)
        {
            auto Metrics=MakeShared<FJsonObject>();
            Metrics->SetNumberField(TEXT("version"),1);
            Metrics->SetNumberField(TEXT("sequence"),double(Sequence));
            Metrics->SetNumberField(TEXT("frameCounter"),double(GFrameCounter));
            Metrics->SetNumberField(TEXT("pid"),FPlatformProcess::GetCurrentProcessId());
            const FDateTime UTC=FDateTime::UtcNow();
            Metrics->SetStringField(TEXT("utc"),UTC.ToIso8601());
            Metrics->SetNumberField(TEXT("timestampMs"),double(UTC.ToUnixTimestamp())*1000+UTC.GetMillisecond());
            Metrics->SetNumberField(TEXT("actualFps"),double(GFrameCounter-PreviousFrame)/(Now-PreviousTime));
            auto AddCVar=[&](const TCHAR* Key,const TCHAR* Name)
            {
                if(const auto* Var=IConsoleManager::Get().FindConsoleVariable(Name)) Metrics->SetNumberField(Key,Var->GetFloat());
                else Metrics->SetField(Key,MakeShared<FJsonValueNull>());
            };
            AddCVar(TEXT("appliedFps"),TEXT("t.MaxFPS"));
            AddCVar(TEXT("captureFps"),TEXT("PixelStreaming2.WebRTC.Fps"));
            AddCVar(TEXT("decoupledCapture"),TEXT("PixelStreaming2.DecoupleFramerate"));
            // Read the engine's effective settings in Shipping as well as Development.
            // A small compiler pool retains all precaching; the remaining count lets
            // startup/first-interaction checks distinguish compilation from rendering.
            Metrics->SetBoolField(TEXT("psoPrecachingEnabled"),PipelineStateCache::IsPSOPrecachingEnabled());
            AddCVar(TEXT("psoPrecompileThreadPoolSize"),TEXT("r.pso.PrecompileThreadPoolSize"));
            AddCVar(TEXT("psoPrecompileThreadPoolPercent"),TEXT("r.pso.PrecompileThreadPoolPercentOfHardwareThreads"));
            Metrics->SetNumberField(TEXT("psoActivePrecacheRequests"),PipelineStateCache::NumActivePrecacheRequests());
            Metrics->SetStringField(TEXT("streamingPlugin"),TEXT("PixelStreaming2"));
            Metrics->SetStringField(TEXT("encoderPolicy"),StartupOptions.Encoder);
            Metrics->SetBoolField(TEXT("nvencApiValidated"),bNVENCValidated);
            Metrics->SetNumberField(TEXT("fixedTargetFps"),StartupOptions.FixedFPS);
            Metrics->SetStringField(TEXT("standbyMode"),StandbyMode);
            AddCVar(TEXT("screenPercentage"),TEXT("r.ScreenPercentage"));
            // Report the effective AA history independently from the native
            // render percentage, so a remote quality check cannot confuse them.
            AddCVar(TEXT("antiAliasingMethod"),TEXT("r.AntiAliasingMethod"));
            AddCVar(TEXT("tsrHistoryPercentage"),TEXT("r.TSR.History.ScreenPercentage"));
            if(GPUSamples) Metrics->SetNumberField(TEXT("gpuMs"),GPUTimeSum/GPUSamples);
            else Metrics->SetField(TEXT("gpuMs"),MakeShared<FJsonValueNull>());
            const TCHAR* ThreadKeys[]={TEXT("gameMs"),TEXT("renderMs"),TEXT("rhiMs")};
            for(int32 Index=0;Index<3;++Index)
            {
                if(ThreadSamples[Index]) Metrics->SetNumberField(ThreadKeys[Index],ThreadTimeSums[Index]/ThreadSamples[Index]);
                else Metrics->SetField(ThreadKeys[Index],MakeShared<FJsonValueNull>());
                ThreadTimeSums[Index]=0; ThreadSamples[Index]=0;
            }
            Metrics->SetStringField(TEXT("gpuMetric"),TEXT("UE RHI GPU frame cycles average; not an isolated GPU capacity guarantee"));
            Metrics->SetStringField(TEXT("error"),Error);
            FString Json; FJsonSerializer::Serialize(Metrics,TJsonWriterFactory<>::Create(&Json));
            if(!AtomicWrite(Directory/TEXT("metrics.json"),Json))
                UE_LOG(LogTemp,Warning,TEXT("GHS_STREAM_METRICS_WRITE_FAILED"));
            PreviousTime=Now; PreviousFrame=GFrameCounter; GPUTimeSum=0; GPUSamples=0;
        }
        return true;
    }
private:
    FString Directory,Error;
    int64 Sequence=0;
    double PreviousTime=0,GPUTimeSum=0;
    uint64 PreviousFrame=0;
    int32 GPUSamples=0;
    double ThreadTimeSums[3]={};
    int32 ThreadSamples[3]={};
};
TUniquePtr<FBridge> Bridge;
FTSTicker::FDelegateHandle Ticker;
}

bool ParseBudget(const FString& Json,FBudget& Out,FString& Error)
{
    Error.Reset();
    if(Json.Len()>16384) { Error=TEXT("Budget exceeds 16384 characters"); return false; }
    TSharedPtr<FJsonObject> Root;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Root) || !Root)
    { Error=TEXT("Budget must be a complete JSON object"); return false; }
    static const TSet<FString> Allowed={TEXT("version"),TEXT("sequence"),TEXT("fps"),TEXT("minBitrateMbps"),TEXT("startBitrateMbps"),TEXT("maxBitrateMbps"),TEXT("mode")};
    for(const auto& Pair:Root->Values)
        if(!Allowed.Contains(FString(Pair.Key.Len(), *Pair.Key))) { Error=TEXT("Budget contains an unsupported field"); return false; }
    double Version=0,Sequence=0,FPS=0,Min=0,Max=0;
    const auto Number=[&](const TCHAR* Name,double& Value)
    {
        const auto* Entry=Root->Values.Find(Name);
        return Entry && Entry->IsValid() && (*Entry)->Type==EJson::Number && (*Entry)->TryGetNumber(Value) && FMath::IsFinite(Value);
    };
    if(!Number(TEXT("version"),Version) || Version!=1 || !Number(TEXT("sequence"),Sequence)
        || Sequence<1 || Sequence>9007199254740991. || FMath::FloorToDouble(Sequence)!=Sequence
        || !Number(TEXT("fps"),FPS) || (FPS!=0 && (FPS<5 || FPS>120)) || FMath::FloorToDouble(FPS)!=FPS
        || !Number(TEXT("minBitrateMbps"),Min) || !Number(TEXT("maxBitrateMbps"),Max)
        || Min<1 || Max>200 || Min>Max)
    { Error=TEXT("Budget requires version 1, positive integer sequence, fps 0 (uncapped) or integer 5..120 and ordered bitrates 1..200 Mbps"); return false; }
    if(Root->HasField(TEXT("startBitrateMbps")))
    {
        double Start=0;
        if(!Number(TEXT("startBitrateMbps"),Start) || Start<Min || Start>Max)
        { Error=TEXT("Start bitrate must be between min and max; it applies at process startup only"); return false; }
    }
    FBudget Parsed; Parsed.Sequence=int64(Sequence); Parsed.FPS=int32(FPS); Parsed.MinBitrateMbps=Min; Parsed.MaxBitrateMbps=Max;
    if(Root->HasField(TEXT("mode")))
    {
        const auto& Mode=Root->Values[TEXT("mode")];
        if(!Mode.IsValid() || Mode->Type!=EJson::String || !Mode->TryGetString(Parsed.Mode)
            || (Parsed.Mode!=TEXT("warming") && Parsed.Mode!=TEXT("standby") && Parsed.Mode!=TEXT("active")))
        { Error=TEXT("Budget mode must be warming, standby or active"); return false; }
    }
    Out=Parsed; return true;
}

bool ValidateBudgetTransition(const FBudget& Budget,const FStartupOptions& Options,bool bAlreadyLeased,FString& Error)
{
    Error.Reset();
    if(!ValidBudget(Budget)) { Error=TEXT("Invalid runtime budget"); return false; }
    const bool bStandby=Budget.Mode==TEXT("standby");
    if(Budget.Mode!=TEXT("active") && (!Options.bStandbyCapable || bAlreadyLeased))
    { Error=TEXT("Only an explicitly permitted pristine instance may warm or enter standby"); return false; }
    if(bStandby && Budget.FPS!=5)
    { Error=TEXT("Standby uses exactly 5 render FPS"); return false; }
    if(!bStandby && Options.FixedFPS>0 && Budget.FPS!=Options.FixedFPS)
    { Error=TEXT("Fixed FPS is enabled; active or warming budgets cannot change its target"); return false; }
    return true;
}

bool ApplyBudget(const FBudget& Budget,int64& LastSequence,FString& Error)
{
    Error.Reset();
    if(!ValidBudget(Budget) || Budget.Sequence<=LastSequence)
    { Error=TEXT("Invalid or already acknowledged budget"); return false; }
    if(!ValidateBudgetTransition(Budget,StartupOptions,bStandbyLeased,Error)) return false;
    auto* FrameLimit=IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS"));
    auto* MinBitrate=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.WebRTC.MinBitrate"));
    auto* MaxBitrate=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.WebRTC.MaxBitrate"));
    if(!FrameLimit || !MinBitrate || !MaxBitrate)
    { Error=TEXT("Pixel Streaming runtime variables are not ready"); return false; }
    const int32 Min=FMath::RoundToInt(Budget.MinBitrateMbps*1000000),Max=FMath::RoundToInt(Budget.MaxBitrateMbps*1000000);
    // Keep PS2's positive negotiated RTP ceiling unchanged. The legacy FPS=0
    // plugin patch is deliberately not carried into EpicRtc. Render-only budgets
    // may still remove t.MaxFPS without sending zero to the capture/encode clock.
    // These three variables are the entire control surface. No GEngine->Exec or user commands.
    FrameLimit->Set(Budget.FPS,ECVF_SetByConsole);
    if(Min>MaxBitrate->GetInt()) { MaxBitrate->Set(Max,ECVF_SetByConsole); MinBitrate->Set(Min,ECVF_SetByConsole); }
    else { MinBitrate->Set(Min,ECVF_SetByConsole); MaxBitrate->Set(Max,ECVF_SetByConsole); }
    if(FrameLimit->GetInt()!=Budget.FPS || MinBitrate->GetInt()!=Min || MaxBitrate->GetInt()!=Max)
    { Error=TEXT("Runtime did not acknowledge the requested budget"); return false; }
    StandbyMode=Budget.Mode;
    if(Budget.Mode==TEXT("active")) bStandbyLeased=true;
    LastSequence=Budget.Sequence; return true;
}

bool ParseStartupOptions(const TCHAR* CommandLine,FStartupOptions& Out,FString& Error)
{
    Error.Reset();
    FStartupOptions Parsed;
    Parsed.bStandbyCapable=FParse::Param(CommandLine,TEXT("GHSStandbyCapable"));
    FParse::Value(CommandLine,TEXT("PixelStreamingEncoder="),Parsed.Encoder);
    if(Parsed.Encoder.Equals(TEXT("NVIDIA"),ESearchCase::IgnoreCase)) Parsed.Encoder=TEXT("NVIDIA");
    else if(Parsed.Encoder.Equals(TEXT("Auto"),ESearchCase::IgnoreCase)) Parsed.Encoder=TEXT("Auto");
    else { Error=TEXT("PixelStreamingEncoder must be NVIDIA or Auto"); return false; }
    FString FPS;
    if(FParse::Value(CommandLine,TEXT("FixedFPS="),FPS))
    {
        if(FPS.IsEmpty() || !FPS.IsNumeric() || !LexTryParseString(Parsed.FixedFPS,*FPS)
            || Parsed.FixedFPS<5 || Parsed.FixedFPS>120 || FPS!=FString::FromInt(Parsed.FixedFPS))
        { Error=TEXT("FixedFPS must be an integer between 5 and 120"); return false; }
    }
    if(Parsed.FixedFPS>0 && (FParse::Param(CommandLine,TEXT("UseFixedTimeStep")) || FParse::Param(CommandLine,TEXT("Deterministic"))))
    { Error=TEXT("FixedFPS targets real render/capture FPS and cannot be combined with a fixed simulation timestep"); return false; }
    Out=Parsed; return true;
}

bool ValidateNvidiaPolicy(bool bNvidiaRHI,bool bNVENCAPIAvailable,const FString& ActualCodec,bool bNegotiateCodecs,FString& Error)
{
    Error.Reset();
    if(!bNvidiaRHI || !bNVENCAPIAvailable)
    { Error=TEXT("NVIDIA was requested but the active RHI / NVENC API is unavailable. Check the GPU adapter and driver, or select Auto."); return false; }
    if(!ActualCodec.Equals(TEXT("H264"),ESearchCase::IgnoreCase) && !ActualCodec.Equals(TEXT("AV1"),ESearchCase::IgnoreCase))
    { Error=TEXT("NVIDIA mode requires an effective H264/AV1 codec; PixelStreaming2 may have fallen back during hardware encoder initialization."); return false; }
    if(bNegotiateCodecs)
    { Error=TEXT("NVIDIA mode cannot negotiate software codecs; the effective codec negotiation setting must be disabled."); return false; }
    return true;
}

void Startup()
{
    if(Bridge) return;
    FString StartupError;
    if(!ParseStartupOptions(FCommandLine::Get(),StartupOptions,StartupError)) { RejectStartup(StartupError); return; }
    StandbyMode=StartupOptions.bStandbyCapable?TEXT("warming"):TEXT("active");
    bStandbyLeased=false;
    if(StartupOptions.FixedFPS>0)
    {
        auto* FrameLimit=IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS"));
        auto* CaptureFPS=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.WebRTC.Fps"));
        if(!FrameLimit || !CaptureFPS) { RejectStartup(TEXT("PixelStreaming2 settings were not loaded")); return; }
        FrameLimit->Set(StartupOptions.FixedFPS,ECVF_SetByCommandline);
        CaptureFPS->Set(StartupOptions.FixedFPS,ECVF_SetByCommandline);
    }
    if(StartupOptions.Encoder==TEXT("NVIDIA"))
    {
        auto* Codec=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.Encoder.Codec"));
        auto* Negotiate=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming2.WebRTC.NegotiateCodecs"));
        const FString CodecName=Codec?Codec->GetString():FString();
        if(!Codec || !Negotiate || (CodecName!=TEXT("H264") && CodecName!=TEXT("AV1")))
        { RejectStartup(TEXT("NVIDIA mode requires H264 or AV1 in PixelStreaming2")); return; }
        // Prevent negotiation of a software-only codec while NVIDIA is explicitly required.
        Negotiate->Set(false,ECVF_SetByCommandline);
        // Bind during the project's Default loading phase, before PS2's OnReady
        // factory checks at OnAllModuleLoadingPhasesComplete can signal a fallback.
        SoftwareFallbackHandle=UPixelStreaming2Delegates::Get()->OnFallbackToSoftwareEncodingNative.AddLambda([]()
        {
            AsyncTask(ENamedThreads::GameThread,[](){ RejectStartup(TEXT("NVIDIA mode rejected a PixelStreaming2 software encoder fallback; check GPU codec support and NVENC session capacity.")); });
        });
    }
    EngineReadyHandle=FCoreDelegates::OnFEngineLoopInitComplete.AddStatic(&ValidateEncoder);
    FString Directory;
    if(!FParse::Value(FCommandLine::Get(),TEXT("GHSStreamControlDir="),Directory)) return;
    if(Directory.IsEmpty() || FPaths::IsRelative(Directory) || Directory.StartsWith(TEXT("\\\\")) || Directory.StartsWith(TEXT("//")))
    { UE_LOG(LogTemp,Warning,TEXT("GHS_STREAM_CONTROL_REJECTED requires an absolute local directory")); return; }
    FPaths::NormalizeDirectoryName(Directory);
    if(!IFileManager::Get().DirectoryExists(*Directory))
    { UE_LOG(LogTemp,Warning,TEXT("GHS_STREAM_CONTROL_REJECTED directory must already exist")); return; }
    Bridge=MakeUnique<FBridge>(Directory);
    Ticker=FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float Delta){ return Bridge && Bridge->Tick(Delta); }),.25f);
    UE_LOG(LogTemp,Display,TEXT("GHS_STREAM_CONTROL_READY"));
}

void Shutdown()
{
    FCoreDelegates::OnFEngineLoopInitComplete.Remove(EngineReadyHandle); EngineReadyHandle.Reset();
    if(SoftwareFallbackHandle.IsValid() && IPixelStreaming2Module::IsAvailable())
        UPixelStreaming2Delegates::Get()->OnFallbackToSoftwareEncodingNative.Remove(SoftwareFallbackHandle);
    SoftwareFallbackHandle.Reset();
    if(Ticker.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(Ticker); Ticker.Reset(); }
    Bridge.Reset();
}
}
