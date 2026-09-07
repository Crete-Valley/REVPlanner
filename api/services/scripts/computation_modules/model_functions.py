from api.services.scripts.computation_modules.SizingObj import *
from api.services.scripts.computation_modules.MES_Conf import *
from api.services.scripts.computation_modules.EVs_module import *
from api.services.scripts.computation_modules.Demand_response import *
from api.services.scripts.computation_modules.Storage import *
import pyomo.environ as pyo
import math
import numbers
from tabulate import tabulate


def OptimiseMultiEnergySystem(CS_name, loads, converters, generators, storage_devices, fuels, rep_days, system_connections, int_rate, co2_par, obj_func, EVs):
    model = pyo.ConcreteModel()
    carriers_set = set(system_connections.keys())
    # Add carriers from converters
    for c in converters:
        carriers_set.add(c.source)
        output = c.output
        if isinstance(output, list):
            carriers_set.update(output)
        else:
            carriers_set.add(output)
    # Add carriers from generators
    for g in generators:
        output = g.output
        if isinstance(output, list):
            carriers_set.update(output)
        else:
            carriers_set.add(output)
    # Add from loads
    for l in loads:
        if l.flexible == 'TL':
            carriers_set.add(l.heat_carrier)
            carriers_set.add(l.cool_carrier)
        else:
            carriers_set.add(l.load_type)
    # Add carriers from storage devices
    for sd in storage_devices:
        carriers_set.add(sd.in_carrier)
    for sd in storage_devices:
        carriers_set.add(sd.out_carrier)
    for f in fuels:
        carriers_set.add(f.type)

    carriers_list = list(carriers_set)
    model.K = pyo.Set(initialize=carriers_list)


    ## System Configuration // decision variables & limits ,converters constraints & efficiencies, profiles- production & demand
    (model, weight_day, buy_price, sell_price, gen_prof, demand_profiles,
     carrier_g, max_cap_g, inv_cost_g, inv_cost_g_cap, maint_cost_g,
     carrier_f,fuels_cost,fuels_CO2_em,fuel_renew,
     max_cap_c, inv_cost_c, inv_cost_c_cap, maint_cost_c,
     input_c, output_c, eff_c) = (
        MESConfiguration(model, loads, converters, generators, fuels, rep_days, system_connections, int_rate))

    # storage module
    (model, inv_cost_sd, inv_cost_sd_cap, maint_cost_sd, input_sd, output_sd) = (
        Add_Storage(model, storage_devices, int_rate, rep_days))

    # EV module
    (model,  EVsCNC, EVs_SC_V2G, ev_cnc_p_ch, cnc_SoC_prof, ev_dict) = Add_EVs(model, EVs, rep_days)

    # DR Module
    model, th_heat_by_carrier, th_cool_by_carrier = Demand_response(model, loads, rep_days)



    model = Add_local_asset_limits(
        model, loads, generators, converters, storage_devices,
        carrier_g, output_c, output_sd, input_sd    )

    ## Energy balances
    def energy_balance_rule(m, k, d, t):
        # Generators
        generation = sum(
            m.RenewableGen[g, d, t] for g in m.G_all if carrier_g[g] == k
        )

        fuelin = sum(m.FuelUse[f, d, t] for f in m.F if carrier_f[f] == k)

        #convertors injection and consumption
        conversion = sum(m.ConvDispatch[c, k, d, t] for c in m.C_all)
        conversion_cons = sum(
            m.CInput[c, d, t] for c in m.C_all if input_c[c] == k
        )

        # Storage injection and consumption
        storage_inj= sum(
            m.SD_inj[sd, d, t] for sd in m.SD_all if output_sd[sd] == k
        )
        storage_cons = sum(
            m.SD_cons[sd, d, t] for sd in m.SD_all if input_sd[sd] == k
        )

        # EVs charging/discharging

        EV_cons = sum( m.P_EV_ch[ev, d, t] for ev in m.EV if ev_dict[ev].carrier==k) + sum( ev_cnc_p_ch[ev.id][d][t] for ev in EVsCNC if ev.carrier==k)
        EV_inj = sum(m.P_EV_dch[ev, d, t] for ev in m.EV if ev_dict[ev].carrier==k)




        # Networks imports & exports
        if k in m.N:
            imports = m.Import[k, d, t]
            exports = m.Export[k, d, t]
        else:
            imports = 0
            exports = 0

        fixed_demand = sum(
            demand_profiles[k][l][d][t]
            for l in m.L_fixed_k[k]
        )

        shiftable_demand = sum(
            m.P_SL[l, d, t]
            for l in m.L_shift_k[k]
        )

        thermal_heat_demand = sum(
            m.P_heat[l, d, t] for l in m.L_th_heat_k[k]
        )

        thermal_cool_demand = sum(
            m.P_cool[l, d, t] for l in m.L_th_cool_k[k]
        )

        flexible_demand = shiftable_demand + thermal_heat_demand + thermal_cool_demand

        return generation + fuelin + conversion + storage_inj + imports + EV_inj - exports - conversion_cons - storage_cons -EV_cons == fixed_demand +flexible_demand

    model.EnergyBalance = pyo.Constraint(
        model.K, model.D, model.T, rule=energy_balance_rule)



    ### Objective ###
    AddObj(model, inv_cost_g,inv_cost_c,inv_cost_sd, inv_cost_g_cap, inv_cost_c_cap, inv_cost_sd_cap, maint_cost_g, maint_cost_c, maint_cost_sd,
                   weight_day, buy_price, sell_price, co2_par, obj_func, carrier_g, carrier_f, fuels_cost, fuels_CO2_em, fuel_renew, rep_days, generators, converters, storage_devices)

    tech_g = {g.id: g.technology for g in generators}
    tech_c = {c.id: c.technology for c in converters}
    tech_sd = {sd.id: sd.technology for sd in storage_devices}
    fuel_type = {f.id: f.type for f in fuels}

    ### Solve ###
    solver = pyo.SolverFactory('highs')
    results = solver.solve(model, load_solutions=False)

    tc = results.solver.termination_condition
    st = results.solver.status
    has_solution = len(results.solution) > 0

    print(f"status = {st}")
    print(f"termination = {tc}")
    print(f"has solution = {has_solution}")

    if has_solution:
        model.solutions.load_from(results)
        return build_results_json(
            CS_name, model, generators, converters, storage_devices, loads,
            inv_cost_g, inv_cost_c, inv_cost_sd, inv_cost_g_cap, inv_cost_c_cap, inv_cost_sd_cap,
            maint_cost_g, maint_cost_c, maint_cost_sd, weight_day, buy_price, sell_price, co2_par,
            carrier_g, fuels_cost, fuels_CO2_em, fuel_renew, fuel_type,
            tech_g, tech_c, tech_sd, EVs, EVsCNC, ev_cnc_p_ch, cnc_SoC_prof, rep_days
        )

    message = "Verify user constraints, network connections, and asset input/output carriers."
    print(f"Not optimal. termination = {results.solver.termination_condition}")
    print(message)
    return {
        "case_study": CS_name,
        "solver": {
            "status": str(st),
            "termination_condition": str(tc),
            "message": message,
            "objective_value": None,
        },
        "sections": {},
    }

def build_results_json(CS_name, m, generators, converters, storage_devices,loads,
                          inv_cost_g, inv_cost_c,inv_cost_sd, inv_cost_g_cap, inv_cost_c_cap,inv_cost_sd_cap,
                          maint_cost_g, maint_cost_c, maint_cost_sd,weight_day, buy_price, sell_price, co2_par, carrier_g,
                          fuels_cost, fuels_CO2_em, fuel_renew, fuel_type,
                          tech_g, tech_c, tech_sd, EVs,  EVsCNC, ev_cnc_p_ch, cnc_SoC_prof, rep_days):
    zero_tol = 1e-6

    json_output = {
        "case_study": CS_name,
        "solver": {
            "status": "optimal",
            "message": "Solver converged to an optimal solution.",
            "objective_value": None,
        },
        "sections": {},
    }

    def to_json_value(value):
        """Convert model and input scalar values to strict JSON primitives."""
        if value is None or isinstance(value, (str, bool)):
            return value
        if isinstance(value, numbers.Integral):
            return int(value)
        if isinstance(value, numbers.Real):
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"Cannot export non-finite value to JSON: {value}")
            return value
        return str(value)

    section_keys = {
        "SYSTEM COSTS": "system_costs",
        "NETWORK RESULTS": "network_results",
        "Assets in initial system": "assets_in_initial_system",
        "Assets to be Installed": "assets_to_be_installed",
        "FUELS": "fuels",
        "EV CHARGING (kW)": "ev_charging_kw",
        "EV DISCHARGING (kW)": "ev_discharging_kw",
        "EV SoC (%)": "ev_soc_percent",
        "SHIFTABLE LOADS PROFILES (MW)": "shiftable_loads_profiles_mw",
        "THERMAL LOADS TEMPERATURES (ºC)": "thermal_loads_temperatures_o_c",
        "THERMAL LOADS PROFILES (MW) - HEAT": "thermal_loads_profiles_mw_heat",
        "THERMAL LOADS PROFILES (MW) - COOL": "thermal_loads_profiles_mw_cool",
        "NETWORK IMPORTS HOURLY (MW)": "network_imports_hourly_mw",
        "NETWORK EXPORTS HOURLY (MW)": "network_exports_hourly_mw",
        "CONVERTER INPUTS HOURLY (MW)": "converter_inputs_hourly_mw",
        "CONVERTER OUTPUTS HOURLY (MW)": "converter_outputs_hourly_mw",
        "CONVERTER TOTAL OUTPUTS HOURLY (MW)": "converter_total_outputs_hourly_mw",
        "STORAGE CHARGING HOURLY (MW)": "storage_charging_hourly_mw",
        "STORAGE DISCHARGING HOURLY (MW)": "storage_discharging_hourly_mw",
        "FUEL USE HOURLY (MW)": "fuel_use_hourly_mw",
    }

    header_keys = {
        "Investment cost (€)": "investment_cost_eur",
        "Annualized Investment cost (€)": "annualized_investment_cost_eur",
        "Maintenance cost (€)": "maintenance_cost_eur",
        "Energy cost (€)": "energy_cost_eur",
        "Energy remuneration (€)": "energy_remuneration_eur",
        "CO2 Emissions (kg)": "co2_emissions_kg",
        "CO2 cost (€)": "co2_cost_eur",
        "Renewable integration (%)": "renewable_integration_percent",
        "Network": "network",
        "Energy import (MWh)": "energy_import_mwh",
        "Energy Cost (€)": "energy_cost_eur",
        "Energy Export (MWh)": "energy_export_mwh",
        "Type": "type",
        "ID": "id",
        "Technology": "technology",
        "Capacity (MW)": "capacity_mw",
        "Maintenance cost (€/year)": "maintenance_cost_eur_year",
        "Ins. Capacity (MW)": "ins_capacity_mw",
        "Type (carrier) ": "type_carrier",
        "Energy (MWh)": "energy_mwh",
        "Cost (€)": "cost_eur",
        "EV": "ev",
        "Day": "day",
        "Load": "load",
        "Temperature": "temperature",
        "Converter": "converter",
        "Storage": "storage",
        "Fuel": "fuel",
        "Carrier": "carrier",
    }

    def add_section(section_name, headers, rows):
        section_key = section_keys[section_name]
        output_headers = [header_keys.get(str(header), str(header)) for header in headers]

        records = []
        for row in rows:
            if len(row) != len(output_headers):
                raise ValueError(
                    f"Section '{section_name}' has {len(output_headers)} columns but a row has {len(row)} values."
                )
            records.append({
                header: to_json_value(value)
                for header, value in zip(output_headers, row)
            })

        json_output["sections"][section_key] = records

    def clean_output_value(value):
        return 0 if abs(value) < zero_tol else value

    def write_hourly_section(section_name, headers, rows):
        print(section_name)
        print(tabulate(rows, headers=headers, tablefmt="grid"))
        add_section(section_name, headers, rows)

    converter_input = {c.id: c.source for c in converters}
    converter_outputs = {
        c.id: c.output if isinstance(c.output, list) else [c.output]
        for c in converters
    }
    storage_input = {sd.id: sd.in_carrier for sd in storage_devices}
    storage_output = {sd.id: sd.out_carrier for sd in storage_devices}
    fuel_carrier = fuel_type

    generators_in_sys = [g for g in generators if g.in_sys == 1]
    converters_in_sys = [c for c in converters if c.in_sys == 1]
    sd_in_sys = [sd for sd in storage_devices if sd.in_sys == 1]


    print("Solver converged to an optimal solution.")
    print("Objective Value: ", pyo.value(m.Obj))

    json_output["solver"]["objective_value"] = to_json_value(pyo.value(m.Obj))


    ### SYSTEM COSTS ###
    investment = sum(inv_cost_g[g] * pyo.value(m.CapG[g]) for g in m.G_candidate) + \
                 sum(inv_cost_c[c] * pyo.value(m.CapC[c]) for c in m.C_candidate) + \
                 sum(inv_cost_sd[sd] * pyo.value(m.CapSD[sd]) for sd in m.SD_candidate)

    investment_annual = sum(inv_cost_g_cap[g] * pyo.value(m.CapG[g]) for g in m.G_candidate) + \
                        sum(inv_cost_c_cap[c] * pyo.value(m.CapC[c]) for c in m.C_candidate) + \
                        sum(inv_cost_sd_cap[sd] * pyo.value(m.CapSD[sd]) for sd in m.SD_candidate)

    maintenance = sum(maint_cost_g[g] * pyo.value(m.CapG[g]) for g in m.G_candidate) + \
                  sum(maint_cost_c[c] * pyo.value(m.CapC[c]) for c in m.C_candidate) + \
                  sum(maint_cost_sd[sd] * pyo.value(m.CapSD[sd]) for sd in m.SD_candidate)+ \
                    sum(maint_cost_g[g.id] * g.max_inst  for g in generators_in_sys ) + \
                    sum(maint_cost_c[c.id] * c.max_inst for c in converters_in_sys) + \
                    sum(maint_cost_sd[sd.id] * sd.max_cap for sd in sd_in_sys)

    energy_cost = sum(
        weight_day[d] * 365 *
        sum(buy_price[k][d][t] * pyo.value(m.Import[k, d, t]*rep_days.dT) for t in m.T)
        for k in m.K for d in m.D if k in m.N
    ) + sum(
        weight_day[d] * 365 *
        sum(pyo.value(m.FuelUse[f, d, t])*rep_days.dT * fuels_cost[f] for t in m.T)
        for f in m.F for d in m.D
    )

    energy_rem = sum(
        weight_day[d] * 365 *
        sum(sell_price[k][d][t] * pyo.value(m.Export[k, d, t]*rep_days.dT) for t in m.T )
        for k in m.K for d in m.D if k in m.N
    )

    co2_net_em = (sum(
        weight_day[d] * 365 *
        sum(co2_par.emissions_rate[k] * pyo.value(m.Import[k, d, t])*rep_days.dT for t in m.T)
        for k in m.K for d in m.D if k in m.N and k in co2_par.emissions_rate
    ) + sum(
        weight_day[d] * 365 *
        sum(co2_par.emissions_profile[k][d][t] * pyo.value(m.Import[k, d, t])*rep_days.dT for t in m.T)
        for k in m.K for d in m.D if k in m.N and k in co2_par.emissions_profile
    ))

    co2_prod_fuels = sum(
        weight_day[d] * 365 *
        sum( fuels_CO2_em[f] * pyo.value(m.FuelUse[f, d, t])*rep_days.dT for t in m.T )
        for f in m.F for d in m.D
        )

    co2_em = co2_net_em + co2_prod_fuels
    co2_cost = co2_em * co2_par.cost

    Imports = sum(
        weight_day[d] * 365 *
        sum(pyo.value(m.Import[k, d, t])*rep_days.dT for t in m.T )
        for k in m.K for d in m.D if k in m.N
    )

    En_fuels_not_renew = sum(
        weight_day[d] * 365 * sum(pyo.value(m.FuelUse[f, d, t])*rep_days.dT for t in m.T)
        for f in m.F for d in m.D
        if fuel_renew[f] == 0
    )

    Renew_prod = sum(
        weight_day[d] * 365 *
        sum(pyo.value(m.RenewableGen[g, d, t]) * rep_days.dT for g in m.G_all for t in m.T)
        for d in m.D
    ) + sum(
        weight_day[d] * 365 *
        sum(pyo.value(m.FuelUse[f, d, t]) * rep_days.dT for t in m.T)
        for f in m.F for d in m.D
        if fuel_renew[f] == 1
    )

    renew_int = Renew_prod / (Renew_prod + Imports + En_fuels_not_renew)

    json_output["solver"]["co2_emissions_kg"] = to_json_value(co2_em)
    json_output["solver"]["renewable_integration_percent"] = to_json_value(renew_int * 100)


    headers = ["Investment cost (€)", "Annualized Investment cost (€)", "Maintenance cost (€)", "Energy cost (€)",
               'Energy remuneration (€)', 'CO2 Emissions (kg)', 'CO2 cost (€)', 'Renewable integration (%)']

    data = [
        [investment, investment_annual, maintenance, energy_cost, energy_rem, co2_em, co2_cost, renew_int * 100]]
    print(tabulate(data, headers=headers, tablefmt="grid"))

    add_section("SYSTEM COSTS", headers, data)

    # Network import/export
    headers_network = [
        'Network', 'Energy import (MWh)', 'Energy Cost (€)',
        'Energy Export (MWh)', 'Energy remuneration (€)'
    ]
    data_network = []

    for k in m.K:
        if k in m.N:
            net_i = sum(
                weight_day[d] * 365 *
                sum(pyo.value(m.Import[k, d, t]) *rep_days.dT for t in m.T)
                for d in m.D
            )

            exp = sum(
                weight_day[d] * 365 *
                sum(pyo.value(m.Export[k, d, t]) *rep_days.dT for t in m.T)
                for d in m.D
            )

            cost_k = sum(
                weight_day[d] * 365 *
                sum(buy_price[k][d][t] * pyo.value(m.Import[k, d, t])*rep_days.dT for t in m.T)
                for d in m.D
            )

            rem = sum(
                weight_day[d] * 365 *
                sum(sell_price[k][d][t] * pyo.value(m.Export[k, d, t]) * rep_days.dT for t in m.T)
                for d in m.D
            )

            data_network.append([k, net_i, cost_k, exp, rem])

    print("\nNetwork Results")
    print(tabulate(data_network, headers=headers_network, tablefmt="grid"))
    add_section("NETWORK RESULTS", headers_network, data_network)

    ### ASSETS  ###

    print("Assets in initial system")
    headers_assets = ["Type", "ID", 'Technology', 'Capacity (MW)', "Maintenance cost (€/year)"]
    data_assets = []

    for g in generators_in_sys:
        data_assets.append(['Generator', g.id, tech_g[g.id],
                            pyo.value(g.max_inst),
                            g.max_inst * maint_cost_g[g.id]])

    for c in converters_in_sys:
        data_assets.append(['Converter', c.id, tech_c[c.id],
                            c.max_inst,
                            c.max_inst * maint_cost_c[c.id]])

    for sd in sd_in_sys:
        data_assets.append(['Storage (MWh)', sd.id, tech_sd[sd.id],
                            sd.max_cap,
                            sd.max_cap * maint_cost_sd[sd.id]])
    print(tabulate(data_assets, headers=headers_assets, tablefmt="grid"))

    add_section("Assets in initial system", headers_assets, data_assets)


    print("Assets to be Installed")
    headers_assets = ["Type", "ID", 'Technology', 'Ins. Capacity (MW)', "Investment cost (€)",
               "Annualized Investment cost (€)", "Maintenance cost (€/year)"]
    data_assets = []
    for g in m.G_candidate:
        data_assets.append(['Generator', g, tech_g[g],
                     pyo.value(m.CapG[g]),
                     pyo.value(m.CapG[g]) * inv_cost_g[g],
                     pyo.value(m.CapG[g]) * inv_cost_g_cap[g],
                     pyo.value(m.CapG[g]) * maint_cost_g[g]])

    for c in m.C_candidate:
        data_assets.append(['Converter', c, tech_c[c],
                     pyo.value(m.CapC[c]),
                     pyo.value(m.CapC[c]) * inv_cost_c[c],
                     pyo.value(m.CapC[c]) * inv_cost_c_cap[c],
                     pyo.value(m.CapC[c]) * maint_cost_c[c]])

    for sd in m.SD_candidate:
        data_assets.append(['Storage (MWh)', sd, tech_sd[sd],
                     pyo.value(m.CapSD[sd]),
                     pyo.value(m.CapSD[sd]) * inv_cost_sd[sd],
                     pyo.value(m.CapSD[sd]) * inv_cost_sd_cap[sd],
                     pyo.value(m.CapSD[sd]) * maint_cost_sd[sd]])

    print(tabulate(data_assets, headers=headers_assets, tablefmt="grid"))

    add_section("Assets to be Installed", headers_assets, data_assets)

    ### FUELS  ###
    headers_fuels = [
        "type",
        "id",
        "cost_eur_mwh",
        "annual_availability_mwh",
        "co2_emissions_kg_mwh",
        "renewable",
        "energy_mwh",
        "final_cost_eur",
    ]

    data_fuels = []

    for f in m.F:
        cons_fuel = sum(
            weight_day[d] * 365
            * sum(
                pyo.value(m.FuelUse[f, d, t]) * rep_days.dT
                for t in m.T
            )
            for d in m.D
        )

        data_fuels.append([
            fuel_type[f],
            f,
            fuels_cost[f],
            "No limit",
            fuels_CO2_em[f],
            bool(fuel_renew[f]),
            cons_fuel,
            cons_fuel * fuels_cost[f],
        ])

    print(tabulate(data_fuels, headers=headers_fuels, tablefmt="grid"))

    add_section("FUELS", headers_fuels, data_fuels)

    ### EV CHARGING ###
    print("EV Charging Profiles (kW)")

    headers_ev = ["EV", "Day"] + [f"t{t+1}" for t in m.T]
    data_ev_ch = []

    for ev in m.EV:
        for d in m.D:
            row = [ev, d]
            for t in m.T:
                row.append(pyo.value(m.P_EV_ch[ev, d, t])*1000)         #MW to kW
            data_ev_ch.append(row)

    for ev in EVsCNC:
        for d in m.D:
            row = [ev.id, d]
            for t in m.T:
                row.append(pyo.value(ev_cnc_p_ch[ev.id][d][t])*1000)         #MW to kW
            data_ev_ch.append(row)

    print(tabulate(data_ev_ch, headers=headers_ev, tablefmt="grid"))

    add_section("EV CHARGING (kW)", headers_ev, data_ev_ch)

    ### EV DISCHARGING ###
    print("EV Discharging Profiles (kW)")

    data_ev_dch = []
    ev_dict = {ev.id: ev for ev in EVs}

    for ev in m.EV:
        if ev_dict[ev].op_mode == "V2G":
            for d in m.D:
                row = [ev, d]
                for t in m.T:
                    row.append(pyo.value(m.P_EV_dch[ev, d, t])*1000)         #MW to kW
                data_ev_dch.append(row)


    print(tabulate(data_ev_dch, headers=headers_ev, tablefmt="grid"))

    add_section("EV DISCHARGING (kW)", headers_ev, data_ev_dch)

    ### EV SoC ###
    print("EV SoC Profiles (%)")

    data_ev_soc = []

    for ev in m.EV:
        ev_obj = ev_dict[ev]
        for d in m.D:
            row = [ev, d]
            for t in m.T:
                row.append(pyo.value(m.SOC_EV[ev, d, t])*100/(ev_obj.bat_cap * ev_obj.number))
            data_ev_soc.append(row)

    for ev in EVsCNC:
        for d in m.D:
            row = [ev.id, d]
            for t in m.T:
                row.append(pyo.value(cnc_SoC_prof[ev.id][d][t])*100/ (ev.bat_cap * ev.number))
            data_ev_soc.append(row)

    print(tabulate(data_ev_soc, headers=headers_ev, tablefmt="grid"))

    add_section("EV SoC (%)", headers_ev, data_ev_soc)

    print("Shiftable Loads Profiles (MW)")

    headers_sl = ["Load", "Day"] + [f"t{t+1}" for t in m.T]
    data_sl = []

    for l in loads:
        if l.flexible == 'SL':
            for d in m.D:
                # Initial profile
                row_ini = [l.id, d] + [l.ini_demand_profiles[d][t] for t in m.T]
                data_sl.append(["INI_" + str(x) if i == 0 else x for i, x in enumerate(row_ini)])
                # Final shifted profile from model
                row_shift = [l.id, d] + [pyo.value(m.P_SL[l.id, d, t]) for t in m.T]
                data_sl.append(["SHIFT_" + str(x) if i == 0 else x for i, x in enumerate(row_shift)])

    print(tabulate(data_sl, headers=headers_sl, tablefmt="grid"))

    add_section("SHIFTABLE LOADS PROFILES (MW)", headers_sl, data_sl)

    print ("Thermal loads temperatures")

    headers_temp = ["Temperature", "Day"] + [f"t{t+1}" for t in m.T]
    data_temp = []

    for l in loads:
        if l.flexible == 'TL':
            for d in m.D:
                # Temp Out profile
                T_out= [l.id, d] + [l.temp_out[d][t] for t in m.T]
                data_temp.append(["Temp. Out_" + str(x) if i == 0 else x for i, x in enumerate(T_out)])
                # Final shifted profile from model
                T_in = [l.id, d] + [pyo.value(m.Temp_in[l.id, d, t]) for t in m.T]
                data_temp.append(["Temp. In_" + str(x) if i == 0 else x for i, x in enumerate(T_in)])

    print(tabulate(data_temp, headers=headers_temp, tablefmt="grid"))

    add_section("THERMAL LOADS TEMPERATURES (ºC)", headers_temp, data_temp)

    print("Thermal Loads Profiles (MW) - Heat")

    headers_tl = ["Load", "Day"] + [f"t{t + 1}" for t in m.T]
    data_tl = []

    for l in loads:
        if l.flexible == 'TL':
            for d in m.D:
                row = [l.id, d]
                for t in m.T:
                    row.append(clean_output_value(pyo.value(m.P_heat[l.id,d,t])))
                data_tl.append(row)

    print(tabulate(data_tl, headers=headers_tl, tablefmt="grid"))

    add_section("THERMAL LOADS PROFILES (MW) - HEAT", headers_tl, data_tl)

    print("Thermal Loads Profiles (MW) - Cool")

    headers_tl = ["Load", "Day"] + [f"t{t + 1}" for t in m.T]
    data_tl = []
    for l in loads:
        if l.flexible == 'TL':
            for d in m.D:
                row = [l.id, d]
                for t in m.T:
                    row.append(clean_output_value(pyo.value(m.P_cool[l.id,d,t])))
                data_tl.append(row)

    print(tabulate(data_tl, headers=headers_tl, tablefmt="grid"))

    add_section("THERMAL LOADS PROFILES (MW) - COOL", headers_tl, data_tl)

    headers_net = ["Network", "Day"] + [f"t{t + 1}" for t in m.T]
    network_import_rows = []
    network_export_rows = []
    for k in m.N:
        for d in m.D:
            import_row = [k, d] + [clean_output_value(pyo.value(m.Import[k, d, t])) for t in m.T]
            export_row = [k, d] + [clean_output_value(pyo.value(m.Export[k, d, t])) for t in m.T]
            network_import_rows.append(import_row)
            network_export_rows.append(export_row)
    write_hourly_section("NETWORK IMPORTS HOURLY (MW)", headers_net, network_import_rows)
    write_hourly_section("NETWORK EXPORTS HOURLY (MW)", headers_net, network_export_rows)

    headers_conv = ["Converter", "Carrier", "Day"] + [f"t{t + 1}" for t in m.T]
    converter_input_rows = []
    converter_output_rows = []
    converter_total_output_rows = []
    for c in m.C_all:
        for d in m.D:
            input_row = [c, converter_input[c], d] + [clean_output_value(pyo.value(m.CInput[c, d, t])) for t in m.T]
            converter_input_rows.append(input_row)
            total_output_row = [c, "total", d]
            for t in m.T:
                total_output_row.append(
                    clean_output_value(
                        sum(pyo.value(m.ConvDispatch[c, k, d, t]) for k in converter_outputs[c])
                    )
                )
            converter_total_output_rows.append(total_output_row)
            for k in converter_outputs[c]:
                output_row = [c, k, d] + [clean_output_value(pyo.value(m.ConvDispatch[c, k, d, t])) for t in m.T]
                converter_output_rows.append(output_row)
    write_hourly_section("CONVERTER INPUTS HOURLY (MW)", headers_conv, converter_input_rows)
    write_hourly_section("CONVERTER OUTPUTS HOURLY (MW)", headers_conv, converter_output_rows)
    write_hourly_section("CONVERTER TOTAL OUTPUTS HOURLY (MW)", headers_conv, converter_total_output_rows)

    headers_sd = ["Storage", "Carrier", "Day"] + [f"t{t + 1}" for t in m.T]
    storage_charge_rows = []
    storage_discharge_rows = []
    for sd in m.SD_all:
        for d in m.D:
            charge_row = [sd, storage_input[sd], d] + [clean_output_value(pyo.value(m.SD_cons[sd, d, t])) for t in m.T]
            discharge_row = [sd, storage_output[sd], d] + [clean_output_value(pyo.value(m.SD_inj[sd, d, t])) for t in m.T]
            storage_charge_rows.append(charge_row)
            storage_discharge_rows.append(discharge_row)
    write_hourly_section("STORAGE CHARGING HOURLY (MW)", headers_sd, storage_charge_rows)
    write_hourly_section("STORAGE DISCHARGING HOURLY (MW)", headers_sd, storage_discharge_rows)

    headers_fuel_hourly = ["Fuel", "Carrier", "Day"] + [f"t{t + 1}" for t in m.T]
    fuel_rows = []
    for f in m.F:
        for d in m.D:
            fuel_row = [f, fuel_carrier[f], d] + [clean_output_value(pyo.value(m.FuelUse[f, d, t])) for t in m.T]
            fuel_rows.append(fuel_row)
    write_hourly_section("FUEL USE HOURLY (MW)", headers_fuel_hourly, fuel_rows)

    return json_output

