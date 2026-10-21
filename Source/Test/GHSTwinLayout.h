#pragma once
#include "CoreMinimal.h"

/** Design units: high-resolution scaling belongs to FGHSTwinViewport. */
struct FGHSTwinLayout
{
    FVector2D PanelPosition, PanelSize, ScenePosition, SceneSize;
    double HeaderHeight = 64;
    static FGHSTwinLayout Calculate(FVector2D Viewport, bool bCollapsed = false)
    {
        FGHSTwinLayout L;
        Viewport.X = FMath::Max(1., Viewport.X); Viewport.Y = FMath::Max(1., Viewport.Y);
        L.HeaderHeight = Viewport.X < 700 ? 52 : 64;
        L.ScenePosition = FVector2D(0, L.HeaderHeight);
        if (bCollapsed)
        {
            L.PanelPosition = FVector2D(Viewport.X, L.HeaderHeight);
            L.PanelSize = FVector2D(0, Viewport.Y-L.HeaderHeight);
            L.SceneSize = FVector2D(Viewport.X, Viewport.Y-L.HeaderHeight);
        }
        else if (Viewport.X < 900)
        {
            const double Height = FMath::Min(Viewport.Y-L.HeaderHeight-180., FMath::Max(280., Viewport.Y*.52));
            L.PanelPosition = FVector2D(0, Viewport.Y-Height);
            L.PanelSize = FVector2D(Viewport.X, Height);
            L.SceneSize = FVector2D(Viewport.X, Viewport.Y-Height-L.HeaderHeight);
        }
        else
        {
            const double Width = FMath::Clamp(Viewport.X * .25, 380., 560.);
            L.PanelPosition = FVector2D(Viewport.X-Width, L.HeaderHeight);
            L.PanelSize = FVector2D(Width, Viewport.Y-L.HeaderHeight);
            L.SceneSize = FVector2D(Viewport.X-Width, Viewport.Y-L.HeaderHeight);
        }
        return L;
    }
    bool IsScenePoint(FVector2D P) const
    {
        return P.X >= ScenePosition.X && P.Y >= ScenePosition.Y && P.X < ScenePosition.X+SceneSize.X && P.Y < ScenePosition.Y+SceneSize.Y;
    }
};

/** Shared geometry for the non-interactive scene heading and native type filters. */
struct FGHSTwinSceneChrome
{
    static constexpr float CornerRadius=12.f;
    static FVector2D FilterPosition(double HeaderHeight,int32 Index)
    { return FVector2D(32+Index*104,HeaderHeight+147); }
    static FVector2D FilterSize() { return FVector2D(96,40); }
    static bool Contains(FVector2D P,FVector2D At,FVector2D Size)
    { return P.X>=At.X && P.Y>=At.Y && P.X<At.X+Size.X && P.Y<At.Y+Size.Y; }
    static bool IsHeadingPoint(FVector2D P,double HeaderHeight)
    { return Contains(P,FVector2D(24,HeaderHeight+16),FVector2D(256,84)); }
    static bool FiltersVisible(const FGHSTwinLayout& Layout)
    { return Layout.SceneSize.X>660 && Layout.SceneSize.Y>=195; }
    static int32 FilterAt(FVector2D P,const FGHSTwinLayout& Layout)
    {
        if(FiltersVisible(Layout))
            for(int32 I=0;I<4;++I) if(Contains(P,FilterPosition(Layout.HeaderHeight,I),FilterSize())) return I;
        return INDEX_NONE;
    }
    static bool Overlaps(FVector2D At,FVector2D Size,const FGHSTwinLayout& Layout)
    {
        auto Intersects=[&](FVector2D P,FVector2D S)
        { return At.X<P.X+S.X && At.X+Size.X>P.X && At.Y<P.Y+S.Y && At.Y+Size.Y>P.Y; };
        if(Intersects(FVector2D(24,Layout.HeaderHeight+16),FVector2D(256,84))) return true;
        return FiltersVisible(Layout) && Intersects(FVector2D(24,Layout.HeaderHeight+108),FVector2D(424,87));
    }
};

/** A full-width drawer; retargeting starts from the current visible position. */
struct FGHSTwinPanelMotion
{
    float Progress=1.f, Start=1.f, Target=1.f, Elapsed=0.f;
    static constexpr float Duration=.42f;
    void Advance(float DeltaSeconds,bool bCollapsed)
    {
        const float NextTarget=bCollapsed?0.f:1.f;
        if(Target!=NextTarget) { Start=Progress; Target=NextTarget; Elapsed=0; }
        if(!FMath::IsFinite(DeltaSeconds) || DeltaSeconds<=0 || Progress==Target) return;
        Elapsed=FMath::Min(Elapsed+DeltaSeconds,Duration);
        const float T=Elapsed/Duration;
        const float Ease=T*T*T*(10.f+T*(-15.f+6.f*T));
        Progress=Elapsed>=Duration?Target:FMath::Lerp(Start,Target,Ease);
    }
    FVector2D Position(const FGHSTwinLayout& Expanded) const
    {
        return Expanded.PanelPosition+FVector2D(Expanded.PanelSize.X*(1.-Progress),0);
    }
    FVector2D SceneControlsPosition(FVector2D Viewport) const
    {
        const auto Expanded=FGHSTwinLayout::Calculate(Viewport);
        // Desktop controls follow the same eased drawer edge on every frame.
        // A narrow bottom sheet slides horizontally: keep controls above it so
        // they never travel through the browser or jump when it becomes hidden.
        const double Right=Viewport.X<900?Viewport.X:Position(Expanded).X;
        return FVector2D(Right-60,Expanded.ScenePosition.Y+Expanded.SceneSize.Y-132);
    }
    FVector2D SceneSearchPosition(FVector2D Viewport) const
    {
        const auto Expanded=FGHSTwinLayout::Calculate(Viewport);
        const double Right=Viewport.X<900?Viewport.X:Position(Expanded).X;
        return FVector2D(FMath::Max(140.,Right-384),Expanded.HeaderHeight+16);
    }
};
