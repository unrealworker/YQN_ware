#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "MPRSorterHUDWidget.generated.h"

class AMPRSorterSimulationActor;

/** Small native panel belonging only to the MPR demonstration actor. */
UCLASS()
class TEST_API UMPRSorterHUDWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    void InitializeSorter(AMPRSorterSimulationActor* Actor);
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
private:
    UPROPERTY(Transient) TWeakObjectPtr<AMPRSorterSimulationActor> Owner;
    bool bCollapsed=true;
};
