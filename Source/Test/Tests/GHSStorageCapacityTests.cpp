#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSStorageCapacityComponent.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "StaticMeshResources.h"
#include "TimerManager.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStorageCapacityPermutation,
    "GHS.StorageCapacity.CompleteStableSlotsAndExactEndpoints",
    EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSStorageCapacityPermutation::RunTest(const FString&)
{
    for(int32 Total:{25056,7530})
    {
        TSet<int32> Ranks;
        int32 DefaultVisible=0, OnePercentVisible=0;
        const float Default=Total==25056?.8f:1.f;
        for(int32 Slot=0;Slot<Total;++Slot)
        {
            Ranks.Add(GHSStorageCapacity::SlotRank(Slot,Total));
            if(GHSStorageCapacity::IsSlotVisible(Slot,Total,Default)) ++DefaultVisible;
            if(GHSStorageCapacity::IsSlotVisible(Slot,Total,.01f)) ++OnePercentVisible;
            if(GHSStorageCapacity::IsSlotVisible(Slot,Total,0.f)
                || !GHSStorageCapacity::IsSlotVisible(Slot,Total,1.f))
                AddError(TEXT("An endpoint exposed an empty slot or omitted a full slot"));
            if(GHSStorageCapacity::IsSlotVisible(Slot,Total,.15f)
                && !GHSStorageCapacity::IsSlotVisible(Slot,Total,.8f))
                AddError(TEXT("Capacity reversal changed the stable slot ordering"));
        }
        TestEqual(TEXT("Permutation visits every slot once"),Ranks.Num(),Total);
        TestEqual(TEXT("Default counts use full geometry"),DefaultVisible,Total==25056?20045:7530);
        TestEqual(TEXT("One percent rounds complete slots"),OnePercentVisible,Total==25056?251:75);
    }
    TestEqual(TEXT("First slot agrees with material"),GHSStorageCapacity::SlotRank(0,25056),17);
    TestEqual(TEXT("Second slot agrees with material"),GHSStorageCapacity::SlotRank(1,25056),114);
    TestFalse(TEXT("Invalid slot never visible"),GHSStorageCapacity::IsSlotVisible(-1,7530,1.f));
    TestEqual(TEXT("NaN preserves last usable value"),GHSStorageCapacity::ClampCapacity(std::numeric_limits<float>::quiet_NaN(),.8f),.8f);
    TestEqual(TEXT("Negative capacity clamps"),GHSStorageCapacity::ClampCapacity(-1.f,.8f),0.f);
    TestEqual(TEXT("Excess capacity clamps"),GHSStorageCapacity::ClampCapacity(2.f,.8f),1.f);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStorageCapacityLODs,
    "GHS.StorageCapacity.AllLODsKeepCompleteCargoAndSteel",
    EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSStorageCapacityLODs::RunTest(const FString&)
{
    TArray<TSharedPtr<FJsonValue>> LODReport;
    const TCHAR* Names[]={TEXT("A_Pass_W36176"),TEXT("A_Pass_W37138"),TEXT("A_W37138"),TEXT("A_W37619"),
        TEXT("B_Pass_W36176"),TEXT("B_W37138"),TEXT("B_W37619"),TEXT("D1"),TEXT("D1_W37138"),TEXT("D1_W37619")};
    const int32 Slots[]={6,6,12,12,18,36,36,6,6,6};
    for(int32 MeshIndex=0;MeshIndex<UE_ARRAY_COUNT(Names);++MeshIndex)
    {
        const FString Name=FString(TEXT("SM_GHS_V2Rack_"))+Names[MeshIndex]+TEXT("_Capacity");
        const FString Path=TEXT("/Game/GHSZcoolSmartFactory/StorageCapacity/Meshes/")+Name+TEXT(".")+Name;
        UStaticMesh* Mesh=LoadObject<UStaticMesh>(nullptr,*Path);
        if(!TestNotNull(*Name,Mesh)) continue;
        const FStaticMeshRenderData* RenderData=Mesh->GetRenderData();
        if(!TestNotNull(TEXT("CPU-readable complete mesh"),RenderData)) continue;
        TestEqual(TEXT("Four distance LODs retained"),RenderData->LODResources.Num(),4);
        int32 LODIndex=0;
        for(const FStaticMeshLODResources& LOD:RenderData->LODResources)
        {
            const FString Context=FString::Printf(TEXT("%s LOD%d"),*Name,LODIndex);
            PushContext(Context);
            const auto& Vertices=LOD.VertexBuffers.StaticMeshVertexBuffer;
            if(!TestTrue(TEXT("Slot UV channel survives LOD reduction"),Vertices.GetNumTexCoords()>=2))
            { PopContext(); ++LODIndex; continue; }
            TSet<int32> CargoSlots;
            TSet<int32> PalletSlots;
            TSet<int32> BoxSlots;
            int32 SteelTriangles=0;
            int32 DetailSteelTriangles=0;
            bool bWholeFaces=true;
            for(const FStaticMeshSection& Section:LOD.Sections)
            {
                for(uint32 Triangle=0;Triangle<Section.NumTriangles;++Triangle)
                {
                    int32 First=INDEX_NONE;
                    for(uint32 Corner=0;Corner<3;++Corner)
                    {
                        const uint32 Vertex=LOD.IndexBuffer.GetIndex(Section.FirstIndex+Triangle*3+Corner);
                        const float Encoded=Vertices.GetVertexUV(Vertex,1).X;
                        const int32 Slot=FMath::RoundToInt(Encoded);
                        if(!FMath::IsNearlyEqual(Encoded,float(Slot),.001f) || (Corner>0 && Slot!=First)) bWholeFaces=false;
                        if(Corner==0) First=Slot;
                    }
                    if(First<0)
                    {
                        ++SteelTriangles;
                        if(Section.MaterialIndex==6) ++DetailSteelTriangles;
                        if(First!=-1 || (Section.MaterialIndex>=3 && Section.MaterialIndex<=5)) bWholeFaces=false;
                    }
                    else
                    {
                        CargoSlots.Add(First);
                        if(First>=Slots[MeshIndex]) bWholeFaces=false;
                        if(Section.MaterialIndex==3) PalletSlots.Add(First);
                        if(Section.MaterialIndex==4) BoxSlots.Add(First);
                    }
                    if(Section.MaterialIndex<3 && First!=-1) bWholeFaces=false;
                }
            }
            auto Row=MakeShared<FJsonObject>();
            Row->SetStringField(TEXT("mesh"),Name);
            Row->SetNumberField(TEXT("lod"),LODIndex);
            Row->SetNumberField(TEXT("triangles"),LOD.GetNumTriangles());
            Row->SetNumberField(TEXT("expected_slots"),Slots[MeshIndex]);
            Row->SetNumberField(TEXT("pallet_slots"),PalletSlots.Num());
            Row->SetNumberField(TEXT("box_slots"),BoxSlots.Num());
            Row->SetBoolField(TEXT("whole_faces"),bWholeFaces);
            TArray<TSharedPtr<FJsonValue>> MissingPallets;
            FString MissingText;
            for(int32 Slot=0;Slot<Slots[MeshIndex];++Slot)
                if(!PalletSlots.Contains(Slot))
                {
                    MissingPallets.Add(MakeShared<FJsonValueNumber>(Slot));
                    MissingText+=FString::Printf(TEXT("%d,"),Slot);
                }
            Row->SetArrayField(TEXT("missing_pallet_slots"),MissingPallets);
#if WITH_EDITOR
            Row->SetNumberField(TEXT("percent_triangles"),Mesh->GetSourceModel(LODIndex).ReductionSettings.PercentTriangles);
#endif
            LODReport.Add(MakeShared<FJsonValueObject>(Row));
            AddInfo(FString::Printf(TEXT("%s: pallets=%d/%d boxes=%d/%d triangles=%d missing_pallets=[%s]"),
                *Context,PalletSlots.Num(),Slots[MeshIndex],BoxSlots.Num(),Slots[MeshIndex],LOD.GetNumTriangles(),*MissingText));
            TestTrue(TEXT("No LOD triangle crosses a visibility threshold"),bWholeFaces);
            TestEqual(TEXT("Each LOD retains every complete cargo slot"),CargoSlots.Num(),Slots[MeshIndex]);
            TestEqual(TEXT("Each LOD retains every complete pallet"),PalletSlots.Num(),Slots[MeshIndex]);
            TestEqual(TEXT("Each LOD retains boxes in every slot"),BoxSlots.Num(),Slots[MeshIndex]);
            TestTrue(TEXT("Frame remains at zero capacity"),SteelTriangles>0);
            if(LODIndex==0) TestTrue(TEXT("Structural adjustment slots sharing Detail material retain the steel sentinel"),DetailSteelTriangles>0);
            PopContext();
            ++LODIndex;
        }
    }
    auto Report=MakeShared<FJsonObject>();
    Report->SetStringField(TEXT("owner"),TEXT("ghs-complete-storage-capacity-v1"));
    Report->SetArrayField(TEXT("lods"),LODReport);
    FString ReportJson;
    FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&ReportJson));
    IFileManager::Get().MakeDirectory(*FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("SceneControls")),true);
    TestTrue(TEXT("Native LOD slot diagnostic saved"),FFileHelper::SaveStringToFile(ReportJson,
        *FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("SceneControls/capacity-lod-slots.json"))));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStorageCapacityRuntime,
    "GHS.StorageCapacity.RuntimePickingAndSliderDoNotMutateInstances",
    EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::NonNullRHI | EAutomationTestFlags::ProductFilter)
bool FGHSStorageCapacityRuntime::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("Fixture world"),World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    World->InitializeActorsForPlay(FURL());
    AActor* Owner=World->SpawnActor<AActor>();
    auto* Instances=NewObject<UHierarchicalInstancedStaticMeshComponent>(Owner);
    Owner->AddInstanceComponent(Instances);
    Instances->bAutoRebuildTreeOnInstanceChanges=false;
    Instances->ComponentTags.Add(TEXT("GHSStorageGroup:GHS_V2_Rack_A_Pass_W36176"));
    auto* Mesh=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/GHSZcoolSmartFactory/StorageCapacity/Meshes/SM_GHS_V2Rack_A_Pass_W36176_Capacity.SM_GHS_V2Rack_A_Pass_W36176_Capacity"));
    if(!TestNotNull(TEXT("Prepared full rack"),Mesh))
    { GEngine->DestroyWorldContext(World); World->DestroyWorld(false); return false; }
    Instances->SetStaticMesh(Mesh);
    Instances->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Always;
    Instances->RegisterComponent();
    const FTransform First(FRotator(0,37,0),FVector(400,-600,170),FVector(1.2,.8,1.1));
    for(int32 Index=0;Index<11;++Index)
    {
        FTransform Transform=First;
        Transform.AddToTranslation(FVector(Index*2000,0,0));
        Instances->AddInstance(Transform);
    }
    Instances->BuildTreeIfOutdated(false,true);
    auto* Capacity=NewObject<UGHSStorageCapacityComponent>(Owner);
    Owner->AddInstanceComponent(Capacity);
    Capacity->RegisterComponent();
    TestTrue(TEXT("Prepared component initialized"),Capacity->InitializeForWorld());
    Owner->DispatchBeginPlay();
    TestTrue(TEXT("Static cargo uses automatic shadow invalidation during play"),
        Instances->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Auto);
    auto* Cargo=Cast<UMaterialInstanceDynamic>(Instances->GetMaterial(4));
    TestNotNull(TEXT("Full cargo receives a MID"),Cargo);
    UMaterialInterface* Steel=Instances->GetMaterial(0);
    const auto CustomData=Instances->PerInstanceSMCustomData;
    const FVector CargoPoint=First.TransformPosition(FVector(-112.03,0,500));
    const FVector FramePoint=First.TransformPosition(FVector(-178,0,400));
    World->SendAllEndOfFrameUpdates();
    TestTrue(TEXT("Fixture has a render state for shadow refresh assertions"),Instances->IsRenderStateCreated());
    TestFalse(TEXT("Initialization render changes were consumed"),Instances->IsRenderStateDirty());
    Capacity->SetCapacity(.8f,1.f);
    TestFalse(TEXT("An unchanged slider does not invalidate cached shadows"),Instances->IsRenderStateDirty());
    Capacity->SetCapacity(0,0);
    TestTrue(TEXT("Changing the opacity mask refreshes the rack shadow render state"),Instances->IsRenderStateDirty());
    TestTrue(TEXT("Active slider changes keep opacity-mask shadows live"),
        Instances->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Always);
    World->SendAllEndOfFrameUpdates();
    Capacity->SetCapacity(0,.5f);
    TestFalse(TEXT("A floor-only slider change does not invalidate rack shadows"),Instances->IsRenderStateDirty());
    Capacity->SetCapacity(std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity());
    TestFalse(TEXT("Rejected nonfinite slider values do not invalidate shadows"),Instances->IsRenderStateDirty());
    TestFalse(TEXT("Zero cargo cannot be picked after inverse instance transform"),Capacity->IsStorageHitVisible(Instances,0,CargoPoint));
    TestTrue(TEXT("Zero cargo retains steel context"),Capacity->IsStorageHitVisible(Instances,0,FramePoint));
    TestTrue(TEXT("Rack steel material is untouched"),Steel==Instances->GetMaterial(0));
    Capacity->SetCapacity(1,1);
    TestTrue(TEXT("Complete cargo is pickable at full capacity"),Capacity->IsStorageHitVisible(Instances,0,CargoPoint));
    for(int32 Index=0;Index<101;++Index) Capacity->SetCapacity(Index/100.f,1.f-Index/100.f);
    for(int32 Index=100;Index>=0;--Index) Capacity->SetCapacity(Index/100.f,1.f-Index/100.f);
    Capacity->SetCapacity(.8f,1.f);
    TestFalse(TEXT("A continuous slider burst does not recreate the HISM proxy per update"),Instances->IsRenderStateDirty());
    TestTrue(TEXT("Stable instances retain all custom data"),CustomData==Instances->PerInstanceSMCustomData);
    TestEqual(TEXT("Slider never adds or removes instances"),Instances->GetInstanceCount(),11);
    FTransform After;
    Instances->GetInstanceTransform(0,After,true);
    TestTrue(TEXT("Slider preserves rotation/scale/position"),First.Equals(After,.0001));
    TestTrue(TEXT("Slider keeps the same shared MID"),Cargo==Instances->GetMaterial(4));
    TestFalse(TEXT("Capacity component has no tick"),Capacity->PrimaryComponentTick.bCanEverTick);
    TSharedPtr<FJsonObject> Report;
    FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Capacity->GetReportJson()),Report);
    if(TestTrue(TEXT("Report is valid JSON"),Report.IsValid()))
    {
        TestEqual(TEXT("All slider changes retain one initialization scan"),Report->GetIntegerField(TEXT("initialization_scans")),1);
        double Refreshes=0;
        TestTrue(TEXT("Shadow refresh requests are diagnosable"),Report->TryGetNumberField(TEXT("shadow_cache_refresh_requests"),Refreshes));
        TestEqual(TEXT("The entire slider burst requests one entry refresh"),Refreshes,1.);
    }
    Owner->SetActorHiddenInGame(true);
    Capacity->SetStorageVisible(false);
    TestFalse(TEXT("Hidden storage cannot be picked"),Capacity->IsStorageHitVisible(Instances,0,CargoPoint));
    Capacity->SetCapacity(.25f,.5f);
    Capacity->SetStorageVisible(true);
    TestEqual(TEXT("Layer restoration retains changed rack capacity"),Capacity->GetRackCapacity(),.25f);
    TestTrue(TEXT("Component layer does not overwrite actor hidden state"),Owner->IsHidden());
    ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([this,World,Instances,Capacity,Mesh,First,Start=FPlatformTime::Seconds(),Phase=0]() mutable
    {
        // This isolated fixture is not a live game viewport; advance its timer on engine frames.
        World->GetTimerManager().Tick(.05f);
        if(Phase==1)
        {
            TSharedPtr<FJsonObject> OverrideReport;
            FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Capacity->GetReportJson()),OverrideReport);
            double Refreshing=1;
            const bool bTimerFinished=OverrideReport.IsValid()
                && OverrideReport->TryGetNumberField(TEXT("shadow_cache_refreshing_components"),Refreshing) && Refreshing==0;
            if(!bTimerFinished && FPlatformTime::Seconds()-Start<2.) return false;
            TestTrue(TEXT("Settle timer finishes after a caller changes shadow policy"),bTimerFinished);
            TestTrue(TEXT("Settle timer preserves a caller's explicit shadow policy"),
                Instances->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Rigid);
            // Resume managed Auto, then exercise shutdown with another timer pending.
            Instances->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Auto;
            Capacity->SetCapacity(.4f,.5f);
            Capacity->DestroyComponent();
            TestTrue(TEXT("Component shutdown restores the authored shadow policy"),
                Instances->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Always);
            TestTrue(TEXT("Component shutdown restores the authored cargo material"),Instances->GetMaterial(4)==Mesh->GetMaterial(4));
            GEngine->DestroyWorldContext(World);
            World->DestroyWorld(false);
            return true;
        }
        const bool bSettled=Instances->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Auto;
        if(!bSettled && FPlatformTime::Seconds()-Start<2.) return false;
        TestTrue(TEXT("Quiet slider returns to cached shadows"),bSettled);
        TSharedPtr<FJsonObject> SettledReport;
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Capacity->GetReportJson()),SettledReport);
        double Refreshes=0;
        if(TestTrue(TEXT("Settled report has refresh diagnostics"),SettledReport.IsValid()
            && SettledReport->TryGetNumberField(TEXT("shadow_cache_refresh_requests"),Refreshes)))
            TestEqual(TEXT("One continuous burst has only entry and final refresh requests"),Refreshes,2.);
        TestEqual(TEXT("Settling preserves the final exact slider value"),Capacity->GetRackCapacity(),.25f);
        World->SendAllEndOfFrameUpdates();
        FTransform Hidden=First;Hidden.SetScale3D(FVector::ZeroVector);
        TestTrue(TEXT("Replay-style pickup accepts a hidden source transform"),Instances->UpdateInstanceTransform(0,Hidden,false,true,true));
        TestTrue(TEXT("Replay-style pickup refreshes automatic shadow state"),Instances->IsRenderStateDirty());
        World->SendAllEndOfFrameUpdates();
        TestTrue(TEXT("Replay-style placement restores the original source transform"),Instances->UpdateInstanceTransform(0,First,false,true,true));
        TestTrue(TEXT("Replay-style placement refreshes automatic shadow state"),Instances->IsRenderStateDirty());
        FTransform Restored;Instances->GetInstanceTransform(0,Restored,false);
        TestTrue(TEXT("Shadow caching preserves the restored pallet transform"),First.Equals(Restored,.0001));
        Capacity->SetCapacity(.3f,.5f);
        Instances->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Rigid;
        Instances->MarkRenderStateDirty();
        Phase=1;
        return false;
    }));
    return true;
}
#endif
