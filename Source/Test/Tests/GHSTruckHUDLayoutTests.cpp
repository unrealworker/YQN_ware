#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSTruckHUDLayout.h"
#include "Misc/AutomationTest.h"
#include <limits>

namespace GHSTruckHUDLayoutTests
{
using namespace GHSTruckHUDLayout;
constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
const FVector2D Canvas(1200, 900);
FItem Item(const TCHAR* Id, double X, double Y, double Width = 100.0)
{
    return { Id, FVector2D(X, Y), FVector2D(Width, 34) };
}
const TArray<FGroup>& Settle(FClusterer& Clusterer, const TArray<FItem>& Items, FVector2D Size = Canvas)
{
    for (int32 Frame = 0; Frame < 8; ++Frame) { Clusterer.Update(Items, Size, 0.05f); }
    return Clusterer.Update(Items, Size, 0.0f);
}
int32 Count(const TArray<FGroup>& Groups)
{
    int32 Result = 0;
    for (const FGroup& Group : Groups) { Result += Group.Members.Num(); }
    return Result;
}
const FGroup* GroupFor(const TArray<FGroup>& Groups, const TCHAR* Id)
{
    return Groups.FindByPredicate([Id](const FGroup& Group) { return Group.Members.Contains(Id); });
}
// Hand-chosen pairs are far apart, but each pair lies within one screen quadrant.
TArray<FItem> FourCells(FVector2D Size)
{
    const double Coordinates[2][2] = { {0.03, 0.47}, {0.53, 0.97} };
    TArray<FItem> Items;
    for (int32 Row = 0; Row < 2; ++Row)
        for (int32 Col = 0; Col < 2; ++Col)
            for (int32 Member = 0; Member < 2; ++Member)
                Items.Add({ FString::Printf(TEXT("Cell%d-%d"), Row * 2 + Col, Member),
                    FVector2D(Coordinates[Col][Member] * Size.X, Coordinates[Row][Member] * Size.Y), FVector2D(100, 34) });
    return Items;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridFourCells, "GHS.DockTruckHUD.Clustering.FourCellsAreIndependent", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridFourCells::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const auto& Groups = Clusterer.Update(FourCells(Canvas), Canvas, 0.0f);
    TestEqual(TEXT("Four occupied quadrants produce four labels immediately"), Groups.Num(), 4);
    TestEqual(TEXT("Every truck remains represented"), Count(Groups), 8);
    for (int32 Cell = 0; Cell < 4; ++Cell)
    {
        const FString Id = FString::Printf(TEXT("Cell%d-0"), Cell);
        const FGroup* Group = GroupFor(Groups, *Id);
        if (!TestTrue(TEXT("Every cell has a group"), Group != nullptr)) { return false; }
        TestEqual(TEXT("Only the two members of this cell aggregate"), Group->Members.Num(), 2);
        TestTrue(TEXT("Distant members of the same cell aggregate"), Group->Members.Contains(FString::Printf(TEXT("Cell%d-1"), Cell)));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridBoundary, "GHS.DockTruckHUD.Clustering.CrossBoundaryNeverMerges", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridBoundary::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const auto& Groups = Settle(Clusterer, { Item(TEXT("NW"),599.9,449.9,275), Item(TEXT("NE"),600,449.9,275),
        Item(TEXT("SW"),599.9,450,275), Item(TEXT("SE"),600,450,275) });
    TestEqual(TEXT("Touching anchors across grid sides remain four groups"), Groups.Num(), 4);
    for (const FGroup& Group : Groups) { TestEqual(TEXT("Label overlap cannot cause cross-cell union"), Group.Members.Num(), 1); }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridResponsive, "GHS.DockTruckHUD.Clustering.ResponsiveAspectRatios", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridResponsive::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    const FVector2D Sizes[] = { FVector2D(1920,1080), FVector2D(960,540), FVector2D(2560,1080), FVector2D(800,1200) };
    TArray<FString> Keys;
    for (const FVector2D& Size : Sizes)
    {
        FClusterer Clusterer;
        const auto& Groups = Clusterer.Update(FourCells(Size), Size, 0.0f);
        if (!TestEqual(TEXT("Each aspect ratio has four groups"), Groups.Num(), 4)) { return false; }
        for (int32 Index = 0; Index < Groups.Num(); ++Index)
        {
            const FGroup& Group = Groups[Index];
            if (Keys.Num() < 4) { Keys.Add(Group.Key); }
            else { TestEqual(TEXT("Normalized anchors preserve memberships across resolutions"), Group.Key, Keys[Index]); }
            TestTrue(TEXT("Labels remain within the adaptive viewport"), Group.Position.X >= 12 && Group.Position.Y >= 12 &&
                Group.Position.X + Group.Size.X <= Size.X - 12 && Group.Position.Y + Group.Size.Y <= Size.Y - 12);
        }
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridResize, "GHS.DockTruckHUD.Clustering.ResizeReassignsImmediately", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridResize::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const TArray<FItem> Items = { Item(TEXT("A"),580,100), Item(TEXT("B"),610,100) };
    TestEqual(TEXT("Original width separates the anchors"), Clusterer.Update(Items,Canvas,0.0f).Num(), 2);
    TestEqual(TEXT("Width resize adopts new halves without stale dwell"), Clusterer.Update(Items,FVector2D(1800,900),0.0f).Num(), 1);
    TestEqual(TEXT("Restoring width splits immediately"), Clusterer.Update(Items,Canvas,0.0f).Num(), 2);
    Clusterer.Reset();
    const TArray<FItem> Vertical = { Item(TEXT("A"),100,430), Item(TEXT("B"),100,460) };
    TestEqual(TEXT("Original height separates rows"), Clusterer.Update(Vertical,Canvas,0.0f).Num(), 2);
    TestEqual(TEXT("Height-only resize updates rows immediately"), Clusterer.Update(Vertical,FVector2D(1200,1200),0.0f).Num(), 1);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridDwell, "GHS.DockTruckHUD.Clustering.PerTruckBoundaryDwell", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridDwell::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items = { Item(TEXT("A"),599,100), Item(TEXT("B"),700,100) };
    const TArray<FGroup> Initial = Clusterer.Update(Items,Canvas,0.0f);
    if (!TestEqual(TEXT("Initial sides remain separate"), Initial.Num(), 2)) { return false; }
    for (int32 Frame = 0; Frame < 40; ++Frame)
    {
        Items[0].Anchor.X = Frame % 2 ? 599 : 601;
        const auto& Held = Clusterer.Update(Items,Canvas,0.05f);
        if (!TestEqual(TEXT("Boundary jitter does not repeatedly merge/split"), Held.Num(), 2)) { return false; }
        TestEqual(TEXT("Boundary jitter preserves animation keys"), Held[0].Key, Initial[0].Key);
    }
    Items[0].Anchor.X = 601;
    TestEqual(TEXT("A single crossing hitch cannot confirm a new cell"), Clusterer.Update(Items,Canvas,10.0f).Num(), 2);
    TestEqual(TEXT("Stable crossing aggregates the cell"), Settle(Clusterer,Items).Num(), 1);
    Items[0].Anchor.X = 599;
    TestEqual(TEXT("Returning across a boundary also needs confirmation"), Clusterer.Update(Items,Canvas,0.05f).Num(), 1);
    TestEqual(TEXT("Stable return separates the cells"), Settle(Clusterer,Items).Num(), 2);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridIndependentDwell, "GHS.DockTruckHUD.Clustering.UnrelatedJitterCannotStarveMigration", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridIndependentDwell::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items = { Item(TEXT("A"),100,100), Item(TEXT("B"),700,100), Item(TEXT("C"),599,650) };
    Clusterer.Update(Items,Canvas,0.0f);
    Items[0].Anchor.X = 700;
    for (int32 Frame = 0; Frame < 8; ++Frame)
    {
        Items[2].Anchor.X = Frame % 2 ? 599 : 601;
        Clusterer.Update(Items,Canvas,0.05f);
    }
    const auto& Groups = Clusterer.Update(Items,Canvas,0.0f);
    const FGroup* A = GroupFor(Groups,TEXT("A"));
    if (!TestTrue(TEXT("A remains represented"), A != nullptr)) { return false; }
    TestTrue(TEXT("Another truck's jitter cannot reset A's confirmation"), A->Members.Contains(TEXT("B")));
    TestEqual(TEXT("One aggregate and one held truck occupy two cells"), Groups.Num(), 2);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridKeys, "GHS.DockTruckHUD.Clustering.StableOrderAndAnimationKeys", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridKeys::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer First;
    const TArray<FItem> Items = { Item(TEXT("A"),20,30), Item(TEXT("B"),580,420), Item(TEXT("C"),900,100) };
    const TArray<FGroup> Before = First.Update(Items,Canvas,0.0f);
    if (!TestEqual(TEXT("Same-cell A/B aggregate; C remains separate"), Before.Num(), 2)) { return false; }
    TestEqual(TEXT("Member order is stable"), Before[0].Members[0], FString(TEXT("A")));
    FClusterer Second;
    const auto& After = Second.Update({ Items[2],Items[1],Items[0] },Canvas,0.0f);
    if (!TestEqual(TEXT("Input order preserves group count"), After.Num(), Before.Num())) { return false; }
    for (int32 Index = 0; Index < Before.Num(); ++Index)
    {
        TestEqual(TEXT("Input order preserves animation keys"), After[Index].Key, Before[Index].Key);
        TestTrue(TEXT("Input order preserves centroid geometry"), After[Index].Position.Equals(Before[Index].Position));
    }
    TestEqual(TEXT("Within-cell motion preserves the key"), First.Update({ Item(TEXT("A"),300,280), Item(TEXT("B"),30,30),Items[2] },Canvas,0.05f)[0].Key, Before[0].Key);
    FClusterer AmbiguousA, AmbiguousB;
    const auto& One = AmbiguousA.Update({ Item(TEXT("A|B"),100,100),Item(TEXT("C"),300,100) },Canvas,0.0f);
    const auto& Two = AmbiguousB.Update({ Item(TEXT("A"),100,100),Item(TEXT("B|C"),300,100) },Canvas,0.0f);
    if (One.Num() != 1 || Two.Num() != 1) { return false; }
    TestTrue(TEXT("Different identities cannot alias a delimiter-based key"), One[0].Key != Two[0].Key);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridDense52, "GHS.DockTruckHUD.Clustering.Dense52ConservesIdentityPerCell", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridDense52::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items;
    for (int32 Index = 0; Index < 52; ++Index)
    {
        const int32 Cell = Index % 4;
        Items.Add({ FString::Printf(TEXT("Truck%02d"),Index), FVector2D((Cell % 2)*600+80+Index,(Cell/2)*450+100),FVector2D(100,34) });
    }
    const auto& Groups = Clusterer.Update(Items,Canvas,0.0f);
    TestEqual(TEXT("52 trucks occupy four separate regions"), Groups.Num(), 4);
    TestEqual(TEXT("No truck is lost"), Count(Groups), 52);
    for (const FItem& Truck : Items)
    {
        int32 Occurrences = 0;
        for (const FGroup& Group : Groups) { if (Group.Members.Contains(Truck.Id)) { ++Occurrences; } }
        TestEqual(TEXT("Every identity belongs to exactly one group"), Occurrences, 1);
    }
    Items.RemoveAt(0);
    const auto& Removed = Clusterer.Update(Items,Canvas,0.0f);
    TestEqual(TEXT("Removal is immediate"), Count(Removed), 51);
    TestTrue(TEXT("Removed trucks cannot persist in pending state"), GroupFor(Removed,TEXT("Truck00")) == nullptr);
    Items.Add(Item(TEXT("New"),100,100));
    const auto& Added = Clusterer.Update(Items,Canvas,0.0f);
    TestEqual(TEXT("Newly visible trucks appear immediately"), Count(Added), 52);
    TestEqual(TEXT("A newly visible member never creates a second committed group in its cell"), Added.Num(), 4);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridGeometry, "GHS.DockTruckHUD.Clustering.AnchorGeometryAndViewportClamp", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridGeometry::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const auto& Groups = Clusterer.Update({ Item(TEXT("A"),599,100),Item(TEXT("B"),601,100,800),
        Item(TEXT("C"),-600,-300),Item(TEXT("D"),10000,10000) },Canvas,0.0f);
    const FGroup* Left = GroupFor(Groups,TEXT("A"));
    const FGroup* Right = GroupFor(Groups,TEXT("B"));
    const FGroup* Last = GroupFor(Groups,TEXT("D"));
    if (!Left || !Right || !Last) { return false; }
    TestTrue(TEXT("Negative anchors clamp to the first cell"), Left->Members.Contains(TEXT("C")));
    TestTrue(TEXT("Offscreen group centroid clamps only to the viewport"), Left->Position.Equals(FVector2D(12,12)));
    TestTrue(TEXT("A right-cell label remains centered on its real anchor across the midline"), Right->Position.Equals(FVector2D(463.5,50)));
    TestTrue(TEXT("Long content retains the width limit"), FMath::IsNearlyEqual(Right->Size.X,275.0));
    TestTrue(TEXT("Overshooting anchors clamp to the viewport"), Last->Position.X + Last->Size.X <= 1188 && Last->Position.Y + Last->Size.Y <= 888);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridNarrowCanvas, "GHS.DockTruckHUD.Clustering.NarrowCanvasKeepsSingletonsNearAnchors", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridNarrowCanvas::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const auto& Groups = Clusterer.Update({ Item(TEXT("A"),319,90,275),Item(TEXT("B"),321,90,275) },
        FVector2D(640,540),0.0f);
    if (!TestEqual(TEXT("Two columns retain two singleton labels"),Groups.Num(),2)) { return false; }
    const double ExpectedX[] = { 181.5, 183.5 };
    for (int32 Index = 0; Index < Groups.Num(); ++Index)
    {
        const FGroup& Group = Groups[Index];
        TestEqual(TEXT("Narrow cell width does not change membership"),Group.Members.Num(),1);
        TestTrue(TEXT("A 640px canvas can retain the full singleton width"),FMath::IsNearlyEqual(Group.Size.X,275.0));
        TestTrue(TEXT("Singletons stay horizontally centered on their own anchors instead of moving to cell edges"),
            FMath::IsNearlyEqual(Group.Position.X,ExpectedX[Index]));
        TestTrue(TEXT("Cross-cell overlap can only introduce one local row of vertical separation"),FMath::Abs(Group.Position.Y-40)<=40.0001);
        TestTrue(TEXT("Singletons still fit the viewport"),Group.Position.X>=12 && Group.Position.X+Group.Size.X<=628);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckGridInvalid, "GHS.DockTruckHUD.Clustering.InvalidInputsAndReset", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckGridInvalid::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    const double NaN = std::numeric_limits<double>::quiet_NaN();
    const double Infinity = std::numeric_limits<double>::infinity();
    FClusterer Clusterer;
    const TArray<FItem> Dirty = { Item(TEXT("A"),100,100),Item(TEXT("B"),300,100),Item(TEXT(""),100,100),
        Item(TEXT("   "),100,100),Item(TEXT("NaN"),NaN,100),Item(TEXT("Inf"),100,100,Infinity),Item(TEXT("Zero"),100,100,0),Item(TEXT("A"),110,100) };
    TestEqual(TEXT("Invalid geometry and duplicate identities are excluded"), Count(Clusterer.Update(Dirty,Canvas,0.0f)), 2);
    const TArray<FItem> Crossing = { Item(TEXT("A"),700,100),Item(TEXT("B"),300,100) };
    for (int32 Index = 0; Index < 8; ++Index)
        TestEqual(TEXT("Nonfinite delta time cannot commit migration"), Clusterer.Update(Crossing,Canvas,static_cast<float>(NaN)).Num(), 1);
    TestEqual(TEXT("Valid time completes migration"), Settle(Clusterer,Crossing).Num(), 2);
    TestEqual(TEXT("Invalid canvas clears visible layout"), Clusterer.Update(Crossing,FVector2D(NaN,900),0.05f).Num(), 0);
    TestEqual(TEXT("Restored canvas uses current membership immediately"), Clusterer.Update(Crossing,Canvas,0.0f).Num(), 2);
    TestEqual(TEXT("Zero canvas dimensions clear layout"), Clusterer.Update(Crossing,FVector2D(0,900),0.05f).Num(), 0);
    TestEqual(TEXT("Empty input clears membership state"), Clusterer.Update({},Canvas,0.0f).Num(), 0);
    TestEqual(TEXT("Reentry cannot inherit a pending migration"), Clusterer.Update({ Item(TEXT("A"),100,100),Item(TEXT("B"),300,100) },Canvas,0.0f).Num(), 1);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckAggregationDisabled, "GHS.DockTruckHUD.Clustering.DisabledPreservesEverySingleton", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckAggregationDisabled::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items;
    for (int32 Index = 0; Index < 52; ++Index)
    {
        Items.Add({ FString::Printf(TEXT("Truck%02d"),Index),FVector2D(100+Index*5,100),FVector2D(100,34) });
    }
    TestEqual(TEXT("All fixture trucks initially share one region"),Clusterer.Update(Items,Canvas,0.0f).Num(),1);
    FClusterer Single;
    const FString SingletonKey = Single.Update({Items[0]},Canvas,0.0f)[0].Key;
    const FItem Duplicate = Items[0];
    Items.Add(Duplicate);
    Items.Add(Item(TEXT(""),100,100));
    Items.Add(Item(TEXT("Invalid"),std::numeric_limits<double>::quiet_NaN(),100));
    const auto& Singles = Clusterer.Update(Items,Canvas,0.0f,false);
    if (!TestEqual(TEXT("Disabling aggregation immediately exposes all 52 trucks"),Singles.Num(),52)) { return false; }
    TestEqual(TEXT("Disabled mode retains the same filtering and deduplication"),Count(Singles),52);
    TestEqual(TEXT("Mode switching preserves the singleton animation identity"),Singles[0].Key,SingletonKey);
    for (int32 Index = 0; Index < Singles.Num(); ++Index)
    {
        TestEqual(TEXT("Each disabled label contains exactly one identity"),Singles[Index].Members.Num(),1);
        TestEqual(TEXT("Every valid identity is retained in deterministic order"),Singles[Index].Members[0],
            FString::Printf(TEXT("Truck%02d"),Index));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckDisabledGeometry, "GHS.DockTruckHUD.Clustering.DisabledUsesOnlyViewportBounds", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckDisabledGeometry::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const auto& Groups = Clusterer.Update({Item(TEXT("A"),599,470,200),Item(TEXT("B"),599,470,200)},Canvas,0.0f,false);
    if (!TestEqual(TEXT("Two overlapping vehicles remain independent when disabled"),Groups.Num(),2)) { return false; }
    TestTrue(TEXT("A natural label may cross both region midlines"),Groups[0].Position.Equals(FVector2D(499,420)));
    TestTrue(TEXT("Disabled labels are not displaced to avoid each other"),Groups[1].Position.Equals(Groups[0].Position));
    const auto& Narrow = Clusterer.Update({Item(TEXT("Narrow"),100,100,800)},FVector2D(200,100),0.0f,false);
    if (Narrow.Num() != 1) { return false; }
    TestTrue(TEXT("Disabled content uses the whole viewport width"),FMath::IsNearlyEqual(Narrow[0].Size.X,176.0));
    TestTrue(TEXT("Disabled labels still respect viewport bounds"),FMath::IsNearlyEqual(Narrow[0].Position.X,12.0));
    const auto& Wide = Clusterer.Update({Item(TEXT("Wide"),500,100,800)},Canvas,0.0f,false);
    TestTrue(TEXT("Disabled labels retain the maximum content width"),FMath::IsNearlyEqual(Wide[0].Size.X,275.0));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTruckAggregationModeSwitch, "GHS.DockTruckHUD.Clustering.ModeSwitchClearsPendingAssignments", GHSTruckHUDLayoutTests::Flags)
bool FGHSTruckAggregationModeSwitch::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items = {Item(TEXT("A"),100,100),Item(TEXT("B"),599,100)};
    TestEqual(TEXT("Initial neighbors aggregate"),Clusterer.Update(Items,Canvas,0.0f).Num(),1);
    Items[1].Anchor.X = 601;
    Clusterer.Update(Items,Canvas,0.05f);
    Clusterer.Update(Items,Canvas,0.10f);
    TestEqual(TEXT("A partly confirmed migration still belongs to the old region"),Clusterer.Update(Items,Canvas,0.05f).Num(),1);
    TestEqual(TEXT("Disabling bypasses pending membership immediately"),Clusterer.Update(Items,Canvas,0.0f,false).Num(),2);
    TestEqual(TEXT("Re-enabling uses current regions immediately"),Clusterer.Update(Items,Canvas,0.0f,true).Num(),2);
    Items[1].Anchor.X = 599;
    TestEqual(TEXT("The new return begins a fresh confirmation"),Clusterer.Update(Items,Canvas,0.05f).Num(),2);
    Clusterer.Update(Items,Canvas,0.0f,false);
    TestEqual(TEXT("Re-enabling also merges current neighbors immediately"),Clusterer.Update(Items,Canvas,0.0f,true).Num(),1);
    Items[1].Anchor.X = 601;
    Clusterer.Update(Items,Canvas,0.05f);
    TestEqual(TEXT("No previous confirmation time survives the mode switch"),Clusterer.Update(Items,Canvas,0.10f).Num(),1);
    TestEqual(TEXT("Fresh migration still waits for its full confirmation"),Clusterer.Update(Items,Canvas,0.05f).Num(),1);
    TestEqual(TEXT("Fresh migration eventually commits"),Clusterer.Update(Items,Canvas,0.05f).Num(),2);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedCoLocatedGroups, "GHS.DockTruckHUD.Clustering.EquipmentTypesNeverMergeAtSameAnchor", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedCoLocatedGroups::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items = {
        {TEXT("TRUCK-01"),FVector2D(200,200),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-01"),FVector2D(200,200),FVector2D(100,34),TEXT("Stacker")},
        {TEXT("TRUCK-02"),FVector2D(200,200),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-02"),FVector2D(200,200),FVector2D(100,34),TEXT("Stacker")}};
    const TArray<FGroup> Groups = Clusterer.Update(Items,Canvas,0.f);
    if (!TestEqual(TEXT("Identical anchors still produce one group per type"),Groups.Num(),2)) return false;
    TestEqual(TEXT("All four identities remain represented"),Count(Groups),4);
    TestEqual(TEXT("Type ordering is lexical"),Groups[0].EquipmentType,FString(TEXT("DockTruck")));
    TestEqual(TEXT("Second type is independently represented"),Groups[1].EquipmentType,FString(TEXT("Stacker")));
    TestTrue(TEXT("Trucks only aggregate with trucks"),Groups[0].Members==TArray<FString>{TEXT("TRUCK-01"),TEXT("TRUCK-02")});
    TestTrue(TEXT("Stackers only aggregate with stackers"),Groups[1].Members==TArray<FString>{TEXT("STACKER-01"),TEXT("STACKER-02")});
    TestTrue(TEXT("Each type preserves its own member centroid"),Groups[0].Anchor.Equals(Groups[1].Anchor));
    TestTrue(TEXT("Colocated types use a bounded local separation"),
        Groups[0].Position.Y+Groups[0].Size.Y <= Groups[1].Position.Y);
    const auto& Reversed = Clusterer.Update({Items[3],Items[2],Items[1],Items[0]},Canvas,0.f);
    TestEqual(TEXT("Discovery order preserves truck key"),Reversed[0].Key,Groups[0].Key);
    TestEqual(TEXT("Discovery order preserves stacker key"),Reversed[1].Key,Groups[1].Key);

    FClusterer One;
    const FString BeforeTypeChange = One.Update({Items[0]},Canvas,0.f)[0].Key;
    Items[0].EquipmentType = TEXT("Stacker");
    const auto& Changed = One.Update({Items[0]},Canvas,0.f);
    TestTrue(TEXT("The same ID changing type receives a new visual identity"),Changed[0].Key != BeforeTypeChange);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedFourQuadrants, "GHS.DockTruckHUD.Clustering.FourQuadrantsPerEquipmentType", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedFourQuadrants::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items;
    for (int32 Cell=0; Cell<4; ++Cell)
        for (const FString Type : {FString(TEXT("DockTruck")),FString(TEXT("Stacker"))})
            for (int32 Member=0; Member<2; ++Member)
                Items.Add({FString::Printf(TEXT("%s-%d-%d"),*Type,Cell,Member),
                    FVector2D((Cell%2)*600+100+Member*300,(Cell/2)*450+150),FVector2D(100,34),Type});
    const auto& Groups = Clusterer.Update(Items,Canvas,0.f);
    if (!TestEqual(TEXT("Each of four quadrants may contain one group of each type"),Groups.Num(),8)) return false;
    TestEqual(TEXT("All sixteen equipment identities remain represented"),Count(Groups),16);
    TSet<FString> Seen;
    for (int32 Index=0; Index<Groups.Num(); ++Index)
    {
        const FGroup& Group = Groups[Index];
        TestEqual(TEXT("Output is row-major by cell"),Group.CellIndex,Index/2);
        TestEqual(TEXT("Each cell sorts equipment types lexically"),Group.EquipmentType,FString(Index%2?TEXT("Stacker"):TEXT("DockTruck")));
        TestEqual(TEXT("Each typed cell contains its two members"),Group.Members.Num(),2);
        for (const FString& Id : Group.Members)
        {
            TestTrue(TEXT("Every member has its group's type"),Id.StartsWith(Group.EquipmentType+TEXT("-")));
            TestFalse(TEXT("No member appears in two groups"),Seen.Contains(Id));
            Seen.Add(Id);
        }
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedTransitions, "GHS.DockTruckHUD.Clustering.TypePurityAcrossResizeZoomAndMigration", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedTransitions::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items = {
        {TEXT("TRUCK-01"),FVector2D(580,200),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-01"),FVector2D(580,200),FVector2D(100,34),TEXT("Stacker")},
        {TEXT("TRUCK-02"),FVector2D(610,200),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-02"),FVector2D(610,200),FVector2D(100,34),TEXT("Stacker")}};
    auto Check = [&](FVector2D Size,float Delta,bool bAggregate,int32 Expected)
    {
        const auto& Groups = Clusterer.Update(Items,Size,Delta,bAggregate);
        TestEqual(TEXT("Expected independently typed groups"),Groups.Num(),Expected);
        TestEqual(TEXT("Every equipment identity survives the transition"),Count(Groups),Items.Num());
        for (const FGroup& Group : Groups)
            for (const FString& Id : Group.Members)
            {
                const FItem* Item = Items.FindByPredicate([&](const FItem& I) { return I.Id==Id; });
                TestTrue(TEXT("No intermediate frame mixes equipment types"),Item && Item->EquipmentType==Group.EquipmentType);
            }
    };
    Check(Canvas,0.f,true,4);
    Check(FVector2D(1800,900),0.f,true,2);
    Check(FVector2D(1800,900),0.f,false,4);
    Check(FVector2D(1800,900),0.f,true,2);
    Check(Canvas,0.f,true,4);
    Items[0].Anchor.X=620;
    Check(Canvas,.05f,true,4);
    Check(Canvas,.1f,true,4);
    Check(Canvas,.05f,true,4);
    Check(Canvas,.05f,true,3);
    // The migrating truck joins only the truck group; colocated stackers retain
    // their independently committed cells until their own dwell completes.
    const auto& Migrated=Clusterer.Update(Items,Canvas,0.f,true);
    const FGroup* Truck=GroupFor(Migrated,TEXT("TRUCK-01"));
    TestTrue(TEXT("Confirmed truck migration joins its own type"),Truck && Truck->Members.Contains(TEXT("TRUCK-02")));
    Check(Canvas,0.f,false,4);
    Check(Canvas,0.f,true,3);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedNarrowBands, "GHS.DockTruckHUD.Clustering.NarrowViewportUsesBoundedLocalSeparation", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedNarrowBands::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    const FVector2D NarrowCanvas(640,540);
    FClusterer Clusterer;
    TArray<FItem> Items = {
        {TEXT("TRUCK-01"),FVector2D(310,260),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-01"),FVector2D(310,260),FVector2D(100,34),TEXT("Stacker")},
        {TEXT("TRUCK-02"),FVector2D(310,260),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-02"),FVector2D(310,260),FVector2D(100,34),TEXT("Stacker")}};
    const TArray<FGroup> Initial = Clusterer.Update(Items,NarrowCanvas,0.f,true);
    if (!TestEqual(TEXT("Colocated equipment forms two separate type groups"),Initial.Num(),2)) return false;
    auto CheckLocal = [&](const TArray<FGroup>& Groups)
    {
        for (const FGroup& Group : Groups)
        {
            TestTrue(TEXT("Local separation never pushes a label farther than one row from its natural position"),
                FMath::Abs(Group.Position.Y-210.0)<=40.0001);
            TestTrue(TEXT("Labels remain horizontally centered across quadrant midlines"),
                FMath::IsNearlyEqual(Group.Position.X,Group.Anchor.X-Group.Size.X/2));
        }
    };
    CheckLocal(Initial);
    TestTrue(TEXT("Two type badges remain non-overlapping in the narrow viewport"),
        Initial[0].Position.Y+Initial[0].Size.Y<=Initial[1].Position.Y);
    TestTrue(TEXT("The per-type centroid remains the actual projected anchor"),Initial[0].Anchor.Equals(FVector2D(310,260)));
    const TArray<FGroup> Reversed=Clusterer.Update({Items[3],Items[2],Items[1],Items[0]},NarrowCanvas,0.f,true);
    for (int32 Index=0; Index<2; ++Index)
        TestTrue(TEXT("Discovery order cannot change a locked local offset"),Reversed[Index].Position.Equals(Initial[Index].Position));

    // A cell boundary only affects group membership. It cannot cause the same
    // group's label to snap to a quadrant edge or a reserved screen band.
    Items[1].Anchor.X=Items[3].Anchor.X=330;
    for (int32 Frame=0; Frame<8; ++Frame) CheckLocal(Clusterer.Update(Items,NarrowCanvas,.05f,true));
    const auto& Migrated=Clusterer.Update(Items,NarrowCanvas,0.f,true);
    const FGroup* Stacker=GroupFor(Migrated,TEXT("STACKER-01"));
    TestTrue(TEXT("Migrating stackers retain their local offset while tracking their anchor"),
        Stacker && Stacker->CellIndex==1 && FMath::IsNearlyEqual(Stacker->Position.Y,Initial[1].Position.Y));

    const auto& Near=Clusterer.Update(Items,NarrowCanvas,0.f,false);
    TestEqual(TEXT("Near mode still shows all independent devices"),Near.Num(),4);
    const FGroup* TruckNear=GroupFor(Near,TEXT("TRUCK-01"));
    TestTrue(TEXT("Near labels use their natural projection without local separation"),TruckNear && FMath::IsNearlyEqual(TruckNear->Position.Y,210.0));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedReservedBands, "GHS.DockTruckHUD.Clustering.SurvivingKeyStaysStillWhenOtherTypeLeavesOrReenters", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedReservedBands::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    const FVector2D NarrowCanvas(640,540);
    FClusterer Clusterer;
    const TArray<FItem> Trucks = {
        {TEXT("TRUCK-01"),FVector2D(310,260),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("TRUCK-02"),FVector2D(310,260),FVector2D(100,34),TEXT("DockTruck")}};
    const TArray<FItem> Stackers = {
        {TEXT("STACKER-01"),FVector2D(310,260),FVector2D(100,34),TEXT("Stacker")},
        {TEXT("STACKER-02"),FVector2D(310,260),FVector2D(100,34),TEXT("Stacker")}};
    TArray<FItem> Both = Trucks;
    Both.Append(Stackers);
    const TArray<FGroup> Initial = Clusterer.Update(Both,NarrowCanvas,0.f,true);
    if (!TestEqual(TEXT("Both supported types have independent local labels"),Initial.Num(),2)) return false;
    const FVector2D TruckPosition=Initial[0].Position;
    TestTrue(TEXT("Even an initially overlapping label stays within one row of its real anchor"),FMath::Abs(TruckPosition.Y-210.0)<=40.0001);

    const auto& TrucksAlone=Clusterer.Update(Trucks,NarrowCanvas,.05f,true);
    if (!TestEqual(TEXT("All stackers may leave the viewport"),TrucksAlone.Num(),1)) return false;
    TestTrue(TEXT("The last stacker leaving cannot shift the truck badge"),TrucksAlone[0].Position.Equals(TruckPosition));
    const auto& StackersReturned=Clusterer.Update(Both,NarrowCanvas,.05f,true);
    TestTrue(TEXT("Stacker reentry cannot shift the truck badge"),StackersReturned[0].Position.Equals(TruckPosition));
    const FVector2D ReturnedStackerPosition=StackersReturned[1].Position;

    const auto& StackersAlone=Clusterer.Update(Stackers,NarrowCanvas,.05f,true);
    if (!TestEqual(TEXT("All trucks may leave the viewport"),StackersAlone.Num(),1)) return false;
    TestTrue(TEXT("The last truck leaving cannot shift the stacker badge"),StackersAlone[0].Position.Equals(ReturnedStackerPosition));
    const auto& TrucksReturned=Clusterer.Update(Both,NarrowCanvas,.05f,true);
    TestTrue(TEXT("Truck reentry cannot shift the stacker badge"),TrucksReturned[1].Position.Equals(ReturnedStackerPosition));
    TestTrue(TEXT("Only the incoming key may move and its movement remains local"),FMath::Abs(TrucksReturned[0].Position.Y-210.0)<=40.0001);

    const auto& Near=Clusterer.Update(Trucks,NarrowCanvas,0.f,false);
    TestTrue(TEXT("Local offsets never constrain near independent labels"),Near.Num()==2 && FMath::IsNearlyEqual(Near[0].Position.Y,210.0));
    FClusterer Legacy;
    const auto& Untyped=Legacy.Update({Item(TEXT("LEGACY"),310,260)},NarrowCanvas,0.f,true);
    TestTrue(TEXT("Legacy empty type stays at the natural anchor position"),Untyped.Num()==1 && FMath::IsNearlyEqual(Untyped[0].Position.Y,210.0));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedNaturalAnchors, "GHS.DockTruckHUD.Clustering.SeparatedTypesUseTheirActualProjectedCentroids", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedNaturalAnchors::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const auto& Groups=Clusterer.Update({
        {TEXT("TRUCK-01"),FVector2D(300,450),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("TRUCK-02"),FVector2D(340,470),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-01"),FVector2D(700,150),FVector2D(100,34),TEXT("Stacker")},
        {TEXT("STACKER-02"),FVector2D(740,170),FVector2D(100,34),TEXT("Stacker")}},FVector2D(1920,1080),0.f,true);
    if (!TestEqual(TEXT("Separated types still use two groups in one quadrant"),Groups.Num(),2)) return false;
    TestTrue(TEXT("Truck centroid is the mean of its own projected members"),Groups[0].Anchor.Equals(FVector2D(320,460)));
    TestTrue(TEXT("Stacker centroid is the mean of its own projected members"),Groups[1].Anchor.Equals(FVector2D(720,160)));
    TestTrue(TEXT("Truck label stays fifty pixels above the real projected centroid"),Groups[0].Position.Equals(FVector2D(228,410)));
    TestTrue(TEXT("Stacker label stays fifty pixels above its different real projected centroid"),Groups[1].Position.Equals(FVector2D(628,110)));
    FClusterer Single;
    const auto& Singleton=Single.Update({{TEXT("TRUCK-01"),FVector2D(850,520),FVector2D(100,34),TEXT("DockTruck")}},FVector2D(1920,1080),0.f,true);
    TestTrue(TEXT("An aggregated-mode singleton also follows its own anchor with no reserved band"),
        Singleton.Num()==1 && Singleton[0].Position.Equals(FVector2D(800,470)));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedIncomingKey, "GHS.DockTruckHUD.Clustering.NewOverlappingKeyCannotDisplaceLockedExistingKey", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedIncomingKey::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    TArray<FItem> Items={
        {TEXT("TRUCK-01"),FVector2D(310,260),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-01"),FVector2D(310,260),FVector2D(100,34),TEXT("Stacker")}};
    const TArray<FGroup> Initial=Clusterer.Update(Items,FVector2D(640,540),0.f,true);
    if (Initial.Num()!=2) return false;
    const FVector2D ExistingPosition=Initial[0].Position;
    Items[1].Id=TEXT("STACKER-02");
    Items[1].Anchor.Y=240;
    const TArray<FGroup> Changed=Clusterer.Update(Items,FVector2D(640,540),0.f,true);
    TestTrue(TEXT("A new overlapping membership cannot move the surviving group key"),Changed[0].Position.Equals(ExistingPosition));
    TestTrue(TEXT("New key separation is limited to forty pixels from its own natural position"),FMath::Abs(Changed[1].Position.Y-190.0)<=40.0001);
    TestTrue(TEXT("The incoming key takes an available local side without moving the old key"),
        Changed[1].Position.Y+Changed[1].Size.Y<=Changed[0].Position.Y || Changed[0].Position.Y+Changed[0].Size.Y<=Changed[1].Position.Y);
    for (int32 Frame=0; Frame<20; ++Frame)
    {
        const auto& Stable=Clusterer.Update(Items,FVector2D(640,540),.05f,true);
        TestTrue(TEXT("Local offsets are not iteratively accumulated"),Stable[0].Position.Equals(Changed[0].Position) && Stable[1].Position.Equals(Changed[1].Position));
    }
    Items[0].Anchor.Y+=5;
    Items[1].Anchor.Y+=5;
    const auto& Moved=Clusterer.Update(Items,FVector2D(640,540),.05f,true);
    TestTrue(TEXT("A locked local placement still follows the real moving anchor"),
        Moved[0].Position.Equals(Changed[0].Position+FVector2D(0,5)) && Moved[1].Position.Equals(Changed[1].Position+FVector2D(0,5)));
    Clusterer.Reset();
    const auto& Reset=Clusterer.Update({Items[0]},FVector2D(640,540),0.f,true);
    TestTrue(TEXT("Reset removes stale local offsets"),Reset.Num()==1 && FMath::IsNearlyEqual(Reset[0].Position.Y,215.0));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSThirdTypeReflow, "GHS.DockTruckHUD.Clustering.ThirdTypeReflowsOnlyItsConflictingLocalCluster", GHSTruckHUDLayoutTests::Flags)
bool FGHSThirdTypeReflow::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    FClusterer Clusterer;
    const TArray<FItem> Existing = {
        {TEXT("TRUCK-01"),FVector2D(310,260),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-01"),FVector2D(310,260),FVector2D(100,34),TEXT("Stacker")},
        // Same horizontal footprint, but another local cluster in the lower cell.
        {TEXT("REMOTE-TRUCK"),FVector2D(310,700),FVector2D(100,34),TEXT("DockTruck")}};
    const TArray<FGroup> Initial=Clusterer.Update(Existing,Canvas,0.f,true);
    if (!TestEqual(TEXT("Two co-located types and a remote group are registered"),Initial.Num(),3)) return false;
    const FVector2D RemotePosition=GroupFor(Initial,TEXT("REMOTE-TRUCK"))->Position;
    TArray<FItem> ThreeTypes=Existing;
    ThreeTypes.Add({TEXT("FORK-01"),FVector2D(310,260),FVector2D(100,34),TEXT("MannedForklift")});
    const TArray<FGroup> Added=Clusterer.Update(ThreeTypes,Canvas,.05f,true);
    if (!TestEqual(TEXT("A new third type keeps all four independent groups"),Added.Num(),4)) return false;
    for (int32 A=0; A<Added.Num(); ++A)
    {
        const FGroup& Group=Added[A];
        TestTrue(TEXT("Reflow stays within forty pixels of the real local anchor"),FMath::Abs(Group.Position.Y-(Group.Anchor.Y-50))<=40.0001);
        for (int32 B=A+1; B<Added.Num(); ++B)
        {
            const FGroup& Other=Added[B];
            const bool bOverlap=Group.Position.X<Other.Position.X+Other.Size.X && Other.Position.X<Group.Position.X+Group.Size.X
                && Group.Position.Y<Other.Position.Y+Other.Size.Y && Other.Position.Y<Group.Position.Y+Group.Size.Y;
            TestFalse(TEXT("An entering third equipment type cannot cover either existing type"),bOverlap);
        }
    }
    TestTrue(TEXT("A separated local cluster is not displaced by the new type"),GroupFor(Added,TEXT("REMOTE-TRUCK"))->Position.Equals(RemotePosition));
    for (int32 Frame=0; Frame<20; ++Frame)
    {
        const auto& Stable=Clusterer.Update(ThreeTypes,Canvas,.05f,true);
        for (const FGroup& Group : Added)
            TestTrue(TEXT("The solved three-type layout does not repeatedly move"),GroupFor(Stable,*Group.Members[0])->Position.Equals(Group.Position));
    }
    const TArray<FGroup> Left=Clusterer.Update(Existing,Canvas,.05f,true);
    for (const FGroup& Group : Left)
        TestTrue(TEXT("Removing the third type keeps surviving keys stationary"),Group.Position.Equals(GroupFor(Added,*Group.Members[0])->Position));
    const auto& Returned=Clusterer.Update(ThreeTypes,Canvas,.05f,true);
    for (const FGroup& Group : Added)
        TestTrue(TEXT("Third-type reentry reuses the available local gap"),GroupFor(Returned,*Group.Members[0])->Position.Equals(Group.Position));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTypedLocalEdges, "GHS.DockTruckHUD.Clustering.LocalSeparationRespectsScreenEdgesAndOriginalVerticalOrder", GHSTruckHUDLayoutTests::Flags)
bool FGHSTypedLocalEdges::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    for (double AnchorY : {10.0,530.0})
    {
        FClusterer Clusterer;
        const auto& Groups=Clusterer.Update({
            {TEXT("TRUCK-01"),FVector2D(310,AnchorY),FVector2D(100,34),TEXT("DockTruck")},
            {TEXT("STACKER-01"),FVector2D(310,AnchorY),FVector2D(100,34),TEXT("Stacker")}},FVector2D(640,540),0.f,true);
        if (!TestEqual(TEXT("Both edge labels remain represented"),Groups.Num(),2)) return false;
        const double BaseY=AnchorY==10.0?12.0:480.0;
        for (const FGroup& Group : Groups)
        {
            TestTrue(TEXT("Edge labels stay wholly inside the viewport"),Group.Position.Y>=12 && Group.Position.Y+Group.Size.Y<=528);
            TestTrue(TEXT("Edge handling cannot exceed the local forty-pixel bound"),FMath::Abs(Group.Position.Y-BaseY)<=40.0001);
        }
        TestTrue(TEXT("Two local rows remain separated at the top and bottom edges"),Groups[0].Position.Y+Groups[0].Size.Y<=Groups[1].Position.Y);
    }
    FClusterer ReverseOrder;
    const auto& Reversed=ReverseOrder.Update({
        {TEXT("TRUCK-01"),FVector2D(310,260),FVector2D(100,34),TEXT("DockTruck")},
        {TEXT("STACKER-01"),FVector2D(310,250),FVector2D(100,34),TEXT("Stacker")}},FVector2D(640,540),0.f,true);
    TestTrue(TEXT("When a stacker's real anchor is above the truck, local separation preserves that order"),
        Reversed.Num()==2 && Reversed[1].Position.Y+Reversed[1].Size.Y<=Reversed[0].Position.Y);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSCrossCellRealCapture, "GHS.DockTruckHUD.Clustering.ActualLowAngleAndNarrowCapturesRemainReadableAndLocal", GHSTruckHUDLayoutTests::Flags)
bool FGHSCrossCellRealCapture::RunTest(const FString& Parameters)
{
    using namespace GHSTruckHUDLayoutTests;
    struct FSample { double X,Y,Width; const TCHAR* Type; int32 Members; };
    // Projected centroids and widths from the real LowAngle/Narrow runtime
    // reports, converted from widget coordinates back to logical HUD pixels.
    const TArray<FSample> Fixtures[] = {
        {
            {820.500000000,499.000000000,184.000000000,TEXT("Stacker"),2},
            {1579.000000000,527.250000000,184.000000000,TEXT("DockTruck"),2},
            {1204.500000000,499.000000000,184.000000000,TEXT("Stacker"),2},
            {644.766666667,584.033333333,184.000000000,TEXT("DockTruck"),2},
            {821.000000000,562.000000000,184.000000000,TEXT("Stacker"),2},
            {1257.055552165,578.722225613,184.000000000,TEXT("DockTruck"),2},
            {1303.000000000,562.000000000,184.000000000,TEXT("Stacker"),2}
        },
        {
            {191.911122319,665.777807931,184.000000000,TEXT("DockTruck"),2},
            {276.740763268,654.814824917,184.000000000,TEXT("Stacker"),2},
            {351.407417890,680.296341416,184.000000000,TEXT("Stacker"),2},
            {278.797400342,746.143827139,184.000000000,TEXT("DockTruck"),2},
            {291.555576968,723.555586177,248.554656982,TEXT("Stacker"),1},
            {411.851867420,837.096330576,184.000000000,TEXT("DockTruck"),2},
            {404.977799324,776.177850688,184.000000000,TEXT("Stacker"),2}
        }};
    const FVector2D Canvases[] = {FVector2D(1920,1080),FVector2D(640,1422.222222222)};
    for (int32 Fixture=0; Fixture<2; ++Fixture)
    {
        FClusterer Clusterer;
        TArray<FItem> Items;
        for (int32 Sample=0; Sample<Fixtures[Fixture].Num(); ++Sample)
            for (int32 Member=0; Member<Fixtures[Fixture][Sample].Members; ++Member)
            {
                const FSample& Value=Fixtures[Fixture][Sample];
                Items.Add({FString::Printf(TEXT("Fixture%d-%d"),Sample,Member),FVector2D(Value.X,Value.Y),FVector2D(Value.Width,34),Value.Type});
            }
        const TArray<FGroup> Groups=Clusterer.Update(Items,Canvases[Fixture],0.f,true);
        if (!TestEqual(TEXT("Captured seven groups retain their independent memberships"),Groups.Num(),7)) return false;
        for (int32 A=0; A<Groups.Num(); ++A)
        {
            const FGroup& Group=Groups[A];
            TestTrue(TEXT("Readable labels remain horizontally centered on their actual equipment"),
                FMath::IsNearlyEqual(Group.Position.X,Group.Anchor.X-Group.Size.X/2));
            TestTrue(TEXT("Every local adjustment remains within forty logical pixels"),FMath::Abs(Group.Position.Y-(Group.Anchor.Y-50))<=40.0001);
            for (int32 B=A+1; B<Groups.Num(); ++B)
            {
                const FGroup& Other=Groups[B];
                const bool bOverlap=Group.Position.X<Other.Position.X+Other.Size.X && Other.Position.X<Group.Position.X+Group.Size.X
                    && Group.Position.Y<Other.Position.Y+Other.Size.Y && Other.Position.Y<Group.Position.Y+Group.Size.Y;
                TestFalse(TEXT("Actual cross-cell and same-type labels remain individually readable"),bOverlap);
            }
        }
        for (int32 Frame=0; Frame<12; ++Frame)
        {
            const auto& Stable=Clusterer.Update(Items,Canvases[Fixture],.05f,true);
            for (int32 Index=0; Index<Groups.Num(); ++Index)
                TestTrue(TEXT("A solved real layout stays locked instead of repeatedly avoiding neighbors"),Stable[Index].Position.Equals(Groups[Index].Position));
        }
    }
    return true;
}
#endif
