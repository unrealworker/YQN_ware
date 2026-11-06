#if WITH_DEV_AUTOMATION_TESTS
#include "../SGHSGlobeWarehouseOverlay.h"
#include "GHSAutomationTestFlags.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/Input/SButton.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeOverlayGeometryTest, "GHS.Globe.PixelOverlayGeometry", GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSGlobeOverlayGeometryTest::RunTest(const FString&)
{
    const FSlateRect Scene(0, 62, 1415, 1080);
    for (const FVector2D Point : {FVector2D(300, 350), FVector2D(800, 600), FVector2D(20, 90), FVector2D(1390, 1050)})
    {
        const auto Layout = FGHSGlobePOIGeometry::Make(Point, Scene);
        TestTrue(TEXT("Card has a constant physical pixel size"), Layout.CardSize.Equals(FVector2D(248, 48)));
        TestTrue(TEXT("Leader begins exactly on the fixed-size point rim"), FMath::IsNearlyEqual((Layout.LineStart - Point).Size(), 10., .0001));
        const double Bottom = Layout.CardPosition.Y + Layout.CardSize.Y;
        TestTrue(TEXT("Leader is connected to a card edge"), FMath::IsNearlyEqual(Layout.LineEnd.Y, Layout.CardPosition.Y, .0001) || FMath::IsNearlyEqual(Layout.LineEnd.Y, Bottom, .0001));
        TestTrue(TEXT("Card stays within the globe scene"), Layout.CardPosition.X >= Scene.Left && Layout.CardPosition.Y >= Scene.Top
            && Layout.CardPosition.X + Layout.CardSize.X <= Scene.Right && Bottom <= Scene.Bottom);
    }
    const FVector2D Point(700, 500), Delta(100, 30);
    const auto First = FGHSGlobePOIGeometry::Make(Point, Scene);
    const auto Next = FGHSGlobePOIGeometry::Make(Point + Delta, Scene);
    TestTrue(TEXT("Card and leader translate together with the same projected anchor"),
        (Next.CardPosition - First.CardPosition).Equals(Delta) && (Next.LineStart - First.LineStart).Equals(Delta) && (Next.LineEnd - First.LineEnd).Equals(Delta));
    TestEqual(TEXT("Fixed point diameter independent of world/camera units"), FGHSGlobePOIGeometry::PointDiameter, 20.f);
    const auto Left = FGHSGlobePOIGeometry::Make(FVector2D(650, 500), Scene);
    const TArray<FSlateRect> Occupied{FSlateRect(Left.CardPosition.X, Left.CardPosition.Y,
        Left.CardPosition.X + Left.CardSize.X, Left.CardPosition.Y + Left.CardSize.Y)};
    const FVector2D RightPoint(800, 500);
    const auto Right = FGHSGlobePOIGeometry::AvoidOverlaps(RightPoint, Scene, Occupied);
    TestTrue(TEXT("Nearby but unclustered warehouses use opposite label rows"), Right.CardPosition.Y > RightPoint.Y);
    TestTrue(TEXT("Resolved cards retain clearance"), Right.CardPosition.Y >= Occupied[0].Bottom + 8);
    TestTrue(TEXT("Resolved leader still joins its own point rim and card edge"),
        FMath::IsNearlyEqual((Right.LineStart - RightPoint).Size(), 10., .0001)
        && FMath::IsNearlyEqual(Right.LineEnd.Y, Right.CardPosition.Y, .0001));
    const auto Repeat = FGHSGlobePOIGeometry::AvoidOverlaps(RightPoint, Scene, Occupied);
    TestTrue(TEXT("Unchanged inputs do not swap label sides between frames"), Repeat.CardPosition.Equals(Right.CardPosition));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeOverlayInteractionTest, "GHS.Globe.PixelOverlayInteraction", GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSGlobeOverlayInteractionTest::RunTest(const FString&)
{
    if (!TestTrue(TEXT("Slate application is available"), FSlateApplication::IsInitialized())) return false;
    TArray<FString> Selected, Entered, SelectionSources, EntrySources;
    TArray<TArray<FString>> Clusters;
    const auto Overlay = SNew(SGHSGlobeWarehouseOverlay)
        .OnSelect_Lambda([&](const FString& Id, const FString& Source) { Selected.Add(Id); SelectionSources.Add(Source); })
        .OnEnter_Lambda([&](const FString& Id, const FString& Source) { Entered.Add(Id); EntrySources.Add(Source); })
        .OnCluster_Lambda([&Clusters](const TArray<FString>& Ids) { Clusters.Add(Ids); });
    Overlay->SetSceneRect(FSlateRect(0, 62, 1415, 1080));
    TestFalse(TEXT("Overlay does not intercept pointer input over the empty globe"), Overlay->GetVisibility().IsHitTestVisible());
    TestTrue(TEXT("Overlay permits hit-testing its interactive cards"), Overlay->GetVisibility().AreChildrenHitTestVisible());
    auto FindButtons = [&Overlay]()
    {
        TArray<TSharedRef<SButton>> Buttons;
        TFunction<void(const TSharedRef<SWidget>&)> Visit = [&](const TSharedRef<SWidget>& Widget)
        {
            if (Widget->GetType() == FName(TEXT("SGlobeInputButton"))) Buttons.Add(StaticCastSharedRef<SButton>(Widget));
            FChildren* Children = Widget->GetChildren();
            for (int32 Index = 0; Index < Children->Num(); ++Index) Visit(Children->GetChildAt(Index));
        };
        Visit(Overlay);
        return Buttons;
    };
    auto Activate = [this](const TSharedRef<SButton>& Button, FKey Key = EKeys::Enter)
    {
        TestTrue(TEXT("Native card button participates in hit-testing"), Button->GetVisibility().IsHitTestVisible());
        TestTrue(TEXT("Native card button supports keyboard activation"), Button->SupportsKeyboardFocus());
        // Exercise the actual SButton down/up event path without creating a
        // native window or changing focus/capture in the user's editor.
        const FKeyEvent Accept(Key, FModifierKeysState(), 0, false, 0, 0);
        const FGeometry Geometry = FGeometry::MakeRoot(FVector2D(248, 48), FSlateLayoutTransform());
        TestTrue(TEXT("Enter key down is handled by SButton"), Button->OnKeyDown(Geometry, Accept).IsEventHandled());
        TestTrue(TEXT("Enter key up is handled by SButton"), Button->OnKeyUp(Geometry, Accept).IsEventHandled());
    };
    FGHSGlobeScreenMarker First;
    First.Id = TEXT("ghs-ca"); First.Name = TEXT("GHS · 加州仓库"); First.Ids = {First.Id}; First.PointPixels = FVector2D(600, 500);
    Overlay->SetMarkers({First});
    auto Buttons = FindButtons();
    if (!TestEqual(TEXT("A warehouse exposes selection and entry buttons"), Buttons.Num(), 2)) return false;
    const auto OriginalSelectButton = Buttons[0];
    Activate(Buttons[0]);
    TestTrue(TEXT("Selection event reaches the overlay with the warehouse identity"), Selected.Num() == 1 && Selected[0] == First.Id && Entered.IsEmpty());
    Activate(Buttons[1]);
    TestTrue(TEXT("Entry arrow reaches its separate overlay callback"), Entered.Num() == 1 && Entered[0] == First.Id);
    TestEqual(TEXT("Enter is identified as keyboard selection"), SelectionSources.Last(), FString(TEXT("keyboard")));
    TestEqual(TEXT("Enter is identified as keyboard entry"), EntrySources.Last(), FString(TEXT("keyboard")));
    Activate(Buttons[0], EKeys::SpaceBar);
    TestEqual(TEXT("Space activation is also keyboard"), SelectionSources.Last(), FString(TEXT("keyboard")));
    // MouseDown click mode exercises real pointer dispatch without OS capture.
    Buttons[0]->SetClickMethod(EButtonClickMethod::MouseDown);
    const FGeometry ClickGeometry = FGeometry::MakeRoot(FVector2D(248, 48), FSlateLayoutTransform());
    const FPointerEvent Pointer(0, FVector2D(20, 20), FVector2D(20, 20),
        TSet<FKey>{EKeys::LeftMouseButton}, EKeys::LeftMouseButton, 0.f, FModifierKeysState());
    TestTrue(TEXT("Pointer press reaches the native button"), Buttons[0]->OnMouseButtonDown(ClickGeometry, Pointer).IsEventHandled());
    TestEqual(TEXT("Pointer overrides the prior keyboard source"), SelectionSources.Last(), FString(TEXT("pointer")));
    Buttons[0]->OnMouseButtonUp(ClickGeometry, Pointer);
    Buttons[0]->SetClickMethod(EButtonClickMethod::DownAndUp);
    Activate(Buttons[0]);
    TestEqual(TEXT("Keyboard overrides the prior pointer source"), SelectionSources.Last(), FString(TEXT("keyboard")));

    const int32 BeforeNonClick = Selected.Num();
    const FPointerEvent RightPointer(0, FVector2D(20, 20), FVector2D(20, 20),
        TSet<FKey>{EKeys::RightMouseButton}, EKeys::RightMouseButton, 0.f, FModifierKeysState());
    Buttons[0]->OnMouseButtonDown(ClickGeometry, RightPointer);
    Buttons[0]->OnMouseButtonUp(ClickGeometry, RightPointer);
    TestEqual(TEXT("Right button events do not activate the warehouse"), Selected.Num(), BeforeNonClick);
    Buttons[0]->SimulateClick();
    TestEqual(TEXT("Accessibility activation after non-click pointer events stays unknown"), SelectionSources.Last(), FString(TEXT("unknown")));
    const FKeyEvent NonActivationKey(EKeys::A, FModifierKeysState(), 0, false, 0, 0);
    Buttons[0]->OnKeyDown(ClickGeometry, NonActivationKey);
    Buttons[0]->OnKeyUp(ClickGeometry, NonActivationKey);
    Buttons[0]->SimulateClick();
    TestEqual(TEXT("Non-activation keys also leave no stale input source"), SelectionSources.Last(), FString(TEXT("unknown")));

    const int32 SelectedBeforeFade = Selected.Num(), EnteredBeforeFade = Entered.Num();
    Overlay->SetPresentation(false, false, false);
    TestFalse(TEXT("Retiring overlay immediately closes its child hit targets"), Overlay->GetVisibility().AreChildrenHitTestVisible());
    TestFalse(TEXT("Retiring overlay is no longer interactive before its first tick"), Overlay->IsAnnotationInteractive());
    Activate(Buttons[0]); Activate(Buttons[1]);
    TestEqual(TEXT("Focused retiring buttons cannot issue a selection"), Selected.Num(), SelectedBeforeFade);
    TestEqual(TEXT("Focused retiring buttons cannot issue an entry"), Entered.Num(), EnteredBeforeFade);
    Overlay->AdvancePresentation(.08f);
    TestTrue(TEXT("Retiring layer is still painted at an intermediate alpha"), Overlay->GetAnnotationOpacity() > 0 && Overlay->GetAnnotationOpacity() < 1);
    Overlay->SetPresentation(true, true, false, true);

    First.PointPixels += FVector2D(80, 20); First.bSelected = true;
    Overlay->SetMarkers({First});
    Buttons = FindButtons();
    TestTrue(TEXT("Projection updates preserve the focused button rather than rebuilding it"), Buttons[0] == OriginalSelectButton);
    FGHSGlobeScreenMarker Second = First;
    Second.Id = TEXT("mpr-nj"); Second.Name = TEXT("MPR · 新泽西仓库"); Second.Ids = {Second.Id};
    Overlay->SetMarkers({Second});
    Buttons = FindButtons();
    Activate(Buttons[0]); Activate(Buttons[1]);
    TestTrue(TEXT("Replacing the visible warehouse does not retain stale event targets"), Selected.Last() == Second.Id && Entered.Last() == Second.Id);

    FGHSGlobeScreenMarker Cluster;
    Cluster.Id = TEXT("cluster-test"); Cluster.Ids = {First.Id, Second.Id}; Cluster.PointPixels = FVector2D(700, 500);
    Overlay->SetMarkers({Cluster});
    Buttons = FindButtons();
    if (!TestEqual(TEXT("An aggregate exposes one cluster button"), Buttons.Num(), 1)) return false;
    Activate(Buttons[0]);
    TestTrue(TEXT("Cluster activation carries all member identities"), Clusters.Num() == 1 && Clusters[0] == Cluster.Ids);
    Overlay->SetMarkers({});
    TestEqual(TEXT("Hidden or empty globe markers leave no clickable card targets"), FindButtons().Num(), 0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeOverlayFadeTest, "GHS.Globe.PixelOverlaySceneFade", GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSGlobeOverlayFadeTest::RunTest(const FString&)
{
    FGHSGlobeAnnotationFade Fade;
    Fade.SetVisible(true, false);
    TestEqual(TEXT("Initial valid globe does not fade"), Fade.Opacity, 1.f);
    TestTrue(TEXT("Curve matches CSS standard at 50 percent time, not parameter t"),
        FMath::IsNearlyEqual(FGHSGlobeAnnotationFade::StandardEase(.5f), .7755613f, .00001f));
    float Last = 0;
    for (int32 I = 0; I <= 100; ++I)
    {
        const float Value = FGHSGlobeAnnotationFade::StandardEase(I / 100.f);
        TestTrue(TEXT("Standard alpha curve is bounded and monotonic"), Value >= Last && Value <= 1.f);
        Last = Value;
    }
    Fade.SetVisible(false, false);
    Fade.Advance(.08f);
    TestTrue(TEXT("Exit is at the expected 160ms midpoint"), FMath::IsNearlyEqual(Fade.Opacity, .2244387f, .00001f));
    Fade.SetVisible(false, false);
    Fade.Advance(.08f);
    TestEqual(TEXT("Repeated per-frame requests do not restart the exit clock"), Fade.Opacity, 0.f);
    Fade.SetVisible(true, false);
    Fade.Advance(.09f);
    TestTrue(TEXT("Return uses the 180ms midpoint"), FMath::IsNearlyEqual(Fade.Opacity, .7755613f, .00001f));
    const float Current = Fade.Opacity;
    Fade.SetVisible(false, false);
    TestEqual(TEXT("Interrupted return begins exit at the current alpha"), Fade.Opacity, Current);
    Fade.Advance(.08f);
    TestTrue(TEXT("Reversed fade continues smoothly from its visible alpha"),
        FMath::IsNearlyEqual(Fade.Opacity, Current * (1.f - .7755613f), .00001f));
    Fade.SetVisible(false, false, true);
    Fade.SetVisible(true, true);
    Fade.Advance(.06f);
    TestTrue(TEXT("Reduced motion retains a 120ms opacity transition"), FMath::IsNearlyEqual(Fade.Opacity, .7755613f, .00001f));
    Fade.Advance(.06f);
    TestEqual(TEXT("Reduced return finishes after 120ms"), Fade.Opacity, 1.f);
    Fade.SetVisible(false, true); Fade.Advance(.12f);
    TestEqual(TEXT("Reduced exit also finishes after 120ms"), Fade.Opacity, 0.f);
    Fade.SetVisible(true, false, true);
    TestEqual(TEXT("Keyboard return applies immediately"), Fade.Opacity, 1.f);
    Fade.SetVisible(false, false, true);
    TestEqual(TEXT("Keyboard exit or hidden world clears immediately"), Fade.Opacity, 0.f);
    Fade.Advance(100.f);
    TestEqual(TEXT("A hidden world never revives old markers"), Fade.Opacity, 0.f);
    return true;
}
#endif
