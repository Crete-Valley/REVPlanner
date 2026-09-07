from api.services.scripts.computation_modules.read_inputs_from_json import ReadCaseData, ReadRepDays
from api.services.scripts.computation_modules.model_functions import OptimiseMultiEnergySystem


def run_model(input_data):
    """Run the optimisation entirely in memory.

    Parameters
    ----------
    input_data : dict
        Python dictionary obtained from the JSON received from the frontend.

    Returns
    -------
    dict
        JSON-serializable optimisation results ready to return to the frontend.
    """
    if not isinstance(input_data, dict):
        raise TypeError("run_model expects input_data to be a dictionary.")

    (
        loads,
        converters,
        generators,
        storage_devices,
        fuels,
        rep_days,
        system_connections,
        int_rate,
        co2_par,
        obj_func,
        EVs,
    ) = ReadCaseData(input_data)

    ReadRepDays(
        input_data,
        loads,
        generators,
        rep_days,
        system_connections,
        co2_par,
        EVs,
    )

    # print(f"Loaded {len(loads)} Loads")
    # print(f"Loaded {len(converters)} Converters")
    # print(f"Loaded {len(generators)} Generators")
    # print(f"Loaded {len(EVs)} EVs fleets")
    # print(f"Loaded {len(storage_devices)} Storage systems")
    # print(f"Representative Days: {rep_days}")

    keys = list(system_connections.keys())
    if len(keys) > 1:
        keys_string = ", ".join(keys[:-1]) + " and " + keys[-1]
        print(f"System Connected to {keys_string} networks")
    elif len(keys) == 1:
        print(f"System Connected to {keys[0]} network")
    else:
        print("System is not connected to any networks")

    case_data = input_data.get("case", {})
    case_study = str(
        case_data.get("name")
        or case_data.get("case_study")
        or case_data.get("id")
        or "case"
    )

    return OptimiseMultiEnergySystem(
        case_study,
        loads,
        converters,
        generators,
        storage_devices,
        fuels,
        rep_days,
        system_connections,
        int_rate,
        co2_par,
        obj_func,
        EVs,
    )
