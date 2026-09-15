import pandas as pd
import plotting_functions


# Function to read CSV files with error handling
def read_csv_with_handling(file_path):
    try:
        df = pd.read_csv(file_path, delimiter=',', on_bad_lines='skip')
    except pd.errors.ParserError as e:
        print(f"Error reading {file_path}: {e}")
        return None
    return df


# Replace 'PV Plants Datasets.xlsx' with the path to your Excel file
file_path = 'PV Plants Datasets.xlsx'

# Define the correspondence table between sheet names and real names
correspondence = {
    'Lisbon_1': ['84071567'],
    'Lisbon_2': ['84071569'],
    'Lisbon_3': ['84071570'],
    'Lisbon_4': ['62032213'], 
    'Setubal': ['84071568'],
    'Faro': ['84071566'],
    'Braga': ['62030198'],
    'Tavira': ['73060645'],
    'Loule': ['73061935']
}

# Read each sheet into a pandas DataFrame and rename them accordingly
dfs = {}
for real_name, sheet_names in correspondence.items():
    for sheet_name in sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        dfs[real_name] = df

# Now, dfs contains DataFrames named according to the correspondence table
# Each DataFrame's name is in the format "real_name"
# You can access them using the DataFrame name, like dfs['Lisbon_1'], dfs['Lisbon_2'], etc.

# Read the CSV files for each location and add them to the dictionary
weather_file_template = '{}_weather.csv'
for location in ['Lisbon', 'Setubal', 'Faro', 'Braga', 'Tavira', 'Loule']:
    file_path = weather_file_template.format(location)
    weather_df = read_csv_with_handling(file_path)
    if weather_df is not None:
        dfs[f'{location}_weather'] = weather_df



lisbon_locations = ['Lisbon_1', 'Lisbon_2', 'Lisbon_3', 'Lisbon_4']
for location in lisbon_locations:
    plotting_functions.calculate_correlations(dfs, location, 'Lisbon')

# For other locations, use their specific weather data
other_locations = ['Setubal', 'Faro', 'Braga', 'Tavira', 'Loule']
for location in other_locations:
    plotting_functions.calculate_correlations(dfs, location, location)

plotting_functions.plot_daily_energy_trends_combined(dfs)

for plant_name, df in dfs.items():
    plotting_functions.plot_3d_energy_production(df, plant_name)