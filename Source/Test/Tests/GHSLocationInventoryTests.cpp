#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSLocationInventory.h"
#include "../GHSTwinSceneData.h"
#include "Dom/JsonObject.h"
#include "GHSAutomationTestFlags.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace GHSInventoryTests
{
const FString Index=TEXT(R"({"schemaVersion":1,"snapshotId":"snapshot-a","warehouseId":"108","warehouseCode":"GHS_CA_US","source":{"fileName":"inventory.csv","sha256":"snapshot-a","exportedAt":"2026-11-25","atomic":false},"locations":[{"id":"001","code":"R02-15-01","state":"empty","quantity":0,"availableQuantity":0,"recordCount":0,"skuCount":0,"shard":"001.json"},{"id":"002","code":"R02-15-02","state":"occupied","quantity":12,"availableQuantity":0,"recordCount":1,"skuCount":1,"shard":"002.json"}]})");
const FString Bindings=TEXT(R"({"schemaVersion":1,"warehouseId":"108","warehouseCode":"GHS_CA_US","bindings":[{"cadId":"CAD_A","level":1,"column":1,"locationId":"001","locationCode":"R02-15-01","confidence":"rule_inferred","evidence":"CAD exact code"},{"cadId":"CAD_A","level":1,"column":2,"locationId":"002","locationCode":"R02-15-02","confidence":"rule_inferred","evidence":"CAD exact code"}]})");
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSInventoryBindings,"GHS.Inventory.RuleBindingsRejectAmbiguityAndInvalidSources",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSInventoryBindings::RunTest(const FString&)
{
    FGHSLocationInventory Store;
    TestTrue(TEXT("Consistent index loads"),Store.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings,TEXT("")));
    FGHSLocationInventory NumericWarehouse;
    TestTrue(TEXT("Mapping numeric warehouse ID accepts the same warehouse"),NumericWarehouse.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings.Replace(TEXT("\"warehouseId\":\"108\""),TEXT("\"warehouseId\":108")),TEXT("")));
    TestEqual(TEXT("Numeric warehouse retains both bindings"),NumericWarehouse.NumBindings(),2);
    const auto* Empty=Store.Find(TEXT("CAD_A"),1,1);
    TestNotNull(TEXT("Exact CAD slot is bound"),Empty);
    if(Empty) {TestEqual(TEXT("Leading zero ID retained"),Empty->Id,FString(TEXT("001")));TestTrue(TEXT("Zero quantity is empty"),Empty->State==EGHSInventoryState::Empty);}
    const auto* Occupied=Store.Find(TEXT("CAD_A"),1,2);
    TestTrue(TEXT("Allocated stock with zero available remains occupied"),Occupied && Occupied->State==EGHSInventoryState::Occupied);
    TestNull(TEXT("Missing CAD never guesses by location"),Store.Find(TEXT(""),1,1));
    TestNull(TEXT("Unknown slot never guesses nearest"),Store.Find(TEXT("CAD_A"),1,3));
    FGHSLocationInventory StaleSource;
    TestFalse(TEXT("Different source hash cannot bind current inventory"),StaleSource.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings.Replace(TEXT("\"schemaVersion\":1"),TEXT("\"schemaVersion\":1,\"sourceInventorySha256\":\"snapshot-old\"")),TEXT("")));
    FGHSLocationInventory WrongWarehouse;
    TestFalse(TEXT("Other warehouse fails closed"),WrongWarehouse.Initialize(GHSInventoryTests::Index.Replace(TEXT("GHS_CA_US"),TEXT("MPR")),GHSInventoryTests::Bindings,TEXT("")));
    FGHSLocationInventory WrongCode;
    TestTrue(TEXT("Bad binding isolated"),WrongCode.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings.Replace(TEXT("R02-15-01"),TEXT("INCORRECT")),TEXT("")));
    TestNull(TEXT("Code mismatch not silently accepted"),WrongCode.Find(TEXT("CAD_A"),1,1));
    FGHSLocationInventory Duplicate;
    TestTrue(TEXT("Duplicate import still supports unaffected rows"),Duplicate.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings.Replace(TEXT("\"column\":2"),TEXT("\"column\":1")),TEXT("")));
    TestNull(TEXT("Both conflicting slot bindings rejected"),Duplicate.Find(TEXT("CAD_A"),1,1));
    FGHSLocationInventory Inconsistent;
    TestTrue(TEXT("Invalid empty declaration parsed as unknown"),Inconsistent.Initialize(GHSInventoryTests::Index.Replace(TEXT("\"quantity\":0"),TEXT("\"quantity\":5")),GHSInventoryTests::Bindings,TEXT("")));
    TestTrue(TEXT("Positive stock cannot be hidden as empty"),Inconsistent.Find(TEXT("CAD_A"),1,1) && Inconsistent.Find(TEXT("CAD_A"),1,1)->State==EGHSInventoryState::Unknown);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSInventoryDetailValidation,"GHS.Inventory.ShardValidationKeepsSnapshotAndLocationIdentity",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSInventoryDetailValidation::RunTest(const FString&)
{
    FGHSLocationInventory Store;Store.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings,TEXT(""));
    const FString Detail=TEXT(R"({"schemaVersion":1,"snapshotId":"snapshot-a","locations":{"001":{"id":"001","code":"R02-15-01","state":"empty","emptyReason":"no_inventory_records","warehouseId":"108","warehouseCode":"GHS_CA_US","fields":{},"totals":{"quantity":0,"availableQuantity":0,"allocationQuantity":0,"freezeQuantity":0,"waitMoveInQuantity":0,"waitMoveOutQuantity":0},"skuCount":0,"recordCount":0,"items":[]}}})");
    TestTrue(TEXT("Matching shard accepted"),Store.AcceptShard(TEXT("001.json"),Detail));
    auto Selection=Store.Selection(TEXT("CAD_A"),1,1);
    TestEqual(TEXT("Click details mapped"),Selection->GetStringField(TEXT("mappingStatus")),FString(TEXT("mapped")));
    TestEqual(TEXT("Rule inference never masquerades as field confirmation"),Selection->GetStringField(TEXT("mappingConfidence")),FString(TEXT("rule_inferred")));
    TestTrue(TEXT("Source is static, not atomic"),Selection->HasField(TEXT("source")));
    FGHSLocationInventory Old;Old.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings,TEXT(""));
    TestFalse(TEXT("Other snapshot cannot populate current slot"),Old.AcceptShard(TEXT("001.json"),Detail.Replace(TEXT("snapshot-a"),TEXT("snapshot-old"))));
    TestEqual(TEXT("Failed details never look empty"),Old.Selection(TEXT("CAD_A"),1,1)->GetStringField(TEXT("mappingStatus")),FString(TEXT("unknown")));
    TestFalse(TEXT("Unsafe shard path rejected"),Store.AcceptShard(TEXT("../001.json"),Detail));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSInventoryMaskAndPicking,"GHS.Inventory.BitMasksStayExactAndEmptySlotUsesLowHitSurface",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSInventoryMaskAndPicking::RunTest(const FString&)
{
    FGHSInventoryMask Mask;
    for(int32 Slot=0;Slot<36;++Slot) TestTrue(TEXT("Slot fits two exact words"),Mask.Set(Slot,Slot%2?EGHSInventoryState::Empty:EGHSInventoryState::Occupied));
    TestFalse(TEXT("Slot 36 cannot overflow the shader contract"),Mask.Set(36,EGHSInventoryState::Occupied));
    TestFalse(TEXT("Negative slot rejected"),Mask.Set(-1,EGHSInventoryState::Empty));
    for(int32 Word=0;Word<4;++Word) {TestTrue(TEXT("Mask remains below float exact integer limit"),Mask.Values[Word]<16777216.f);TestEqual(TEXT("Integer roundtrip exact"),float(uint32(Mask.Values[Word])),Mask.Values[Word]);}
    TestEqual(TEXT("Both 18-bit known words full"),Mask.Values[2],262143.f);TestEqual(TEXT("Second known word full"),Mask.Values[3],262143.f);
    Mask.Set(18,EGHSInventoryState::Unknown);TestFalse(TEXT("Unknown clears prior known bit"),Mask.IsKnown(18));
    const FBox Cargo(FVector(-50,-60,450),FVector(50,60,650));
    const FBox Empty=GHSLocationInventory::EmptyPickBounds(Cargo);
    TestEqual(TEXT("Empty hit surface starts at slot floor"),Empty.Min.Z,450.);
    TestTrue(TEXT("Empty volume cannot occlude full cargo height"),Empty.Max.Z<=454.);
    double Distance=0;
    TestFalse(TEXT("Horizontal ray passes through empty slot"),GHSTwinSelection::IntersectBox(FVector(-100,0,550),FVector(1,0,0),FTransform::Identity,Empty,Distance));
    TestTrue(TEXT("Top down click still selects empty slot"),GHSTwinSelection::IntersectBox(FVector(0,0,800),FVector(0,0,-1),FTransform::Identity,Empty,Distance));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSInventoryTransformContract,"GHS.Inventory.CompleteTransformContractRejectsFlippedScaledOrOldMeshes",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSInventoryTransformContract::RunTest(const FString&)
{
    const FString Contract=GHSInventoryTests::Bindings.Replace(TEXT("\"evidence\":\"CAD exact code\""),TEXT("\"evidence\":\"CAD exact code\",\"expectedPositionM\":[1,2,3],\"expectedWorldRotationDeg\":[0,-90,0],\"expectedWorldScale\":[1,1,1],\"expectedMesh\":\"Full_Capacity\""));
    FGHSLocationInventory Store;TestTrue(TEXT("Contract loads"),Store.Initialize(GHSInventoryTests::Index,Contract,TEXT("")));
    const FTransform Expected(FRotator(0,-90,0),FVector(100,-200,300));
    TestNotNull(TEXT("CAD Y reflection and full mesh match"),Store.FindForTransform(TEXT("CAD_A"),1,1,TEXT("Full_Capacity"),Expected));
    FTransform Changed=Expected;Changed.SetRotation(FRotator(0,90,0).Quaternion());
    TestNull(TEXT("Same center but reversed columns is rejected"),Store.FindForTransform(TEXT("CAD_A"),1,1,TEXT("Full_Capacity"),Changed));
    Changed=Expected;Changed.SetScale3D(FVector(2,1,1));
    TestNull(TEXT("Scaled geometry requires remapping"),Store.FindForTransform(TEXT("CAD_A"),1,1,TEXT("Full_Capacity"),Changed));
    Changed=Expected;Changed.AddToTranslation(FVector(2,0,0));
    TestNull(TEXT("Moved geometry requires remapping"),Store.FindForTransform(TEXT("CAD_A"),1,1,TEXT("Full_Capacity"),Changed));
    TestNull(TEXT("Old sparse mesh cannot claim complete inventory slots"),Store.FindForTransform(TEXT("CAD_A"),1,1,TEXT("Full_Occ70"),Expected));
    FGHSLocationInventory Missing;Missing.Initialize(GHSInventoryTests::Index,GHSInventoryTests::Bindings,TEXT(""));
    TestNull(TEXT("Missing transform never affects scene geometry"),Missing.FindForTransform(TEXT("CAD_A"),1,1,TEXT("Full_Capacity"),Expected));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSInventoryActualSnapshot,"GHS.Inventory.ActualSnapshotAndContentSourceHashesStayAligned",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSInventoryActualSnapshot::RunTest(const FString&)
{
    const FString Data=FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data");FString Index,Mapping;
    if(!TestTrue(TEXT("Actual snapshot readable"),FFileHelper::LoadFileToString(Index,*(Data/TEXT("inventory/index.json"))))
        || !TestTrue(TEXT("Actual binding readable"),FFileHelper::LoadFileToString(Mapping,*(Data/TEXT("inventory-bindings.json"))))) return false;
    FGHSLocationInventory Store;
    TestTrue(TEXT("Three actual Content sources match recorded SHA256"),Store.Initialize(Index,Mapping,Data/TEXT("inventory")));
    TestTrue(TEXT("Current mapping has substantial valid rack coverage"),Store.NumBindings()>20000);
    TestTrue(TEXT("Current snapshot includes complete warehouse archive"),Store.NumLocations()>90000);
    TSharedPtr<FJsonObject> Root;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Mapping),Root);
    Root->GetObjectField(TEXT("sourceHashes"))->SetStringField(TEXT("Content/GHSTwinUI/data/rack-slots.json"),TEXT("stale-source"));
    FString Stale;FJsonSerializer::Serialize(Root.ToSharedRef(),TJsonWriterFactory<>::Create(&Stale));
    FGHSLocationInventory Bad;
    TestFalse(TEXT("Changed slot definition cannot reuse old mapping"),Bad.Initialize(Index,Stale,Data/TEXT("inventory")));
    TestEqual(TEXT("Stale mapping has no live bindings"),Bad.NumBindings(),0);
    return true;
}
#endif
