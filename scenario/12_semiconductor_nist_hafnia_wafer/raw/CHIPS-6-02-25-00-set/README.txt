NIST Data Publication:
Nanometer-Scale Planar Reference Materials Project data: Year: 2025
Set: 00, ~10nm Hafnia on Silicon, deposited via ALD on 200mm wafers.
Version 1.0.0
DOI: https://doi.org/10.18434/mds2-3930


Authors:
  Donald A Windover
    National Institute of Standards and Technology
    Materials Measurement Science Division
  Justin M Gorham
    National Institute of Standards and Technology
    Materials Measurement Science Division
  Chris Yung
    National Institute of Standards and Technology
    Applied Physics Division

Contact:
  Donald Windover
    donald.windover@nist.gov


Description:

Data directory name:  "CHIPS-6-02-25-00-set"

Material under study: 

Set contains twelve, 200 mm wafers, each with 65 cycles of
atomic layer deposition of hafnia, using an Arradiance Gemstar XT ALD System, 
Serial Number: 08.164310262022.

Blank Si wafers purchased from WaferPro: [Part
No:  F08041], SEMI standard, 200 mm, SSP, Prime, Float Zone, (100) orientation,
with backside laser mark. The wafers were left with native silicon oxide from
production, and were deposited during four days, after 2 hour instrument
temperature stability warm ups, and approximately 3 seconds per cycle, and with
three wafers loaded in top, middle, and bottom locations during each deposition.
This deposition approach should provide four correlated sets of deposition.
This should allow us to do run-to-run sister wafer correlations for the top,
middle, and bottom of our deposition system. 

Deposition #1 on 2025/06/25
included wafers: 25-01 (top of chamber), 25-02 (middle of chamber), 25-03
(bottom of chamber). Deposition #2 on 2025/06/27 included wafers: 25-04 (top of
chamber), 25-05 (middle of chamber), 25-06 (bottom of chamber). Deposition #3 on
2025/06/30 included wafers: 25-07 (top of chamber), 25-08 (middle of chamber),
25-09 (bottom of chamber). Deposition #4 on 2025/07/02 included wafers: 25-10
(top of chamber), 25-11 (middle of chamber), 25-12 (bottom of chamber).

Wafers 25-02 (#1, middle), 24-04 (#2, top), 25-08 (#3, middle), & 25-12 (#4,
bottom) were selected to be diced at a future date. All data contained in this
first data release are from whole wafer measurements.

Measurements in this first release: This repository contains the X-ray
reflectometry (XRR) and variable wavelength spectroscopic ellipsometry (SE) from
twelve, 200mm wafers.

Spectroscopic Ellipsometry (SE): SE was collected using a J.A. Woolam M-2000 DI
Spectroscopic Ellipsometer, Serial Number: 1212020.

A full wafer map of SE was taken for the four wafers, which are to be diced and
distributed as pieces to the semiconductor community.  SE scans of all remaining
whole wafers is planned for a future release.  

X-ray reflectivity (XRR):  XRR was collected using a Rigaku SmartLab 9kW Cu rotating
anode Instrument with a Graded parabolic mirror, a Ge 220 x 2 bounce monochromator, 
and a HyPix 3000 detector, Serial Number: BD73000647-01.

Nine, XRR measurements are taken
for each of the four wafers, which are to be diced.  These data sets are taken
at the center of each wafer and at +/- 52.5 mm from the center in all quadrant
directions.  The XRR data will be used to reduce the uncertainty within the SE
data sets provided.  

Preliminary XRR scans have been taken on the remaining
eight wafers, with a more detailed mapping planned for a future release.  Both
the whole wafers and the diced portions will be available for distribution
within the semiconductor community via the NIST Office of Reference Materials as
a future research grade test material.


-------------------
General Information
-------------------

Data files are named by wafer number (Example, 25-01) and wafer location 
(Example -105 (center).


Key funding sources: This work was performed with funding from the CHIPS Metrology Program, 
part of CHIPS for America, National Institute of Standards and Technology, U.S. Department of Commerce.

--------------
Data Use Notes
--------------

This data is publicly available according to the NIST statements of
copyright, fair use and licensing; see
https://www.nist.gov/director/copyright-fair-use-and-licensing-statements-srd-data-and-software

You may cite the use of this data as follows:
Windover, Donald A, Gorham, Justin M, Yung, Chris (2025), CHIPS 6.02 -
Nanometer-Scale Planar Reference Materials Project data: Year: 2025 Set: 00,
~10nm Hafnia on Silicon, deposited via ALD on 200mm wafers., Version 1.0.0,
National Institute of Standards and Technology,
https://doi.org/10.18434/mds2-3930 (Accessed: [give download date])

----------
References
----------

##
# List any other relevant references, including related data publications
# and ancillary data.
##
-------------
Data Overview
-------------

Data files are named by wafer number (Example, 25-01) and wafer location (Example -105 (center).

Data file types present in the data repository:

XRR file types
CHIPS-6-02-25-WAFER#-POSITION-DATE.rasx (Binary file format proprietary to Rigaku (https://rigaku.com/) which are saved during data collection)
CHIPS-6-02-25-WAFER#-POSITION-DATE.ras (Readable space delimited files converted using Rigaku file converter, which is used by existing NIST data conversion routines.

Note:  Within the *.ras file, we can find instrument parameters used for data collection.  
Relevant optics configuration is read from this file and will appear in the title of generated data in the data\interim directory in a future release.

SE file types
CHIPS-6-02-25-WAFER#-full.SE (Binary file proprietary to J.A. Woollam (https:\\www.jawoollam.com))
CHIPS-6-02-25-WAFER#-105.txt (space delimited data file with the first 7 columns as: 
"Wavelength (nm), Psi (65.00, 70.00, 75.00°), Delta (65.00, 70.00, 75.00°)"
Preliminary analysis files included, with a Cauchy single layer assumption, and fitting between 300nm to 1000nm using "CompleteEASE, Version: 5.23, By J.A. Woollam)
CHIPS-6-02-25-WAFER#-full.rtf (Wafer map of model parameter variation in Cauchy single layer model)
CHIPS-6-02-25-WAFER#-parameters.csv (Optimized results for Spectroscopic model parameters with columns as:
"X (cm),Y (cm),MSE,Absolute MSE,Thickness # 1 (nm),A,B,C,n of Cauchy @ 632.8 nm,Thickness # 1 (nm) Error,A Error,B Error,C Error,n of Cauchy @ 632.8 nm Error"



##################################################
## CHIPS-6-02-25-22 series repository structure ##
##################################################

CHIPS-6-02-25-00-deposition-matrix.png (diagram showing all 12 wafers over the four deposition dates)
\25-01 (all measurements & analysis on wafer 25-01)
CHIPS-6-02-25-01-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-02 (all measurements & analysis on wafer 25-02)
CHIPS-6-02-25-02-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-02d (all measurements & analysis on wafer 25-02, post dicing)
\25-03 (all measurements & analysis on wafer 25-03)
CHIPS-6-02-25-03-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-04 (all measurements & analysis on wafer 25-04)
CHIPS-6-02-25-04-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-04d (all measurements & analysis on wafer 25-04, post dicing)
\25-05 (all measurements & analysis on wafer 25-05)
CHIPS-6-02-25-05-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-06 (all measurements & analysis on wafer 25-06)
CHIPS-6-02-25-06-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-07 (all measurements & analysis on wafer 25-07)
CHIPS-6-02-25-07-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-08 (all measurements & analysis on wafer 25-08)
CHIPS-6-02-25-08-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-08d (all measurements & analysis on wafer 25-08, post dicing)
\25-09 (all measurements & analysis on wafer 25-09)
CHIPS-6-02-25-09-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-10 (all measurements & analysis on wafer 25-10)
CHIPS-6-02-25-10-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-11 (all measurements & analysis on wafer 25-11)
CHIPS-6-02-25-11-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-12 (all measurements & analysis on wafer 25-12)
CHIPS-6-02-25-12-measurements-DATE.png (diagram of all measurements on the wafer, as of date)
\25-12d (all measurements & analysis on wafer 25-12, post dicing)
\Production-details (instrument alignment files and configuration information)

\25-01\
\25-01\data (all data files from measurements)
\25-01\data\raw (original data files)
\25-01\data\raw\xrr (xrr data files from the instrument - currently from 5 locations)
XRR measurements at:  25-01-105,-202,-224, & -245
Measurements taken on:  2025/06/26

\25-02\
\25-02\data (all data files from measurements)
\25-02\data\raw (original data files)
\25-02\data\raw\se (SE measurements at the center of each dicing dimension)
Whole wafer SE file & wafer center txt file
Preliminary analysis files included, with a Cauchy single layer assumption, and fitting between 300nm to 1000nm
Measurements taken at:  2025/07/16

\25-02\data\raw\xrr (xrr data files from the instrument - currently from 9 locations)
XRR measurements at:  25-02-105, & -224,
Measurements taken on:  2025/06/26
XRR measurements at:  25-02-202,-245, & -263,
Measurements taken on:  2025/07/08
XRR measurements at:  25-02-302,-324,-343, & -361
Measurements taken on:  2025/07/15

\25-03\
\25-03\data (all data files from measurements)
\25-03\data\raw (original data files)
\25-03\data\raw\xrr (xrr data files from the instrument - currently from 5 locations)
XRR measurements at:  25-03-105, & -224
Measurements taken on:  2025/06/26
XRR measurements at:  25-03-202,-245, & -263
Measurements taken on:  2025/07/15

\24-04\
\25-04\data (all data files from measurements)
\25-04\data\raw (original data files)
\25-04\data\raw\se (SE measurements at the center of each dicing dimension)
Whole wafer SE file & wafer center txt file
Preliminary analysis files included, with a Cauchy single layer assumption, and fitting between 300nm to 1000nm
Measurements taken at:  2025/07/15

\25-04\data\raw\xrr (xrr data files from the instrument - currently from 9 locations)
XRR measurements at:  25-02-105, & -224,
Measurements taken on:  2025/07/01
XRR measurements at:  25-02-202,-245, & -263,
Measurements taken on:  2025/07/08
XRR measurements at:  25-02-302,-324,-343, & -361
Measurements taken on:  2025/07/16

\25-05\
\25-05\data (all data files from measurements)
\25-05\data\raw (original data files)
\25-05\data\raw\xrr (xrr data files from the instrument - currently from 5 locations)
XRR measurements at:  25-05-105, & -224
Measurements taken on:  2025/07/01
XRR measurements at:  25-05-202,-245, & -263
Measurements taken on:  2025/07/15

\25-06\
\25-06\data (all data files from measurements)
\25-06\data\raw (original data files)
\25-06\data\raw\xrr (xrr data files from the instrument - currently from 2 locations)
XRR measurements at:  25-06-105, & -224
Measurements taken on:  2025/07/01

\25-07\
\25-07\data (all data files from measurements)
\25-07\data\raw (original data files)
\25-07\data\raw\xrr (xrr data files from the instrument - currently from 2 locations)
XRR measurements at:  25-07-105, & -224
Measurements taken on:  2025/07/01

\24-08\
\25-08\data (all data files from measurements)
\25-08\data\raw (original data files)
\25-08\data\raw\se (SE measurements at the center of each dicing dimension)
Whole wafer SE file & wafer center txt file
Preliminary analysis files included, with a Cauchy single layer assumption, and fitting between 300nm to 1000nm
Measurements taken at:  2025/07/17

\25-08\data\raw\xrr (xrr data files from the instrument - currently from 9 locations)
XRR measurements at:  25-08-105, & -224,
Measurements taken on:  2025/07/01
XRR measurements at:  25-08-202,-245, & -263,
Measurements taken on:  2025/07/08
XRR measurements at:  25-08-302,-324,-343, & -361
Measurements taken on:  2025/07/16

\25-09\
\25-09\data (all data files from measurements)
\25-09\data\raw (original data files)
\25-09\data\raw\xrr (xrr data files from the instrument - currently from 2 locations)
XRR measurements at:  25-09-105
Measurements taken on:  2025/07/01
XRR measurements at:  25-09-224
Measurements taken on:  2025/07/03

\25-10\
\25-10\data (all data files from measurements)
\25-10\data\raw (original data files)
\25-10\data\raw\xrr (xrr data files from the instrument - currently from 2 locations)
XRR measurements at:  25-10-105, & -224
Measurements taken on:  2025/07/03

\25-11\
\25-11\data (all data files from measurements)
\25-11\data\raw (original data files)
\25-11\data\raw\xrr (xrr data files from the instrument - currently from 2 locations)
XRR measurements at:  25-11-105, & -224
Measurements taken on:  2025/07/03

\24-12\
\25-12\data (all data files from measurements)
\25-12\data\raw (original data files)
\25-12\data\raw\xrr (xrr data files from the instrument - currently from 9 locations)
XRR measurements at:  25-12-105, &-202,-224,-245, & -263,
Measurements taken on:  2025/07/03
XRR measurements at:  25-12-302,-324,-343, & -361
Measurements taken on:  2025/07/16

---------------
Version History
---------------

1.0.0 (this version)
  initial release