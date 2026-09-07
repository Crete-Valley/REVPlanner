import warnings

from api.services.scripts.computation_modules.read_inputs import (
    CO2Par,
    Converter,
    EVFleets,
    Fuels,
    Generation,
    Load,
    ObjFunc,
    RepDays,
    Storage,
    SystemConn,
)


def _validate_input_data(data):
    """Validate that the model input has already been deserialized to a Python dict.

    The API/backend layer should deserialize the JSON received from the frontend
    before calling the model. No input file is read or written here.
    """
    if not isinstance(data, dict):
        raise TypeError(
            "Expected input data as a Python dictionary. "
            "Deserialize the JSON received from the frontend before calling the model."
        )
    return data

def _require_mapping(data, key):
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Expected '{key}' to be a JSON object.")
    return value


def _normalize_objective(value):
    normalized = str(value).strip().lower()
    mapping = {
        "min_npv": "Min_NPV",
        "min_co2_em": "Min_Co2_em",
        "max_renw_int": "Max_renw_int",
    }
    if normalized not in mapping:
        raise ValueError(f"Unsupported objective: {value}")
    return mapping[normalized]


def _normalize_control_type(value):
    normalized = str(value).strip().lower()
    mapping = {
        "fixed": "0",
        "shiftable": "SL",
        "thermal": "TL",
        "0": "0",
        "sl": "SL",
        "tl": "TL",
    }
    if normalized not in mapping:
        raise ValueError(
            f"Unsupported load control type '{value}'. Expected fixed, shiftable, or thermal."
        )
    return mapping[normalized]


def _validate_profile_length(profile, expected_len, label):
    if len(profile) != expected_len:
        raise ValueError(
            f"Expected {expected_len} periods, but found {len(profile)} in {label}."
        )


def _as_fraction_list(values, label):
    profile = [float(v) / 100 for v in values]
    if not profile:
        raise ValueError(f"Profile '{label}' is empty.")
    return profile


def ReadCaseData(data):
    data = _validate_input_data(data)

    case = _require_mapping(data, "case")
    system_connections_json = _require_mapping(data, "system_connections")
    fuels_json = _require_mapping(data, "fuels")
    loads_json = _require_mapping(data, "loads")
    evs_json = _require_mapping(data, "ev_fleets")
    generators_json = _require_mapping(data, "generation_assets")
    converters_json = _require_mapping(data, "energy_converters")
    storage_json = _require_mapping(data, "storage_assets")
    co2_json = _require_mapping(data, "co2")

    periods = int(case["periods_per_day"])
    number = int(case["number_of_representative_days"])
    int_rate = float(case["interest_rate_percent"]) / 100

    repr_percent = case.get("representative_day_weights_percent")
    if not isinstance(repr_percent, list):
        raise ValueError("Missing 'case.representative_day_weights_percent'.")
    if len(repr_percent) != number:
        raise ValueError(
            f"Expected {number} representative-day weights, but found {len(repr_percent)}."
        )
    repr_list = [float(value) / 100 for value in repr_percent]
    total = sum(repr_list)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"The sum of representative-day weights {total} is not equal to 100 %.")

    rep_days = RepDays(periods, number, repr_list, 24 / periods)

    constraints = case.get("constraints", {})
    if constraints is None:
        constraints = {}
    obj_function = ObjFunc(
        _normalize_objective(case["objective"]),
        constraints.get("max_investment_cost_eur"),
        constraints.get("max_maintenance_cost_eur"),
        constraints.get("max_co2_emissions_kg"),
        constraints.get("max_co2_emissions_cost_eur"),
        None
        if constraints.get("min_renewable_integration_percent") is None
        else float(constraints["min_renewable_integration_percent"]) / 100,
    )

    system_connections = {}
    for net, conn in system_connections_json.items():
        system_connections[net] = SystemConn(
            str(conn["consumption_tariff_id"]).strip(),
            str(conn["injection_remuneration_id"]).strip(),
        )

    fuels = []
    for fuel_id, fuel_data in fuels_json.items():
        renewable = fuel_data["renewable"]
        if not isinstance(renewable, bool):
            warnings.warn(
                f"Fuel '{fuel_id}' has non-boolean renewable flag '{renewable}'. "
                "It will be coerced to bool."
            )
        fuels.append(
            Fuels(
                fuel_id,
                fuel_data["type"],
                fuel_data["cost_eur_per_mwh"],
                fuel_data["annual_availability_mwh"],
                fuel_data["co2_emissions_kg_per_mwh"],
                int(bool(renewable)),
            )
        )

    co2_par = CO2Par(
        float(co2_json.get("cost_eur_per_kg", 0.0)),
        {
            net: float(value)
            for net, value in co2_json.get("network_emissions_kg_per_mwh", {}).items()
        },
    )

    loads = []
    for load_id, load_data in loads_json.items():
        flexible = _normalize_control_type(load_data["control_type"])
        connection_point = load_data["connection_point"]
        load_type = str(load_data["type"]).strip().lower()
        R = load_data.get("thermal_resistance_c_per_kw")
        C = load_data.get("thermal_capacitance_kwh_per_c")
        number_of_buildings = int(load_data.get("number_of_buildings", 1))
        if number_of_buildings <= 0:
            raise ValueError(
                f"Load '{load_id}' has invalid number_of_buildings={number_of_buildings}. "
                "Expected a positive integer."
            )

        if flexible == "TL":
            if R is None or C is None:
                raise ValueError(
                    f"Controllable thermal load '{load_id}' must have thermal resistance and capacitance."
                )
            thermal_types = [x.strip().lower() for x in load_type.split("and")]
            if len(thermal_types) != 2:
                raise ValueError(
                    f"Controllable thermal load '{load_id}' type must present two carriers like 'heat and cool'."
                )
            heat_candidates = [x for x in thermal_types if x.startswith("heat")]
            cool_candidates = [x for x in thermal_types if x.startswith("cool")]
            if len(heat_candidates) != 1 or len(cool_candidates) != 1:
                raise ValueError(
                    f"Controllable thermal load '{load_id}' must define exactly one heat carrier and one cool carrier."
                )

            load = Load(
                load_id,
                connection_point,
                "thermal",
                flexible,
                (float(R) * 1000) / number_of_buildings,
                (float(C) / 1000) * number_of_buildings,
                heat_carrier=heat_candidates[0],
                cool_carrier=cool_candidates[0],
                number_of_buildings=number_of_buildings,
            )
        else:
            parsed_types = [x.strip().lower() for x in load_type.split("and") if x.strip()]
            if len(parsed_types) > 1:
                raise ValueError(
                    f"Load '{load_id}' is not controllable thermal (TL), so it must have only one type."
                )
            if R is not None or C is not None:
                warnings.warn(
                    f"Thermal resistance and capacitance apply only to thermal loads and will be ignored for {load_id}."
                )
            if number_of_buildings != 1:
                warnings.warn(
                    f"number_of_buildings only applies to thermal loads and will be ignored for {load_id}."
                )
            load = Load(load_id, connection_point, parsed_types[0] if parsed_types else load_type, flexible)

        loads.append(load)

    mode_mapping = {"cnc": "CnC", "sc": "SC", "v2g": "V2G"}
    EVs = []
    for ev_id, ev_data in evs_json.items():
        mode_key = str(ev_data["operation_mode"]).strip().lower()
        if mode_key not in mode_mapping:
            raise ValueError(
                f"Invalid operation mode '{ev_data['operation_mode']}' for EV fleet '{ev_id}'. "
                "Allowed values are: cnc, sc, v2g."
            )
        dch_eff = ev_data.get("discharging_efficiency_percent")
        if mode_key == "v2g" and (dch_eff is None or float(dch_eff) <= 0):
            raise ValueError(
                f"EV fleet '{ev_id}' is set to V2G but has invalid discharging efficiency."
            )
        EVs.append(
            EVFleets(
                ev_id,
                ev_data["number_of_evs"],
                float(ev_data["battery_capacity_per_ev_kwh"]) / 1000,
                float(ev_data["max_charging_power_per_ev_kw"]) / 1000,
                float(ev_data["max_discharging_power_per_ev_kw"]) / 1000,
                float(ev_data["daily_energy_consumption_per_ev_kwh"]) / 1000,
                float(ev_data["charging_efficiency_percent"]) / 100,
                None if dch_eff is None else float(dch_eff) / 100,
                mode_mapping[mode_key],
                ev_data["connection_point"],
                ev_data["network_name"],
            )
        )

    generators = []
    for gen_id, gen_data in generators_json.items():
        in_sys = int(bool(gen_data["installed"]))
        investment = gen_data.get("installation_eur_per_mw")
        maintenance = gen_data.get("maintenance_eur_per_mw_year")
        life_time = gen_data.get("expected_lifetime_years")
        if in_sys == 0 and (investment is None or maintenance is None or life_time is None):
            raise ValueError(
                f"Expected lifetime, investment, and/or maintenance costs for candidate generator '{gen_id}' are missing."
            )
        if in_sys == 1:
            if maintenance is None:
                maintenance = 0
            if investment not in (None, 0) or life_time is not None:
                warnings.warn(
                    f"Generator '{gen_id}' is already installed, but has investment ({investment}) or life_time ({life_time}) defined. These values will be ignored."
                )
                investment = 0
                life_time = 0
        generators.append(
            Generation(
                gen_id,
                in_sys,
                gen_data["technology"],
                gen_data["max_installed_power_mw"],
                gen_data["connection_point"],
                gen_data["output_energy_carrier"],
                investment,
                maintenance,
                life_time,
                gen_data.get("local_assigned_load"),
            )
        )

    converters = []
    for conv_id, conv_data in converters_json.items():
        in_sys = int(bool(conv_data["installed"]))
        investment = conv_data.get("installation_eur_per_mw")
        maintenance = conv_data.get("maintenance_eur_per_mw_year")
        life_time = conv_data.get("expected_lifetime_years")
        if in_sys == 0 and (investment is None or maintenance is None or life_time is None):
            raise ValueError(
                f"Expected lifetime, investment, and/or maintenance costs for candidate converter {conv_id} are missing."
            )
        if in_sys == 1:
            if maintenance is None:
                maintenance = 0
            if investment not in (None, 0) or life_time is not None:
                warnings.warn(
                    f"Converter '{conv_id}' is already installed, but has investment ({investment}) or life_time ({life_time}) defined. These values will be ignored."
                )
                investment = 0
                life_time = 0

        outputs_raw = conv_data["output_energy_carrier"]
        output = outputs_raw if isinstance(outputs_raw, list) else str(outputs_raw).strip()
        efficiencies_raw = conv_data["conversion_efficiency_percent_or_cop"]
        efficiencies_list = (
            [float(value) / 100 for value in efficiencies_raw]
            if isinstance(efficiencies_raw, list)
            else [float(efficiencies_raw) / 100]
        )
        output_list = output if isinstance(output, list) else [output]
        if len(output_list) != len(efficiencies_list):
            raise ValueError(
                f"Mismatch in outputs ({output_list}) and efficiencies ({efficiencies_list}) for converter {conv_id}."
            )
        efficiency = dict(zip(output_list, efficiencies_list))

        simult = conv_data.get("simultaneous_multiple_outputs")
        if len(output_list) > 1:
            converters.append(
                Converter(
                    conv_id,
                    in_sys,
                    conv_data["technology"],
                    conv_data["max_installed_power_mw"],
                    efficiency,
                    conv_data["connection_point"],
                    conv_data["primary_energy_source"],
                    output,
                    investment,
                    maintenance,
                    life_time,
                    conv_data.get("local_assigned_load"),
                    int(bool(simult)),
                )
            )
        else:
            converters.append(
                Converter(
                    conv_id,
                    in_sys,
                    conv_data["technology"],
                    conv_data["max_installed_power_mw"],
                    efficiency,
                    conv_data["connection_point"],
                    conv_data["primary_energy_source"],
                    output,
                    investment,
                    maintenance,
                    life_time,
                    conv_data.get("local_assigned_load"),
                )
            )

    storage_devices = []
    for sd_id, sd_data in storage_json.items():
        in_sys = int(bool(sd_data["installed"]))
        investment = sd_data.get("installation_eur_per_mwh")
        maintenance = sd_data.get("maintenance_eur_per_mwh_year")
        life_time = sd_data.get("expected_lifetime_years")
        if in_sys == 0 and (investment is None or maintenance is None or life_time is None):
            raise ValueError(
                f"Expected lifetime, investment, and/or maintenance costs for candidate storage device '{sd_id}' are missing."
            )
        if in_sys == 1:
            if maintenance is None:
                maintenance = 0
            if investment not in (None, 0) or life_time is not None:
                warnings.warn(
                    f"Storage device '{sd_id}' is already installed, but has investment ({investment}) or life_time ({life_time}) defined. These values will be ignored."
                )
                investment = 0
                life_time = 0
        storage_devices.append(
            Storage(
                sd_id,
                in_sys,
                sd_data["technology"],
                sd_data["max_capacity_mwh"],
                sd_data["connection_point"],
                sd_data["primary_energy_carrier"],
                sd_data["output_energy_carrier"],
                sd_data["charging_rate_mw_per_mwh"],
                sd_data["discharging_rate_mw_per_mwh"],
                float(sd_data["charging_efficiency_percent"]) / 100,
                float(sd_data["discharging_efficiency_percent"]) / 100,
                float(sd_data["self_discharge_percent_per_hour"]) / 100,
                investment,
                maintenance,
                life_time,
                sd_data.get("local_assigned_load"),
            )
        )

    return (
        loads,
        converters,
        generators,
        storage_devices,
        fuels,
        rep_days,
        system_connections,
        int_rate,
        co2_par,
        obj_function,
        EVs,
    )


def ReadRepDays(data, loads, generators, rep_days, system_connections, co2_par, EVs):
    data = _validate_input_data(data)
    rep_days_json = data.get("representative_days")
    if not isinstance(rep_days_json, list):
        raise ValueError("Expected 'representative_days' to be a list.")
    if len(rep_days_json) != rep_days.number:
        raise ValueError(
            f"Expected {rep_days.number} representative days, but found {len(rep_days_json)}."
        )

    generators_by_id = {g.id: g for g in generators}
    loads_by_id = {l.id: l for l in loads}
    evs_by_id = {ev.id: ev for ev in EVs}

    for day_idx, day_data in enumerate(rep_days_json):
        if int(day_data.get("index", day_idx + 1)) != day_idx + 1:
            raise ValueError(
                f"Representative day index mismatch at position {day_idx + 1}."
            )
        profiles = _require_mapping(day_data, "profiles")

        generation_profiles = profiles.get("generation_percent_installed_power", {})
        gen_id_rep_day = []
        for gen_id, profile_values in generation_profiles.items():
            gen_id_rep_day.append(gen_id)
            if gen_id not in generators_by_id:
                warnings.warn(
                    f"Generator ID '{gen_id}' in representative day {day_idx + 1} not found in system generators."
                )
                continue
            profile = _as_fraction_list(profile_values, f"generator {gen_id} in day {day_idx + 1}")
            _validate_profile_length(profile, rep_days.periods, f"generator {gen_id} in day {day_idx + 1}")
            generators_by_id[gen_id].generation_profiles[day_idx] = profile

        for gen in generators:
            if gen.id not in gen_id_rep_day:
                warnings.warn(f"Profile for Generator '{gen.id}' not found in representative day {day_idx + 1}.")

        loads_id_rep_day = []
        for section_name in ("non_controllable_loads_mw", "controllable_loads_initial_profile_mw"):
            for load_id, profile_values in profiles.get(section_name, {}).items():
                loads_id_rep_day.append(load_id)
                if load_id not in loads_by_id:
                    continue
                profile = [float(v) for v in profile_values]
                _validate_profile_length(profile, rep_days.periods, f"load {load_id} in day {day_idx + 1}")
                loads_by_id[load_id].ini_demand_profiles[day_idx] = profile

        for load in loads:
            if load.id not in loads_id_rep_day and load.flexible != "TL":
                warnings.warn(f"Profile for Load '{load.id}' not found in representative day {day_idx + 1}.")

        shiftable = profiles.get("shiftable_loads", {})
        shiftable_ids = []
        for load_id, params in shiftable.items():
            shiftable_ids.append(load_id)
            if load_id in loads_by_id:
                loads_by_id[load_id].max_adv[day_idx] = params["max_advance_periods"]
                loads_by_id[load_id].max_delay[day_idx] = params["max_delay_periods"]

        for load in loads:
            if load.flexible == "SL" and load.id not in shiftable_ids:
                warnings.warn(
                    f"Parameters for Shiftable Load '{load.id}' not found in representative day {day_idx + 1}."
                )

        thermal = profiles.get("thermal_load_parameters", {})
        thermal_ids = []
        for load_id, params in thermal.items():
            thermal_ids.append(load_id)
            if load_id in loads_by_id:
                loads_by_id[load_id].temp_min[day_idx] = params["t_min_c"]
                loads_by_id[load_id].temp_max[day_idx] = params["t_max_c"]
                profile = [float(v) for v in params["outdoor_temperature_c"]]
                _validate_profile_length(
                    profile,
                    rep_days.periods,
                    f"load {load_id} temperature profile in day {day_idx + 1}",
                )
                loads_by_id[load_id].temp_out[day_idx] = profile

        for load in loads:
            if load.flexible == "TL" and load.id not in thermal_ids:
                warnings.warn(
                    f"Parameters for Thermal Load '{load.id}' not found in representative day {day_idx + 1}."
                )

        for net_name, profile_values in profiles.get("network_co2_emissions_kg_per_mwh", {}).items():
            if net_name not in system_connections:
                warnings.warn(
                    f"Network name '{net_name}' in representative day {day_idx + 1} not found in system connections."
                )
                continue
            profile = [float(v) for v in profile_values]
            _validate_profile_length(
                profile,
                rep_days.periods,
                f"net emissions for {net_name} in day {day_idx + 1}",
            )
            if net_name in co2_par.emissions_rate:
                warnings.warn(
                    f"'{net_name}' network CO2 emissions rate replaced by profile defined in representative day {day_idx + 1}."
                )
                del co2_par.emissions_rate[net_name]
            if net_name not in co2_par.emissions_profile:
                co2_par.emissions_profile[net_name] = {}
            co2_par.emissions_profile[net_name][day_idx] = profile

        tariff_rep_day = {}
        for tariff_id, profile_values in profiles.get("tariffs_eur_per_mwh", {}).items():
            profile = [float(v) for v in profile_values]
            _validate_profile_length(profile, rep_days.periods, f"tariff {tariff_id} in day {day_idx + 1}")
            tariff_rep_day[tariff_id] = profile

        for carrier, conn in system_connections.items():
            if conn.tariff_code in tariff_rep_day:
                conn.tariff[day_idx] = tariff_rep_day[conn.tariff_code]
            else:
                warnings.warn(
                    f"Tariff for network consumed energy ({carrier}) with code {conn.tariff_code} doesn't exist on day {day_idx + 1}."
                )
            if conn.remuneration_code in tariff_rep_day:
                conn.remuneration_price[day_idx] = tariff_rep_day[conn.remuneration_code]
            else:
                warnings.warn(
                    f"Remuneration tariff for network injected {carrier} with code {conn.remuneration_code} doesn't exist on day {day_idx + 1}."
                )

        avail_ids = []
        for ev_id, profile_values in profiles.get("ev_availability_percent_connected", {}).items():
            avail_ids.append(ev_id)
            if ev_id not in evs_by_id:
                continue
            profile = _as_fraction_list(profile_values, f"EV availability profile {ev_id} in day {day_idx + 1}")
            _validate_profile_length(profile, rep_days.periods, f"EV availability profile {ev_id} in day {day_idx + 1}")
            evs_by_id[ev_id].avail_profile[day_idx] = profile

        use_ids = []
        for ev_id, profile_values in profiles.get("ev_use_percent", {}).items():
            use_ids.append(ev_id)
            if ev_id not in evs_by_id:
                continue
            profile = _as_fraction_list(profile_values, f"EV use profile {ev_id} in day {day_idx + 1}")
            _validate_profile_length(profile, rep_days.periods, f"EV use profile {ev_id} in day {day_idx + 1}")
            evs_by_id[ev_id].EV_use_prof[day_idx] = profile
            if abs(sum(profile) - 1) > 1e-4:
                raise ValueError(
                    f"EV battery use profile {ev_id} in day {day_idx} must sum to 100, but sums to {sum(profile) * 100:.2f}"
                )

        for ev in EVs:
            if ev.id not in avail_ids:
                raise ValueError(
                    f"Availability profile for EV '{ev.id}' not found in representative day {day_idx + 1}."
                )
            if ev.id not in use_ids:
                raise ValueError(
                    f"EV use profile for EV '{ev.id}' not found in representative day {day_idx + 1}."
                )

    missing_co2 = []
    incomplete_profiles = {}
    for net in system_connections.keys():
        has_rate = net in co2_par.emissions_rate
        has_profile = net in co2_par.emissions_profile
        if has_rate:
            continue
        if has_profile:
            missing_days = [
                day + 1
                for day in range(rep_days.number)
                if day not in co2_par.emissions_profile[net]
            ]
            if missing_days:
                incomplete_profiles[net] = missing_days
        else:
            missing_co2.append(net)

    errors = []
    if missing_co2:
        errors.append(
            "Missing CO2 emissions data for network(s): "
            + ", ".join(missing_co2)
            + ". Each system connection must have either a constant CO2 emissions rate "
            + "in the JSON case data or a daily profile in all representative days."
        )
    if incomplete_profiles:
        details = "; ".join(
            f"{net}: missing day(s) {days}" for net, days in incomplete_profiles.items()
        )
        errors.append("Incomplete CO2 emissions profiles for network(s): " + details)
    if errors:
        raise ValueError("\n".join(errors))