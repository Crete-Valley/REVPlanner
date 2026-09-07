"""Example entry point for KPI, optimisation and barriers calculations.

This file uses the same three input payloads as the original integration test:
1. KPI input
2. Computation-modules input
3. Barriers input
"""
import json
from pathlib import Path

from api.services.scripts.module_integration import (
    barriers_calculation,
    computation_modules,
    kpi_calculation,
    outputs_to_front,
)

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"


def load_json(filename):
    """Load one JSON example file from the examples directory."""
    with (EXAMPLES / filename).open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def inputs_from_user():
    """Load the three inputs used by the original ``_main_test.py``."""
    kpi_front_data = load_json("inputs_kpis_moires.json")
    cm_front_data = load_json("input_computation_modules_moires.json")
    barriers_front_data = load_json("barriers_input_example_moires.json")
    return kpi_front_data, cm_front_data, barriers_front_data


def main():
    kpi_front_data, cm_front_data, barriers_front_data = inputs_from_user()

    # KPI calculation is kept exactly as part of the original integration flow.
    kpi_results = kpi_calculation(kpi_front_data)
    results_cm, climate_vulnerabilities = computation_modules(cm_front_data)
    outputs_barriers = barriers_calculation(barriers_front_data)

    outputs = outputs_to_front(
        results_cm,
        climate_vulnerabilities,
        outputs_barriers,
    )

    # Keep KPI results available in the output of this standalone example.
    # This does not change module_integration.outputs_to_front().
    outputs["kpis"] = {
        "by_category": kpi_results[0],
        "by_primary_use": kpi_results[1],
    }

    output_path = ROOT / "outputs_test.json"
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(outputs, output_file, indent=4, ensure_ascii=False)

    print(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
