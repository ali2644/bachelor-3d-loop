from __future__ import annotations

import unittest

from optimizer.objective import (
    ObjectiveExpressionError,
    evaluate_objective_expression,
    validate_objective_expression,
)


class ObjectiveExpressionTest(unittest.TestCase):
    def test_evaluates_measurements_and_print_time(self) -> None:
        value = evaluate_objective_expression(
            "5 + print_time_minutes * Ra_um + Rz_um",
            ra_um=4.0,
            rz_um=20.0,
            print_time_seconds=120.0,
        )

        self.assertEqual(value, 33.0)

    def test_print_time_aliases_are_seconds(self) -> None:
        value = evaluate_objective_expression(
            "print_time + print_time_seconds",
            ra_um=4.0,
            rz_um=20.0,
            print_time_seconds=120.0,
        )

        self.assertEqual(value, 240.0)

    def test_rejects_code_execution_and_unknown_names(self) -> None:
        expressions = (
            "__import__('os').system('echo unsafe')",
            "Ra_um if Ra_um > 1 else 0",
            "unknown_metric + Ra_um",
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                with self.assertRaises(ObjectiveExpressionError):
                    validate_objective_expression(expression)

    def test_requires_only_variables_referenced_by_expression(self) -> None:
        value = evaluate_objective_expression(
            "Ra_um",
            ra_um=4.5,
            rz_um=None,
            print_time_seconds=None,
        )

        self.assertEqual(value, 4.5)

        with self.assertRaisesRegex(
            ObjectiveExpressionError,
            "print_time",
        ):
            evaluate_objective_expression(
                "Ra_um + print_time",
                ra_um=4.5,
                rz_um=None,
                print_time_seconds=None,
            )


if __name__ == "__main__":
    unittest.main()
