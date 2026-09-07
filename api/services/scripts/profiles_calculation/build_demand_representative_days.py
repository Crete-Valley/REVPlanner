from datetime import date, timedelta
from math import sqrt


REPRESENTATIVE_GROUPS = (
    ("winter", "workday"),
    ("winter", "holiday"),
    ("summer", "workday"),
    ("summer", "holiday"),
    ("shoulder", "workday"),
    ("shoulder", "holiday"),
)

SEASON_MONTHS = {
    "winter": {12, 1, 2},
    "summer": {6, 7, 8},
    "shoulder": {3, 4, 5, 9, 10, 11},
}


def build_demand_representative_input(demand_input, year=2025, input_unit="kW"):

    _validate_year(year)

    profiles = _extract_and_validate_profiles(demand_input)

    loads, load_map = _build_loads(profiles)

    day_records = _build_day_records(
        profiles,
        load_map,
        year,
        input_unit
    )

    representative_days = []

    for rep_index, (season, day_type) in enumerate(REPRESENTATIVE_GROUPS, start=1):

        candidates = [
            day
            for day in day_records
            if day["season"] == season
            and day["day_type"] == day_type
        ]

        if not candidates:
            raise ValueError(
                f"No candidate days found for {season} - {day_type}"
            )

        selected_day = _select_representative_day(candidates)

        representativeness_percent = (
            len(candidates) / 365 * 100
        )

        representative_days.append({
            "id": f"rep_day_{rep_index}",
            "index": rep_index,
            "representativeness_percent": representativeness_percent,
            "profiles": {
                "non_controllable_loads_mw": selected_day["profiles"],
                "controllable_loads_initial_profile_mw": None,
                "shiftable_loads": None,
                "thermal_load_parameters": None
            }
        })

    return {
        "loads": loads,
        "representative_days": representative_days
    }

def process_front_loads_input(front_input):

    loads = front_input["loads"]
    representative_days = front_input["representative_days"]

    for rep_day in representative_days:

        profiles = rep_day["profiles"]

        non_controllable = profiles.get(
            "non_controllable_loads_mw",
            {}
        )

        controllable = profiles.get(
            "controllable_loads_initial_profile_mw",
            {}
        )

        shiftable = profiles.get(
            "shiftable_loads",
            {}
        )

        for load_id, load in loads.items():

            control_type = load["control_type"]

            if control_type == "fixed":

                if load_id not in non_controllable:
                    raise ValueError(
                        f"Fixed load {load_id} has no profile "
                        "in non_controllable_loads_mw"
                    )

            elif control_type == "shiftable":

                if load_id not in controllable:
                    raise ValueError(
                        f"Shiftable load {load_id} has no profile "
                        "in controllable_loads_initial_profile_mw"
                    )

                if load_id not in shiftable:
                    raise ValueError(
                        f"Shiftable load {load_id} has no parameters "
                        "in shiftable_loads"
                    )

            elif control_type == "thermal":

                # No lo tratamos todavía
                pass

            else:

                raise ValueError(
                    f"Invalid control_type '{control_type}' "
                    f"for load {load_id}"
                )

    return front_input

def _validate_year(year):

    days_in_year = (
        date(year + 1, 1, 1) - date(year, 1, 1)
    ).days

    if days_in_year != 365:
        raise ValueError(
            "The demand profiles contain 8760 values, "
            "so the selected year must not be a leap year."
        )


def _extract_and_validate_profiles(demand_input):

    if not isinstance(demand_input, list) or not demand_input:
        raise ValueError("demand_input must be a non-empty list")

    profiles = []

    for item in demand_input:

        demand_profile = item.get("demand_profile")

        if not isinstance(demand_profile, dict):
            raise ValueError("Invalid demand_profile")

        required_profiles = (
            "heating_demand",
            "cooling_demand",
            "electricity_demand"
        )

        for profile_name in required_profiles:

            values = demand_profile.get(profile_name)

            if not isinstance(values, list):
                raise ValueError(
                    f"{profile_name} must be a list"
                )

            if len(values) != 8760:
                raise ValueError(
                    f"{profile_name} must contain 8760 values"
                )

        profiles.append(demand_profile)

    return profiles


def _build_loads(profiles):

    loads = {}
    load_map = []

    load_number = 1

    for profile in profiles:

        building_loads = {}

        for load_type in ("electric", "cool", "heat"):

            load_id = f"LOAD{load_number:03d}"

            loads[load_id] = {
                "type": load_type,
                "connection_point": None,
                "thermal_resistance_c_per_kw": None,
                "thermal_capacitance_kwh_per_c": None,
                "control_type": "fixed"
            }

            building_loads[load_type] = load_id

            load_number += 1

        load_map.append(building_loads)

    return loads, load_map


def _build_day_records(profiles, load_map, year, input_unit):

    conversion = _conversion_to_mw(input_unit)

    day_records = []

    current_date = date(year, 1, 1)

    for day_index in range(365):

        season = _get_season(current_date.month)

        if current_date.weekday() < 5:
            day_type = "workday"
        else:
            day_type = "holiday"

        start = day_index * 24
        end = start + 24

        day_profiles = {}
        comparison_vector = []

        for building_index, demand_profile in enumerate(profiles):

            building_loads = load_map[building_index]

            source_profiles = {
                "electric": "electricity_demand",
                "cool": "cooling_demand",
                "heat": "heating_demand"
            }

            for load_type, source_name in source_profiles.items():

                load_id = building_loads[load_type]

                values = [
                    float(value) * conversion
                    for value in demand_profile[source_name][start:end]
                ]

                day_profiles[load_id] = values

                comparison_vector.extend(values)

        day_records.append({
            "date": current_date,
            "season": season,
            "day_type": day_type,
            "profiles": day_profiles,
            "vector": comparison_vector
        })

        current_date += timedelta(days=1)

    return day_records


def _get_season(month):

    for season, months in SEASON_MONTHS.items():

        if month in months:
            return season

    raise ValueError(
        f"Month {month} does not belong to any season"
    )


def _conversion_to_mw(input_unit):

    unit = input_unit.lower()

    if unit == "mw":
        return 1

    if unit == "kw":
        return 1 / 1000

    if unit == "w":
        return 1 / 1_000_000

    raise ValueError(
        "input_unit must be W, kW or MW"
    )


def _select_representative_day(candidates):

    vector_length = len(
        candidates[0]["vector"]
    )

    average_profile = []

    for position in range(vector_length):

        average_value = sum(
            day["vector"][position]
            for day in candidates
        ) / len(candidates)

        average_profile.append(
            average_value
        )

    best_day = None
    best_distance = None

    for day in candidates:

        distance = sqrt(
            sum(
                (value - average_value) ** 2
                for value, average_value
                in zip(day["vector"], average_profile)
            )
        )

        if best_distance is None or distance < best_distance:

            best_distance = distance
            best_day = day

    return best_day