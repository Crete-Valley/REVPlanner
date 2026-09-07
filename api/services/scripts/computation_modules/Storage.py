import pyomo.environ as pyo
from api.services.scripts.computation_modules.MES_Conf import compute_crf


def Add_Storage(model, storage_devices, int_rate, rep_days):
    candidate_sd = [sd for sd in storage_devices if sd.in_sys == 0]

    ### SD Set ###
    model.SD_all = pyo.Set(initialize=[sd.id for sd in storage_devices])
    model.SD_candidate = pyo.Set(initialize=[sd.id for sd in candidate_sd])

    ### Variables ###
    model.CapSD = pyo.Var(model.SD_candidate, within=pyo.NonNegativeReals)
    model.SD_cons = pyo.Var(model.SD_all, model.D, model.T, within=pyo.NonNegativeReals)
    model.SD_inj = pyo.Var(model.SD_all, model.D, model.T, within=pyo.NonNegativeReals)
    model.SD_SoC = pyo.Var(model.SD_all, model.D, model.T, within=pyo.NonNegativeReals)
    model.SD_bin = pyo.Var(model.SD_all, model.D, model.T, within=pyo.Binary) #Prevent simultaneous charge & discharge

    max_cap_sd = {sd.id: sd.max_cap for sd in storage_devices}
    inv_cost_sd_cap = {sd.id: sd.investment * compute_crf(int_rate, sd.life_time) for sd in storage_devices if sd.in_sys==0}
    inv_cost_sd = {sd.id: sd.investment for sd in storage_devices}
    maint_cost_sd = {sd.id: sd.maintenance for sd in storage_devices}
    input_sd = {sd.id: sd.in_carrier for sd in storage_devices}
    output_sd = {sd.id: sd.out_carrier for sd in storage_devices}
    ch_eff_sd = { sd.id: sd.eff_charge for sd in storage_devices}
    dch_eff_sd = {sd.id: sd.eff_discharge for sd in storage_devices}
    loss_rate_sd={sd.id: sd.loss_rate for sd in storage_devices}
    ch_rate_sd={sd.id: sd.ch_rate for sd in storage_devices}
    dch_rate_sd={sd.id: sd.dch_rate for sd in storage_devices}
    bigM={sd.id: sd.max_cap for sd in storage_devices}


    ### Storage Constraints ###

    # Capacity limits
    model.CapSDLimit = pyo.Constraint(
        model.SD_candidate, rule=lambda m, sd: m.CapSD[sd] <= max_cap_sd[sd])

    # Charging/ Discharging limits
    candidate_ids_sd = [sd.id for sd in candidate_sd]
    def charging_limit_rule(m, sd, d, t):
        if sd in candidate_ids_sd : # candidate storage device
            return m.SD_cons[sd, d, t] <= m.CapSD[sd] * ch_rate_sd[sd]
        else:  # Installed
            return m.SD_cons[sd, d, t] <= max_cap_sd[sd] * ch_rate_sd[sd]
    model.SDChargingLimit = pyo.Constraint(model.SD_all, model.D, model.T, rule=charging_limit_rule)

    def discharging_limit_rule(m, sd, d, t):
        if sd in candidate_ids_sd : # candidate storage device
            return m.SD_inj[sd, d, t] <= m.CapSD[sd] * dch_rate_sd[sd]
        else:  # Installed
            return m.SD_inj[sd, d, t] <= max_cap_sd[sd] * dch_rate_sd[sd]
    model.SDDischargingLimit = pyo.Constraint(model.SD_all, model.D, model.T, rule=discharging_limit_rule)

    # Prevent simultaneous charge & discharge
    # Charging only if bin = 1
    model.SDChargingLimit2 = pyo.Constraint(
        model.SD_all, model.D, model.T,
        rule=lambda m, sd, d, t: m.SD_cons[sd, d, t] <= bigM[sd] * ch_rate_sd[sd] * m.SD_bin[sd, d, t]
    )
    model.SDDischargingLimit2 = pyo.Constraint(
        model.SD_all, model.D, model.T,
        rule=lambda m, sd, d, t: m.SD_inj[sd, d, t] <= bigM[sd] * dch_rate_sd[sd] * (1 - m.SD_bin[sd, d, t])
    )

    ## SoC constraints ##
    # Maximum SoC
    def soc_limit_rule(m, sd, d, t):
        if sd in candidate_ids_sd : # candidate storage device
            return m.SD_SoC[sd, d, t] <= m.CapSD[sd]
        else:  # Installed
            return m.SD_SoC[sd, d, t] <= max_cap_sd[sd]
    model.SOCUpperBound = pyo.Constraint(model.SD_all, model.D, model.T, rule=soc_limit_rule)


    #SoC balance
    def soc_balance_rule(m, sd, d, t):

        if t == 0:
            last_t = rep_days.periods - 1
            return (
                    m.SD_SoC[sd, d, t]
                    ==
                    m.SD_SoC[sd, d, last_t] * ((1 - loss_rate_sd[sd])**rep_days.dT)
                    + ch_eff_sd[sd] * m.SD_cons[sd, d, t] * rep_days.dT
                    - (m.SD_inj[sd, d, t] * rep_days.dT )/ dch_eff_sd[sd]
            )

        return (
                m.SD_SoC[sd, d, t]
                ==
                m.SD_SoC[sd, d, t - 1] * ((1 - loss_rate_sd[sd])**rep_days.dT)
                + ch_eff_sd[sd] * m.SD_cons[sd, d, t] * rep_days.dT
                - (m.SD_inj[sd, d, t] * rep_days.dT)/ dch_eff_sd[sd]
        )

    model.SOCBalance = pyo.Constraint(
        model.SD_all, model.D, model.T,
        rule=soc_balance_rule
    )


    return (model, inv_cost_sd, inv_cost_sd_cap, maint_cost_sd, input_sd, output_sd)
