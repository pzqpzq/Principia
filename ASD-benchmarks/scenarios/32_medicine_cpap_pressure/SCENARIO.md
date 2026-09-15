# P100-032: CPAP respiratory pressure measurements

How do pressure settings affect respiratory dynamics across trials?

Source: https://www.physionet.org/content/respiratory-heartrate-dataset/1.0.0/

Version: 1.0.0; 2024-03-20

Measurement coverage: PhysioNet version 1.0.0 published 2024-03-20; StartTime fields preserve per-trial acquisition timestamps.

Data origin: measured_or_observed

Source processing: Raw sensor/ADC exports require the source calibration code to interpret pressure/flow. Separate source processed tables, EIT and HRM are deliberately excluded. No calibration was applied during collection.

Interpretation limits: Source Code documents sensor conversions and experimental protocols. PEEP settings and maneuver names are not independent subjects. Resistance/compliance may not both be identifiable without defensible flow reconstruction and timing. Raw pressure recordings and calibration/context for 60 trials; pressure-only inference requires identifiable physiological assumptions.

Terms: CC BY 4.0
