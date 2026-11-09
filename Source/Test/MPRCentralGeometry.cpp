#include "MPRCentralGeometry.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Math/RotationMatrix.h"

namespace MPRCentralGeometry
{
    namespace
    {
        void Box(UInstancedStaticMeshComponent* Component, const FVector& Position,
            const FVector& Dimensions, const FQuat& Rotation = FQuat::Identity)
        {
            if (!Component || Position.ContainsNaN() || Dimensions.ContainsNaN()
                || Dimensions.GetMin() <= 0)
                return;
            Component->AddInstance(FTransform(Rotation, Position, Dimensions / 100.0), true);
        }

        void Beam(UInstancedStaticMeshComponent* Component, const FVector& Start,
            const FVector& End, double Width, double Height)
        {
            const FVector Delta = End - Start;
            const double Length = Delta.Size();
            if (Length < 0.01)
                return;
            Box(Component, (Start + End) * 0.5, FVector(Length, Width, Height),
                FRotationMatrix::MakeFromX(Delta / Length).ToQuat());
        }

        void Leg(UInstancedStaticMeshComponent* Metal, const FVector& Top, double FloorZ,
            double Size = 4.0)
        {
            const double Height = Top.Z - FloorZ;
            if (Height < 3)
                return;
            Box(Metal, FVector(Top.X, Top.Y, FloorZ + Height * 0.5), FVector(Size, Size, Height));
            Box(Metal, FVector(Top.X, Top.Y, FloorZ + 1), FVector(Size + 7, Size + 7, 2));
        }

        double DistanceToBeltXY(const FVector& Point, const Belt& Segment)
        {
            const FVector2D P(Point.X, Point.Y);
            const FVector2D A(Segment.Start.X, Segment.Start.Y);
            const FVector2D D(Segment.End.X - Segment.Start.X, Segment.End.Y - Segment.Start.Y);
            const double T = FMath::Clamp(FVector2D::DotProduct(P - A, D)
                / FMath::Max(D.SizeSquared(), 0.001), 0.0, 1.0);
            return (P - A - D * T).Size();
        }

        bool ClearSupport(const FVector& Point, const TArray<Belt>& Branches,
            const TArray<Feed>& Stations)
        {
            for (const Belt& Branch : Branches)
                if (DistanceToBeltXY(Point, Branch) < Branch.WidthCm * 0.5 + 17)
                    return false;
            for (const Feed& Station : Stations)
                if (FVector::DistSquared2D(Point, Station.OperatorFeet) < FMath::Square(85.0)
                    || FVector::DistSquared2D(Point, Station.Drop) < FMath::Square(60.0))
                    return false;
            return true;
        }

        void RailLoop(const Bank& Layout, double Radius, double Z,
            UInstancedStaticMeshComponent* Metal)
        {
            const FVector C = Layout.Center;
            const double H = Layout.HalfStraightCm;
            // Long rails are single continuous members. Short tangent pieces are
            // needed only at the two curved ends, keeping the instance count low.
            for (double Side : {-1.0, 1.0})
                Beam(Metal, C + FVector(Side * Radius, -H, Z),
                    C + FVector(Side * Radius, H, Z), 3.2, 3.2);
            constexpr int32 ArcSegments = 20;
            for (double End : {-1.0, 1.0})
            {
                const double StartAngle = End > 0 ? 0.0 : UE_PI;
                for (int32 I = 0; I < ArcSegments; ++I)
                {
                    const double A = StartAngle + UE_PI * I / ArcSegments;
                    const double B = StartAngle + UE_PI * (I + 1) / ArcSegments;
                    Beam(Metal,
                        C + FVector(Radius * FMath::Cos(A), End * H + Radius * FMath::Sin(A), Z),
                        C + FVector(Radius * FMath::Cos(B), End * H + Radius * FMath::Sin(B), Z),
                        3.2, 3.2);
                }
            }
        }

        void Conveyor(const Belt& Branch, double FloorZ, UInstancedStaticMeshComponent* Metal,
            UInstancedStaticMeshComponent* White, UInstancedStaticMeshComponent* Blue,
            UInstancedStaticMeshComponent* Rubber)
        {
            const FVector Delta = Branch.End - Branch.Start;
            const double Length = Delta.Size();
            if (Length < 3 || Branch.WidthCm < 8)
                return;
            const FQuat Rotation = FRotationMatrix::MakeFromX(Delta / Length).ToQuat();
            const FVector Right = Rotation.GetRightVector();
            const FVector Up = Rotation.GetUpVector();
            const FVector Mid = (Branch.Start + Branch.End) * 0.5;
            const double W = Branch.WidthCm;

            // Start/End define the actual top surface, with the deck beneath.
            Box(White, Mid - Up * 3.0, FVector(Length, W, 4), Rotation);
            Box(Rubber, Mid - Up * 0.5, FVector(Length, W - 4, 1), Rotation);
            for (double Side : {-1.0, 1.0})
            {
                Box(Blue, Mid + Right * Side * (W * 0.5 - 1)
                    - Up * 0.5, FVector(Length, 2, 6), Rotation);
                Box(Metal, Mid + Right * Side * (W * 0.5 - 6)
                    - Up * 8, FVector(Length, 3, 4), Rotation);
            }
            // Visible drive-end plate rather than a bright strip across the belt.
            Box(Blue, Branch.End - Up * 5, FVector(4, W, 5), Rotation);
            const int32 SupportPairs = Length > 100 ? 2 : 1;
            for (int32 I = 0; I < SupportPairs; ++I)
            {
                const double T = SupportPairs == 1 ? 0.5 : (I == 0 ? 0.18 : 0.82);
                const FVector Top = FMath::Lerp(Branch.Start, Branch.End, T)
                    - Up * 6;
                for (double Side : {-1.0, 1.0})
                    Leg(Metal, Top + Right * Side * (W * 0.5 - 6), FloorZ);
                Beam(Metal, Top - Right * (W * 0.5 - 6) - FVector(0, 0, 38),
                    Top + Right * (W * 0.5 - 6) - FVector(0, 0, 38), 3, 3);
            }
        }

        void Workstation(const Feed& Station, UInstancedStaticMeshComponent* Metal,
            UInstancedStaticMeshComponent* White, UInstancedStaticMeshComponent* Blue,
            UInstancedStaticMeshComponent* Rubber)
        {
            const double Yaw = FMath::DegreesToRadians(Station.YawDegrees);
            const FQuat Rotation(FVector::UpVector, Yaw);
            const FVector Forward(FMath::Cos(Yaw), FMath::Sin(Yaw), 0);
            const FVector Right(-Forward.Y, Forward.X, 0);
            // Leave 20 cm between the operator's foot centre and the near edge.
            const FVector Mid = Station.Drop + Forward * 10;
            Box(White, Mid - FVector(0, 0, 4), FVector(80, 65, 7), Rotation);
            Box(Rubber, Mid - FVector(0, 0, 0.5), FVector(78, 59, 1), Rotation);
            for (double Side : {-1.0, 1.0})
            {
                Box(Blue, Mid + Right * Side * 31.5 - FVector(0, 0, 2), FVector(80, 2, 5), Rotation);
                for (double End : {-1.0, 1.0})
                    Leg(Metal, Mid + Forward * End * 33 + Right * Side * 27
                        - FVector(0, 0, 7), Station.OperatorFeet.Z);
            }
            // Display is beside the induction surface, outside the parcel path.
            const FVector Mast = Mid + Forward * 15 + Right * 39;
            Leg(Metal, Mast + FVector(0, 0, 38), Station.OperatorFeet.Z, 3);
            Box(White, Mast + FVector(0, 0, 34), FVector(4, 30, 22), Rotation);
            Box(Rubber, Mast - Forward * 2.2 + FVector(0, 0, 34), FVector(0.5, 26, 18), Rotation);
            Box(Blue, Mast - Forward * 2.5 + FVector(0, 0, 26), FVector(0.6, 24, 1), Rotation);
            // Scanner head is a small side-mounted housing; it does not bridge
            // the operator's hand trajectory or block the transfer belt.
            Box(White, Mid + Forward * 16 - Right * 34 + FVector(0, 0, 11), FVector(12, 8, 16), Rotation);
            Box(Rubber, Mid + Forward * 9.7 - Right * 34 + FVector(0, 0, 12), FVector(0.5, 5, 6), Rotation);
        }
    }

    FVector CentralPoint(const Bank& Layout, double Fraction, double& HeadingRad)
    {
        const double H = FMath::Max(0.0, Layout.HalfStraightCm);
        const double R = FMath::Max(0.01, Layout.RadiusCm);
        const double Straight = 2.0 * H;
        const double Arc = UE_PI * R;
        const double Length = 2.0 * Straight + 2.0 * Arc;
        const double Wrapped = FMath::IsFinite(Fraction) ? Fraction - FMath::FloorToDouble(Fraction) : 0;
        double Distance = Wrapped * Length;
        FVector Point;
        if (Distance < Straight)
        {
            Point = FVector(R, -H + Distance, 0);
            HeadingRad = UE_PI * 0.5;
        }
        else if ((Distance -= Straight) < Arc)
        {
            const double Angle = Distance / R;
            Point = FVector(R * FMath::Cos(Angle), H + R * FMath::Sin(Angle), 0);
            HeadingRad = Angle + UE_PI * 0.5;
        }
        else if ((Distance -= Arc) < Straight)
        {
            Point = FVector(-R, H - Distance, 0);
            HeadingRad = -UE_PI * 0.5;
        }
        else
        {
            const double Angle = UE_PI + (Distance - Straight) / R;
            Point = FVector(R * FMath::Cos(Angle), -H + R * FMath::Sin(Angle), 0);
            HeadingRad = Angle + UE_PI * 0.5;
        }
        HeadingRad = FMath::Atan2(FMath::Sin(HeadingRad), FMath::Cos(HeadingRad));
        return Layout.Center + Point;
    }

    void Build(const Bank& Layout, const TArray<Belt>& Branches, const TArray<Feed>& Stations,
        UInstancedStaticMeshComponent* Metal, UInstancedStaticMeshComponent* White,
        UInstancedStaticMeshComponent* Blue, UInstancedStaticMeshComponent* Rubber)
    {
        if (Layout.Center.ContainsNaN() || !FMath::IsFinite(Layout.HalfStraightCm)
            || !FMath::IsFinite(Layout.RadiusCm) || !FMath::IsFinite(Layout.FrameHeightCm)
            || Layout.HalfStraightCm <= 0 || Layout.RadiusCm <= 8 || Layout.FrameHeightCm < 120)
            return;

        const double Height = Layout.FrameHeightCm;
        for (double RadiusOffset : {-5.0, 5.0})
        {
            // Reused moving-column mesh: runners sit 17.6 cm inboard and
            // the top guide 25.6 cm inboard after the 1.6 XY scale.
            RailLoop(Layout, Layout.RadiusCm - 25.6 + RadiusOffset, Height, Metal);
            RailLoop(Layout, Layout.RadiusCm - 17.6 + RadiusOffset, 5, Metal);
        }

        const double SupportX = Layout.RadiusCm + 24;
        const int32 Bays = FMath::Max(1, FMath::CeilToInt(2 * Layout.HalfStraightCm / 260));
        for (int32 I = 0; I <= Bays; ++I)
        {
            const double Y = FMath::Lerp(-Layout.HalfStraightCm, Layout.HalfStraightCm,
                static_cast<double>(I) / Bays);
            int32 Supports = 0;
            for (double Side : {-1.0, 1.0})
            {
                const FVector Foot = Layout.Center + FVector(Side * SupportX, Y, 0);
                if (!ClearSupport(Foot, Branches, Stations))
                    continue;
                Leg(White, Foot + FVector(0, 0, Height + 9), Layout.Center.Z, 7);
                Box(Blue, Foot + FVector(0, 0, 12), FVector(8, 8, 24));
                ++Supports;
            }
            if (Supports > 0)
                Beam(White, Layout.Center + FVector(-SupportX, Y, Height + 8),
                    Layout.Center + FVector(SupportX, Y, Height + 8), 7, 7);
        }

        // End guards stay outside the moving capsule and leave the side
        // workstations/connecting conveyors accessible.
        for (double End : {-1.0, 1.0})
        {
            const double Y = End * (Layout.HalfStraightCm + Layout.RadiusCm + 21);
            const FVector C = Layout.Center + FVector(0, Y, 0);
            Box(White, C + FVector(0, 0, 45), FVector(2 * Layout.RadiusCm + 26, 2.5, 80));
            Beam(Metal, C + FVector(-SupportX, 0, 88), C + FVector(SupportX, 0, 88), 4, 4);
            for (double Side : {-1.0, 1.0})
                Leg(White, C + FVector(Side * SupportX, 0, Height + 9), Layout.Center.Z, 7);
            Beam(White, C + FVector(-SupportX, 0, Height + 8),
                C + FVector(SupportX, 0, Height + 8), 7, 7);
        }
        const FVector Cabinet = Layout.Center
            + FVector(0, -Layout.HalfStraightCm - Layout.RadiusCm - 46, 39);
        Box(White, Cabinet, FVector(42, 32, 76));
        Box(Blue, Cabinet + FVector(0, -16.5, 0), FVector(36, 1, 64));
        Box(Rubber, Cabinet + FVector(12, -17.5, 5), FVector(2, 2, 12));

        for (const Belt& Branch : Branches)
            Conveyor(Branch, Layout.Center.Z, Metal, White, Blue, Rubber);
        for (const Feed& Station : Stations)
            Workstation(Station, Metal, White, Blue, Rubber);
    }
}
