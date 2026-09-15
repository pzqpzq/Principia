%% Data Collection for MAY 2023 Trial 
% Ella Guy 
% Last Updated: 30MAR2023

% Data from arduino serial to MATLAB
% Scales data into pressure [Pa] and circumference [mm]
% Saves outfile as a .mat file 

clc, clear all, close all

%% Initialisation

% Trial Information =======================================================
timeLength = 60; % (T1 350, T2 350, T3 60) recording length of the trial

% Inputs-------------------------------------------------------------------
SubjectNumber = ;      % de-identifyed subject number
TestNumber = ;         % test type

Width_chest = ; % [cm]
Depth_chest = ; % [cm]
%--------------------------------------------------------------------------

% Make sure to plug in data collection system before tape extension to
% account for initial circumference
%==========================================================================

% Arduino Communication Information =======================================
comPort = 'COM3';  % Check COM port arduino is connected to
baudRate = 115200; % Match with arduino baudrate
%==========================================================================

%Predefining variables to be read from arduino ----------------------------
dataLength = 100*timeLength;

GaugeP_ADC = zeros(dataLength, 1);             
InhaleP_ADC = zeros(dataLength, 1);          
ExhaleP_ADC = zeros(dataLength, 1);
Chest_counts = zeros(dataLength, 1);
Abd_counts = zeros(dataLength, 1);

t = zeros(dataLength, 1);  % Time using computer clock
%--------------------------------------------------------------------------

% Port reset:
delete(instrfindall);

% Serial open
arduino = serial(comPort,'BaudRate',baudRate);

%% Read data from arduino to MATLAB arrays

% Open comms to arduino and initialise clock and index
fopen(arduino)
t0 = clock;
i = 1;
StartTime = datetime;

% Collecting data for the defined time 
while etime(clock, t0) < timeLength
    
    y = fscanf(arduino, '%s');
    out = sscanf(y, '%d,%d,%d,%d,%d');
    
    t(i) = etime(clock, t0);
    GaugeP_ADC(i) = out(1);      
    InhaleP_ADC(i) = out(2);       
    ExhaleP_ADC(i) = out(3);
    Chest_counts(i) = out(4);
    Abd_counts(i) = out(5);

    i = i+1;  
end

% Close comms with arduino
fclose(arduino);

%% Data Unit Conversions

% Initising time array
time = t - t(1);

P_max = 1; % [psi]
P_min = -1; % [psi]

% Venturi Differential Pressures ------------------------------------------
GaugeP = ((GaugeP_ADC - 0.1*(2^14))./((0.8*(2^14))/(P_max-P_min)) + P_min).*70.306957829636; % [cmH2O]
InhaleDeltaP = ((InhaleP_ADC - 0.1*(2^14))./((0.8*(2^14))/(P_max-P_min)) + P_min).*70.306957829636; %[cmH2O] 
ExhaleDeltaP = ((ExhaleP_ADC - 0.1*(2^14))./((0.8*(2^14))/(P_max-P_min)) + P_min).*70.306957829636; %[cmH2O]
%--------------------------------------------------------------------------

% Tape Measure Change in Lengths ------------------------------------------
r_0 = 22; % initial radius of full spool [mm]
thickness = 0.15; % tape thickness [mm] 
tapeOffset = 108; % initial tape circumference [mm]

% Revolutions from encoder count
deltaTheta_chest = Chest_counts./(4*1024); %[revs]
deltaTheta_abd = Abd_counts./(4*1024); %[revs]

% Spool Radius as a function of revolutions
r_chest = r_0 - thickness.*(floor(deltaTheta_chest)); %[mm]
r_abd = r_0 - thickness.*(floor(deltaTheta_abd)); %[mm]

% Unspooled length 
Chest = tapeOffset + 2*pi.*r_chest.*(deltaTheta_chest); %[mm]
Abd = tapeOffset + 2*pi.*r_abd.*(deltaTheta_abd); %[mm]

%% Plots of collected data (with converted units)

figure(1) %----------------------------------------------------------------
subplot(5, 1, 1)
plot(time, GaugeP, '.')
grid on
grid minor
title("Gauge Pressure at venturi throat [cmH_2O]", 'Fontsize', 12)

subplot(5, 1, 2)
plot(time, InhaleDeltaP, '.')
grid on
grid minor
title("Differential Pressure over venturi in Inhalatory Direction [cmH_2O]", 'Fontsize', 12)

subplot(5, 1, 3)
plot(time, ExhaleDeltaP, '.')
grid on
grid minor
title("Differential Pressure over venturi in Exhalatory Direction [cmH_2O]", 'Fontsize', 12)

subplot(5, 1, 4)
plot(time, Chest, '.')
grid on
grid minor
title("Chest Circumference [mm]", 'Fontsize', 12)

subplot(5, 1, 5)
plot(time, Abd, '.')
grid on
grid minor
title("Abdominal Circumference [mm]", 'Fontsize', 12)
%--------------------------------------------------------------------------

%% Generates Outfiles 

% Raw files ---------------------------------------------------------------
outfile_format_raw = 'MayTrial2023_Subject%d_%d_raw.mat';
outfile_raw = sprintf(outfile_format_raw, SubjectNumber, TestNumber);

save(outfile_raw, 'time', 'GaugeP_ADC', 'InhaleP_ADC', 'ExhaleP_ADC', ...
    'Width_chest', 'Depth_chest', 'StartTime');
%--------------------------------------------------------------------------

% Files with unit conversions ---------------------------------------------
outfile_format = 'MayTrial2023_Subject%d_%d.mat';
outfile = sprintf(outfile_format, SubjectNumber, TestNumber);

save(outfile, 'time', 'GaugeP', 'InhaleDeltaP', 'ExhaleDeltaP', ...
     'Width_chest', 'Depth_chest', 'StartTime');
%--------------------------------------------------------------------------