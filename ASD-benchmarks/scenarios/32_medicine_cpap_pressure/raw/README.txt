


'ProcessedDataset'
Folder contains processed data from pressure & flow sensor array (PSD / PQ), Electrical Impedance Tomography (EIT), Electrocardiogram (ECG), Photoplethysmogram (PPG), and Heart-rate belt (HRB).
Files are saved in these folders by subject number ('01' through to '20') and test type (e.g. Subject 1 files are as follows: 'ProcessedData_Subject01_PEEP.csv'; 'ProcessedData_Subject01_PEEP_BH.csv', and 'ProcessedData_Subject01_FEM.csv').
Test type suffixes correspond to incremented increasing PEEP ('_PEEP'), incremented increasing PEEP with breath holds ('_PEEP_BH'), and forced expiratory manoeuvre ('_FEM'). 
These files contain data in columns (A:R): 
	'PSD Time [s]' - Pressure sensor data time array [s]
	'PSD Gauge Pressure [cmH2O]' - Gauge pressure sensor data [cmH2O]
	'PSD Inspiratory Differential Pressure [cmH2O]' - Inspiratory differential pressure sensor data [cmH2O]	
	'PSD Expiratory Differential Pressure [cmH2O]' - Expiratory differential pressure sensor data [cmH2O]	
	'PSD Flow [L/s]' - Flow from combined inspiratory and expiratory differential pressure sensor data [cmH2O]	
	'PSD Tidal Volume [L]' - Tidal volume based on inspiratory indices and flow data [L]	
	'PSD Inspiratory Indicies' - Identified inspiratory indicies (based on identified gauge pressure inflection points) 
	'EIT Time [s]' - EIT time array [s]	
	'EIT Global Aeration' - EIT global aeration array
	'ECG Time [s]' - ECG time array [s]	
	'ECG [mV]' - ECG data array [mV]	
	'PPG Time [s]' - PPG time array [s]			
	'PPG0' - PPG data array from first LED array
	'PPG1' - PPG data array from second LED array	
	'PPG2' - PPG data array from third LED array
	'HRB Time [s]' - HRB time array [s]	
	'HRB Heartrate [bpm]' - HRB Heartrate [bpm]
	'HRB RR Interval [ms]' - HRB RR Interval [ms]
With the exception of subjects 1 & 2 who do not have recorded heart-rate belt data and so only have data in columns (A:O)


 
'PQ_rawData'
Folder contains raw data and raw data with units processed from the pressure & flow sensor array.
Files with relevant units are saved in these folders by subject number and test type (e.g. Subject 1 files are as follows: 'Subject1_PEEP.csv'; 'Subject1_PEEP_BH.csv', and 'Subject1_FEM.csv').
These files contain data in columns (A:E): 
	'Time [s]' - Pressure sensor data time array [s]
	'Gauge Pressure [cmH2O]' - Gauge pressure sensor data [cmH2O]
	'Inspiratory Differential Pressure [cmH2O]' - Inspiratory differential pressure sensor data [cmH2O]	
	'Expiratory Differential Pressure  [cmH2O]' - Expiratory differential pressure sensor data [cmH2O]	
	'StartTime' - Recording start time saved in 'HH:mm:ss' format
Files with raw ADC counts are saved similarly in these folders by subject number and test type with the added suffix '_raw' (e.g. Subject 1 files are as follows: 'Subject1_PEEP_raw.csv'; 'Subject1_PEEP_BH_raw.csv', and 'Subject1_FEM_raw.csv').
These files contain data in columns (A:E): 
	'Time [s]' - Pressure sensor data time array [s]
	'Gauge Pressure' - Gauge pressure sensor data [ADC]
	'Inspiratory differenrtial pressure' - Inspiratory differential pressure sensor data [ADC]
	'Expiratory differenrtial pressure' - Expiratory  differential pressure sensor data [ADC]
	'StartTime' - Recording start time saved as in DateNumber format (datenum(t), where t was saved in 'dd-mmm-yyyy HH:MM:SS' format)


'EIT_rawData'
Folder contains raw data from EIT (Electrical Impedance Tomography).
Files are saved in these folders by subject number ('01' through to '20') and test type (e.g. Subject 1 files are as follows: 'S01_PEEP.bin'; 'S01_PEEP_BH.bin', and 'S01_FEM.bin').
These files contain data as a matrix of pixel values representing regional aeration for a cross-sectional image (32x32 frame) over time (with 50Hz sampling).


'HRM_rawData'
Folder contains raw data from heart-rate monitoring systems (ECG, PPG, and HRB).
Files are saved in the following subfolders accordingly: 'ECG'; 'PPG'; 'HRB'.  
The 'ECG' (Electrocardiogram) folder contains files 
These files contain data in columns (A:B)
	'Time' - ECG data time array in 'HH:mm:ss.SSS' format	
	'ECG(mV)' - ECG data array [mV]
The 'PPG' (Photoplethysmogram) folder contains files 
These files contain data in columns (A:D)
	'Time' - PPG data time array in 'HH:mm:ss.SSS' format
	'PPG0' - PPG data array from first LED array
	'PPG1' - PPG data array from second LED array	
	'PPG2' - PPG data array from third LED array
The 'HRB' (Heart-rate belt) folder contains files by subject number (e.g. Subject 3 file is '3.txt'), HRB data was not collected for subjects 1 and 2.
These files contain comma separated data:
	'Time' - HRB data time array in 'HH:mm:ss.SSSSSS''Z' format
	'msgid' - HRB data message ID array
	'rr_ms' - HRB RR interval data array
	'hr_bpm' - HRB heart-rate data array


'subject-info.csv'
File contains the relevant self-reported demographic/medical information for the 20 subjects, as well as measured chest width and depth.
	Columns A to E (General Information) respectively contain: Subject Number, Sex [M/F], Height[cm], Weight [kg], and Age [years]. 
	Columns F to H (Thoracic Dimensions) respectively contain: Bra Size (if applicable), Back Size [mm], Sternum to spine size [mm].
	Columns I to K (Asthma History) respectively contain: Asthma (Y/N), Medication,	Dosage Frequency (units included in column value).
	Columns M to P (Smoking History) respectively contain: History of Smoking (Y/N), Current Smoker (Y/N), How long since you quit smoking (units included in column value), Smoking Frequency (units included in column value), and Time as a smoker (units 		included in column value).
	Columns Q to U (Vaping History) respectively contain: History of Vaping (Y/N), Current Vaper (Y/N), How long since you quit vaping (units included in column value), Vaping Frequency (units included in column value), Time as a vaper (units included 		in column value). 


'Figure1.png' is an example plot of the processed dataset for subject 3 incremented increasing PEEP test 
'Figure2.png' is an example plot of the processed dataset for subject 3 incremented increasing PEEP with breath holds test
'Figure3.png' is an example plot of the processed dataset for subject 3 forced expiratory manoeuvre test 


'Code'
Folder contains MATLAB code, used in data collection, processing, and visualisation.
	'DataCollection_PQ.m' - collects PQ data
	'DataProcessing.m' - combines and processes pressure & flow sensor array, EIT, ECG, PPG, and HRB data to generate 'ProcessedDataset' files
	'read_binData.m' - function to read EIT device ('bin') files 
	'FigureGeneration.m' - generates example plots (e.g. 'Figure1.png' , 'Figure2.png', 'Figure3.png') of dataset by subject and test type 

 