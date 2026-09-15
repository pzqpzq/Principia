# P100-033: Smartphone PPG with ECG reference and acquisition disturbances

How do acquisition conditions affect pulse-signal quality and measurement error?

Source: https://www.physionet.org/content/butppg/2.0.0/

Version: 2.0.0; 2024-08-23

Measurement coverage: August 2020–December 2021 observations; source version 2.0.0 published 2024-08-23.

Data origin: measured_or_observed

Source processing: PPG was extracted from smartphone video; signals were manually synchronized and segmented by source authors. PPG 30 Hz, ECG 1,000 Hz, ACC 100 Hz per documentation. The package is not raw video.

Interpretation limits: The database was designed for PPG quality and heart-rate evaluation and has existing published analyses. Source quality flags mark some recordings unreliable; they are retained. Segments from a participant are strongly dependent; clinical deployment is outside acquisition acceptance. Read-only checks found 48 ECG and 48 PPG headers declaring a single frame with 10,000 or 300 channels, respectively; the other 3,840 recordings use conventional multiframe layouts. Header/data byte lengths and all 27,125 publisher-listed member hashes match. Preserve this source orientation difference. BUT smartphone PPG/WFDB and annotations; processed/reference products have distinct roles.

Terms: CC BY 4.0
