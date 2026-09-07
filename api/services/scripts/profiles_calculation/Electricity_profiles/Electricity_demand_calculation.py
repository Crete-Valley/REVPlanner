# -*- coding: utf-8 -*-
"""
Created on Thu Feb 22 13:51:16 2024

Vincenzo Ezio Santovito
@author: vinsan

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

Copyright @CARTIF 2024
"""

import json
import pandas as pd
import numpy as np
import os
import random

# Function to compare the UI usuario answer and those from LPG in the case of no exact match
def are_dicts_similar(dict1, dict2, threshold):
    '''
   This function compares two dictionaries to determine their similarity based on common key-value pairs.

   Parameters
   ----------
   dict1 : dict
       The first dictionary for comparison.
   dict2 : dict
       The second dictionary for comparison.
   threshold : int
       The threshold of similarity, indicating the minimum number of common elements.

   Returns
   -------
   bool
       True if the number of common elements is equal to or greater than the threshold, False otherwise.
   '''
    common_elements = sum(1 for key, value in dict1.items() if key in dict2 and dict2[key] == value)
    return common_elements >= threshold


def lpg_electricity_profile_generator(ruta_jsons, ruta_csvs, answer):
    '''
    This function generates an electricity consumption profile based on user input and available data.

    Parameters
    ----------
    ruta_jsons : str
        The path to the folder containing JSON files with household specifications.
    ruta_csvs : str
        The path to the folder containing CSV files with electricity consumption profiles.
    answer : dict
        A dictionary representing user input specifying household characteristics.

    Returns
    -------
    np.array
        An array representing the electricity consumption profile.

    Notes
    -----
    This function attempts to match the user input with available household specifications and assigns the corresponding electricity consumption profile.
    If no exact match is found, it offers three options:
    1. Assign a random profile from available data.
    2. Assign the closest matching profile.
    3. Assign the average of all available profiles.
    '''
    usuarios = {}
    demandas = {}

    json_files = [archivo for archivo in os.listdir(ruta_jsons) if archivo.endswith('.json')]
    csv_files = [archivo for archivo in os.listdir(ruta_csvs) if archivo.endswith('.csv')]
    
    # Storing all the households in a proper dictionary
    for json_file in json_files:
        with open(os.path.join(ruta_jsons,json_file)) as file:
            usuario = json.load(file)                    #.json of a specific household
            json_name = os.path.splitext(json_file)[0]   #.json file name without the extension
            usuarios[json_name] = usuario                # Dictionary containing all the types of households (The key is CHR_)
    
    # Storing all the Electricity Consumption Profiles in a dictionary of dataframes in which the access key is the household ID
    for csv_file in csv_files:
        demanda = pd.read_csv(os.path.join(ruta_csvs, csv_file))
        csv_name = os.path.splitext(csv_file)[0]
        demandas[csv_name] = demanda
    

    profile = np.zeros(8760)
    n = 0
    
    for key1,value1 in usuarios.items():
        for key2,value2 in demandas.items():
            if key1 == answer:
                profile = demandas[key2]['Consumption [kWh]']
                
    if profile.sum() == 0:  # This means the assignment did not work as no available usuario matches the answer from the UI
            #Option1 - Random profile
            profile = random.choice(list(demandas.values()))['Consumption [kWh]']
            
            #Option2 - Similar profile
            for key1,value1 in usuarios.items():
                if are_dicts_similar(answer,value1,4) and value1["number_of_family_members"] == answer["number_of_family_members"]:
                    profile = demandas[key1]
                
            #Option3 - Average of all profiles
            for key in demandas:
                profile = profile + demandas[key]['Consumption [kWh]']
                n = n+1
            profile = profile/n
            
    return profile    