import requests
import pandas as pd
from windpowerlib import WindTurbine, ModelChain
import os

def extraer_curva_powerlib(nombre_turbina, path_csv=None):
    if path_csv is None:
        path_csv = os.path.join(os.path.dirname(__file__), "power_curves.csv")
    
    df = pd.read_csv(path_csv)
    df = df[df["turbine_type"] == nombre_turbina]
    if df.empty:
        raise ValueError(f"Turbina '{nombre_turbina}' no encontrada.")
    
    df_t = df.drop(columns="turbine_type").T.reset_index()
    df_t.columns = ["wind_speed", "value"]
    df_t["wind_speed"] = df_t["wind_speed"].astype(float)
    df_t["value"] = df_t["value"].astype(float) / 1000.0  # W → kW
    return df_t.dropna().sort_values("wind_speed")

def get_openmeteo_weather(lat, lon, year=2024, altura=100):
    url = "https://archive-api.open-meteo.com/v1/archive"
    var_viento = f"wind_speed_{altura}m"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "hourly": f"temperature_2m,{var_viento},pressure_msl",
        "timezone": "Europe/Madrid"
    }
    # Request weather data from the API
    resp = requests.get(url, params=params)
    data = resp.json()["hourly"]
    df = pd.DataFrame(data)

    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    return df.rename(columns={var_viento: "wind_speed"})

def simulate_wind_power(df_weather, curve_name="E48/800", altura_datos=100, hub_height=60, rugosidad=0.4, path_csv=None):
    df_meteo = pd.DataFrame(index=df_weather.index)
    df_meteo[("wind_speed", altura_datos)] = df_weather["wind_speed"]
    df_meteo[("temperature", "")] = df_weather["temperature_2m"]
    df_meteo[("pressure", "")] = df_weather["pressure_msl"] * 100
    df_meteo[("roughness_length", "")] = rugosidad
    df_meteo.columns = pd.MultiIndex.from_tuples(df_meteo.columns)

    # Load the turbine curve and define the turbine characteristics
    curva = extraer_curva_powerlib(curve_name, path_csv)
    turbina = WindTurbine(name=curve_name, hub_height=hub_height, power_curve=curva)

    # Run the windpowerlib simulation
    mc = ModelChain(turbina)
    mc.run_model(df_meteo)

    return mc.power_output  # returns power in kW

def apply_efficiencies(series_kw, n_turbines=1, wake_loss=0.05, eta_mec=0.98, eta_conv=0.96, disponibilidad=0.98, perdidas_red=0.01):
    factor = (1 - wake_loss) * eta_mec * eta_conv * disponibilidad * (1 - perdidas_red)
    return series_kw * n_turbines * factor

def generate_wind_profile(lat, lon, year=2024, curve="E48/800", altura_datos=100, hub_height=60, rugosidad=0.4, pot_nom_kw=800):
    try:
        # 1) Download weather data
        df_weather = get_openmeteo_weather(lat, lon, year, altura=altura_datos)

        # 2) Simulate gross turbine output
        potencia_bruta = simulate_wind_power(df_weather, curve_name=curve, altura_datos=altura_datos, hub_height=hub_height, rugosidad=rugosidad)

        # 3) Apply efficiency correction
        potencia_neta = apply_efficiencies(potencia_bruta)

        # 4) Normalize by nominal power to get a [0–1] profile
        perfil_unitario = (potencia_neta / pot_nom_kw).clip(0, 1)

        return perfil_unitario.fillna(0).tolist()
    except Exception as e:
        print(f"Error generating realistic wind simulation: {e}")
        return [0] * 8760         # Return an empty zero profile in case of failure
