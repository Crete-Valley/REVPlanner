"""Example entry point for representative demand calculation."""
import json
from pathlib import Path

from api.services.scripts.module_integration import demand_calculation

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"


def inputs_from_user():
    """Load the original demand input example."""
    input_path = EXAMPLES / "inputs_user.json"
    with input_path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def main():
    front_data_buildings = inputs_from_user()
    demand_representative_days = demand_calculation(front_data_buildings)

    output_path = ROOT / "demand_output.json"
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(demand_representative_days, output_file, indent=4, ensure_ascii=False)

    print(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
