"""Main integration layer for the public project version.

Only functions currently used by the supplied entry scripts are active here.
Future/incomplete integration functions are kept commented at the end of the file.
"""
from api.services.scripts.rat_rev_tool.main import (
    BarriersInput,
    BarriersRequest,
    KPIInput,
    KPIRequest,
    calculate_barriers_scores,
    calculate_kpi_scores,
    calculate_kpi_scores_primary_use,
)
from api.services.scripts.rat_rev_tool.climate_vulnerability_calculation import (
    get_climate_vulnerabilities,
)


def demand_calculation(load_front_data):
    """Build representative demand days from the frontend building input.

    This workflow calls external services (PVGIS/Open-Meteo/Thermagrid).
    Thermagrid credentials must be configured through environment variables.
    """
    # Demand-specific imports are lazy so KPI/optimisation workflows do not
    # require geospatial/weather libraries at import time.
    from api.services.scripts.profiles_calculation.RESbased_scenario_generator import (
        demand_thermagrid,
        fetch_geojson,
        generate_demand_inputs,
        generate_geojson,
    )
    from api.services.scripts.profiles_calculation.build_demand_representative_days import (
        build_demand_representative_input,
    )
    front_data = load_front_data["cel"]["Buildings"]
    geojson_object = generate_geojson(front_data=front_data)

    # Generate the weather/irradiance payload once and reuse it for Thermagrid.
    inputs_thermagrid, _solar_profile, _wind_power = generate_demand_inputs(
        geojson_object=geojson_object
    )
    geojson_file = fetch_geojson(
        geojson_object=geojson_object,
        inputs_thermagrid=inputs_thermagrid,
    )
    demand_profile = demand_thermagrid(front_data=front_data, geojson_file=geojson_file)
    return build_demand_representative_input(
        demand_input=demand_profile,
        year=2025,
        input_unit="kW",
    )


def kpi_calculation(kpi_front_data):
    """Calculate KPI scores by category and by primary use."""
    selected_kpis = [KPIInput(**kpi) for kpi in kpi_front_data["entries"]]
    data = KPIRequest(selected_kpis=selected_kpis, a=4, b=4)
    return calculate_kpi_scores(data), calculate_kpi_scores_primary_use(data)


def barriers_calculation(barriers_front_data):
    """Calculate barrier risk scores and associated incentives."""
    selected_barriers = []
    for category_block in barriers_front_data["barriers"]:
        for persona, barriers in category_block.items():
            for barrier in barriers:
                selected_barriers.append(
                    BarriersInput(
                        persona=persona,
                        id=barrier["id"],
                        likelihood=barrier["valueLikelihood"],
                        impact=barrier["valueImpact"],
                    )
                )
    return calculate_barriers_scores(BarriersRequest(selected_barriers=selected_barriers))


def computation_modules(technology_front_data):
    """Run the optimisation model and derive climate vulnerabilities."""
    from api.services.scripts.computation_modules.main import run_model

    results_cm = run_model(technology_front_data)
    climate_vulnerabilities_per_tech = get_climate_vulnerabilities(technology_front_data)
    return results_cm, climate_vulnerabilities_per_tech


def outputs_to_front(results_cm, climate_vulnerabilities_per_tech, outputs_barriers):
    """Build the response structure expected by the frontend integration."""
    return {
        "computation_modules": results_cm,
        "climate_vulnerabilities": climate_vulnerabilities_per_tech,
        "barriers": outputs_barriers,
    }


# ---------------------------------------------------------------------------
# NOT USED IN THIS PUBLIC VERSION YET
# ---------------------------------------------------------------------------
# The original repository also contained ``parse_demand`` based on
# ``process_front_loads_input``. It is intentionally disabled here because
# neither of the supplied entry scripts calls it and its integration flow is
# not complete for this release.
#
# from api.services.scripts.profiles_calculation.build_demand_representative_days import (
#     process_front_loads_input,
# )
#
# def parse_demand(demand_front_data, diagram_front_data):
#     final_loads = process_front_loads_input(demand_front_data)
#     return final_loads
