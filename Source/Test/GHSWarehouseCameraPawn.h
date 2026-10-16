#pragma once

#include "CoreMinimal.h"
#include "UniversalCamera.h"
#include "GHSWarehouseCameraPawn.generated.h"

/** Ground-plane Pawn movement; UniversalCamera orbits around the moving Pawn. */
UCLASS(Blueprintable)
class TEST_API AGHSWarehouseCameraPawn : public AUniversalCamera
{
    GENERATED_BODY()
public:
    AGHSWarehouseCameraPawn();
    virtual void Tick(float DeltaSeconds) override;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Warehouse Camera")
    TObjectPtr<UCameraComponent> WarehouseCamera;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview")
    FVector OverviewCenter = FVector(-646.665, 833.981, 0.0);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview", meta=(ClampMin="900"))
    float OverviewDistance = 53500.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview")
    float OverviewPitch = -30.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Overview")
    float OverviewYaw = -90.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0.01", ClampMax="1"))
    float OrbitDegreesPerPixel = 0.18f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0.01", ClampMax="1"))
    float PitchDegreesPerPixel = 0.14f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0.01", ClampMax="0.5"))
    float WheelZoomExponent = 0.12f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="0"))
    float MinimumCameraHeight = 150.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Warehouse Camera|Interaction", meta=(ClampMin="100"))
    FVector2D MaximumPan = FVector2D(30000.0, 15000.0);

    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void ResetOverview(bool Immediate = false);
    /** Delta is measured in screen pixels, positive Y down. Do not multiply by time. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void OrbitPixels(FVector2D Delta);
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void PanPixels(FVector2D Delta, int32 ViewportWidth);
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void ZoomSteps(float Steps);

protected:
    virtual void BeginPlay() override;
    virtual FRotator Lag_GetTickDesiredRotation_Implementation(float DeltaTime) override;
private:
    void ConfigureGroundRestrictions();
};
