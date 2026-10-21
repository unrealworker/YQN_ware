#pragma once
#include "CoreMinimal.h"

/** The native and streamed search share physical-pixel geometry. */
struct FGHSTwinSearchLayout
{
    FVector2D Position=FVector2D::ZeroVector,Size=FVector2D::ZeroVector;
    int32 VisibleRows=0;
    static constexpr double HeaderHeight=36,RowHeight=64,FooterHeight=36;
    static FGHSTwinSearchLayout Calculate(FVector2D InputPosition,FVector2D InputSize,double SceneBottom,int32 Count)
    {
        FGHSTwinSearchLayout L; L.Position=InputPosition+FVector2D(0,InputSize.Y+8);
        const double Available=FMath::Max(0.,SceneBottom-L.Position.Y-8);
        L.VisibleRows=FMath::Clamp(FMath::FloorToInt((Available-HeaderHeight-FooterHeight)/RowHeight),0,FMath::Min(8,Count));
        L.Size=FVector2D(InputSize.X,FMath::Min(Available,HeaderHeight+FooterHeight+FMath::Max(1,L.VisibleRows)*RowHeight)); return L;
    }
    int32 RowAt(FVector2D P) const
    {
        if(P.X<Position.X || P.X>=Position.X+Size.X || P.Y<Position.Y+HeaderHeight) return INDEX_NONE;
        const int32 Row=FMath::FloorToInt((P.Y-Position.Y-HeaderHeight)/RowHeight);
        return Row>=0 && Row<VisibleRows?Row:INDEX_NONE;
    }
    static int32 MoveIndex(int32 Current,int32 Direction,int32 Count)
    { return Count>0?((FMath::Max(0,Current)+Direction)%Count+Count)%Count:INDEX_NONE; }
    static int32 WindowStart(int32 Selected,int32 First,int32 VisibleRows,int32 Count)
    {
        if(VisibleRows<=0) return 0;
        if(Selected<First) First=Selected;
        else if(Selected>=First+VisibleRows) First=Selected-VisibleRows+1;
        return FMath::Clamp(First,0,FMath::Max(0,Count-VisibleRows));
    }
};
