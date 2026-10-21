#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSTwinSceneData.h"
#include "../GHSTwinSearchLayout.h"
#include "../GHSTwinHUDWidget.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Slate/SObjectWidget.h"
#include "Widgets/SNullWidget.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSearchCurrentScene,"GHS.TwinUI.Search.UsesCurrentSceneIdentityAndChineseNames",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinSearchCurrentScene::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(GEngine) GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    auto* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    auto MakeDevice=[&](const TCHAR* Id)
    {
        auto* Actor=World->SpawnActor<AStaticMeshActor>();
        Actor->GetStaticMeshComponent()->SetStaticMesh(Cube); Actor->Tags={FName(Id)}; return Actor;
    };
    auto* First=MakeDevice(TEXT("TwinId=GHS_AGV_07"));
    MakeDevice(TEXT("TwinId=GHS_AGV_08"));
    auto* Fork=MakeDevice(TEXT("TwinId=GHN_MannedForklift_07"));
    Fork->Tags.Add(TEXT("NormalWarehouseMannedForklift"));
    auto* Pallets=World->SpawnActor<AActor>();
    auto* Cargo=NewObject<UInstancedStaticMeshComponent>(Pallets);
    Pallets->SetRootComponent(Cargo); Pallets->AddInstanceComponent(Cargo);
    Cargo->SetStaticMesh(DuplicateObject<UStaticMesh>(Cube,GetTransientPackage(),MakeUniqueObjectName(GetTransientPackage(),UStaticMesh::StaticClass(),TEXT("SM_GHS_Presentation_Cargo_Search"))));
    Cargo->RegisterComponent(); Cargo->AddInstance(FTransform::Identity);
    FGHSTwinSceneData Scene; Scene.Refresh(World);
    const auto Before=Scene.GetCacheStats();
    int32 Total=0; const auto Results=Scene.Search(TEXT(" agv "),1,&Total);
    TestEqual(TEXT("Type matches all actual AGVs case-insensitively"),Total,2);
    TestEqual(TEXT("Result limit is enforced"),Results.Num(),1);
    if(!Results.IsEmpty()) TestEqual(TEXT("Stable identity ordering"),Results[0].Id,FString(TEXT("AGV-07")));
    const auto ForkResults=Scene.Search(TEXT("叉车"));
    TestTrue(TEXT("Chinese type returns the real forklift"),ForkResults.Num()==1 && ForkResults[0].Id==TEXT("FORK-07"));
    const auto Exact=Scene.Search(TEXT("agv-08"));
    TestTrue(TEXT("Exact identifier search"),Exact.Num()==1 && Exact[0].Id==TEXT("AGV-08"));
    TestEqual(TEXT("No sample AGV invented"),Scene.Search(TEXT("AGV-999")).Num(),0);
    TestTrue(TEXT("Material query finds actual pallet geometry"),Scene.Search(TEXT("物料")).ContainsByPredicate([](const FGHSTwinSearchResult& R){return R.Id.StartsWith(TEXT("PALLET:"));}));
    TestEqual(TEXT("Search does not scan the world"),Scene.GetCacheStats().WorldScans,Before.WorldScans);
    TestEqual(TEXT("Search does not serialize snapshots"),Scene.GetCacheStats().SnapshotSerializations,Before.SnapshotSerializations);
    First->Destroy(); Scene.Refresh(World);
    TestEqual(TEXT("Destroyed model disappears"),Scene.Search(TEXT("agv")).Num(),1);
    Scene.Refresh(nullptr);
    TestEqual(TEXT("Changing away from warehouse clears index"),Scene.Search(TEXT("叉车")).Num(),0);
    if(GEngine) GEngine->DestroyWorldContext(World); World->DestroyWorld(false);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSearchBridge,"GHS.TwinUI.Search.StreamCommandsAreScopedAndSelectionsValidated",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinSearchBridge::RunTest(const FString&)
{
    auto* HUD=NewObject<UGHSTwinHUDWidget>();
    auto State=[&]() {TSharedPtr<FJsonObject> Result;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(HUD->GetSearchState()),Result);return Result;};
    HUD->HandleStreamSearch(TEXT("{\"type\":\"unrelated\",\"action\":\"open\"}"));
    TestFalse(TEXT("Unrelated data channel messages cannot open the search"),State()->GetBoolField(TEXT("open")));
    HUD->HandleStreamSearch(TEXT("{\"type\":\"ghs.sceneSearch\",\"action\":\"query\",\"query\":\"叉车\",\"requestId\":12345,\"clientId\":\"viewer-a\"}"));
    TestEqual(TEXT("Committed Chinese query survives the bridge"),State()->GetStringField(TEXT("query")),FString(TEXT("叉车")));
    TestEqual(TEXT("Response keeps request identity"),State()->GetNumberField(TEXT("requestId")),12345.);
    TestEqual(TEXT("Broadcast response keeps viewer identity"),State()->GetStringField(TEXT("clientId")),FString(TEXT("viewer-a")));
    TestTrue(TEXT("Query opens results"),State()->GetBoolField(TEXT("open")));
    TestFalse(TEXT("Remote search does not consume another viewer's up key"),HUD->HandleSearchKey(EKeys::Up));
    TestFalse(TEXT("Remote search does not consume another viewer's escape key"),HUD->HandleSearchKey(EKeys::Escape));
    TestTrue(TEXT("Foreign native keys leave the remote dropdown open"),State()->GetBoolField(TEXT("open")));
    HUD->HandleStreamSearch(TEXT("{\"type\":\"ghs.sceneSearch\",\"action\":\"select\",\"id\":\"AGV-999\"}"));
    TestTrue(TEXT("Invented result cannot be selected"),HUD->SelectedId.IsEmpty());
    HUD->HandleStreamSearch(TEXT("{\"type\":\"ghs.sceneSearch\",\"action\":\"close\"}"));
    TestFalse(TEXT("Close preserves query while collapsing results"),State()->GetBoolField(TEXT("open")));
    TestEqual(TEXT("Query remains editable after close"),State()->GetStringField(TEXT("query")),FString(TEXT("叉车")));
    HUD->HandleStreamSearch(TEXT("{\"type\":\"ghs.sceneSearch\",\"action\":\"query\",\"query\":\"agv\",\"clientId\":\"viewer-b\"}"));
    HUD->HandleStreamSearch(TEXT("{\"type\":\"ghs.sceneSearch\",\"action\":\"close\",\"query\":\"叉车\",\"clientId\":\"viewer-a\"}"));
    TestEqual(TEXT("Closing a shared search replies with that caller's query"),State()->GetStringField(TEXT("query")),FString(TEXT("叉车")));
    TestEqual(TEXT("Closing reply retains the caller's identity"),State()->GetStringField(TEXT("clientId")),FString(TEXT("viewer-a")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSearchUtf16Padding,"GHS.TwinUI.Search.AcceptsUtf16TransportPaddingWithoutChangingQuery",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinSearchUtf16Padding::RunTest(const FString&)
{
    auto* HUD=NewObject<UGHSTwinHUDWidget>();
    auto State=[&]() {TSharedPtr<FJsonObject> Result;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(HUD->GetSearchState()),Result);return Result;};
    const TCHAR Padding[]={0,0,0,0,0,0,0,0};
    int32 RequestId=0;
    for(const TCHAR* Query:{TEXT(" 叉车 "),TEXT("agv")})
    {
        for(const bool bPadded:{false,true})
        {
            const FString Payload=FString::Printf(TEXT("{\"type\":\"ghs.sceneSearch\",\"action\":\"query\",\"query\":\"%s\",\"requestId\":%d,\"clientId\":\"utf16-viewer\"}"),Query,++RequestId);
            FString Packet=Payload;
            if(bPadded) Packet.AppendChars(Padding,UE_ARRAY_COUNT(Padding));
            TestEqual(TEXT("Fixture retains raw UTF-16 transport padding"),Packet.Len(),Payload.Len()+(bPadded?int32(UE_ARRAY_COUNT(Padding)):0));
            HUD->HandleStreamSearch(Packet);
            TestEqual(TEXT("Chinese and ASCII queries preserve their exact text and spaces"),State()->GetStringField(TEXT("query")),FString(Query));
            TestEqual(TEXT("Each padded or unpadded request is parsed independently"),State()->GetNumberField(TEXT("requestId")),double(RequestId));
            TestEqual(TEXT("Transport padding does not alter response routing"),State()->GetStringField(TEXT("clientId")),FString(TEXT("utf16-viewer")));
        }
    }
    FString Oversized=TEXT("{\"type\":\"ghs.sceneSearch\",\"action\":\"query\",\"query\":\"oversized\"}");
    while(Oversized.Len()<=4096) Oversized.AppendChars(Padding,UE_ARRAY_COUNT(Padding));
    HUD->HandleStreamSearch(Oversized);
    TestEqual(TEXT("Raw transport size limit still applies before stripping padding"),State()->GetNumberField(TEXT("requestId")),double(RequestId));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinBadgeInk,"GHS.TwinUI.Search.ChineseBadgeInkCentersWithActualFont",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinBadgeInk::RunTest(const FString&)
{
    const FSlateFontInfo Font(FPaths::ProjectContentDir()/TEXT("GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf"),12);
    for(const TCHAR* State:{TEXT("运行"),TEXT("待机"),TEXT("预警"),TEXT("故障"),TEXT("充电中"),TEXT("待接入")})
    {
        const auto M=GHSTwinTypography::Measure(State,Font);
        TestTrue(TEXT("Font produces non-empty glyph ink"),M.InkBottom>M.InkTop && M.Size.X>0);
        const double Top=M.CenteredOriginY(24)+M.InkTop,Bottom=M.CenteredOriginY(24)+M.InkBottom;
        TestTrue(TEXT("Visible glyph ink fits inside 24px badge"),Top>=0 && Bottom<=24);
        TestTrue(TEXT("Visible top and bottom margins match"),FMath::IsNearlyEqual(Top,24-Bottom,.01));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSearchGeometry,"GHS.TwinUI.Search.DropdownStaysWithinSceneAndKeyboardWraps",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinSearchGeometry::RunTest(const FString&)
{
    for(const double Bottom:{300.,600.,1080.})
    {
        const auto L=FGHSTwinSearchLayout::Calculate(FVector2D(100,80),FVector2D(360,48),Bottom,8);
        TestTrue(TEXT("Dropdown stays within scene height"),L.Position.Y+L.Size.Y<=Bottom-8+.01);
        for(int32 I=0;I<L.VisibleRows;++I) TestEqual(TEXT("Hit testing selects the displayed row"),L.RowAt(L.Position+FVector2D(20,L.HeaderHeight+I*L.RowHeight+L.RowHeight*.5)),I);
        TestEqual(TEXT("Footer cannot select a result"),L.RowAt(L.Position+L.Size-FVector2D(8,8)),INDEX_NONE);
    }
    TestEqual(TEXT("Up wraps from first to last"),FGHSTwinSearchLayout::MoveIndex(0,-1,3),2);
    TestEqual(TEXT("Down wraps from last to first"),FGHSTwinSearchLayout::MoveIndex(2,1,3),0);
    TestEqual(TEXT("Empty results cannot be selected"),FGHSTwinSearchLayout::MoveIndex(0,1,0),INDEX_NONE);
    TestEqual(TEXT("Large wheel step wraps a two-result list safely"),FGHSTwinSearchLayout::MoveIndex(0,-3,2),1);
    TestEqual(TEXT("Eighth result scrolls into seven-row window"),FGHSTwinSearchLayout::WindowStart(7,0,7,50),1);
    TestEqual(TEXT("Last result remains visible"),FGHSTwinSearchLayout::WindowStart(49,0,7,50),43);
    TestEqual(TEXT("Moving back up scrolls the result into view"),FGHSTwinSearchLayout::WindowStart(2,43,7,50),2);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSearchPages,"GHS.TwinUI.Search.EveryResultCanBePagedAndSelected",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinSearchPages::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(GEngine) GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    auto* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    for(int32 I=1;I<=125;++I)
    {
        auto* Actor=World->SpawnActor<AStaticMeshActor>();Actor->GetStaticMeshComponent()->SetStaticMesh(Cube);
        Actor->Tags={FName(FString::Printf(TEXT("TwinId=GHS_AGV_%d"),I))};
    }
    FGHSTwinSceneData Scene;Scene.Refresh(World);
    int32 Total=0;TSet<FString> Ids;FString LastId;
    for(int32 Offset=0;Offset<125;Offset+=50)
    {
        const auto Page=Scene.Search(TEXT("agv"),50,&Total,Offset);
        TestEqual(TEXT("Every page reports the complete total"),Total,125);
        TestEqual(TEXT("Page payload is bounded, final page is not discarded"),Page.Num(),FMath::Min(50,125-Offset));
        for(const auto& Row:Page) {Ids.Add(Row.Id);LastId=Row.Id;}
    }
    TestEqual(TEXT("All 125 real actors are reachable without duplicate pages"),Ids.Num(),125);
    TestTrue(TEXT("A last-page result can be validated independently of first page"),Scene.MatchesSearch(TEXT("agv"),LastId));
    const auto Builds=Scene.GetCacheStats().SearchIndexBuilds;
    Scene.Search(TEXT("AGV-07"),50,&Total);
    TestEqual(TEXT("Changing a query reuses scene index"),Scene.GetCacheStats().SearchIndexBuilds,Builds);

    auto* HUD=NewObject<UGHSTwinHUDWidget>(World);
    auto Slate=SNew(SObjectWidget,HUD)[SNullWidget::NullWidget];
    Slate->Tick(FGeometry::MakeRoot(FVector2D(1280,720),FSlateLayoutTransform()),0,.016f);
    HUD->SearchChanged(FText::FromString(TEXT("agv")));
    Slate->Tick(FGeometry::MakeRoot(FVector2D(1280,720),FSlateLayoutTransform()),0,.016f);
    for(int32 I=0;I<124;++I) HUD->HandleSearchKey(EKeys::Down);
    TSharedPtr<FJsonObject> State;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(HUD->GetSearchState()),State);
    TestEqual(TEXT("Native keyboard crosses page boundaries"),State->GetIntegerField(TEXT("selectedIndex")),124);
    TestEqual(TEXT("Native state contains last page"),State->GetIntegerField(TEXT("offset")),100);
    HUD->SearchCommitted(FText::FromString(TEXT("agv")),ETextCommit::OnEnter);
    TestEqual(TEXT("Enter selects actual last-page model"),HUD->SelectedId,LastId);
    Slate->ResetWidget();Scene.Refresh(nullptr);
    if(GEngine) GEngine->DestroyWorldContext(World);World->DestroyWorld(false);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSearchFreshSlots,"GHS.TwinUI.Search.FreshRackSlotsResolveBeforeAnyPick",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinSearchFreshSlots::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(GEngine) GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    auto* Host=World->SpawnActor<AActor>();auto* Racks=NewObject<UInstancedStaticMeshComponent>(Host);
    Host->SetRootComponent(Racks);Host->AddInstanceComponent(Racks);
    auto* Mesh=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/GHSRefinementV2/Meshes/SM_GHS_V2Rack_A.SM_GHS_V2Rack_A"));
    Racks->SetStaticMesh(Mesh);Racks->SetMobility(EComponentMobility::Movable);Racks->RegisterComponent();
    for(int32 I=0;I<6;++I) Racks->AddInstance(FTransform(FVector(I*600,0,0)));
    FGHSTwinSceneData Scene;Scene.Refresh(World);
    int32 Total=0;const auto First=Scene.Search(TEXT("货位"),50,&Total);
    TestTrue(TEXT("Fresh scene exposes actual cargo slots without prior clicks"),Total>64 && First.Num()==50);
    TestFalse(TEXT("Rack steel itself is never a selectable search result"),First.ContainsByPredicate([](const FGHSTwinSearchResult& R){return R.Id.StartsWith(TEXT("RACK:"));}));
    const auto Level2=Scene.Search(TEXT("第2层"),50,&Total);
    TestTrue(TEXT("Compact Chinese layer query finds actual metadata slots"),Level2.Num()>0);
    const auto Before=Scene.GetCacheStats();FVector Location,Extent;
    if(!First.IsEmpty())
    {
        const FString FirstId=First[0].Id;
        TestTrue(TEXT("Fresh material ID resolves real slot bounds"),Scene.Resolve(FirstId,Location,Extent));
        const FVector Old=Location;
        const auto All=Scene.Search(TEXT("货位"),1000,&Total);
        for(const auto& Row:All) Scene.Resolve(Row.Id,Location,Extent);
        TestTrue(TEXT("Material remains resolvable after 64-entry selection cache evicts it"),Scene.Resolve(FirstId,Location,Extent));
        Racks->AddWorldOffset(FVector(700,900,0));
        TestTrue(TEXT("Resolved slot follows live parent transform"),Scene.Resolve(FirstId,Location,Extent) && Location.Equals(Old+FVector(700,900,0),.01));
    }
    TestEqual(TEXT("Slot search and resolve never rescan world"),Scene.GetCacheStats().WorldScans,Before.WorldScans);
    TestEqual(TEXT("Repeated slot search reuses cached index"),Scene.GetCacheStats().SearchIndexBuilds,Before.SearchIndexBuilds);
    Host->Destroy();Scene.Refresh(World);
    TestEqual(TEXT("Destroyed racks remove their indexed cargo slots"),Scene.Search(TEXT("货位"),50,&Total).Num(),0);
    Scene.Refresh(nullptr);if(GEngine) GEngine->DestroyWorldContext(World);World->DestroyWorld(false);
    return true;
}
#endif
