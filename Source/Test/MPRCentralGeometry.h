#pragma once

#include "CoreMinimal.h"

class UInstancedStaticMeshComponent;

/** Static, cube-instanced parts of the MPR shared distribution equipment. */
namespace MPRCentralGeometry
{
    // SM_MPR_SorterSimTray is 32 cm along travel and 25 cm across travel.
    // Shared-loop carriers reuse that asset at 1.6 XY scale.
    inline constexpr double CentralCarrierScaleXY = 1.6;
    inline constexpr double TransferGapCm = 2.0;

    /** Fixed belt setback from a moving tray centreline. Radius=0 is a straight;
     *  a curved return also reserves the outward sweep of the tray corners. */
    double TransferSetbackCm(double ScaleXY, double TurnRadiusCm = 0.0);

    struct Bank
    {
        FVector Center = FVector::ZeroVector;
        double HalfStraightCm = 0;
        double RadiusCm = 0;
        double FrameHeightCm = 285;
    };

    // Start/End and Drop describe the supporting belt surface in world cm.
    // The caller adds the parcel half-height to obtain its centre path.
    struct Belt
    {
        FVector Start = FVector::ZeroVector;
        FVector End = FVector::ZeroVector;
        double WidthCm = 42;
    };

    struct Feed
    {
        FVector OperatorFeet = FVector::ZeroVector;
        double YawDegrees = 0;
        FVector Drop = FVector::ZeroVector;
    };

    /**
     * Arc-length parameter on a capsule along world Y, at Center.Z.
     * 0 = (+Radius,-HalfStraight). Right straight travels +Y, then the +Y
     * semicircle, left straight travels -Y, then the -Y semicircle.
     * HeadingRad is the world XY tangent measured from +X.
     */
    FVector CentralPoint(const Bank& Layout, double Fraction, double& HeadingRad);

    /** Appends world-space instances. All four components must use a 100 cm cube.
     *  The caller owns clearing, material assignment, collision and registration.
     */
    void Build(const Bank& Layout, const TArray<Belt>& Branches, const TArray<Feed>& Stations,
        UInstancedStaticMeshComponent* Metal, UInstancedStaticMeshComponent* White,
        UInstancedStaticMeshComponent* Blue, UInstancedStaticMeshComponent* Rubber);
}
