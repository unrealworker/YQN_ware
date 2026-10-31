#pragma once
#include "CoreMinimal.h"

/** Matches FWebBrowserViewport::Tick: Slate layout units are not CEF CSS pixels. */
struct FGHSGlobeBrowserGeometry
{
    static FVector2D ToCssSize(FVector2D LayoutSize,float AccumulatedScale,float WindowDpi)
    {
        if(!FMath::IsFinite(LayoutSize.X)||!FMath::IsFinite(LayoutSize.Y)||LayoutSize.X<=0||LayoutSize.Y<=0
            ||!FMath::IsFinite(AccumulatedScale)||AccumulatedScale<=0||!FMath::IsFinite(WindowDpi)||WindowDpi<=0)return FVector2D::ZeroVector;
        // FGeometry's local size and scale use floats; preserve the engine's
        // float divide/multiply before it promotes the result for IntPoint().
        const float DpiScale=AccumulatedScale/WindowDpi;
        const FVector2D Css(FVector2f(LayoutSize)*DpiScale);
        if(!FMath::IsFinite(Css.X)||!FMath::IsFinite(Css.Y)||Css.X>200000||Css.Y>200000)return FVector2D::ZeroVector;
        return FVector2D(Css.IntPoint());
    }
    static bool CoversFullLayout(FVector2D FullSize,FVector2D BrowserOrigin,FVector2D BrowserEnd,bool Compact)
    {
        return !Compact&&FullSize.X>0&&FullSize.Y>0&&BrowserOrigin.Equals(FVector2D::ZeroVector,1.)&&BrowserEnd.Equals(FullSize,1.);
    }
};

/** A browser curtain must acknowledge the current transition at its full allocated size. */
struct FGHSGlobeCurtainGate
{
    void Begin(FVector2D FullSize,double Now)
    {
        ++Generation;if(Generation==0)++Generation;
        ExpectedSize=FullSize;StartedAt=Now;bActive=true;bAcknowledged=false;
    }
    void Cancel(){bActive=false;bAcknowledged=false;}
    bool Accept(uint32 Candidate,FVector2D Size,float Opacity,uint64 Frame)
    {
        if(!bActive||Candidate!=Generation||!FMath::IsFinite(Opacity)||Opacity<1.f
            ||!FMath::IsFinite(Size.X)||!FMath::IsFinite(Size.Y)||Size.X<=0||Size.Y<=0
            ||!Size.Equals(ExpectedSize,1.))return false;
        // Duplicate browser reports must not continually move the settling frame forward.
        if(!bAcknowledged){bAcknowledged=true;AcknowledgedFrame=Frame;}
        return true;
    }
    bool Ready(uint64 Frame,bool FullBrowserCoverage)const{return bActive&&bAcknowledged&&FullBrowserCoverage&&Frame>=AcknowledgedFrame+2;}
    bool Expired(double Now)const{return bActive&&Now-StartedAt>10.;}
    bool Active()const{return bActive;}
    uint32 GetGeneration()const{return Generation;}
    FVector2D GetExpectedSize()const{return ExpectedSize;}
private:
    FVector2D ExpectedSize=FVector2D::ZeroVector;
    double StartedAt=0;
    uint64 AcknowledgedFrame=0;
    uint32 Generation=0;
    bool bActive=false,bAcknowledged=false;
};
