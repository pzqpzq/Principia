import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

def calculate_correlations(dfs, location, weather_location):
    production_df = dfs[location].copy()  
    weather_df = dfs[f'{weather_location}_weather'].copy()
    
    production_df['Date'] = pd.to_datetime(production_df['Date'], errors='coerce')
    weather_df['time'] = pd.to_datetime(weather_df['time'], errors='coerce')
    
    # Drop rows with NaT values that couldn't be parsed
    production_df = production_df.dropna(subset=['Date'])
    weather_df = weather_df.dropna(subset=['time'])
    
    # Merge the DataFrames based on closest date match
    merged_df = pd.merge_asof(production_df.sort_values('Date'), weather_df.sort_values('time'),
                              left_on='Date', right_on='time', direction='nearest')
    
    # Check if the merged dataframe is empty or all zeros
    if merged_df.empty or merged_df['Produced Energy (kWh)'].sum() == 0:
        print(f"No valid data to plot for {location}. Skipping.")
        return
    
    # Drop non-numeric columns (like Date, time) for correlation calculation
    numeric_cols = merged_df.select_dtypes(include='number').columns
    # Remove specific energy production column from the list
    numeric_cols = numeric_cols.drop('Specific Energy (kWh/kWp)', errors='coerce')
    merged_numeric = merged_df[numeric_cols]
    
    # Calculate correlations
    correlations = merged_numeric.corr()
    
    plt.figure(figsize=(12, 10), dpi=300)
    sns.set(font_scale=1.1)
    sns.heatmap(correlations, annot=True, cmap='magma', vmin=-1, vmax=1, fmt='.2f', linewidths=1, linecolor='white',
                annot_kws={"size": 10, "weight": "bold", "color": 'black'})
    plt.title(f'Correlation Matrix for Weather Features vs. Produced Energy in {location}', fontsize=16)
    plt.xticks(rotation=45, ha='right', fontsize=12)
    plt.yticks(rotation=0, fontsize=12)
    plt.tight_layout()
    plt.show()


def plot_3d_energy_production(df, plant_name):
    df['Date'] = pd.to_datetime(df['Date'])

    df['Month'] = df['Date'].dt.month
    df['Hour'] = df['Date'].dt.hour

    # Group by hour and month, and calculate the average energy produced
    average_energy = df.groupby(['Hour', 'Month'])['Produced Energy (kWh)'].mean().reset_index().astype(float)
    hour = average_energy['Hour']
    month = average_energy['Month']
    energy = average_energy['Produced Energy (kWh)']

    # Creating meshgrid for Hour and Month
    hour_grid, month_grid = np.meshgrid(np.unique(hour), np.unique(month))

    # Reshape energy data to match the shape of the meshgrid
    energy_grid = np.zeros_like(hour_grid, dtype=float)
    for i in range(len(hour)):
        h_idx = np.where(np.unique(hour) == hour[i])[0][0]
        m_idx = np.where(np.unique(month) == month[i])[0][0]
        energy_grid[m_idx, h_idx] = energy[i]

    fig = plt.figure(figsize=(12, 8), dpi=300)
    ax = fig.add_subplot(111, projection='3d')
    surf = ax.plot_surface(hour_grid, month_grid, energy_grid, cmap='viridis')

    ax.set_xlabel('Hour')
    ax.set_ylabel('Month')
    ax.set_zlabel('Produced Energy (kWh)')
    ax.set_title(f'Average Energy Production by Hour and Month - {plant_name}')

    fig.colorbar(surf)
    plt.show()




def plot_daily_energy_trends_combined(dfs):
    plt.figure(figsize=(15, 8), dpi = 300)
    
    for plant_name, df in dfs.items():
        df['Date'] = pd.to_datetime(df['Date'])
        
        df['Day_of_Year'] = df['Date'].dt.dayofyear
        
        daily_energy = df.groupby('Day_of_Year')['Produced Energy (kWh)'].sum().reset_index()
        
        sns.lineplot(x='Day_of_Year', y='Produced Energy (kWh)', data=daily_energy, label=plant_name)
    
    plt.title('Daily Energy Production Trends for All PV Locations')
    plt.xlabel('Day of the Year')
    plt.ylabel('Produced Energy (kWh)')
    plt.legend(title='PV Location')
    plt.grid(True)
    plt.show()


