"""Regression for visible salt-and-pepper cargo at integer mask boundaries.

The renderer interpolates constant vertex values in float32; +/- rounding error
must never change a whole pallet's occupancy. GPU scene captures also required.
"""
import math
import random
import struct
import unittest


def f32(value):
    return struct.unpack('f',struct.pack('f',value))[0]


class PackedMaskPrecision(unittest.TestCase):
    def test_round_trip_survives_interpolation_roundoff_at_every_bit(self):
        words=[0,1,(1<<18)-1]+[(1<<bit) for bit in range(18)]
        randomizer=random.Random(20261125)
        words += [randomizer.randrange(1<<18) for _ in range(1000)]
        for word in words:
            for delta in (-.03125,-.001,0,.001,.03125):
                interpolated=f32(word+delta)
                restored=math.floor(interpolated+.5)
                for bit in range(18):
                    self.assertEqual(math.floor(restored/(1<<bit))%2,(word>>bit)&1)

    def test_original_decoder_reproduces_pixel_noise(self):
        # Adjacent pixels can straddle the integer without any inventory change.
        self.assertEqual(math.floor(f32(7))%2,1)
        self.assertEqual(math.floor(f32(7-.001))%2,0)


if __name__=='__main__':
    unittest.main()
