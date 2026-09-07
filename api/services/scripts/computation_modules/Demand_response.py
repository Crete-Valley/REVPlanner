import pyomo.environ as pyo

def Demand_response(model, loads, rep_days):

    model = model_shiftable_loads(model, loads, rep_days)

    model, th_heat_by_carrier, th_cool_by_carrier = model_thermal_loads(model, loads, rep_days)

    return model, th_heat_by_carrier, th_cool_by_carrier
def model_shiftable_loads(model, loads, rep_days):
    shift_load={l.id: l for l in loads if l.flexible=='SL'}
    model.L_flex = pyo.Set(initialize=[l.id for l in loads if l.flexible=='SL'])

    # Variables
    # For each load/day, define possible shifts
    shift_options = {}
    for l_id, l in shift_load.items():
        for d in range(rep_days.number):
            adv = l.max_adv[d]
            delay = l.max_delay[d]
            shift_options[(l_id, d)] = list(range(-adv, delay +1 ))


    # Binary selection variables
    model.ShiftSel = pyo.Var(
        [(l, d, s) for (l, d), shifts in shift_options.items() for s in shifts],
        within=pyo.Binary
    )

    # Constraint: exactly one shift selected per load per day
    def one_shift_rule(m, l, d):
        return sum(m.ShiftSel[l,d,s] for s in shift_options[(l,d)]) == 1
    model.OneShift = pyo.Constraint(model.L_flex, model.D, rule=one_shift_rule)


    # Shifted load variable
    model.P_SL = pyo.Var(model.L_flex, model.D, model.T, within=pyo.Reals)

    # Constraint: compute shifted load
    def compute_shifted_load_rule(m, l, d, t):
        load_obj = shift_load[l]
        return m.P_SL[l, d, t] == sum(
            m.ShiftSel[l, d, s] * load_obj.ini_demand_profiles[d][(t - s) % rep_days.periods]
            for s in shift_options[(l, d)]
        )

    model.ComputeShiftedLoad = pyo.Constraint(model.L_flex, model.D, model.T, rule=compute_shifted_load_rule)

    return model


def model_thermal_loads(model, loads, rep_days):

    # SETS
    thermal_loads = { l for l in loads if l.flexible=='TL'}
    model.L_th =  pyo.Set(initialize=[l.id for l in loads if l.flexible=='TL'])

    th_heat_by_carrier = {}
    th_cool_by_carrier = {}

    for k in model.K:
        th_heat_by_carrier[k] = [l.id for l in loads if l.flexible == 'TL' and l.heat_carrier == k]
        th_cool_by_carrier[k] = [l.id for l in loads if l.flexible == 'TL' and l.cool_carrier == k]

    model.L_th_heat_k = pyo.Set(model.K, initialize=lambda m, k: th_heat_by_carrier[k])
    model.L_th_cool_k = pyo.Set(model.K, initialize=lambda m, k: th_cool_by_carrier[k])

    #Parameters
    model.R_th = pyo.Param(model.L_th, initialize={l.id: l.R for l in thermal_loads})
    model.C_th = pyo.Param(model.L_th, initialize={l.id: l.C for l in thermal_loads})

    # Time-dependent parameters: now indexed by (load, day, time)
    model.Temp_out = pyo.Param(model.L_th, model.D, model.T, initialize={
        (l.id, d, t): l.temp_out[d][t] for l in thermal_loads for d in model.D for t in model.T
    })

    model.Temp_min = pyo.Param(model.L_th, model.D, initialize={
        (l.id, d): l.temp_min[d] for l in thermal_loads for d in model.D
    })
    model.Temp_max = pyo.Param(model.L_th, model.D, initialize={
        (l.id, d): l.temp_max[d] for l in thermal_loads for d in model.D
    })

    # Variables
    model.Temp_in = pyo.Var(model.L_th, model.D, model.T,  within=pyo.Reals)
    model.P_heat = pyo.Var(model.L_th, model.D, model.T, within=pyo.NonNegativeReals)
    model.P_cool = pyo.Var(model.L_th, model.D, model.T, within=pyo.NonNegativeReals)
    # binary var to prevent simultaneous heat & cool
    model.bin_heat = pyo.Var(model.L_th, model.D, model.T,within=pyo.Binary)

    #BigM
    M = max(
        max(l.temp_max[d] for l in thermal_loads for d in model.D),
        max(l.temp_min[d] for l in thermal_loads for d in model.D),
        max(l.temp_out[d][t] for l in thermal_loads for d in model.D for t in model.T)
    )
    # --- CONSTRAINTS ---

    # Thermal dynamics with day dimension
    def thermal_dynamics_rule(m, l, d, t):
        t_prev = m.T.prev(t) if t != m.T.first() else m.T.last()
        return m.Temp_in[l, d, t] == m.Temp_in[l, d, t_prev] + (
                (1 / m.C_th[l]) * (
                m.P_heat[l, d, t]
                - m.P_cool[l, d, t]
                - (m.Temp_in[l, d, t_prev] - m.Temp_out[l, d, t]) / m.R_th[l])
        ) * rep_days.dT

    model.thermal_dynamics = pyo.Constraint(model.L_th, model.D, model.T, rule=thermal_dynamics_rule)

    # Temperature comfort bounds
    def temperature_bounds_rule(m, l, d, t):
        return pyo.inequality(m.Temp_min[l, d], m.Temp_in[l, d, t], m.Temp_max[l, d])

    model.temperature_bounds = pyo.Constraint(model.L_th, model.D, model.T, rule=temperature_bounds_rule)

    # Heat or Cool
    def prevent_heat_rule(m, l, d, t):
        return m.P_heat[l, d, t] <= M * m.bin_heat[l, d, t]

    def prevent_cool_rule(m, l, d, t):
        return m.P_cool[l, d, t] <= M * (1 - m.bin_heat[l, d, t])

    model.prevent_heat = pyo.Constraint(model.L_th, model.D, model.T, rule=prevent_heat_rule)
    model.prevent_cool = pyo.Constraint(model.L_th, model.D, model.T, rule=prevent_cool_rule)

    return model, th_heat_by_carrier, th_cool_by_carrier


