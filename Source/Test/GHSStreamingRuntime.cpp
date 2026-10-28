#include "GHSStreamingRuntime.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "EngineGlobals.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#endif

namespace GHSStreamingRuntime
{
namespace
{
bool ValidBudget(const FBudget& Budget)
{
    return Budget.Sequence>0 && Budget.Sequence<=9007199254740991LL && (Budget.FPS==0 || (Budget.FPS>=5 && Budget.FPS<=120))
        && FMath::IsFinite(Budget.MinBitrateMbps) && FMath::IsFinite(Budget.MaxBitrateMbps)
        && Budget.MinBitrateMbps>=1 && Budget.MaxBitrateMbps<=200 && Budget.MinBitrateMbps<=Budget.MaxBitrateMbps;
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

        const double GPUms=FPlatformTime::ToMilliseconds(GGPUFrameTime);
        if(FMath::IsFinite(GPUms) && GPUms>0 && GPUms<10000) { GPUTimeSum+=GPUms; ++GPUSamples; }
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
            AddCVar(TEXT("captureFps"),TEXT("PixelStreaming.WebRTC.Fps"));
            AddCVar(TEXT("screenPercentage"),TEXT("r.ScreenPercentage"));
            if(GPUSamples) Metrics->SetNumberField(TEXT("gpuMs"),GPUTimeSum/GPUSamples);
            else Metrics->SetField(TEXT("gpuMs"),MakeShared<FJsonValueNull>());
            Metrics->SetStringField(TEXT("gpuMetric"),TEXT("UE GGPUFrameTime average; not an isolated GPU capacity guarantee"));
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
    static const TSet<FString> Allowed={TEXT("version"),TEXT("sequence"),TEXT("fps"),TEXT("minBitrateMbps"),TEXT("startBitrateMbps"),TEXT("maxBitrateMbps")};
    for(const auto& Pair:Root->Values)
        if(!Allowed.Contains(Pair.Key)) { Error=TEXT("Budget contains an unsupported field"); return false; }
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
    Out=Parsed; return true;
}

bool ApplyBudget(const FBudget& Budget,int64& LastSequence,FString& Error)
{
    Error.Reset();
    if(!ValidBudget(Budget) || Budget.Sequence<=LastSequence)
    { Error=TEXT("Invalid or already acknowledged budget"); return false; }
    auto* FrameLimit=IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS"));
    auto* MinBitrate=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming.WebRTC.MinBitrate"));
    auto* MaxBitrate=IConsoleManager::Get().FindConsoleVariable(TEXT("PixelStreaming.WebRTC.MaxBitrate"));
    if(!FrameLimit || !MinBitrate || !MaxBitrate)
    { Error=TEXT("Pixel Streaming runtime variables are not ready"); return false; }
    const int32 Min=FMath::RoundToInt(Budget.MinBitrateMbps*1000000),Max=FMath::RoundToInt(Budget.MaxBitrateMbps*1000000);
    // Keep negotiated RTP parameters unchanged. The project PixelStreaming patch omits
    // max_framerate for startup FPS=0; coupled capture follows actual rendered frames.
    // A finite configured ceiling still uses only t.MaxFPS for temporary workload control.
    // These three variables are the entire control surface. No GEngine->Exec or user commands.
    FrameLimit->Set(Budget.FPS,ECVF_SetByConsole);
    if(Min>MaxBitrate->GetInt()) { MaxBitrate->Set(Max,ECVF_SetByConsole); MinBitrate->Set(Min,ECVF_SetByConsole); }
    else { MinBitrate->Set(Min,ECVF_SetByConsole); MaxBitrate->Set(Max,ECVF_SetByConsole); }
    if(FrameLimit->GetInt()!=Budget.FPS || MinBitrate->GetInt()!=Min || MaxBitrate->GetInt()!=Max)
    { Error=TEXT("Runtime did not acknowledge the requested budget"); return false; }
    LastSequence=Budget.Sequence; return true;
}

void Startup()
{
    if(Bridge) return;
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
    if(Ticker.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(Ticker); Ticker.Reset(); }
    Bridge.Reset();
}
}
