'''
================================================================================
DIGITAF PROJECT — OPEN ACCESS DATA METHODOLOGY
--------------------------------------------------------------------------------
This processing script was developed as part of the DigitAF EU Project 
to advance open science and robust data provenance.

ACKNOWLEDGEMENT:
This code was co-created and optimized with the assistance of AI (Gemini) 
to transform legacy, human-centric spreadsheet data into an efficient, 
highly scalable, split-tabular JSON data representation. This migration reduced 
the storage footprint by over 98.8% (from 25MB to 300KB), optimizing the dataset 
for high-throughput computational workflows and machine readability.
================================================================================
'''

import pandas as pd
import json

# This python code was made 


excel_file = "DigitAF_Soil_All_LLs_Data.xlsx"

# 1. Standard Dataset Metadata
title_text = "Methods to Verify and Account for the Carbon and Soil Health Benefits of Agroforestry"

dataset_metadata = {
    "DOI": "https://doi.org/10.5281/zenodo.21204617",
    "title": "Methods to Verify and Account for the Carbon and Soil Health Benefits of Agroforestry",
    "project": "DIGITAF",
    "description": "This dataset contains the data from a soil health assessment across eight sites in seleceted Living Lab farms in Portugal, Finland, Spain, Italy, United Kingdom, the Netherlands, Czechia and Germany. In all sites, a consistent set of four parameters of soil health were measured, which are also required within the UKCEH Soil Health Tool (UKCEH, 2024). The four parameters are the level of soil organic matter (or soil organic carbon), the level of acidity (pH, in water and KCl), the soil bulk density, and the number of earthworms. Measurements of the effect of agroforestry on soil health parameters were completed following a common protocol (Aynekulu et al., 2026, annexed to the DigitAF deliverable 3.5 report by den Herder et al .2026). However in some sites, the protocol was modified to accommodate the differences in agroforestry system design, soil type, and in some cases to allow direct comparisons with previous measurements. Hence the detailed sampling protocols are described for each of the eight sites and can be found in den Herder et al. (2026), and the metadata sheets for each country.",
    "global_references": [
        "Aynekulu, E., Cumplido-Marin, L., Burgess, P., & den Herder, M. (2026). Monitoring Soil Health in Agroforestry Systems: A Guide to Assessment. DigitAF EU Project. https://doi.org/10.5281/zenodo.20529901",
        "den Herder, M. et al. (2026). Methods to Verify and Account for the Carbon and Soil Health Benefits of Agroforestry. DigitAF EU Project. https://doi.org/10.5281/zenodo.20529635",
        "UK Centre for Ecology and Hydrology (UKCEH) (2024a) Countryside Survey Soil Health Webtool SOil funDamentals (SOD). https://connect-apps.ceh.ac.uk/soilhealth/"
    ]
}
site_metadata = {
    "Portugal": {
        "location": "MVARC, Moinhos de Vento de Baixo, Mértola, Portugal",
        "contact": "Jo Smith, josmith@mvarc.eu",
        "sampling_date": "6-10th May 2025",
        "experimental_design": "A nested design was used with 'Treatment' at the highest level. Bulk density was measured once at each point on the transect. A rigid cylinder was used.",
        "site_image": "portugal_site_map.png",
        "methodology_notes": {
            "stones_pct": "Percentage of the soil core (by weight) composed of particles greater than 2mm.",
            "ph": "Soil pH was measured with a glass electrode (soil:water 1:2.5) pH meter.",
            "carbon_nitrogen": "Aliquots of 10g of soil were ground in a ball mill and then analyzed.",
            "soc_stocks_formula": "Soil carbon stock (t/ha) = BD (Bulk density in g/cm3) * % SOC (as a decimal) * D (depth in cm) * 100"
        }
    },
    "Finland": {
        "location": "Sammallahden tila, Liperi, Pohjois-Karjala, Finland",
        "contact": "Michael den Herder, michael.denherder@efi.int",
        "sampling_date": "26-28.2025, 30.5.2025, 2.6.2025",
        "experimental_design": "To explore the effects of agroforestry management on soil health, soil samples were taken in three treatments using a stratified random sampling design: Permanent grass (grazed), forest grazing/wood pasture (grazed), forest (ungrazed). In each treatment 10 points were sampled. For permanent grass, two fields were sampled separately because of different grazing regimes (sheep vs cows). Samples divided into two depths at 0-20 cm and 20-40 cm.",
        "site_image": "finland_site_map.png",
        "coordinate_system": "EPSG:4326 - WGS84 Lat Lon in decimal degrees",
        "methodology_notes": {
            "sampling_tool": "Auger with a diameter of 2.4 cm and a length of 40 cm. 5 sub-samples mixed in a bucket and analyzed as one.",
            "bulk_density": "Steel cylinder of 5 cm diameter and 10 cm height (volume 196.35 cm3). Undisturbed sample collected, sun-dried for two weeks until constant mass, and expressed in g/cm3.",
            "earthworms": "Counted from a cube of soil to a depth of 20 cm from the surface and measuring 20 cm x 20 cm x 20 cm.",
            "stones_pct": "Percentage of the soil core (by weight) composed of clay (<0.002 mm), silt (0.002-0.05 mm), sand (0.05-2 mm) and particles greater than 2mm.",
            "ph": "pH measured in water and KCl.",
            "carbon_nitrogen_equipment": "Aliquots of 10g of soil were ground in a ball mill and then analyzed in the DUMATHERM® N Pro analyzer (C. Gerhardt GmbH & Co. Germany) to determine %C (SOC) and %N (TN).",
            "soc_stocks_formula": "Soil carbon stock (t/ha) = BD (Bulk density in g/cm3) * % SOC (as a decimal) * D (soil depth in cm) * 100"
        }
    },
    "Spain": {
        "location": "Majadas de Tiétar, Spain",
        "contact": "Victor Rolo, rolo@unex.es",
        "sampling_date": "May-25",
        "experimental_design": "The sampling design followed an individual isolated tree framework, where the influence of an isolated tree is assessed. Six central trees were selected. In each central tree, three samples were collected: one located under its canopy, half-way from the tree trunk to the drip line of the canopy, and two samples beyond the tree canopy, varying, in general, on open pasture.",
        "site_image": "spain_site_map.png",
        "coordinate_system": "Original: EPSG:25830 - ETRS89 / UTM zone 30N. Transformed to EPSG:4326 - WGS84 Lat Lon in decimal degrees.",
        "methodology_notes": {
            "soil_sampling_and_bulk_density": "Soil samples were taken at each point at a depth of 30 cm with an undisturbed liner soil sampler (Eijkelkamp) with a bayonet connection allowing PVC liner 50 mm in diameter. Intact samples were divided into 0-5, 5-10, 10-20 and 20-30 cm layers. Oven dried until constant weight and sieved at 2 mm. Bulk density calculated for each layer as ratio between mass of dry soil and sampled volume.",
            "stones_pct": "Percentage of the soil core (by weight) composed of particles greater than 2mm.",
            "ph": "Soil pH was measured with a glass electrode (soil:water 1:2.5) pH meter (CRISON Basic20, Alella, Spain).",
            "carbon_nitrogen_equipment": "Aliquots of 10g of soil were ground in a ball mill and then analyzed in the DUMATHERM® N Pro analyzer (C. Gerhardt GmbH & Co. Germany) to determine %C (SOC) and %N (TN).",
            "soc_stocks_formula": "Soil carbon stock (t/ha) = BD (Bulk density in g/cm3) * % SOC (as percent) * D (soil depth in cm)",
            "earthworms": "Number of earthworms in soil volume of 20 x 20 x 20 cm.",
            "additional_metrics": {
                "basal_respiration": "µg CO2-C g-1 soil h-1",
                "msir": "µg CO2-C g-1 soil h-1",
                "shannon": "Shannon diversity index"
            }
        }
    },
    "Italy": {
      "location": "Arnino Long-term experiment, Italy",
      "contact": "Contact details pending verification",
      "sampling_date": "May-25",
      "experimental_design": "Long-term monitoring matrix split across specialized alley-cropping agroforestry plots (Tree Lines) and standard arable control plots.",
      "site_image": "italy_site_map.png",
      "coordinate_system": "EPSG:4326 - WGS84 Lat Lon in decimal degrees",
      "methodology_notes": {
        "sampling_depth": "Surface horizon sampling focused on comparative soil quality impacts adjacent to established agroforestry tree rows.",
        "soil_health_parameters": "Standard screening including active indicators, soil reaction baseline, and structural stability values."
      }
    },
    "United Kingdom": {
      "location": "Clapham Park, United Kingdom",
      "contact": "Contact details pending verification",
      "sampling_date": "18th September 2025",
      "experimental_design": "Multi-system comparison evaluating three distinct open pasture regimes (Standard Pasture, Silvopasture row modifications, and adjacent Farm Woodlands) and an older, dense Mature Woodland baseline footprint.",
      "site_image": "uk_site_map.png",
      "coordinate_system": "EPSG:4326 - WGS84 Lat Lon in decimal degrees",
      "methodology_notes": {
        "sampling_protocol": "Standardized core Extractions matching the UKCEH Soil Health Tool criteria for open pasture, timber corridors, and reference canopy soils.",
        "biomass_indicators": "Macrofauna abundance counting (earthworms) integrated with baseline carbon monitoring vectors."
      }
    },
    "the Netherlands": {
      "location": "Tussen de Hagen, the Netherlands",
      "contact": "Contact details pending verification",
      "sampling_date": "1st October 2025",
      "experimental_design": "Transect monitoring grid explicitly mapped out relative to windbreak hedgerow distance vectors. Samples are structurally coded by orientation and distance (e.g., 'W10' for 10 meters West of the tree line, 'O5' for 5 meters East).",
      "site_image": None,
      "coordinate_system": "EPSG:4326 - WGS84 Lat Lon in decimal degrees",
      "methodology_notes": {
        "transect_coding": "Coded fields represent exact distance zones relative to the hedge center (West = W, East = O/Oost) to map microclimate and root-zone soil chemistry changes.",
        "macrofauna_sampling": "Earthworm count records taken across the distance plots to measure biodiversity variations near tree corridors."
      }
    },
    "Czechia": {
        "location": "Jagava and Šardice, Czechia",
        "contact": None,
        "sampling_date": None,
        "experimental_design": None,
        "site_image": None
    },
    "Germany": {
        "location": "Domin’s Farm Peickwitz, Germany",
        "contact": None,
        "sampling_date": None,
        "experimental_design": None,
        "site_image": None
    }
}

# Read the soil data sheet
df = pd.read_excel(excel_file, sheet_name="Data Ph, C, Bulk density, worms")

# Map your Excel headers to short, clean machine keys
rename_dict = {
    "Sample ID": "sample_id",
    "Country": "country",
    "Living Lab name": "living_lab_name",
    "Soil sample Nr": "soil_sample_nr",
    "Transect": "transect",
    "Field ID": "field_id",
    "Treatment cod": "treatment_code",
    "Treatment": "treatment",
    "Sampling date": "sampling_date",
    "Agroforestry practi": "agroforestry_practice",
    "Age of practice": "age_of_practice_years",
    "Sample depth (c": "sample_depth_cm",
    "Lat": "latitude",
    "Long": "longitude",
    "Elevation (m a": "elevation_m_asl",
    "pH/H2O": "ph_h2o",
    "pH/KCl": "ph_kcl",
    "differenc": "ph_difference",
    "Bulk density (g/cm3)": "bulk_density_g_cm3",
    "N (%)": "nitrogen_pct",
    "Corg (%)": "organic_carbon_pct",
    "C stocks (t/ha)": "carbon_stocks_t_ha",
    "Nr of earthworms (nr) Spring 2025": "earthworms_count_spring_2025",
    "Earthworm weight (gr fresh weight)": "earthworms_weight_g_spring_2025",
    "Nr of earthworms (nr) Autumn 2025": "earthworms_count_autumn_2025",
    "Nr of earthworms (nr) March 2026": "earthworms_count_march_2026",
    "Clay (%)": "clay_pct",
    "Silt (%)": "silt_pct",
    "Sand (%)": "sand_pct",
    "Course > 2mm (%)": "coarse_fragments_greater_2mm_pct"
}
df = df.rename(columns=rename_dict)

# Match up columns present in the dataframe with our clean map
existing_columns = [col for col in rename_dict.values() if col in df.columns]
df = df[existing_columns]

# 5. Extract Tabular Structure using Pandas 'split' option (removes nested repetition)
tabular_data = json.loads(df.to_json(orient="split", date_format="iso"))

# Clean up index overhead metadata generated natively by pandas split
if "index" in tabular_data:
    del tabular_data["index"]

# 6. Build the Final Single Compressed Document
final_json = {
    "dataset_metadata": dataset_metadata,
    "site_metadata": site_metadata,
    "soil_data": tabular_data
}

# 7. Export JSON
output_filename = "digitaf_soil_dataset_final.json"
with open(output_filename, "w", encoding="utf-8") as f:
    json.dump(final_json, f, indent=2, ensure_ascii=False)

print(f"Success! Highly efficient file saved as '{output_filename}'. Ready for Zenodo upload.")