import pyomo.environ as pyo

def Add_EVs(model, EVs_all, rep_days):

    # Split by operation mode
    EVsCNC = [ev for ev in EVs_all if ev.op_mode == "CnC"]
    EVs_SC_V2G = [ev for ev in EVs_all if ev.op_mode in ("SC", "V2G")]

    (ev_cnc_p_ch, cnc_SoC_prof)=CnC_profiles(EVsCNC, rep_days)

    # Evs SC and V2G mode
    (model) = EVs_modeling_SC_V2G(model, EVs_SC_V2G, rep_days)

    ev_dict = {ev.id: ev for ev in EVs_all}

    return model,  EVsCNC, EVs_SC_V2G, ev_cnc_p_ch, cnc_SoC_prof, ev_dict
def EVs_modeling_SC_V2G(model, EVs, rep_days):
    model.EV = pyo.Set(initialize=[ev.id for ev in EVs])

    ev_dict = {ev.id: ev for ev in EVs}

    # Variables
    model.P_EV_ch = pyo.Var(model.EV, model.D, model.T, within=pyo.NonNegativeReals)
    model.P_EV_dch = pyo.Var(model.EV, model.D, model.T, within=pyo.NonNegativeReals)
    model.SOC_EV = pyo.Var(model.EV, model.D, model.T, within=pyo.NonNegativeReals)

    # SOC limits
    def soc_limit_rule(m, ev, d, t):
        return m.SOC_EV[ev, d, t] <= (
                ev_dict[ev].number * ev_dict[ev].bat_cap
        )

    model.EV_SOC_limit = pyo.Constraint(model.EV, model.D, model.T, rule=soc_limit_rule)


    model.bin_ev = pyo.Var(model.EV, model.D, model.T, within=pyo.Binary)

    def ch_limit(m, ev, d, t):
        avail = ev_dict[ev].avail_profile[d][t]
        return m.P_EV_ch[ev, d, t] <= ev_dict[ev].number * ev_dict[ev].p_ch * avail * m.bin_ev[ev, d, t]

    def dch_limit(m, ev, d, t):
        if ev_dict[ev].op_mode != "V2G":
            return m.P_EV_dch[ev, d, t] == 0
        avail = ev_dict[ev].avail_profile[d][t]
        return m.P_EV_dch[ev, d, t] <= ev_dict[ev].number * ev_dict[ev].p_dch * avail * (1 - m.bin_ev[ev, d, t])

    model.EV_charge_limit = pyo.Constraint(model.EV, model.D, model.T, rule=ch_limit)
    model.EV_discharge_limit = pyo.Constraint(model.EV, model.D, model.T, rule=dch_limit)

    # SOC balance
    def soc_balance_rule(m, ev, d, t):
        eta_ch = ev_dict[ev].ch_eff
        eta_dch = ev_dict[ev].dch_eff if ev_dict[ev].dch_eff else 1

        driving_share = ev_dict[ev].EV_use_prof[d][t]
        driving_energy = driving_share * ev_dict[ev].daily_use * ev_dict[ev].number

        if t == m.T.first():
            last_t = rep_days.periods - 1
            return (
                    m.SOC_EV[ev, d, t]
                    == m.SOC_EV[ev, d, last_t]
                    + eta_ch * m.P_EV_ch[ev, d, t]*rep_days.dT
                    - (m.P_EV_dch[ev, d, t]*rep_days.dT) / eta_dch
                    - driving_energy
            )

        return (
                m.SOC_EV[ev, d, t]
                == m.SOC_EV[ev, d, t - 1]
                + eta_ch * m.P_EV_ch[ev, d, t]*rep_days.dT
                - (m.P_EV_dch[ev, d, t]*rep_days.dT) / eta_dch
                - driving_energy
        )

    model.EV_SOC_balance = pyo.Constraint(model.EV, model.D, model.T, rule=soc_balance_rule)

    return model

def CnC_profiles(EVs, rep_days):
    cnc_profiles = {}
    cnc_SoC_prof = {}

    for ev in EVs:
        if ev.op_mode != "CnC":
            continue  # skip non-CnC EVs

        cnc_profiles[ev.id] = {}
        cnc_SoC_prof[ev.id] = {}

        bat_cap_total = ev.bat_cap * ev.number
        p_ch_total = ev.p_ch * ev.number

        for d in range(rep_days.number):

            # Initialize SOC
            soc = bat_cap_total

            # Store full 3-cycle trajectory
            soc_trajectory = []
            ch_trajectory = []

            # Repeat the same day 3 times
            for cycle in range(3):
                for t in range(rep_days.periods):

                    avail = ev.avail_profile[d][t]

                    # Driving consumption
                    driving_share = ev.EV_use_prof[d][t]
                    driving_energy = driving_share * ev.daily_use * ev.number

                    # Update SOC after driving
                    soc -= driving_energy

                    # Charging
                    if avail > 0 and soc < bat_cap_total:
                        charge = min(p_ch_total*avail, (bat_cap_total - soc)/(ev.ch_eff*rep_days.dT))
                        soc += charge*rep_days.dT*ev.ch_eff
                    else:
                        charge = 0.0

                    if soc<0 and cycle > 1:
                        import warnings
                        warnings.warn(f" EVs from the fleet '{ev.id}' are consuming more energy than they can charge.")
                    # Store
                    soc_trajectory.append(soc)
                    ch_trajectory.append(charge)

            # Extract last cycle only
            T = rep_days.periods
            cnc_profiles[ev.id][d] = ch_trajectory[-T:]
            cnc_SoC_prof[ev.id][d] = soc_trajectory[-T:]

    return cnc_profiles, cnc_SoC_prof