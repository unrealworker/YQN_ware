#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSWarehouseRegistry.h"
#include "../GHSWarehouseExperience.h"
#include "../GHSGlobeTransition.h"
#include "../GHSGlobeNavigation.h"
#include "../GHSWarehouseCameraPawn.h"
#include "Camera/CameraComponent.h"
#include "Engine/Engine.h"
#include "Engine/Level.h"
#include "Engine/World.h"
#include "GameFramework/PlayerInput.h"
#include "Misc/ScopeExit.h"
#include "GHSAutomationTestFlags.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeGeographyTest,"GHS.Globe.Geography",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobeGeographyTest::RunTest(const FString&)
{
    TestTrue(TEXT("Greenwich equator faces +X"),GHSGlobe::ToSphere(0,0,100).Equals(FVector(100,0,0),.001));
    TestTrue(TEXT("East longitude follows imported globe toward -Y"),GHSGlobe::ToSphere(0,90,100).Equals(FVector(0,-100,0),.001));
    TestTrue(TEXT("North pole faces +Z"),GHSGlobe::ToSphere(90,0,100).Equals(FVector(0,0,100),.001));
    const FVector California=GHSGlobe::ToSphere(34.190629582941,-117.428430792609,100);
    TestTrue(TEXT("California north western hemisphere after FBX handedness conversion"),California.Z>0 && California.X<0 && California.Y>0);
    TestTrue(TEXT("Unit geographic radius preserved"),FMath::IsNearlyEqual(California.Length(),100.,.001));
    TestFalse(TEXT("Backside point cannot be selected"),GHSGlobe::IsSurfaceVisible(FVector(-100,0,0),FVector(300,0,0),FVector::ZeroVector));
    TestTrue(TEXT("Frontside point visible"),GHSGlobe::IsSurfaceVisible(FVector(100,0,0),FVector(300,0,0),FVector::ZeroVector));
    TestFalse(TEXT("Latitude must be geographically valid"),GHSGlobe::ValidCoordinates(91,0));
    TestFalse(TEXT("NaN cannot reach transforms"),GHSGlobe::ValidCoordinates(std::numeric_limits<double>::quiet_NaN(),0));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeCatalogTest,"GHS.Globe.Catalog",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobeCatalogTest::RunTest(const FString&)
{
    TArray<FGHSGlobeWarehouse> Entries;FString Error;
    const FString Entry=TEXT("{\"id\":\"ghs-ca\",\"name\":\"GHS\",\"city\":\"San Bernardino\",\"address\":\"17335 Glen Helen Pkwy\",\"latitude\":34.190629582941,\"longitude\":-117.428430792609,\"map\":\"/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory\",\"runtimeProfile\":\"ghs\",\"features\":[\"warehouse-ui\",\"traffic\"]}");
    TestTrue(TEXT("Valid catalog loads"),GHSGlobe::ParseCatalog(TEXT("{\"schemaVersion\":2,\"warehouses\":[")+Entry+TEXT("]}"),Entries,Error));
    TestEqual(TEXT("One real configured warehouse"),Entries.Num(),1);
    TestFalse(TEXT("Duplicate ids rejected atomically"),GHSGlobe::ParseCatalog(TEXT("{\"schemaVersion\":2,\"warehouses\":[")+Entry+TEXT(",")+Entry+TEXT("]}"),Entries,Error));
    TestTrue(TEXT("Invalid catalog cannot retain stale entries"),Entries.IsEmpty());
    for(const TCHAR* Id:{TEXT("cluster-0-0"),TEXT("cluster:64:1:1")})
    {
        const FString Reserved=Entry.Replace(TEXT("ghs-ca"),Id);
        TestFalse(TEXT("Warehouse identity cannot collide with aggregate marker identifiers"),GHSGlobe::ParseCatalog(TEXT("{\"schemaVersion\":2,\"warehouses\":[")+Reserved+TEXT("]}"),Entries,Error));
        TestTrue(TEXT("Reserved identity rejects the whole catalog"),Entries.IsEmpty());
    }
    TestTrue(TEXT("Reserved marker prefixes are case-sensitive"),GHSGlobe::ParseCatalog(TEXT("{\"schemaVersion\":2,\"warehouses\":[")+Entry.Replace(TEXT("ghs-ca"),TEXT("Cluster-west"))+TEXT("]}"),Entries,Error));
    TestFalse(TEXT("External map URLs rejected"),GHSGlobe::IsAllowedMap(TEXT("https://example.com/Map")));
    TestFalse(TEXT("Path traversal rejected"),GHSGlobe::IsAllowedMap(TEXT("/Game/Maps/../Unsafe")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeRegistryIsolationTest,"GHS.Globe.RegistryIsolation",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobeRegistryIsolationTest::RunTest(const FString&)
{
    FGHSWarehouseRegistry Registry;FString Error;
    const FString Generic=TEXT(R"({"schemaVersion":2,"warehouses":[{"id":"future-warehouse","name":"Future","latitude":35,"longitude":140,"map":"/Game/Maps/Future","runtimeProfile":"generic","features":[],"entryCamera":{"x":0,"y":0,"z":500,"distance":10000,"pitch":-35,"yaw":40}}]})");
    TestTrue(TEXT("New generic warehouse is entirely data driven"),Registry.Load(Generic,Error));
    const auto* W=Registry.Find(TEXT("future-warehouse"));
    if(!TestNotNull(TEXT("Indexed registry lookup"),W))return false;
    const auto Adapter=IGHSWarehouseExperience::Create(*W);
    TestTrue(TEXT("Generic profile owns no GHS HUD lifecycle"),Adapter&&!Adapter->UsesWarehouseHUD());
    TestTrue(TEXT("Entry pose comes from warehouse config"),W->EntryPivot.Equals(FVector(0,0,500))&&W->EntryDistance==10000);
    const auto Revision=Registry.GetRevision();const FString Cached=Registry.GetCatalogJson();
    TestFalse(TEXT("Unknown runtime profile fails closed"),Registry.Load(Generic.Replace(TEXT("generic"),TEXT("typo")),Error));
    TestEqual(TEXT("Failed reload preserves last valid revision"),Registry.GetRevision(),Revision);
    TestEqual(TEXT("Failed reload preserves cached catalog"),Registry.GetCatalogJson(),Cached);
    TestNotNull(TEXT("Failed reload preserves active identity"),Registry.Find(TEXT("future-warehouse")));
    TestFalse(TEXT("Generic cannot opt into unsupported GHS features"),Registry.Load(Generic.Replace(TEXT("\"features\":[]"),TEXT("\"features\":[\"traffic\"]")),Error));
    TestFalse(TEXT("Future schema cannot silently change meaning"),Registry.Load(Generic.Replace(TEXT("\"schemaVersion\":2"),TEXT("\"schemaVersion\":3")),Error));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeStreamExclusionTest,"GHS.Globe.StreamExclusion",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobeStreamExclusionTest::RunTest(const FString&)
{
    TestFalse(TEXT("Loaded hidden destination still owns the only slot"),FGHSWarehouseStreamPolicy::CanStart(true,false));
    TestFalse(TEXT("Unloading destination blocks new allocation"),FGHSWarehouseStreamPolicy::CanStart(true,true));
    TestFalse(TEXT("Pending removal blocks new allocation even if pointer gone"),FGHSWarehouseStreamPolicy::CanStart(false,true));
    TestTrue(TEXT("Only fully empty slot can preload"),FGHSWarehouseStreamPolicy::CanStart(false,false));
    TestFalse(TEXT("Hidden level is not disposed while still registered"),FGHSWarehouseStreamPolicy::FinishedUnloading(false,true));
    TestFalse(TEXT("Loaded level is not disposed after deregistration"),FGHSWarehouseStreamPolicy::FinishedUnloading(true,false));
    TestTrue(TEXT("Removed and unloaded level releases ownership"),FGHSWarehouseStreamPolicy::FinishedUnloading(false,false));
    TestFalse(TEXT("Early invisible flag does not imply component removal completed"),FGHSWarehouseStreamPolicy::CanRevealGlobe(false,true,true));
    TestFalse(TEXT("An invisible level still in the active world cannot reveal globe"),FGHSWarehouseStreamPolicy::CanRevealGlobe(false,false,true));
    TestFalse(TEXT("A visible old warehouse cannot reveal globe after timeout"),FGHSWarehouseStreamPolicy::CanRevealGlobe(true,false,false));
    TestTrue(TEXT("A detached invisible level can release the curtain while retaining the unload slot"),FGHSWarehouseStreamPolicy::CanRevealGlobe(false,false,false));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeClusteringTest,"GHS.Globe.Clustering",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobeClusteringTest::RunTest(const FString&)
{
    TArray<FGHSWarehouseProjectedPoint> Points;
    for(int32 Index=0;Index<2000;++Index)Points.Add({FString::Printf(TEXT("warehouse-%d"),Index),FVector2D((Index%50)*30.,(Index/50)*20.)});
    const auto Clusters=GHSClusterWarehousePoints(Points,TEXT("warehouse-1750"));
    TestTrue(TEXT("Two thousand warehouses stay within the native label budget"),Clusters.Num()<=256);
    TSet<FString> Membership;int32 Count=0;
    for(const auto& Cluster:Clusters)for(const auto& Id:Cluster.Ids){++Count;Membership.Add(Id);}
    TestEqual(TEXT("Every warehouse remains represented exactly once"),Count,2000);
    TestEqual(TEXT("No warehouse lost through budget reduction"),Membership.Num(),2000);
    TestEqual(TEXT("Selected warehouse keeps an independent label"),Clusters[0].Id,FString(TEXT("warehouse-1750")));
    TestEqual(TEXT("Selected warehouse is not grouped"),Clusters[0].Ids.Num(),1);
    const auto Repeat=GHSClusterWarehousePoints(Points,TEXT("warehouse-1750"));
    TestEqual(TEXT("Stable grid produces repeatable identifiers"),Repeat.Last().Id,Clusters.Last().Id);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeCurtainTest,"GHS.Globe.CurtainHandshake",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobeCurtainTest::RunTest(const FString&)
{
    FGHSGlobeCurtainGate Gate;const FVector2D FullSize(1672,941);
    Gate.Begin(FullSize,0);const uint32 First=Gate.GetGeneration();
    TestFalse(TEXT("Numeric opacity alone cannot permit a world change"),Gate.Ready(100,true));
    TestFalse(TEXT("Compact return browser cannot acknowledge full coverage"),Gate.Accept(First,FVector2D(156,44),1,10));
    TestFalse(TEXT("A fading curtain cannot acknowledge full coverage"),Gate.Accept(First,FullSize,.99f,10));
    TestFalse(TEXT("Malformed browser dimensions are rejected"),Gate.Accept(First,FVector2D(std::numeric_limits<double>::quiet_NaN(),941),1,10));
    TestTrue(TEXT("Current full-size opaque curtain is accepted"),Gate.Accept(First,FullSize,1,10));
    TestFalse(TEXT("CEF acknowledgement cannot switch the world in the same frame"),Gate.Ready(10,true));
    TestTrue(TEXT("A duplicate acknowledgement is idempotent"),Gate.Accept(First,FullSize,1,11));
    TestFalse(TEXT("Full-size acknowledgement cannot approve an actually compact surface"),Gate.Ready(12,false));
    TestTrue(TEXT("Early acknowledgement remains valid when full native coverage settles"),Gate.Ready(12,true));
    Gate.Begin(FVector2D(1920,1080),20);
    TestFalse(TEXT("Previous transition cannot acknowledge a new transition"),Gate.Accept(First,FullSize,1,30));
    TestFalse(TEXT("Resize invalidates prior coverage"),Gate.Ready(40,true));
    TestFalse(TEXT("Handshake has a bounded grace period"),Gate.Expired(29.9));
    TestTrue(TEXT("Missing browser acknowledgement times out"),Gate.Expired(30.1));
    Gate.Cancel();TestFalse(TEXT("Canceled transitions cannot switch the world"),Gate.Ready(100,true));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeBrowserGeometryTest,"GHS.Globe.BrowserGeometry",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobeBrowserGeometryTest::RunTest(const FString&)
{
    using Geometry=FGHSGlobeBrowserGeometry;
    TestTrue(TEXT("Offscreen unit scale preserves CSS dimensions"),Geometry::ToCssSize(FVector2D(1672,941),1,1).Equals(FVector2D(1672,941)));
    TestTrue(TEXT("Slate two-thirds scale and 150 percent Windows DPI use distinct units"),Geometry::ToCssSize(FVector2D(1920,1080),2.f/3.f,1.5f).Equals(FVector2D(853,480)));
    TestTrue(TEXT("Four-thirds design scale at 150 percent Windows DPI maps to CEF view rect"),Geometry::ToCssSize(FVector2D(1920,1200),4.f/3.f,1.5f).Equals(FVector2D(1707,1067)));
    TestTrue(TEXT("Accumulated scale includes parent transforms, not only design scale"),Geometry::ToCssSize(FVector2D(1280,800),2.,1.5).Equals(FVector2D(1707,1067)));
    TestTrue(TEXT("Invalid DPI cannot authorize a curtain"),Geometry::ToCssSize(FVector2D(1920,1080),1,0).IsNearlyZero());
    for(const float Scale:{2.f/3.f,4.f/3.f})
    {
        const float EngineDpiScale=Scale/1.5f;
        for(int32 Eighths=1000;Eighths<40000;++Eighths)
        {
            const FVector2f Layout(float(Eighths)/8.f,941.f);
            const FVector2D EngineSize(Layout*EngineDpiScale);
            if(!TestTrue(TEXT("Fractional Slate size follows the engine float operation order exactly"),
                Geometry::ToCssSize(FVector2D(Layout),Scale,1.5f).Equals(FVector2D(EngineSize.IntPoint()))))return false;
        }
    }
    const FVector2D Full(1920,1200),Css=Geometry::ToCssSize(Full,4.f/3.f,1.5f);
    TestTrue(TEXT("Full browser allocation covers the HUD"),Geometry::CoversFullLayout(Full,FVector2D::ZeroVector,Full,false));
    TestFalse(TEXT("Compact allocation does not cover the HUD"),Geometry::CoversFullLayout(Full,FVector2D(24,1092),FVector2D(180,1136),false));
    TestFalse(TEXT("Compact state rejects stale full-size cached geometry"),Geometry::CoversFullLayout(Full,FVector2D::ZeroVector,Full,true));
    TestFalse(TEXT("Full-size surface with an offset does not cover the viewport"),Geometry::CoversFullLayout(Full,FVector2D(24,0),Full+FVector2D(24,0),false));
    FGHSGlobeCurtainGate Gate;Gate.Begin(Css,0);
    TestFalse(TEXT("Slate logical dimensions cannot substitute for CSS dimensions"),Gate.Accept(Gate.GetGeneration(),Full,1,10));
    TestFalse(TEXT("DPI-mapped compact dimensions cannot acknowledge full coverage"),Gate.Accept(Gate.GetGeneration(),Geometry::ToCssSize(FVector2D(156,44),4.f/3.f,1.5f),1,10));
    TestTrue(TEXT("Exact CEF CSS dimensions can acknowledge"),Gate.Accept(Gate.GetGeneration(),Css,1,10));
    TestFalse(TEXT("Acknowledgement waits for native allocated coverage"),Gate.Ready(12,false));
    TestTrue(TEXT("Settled full CSS surface permits transition"),Gate.Ready(12,true));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobePersistentCameraTest,"GHS.Globe.PersistentCameraOwnership",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSGlobePersistentCameraTest::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("Transient camera ownership world"),World)||!GEngine)return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT{GEngine->DestroyWorldContext(World);World->DestroyWorld(false);};
    World->InitializeActorsForPlay(FURL());
    auto* Controller=World->SpawnActor<AGHSGlobePlayerController>();
    auto* Camera=World->SpawnActor<AGHSWarehouseCameraPawn>();
    if(!TestNotNull(TEXT("Globe controller"),Controller)||!TestNotNull(TEXT("Persistent camera"),Camera))return false;
    Controller->PlayerInput=NewObject<UPlayerInput>(Controller);Controller->Possess(Camera);
    Controller->Command(TEXT("{\"action\":\"home\"}"));
    TestTrue(TEXT("Initial camera belongs to the persistent level"),Camera->GetLevel()==World->PersistentLevel);
    TestTrue(TEXT("Initial globe camera is possessed"),Controller->GetPawn()==Camera);
    auto* DestinationLevel=NewObject<ULevel>(World,NAME_None,RF_Transient);
    DestinationLevel->OwningWorld=World;World->AddLevel(DestinationLevel);
    for(int32 Cycle=0;Cycle<2;++Cycle)
    {
        FActorSpawnParameters Spawn;Spawn.OverrideLevel=DestinationLevel;Spawn.ObjectFlags|=RF_Transient;
        auto* PlacedCamera=World->SpawnActor<AGHSWarehouseCameraPawn>(FVector::ZeroVector,FRotator::ZeroRotator,Spawn);
        if(!TestNotNull(TEXT("Destination's placed camera"),PlacedCamera))return false;
        TestTrue(TEXT("Destination camera belongs to a different level"),PlacedCamera->GetLevel()==DestinationLevel);
        // APawn::PreInitializeComponents issues this exact call for AutoPossessPlayer=Player0.
        Controller->Possess(PlacedCamera);
        TestTrue(TEXT("Streamed Player0 auto-possession cannot replace the persistent camera"),Controller->GetPawn()==Camera);
        TestNull(TEXT("Streamed camera is not controlled by the globe player"),PlacedCamera->GetController());
        PlacedCamera->Destroy();
        TestTrue(TEXT("Removing destination camera preserves player possession"),Controller->GetPawn()==Camera);
        TestTrue(TEXT("Globe lens survives destination removal"),FMath::IsNearlyEqual(Camera->WarehouseCamera->FieldOfView,20.f,.01f));
    }
    Controller->UnPossess();
    return true;
}
#endif
