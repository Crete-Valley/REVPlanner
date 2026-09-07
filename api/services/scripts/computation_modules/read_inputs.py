import pandas as pd
from io import StringIO
import warnings
import os

class RepDays:
    def __init__(self, periods, number, repr, dT):
        self.periods = periods
        self.number = number
        self.repr = repr
        self.dT=dT
    def __repr__(self):
        return f"RepDays(periods={self.periods},number={self.number}, repr={self.repr})"
class CO2Par:
    def __init__(self, cost, emissions):
        self.cost = cost
        self.emissions_rate = emissions
        self.emissions_profile={}

class Generation:
    def __init__(self, id, in_sys, technology, max_inst, connection_point, output,  investment, maintenance, life_time, local):
        self.id = id
        self.in_sys=in_sys
        self.technology = technology
        self.max_inst = max_inst
        self.connection_point = connection_point
        self.output = output
        self.investment = investment
        self.maintenance = maintenance
        self.life_time=life_time
        self.generation_profiles = {}
        self.local=local

class Converter:
    def __init__(self, id, in_sys, technology, max_inst, efficiency, connection_point, source, output,  investment, maintenance, life_time, local, simult=None):
        self.id = id
        self.in_sys=in_sys
        self.technology = technology
        self.max_inst = max_inst
        self.connection_point = connection_point
        self.source = source
        self.output = output
        self.efficiency = efficiency
        self.investment = investment
        self.maintenance = maintenance
        self.life_time=life_time
        self.simult=simult
        self.local=local

class Storage:
    def __init__(self, id, in_sys, technology, max_cap, connection_point,
                 in_carrier, out_carrier, ch_rate, dch_rate,
                 eff_charge, eff_discharge, loss_rate,
                 investment, maintenance, life_time, local):
        self.id = id
        self.in_sys=in_sys
        self.technology = technology
        self.max_cap = max_cap
        self.connection_point = connection_point
        self.in_carrier = in_carrier
        self.out_carrier = out_carrier
        self.ch_rate = ch_rate
        self.dch_rate = dch_rate
        self.eff_charge = eff_charge
        self.eff_discharge = eff_discharge
        self.loss_rate = loss_rate
        self.investment = investment
        self.maintenance = maintenance
        self.life_time = life_time
        self.local=local

class Load:
    def __init__(self, id, connection_point, load_type, flexible ,  R = None , C=None, heat_carrier=None, cool_carrier=None, number_of_buildings=1):
        self.id = id
        self.connection_point = connection_point
        self.load_type = load_type
        self.flexible = flexible
        self.ini_demand_profiles = {}   # Dictionary with day designation as key and profile as np.array
        self.max_adv = {}               # only for shiftable loads
        self.max_delay = {}
        self.R=R                            # only for thermal loads
        self.C=C
        self.temp_min = {}                 # comfort bounds - only for thermal loads
        self.temp_max = {}
        self.temp_out = {}                 # Temp profile for each day - only for thermal loads

        # only for controllable thermal loads
        self.heat_carrier = heat_carrier
        self.cool_carrier = cool_carrier
        self.number_of_buildings = number_of_buildings




class Fuels:
    def __init__(self, id, fuel_type, cost, avail, co2_em, renew):
        self.id = id
        self.type = fuel_type
        self.cost = cost
        self.avail = avail
        self.co2_em = co2_em
        self.renew = renew
class ObjFunc:
    def __init__(self, obj, max_inv=None, max_maint=None, max_co2_em=None, max_co2_costs=None, min_renew=None):
        self.obj = obj
        self.max_inv = max_inv
        self.max_maint = max_maint
        self.max_co2_em = max_co2_em
        self.max_co2_costs = max_co2_costs
        self.min_renew = min_renew

class SystemConn:
    def __init__(self, tariff_code, remuneration_code):
        self.tariff_code = tariff_code
        self.remuneration_code = remuneration_code
        self.tariff = {}
        self.remuneration_price = {}

class EVFleets:
    def __init__(self, id, number, bat_cap, p_ch, p_dch, daily_use, ch_eff, dch_eff, op_mode, connection_point, carrier):
        self.id = id
        self.number = number
        self.bat_cap = bat_cap
        self.p_ch = p_ch
        self.p_dch = p_dch
        self.daily_use = daily_use
        self.ch_eff = ch_eff
        self.dch_eff = dch_eff
        self.op_mode = op_mode
        self.connection_point = connection_point
        self.avail_profile = {}
        self.EV_use_prof = {}
        self.carrier = carrier

def ReadCaseData(inputs_folder):
    import warnings
    sections = ['Study parameters','CO2 emissions per network','CO2 costs', 'Energy Converter', 'Generation', 'Load Data',  'Storage', 'Fuels', 'Objective', 'User constraints',  'System connections', 'EV fleets' ]
    dataframes = {}
    folder_path=inputs_folder
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Input folder '{folder_path}' does not exist.")
    else:
        with open(folder_path+'/CaseData.csv', 'r', encoding='utf-8') as f:
            lines = f.readlines()


    i = 0
    while i < len(lines):
        line = lines[i].strip().strip(';') # Ignore extra ;;
        if line in sections:
            section_name = line
            header = lines[i + 1].strip()
            data_lines = []
            i += 2
            while i < len(lines) and lines[i].strip().strip(';') != '':
                data_lines.append(lines[i])
                i += 1
            data_str = header + '\n' + ''.join(data_lines)
            df = pd.read_csv(StringIO(data_str), sep=';')
            dataframes[section_name] = df
        else:
            i += 1


    # Accessing dataframes:
    df_study_par = dataframes.get('Study parameters')
    df_co2_costs=dataframes.get('CO2 costs')
    df_co2_em=dataframes.get('CO2 emissions per network')
    df_energy_conversion = dataframes.get('Energy Converter')
    df_generation = dataframes.get('Generation')
    df_storage = dataframes.get('Storage')
    df_loads = dataframes.get('Load Data')
    df_fuels = dataframes.get('Fuels')
    df_obj_function=dataframes.get('Objective')
    df_user_const=dataframes.get('User constraints')
    df_system_connections=dataframes.get('System connections')
    df_evfleet = dataframes.get('EV fleets')

    # Representative days
    rep_days = None
    if df_study_par is not None:
        # Ensure correct columns
        df_study_par.columns = df_study_par.columns.str.strip().str.lower()
        if len(df_study_par) != 1:
            raise ValueError(f"'Study parameters' section must have exactly one row, found {len(df_study_par)}.")
        row = df_study_par.iloc[0]
        # Extract number
        int_rate=float(row['interest rate (%)'])/100 #  converted to fraction
        number = int(row['number of days'])
        n_periods=int(row['periods per day'])
        # Extract representativeness values:
        repr_list = []
        for col in df_study_par.columns:
            if col != 'number of days' and col != 'periods per day' and col != 'interest rate (%)':
                value = row[col]
                if pd.notna(value):
                    try:
                        repr_list.append(float(value)/100) # converts % to fraction
                    except ValueError:
                        continue  # skip non-numeric leftovers
        # Check length and total
        if len(repr_list) != number:
            raise ValueError(f"Expected {number} representative days, but found {len(repr_list)} in row: {repr_list}")
        total = sum(repr_list)
        if abs(total - 1.0) > 1e-9:  # small tolerance for floating point
            raise ValueError(f"The sum of representativeness {total} is not equal to 100 %.")
        dT=24/n_periods
        rep_days = RepDays(n_periods, number, repr_list, dT)


    # Objective
    if df_obj_function is None or df_obj_function.empty:
        raise ValueError("Missing 'Objective' section in CaseData.csv.")

    df_obj_function.columns = df_obj_function.columns.str.strip().str.lower()
    if len(df_obj_function) != 1:
        raise ValueError(f"'Objective' section must have exactly one row, found {len(df_obj_function)}.")

    row = df_obj_function.iloc[0]
    obj = str(row['min_npv || min_co2_em || max_renw_int']).strip().lower()

    mapping = {
        'min_npv': 'Min_NPV',
        'min_co2_em': 'Min_Co2_em',
        'max_renw_int': 'Max_renw_int',
    }

    obj_func = mapping.get(obj)
    if obj_func is None:
        raise ValueError(f"Unsupported objective: {row['min_npv || min_co2_em || max_renw_int']}")


    # User constraints
    max_inv = None
    max_maint = None
    max_co2_em = None
    max_co2_costs = None
    min_renew = None

    if df_user_const is not None and len(df_user_const) > 0:
        df_user_const.columns = df_user_const.columns.str.strip().str.lower()
        row = df_user_const.iloc[0]

        # Because if empy the values are supposed to be None and not NaN
        def get_value(colname):
            if colname in df_user_const.columns:
                val = row[colname]
                return None if pd.isna(val) else val
            return None

        max_inv = get_value('max. investment cost (€)')
        max_maint = get_value('max maintenance costs (€)')
        max_co2_em = get_value('max co2 emissions levels (kg)')
        max_co2_costs = get_value('max co2 emissions costs (€)')
        min_renew_value = get_value('min renewable integration (%)')
        if min_renew_value is None:
            min_renew = None  # keep it None if not set
        else:
            min_renew = min_renew_value / 100
    obj_function = ObjFunc(obj_func, max_inv, max_maint, max_co2_em, max_co2_costs, min_renew)

    # system connections
    system_connections = {}
    if df_system_connections is not None and not df_system_connections.empty:
        df_system_connections.columns = df_system_connections.columns.str.strip().str.lower()
        for _, row in df_system_connections.iterrows():
            net = row['network name']
            tariff_code = row['consumption tariff'].strip()
            remuneration_code = row['injection remuneration'].strip()
            connection = SystemConn(tariff_code, remuneration_code)
            system_connections[net] = connection



    # Map df_fuels to fuels objects
    fuels = []
    if df_fuels is not None:
        df_fuels.columns = df_fuels.columns.str.strip().str.lower()
        for _, row in df_fuels.iterrows():

            id = row['id']
            type = row['type']
            cost = row['cost (€/mwh)']
            avail = row['annual availability (mwh)']
            co2_em = row['co2 emissions(kg/mwh)']
            renew = row['renewable (1 if true)']
            if renew not in (0, 1):
                warnings.warn(f"Warning: renewable flag has unexpected value {renew}. Expected 0 or 1.")

            f = Fuels(id, type, cost, avail, co2_em, renew)
            fuels.append(f)

    # CO2 Parameters
    co2_cost = 0.0  # or None, depending on what CO2Par expects

    if df_co2_costs is not None:
        df_co2_costs.columns = df_co2_costs.columns.str.strip().str.lower()
        if len(df_co2_costs) != 1:
            raise ValueError(f"'CO2 costs' section must have exactly one row, found {len(df_co2_costs)}.")
        row = df_co2_costs.iloc[0]
        co2_cost = float(row['cost (€/kg)'])

    emission_rate = {}
    if df_co2_em is not None:
        df_co2_em.columns = df_co2_em.columns.str.strip().str.lower()
        for _, row in df_co2_em.iterrows():
            net_name = row['network name']
            emission_rate[net_name] = float(row['co2 emissions (kg/mwh)'])

    co2_par = CO2Par(co2_cost, emission_rate)

    # Map df_loads to Load objects
    loads = []
    if df_loads is not None:
        df_loads.columns = df_loads.columns.str.strip().str.lower()
        for _, row in df_loads.iterrows():
            id = row['id']
            connection_point = row['connection point']
            load_type = str(row['type']).strip().lower()
            flexible = str(row['controllable']).strip().upper()
            if flexible in ('0', '0.0', 'NONE', 'NAN'):
                flexible = '0'
            elif flexible not in ('SL', 'TL'):
                warnings.warn(f"Warning: In {id} flexible field must be 0, SL, or TL.")
                flexible = '0'

            R = row['thermal resistance (°c/kw)']
            C = row['thermal capacitance (kwh/°c)']

            # controllable thermal loads
            if flexible == 'TL':
                if not pd.notna(R) or not pd.notna(C):
                    raise ValueError(
                        f"Controllable thermal load '{id}' must have values for thermal resistance and capacitance."
                    )

                # custom case: the column must contain two carrier names separated by 'and'
                thermal_types = [x.strip().lower() for x in load_type.split('and')]
                if len(thermal_types) != 2:
                    raise ValueError(
                        f"Controllable thermal load '{id}' type must present two carriers like 'heat and cool' 'heatX and coolY'."
                    )

                heat_candidates = [x for x in thermal_types if x.startswith('heat')]
                cool_candidates = [x for x in thermal_types if x.startswith('cool')]

                if len(heat_candidates) != 1 or len(cool_candidates) != 1:
                    raise ValueError(
                        f"Controllable thermal load '{id}' must define exactly one heat carrier "
                        f"and one cool carrier, e.g. 'heatX and coolY'."
                    )

                heat_carrier = heat_candidates[0]
                cool_carrier = cool_candidates[0]

                R = R * 1000  # °C/kW -> °C/MW
                C = C / 1000  # kWh/°C -> MWh/°C

                load = Load(
                    id, connection_point, 'thermal', flexible,
                    R, C, heat_carrier=heat_carrier, cool_carrier=cool_carrier
                )

            # ---- non-thermal loads ----
            else:
                # reject multiple types for non-TL loads
                parsed_types = [x.strip().lower() for x in load_type.split('and') if x.strip()]
                if len(parsed_types) > 1:
                    raise ValueError(
                        f"Load '{id}' is not controllable thermal (TL), so it must have only one type. "
                        f"Got: '{load_type}'. Multiple types are only allowed for TL loads."
                    )

                load_type = parsed_types[0] if parsed_types else load_type
                load = Load(id, connection_point, load_type, flexible)

                if pd.notna(R) or pd.notna(C):
                    warnings.warn(
                        f"Warning: Thermal resistance and capacitance apply only to controllable thermal loads "
                        f"and will be ignored for {id}."
                    )

            loads.append(load)



    EVs = []
    if df_evfleet is not None:
        df_evfleet.columns = df_evfleet.columns.str.strip().str.lower()

        mapping = {'CNC': 'CnC', 'SC': 'SC', 'V2G': 'V2G'}
        valid_modes = set(mapping.keys())

        for _, row in df_evfleet.iterrows():
            # Convert EV inputs to model base units: MW and MWh
            id = row['id']
            number = row['number']
            bat_cap = row['battery capacity per ev (kwh)'] / 1000  # kWh to MWh
            p_ch = row['max charging power per ev (kw)'] / 1000  # kW to MW
            p_dch = row['max discharging power per ev (kw), for v2g only'] / 1000  # kW to MW
            daily_use = row['daily energy consumption per ev (kwh)'] / 1000  # kWh to MWh
            ch_eff = row['charging efficiency (%)'] / 100
            dch_eff = row['discharging efficiency (%)'] / 100
            connection_point = row['connection point']
            carrier=row['network name']

            raw_mode = str(row['operation mode (cnc, sc, v2g)']).strip().upper()

            if raw_mode not in valid_modes:
                raise ValueError(
                    f"Invalid operation mode '{row['operation mode (cnc, sc, v2g)']}' for EV fleet '{id}'. "
                    f"Allowed values are: CnC, SC, V2G."
                )

            op_mode = mapping[raw_mode]

            # Check discharging efficiency for V2G
            if op_mode == "V2G":
                if pd.isna(dch_eff) or dch_eff <= 0:
                    raise ValueError(
                        f"EV fleet '{id}' is set to V2G but has invalid discharging efficiency. It must be > 0."
                    )

            ev = EVFleets(id, number, bat_cap, p_ch, p_dch, daily_use, ch_eff, dch_eff, op_mode, connection_point, carrier)
            EVs.append(ev)

    #Energy generators
    generators = []
    if df_generation is not None:
        df_generation.columns = df_generation.columns.str.strip().str.lower()
        for _, row in df_generation.iterrows():
            id = row['id']
            in_sys= row['installed ? ( 1 if already installed in the system)']
            technology = row['technology']
            max_inst = row['max inst. power (mw)']
            connection_point = row['connection point']
            output = row['output energy carrier']
            investment = row['installation (€/mw)']
            maintenance = row['maintenance (€/mw.year)']
            life_time = row['expected life-time']
            local=row['local (assigned load)']

            # Validation for candidates
            if int(in_sys) == 0 and (pd.isna(investment) or pd.isna(maintenance) or pd.isna(life_time)):
                raise ValueError(
                    f"Expected lifetime, investment, and/or maintenance costs for candidate generator '{id}' are missing."
                )

            # validation for assets already installed
            if int(in_sys) == 1:
                if (pd.isna(maintenance)):
                    maintenance=0

            if int(in_sys) == 1:
                if (not pd.isna(investment) and investment != 0) or \
                        (not pd.isna(life_time)):
                    warnings.warn(
                        f"Generator '{id}' is already installed, but has investment ({investment}) or life_time ({life_time}) defined. These values will be ignored."
                    )
                    investment=0
                    life_time=0



            generator = Generation(id,in_sys, technology, max_inst, connection_point, output, investment, maintenance, life_time, local)
            generators.append(generator)

    #Energy converters
    # Map df_energy_conversion to Converters objects
    converters = []
    if df_energy_conversion is not None:
        df_energy_conversion.columns = df_energy_conversion.columns.str.strip().str.lower()
        for _, row in df_energy_conversion.iterrows():
            id = row['id']
            in_sys = row['installed ? ( 1 if already installed in the system)']
            technology = row['technology']
            max_inst = row['max inst. power (mw)']
            connection_point = row['connection point']
            source = row['primary energy source']
            investment = row['installation (€/mw)']
            maintenance = row['maintenance (€/mw.year)']
            life_time = row['expected life-time']
            local=row['local (assigned load)']
            if in_sys==0  and (pd.isna(investment) or pd.isna(maintenance) or pd.isna(life_time)):
                raise ValueError(
                    f" Expected lifetime, investment, and/or maintenance costs for candidate converter {id} are missing."
                )
            # Process outputs
            outputs_raw = str(row['output energy carrier'])
            outputs_split = [o.strip() for o in outputs_raw.split('and')]
            output = outputs_split if len(outputs_split) > 1 else outputs_split[0]

            # Process efficiencies
            efficiencies_raw = str(row['conversion efficiency (%) (or cop)'])
            efficiencies_split = [e.strip() for e in efficiencies_raw.split('and')]
            efficiencies_split = [float(e)/100 for e in efficiencies_split] # converts % to fraction  ( COP in input file must be multiplied by 100)

            # Build efficiency dictionary
            if isinstance(output, list):
                if len(output) != len(efficiencies_split):
                    raise ValueError(
                        f"Mismatch in outputs ({output}) and efficiencies ({efficiencies_split}) for converter {id}"
                    )
                efficiency = dict(zip(output, efficiencies_split))
            else:
                efficiency = {output: efficiencies_split[0]}


            # validation for assets already installed
            if int(in_sys) == 1:
                if ( pd.isna(maintenance)):
                    maintenance = 0

            if int(in_sys) == 1:
                if (not pd.isna(investment) and investment != 0) or \
                        (not pd.isna(life_time)):
                    warnings.warn(
                        f"Converter '{id}' is already installed, but has investment ({investment}) or life_time ({life_time}) defined. These values will be ignored."
                    )
                    investment=0
                    life_time=0


            if len(efficiency) > 1:
                simult = row['simultaneous (only for multiple outputs)']
                converter = Converter(id, in_sys, technology, max_inst, efficiency, connection_point, source, output,  investment, maintenance, life_time, local, simult)
            else:
                converter = Converter(id, in_sys, technology, max_inst, efficiency, connection_point, source, output,  investment, maintenance, life_time, local)

            converters.append(converter)

    #Energy storage devices
    # Map df_storage to Storage objects
    storage_devices = []
    if df_storage is not None:
        df_storage.columns = df_storage.columns.str.strip().str.lower()
        for _, row in df_storage.iterrows():

            id = row['id']
            in_sys = row['installed ? ( 1 if already installed in the system)']
            technology = row['technology']
            max_cap = row['max. capacity (mwh)']
            connection_point = row['connection point']
            in_carrier = row['primary energy carrier']
            out_carrier = row['output energy carrier']
            ch_rate=row['charging rate (mw/mwh)']
            dch_rate=row['discharging rate (mw/mwh)']
            eff_charge=row['charging efficiency (%)']/100  # converts % to fraction
            eff_discharge=row['discharging efficiency (%)']/100  # converts % to fraction
            loss_rate=row['self-discharge (%/hour)']/100  # converts % to fraction
            investment = row['installation (€/mwh)']
            maintenance = row['maintenance (€/mwh.year)']
            life_time = row['expected life-time']
            local=row['local (assigned load)']

            #Validtion for candidates
            if int(in_sys) == 0 and (pd.isna(investment) or pd.isna(maintenance) or pd.isna(life_time)):
                raise ValueError(
                    f"Expected lifetime, investment, and/or maintenance costs for candidate storage device '{id}' are missing."
                )

            # validation for assets already installed
            if int(in_sys) == 1:
                if (pd.isna(maintenance)):
                    maintenance = 0

            if int(in_sys) == 1:
                if (not pd.isna(investment) and investment != 0) or \
                        (not pd.isna(life_time)):
                    warnings.warn(
                        f"Storage device '{id}' is already installed, but has investment ({investment}) or life_time ({life_time}) defined. These values will be ignored."
                    )
                    investment=0
                    life_time=0


            sd = Storage( id,in_sys, technology, max_cap, connection_point,
                 in_carrier, out_carrier, ch_rate, dch_rate,
                 eff_charge, eff_discharge, loss_rate,
                 investment, maintenance, life_time, local)
            storage_devices.append(sd)






    return loads, converters, generators, storage_devices, fuels, rep_days, system_connections, int_rate, co2_par , obj_function, EVs


def ReadRepDays(inputs_folder, loads, generators, rep_days, system_connections, co2_par, EVs):
    folder_path=inputs_folder
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Input folder '{folder_path}' does not exist.")

    for day in range(rep_days.number):
        day_name= str(day + 1)
        with open(folder_path + '/RepDay' + str(day + 1) + '.csv', 'r', encoding='utf-8') as f:
            lines = f.readlines()

        sections = ['Generation', 'Non-Controllable loads', 'Tariffs', 'Network CO2 emissions (kg/MWh)', 'EVs availability (% of EVs connected)', 'EVs use (%)', 'Controllable loads (initial profile)', 'Shiftable loads', 'Thermal Load parameters']
        dataframes = {}

        i = 0
        while i < len(lines):
            line = lines[i].strip().strip(';')  # Ignore extra ;;
            if line in sections:
                section_name = line
                header = lines[i + 1].strip()
                data_lines = []
                i += 2
                while i < len(lines) and lines[i].strip().strip(';') != '':
                    data_lines.append(lines[i])
                    i += 1
                data_str = header + '\n' + ''.join(data_lines)
                df = pd.read_csv(StringIO(data_str), sep=';')
                dataframes[section_name] = df
            else:
                i += 1

        # Accessing dataframes:
        df_loads = dataframes.get('Non-Controllable loads')
        df_generation = dataframes.get('Generation')
        df_tariffs = dataframes.get('Tariffs')
        df_el_net_emissions=dataframes.get('Network CO2 emissions (kg/MWh)')
        df_EVs_avail=dataframes.get('EVs availability (% of EVs connected)')
        df_EVs_use=dataframes.get('EVs use (%)')
        df_floads_p=dataframes.get('Controllable loads (initial profile)')
        df_shift_loads_par=dataframes.get('Shiftable loads')
        df_thermal_loads=dataframes.get('Thermal Load parameters')

        gen_id_rep_day = []
        if df_generation is not None:
            df_generation.columns = df_generation.columns.str.strip().str.lower()
            for _, row in df_generation.iterrows():
                gen_id = row['id']
                gen_id_rep_day.append(gen_id)
                matching = [g for g in generators if g.id == gen_id]
                if not matching:
                    warnings.warn(f"Generator ID '{gen_id}' in RepDay{day+1}.csv not found in system generators.")
                    continue  # skip unknown generators
                g = matching[0]

                profile = []
                for col in df_generation.columns:
                    if col != 'id':
                        value = row[col]
                        if pd.notna(value):
                            try:
                                profile.append(float(value)/100) # converts % to fraction
                            except ValueError:
                                continue  # skip non-numeric leftovers
                # Check length and total
                if len(profile) != rep_days.periods:
                    raise ValueError(
                        f"Expected {rep_days.periods} periods, but found {len(profile)} in generator {gen_id} in day {day} ")
                g.generation_profiles[day] = profile

        for gen in generators:
            if gen.id not in gen_id_rep_day:
                warnings.warn(f"Profile for Generator '{gen.id}' not found in RepDay{day + 1}.csv.")
                continue  # skip unknown generators

        loads_id_rep_day=[]
        if df_loads is not None:
            df_loads.columns = df_loads.columns.str.strip().str.lower()
            # Assign load profiles
            for _, row in df_loads.iterrows():
                load_id = row['id']
                loads_id_rep_day.append(load_id)
                matching = [l for l in loads if l.id == load_id]
                if not matching:
                    continue  # skip unknown loads
                l = matching[0]
                profile = []
                for col in df_loads.columns:
                    if col != 'id':
                        value = row[col]
                        if pd.notna(value):
                            try:
                                profile.append(float(value))
                            except ValueError:
                                continue  # skip non-numeric leftovers
                # Check length and total
                if len(profile) != rep_days.periods:
                    raise ValueError(
                        f"Expected {rep_days.periods} periods, but found {len(profile)} in load {load_id} in day {day} ")
                l.ini_demand_profiles[day] = profile


        if df_floads_p is not None:
            df_floads_p.columns = df_floads_p.columns.str.strip().str.lower()
            # Assign load profiles
            for _, row in df_floads_p.iterrows():
                f_load_id = row['id']
                loads_id_rep_day.append(f_load_id)
                matching = [l for l in loads if l.id == f_load_id]
                if not matching:
                    continue  # skip unknown loads
                l = matching[0]
                profile = []
                for col in df_floads_p.columns:
                    if col != 'id':
                        value = row[col]
                        if pd.notna(value):
                            try:
                                profile.append(float(value))
                            except ValueError:
                                continue  # skip non-numeric leftovers
                # Check length and total
                if len(profile) != rep_days.periods:
                    raise ValueError(
                        f"Expected {rep_days.periods} periods, but found {len(profile)} in load {f_load_id} in day {day} ")
                l.ini_demand_profiles[day] = profile

        for load in loads:
            if load.id not in loads_id_rep_day and load.flexible!= 'TL':
                warnings.warn(f"Profile for Load '{load.id}' not found in RepDay{day + 1}.csv.")
                continue


        f_loads_parm_id_rep_day=[]
        if df_shift_loads_par is not None:
            df_shift_loads_par.columns = df_shift_loads_par.columns.str.strip().str.lower()
            # Assign load profiles
            for _, row in df_shift_loads_par.iterrows():
                f_load_id = row['id']
                f_loads_parm_id_rep_day.append(f_load_id)
                max_adv = row['max. advance (n periods)']
                max_delay = row['max. delay (n periods)']
                matching = [l for l in loads if l.id == f_load_id]
                if matching:
                    l = matching[0]
                    l.max_adv[day] = max_adv
                    l.max_delay[day] = max_delay

        for load in loads:
            if load.flexible == 'SL' and load.id not in f_loads_parm_id_rep_day:
                warnings.warn(f"Parameters for Shiftable Load '{load.id}' not found in RepDay{day + 1}.csv.")
                continue

        th_load_rep_day = []
        if df_thermal_loads is not None:
            df_thermal_loads.columns = df_thermal_loads.columns.str.strip().str.lower()
            # Assign load profiles
            for _, row in df_thermal_loads.iterrows():
                th_load_id = row['id']
                th_load_rep_day.append(th_load_id)
                temp_min = row['t min ( ºc)']
                temp_max = row['t max ( ºc)']
                matching = [l for l in loads if l.id == th_load_id]
                if matching:
                    l = matching[0]
                    l.temp_min[day] = temp_min
                    l.temp_max[day] = temp_max
                    profile = []
                    for col in df_thermal_loads.columns:
                        if col != 'id' and col != 't min ( ºc)' and col != 't max ( ºc)':
                            value = row[col]
                            if pd.notna(value):
                                try:
                                    profile.append(float(value))
                                except ValueError:
                                    continue  # skip non-numeric leftovers
                    # Check length and total
                    if len(profile) != rep_days.periods:
                        raise ValueError(
                            f"Expected {rep_days.periods} periods, but found {len(profile)} in load {th_load_id} temperature profile in day {day} ")
                    l.temp_out[day] = profile

        for load in loads:
            if load.flexible == 'TL' and load.id not in th_load_rep_day:
                warnings.warn(f"Parameters for Thermal Load '{load.id}' not found in RepDay{day + 1}.csv.")
                continue

        co2em_id_rep_day = []
        if df_el_net_emissions is not None:
            df_el_net_emissions.columns = df_el_net_emissions.columns.str.strip().str.lower()

            for _, row in df_el_net_emissions.iterrows():
                co2em_id = row['network name']
                co2em_id_rep_day.append(co2em_id)

                if co2em_id not in system_connections:
                    warnings.warn(
                        f"Network name '{co2em_id}' in RepDay{day + 1}.csv not found in system connections."
                    )
                    continue

                profile = []
                for col in df_el_net_emissions.columns:
                    if col != 'network name':
                        value = row[col]
                        if pd.notna(value):
                            try:
                                profile.append(float(value))
                            except ValueError:
                                continue

                if len(profile) != rep_days.periods:
                    raise ValueError(
                        f"Expected {rep_days.periods} periods for Net emissions, but found {len(profile)} in day {day + 1}"
                    )

                if co2em_id in co2_par.emissions_rate:
                    warnings.warn(
                        f"'{co2em_id}' network CO2 emissions rate replaced by profile defined in rep. day {day_name}."
                    )
                    del co2_par.emissions_rate[co2em_id]

                if co2em_id not in co2_par.emissions_profile:
                    co2_par.emissions_profile[co2em_id] = {}

                co2_par.emissions_profile[co2em_id][day] = profile




        # Tariffs
        tariff_rep_day={}
        if df_tariffs is not None:
            df_tariffs.columns = df_tariffs.columns.str.strip().str.lower()
            tariff_rep_day={}
            for _, row in df_tariffs.iterrows():
                tariff_id = row['id']
                profile = []
                for col in df_tariffs.columns:
                    if col != 'id':
                        value = row[col]
                        if pd.notna(value):
                            try:
                                profile.append(float(value))
                            except ValueError:
                                continue  # skip non-numeric leftovers
                # Check length and total
                if len(profile) != rep_days.periods:
                    raise ValueError(f"Expected {rep_days.periods} periods, but found {len(profile)} in tariff  {tariff_id} in day {day+1} ")

                tariff_rep_day[tariff_id]= profile


        for carrier, car in system_connections.items():
            # Handle tariff
            if car.tariff_code in tariff_rep_day:
                car.tariff[day] = tariff_rep_day[car.tariff_code]
            else:
                warnings.warn(
                    f"Tariff for network consumed energy ({carrier}) with code {car.tariff_code} doesn't exist on day {day + 1}"
                )

            # Handle remuneration price
            if car.remuneration_code in tariff_rep_day:
                car.remuneration_price[day] = tariff_rep_day[car.remuneration_code]
            else:
                warnings.warn(
                    f"Remuneration tariff for network injected {carrier} with code {car.remuneration_code} doesn't exist on day {day + 1}"
                )

        avail_id_rep_day=[]
        if df_EVs_avail is not None:
            df_EVs_avail.columns = df_EVs_avail.columns.str.strip().str.lower()
            # Assign load profiles
            for _, row in df_EVs_avail.iterrows():
                avail_id = row['id']
                avail_id_rep_day.append(avail_id)
                matching = [ev for ev in EVs if ev.id == avail_id]
                if not matching:
                    continue  # skip unknown EV ids
                ev = matching[0]
                profile = []
                for col in df_EVs_avail.columns:
                    if col != 'id':
                        value = row[col]
                        if pd.notna(value):
                            try:
                                profile.append(float(value)/100)
                            except ValueError:
                                continue  # skip non-numeric leftovers
                # Check length and total
                if len(profile) != rep_days.periods:
                    raise ValueError(
                        f"Expected {rep_days.periods} periods, but found {len(profile)} in EV availibility profile {avail_id} in day {day} ")
                ev.avail_profile[day] = profile

        EV_use_rep_day = []
        if df_EVs_use is not None:
            df_EVs_use.columns = df_EVs_use.columns.str.strip().str.lower()
            for _, row in df_EVs_use.iterrows():
                EV_use_id = row['id']
                EV_use_rep_day.append(EV_use_id)
                matching = [ev for ev in EVs if ev.id == EV_use_id]
                if not matching:
                    continue  # skip unknown EV ids
                ev = matching[0]
                profile = []
                for col in df_EVs_use.columns:
                    if col != 'id':
                        value = row[col]
                        if pd.notna(value):
                            try:
                                profile.append(float(value)/100)
                            except ValueError:
                                continue  # skip non-numeric leftovers
                # Check length
                if len(profile) != rep_days.periods:
                    raise ValueError(
                        f"Expected {rep_days.periods} periods, but found {len(profile)} in EV battery use profile {EV_use_id} in day {day} ")
                ev.EV_use_prof [day] = profile

                # Check that the profile sums to 100
                if abs(sum(profile) - 1) > 1e-4:
                    raise ValueError(
                        f"EV battery use profile {EV_use_id} in day {day} must sum to 100, but sums to {sum(profile)*100:.2f}"
                    )

        for ev in EVs:

            if ev.id not in avail_id_rep_day:
                raise ValueError(
                    f"Availability profile for EV '{ev.id}' not found in RepDay{day + 1}.csv."
                )

            if ev.id not in EV_use_rep_day:
                raise ValueError(
                    f"EV use profile for EV '{ev.id}' not found in RepDay{day + 1}.csv."
                )

    # Final validation: every system connection must have CO2 data
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
            "Missing CO2 emissions data for network(s): " +
            ", ".join(missing_co2) +
            ". Each system connection must have either a constant CO2 emissions rate "
            "in CaseData.csv or a daily profile in all RepDay files."
        )

    if incomplete_profiles:
        details = "; ".join(
            f"{net}: missing day(s) {days}"
            for net, days in incomplete_profiles.items()
        )
        errors.append(
            "Incomplete CO2 emissions profiles for network(s): " + details
        )

    if errors:
        raise ValueError("\n".join(errors))

