#pragma once
#include "CoreMinimal.h"

/** Bounded layout for the eight replay devices, independent of the live catalogue. */
namespace GHSReplayPOI
{
enum class EStatus { Idle,Active,Waiting,Fault };
inline EStatus StatusKind(const FString& Status)
{
    if(Status.Contains(TEXT("故障"))) return EStatus::Fault;
    if(Status.Contains(TEXT("等待")) || Status.Contains(TEXT("让行"))) return EStatus::Waiting;
    if(Status.IsEmpty() || Status==TEXT("待命") || Status==TEXT("循环完成")) return EStatus::Idle;
    return EStatus::Active;
}
inline FString CompactStatus(const FString& Status)
{
    if(Status==TEXT("测试补给车 · 返回园区")) return TEXT("补给回场");
    if(Status==TEXT("货叉插入蓝托盘")) return TEXT("插入托盘");
    if(Status==TEXT("等待补给车辆")) return TEXT("等待补给");
    if(Status==TEXT("交叉通道让行")) return TEXT("通道让行");
    if(Status==TEXT("倒车退出车厢") || Status==TEXT("倒车退出地堆")) return TEXT("倒车退出");
    return Status.IsEmpty()?TEXT("准备中"):Status;
}
inline bool Contains(const FBox2D& Outer,const FBox2D& Inner)
{return Outer.bIsValid && Inner.bIsValid && Inner.Min.X>=Outer.Min.X && Inner.Min.Y>=Outer.Min.Y && Inner.Max.X<=Outer.Max.X && Inner.Max.Y<=Outer.Max.Y;}
inline bool Intersects(const FBox2D& A,const FBox2D& B,double Gap)
{return A.Min.X<B.Max.X+Gap && A.Max.X>B.Min.X-Gap && A.Min.Y<B.Max.Y+Gap && A.Max.Y>B.Min.Y-Gap;}
inline bool Place(FVector2D Anchor,FVector2D Size,const FBox2D& Bounds,const TArray<FBox2D>& Blocked,
    const TArray<FBox2D>& Occupied,const FVector2D* Previous,FVector2D& Result)
{
    if(!Bounds.bIsValid || !Bounds.IsInside(Anchor) || Size.X<=0 || Size.Y<=0 || Size.X>Bounds.GetSize().X || Size.Y>Bounds.GetSize().Y || !FMath::IsFinite(Anchor.X) || !FMath::IsFinite(Anchor.Y)) return false;
    auto Accept=[&](FVector2D At)
    {
        const FBox2D Card(At,At+Size),AnchorGap(Anchor-FVector2D(14,14),Anchor+FVector2D(14,14));
        if(!Contains(Bounds,Card) || Intersects(Card,AnchorGap,0)) return false;
        for(const auto& B:Blocked) if(Intersects(Card,B,6)) return false;
        for(const auto& B:Occupied) if(Intersects(Card,B,8)) return false;
        Result=At;return true;
    };
    if(Previous && Accept(*Previous)) return true;
    // Choose nearby slots first. The fixed upper bound keeps crowded layouts cheap.
    for(int32 Row=0;Row<6;++Row)
    {
        const double Above=-Size.Y-24-Row*(Size.Y+12),Below=24+Row*(Size.Y+12);
        for(const double Y:{Above,Below})
            for(const double X:{-Size.X*.5,24.,-Size.X-24.})
            {
                const FVector2D At(FMath::Clamp(Anchor.X+X,Bounds.Min.X,Bounds.Max.X-Size.X),Anchor.Y+Y);
                if(Accept(At)) return true;
            }
    }
    return false;
}
}
