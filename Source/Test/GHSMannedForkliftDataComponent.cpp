#include "GHSMannedForkliftDataComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"

namespace
{
    bool ParsePositiveIdentifier(const FString& Value, int32& Out)
    {
        if (Value.IsEmpty()) return false;
        int32 Number=0;
        for (const TCHAR Character : Value)
        {
            if (Character<TEXT('0') || Character>TEXT('9')) return false;
            const int32 Digit=Character-TEXT('0');
            if (Number>(MAX_int32-Digit)/10) return false;
            Number=Number*10+Digit;
        }
        if (Number==0) return false;
        Out=Number;
        return true;
    }
    bool IsMeasuredState(EGHSMannedForkliftStatus Status)
    {
        return Status==EGHSMannedForkliftStatus::Running || Status==EGHSMannedForkliftStatus::Idle
            || Status==EGHSMannedForkliftStatus::Warning;
    }
}

UGHSMannedForkliftDataComponent::UGHSMannedForkliftDataComponent()
{
    PrimaryComponentTick.bCanEverTick=false;
}

bool UGHSMannedForkliftDataComponent::InitializeFromActorTags()
{
    const AActor* Owner=GetOwner();
    if (!IsValid(Owner) || !Owner->ActorHasTag(TEXT("NormalWarehouseMannedForklift"))) return false;
    FString TwinId;
    bool bFound=false;
    for (const FName Tag : Owner->Tags)
    {
        const FString Value=Tag.ToString();
        if (!Value.StartsWith(TEXT("TwinId="),ESearchCase::CaseSensitive)) continue;
        if (bFound) return false;
        bFound=true;
        TwinId=Value.Mid(7);
    }
    if (!bFound || !TwinId.RemoveFromStart(TEXT("GHN_MannedForklift_"),ESearchCase::CaseSensitive)) return false;
    return InitializeIdentity(TEXT("FORK-")+TwinId);
}

bool UGHSMannedForkliftDataComponent::InitializeIdentity(const FString& Id)
{
    FString NumberText=Id;
    int32 Number=0;
    if (!NumberText.RemoveFromStart(TEXT("FORK-"),ESearchCase::CaseSensitive)
        || !ParsePositiveIdentifier(NumberText,Number)) return false;
    ForkliftId=FString::Printf(TEXT("FORK-%02d"),Number);
    IdentityOwner=GetOwner();
    return true;
}

bool UGHSMannedForkliftDataComponent::IsIdentityBoundToOwner() const
{
    return IdentityOwner.IsValid() && IdentityOwner.Get()==GetOwner();
}

bool UGHSMannedForkliftDataComponent::ResetForReassignedIdentity(const FString& Id)
{
    if (!InitializeIdentity(Id)) return false;
    LoadTonnes=SpeedKmh=-1.f;
    DriverId.Empty(); Area.Empty(); TaskId.Empty(); Reason.Empty();
    Status=EGHSMannedForkliftStatus::AwaitingData;
    bIsDemoData=false;
    LastUpdateSeconds=LastOnlineSeconds=-1.f;
    // A copied component must not be seeded with its source vehicle's demo or live data again.
    bHasAcceptedUpdate=true;
    return true;
}

bool UGHSMannedForkliftDataComponent::SetTelemetry(float Load,float Speed,EGHSMannedForkliftStatus NewStatus,
    const FString& NewDriverId,const FString& NewArea,const FString& NewTaskId,const FString& NewReason,bool bDemoData)
{
    if (!FMath::IsFinite(Load) || !FMath::IsFinite(Speed)) return false;
    const bool bDisconnected=NewStatus==EGHSMannedForkliftStatus::Offline || NewStatus==EGHSMannedForkliftStatus::AwaitingData;
    const bool bFault=NewStatus==EGHSMannedForkliftStatus::Fault;
    if (!IsMeasuredState(NewStatus) && !bDisconnected && !bFault) return false;
    const bool bValid=Load>=0.f && Speed>=0.f;
    const bool bUnknown=Load==-1.f && Speed==-1.f;
    if (!bValid && !((bDisconnected || bFault) && bUnknown)) return false;

    LoadTonnes=(bDisconnected || bFault)?-1.f:Load;
    SpeedKmh=(bDisconnected || bFault)?-1.f:Speed;
    DriverId=bDisconnected?FString():NewDriverId;
    Area=bDisconnected?FString():NewArea;
    TaskId=bDisconnected?FString():NewTaskId;
    Reason=NewReason;
    Status=NewStatus;
    bIsDemoData=bDemoData;
    const UWorld* World=GetWorld();
    LastUpdateSeconds=World?World->GetTimeSeconds():-1.f;
    if (!bDisconnected) LastOnlineSeconds=LastUpdateSeconds;
    bHasAcceptedUpdate=true;
    return true;
}

bool UGHSMannedForkliftDataComponent::HasTelemetry() const
{
    return IsMeasuredState(Status) && FMath::IsFinite(LoadTonnes) && LoadTonnes>=0.f
        && FMath::IsFinite(SpeedKmh) && SpeedKmh>=0.f;
}

bool UGHSMannedForkliftDataComponent::ApplyDemoState(int32 Index)
{
    if (Index<0 || bHasAcceptedUpdate) return false;
    struct FSample { EGHSMannedForkliftStatus State; float Load,Speed; const TCHAR* Driver; const TCHAR* Area; const TCHAR* Task; const TCHAR* Reason; };
    static const FSample Samples[] = {
        {EGHSMannedForkliftStatus::Running,1.2f,5.f,TEXT("OP-07"),TEXT("A区 · 地堆"),TEXT("T-0401"),TEXT("转运至 A-03-12")},
        {EGHSMannedForkliftStatus::Idle,0.f,0.f,TEXT("OP-12"),TEXT("B区 · 地堆"),TEXT(""),TEXT("已停靠 · 等待派单")},
        {EGHSMannedForkliftStatus::Warning,1.8f,2.f,TEXT("OP-09"),TEXT("C区 · 地堆"),TEXT("T-0403"),TEXT("载荷预警（设计示例）")},
        {EGHSMannedForkliftStatus::Fault,-1.f,-1.f,TEXT("OP-04"),TEXT("D区 · 地堆"),TEXT("T-0404"),TEXT("液压系统故障 · 指标待确认")},
        {EGHSMannedForkliftStatus::Offline,-1.f,-1.f,TEXT(""),TEXT(""),TEXT(""),TEXT("设备连接中断")},
        {EGHSMannedForkliftStatus::Running,.8f,3.5f,TEXT("OP-18"),TEXT("F区 · 地堆"),TEXT("T-0406"),TEXT("托盘转运作业")},
        {EGHSMannedForkliftStatus::Idle,0.f,0.f,TEXT("OP-21"),TEXT("G区 · 地堆"),TEXT(""),TEXT("已停靠 · 等待派单")},
        {EGHSMannedForkliftStatus::Running,1.f,4.f,TEXT("OP-11"),TEXT("H区 · 地堆"),TEXT("T-0408"),TEXT("托盘转运作业")}
    };
    const FSample& Sample=Samples[Index%UE_ARRAY_COUNT(Samples)];
    return SetTelemetry(Sample.Load,Sample.Speed,Sample.State,Sample.Driver,Sample.Area,Sample.Task,Sample.Reason,true);
}
