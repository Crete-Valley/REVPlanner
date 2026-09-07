import pyomo.environ as pyo

def compute_crf(i, n):
    if n is None or n <= 0:
        raise ValueError(f"Invalid asset lifetime for CRF: {n}. Lifetime must be > 0.")
    if i == 0:
        return 1 / n
    return (i * (1 + i) ** n) / ((1 + i) ** n - 1)

def Add_generators(model, generators, int_rate):

    # Candidate generators (in_sys == 0)
    candidate_g = [g for g in generators if g.in_sys == 0]

    ### Sets ###
    model.G_all = pyo.Set(initialize=[g.id for g in generators])
    model.G_candidate = pyo.Set(initialize=[g.id for g in candidate_g])

    ### Variables ###
    model.CapG = pyo.Var(model.G_candidate, within=pyo.NonNegativeReals)
    model.RenewableGen = pyo.Var(model.G_all, model.D, model.T, within=pyo.NonNegativeReals)

    # Generators
    carrier_g = {g.id: g.output for g in generators}
    max_cap_g = {g.id: g.max_inst for g in generators}
    inv_cost_g = {g.id: g.investment for g in generators}
    inv_cost_g_cap = {g.id: g.investment * compute_crf(int_rate, g.life_time) for g in generators if g.in_sys == 0}
    maint_cost_g = {g.id: g.maintenance for g in generators}
    gen_prof = {g.id: g.generation_profiles for g in generators}


    ### Assets and System Constraints ###
    # Capacity limits
    model.CapGLimit = pyo.Constraint(
        model.G_candidate, rule=lambda m, g: m.CapG[g] <= max_cap_g[g])

    # Dispatch limits for generators
    candidate_ids_g = [g.id for g in candidate_g]
    def gen_dispatch_rule(m, g, d, t):
        if g in candidate_ids_g:  # candidate generator
            return m.RenewableGen[g, d, t] == m.CapG[g] * gen_prof[g][d][t]
        else:  # Installed
            return m.RenewableGen[g, d, t] == max_cap_g[g] * gen_prof[g][d][t]

    model.GenDispatchLimit = pyo.Constraint(model.G_all, model.D, model.T, rule=gen_dispatch_rule)

    return model, gen_prof,carrier_g, max_cap_g, inv_cost_g, inv_cost_g_cap, maint_cost_g

def Add_converters(model, converters, int_rate):
    # Candidate Converters (in_sys == 0)
    candidate_c = [c for c in converters if c.in_sys == 0]


    ### Sets ###
    model.C_all = pyo.Set(initialize=[c.id for c in converters])
    model.C_candidate = pyo.Set(initialize=[c.id for c in candidate_c])
    model.C_non_simult = pyo.Set( initialize=[c.id for c in converters
            if len(c.output if isinstance(c.output, list) else [c.output]) > 1 and c.simult == 0]
                                  )
    ### Variables ###
    model.CapC = pyo.Var(model.C_candidate, within=pyo.NonNegativeReals)
    model.CInput = pyo.Var(model.C_all, model.D, model.T, within=pyo.NonNegativeReals)
    model.ConvDispatch = pyo.Var(model.C_all, model.K, model.D, model.T, within=pyo.NonNegativeReals)

   ### Parameters ###
    max_cap_c = {c.id: c.max_inst for c in converters}
    inv_cost_c_cap = {c.id: c.investment * compute_crf(int_rate, c.life_time) for c in converters if c.in_sys == 0}
    inv_cost_c = {c.id: c.investment for c in converters}
    maint_cost_c = {c.id: c.maintenance for c in converters}

    input_c = {c.id: c.source for c in converters}
    output_c = {
        c.id: c.output if isinstance(c.output, list)
        else [c.output]
        for c in converters
    }
    eff_c = {
        (c.id, k): c.efficiency[k] for c in converters for k in output_c[c.id]
    }


    ### Constraints ###
    # Capacity limits
    model.CapCLimit = pyo.Constraint(
        model.C_candidate, rule=lambda m, c: m.CapC[c] <= max_cap_c[c])  # only for candidates

    # Limit dispatch based on capacity
    candidate_ids_c = {c.id for c in candidate_c}
    def conv_dispatch_limit_rule(m, c, k, d, t):
        # Determine max capacity for this converter
        cap = m.CapC[c] if c in candidate_ids_c else max_cap_c[c]
        return m.ConvDispatch[c, k, d, t] <= cap

    model.ConvDispatchLimit = pyo.Constraint(
        model.C_all, model.K, model.D, model.T,
        rule=conv_dispatch_limit_rule
    )

    ## Converters with just one possible output at each time, (multiple outputs) - EX: HAVAC ##
    # Binary variables for non-simultaneous converters
    model.bin_conv = pyo.Var(
        [(c.id, k, d, t)
         for c in converters if len(output_c[c.id]) > 1 and c.simult == 0
         for k in output_c[c.id]
         for d in model.D for t in model.T],
        within=pyo.Binary
    )

    # Only one output active per period for non-simultaneous converters
    def conv_one_output_rule(m, c, d, t):
        return sum(m.bin_conv[c, k, d, t] for k in output_c[c]) <= 1

    model.ConvOneOutput = pyo.Constraint(model.C_non_simult, model.D, model.T, rule=conv_one_output_rule)

    def c_non_simult_rule(m, c, k, d, t):
        M = max_cap_c[c]
        return m.ConvDispatch[c, k, d, t] <= M * m.bin_conv[c, k, d, t]

    model.Conv_non_simult = pyo.Constraint(
        [(c, k, d, t)
         for c in model.C_non_simult
         for k in output_c[c]
         for d in model.D
         for t in model.T],
        rule=c_non_simult_rule
    )

    def conv_balance(m, c, k, d, t):
        if (c, k) not in eff_c:
            return m.ConvDispatch[c, k, d, t] == 0
        if c in m.C_non_simult:
            return m.ConvDispatch[c, k, d, t] <= m.CInput[c, d, t] * eff_c[(c, k)]
        else:
            return m.ConvDispatch[c, k, d, t] == m.CInput[c, d, t] * eff_c[(c, k)]

    model.ConvBalance = pyo.Constraint(
        model.C_all, model.K, model.D, model.T, rule=conv_balance)



    return model, max_cap_c, inv_cost_c, inv_cost_c_cap, maint_cost_c, input_c, output_c, eff_c
    
def Add_Fuels(model, fuels, rep_days,weight_day ):

    ### Sets ###
    model.F = pyo.Set(initialize=[f.id for f in fuels])

    ### Variables ###
    model.FuelUse = pyo.Var(model.F, model.D, model.T, within=pyo.NonNegativeReals)

    # Parameters #
    carrier_f = {f.id: f.type for f in fuels}
    fuels_cost = {f.id: f.cost for f in fuels}
    fuels_CO2_em = {f.id: f.co2_em for f in fuels}
    fuel_renew = {f.id: f.renew for f in fuels}

    #Fuel availability constraint
    AnnualAvailability = {f.id: f.avail for f in fuels}
    def annual_fuel_limit_rule(m, f):

        if AnnualAvailability[f] == "NL":
            return pyo.Constraint.Skip
        else:
            AnnualAvailability[f] = float(AnnualAvailability[f])  # ensure numeric

        return sum(m.FuelUse[f, d, t]* rep_days.dT * weight_day[d] * 365
                   for d in m.D
                   for t in m.T) <= AnnualAvailability[f]

    model.AnnualFuelLimit = pyo.Constraint(model.F, rule=annual_fuel_limit_rule) # verificar


    return model, carrier_f,fuels_cost, fuels_CO2_em, fuel_renew

def Add_loads(model, loads):
    ### Sets ###
    model.L = pyo.Set(initialize=[l.id for l in loads])

    # Load classification by flexibility / carrier
    model.L_fixed = pyo.Set(
        initialize=[l.id for l in loads if str(l.flexible) in ('0', '0.0')]
    )
    model.L_shift = pyo.Set(
        initialize=[l.id for l in loads if l.flexible == 'SL']
    )

    # Carrier-indexed subsets
    fixed_by_carrier = {
        k: [l.id for l in loads if l.load_type == k and str(l.flexible) in ('0', '0.0')]
        for k in model.K
    }
    shift_by_carrier = {
        k: [l.id for l in loads if l.load_type == k and l.flexible == 'SL']
        for k in model.K
    }

    model.L_fixed_k = pyo.Set(model.K, initialize=lambda m, k: fixed_by_carrier[k])
    model.L_shift_k = pyo.Set(model.K, initialize=lambda m, k: shift_by_carrier[k])

    # Create demand profiles per carrier only for fixed loads
    demand_profiles = {k: {} for k in model.K}
    for k in model.K:
        for l in model.L_fixed_k[k]:
            load_obj = next(ld for ld in loads if ld.id == l)
            demand_profiles[k][l] = load_obj.ini_demand_profiles

    return model, demand_profiles

def MESConfiguration(model, loads, converters, generators, fuels, rep_days, system_connections, int_rate):

    ### Sets ###
    model.D = pyo.Set(initialize=range(rep_days.number))
    model.T = pyo.Set(initialize=range(rep_days.periods))
    net_conn_carriers = list(system_connections.keys())
    model.N = pyo.Set(initialize=net_conn_carriers)

    ### Variables ###
    model.Import = pyo.Var(model.N, model.D, model.T, within=pyo.NonNegativeReals)
    model.Export = pyo.Var(model.N, model.D, model.T, within=pyo.NonNegativeReals)

    ### Parameters ###
    weight_day = {d: rep_days.repr[d] for d in model.D}
    buy_price = {k: system_connections[k].tariff for k in model.N}
    sell_price = {k: system_connections[k].remuneration_price for k in model.N}

    (model, gen_prof, carrier_g, max_cap_g, inv_cost_g, inv_cost_g_cap, maint_cost_g) = \
        Add_generators(model, generators, int_rate)
    (model, max_cap_c, inv_cost_c, inv_cost_c_cap, maint_cost_c, input_c, output_c, eff_c) =\
        Add_converters(model, converters, int_rate)
    (model, carrier_f,fuels_cost, fuels_CO2_em, fuel_renew) =\
        Add_Fuels(model, fuels, rep_days, weight_day)
    model, demand_profiles = Add_loads(model, loads)


    return (model, weight_day, buy_price, sell_price, gen_prof, demand_profiles,
            carrier_g, max_cap_g, inv_cost_g, inv_cost_g_cap, maint_cost_g,
            carrier_f,fuels_cost, fuels_CO2_em, fuel_renew,
            max_cap_c, inv_cost_c, inv_cost_c_cap, maint_cost_c,
            input_c, output_c, eff_c)

def Add_local_asset_limits(model, loads, generators, converters, storage_devices,
                           carrier_g, output_c, output_sd, input_sd):
    """
    Limit the injection of local assets assigned to a load so that,
    in each day and each period, their output does not exceed the respective load power.
    """
    load_dict = {l.id: l for l in loads}

    # collect load ids that appear in local assets
    local_load_ids = set()

    for g in generators:
        if g.local not in [None, "", 0, "0"] and g.local in load_dict:
            local_load_ids.add(g.local)

    for c in converters:
        if c.local not in [None, "", 0, "0"] and c.local in load_dict:
            local_load_ids.add(c.local)

    for sd in storage_devices:
        if sd.local not in [None, "", 0, "0"] and sd.local in load_dict:
            local_load_ids.add(sd.local)

    model.L_local = pyo.Set(initialize=list(local_load_ids))

    def local_asset_limit_rule(m, l_id, k, d, t):
        l = load_dict[l_id]

        if l.flexible == '0' or l.flexible == 0:
            if l.load_type != k:
                return pyo.Constraint.Skip
            load_power = l.ini_demand_profiles[d][t]

        elif l.flexible == 'SL':
            if l.load_type != k:
                return pyo.Constraint.Skip
            load_power = m.P_SL[l_id, d, t]


        elif l.flexible == 'TL':
            if k == l.heat_carrier:
                load_power = m.P_heat[l_id, d, t]
            elif k == l.cool_carrier:
                load_power = m.P_cool[l_id, d, t]
            else:
                return pyo.Constraint.Skip

        else:
            return pyo.Constraint.Skip

        #  local generation
        gen_local = sum(
            m.RenewableGen[g.id, d, t]
            for g in generators
            if g.local == l_id and carrier_g[g.id] == k
        )

        #  local converter output
        conv_local = sum(
            m.ConvDispatch[c.id, k, d, t]
            for c in converters
            if c.local == l_id and k in output_c[c.id]
        )

        #  local storage discharge
        stor_discharge_local  = sum(
            m.SD_inj[sd.id, d, t]
            for sd in storage_devices
            if sd.local == l_id and output_sd[sd.id] == k
        )

        #  local storage charge
        stor_charge_local = sum(
            m.SD_cons[sd.id, d, t]
            for sd in storage_devices
            if sd.local == l_id and input_sd[sd.id] == k
        )

        return gen_local + conv_local + stor_discharge_local - stor_charge_local <= load_power

    model.LocalAssetLimit = pyo.Constraint(
        model.L_local, model.K, model.D, model.T,
        rule=local_asset_limit_rule
    )

    return model