# Local-Data Evaluation Corpus

This directory contains exactly 20 newly installed, source-grounded evaluation scenarios plus the pre-existing `TJ-SHD` folder. The 20 new scenarios contain 493 files and 800,637,339 bytes (763.547 MiB). Every scenario passed the manifest, checksum, archive-safety, scientific-format, and folder-contract checks recorded in `VALIDATION_REPORT.json`.

The installed total is 0.801 decimal GB, below the planning estimate of 0.9-1.1 GB. This reflects the current byte sizes of the locked deterministic selections; no unrelated or duplicated data were added merely to inflate the corpus.

## Folder contract

Each new scenario contains `SCENARIO.md`, `USER_BRIEF.txt`, `PROVENANCE.json`, `SHA256SUMS`, `raw/`, and `context/`.

- `raw/` contains official downloaded bytes. No scientific values were normalized, imputed, filtered, converted, or replaced with derived findings.
- `context/` contains official manifests, codebooks, schemas, API responses, layouts, or source metadata.
- `USER_BRIEF.txt` is generated simulation context and is never scientific evidence.
- `PROVENANCE.json` uses `principia.local-scenario/v1` and records source, version, license/access, deterministic selection, exclusions, ethics restrictions, file roles, byte sizes, SHA-256, MIME type, URLs, and transport notes.


## Corpus catalog

| Scenario | Domain | MiB | Publisher |
|---|---:|---:|---|
| `01_mathematics_oeis_daily_sequences` | mathematics | 37.624 | OEIS Foundation Inc. |
| `02_astronomy_mast_tars_sector96` | astronomy | 2.404 | Space Telescope Science Institute / MAST |
| `03_physics_gwosc_o4a_h1_strain` | physics | 123.244 | Gravitational Wave Open Science Center |
| `04_particle_physics_atlas_4lep_2015` | particle physics | 82.331 | CERN Open Data / ATLAS Collaboration |
| `05_biology_geo_gse303208_multiomics` | biology | 47.755 | NCBI Gene Expression Omnibus |
| `06_physics_nist_rydberg_rf_sensing` | atomic physics | 43.032 | National Institute of Standards and Technology |
| `07_neuroscience_physionet_gait_s1` | neuroscience | 37.391 | PhysioNet |
| `08_medical_imaging_tcia_ea1141` | medical imaging | 57.118 | The Cancer Imaging Archive / NCI Imaging Data Commons |
| `09_neuroscience_dandi_001176` | neuroscience | 29.522 | DANDI Archive |
| `10_computer_security_nvd_recent_snapshot` | cybersecurity | 20.043 | National Institute of Standards and Technology / NVD |
| `11_ai_mlperf_inference_v6_0` | artificial intelligence | 1.146 | MLCommons |
| `12_semiconductor_nist_hafnia_wafer` | semiconductors | 139.261 | National Institute of Standards and Technology |
| `13_materials_nist_encapsulant_cure` | materials science | 5.084 | National Institute of Standards and Technology |
| `14_sociology_census_htops_2026` | sociology | 37.769 | U.S. Census Bureau |
| `15_economics_federal_reserve_shed_2025` | economics | 5.288 | Board of Governors of the Federal Reserve System |
| `16_economics_bls_cpi_ces_2026` | economics | 14.240 | U.S. Bureau of Labor Statistics |
| `17_geography_usgs_comcat_2026_07` | geography | 7.806 | U.S. Geological Survey |
| `18_climate_noaa_storm_events_2025` | climate | 13.493 | NOAA National Centers for Environmental Information |
| `19_transport_nhtsa_safety_2025_2026` | transportation | 44.623 | National Highway Traffic Safety Administration |
| `20_ocean_noaa_coral_ssta_20260816` | oceanography | 14.373 | NOAA Coral Reef Watch |



## Scientific and ethics boundary

This corpus supports hypothesis generation. No observed pattern should be described as novel until it has exact file/row/time provenance, units and computation, uncertainty, missingness and confounder analysis, falsifiers and negative evidence, comparison with the source publication, robustness checks, and a current literature novelty review.

Human data are public and deidentified. Re-identification is prohibited. Controlled/private data and credentials are absent. License and redistribution terms remain scenario-specific; this local R&D corpus should not be automatically bundled into a commercial distribution.


