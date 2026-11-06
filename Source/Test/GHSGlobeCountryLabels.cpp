#include "GHSGlobeCountryLabels.h"

#include "GHSWarehouseRegistry.h"
#include "Components/DecalComponent.h"
#include "Components/SceneComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Math/RotationMatrix.h"

AGHSGlobeCountryLabels::AGHSGlobeCountryLabels()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("CountryLabelRoot")));
    RootComponent->SetMobility(EComponentMobility::Movable);
    RootComponent->SetAbsolute(false, false, true);
    Tags.Add(TEXT("GHS_GlobeCountryLabels"));
}

void AGHSGlobeCountryLabels::Initialize(AActor* GlobeRoot, float GlobeRadius)
{
    for (const auto& Label : Labels) if (Label) Label->DestroyComponent();
    Labels.Reset();
    if (!IsValid(GlobeRoot) || !GlobeRoot->GetRootComponent() || !FMath::IsFinite(GlobeRadius) || GlobeRadius <= 0.f)
        return;
    AttachToActor(GlobeRoot, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    SetActorRelativeLocation(FVector::ZeroVector);
    SetActorRelativeRotation(FRotator::ZeroRotator);
    SetActorScale3D(FVector::OneVector);

    auto* Material = LoadObject<UMaterialInterface>(nullptr,
        TEXT("/Game/GlobeNavigation/Materials/M_CountrySurfaceLabel.M_CountrySurfaceLabel"));
    if (!Material)
    {
        UE_LOG(LogTemp, Error, TEXT("GHS globe country surface-label material is missing"));
        return;
    }
    struct FCountry { const TCHAR* Name; double Latitude, Longitude; float Size; };
    // Atlas order is shared with Tools/GlobeNavigation/create_country_labels.py.
    // Small neighboring countries use smaller text to preserve geographic spacing.
    static const FCountry Countries[] = {
        {TEXT("加拿大"),57,-105,1.f}, {TEXT("美国"),39,-98,1.f},
        {TEXT("墨西哥"),23,-102,.85f}, {TEXT("哥伦比亚"),4,-74,.62f},
        {TEXT("委内瑞拉"),8,-65,.62f}, {TEXT("秘鲁"),-9,-75,.72f},
        {TEXT("巴西"),-10,-52,1.f}, {TEXT("智利"),-34,-71,.72f},
        {TEXT("阿根廷"),-37,-64,.72f}, {TEXT("中国"),35,103,1.f},
        {TEXT("澳大利亚"),-25,134,1.f}, {TEXT("印度"),22,79,.9f},
        {TEXT("俄罗斯"),61,100,1.f}, {TEXT("南非"),-29,25,.85f}
    };
    for (int32 Index = 0; Index < UE_ARRAY_COUNT(Countries); ++Index)
    {
        const auto& Country = Countries[Index];
        const double Lat = FMath::DegreesToRadians(Country.Latitude);
        const double Lon = FMath::DegreesToRadians(Country.Longitude);
        const FVector Radial = GHSGlobe::ToSphere(Country.Latitude, Country.Longitude, 1.);
        const FVector North(-FMath::Sin(Lat)*FMath::Cos(Lon), FMath::Sin(Lat)*FMath::Sin(Lon), FMath::Cos(Lat));
        auto* Label = NewObject<UDecalComponent>(this, NAME_None, RF_Transient);
        AddInstanceComponent(Label);
        Label->SetupAttachment(RootComponent);
        Label->ComponentTags.Add(TEXT("GHS_GlobeCountrySurfaceLabel"));
        Label->ComponentTags.Add(FName(*(FString(TEXT("Country:")) + Country.Name)));
        Label->SetRelativeLocation(Radial * (GlobeRadius * 1.015));
        // DeferredDecal.usf maps local Z to U and local Y to V. Thus Z=east,
        // Y=south makes the glyphs north-up without a camera-facing billboard.
        Label->SetRelativeRotation(FRotationMatrix::MakeFromXY(-Radial, -North).ToQuat());
        const float HalfHeight = GlobeRadius * .027f * Country.Size;
        Label->DecalSize = FVector(GlobeRadius * .04f, HalfHeight, HalfHeight * 4.f);
        Label->SetFadeScreenSize(0.f);
        auto* Instance = UMaterialInstanceDynamic::Create(Material, Label);
        Instance->SetVectorParameterValue(TEXT("AtlasRect"), FLinearColor(.25f, .25f, (Index % 4) * .25f, (Index / 4) * .25f));
        Label->SetDecalMaterial(Instance);
        Label->RegisterComponent();
        Labels.Add(Label);
    }
}
