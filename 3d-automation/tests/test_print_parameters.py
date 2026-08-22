from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from printer.print_parameters import (
    PrintParameters,
    SlicerProfileGenerator,
)


BASE_PROFILE = """\
# unchanged full profile
top_solid_layers = 5
top_solid_infill_speed = 80
top_infill_extrusion_width = 0.40
extrusion_multiplier = 1.05
temperature = 220
min_fan_speed = 60
max_fan_speed = 80
bridge_fan_speed = 100
skirts = 1
brim_width = 10
top_solid_min_thickness = 0.7
slowdown_below_layer_time = 12
enable_dynamic_fan_speeds = 0
unrelated_setting = unchanged
"""


class PrintParametersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.base_profile = self.root / "slicer_profile.ini"
        self.base_profile.write_text(
            BASE_PROFILE,
            encoding="utf-8",
        )

    def test_extracts_six_start_values_from_existing_profile(self) -> None:
        parameters = PrintParameters.from_profile(self.base_profile)

        self.assertEqual(
            parameters,
            PrintParameters(
                top_solid_layers=5,
                print_speed=80,
                extrusion_width=0.40,
                extrusion_multiplier=1.05,
                temperature=220,
                fan_speed=80,
            ),
        )

    def test_rejects_parameter_outside_boundary(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"top_solid_layers is fixed at 5, got 6",
        ):
            PrintParameters(
                top_solid_layers=6,
                print_speed=80,
                extrusion_width=0.40,
                extrusion_multiplier=1.05,
                temperature=220,
                fan_speed=50,
            )

    def test_explicit_value_can_replace_out_of_range_base_value(self) -> None:
        self.base_profile.write_text(
            BASE_PROFILE.replace(
                "top_solid_layers = 5",
                "top_solid_layers = 7",
            ).replace(
                "top_solid_infill_speed = 80",
                "top_solid_infill_speed = 40",
            ),
            encoding="utf-8",
        )

        parameters = PrintParameters.from_profile(
            self.base_profile,
            top_solid_layers=5,
            print_speed=80,
        )

        self.assertEqual(parameters.top_solid_layers, 5)
        self.assertEqual(parameters.print_speed, 80)
        self.assertEqual(parameters.extrusion_width, 0.40)
        self.assertEqual(parameters.extrusion_multiplier, 1.05)
        self.assertEqual(parameters.temperature, 220)
        self.assertEqual(parameters.fan_speed, 80)

    def test_generated_profile_changes_only_controlled_settings(self) -> None:
        parameters = PrintParameters(
            top_solid_layers=5,
            print_speed=90,
            extrusion_width=0.38,
            extrusion_multiplier=1.05,
            temperature=215,
            fan_speed=30,
        )

        output_path = SlicerProfileGenerator(
            self.root / "generated"
        ).generate(
            self.base_profile,
            parameters,
        )

        generated = output_path.read_text(encoding="utf-8")
        original = self.base_profile.read_text(encoding="utf-8")

        self.assertIn("top_solid_layers = 5\n", generated)
        self.assertIn("top_solid_infill_speed = 90\n", generated)
        self.assertIn("top_infill_extrusion_width = 0.38\n", generated)
        self.assertIn("extrusion_multiplier = 1.05\n", generated)
        self.assertIn("temperature = 215\n", generated)
        self.assertIn("min_fan_speed = 30\n", generated)
        self.assertIn("max_fan_speed = 30\n", generated)
        self.assertIn("bridge_fan_speed = 30\n", generated)
        self.assertIn("skirts = 0\n", generated)
        self.assertIn("brim_width = 0\n", generated)
        self.assertIn("top_solid_min_thickness = 0\n", generated)
        self.assertIn("slowdown_below_layer_time = 0\n", generated)
        self.assertIn("unrelated_setting = unchanged\n", generated)

        self.assertIn("skirts = 1\n", original)
        self.assertIn("unrelated_setting = unchanged\n", original)

    def test_generated_profile_can_use_reproducible_cycle_filename(self) -> None:
        parameters = PrintParameters.from_profile(self.base_profile)

        output_path = SlicerProfileGenerator(
            self.root / "generated"
        ).generate(
            self.base_profile,
            parameters,
            output_filename="cycle_007_profile.ini",
        )

        self.assertEqual(output_path.name, "cycle_007_profile.ini")
        self.assertTrue(output_path.is_file())


if __name__ == "__main__":
    unittest.main()