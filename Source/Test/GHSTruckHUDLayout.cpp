#include "GHSTruckHUDLayout.h"

namespace GHSTruckHUDLayout
{
namespace
{
constexpr double CanvasMargin = 12.0;
constexpr double LocalGap = 6.0;
constexpr double MaxLocalOffset = 40.0;
constexpr float CellDwell = 0.20f;
const FVector2D ClusterSize(184.0, 34.0);

bool IsFiniteVector(FVector2D Value)
{
    return FMath::IsFinite(Value.X) && FMath::IsFinite(Value.Y);
}

int32 CellFor(FVector2D Anchor, FVector2D Canvas)
{
    // Truncating a nonnegative normalized value is floor. Clamp before converting
    // so finite but extreme offscreen anchors cannot overflow the integer cast.
    const int32 Column = FMath::Min(GridColumns - 1,
        static_cast<int32>(FMath::Clamp(Anchor.X / Canvas.X, 0.0, 1.0) * GridColumns));
    const int32 Row = FMath::Min(GridRows - 1,
        static_cast<int32>(FMath::Clamp(Anchor.Y / Canvas.Y, 0.0, 1.0) * GridRows));
    return Row * GridColumns + Column;
}

FVector2D ClampToViewport(FVector2D Position,FVector2D Size,FVector2D Canvas)
{
    return FVector2D(
        FMath::Clamp(Position.X,CanvasMargin,FMath::Max(CanvasMargin,Canvas.X-CanvasMargin-Size.X)),
        FMath::Clamp(Position.Y,CanvasMargin,FMath::Max(CanvasMargin,Canvas.Y-CanvasMargin-Size.Y)));
}

bool Overlaps(FVector2D A,FVector2D SizeA,FVector2D B,FVector2D SizeB)
{
    return A.X<B.X+SizeB.X+LocalGap && B.X<A.X+SizeA.X+LocalGap
        && A.Y<B.Y+SizeB.Y+LocalGap && B.Y<A.Y+SizeA.Y+LocalGap;
}

void UpdateGeometry(FGroup& Group, const TArray<FItem>& Items, FVector2D Canvas)
{
    Group.Members.Sort([](const FString& A, const FString& B)
    {
        return A.Compare(B, ESearchCase::CaseSensitive) < 0;
    });
    Group.Key = Group.EquipmentType.IsEmpty() ? FString()
        : FString::Printf(TEXT("Type%d:%s;"),Group.EquipmentType.Len(),*Group.EquipmentType);
    Group.Anchor = FVector2D::ZeroVector;
    for (const FString& Id : Group.Members)
    {
        const FItem* Item = Items.FindByPredicate([&Id](const FItem& Value) { return Value.Id == Id; });
        Group.Anchor += Item->Anchor / static_cast<double>(Group.Members.Num());
        // Equipment type and membership identify a visual transition. Position
        // and cell changes retain the same badge's local fade/follow behavior.
        Group.Key += FString::Printf(TEXT("%d:"), Id.Len());
        Group.Key += Id;
        Group.Key += TEXT(";");
        Group.Size = Group.Members.Num() == 1 ? Item->Size : ClusterSize;
    }
    const FVector2D Natural = Group.Anchor - FVector2D(Group.Size.X * 0.5, 50.0);
    // The 2x2 grid chooses membership only. A label always belongs at the mean
    // projected position of its own members, with only viewport edge clamping.
    Group.Position = ClampToViewport(Natural,Group.Size,Canvas);
}
}

const TArray<FGroup>& FClusterer::Update(const TArray<FItem>& Items, FVector2D Canvas, float DeltaSeconds, bool bAggregate)
{
    if (!IsFiniteVector(Canvas) || Canvas.X <= 0.0 || Canvas.Y <= 0.0)
    {
        Reset();
        return Groups;
    }

    TArray<FItem> Valid;
    Valid.Reserve(Items.Num());
    const double MaxSingletonWidth = FMath::Max(1.0,
        FMath::Min(275.0, Canvas.X - CanvasMargin * 2.0));
    for (const FItem& Item : Items)
    {
        if (!Item.Id.TrimStartAndEnd().IsEmpty() && IsFiniteVector(Item.Anchor) && IsFiniteVector(Item.Size) &&
            Item.Size.X > 0.0 && Item.Size.Y > 0.0)
        {
            FItem Sanitized = Item;
            Sanitized.Size.X = FMath::Min(Sanitized.Size.X, MaxSingletonWidth);
            Valid.Add(MoveTemp(Sanitized));
        }
    }
    // A duplicate identity is still one device. Resolve duplicate type/geometry without
    // depending on discovery order, which would otherwise disturb animation keys.
    Valid.Sort([](const FItem& A, const FItem& B)
    {
        const int32 IdOrder = A.Id.Compare(B.Id, ESearchCase::CaseSensitive);
        if (IdOrder != 0) { return IdOrder < 0; }
        const int32 TypeOrder = A.EquipmentType.Compare(B.EquipmentType, ESearchCase::CaseSensitive);
        if (TypeOrder != 0) { return TypeOrder < 0; }
        if (A.Anchor.X != B.Anchor.X) { return A.Anchor.X < B.Anchor.X; }
        if (A.Anchor.Y != B.Anchor.Y) { return A.Anchor.Y < B.Anchor.Y; }
        if (A.Size.X != B.Size.X) { return A.Size.X < B.Size.X; }
        return A.Size.Y < B.Size.Y;
    });
    for (int32 Index = Valid.Num() - 1; Index > 0; --Index)
    {
        if (Valid[Index].Id == Valid[Index - 1].Id) { Valid.RemoveAt(Index); }
    }
    if (Valid.IsEmpty())
    {
        Reset();
        return Groups;
    }

    if (!bAggregate)
    {
        // Crossing the zoom threshold is immediate. Throw away the old grid
        // confirmation state so zooming back out starts from current anchors.
        Assignments.Reset();
        LocalPlacements.Reset();
        PreviousCanvas = FVector2D::ZeroVector;
        Groups.Reset();
        for (const FItem& Item : Valid)
        {
            FGroup Group;
            Group.CellIndex = CellFor(Item.Anchor, Canvas);
            Group.EquipmentType = Item.EquipmentType;
            Group.Members.Add(Item.Id);
            UpdateGeometry(Group, Valid, Canvas);
            Groups.Add(MoveTemp(Group));
        }
        return Groups;
    }

    const bool bCanvasChanged = Canvas.X != PreviousCanvas.X || Canvas.Y != PreviousCanvas.Y;
    PreviousCanvas = Canvas;
    Assignments.RemoveAll([&Valid](const FAssignment& Assignment)
    {
        return !Valid.ContainsByPredicate([&Assignment](const FItem& Item) { return Item.Id == Assignment.Id; });
    });
    for (const FItem& Item : Valid)
    {
        const int32 TargetCell = CellFor(Item.Anchor, Canvas);
        const int32 Index = Assignments.IndexOfByPredicate([&Item](const FAssignment& Value) { return Value.Id == Item.Id; });
        if (Index == INDEX_NONE)
        {
            FAssignment New;
            New.Id = Item.Id;
            New.CellIndex = TargetCell;
            Assignments.Add(MoveTemp(New));
            continue;
        }
        FAssignment& Assignment = Assignments[Index];
        if (bCanvasChanged || TargetCell == Assignment.CellIndex)
        {
            // Resize is an immediate coordinate-system change, not camera jitter.
            Assignment.CellIndex = TargetCell;
            Assignment.PendingCellIndex = INDEX_NONE;
            Assignment.PendingSeconds = 0.0f;
        }
        else if (TargetCell != Assignment.PendingCellIndex)
        {
            Assignment.PendingCellIndex = TargetCell;
            Assignment.PendingSeconds = 0.0f;
        }
        else
        {
            // Confirm each truck separately: a different boundary-jittering truck
            // must not continually reset this one's stable migration.
            if (FMath::IsFinite(DeltaSeconds))
            {
                Assignment.PendingSeconds += FMath::Clamp(DeltaSeconds, 0.0f, 0.1f);
            }
            if (Assignment.PendingSeconds >= CellDwell)
            {
                Assignment.CellIndex = TargetCell;
                Assignment.PendingCellIndex = INDEX_NONE;
                Assignment.PendingSeconds = 0.0f;
            }
        }
    }

    TArray<FString> EquipmentTypes;
    for (const FItem& Item : Valid) EquipmentTypes.AddUnique(Item.EquipmentType);
    EquipmentTypes.Sort([](const FString& A,const FString& B)
        { return A.Compare(B,ESearchCase::CaseSensitive)<0; });
    Groups.Reset();
    for (int32 Cell = 0; Cell < GridColumns * GridRows; ++Cell)
    for (int32 TypeIndex = 0; TypeIndex < EquipmentTypes.Num(); ++TypeIndex)
    {
        const FString& EquipmentType = EquipmentTypes[TypeIndex];
        FGroup Group;
        Group.CellIndex = Cell;
        Group.EquipmentType = EquipmentType;
        for (const FAssignment& Assignment : Assignments)
        {
            if (Assignment.CellIndex != Cell) continue;
            const FItem* Item = Valid.FindByPredicate([&Assignment](const FItem& Value) { return Value.Id==Assignment.Id; });
            if (Item && Item->EquipmentType == EquipmentType) Group.Members.Add(Assignment.Id);
        }
        if (!Group.Members.IsEmpty())
        {
            UpdateGeometry(Group, Valid, Canvas);
            Groups.Add(MoveTemp(Group));
        }
    }

    // Keep a one-time local offset with each visual key. A different type leaving
    // or arriving cannot reset a surviving key, and offsets never accumulate.
    for (auto It=LocalPlacements.CreateIterator(); It; ++It)
        if (!Groups.ContainsByPredicate([&](const FGroup& Group) { return Group.Key==It.Key(); })) It.RemoveCurrent();
    TSet<FString> ExistingKeys;
    TArray<FVector2D> Bases;
    for (FGroup& Group : Groups)
    {
        if (LocalPlacements.Contains(Group.Key)) ExistingKeys.Add(Group.Key);
        Bases.Add(Group.Position);
        const FLocalPlacement& Placement=LocalPlacements.FindOrAdd(Group.Key);
        Group.Position=ClampToViewport(Group.Position+FVector2D(0,Placement.OffsetY),Group.Size,Canvas);
    }
    bool bOverlap=false;
    for (int32 A=0; A<Groups.Num(); ++A)
    for (int32 B=A+1; B<Groups.Num(); ++B)
        bOverlap |= Overlaps(Groups[A].Position,Groups[A].Size,Groups[B].Position,Groups[B].Size);
    if (!bOverlap) return Groups;

    // Solve a new local arrangement once, considering all horizontally
    // overlapping groups, including the same type in neighboring quadrants.
    // Every movable label remains within one row of its own anchor. Prefer
    // fixed existing labels; only an infeasible incoming local cluster may reflow.
    const bool bHasNewKeys=ExistingKeys.Num()!=Groups.Num();
    TArray<int32> Order;
    TArray<double> Lower,Upper;
    TArray<uint8> Movable;
    for (int32 Index=0; Index<Groups.Num(); ++Index)
    {
        FLocalPlacement& Placement=LocalPlacements.FindChecked(Groups[Index].Key);
        const bool bCanMove=!Placement.bLocked && (!bHasNewKeys || !ExistingKeys.Contains(Groups[Index].Key));
        if (bHasNewKeys && ExistingKeys.Contains(Groups[Index].Key)) Placement.bLocked=true;
        Order.Add(Index);
        Movable.Add(bCanMove);
    }
    Order.Sort([&](int32 A,int32 B)
    {
        if (Bases[A].Y!=Bases[B].Y) return Bases[A].Y<Bases[B].Y;
        const int32 TypeOrder=Groups[A].EquipmentType.Compare(Groups[B].EquipmentType,ESearchCase::CaseSensitive);
        return TypeOrder!=0?TypeOrder<0:Groups[A].Key.Compare(Groups[B].Key,ESearchCase::CaseSensitive)<0;
    });
    auto SharesHorizontalSpace=[&](int32 A,int32 B)
    {
        return Bases[A].X<Bases[B].X+Groups[B].Size.X+LocalGap
            && Bases[B].X<Bases[A].X+Groups[A].Size.X+LocalGap;
    };
    auto SolveBounds=[&]()
    {
        Lower.Reset(); Upper.Reset();
        for (int32 Index=0; Index<Groups.Num(); ++Index)
        {
            Lower.Add(Movable[Index]?FMath::Max(CanvasMargin,Bases[Index].Y-MaxLocalOffset):Groups[Index].Position.Y);
            Upper.Add(Movable[Index]?FMath::Min(FMath::Max(CanvasMargin,Canvas.Y-CanvasMargin-Groups[Index].Size.Y),Bases[Index].Y+MaxLocalOffset):Groups[Index].Position.Y);
        }
        for (int32 Next=0; Next<Order.Num(); ++Next)
            for (int32 Previous=0; Previous<Next; ++Previous)
                if (SharesHorizontalSpace(Order[Previous],Order[Next]))
                    Lower[Order[Next]]=FMath::Max(Lower[Order[Next]],Lower[Order[Previous]]+Groups[Order[Previous]].Size.Y+LocalGap);
        for (int32 Previous=Order.Num()-1; Previous>=0; --Previous)
            for (int32 Next=Previous+1; Next<Order.Num(); ++Next)
                if (SharesHorizontalSpace(Order[Previous],Order[Next]))
                    Upper[Order[Previous]]=FMath::Min(Upper[Order[Previous]],Upper[Order[Next]]-Groups[Order[Previous]].Size.Y-LocalGap);
        for (int32 Index=0; Index<Groups.Num(); ++Index)
            if (Lower[Index]>Upper[Index]) return false;
        return true;
    };
    if (!SolveBounds())
    {
        if (!bHasNewKeys) return Groups;
        // Two locked rows can leave no gap for a newly visible third type.
        // Unlock only the incoming key's connected local collision cluster.
        // A remote key, even at the same X, retains its established placement.
        TSet<int32> Reflow;
        TArray<int32> Pending;
        for (int32 A=0; A<Groups.Num(); ++A)
        {
            if (ExistingKeys.Contains(Groups[A].Key)) continue;
            for (int32 B=0; B<Groups.Num(); ++B)
                if (A!=B && Overlaps(Groups[A].Position,Groups[A].Size,Groups[B].Position,Groups[B].Size))
                {
                    Reflow.Add(A); Pending.Add(A); break;
                }
        }
        for (int32 Cursor=0; Cursor<Pending.Num(); ++Cursor)
        {
            const int32 A=Pending[Cursor];
            for (int32 B=0; B<Groups.Num(); ++B)
            {
                if (Reflow.Contains(B) || !SharesHorizontalSpace(A,B)) continue;
                const bool bLocalRangesTouch=Bases[A].Y-MaxLocalOffset<=Bases[B].Y+MaxLocalOffset+Groups[B].Size.Y+LocalGap
                    && Bases[B].Y-MaxLocalOffset<=Bases[A].Y+MaxLocalOffset+Groups[A].Size.Y+LocalGap;
                if (bLocalRangesTouch) { Reflow.Add(B); Pending.Add(B); }
            }
        }
        if (Reflow.IsEmpty()) return Groups;
        for (const int32 Index : Reflow) Movable[Index]=true;
        // If the viewport edge still makes the bounded arrangement impossible,
        // do not push badges arbitrarily far from their equipment anchors.
        if (!SolveBounds()) return Groups;
    }
    for (int32 Next=0; Next<Order.Num(); ++Next)
    {
        const int32 Index=Order[Next];
        double Minimum=Lower[Index];
        for (int32 Previous=0; Previous<Next; ++Previous)
            if (SharesHorizontalSpace(Order[Previous],Index))
                Minimum=FMath::Max(Minimum,Groups[Order[Previous]].Position.Y+Groups[Order[Previous]].Size.Y+LocalGap);
        Groups[Index].Position.Y=FMath::Clamp(Bases[Index].Y,Minimum,Upper[Index]);
        FLocalPlacement& Placement=LocalPlacements.FindChecked(Groups[Index].Key);
        if (Movable[Index]) Placement.OffsetY=Groups[Index].Position.Y-Bases[Index].Y;
        Placement.bLocked=true;
    }
    return Groups;
}

void FClusterer::Reset()
{
    Groups.Reset();
    Assignments.Reset();
    LocalPlacements.Reset();
    PreviousCanvas = FVector2D::ZeroVector;
}
}
