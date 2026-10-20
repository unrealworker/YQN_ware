#pragma once
#include "CoreMinimal.h"

/** Physical pixels: this HUD bypasses the project's legacy whole-screen DPI curve. */
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
};
