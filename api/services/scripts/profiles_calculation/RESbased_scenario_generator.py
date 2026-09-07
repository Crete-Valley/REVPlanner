# -*- coding: utf-8 -*-
"""
Dependencies:
    Pending to update
Created on July 2026

@author: Iciar Bernal Peña
License: GNU GPLv3
The GNU General Public License is a free, copyleft license for software and other kinds of works.
https://www.gnu.org/licenses/gpl-3.0.html
You may copy, distribute and modify the software as long as you track changes/dates in source files.
 Any modifications to or software including (via compiler) GPL-licensed code must also be made 
 available under the GPL along with build & install instructions. 
 This means, you must:
     - Include original
     - State Changes
     - Disclose source
     - Include the same license -- to make sure it remains free software for all its users.
     - Include copyright
     - Include install instructions 
     
You cannot: sublicense or hold liable.

Copyright @CARTIF 2026

"""
import os
import pandas as pd
import json
import requests
import geopandas as gpd
from shapely import wkt
from shapely.geometry import shape
from shapely.ops import unary_union, transform
import pyproj
import pvlib
from pvlib.location import Location
from api.constants import SRID, THERMAGRID_API_KEY, THERMAGRID_API_URL
from api.services.scripts.profiles_calculation.Electricity_profiles import Electricity_demand_calculation as el
from api.services.scripts.profiles_calculation.wind_module import generate_wind_profile
building_use_mapping = {
        1: "residential",  # residential
        2: "residential",  # residential
        3: "residential",  # residential
        4: "office",  # office
        5: "commerce",  # commerce
        6: "education",  # education
}

def calculate_areas(geojson_file):
    """
    Calculate the area of each polygon in a GeoJSON file.

    Parameters:
    geojson_object (str): Path to the GeoJSON file containing polygons.

    Returns:
    dict: A dictionary with polygon indices as keys and their respective areas as values.
    """

    areas = {}
    community_demand = []
    
    for i, feature in enumerate(geojson_file['features']):
        geom = shape(feature['geometry'])
        # Definir la proyección de origen (WGS84)
        wgs84 = pyproj.CRS("EPSG:4326")

        # Definir una proyección métrica adecuada, 3857 por ej.
        projected_crs = pyproj.CRS("EPSG:3857")

        # Transformar a sistema métrico
        project = pyproj.Transformer.from_crs(wgs84, projected_crs, always_xy=True).transform
        geom_projected = transform(project, geom)

        # Calcular área en metros cuadrados
        area = geom_projected.area
        height = feature['properties']['height']
        building_demand = {
            'id': feature['id'],
            'heating': feature['properties']['heating'],
            'cooling': feature['properties']['cooling'],
            'dhw': feature['properties']['dhw']
        } 
        areas[i] = area
        community_demand.append(building_demand)
    return areas, community_demand


def fetch_geojson(geojson_object, inputs_thermagrid=None):
    """Send the generated demand payload to the Thermagrid API."""
    api_url = THERMAGRID_API_URL
    api_key = str(THERMAGRID_API_KEY)

    if not api_url or not api_key:
        raise RuntimeError(
            "THERMAGRID_API_URL and THERMAGRID_API_KEY must be configured "
            "as environment variables before running demand_calculation()."
        )

    if inputs_thermagrid is None:
        inputs_thermagrid, _solar_profile, _wind_power = generate_demand_inputs(
            geojson_object=geojson_object
        )

    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key,
    }
    params_json = json.dumps(inputs_thermagrid, indent=2)
    response = requests.post(api_url, data=params_json, headers=headers, timeout=None)
    response.raise_for_status()
    return response.json()

def demand_thermagrid(front_data, geojson_file):
    """
    Reads demand data from a file and generates a demand profile for each user profile in the list.

    Parameters:
    data (dict): Dictionary containing the API request payload.
    front_data (list): List of dictionaries containing user profile data.

    Returns:
    list: List of generated demand profiles.
    """
    areas, community_demand = calculate_areas(geojson_file=geojson_file)

    demand_profiles = []
    buildings_id = 0
    
    for buildings in front_data:
        common_profile = buildings["common_profile"]
        occupants = buildings["occupants"]
        answer = {}

        if common_profile == 1: # STUDENTS # CHR01
            answer = {
                "usuario": {
                    "number_of_family_members": occupants,
                    "number_of_people_working": occupants,
                    "number_of_people_students": None,
                    "number_of_people_retired": None,
                    "number_of_toddler": None,
                    "number_of_children": None,
                    "number_of_adult_young": occupants,
                    "number_of_adult": None,
                    "number_of_senior": None
                }
            }
        elif common_profile == 2: # ADULT COUPLE # CHR02
            answer = {
                "usuario": {
                    "number_of_family_members": occupants,
                    "number_of_people_working": occupants,
                    "number_of_people_students": None,
                    "number_of_people_retired": None,
                    "number_of_toddler": None,
                    "number_of_children": None,
                    "number_of_adult_young": None,
                    "number_of_adult": occupants,
                    "number_of_senior": None
                }
            }
        elif common_profile == 3: # FAMILY WITH KIDS # CHR44
            answer = {
                "usuario": {
                    "number_of_family_members": occupants,
                    "number_of_people_working": 2,
                    "number_of_people_students": (occupants - 2),
                    "number_of_people_retired": None,
                    "number_of_toddler": None,
                    "number_of_children": (occupants - 2),
                    "number_of_adult_young": None,
                    "number_of_adult": 2,
                    "number_of_senior": None
                }
            }
        elif common_profile == 4: # RETIRED COUPLE # CHR16
            answer = {
                "usuario": {
                    "number_of_family_members": occupants,
                    "number_of_people_working": None,
                    "number_of_people_students": None,
                    "number_of_people_retired": occupants,
                    "number_of_toddler": None,
                    "number_of_children": None,
                    "number_of_adult_young": None,
                    "number_of_adult": None,
                    "number_of_senior": occupants
                }
            }

        # Generate electricity profile
        route_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Electricity_profiles")

        route_jsons = os.path.join(route_base, "Unique_Usuarios")
        route_csvs = os.path.join(route_base, "Electricity_Profiles_LPG_Hourly")
        profile = el.lpg_electricity_profile_generator(ruta_jsons=route_jsons, ruta_csvs=route_csvs, answer=answer)
        electricity_profile_df = profile.to_frame(name='electricity_demand')
        electricity_profile = electricity_profile_df['electricity_demand'].tolist()
        
        demand_profile = {
            "demand_profile": {
                "id": community_demand[buildings_id]['id'],  # Use the ID from community_demand
                "heating_demand": community_demand[buildings_id]['heating'],
                "cooling_demand": community_demand[buildings_id]['cooling'],
                "dhw_demand": community_demand[buildings_id]['dhw'],
                "electricity_demand": electricity_profile,
            }
        }
        buildings_id += 1
        demand_profiles.append(demand_profile)
    return demand_profiles

def generate_demand_inputs(geojson_object):
    """
    Calculate temperatures and radiations based on TMY data and return a JSON with 
    the original GeoJSON, temperatures, and radiations.

    Parameters
    ----------
    geojson_input : dict
        The GeoJSON object containing the multipolygons.

    Returns
    -------
    dict
        A dictionary containing the original GeoJSON, temperatures, and calculated radiations.
    """
    URL = 'https://re.jrc.ec.europa.eu/api/v5_3/'

    # Calculate the centroid of the provided multipolygons
    multipolygons = [shape(feature['geometry']) for feature in geojson_object['features']]
    union_multipolygon = unary_union(multipolygons)
    centroid = union_multipolygon.centroid
    longitude, latitude = centroid.x, centroid.y
    
    #------------------------------------------------------
    # ASSUMES INPUT AND OUTPUT CRS IS EPSG 4326
    # IF NOT, IT MUST BE MODIFIED
    #------------------------------------------------------

    print("\n·····························")
    print("** LOCATION SUMMARY **")
    print("·····························")
    print(f"centroid: {centroid}")
    print(f"latitude: {latitude}")
    print(f"longitude: {longitude}")

    # Call PVGIS API (with pvlib) to get TMY data
    tmy_data, meta = pvlib.iotools.get_pvgis_tmy(
        latitude,
        longitude,
        map_variables=False,
        url=URL
    )

    tmy_data.index = pd.to_datetime(tmy_data.index)

    site = Location(latitude, longitude)

    # Get solar data
    solar_position = site.get_solarposition(times=tmy_data.index)

    # Define orientations of vertical surfaces
    orientations = {
        'rad_n': 0,
        'rad_s': 180,
        'rad_e': 90,
        'rad_o': 270
    }

    # Tilt angle (90 degrees for vertical surfaces)
    tilt_angle = 90

    # Create the output dictionary (json)
    inputs_thermagrid = {
        "geojson": geojson_object,  # Provided GeoJSON
        "temperature": tmy_data['T2m'].tolist()  # Temperature list
    }
    irradiance_by_orientation = {}

    for orientation_name, azimuth_angle in orientations.items():

        irradiance = pvlib.irradiance.get_total_irradiance(
            surface_tilt=tilt_angle,
            surface_azimuth=azimuth_angle,
            solar_zenith=solar_position["apparent_zenith"],
            solar_azimuth=solar_position["azimuth"],
            dni=tmy_data["Gb(n)"],
            ghi=tmy_data["G(h)"],
            dhi=tmy_data["Gd(h)"],
        )

        irradiance_by_orientation[orientation_name] = irradiance

        inputs_thermagrid[orientation_name] = (
            irradiance["poa_global"].tolist()
        )

    # South-facing irradiation already calculated
    south_irradiance = irradiance_by_orientation["rad_s"]

    # Solar production normalised to 1 kWp
    solar_profile = (
        south_irradiance["poa_global"] / 1000
    ).tolist()

    wind_power = generate_wind_profile(
        latitude,
        longitude,
        year=2023
    )

    return (
        inputs_thermagrid,
        solar_profile,
        wind_power
    )

def generate_geojson(front_data):
    """
    Generates a GeoJSON object from the input data and saves it to the 'outputs' folder.

    Parameters:
    front_data (list): A list of dictionaries containing building information.

    Returns:
    dict: A GeoJSON object with the building information.
    """
    gdf = gpd.GeoDataFrame(front_data)
    gdf["geometry"]=gdf["geom"].apply(wkt.loads)
    gdf.set_geometry("geometry")
    gdf.drop("geom",axis=1)
    gdf.set_crs(epsg=SRID, inplace=True)
    gdf["id"] = range(1, len(gdf) + 1)
    gdf["use"] = gdf["building_use_id"].map(building_use_mapping)
    gdf["height"] = 6
    gdf["year"] = gdf["construction_year"]
    gdf["heating_system"] = 1
    gdf["cooling_system"] = 2

    return json.loads(gdf.to_json())

