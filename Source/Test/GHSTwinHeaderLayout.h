#pragma once
#include "CoreMinimal.h"

/** Header positions in the same design units as the scene and input bounds. */
struct FGHSTwinHeaderLayout
{
    double Height=64, BrandRowHeight=64;
    FVector2D AddressPosition, ClockPosition, PanelButtonPosition;
    FVector2D AddressSize=FVector2D(270,48), ClockSize=FVector2D(266,48);
    FVector2D PanelButtonSize=FVector2D(96,44);
    bool bShowContext=false,bCompactBrand=false;

    static FGHSTwinHeaderLayout Calculate(double Width)
    {
        FGHSTwinHeaderLayout L;
        L.bCompactBrand=Width<440;
        L.bShowContext=Width>=1250;
        if(Width>=1000)
        {
            L.AddressPosition=FVector2D(L.bShowContext?440:300,8);
            L.ClockPosition=FVector2D(Width-402,8);
        }
        else
        {
            L.BrandRowHeight=52;
            L.AddressPosition=FVector2D(24,56);
            if(Width>=640) { L.Height=112; L.ClockPosition=FVector2D(Width-290,56); }
            else { L.Height=168; L.ClockPosition=FVector2D(24,112); }
        }
        L.PanelButtonPosition=FVector2D(Width-112,(L.BrandRowHeight-44)*.5);
        return L;
    }

    bool IsPanelButton(FVector2D P) const
    {
        return P.X>=PanelButtonPosition.X && P.X<PanelButtonPosition.X+PanelButtonSize.X
            && P.Y>=PanelButtonPosition.Y && P.Y<PanelButtonPosition.Y+PanelButtonSize.Y;
    }
};
