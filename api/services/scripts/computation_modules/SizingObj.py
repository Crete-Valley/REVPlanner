import pyomo.environ as pyo
def AddObj(m, inv_cost_g,inv_cost_c,inv_cost_sd, inv_cost_g_cap, inv_cost_c_cap, inv_cost_sd_cap, maint_cost_g, maint_cost_c, maint_cost_sd,
                   weight_day, buy_price, sell_price, co2_par, obj_func, carrier_g, carrier_f, fuels_cost, fuels_CO2_em, fuel_renew, rep_days,
                    generators, converters, storage_devices):
    generators_in_sys = [g for g in generators if g.in_sys == 1]
    converters_in_sys = [c for c in converters if c.in_sys == 1]
    sd_in_sys = [sd for sd in storage_devices if sd.in_sys == 1]

    ## Objecive Constraints
    if obj_func.max_inv is not None:
        def max_inv_const(m):
            investment_total = sum(inv_cost_g[g] * m.CapG[g] for g in m.G_candidate) + \
                            sum(inv_cost_c[c] * m.CapC[c] for c in m.C_candidate) + \
                            sum(inv_cost_sd[sd] * m.CapSD[sd] for sd in m.SD_candidate)
            return investment_total <= obj_func.max_inv
        m.InvMax = pyo.Constraint(rule=max_inv_const)
    if obj_func.max_maint is not None:
        def max_maint_cost(m):
            maintenance = sum(maint_cost_g[g] * m.CapG[g] for g in m.G_candidate) + \
                          sum(maint_cost_c[c] * m.CapC[c] for c in m.C_candidate) + \
                          sum(maint_cost_sd[sd] * m.CapSD[sd] for sd in m.SD_candidate)+ \
                          sum(maint_cost_g[g.id] * g.max_inst  for g in generators_in_sys ) + \
                          sum(maint_cost_c[c.id] * c.max_inst for c in converters_in_sys) + \
                          sum(maint_cost_sd[sd.id] * sd.max_cap for sd in sd_in_sys)
            return maintenance <= obj_func.max_maint
        m.MaintMax = pyo.Constraint( rule=max_maint_cost)
    if obj_func.max_co2_em is not None:
        def max_co2_emission(m):
            co2_levels = sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_rate[k] * m.Import[k, d, t] *rep_days.dT # network emissions with avg value
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_rate
            ) + sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_profile[k][d][t] * m.Import[k, d, t] *rep_days.dT # network emissions with emissions profile
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_profile
            ) + sum(
                weight_day[d] * 365 *
                sum(
                    fuels_CO2_em[f] * m.FuelUse[f, d, t] *rep_days.dT  # Fuels emissions (primary source on the system)
                    for t in m.T
                )
               for f in m.F for d in m.D
            )
            return co2_levels <= obj_func.max_co2_em
        m.CO2Max_levels = pyo.Constraint(rule=max_co2_emission)

    if obj_func.max_co2_costs is not None:
        def max_co2_costs(m):
            co2_levels = sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_rate[k] * m.Import[k, d, t] *rep_days.dT
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_rate
            ) + sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_profile[k][d][t] * m.Import[k, d, t]*rep_days.dT
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_profile
            ) + sum(
                weight_day[d] * 365 *
                sum(
                    fuels_CO2_em[f] * m.FuelUse[f, d, t]*rep_days.dT  # Fuels emissions (primary source on the system)
                    for t in m.T
                )
                for f in m.F for d in m.D
            )
            co2costs=co2_levels*co2_par.cost
            return co2costs <= obj_func.max_co2_costs

        m.CO2Max_Costs = pyo.Constraint(rule=max_co2_costs)

    if obj_func.min_renew is not None:
        def min_renew_int(m):
            Imports = sum(
                weight_day[d] * 365 *
                sum(
                    m.Import[k, d, t]*rep_days.dT
                    for t in m.T
                )
                for k in m.N for d in m.D
            )
            en_not_renew = sum(
                weight_day[d] * 365 * sum(m.FuelUse[f, d, t]*rep_days.dT for t in m.T)
                for f in m.F for d in m.D
                if fuel_renew[f] == 0
            )

            Renew_prod = sum(
                weight_day[d] * 365 *
                sum(m.RenewableGen[g, d, t] * rep_days.dT for g in m.G_all for t in m.T)
                for d in m.D
            ) + sum(
                weight_day[d] * 365 *
                sum(m.FuelUse[f, d, t] * rep_days.dT for t in m.T)
                for f in m.F for d in m.D
                if fuel_renew[f] == 1
            )

            return Renew_prod-(Renew_prod + Imports + en_not_renew ) * obj_func.min_renew >= 0
        m.RenewInt_min = pyo.Constraint( rule=min_renew_int)



    ## Objective Function
    def objective_rule(m):

        #Capitalized investment cost (annual)
        investment = sum(inv_cost_g_cap[g] * m.CapG[g] for g in m.G_candidate) + \
                     sum(inv_cost_c_cap[c] * m.CapC[c] for c in m.C_candidate) +\
                     sum(inv_cost_sd_cap[sd] * m.CapSD[sd] for sd in m.SD_candidate)

        # Annual maintenance
        maintenance = sum(maint_cost_g[g] * m.CapG[g] for g in m.G_candidate) + \
                      sum(maint_cost_c[c] * m.CapC[c] for c in m.C_candidate) + \
                      sum(maint_cost_sd[sd] * m.CapSD[sd] for sd in m.SD_candidate)+ \
                      sum(maint_cost_g[g.id] * g.max_inst  for g in generators_in_sys ) + \
                      sum(maint_cost_c[c.id] * c.max_inst for c in converters_in_sys) + \
                      sum(maint_cost_sd[sd.id] * sd.max_cap for sd in sd_in_sys)

        energy_cost = sum(
            weight_day[d] * 365 *
            sum(
                buy_price[k][d][t] * m.Import[k, d, t]*rep_days.dT -
                sell_price[k][d][t] * m.Export[k, d, t]*rep_days.dT
                for t in m.T
            )
            for k in m.N for d in m.D
        ) + sum(
            weight_day[d] * 365 * sum(m.FuelUse[f, d, t]*rep_days.dT*fuels_cost[f] for t in m.T)
            for f in m.F for d in m.D
        )





        ## Objective Function
        if obj_func.obj == 'Min_NPV':

            co2_levels = sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_rate[k] * m.Import[k, d, t]*rep_days.dT
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_rate
            ) + sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_profile[k][d][t] * m.Import[k, d, t]*rep_days.dT
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_profile
            ) + sum(
                weight_day[d] * 365 *
                sum(
                    fuels_CO2_em[f] * m.FuelUse[f, d, t]*rep_days.dT  # Fuels emissions (primary source on the system)
                    for t in m.T
                )
                for f in m.F for d in m.D
            )
            co2_cost = co2_levels * co2_par.cost

            return investment + maintenance + energy_cost + co2_cost

        elif obj_func.obj == 'Min_Co2_em':

            co2_levels = sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_rate[k] * m.Import[k, d, t]*rep_days.dT
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_rate
            ) + sum(
                weight_day[d] * 365 *
                sum(
                    co2_par.emissions_profile[k][d][t] * m.Import[k, d, t]*rep_days.dT
                    for t in m.T
                )
                for k in m.N for d in m.D if k in co2_par.emissions_profile
            ) + sum(
                weight_day[d] * 365 * sum(fuels_CO2_em[f] * m.FuelUse[f, d, t]*rep_days.dT  # Fuels emissions (primary source on the system)
                for t in m.T
                )
                for f in m.F for d in m.D
            )

            return co2_levels + (
                        investment + maintenance + energy_cost ) * 1e-9  # for multiple equivalent solutions

        elif obj_func.obj == 'Max_renw_int':

            en_imports = sum(
                weight_day[d] * 365 *
                sum(m.Import[k, d, t]*rep_days.dT for t in m.T
                    )
                for k in m.N for d in m.D
            )
            en_not_renew = + sum(
                weight_day[d] * 365 * sum(m.FuelUse[f, d, t]*rep_days.dT for t in m.T)
                for f in m.F for d in m.D
                if fuel_renew[f] == 0
            )
            return en_imports + en_not_renew + (
                        investment + maintenance + energy_cost ) * 1e-9  # for multiple equivalent solutions
        else:
            raise ValueError(f"'Objective not recognized")


    m.Obj = pyo.Objective(rule=objective_rule, sense=pyo.minimize)
