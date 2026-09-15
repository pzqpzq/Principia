%% Data Processing for 2023 ARM Trial 
% Ella Guy 
% Last Updated: 24FEB2024

clear all, close all, clc

%--------------------------------------------------------------------------
% Inputs ------------------------------------------------------------------

SubjectNumber = 20; % de-identifyed subject number
TestNumber = 2; % test reference (1: increasing PEEP,
                                % 2: Breath-holds with increasing PEEP, and 
                                % 3: Forced Expiratory Manuevers)

breathMin = 0.007; % minimum fluctuation in second derivative breath selection  

% Alignment Breath --------------------------------------------------------

% In BOB data 
T_min_BOB = 26; %[s]
T_max_BOB = 27; %[s] 

% In EIT data 
T_min_EIT = 26; %[s]
T_max_EIT = 27; %[s]
%--------------------------------------------------------------------------

%% Loads Data
%--------------------------------------------------------------------------
Trials = {'PEEP', 'PEEP_BH', 'FEM'};
Trial = Trials{TestNumber};

RecordingLengths = [350, 350, 60];
RecordingLength = RecordingLengths(TestNumber);

% sensor offsets
OffsetA = -0.150;
OffsetB = -0.064;

%--------------------------------------------------------------------------
% Load Respiratory Data ---------------------------------------------------

Infile_format = 'PQ_rawData/Subject%d_%s.csv';
Infile = sprintf(Infile_format, SubjectNumber, Trial);

Respiratory = readtable(Infile,'NumHeaderLines',1); 

time = table2array(Respiratory(:,1)); % time [s]
GaugeP = table2array(Respiratory(:,2)); % Gauge pressure reading [cmH2O]
InhaleDeltaP = table2array(Respiratory(:,3)); % Inspiratory differenrtial pressure [cmH2O]
ExhaleDeltaP = table2array(Respiratory(:,4)); % Expiratory differenrtial pressure [cmH2O]
Depth_chest = table2array(Respiratory(1,5)); % Chest crossectional depth (a) [cm]
Width_chest = table2array(Respiratory(1,6)); % Chest crossectional width (b) [cm]
StartTime = datestr(table2array(Respiratory(1,7)));

BOB_timestep = 0.01;

[h, m, s] = hms(datetime(StartTime, 'InputFormat', 'HH:mm:ss'));
PSD_StartTime = [h, m, s];

for ai = length(time):-1:1
    if time(ai) >= 0
        trim_PSG = ai;
break
    end
end

PSD_t = time(1:trim_PSG);
PSD_P = GaugeP(1:trim_PSG);

PSD_DPI = InhaleDeltaP(1:trim_PSG);
PSD_DPE = ExhaleDeltaP(1:trim_PSG);

% -------------------------------------------------------------------------
% Load EIT File -----------------------------------------------------------

EIT_infile_format = 'EIT_rawData/S%02d_%s.bin';
EIT_infile = sprintf(EIT_infile_format, SubjectNumber, Trial);

EIT_data = read_binData(EIT_infile);

Aeration = sum(sum(EIT_data));
Aeration = Aeration(:);

EIT_sample_frequency = 50; % [Hz]
EIT_timestep = 1/EIT_sample_frequency; % [s]
Time_Aeration = EIT_timestep.*([1:length(Aeration)]);

% -------------------------------------------------------------------------
% Load ECG File -----------------------------------------------------------

ECG_infile_format = 'HRM_rawData/ECG/S%02d_ECG.csv';
ECG_infile = sprintf(ECG_infile_format, SubjectNumber);

ECG_file = readtable(ECG_infile,'NumHeaderLines',1); 

ECG = table2array(ECG_file(:,2));
ECG_time = table2array(ECG_file(:,1));

[h1, m1, s1] = hms(datetime(ECG_time(1), 'InputFormat', 'HH:mm:ss.SSS'));
ECG_StartTime = [h1, m1, s1];

trim_ECG = 1;
for ei = 1:length(ECG_time)
    [hw, mw, sw] = hms(datetime(ECG_time(ei), 'InputFormat', 'HH:mm:ss.SSS'));
    if hw == PSD_StartTime(1)
        if mw == PSD_StartTime(2)
            if floor(sw) == PSD_StartTime(3)
                trim_ECG = ei;
    break
            end
        end
    end
end

ECG_time2 = ECG_time(trim_ECG:end);

for bii = 1:length(ECG_time2)
    [hw, mw, sw] = hms(datetime(ECG_time2(bii), 'InputFormat', 'HH:mm:ss.SSS'));
    ECG_t(bii) = (hw - PSD_StartTime(1))*3600 + ...
        (mw - PSD_StartTime(2))*60 + ...
        (sw - PSD_StartTime(3));
    if ECG_t(bii) >= RecordingLength
break
    end
end

ECG_trace = ECG(trim_ECG: trim_ECG+length(ECG_t)-1);

% -------------------------------------------------------------------------
% Load PPG File -----------------------------------------------------------

PPG_infile_format = 'HRM_rawData/PPG/S%02d_PPG.csv';
PPG_infile = sprintf(PPG_infile_format, SubjectNumber);

PPG_file = readtable(PPG_infile,'NumHeaderLines',1); 

PPG0 = table2array(PPG_file(:,2));
PPG1 = table2array(PPG_file(:,3));
PPG2 = table2array(PPG_file(:,4));
PPG_time = table2array(PPG_file(:,1));

[h2, m2, s2] = hms(datetime(PPG_time(1), 'InputFormat', 'HH:mm:ss.SSS'));
PPG_StartTime = [h2, m2, s2];

trim_PPG = 1;
for ci = 1:length(PPG_time)
    [hw, mw, sw] = hms(datetime(PPG_time(ci), 'InputFormat', 'HH:mm:ss.SSS'));
    if hw == PSD_StartTime(1)
        if mw == PSD_StartTime(2)
            if floor(sw) == PSD_StartTime(3)
                trim_PPG = ci;
    break
            end
        end
    end
end

PPG_time2 = PPG_time(trim_PPG:end);

for cii = 1:length(PPG_time2)
    [hw, mw, sw] = hms(datetime(PPG_time2(cii), 'InputFormat', 'HH:mm:ss.SSS'));
    PPG_t(cii) = (hw - PSD_StartTime(1))*3600 + ...
        (mw - PSD_StartTime(2))*60 + ...
        (sw - PSD_StartTime(3));
    if PPG_t(cii) >= RecordingLength
break
    end
end

PPG_trace0 = PPG0(trim_PPG: trim_PPG+length(PPG_t)-1);
PPG_trace1 = PPG1(trim_PPG: trim_PPG+length(PPG_t)-1);
PPG_trace2 = PPG2(trim_PPG: trim_PPG+length(PPG_t)-1);

% -------------------------------------------------------------------------
% Load HR Belt File -------------------------------------------------------

HRB_infile_format = 'HRM_rawData/HRB/%d.txt';
HRB_infile = sprintf(HRB_infile_format, SubjectNumber);

HRB_file = readtable(HRB_infile,'NumHeaderLines',1); 

HRB_time_str = table2array(HRB_file(:,1));
HRB_msgid = table2array(HRB_file(:,2));
HRB_rr_ms = table2array(HRB_file(:,3));
HRB_hr_bpm = table2array(HRB_file(:,4));

for i = 1:length(HRB_time_str)
    HRB_time(i) = datetime(HRB_time_str{i},'InputFormat', 'HH:mm:ss.SSSSSS''Z');
end

[h3, m3, s3] = hms(HRB_time(1));
HRB_StartTime = [h3, m3, s3];

if PSD_StartTime(1) >= 12
    PSD_StartTime(1) = PSD_StartTime(1) - 12;
end

trim_HRB = 1;
for di = 1:length(HRB_time)
    [hw, mw, sw] = hms(HRB_time(di));
    if hw >= 12
        hw = hw - 12;
    end
    
    if hw == PSD_StartTime(1)
        if mw == PSD_StartTime(2)
            if floor(sw) == PSD_StartTime(3)
                trim_HRB = di;
break
            end
        end
    end
end

HRB_time2 = HRB_time(trim_HRB:end);

for dii = 1:length(HRB_time2)
    [hw, mw, sw] = hms(HRB_time2(dii));
    if hw > 12
        hw = hw - 12;
    end

    HRB_t(dii) = (hw - PSD_StartTime(1))*3600 + ...
        (mw - PSD_StartTime(2))*60 + ...
        (sw - PSD_StartTime(3));
    if HRB_t(dii) >= RecordingLength
break
    end
end

HRB_HR = HRB_hr_bpm(trim_HRB: trim_HRB+length(HRB_t)-1);
HRB_RR = (trim_HRB: trim_HRB+length(HRB_t)-1);

% -------------------------------------------------------------------------

% Processing Respiratory Data --------------------------------------------
% Flow --------------------------------------------------------------------

d1 = 0.015;          % Venturi intake diameter [m]
d2 = 0.010;          % Venturi constriction diameter [m]
cd = 0.97;           % Discharge coefficient
rho = 1.225;         % Density of air [kg/m^3]

A1 = pi*(d1/2)^2;    % Venturi intake cross-sectional area [m^2]
A2 = pi*(d2/2)^2;    % Venturi constrictioncross-sectional area [m^2]

DeltaP = InhaleDeltaP(1:trim_PSG) - ExhaleDeltaP(1:trim_PSG);
PSD_Q = zeros(length(DeltaP), 1);

for ei = 1 : length(DeltaP)
    if PSD_P(ei) <= 0
        PSD_Q(ei) = 1000*cd*A2*sqrt((2*(abs(DeltaP(ei))*98.0665))/(rho*(1-(A2/A1)^2)));
    else
        PSD_Q(ei) = -1.*1000*cd*A2*sqrt((2*(abs(DeltaP(ei))*98.0665))/(rho*(1-(A2/A1)^2)));
    end
end

% -------------------------------------------------------------------------
% Indicies ----------------------------------------------------------------

Smoothed_Q = movmedian(PSD_Q, 20);

Smoothed_P = smooth(movmedian(PSD_P, 20), 250);
Inflect_P = smooth(movmedian(diff(Smoothed_P,2),20), 250);

InspInd_working1 = [];
for fi = 2:length(Inflect_P)
    if Inflect_P(fi-1) < 0 && Inflect_P(fi) >= 0 
        InspInd_working1 = [InspInd_working1, fi];
    end
end

InspInd_working2 = [InspInd_working1(1)];
for fii = 2:length(InspInd_working1)-1
    breath = max(cumtrapz(Inflect_P(InspInd_working1(fii):InspInd_working1(fii+1))));
    if breath >= breathMin 
        InspInd_working2 = [InspInd_working2, InspInd_working1(fii)];
    end
end

InspInd = [InspInd_working2(1)];
for fiii = 2:length(InspInd_working2)
    breath = min(cumtrapz(Inflect_P(InspInd_working2(fiii):-1:InspInd_working2(fiii-1))));
    if breath <= -1*breathMin 
        InspInd = [InspInd, InspInd_working2(fiii)];
    end
end

% -------------------------------------------------------------------------
% Volume ------------------------------------------------------------------

V_working = 0;
PSD_V = [V_working];

for hi = 2:length(PSD_Q)
    if  ismember(hi, InspInd) == 0
        V_working = V_working + trapz(BOB_timestep, PSD_Q(hi-1:hi));
    else 
        V_working = 0;
    end
    PSD_V  = [PSD_V ; V_working];
end

% -------------------------------------------------------------------------

figure(1)
subplot(2,1,1)
hold on 
plot(PSD_t, PSD_V)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

subplot(2,1,2)
hold on 
plot(Time_Aeration, Aeration)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

%% Aligning EIT Data ------------------------------------------------------

I_min_BOB = (BOB_timestep*floor(T_min_BOB/BOB_timestep))/BOB_timestep;
I_max_BOB = (BOB_timestep*floor(T_max_BOB/BOB_timestep))/BOB_timestep;

I_min_EIT = (EIT_timestep*floor(T_min_EIT/EIT_timestep))/EIT_timestep;
I_max_EIT = (EIT_timestep*floor(T_max_EIT/EIT_timestep))/EIT_timestep;

[LM_BOB, LMI_BOB] = max(PSD_V(I_min_BOB:I_max_BOB));
[LM_EIT, LMI_EIT] = max(Aeration(I_min_EIT:I_max_EIT));

LMT_BOB = PSD_t(I_min_BOB + LMI_BOB);
LMT_EIT = Time_Aeration(I_min_EIT + LMI_EIT);

% Aligning ----------------------------------------------------------------

T_align =  LMT_BOB - LMT_EIT;

EIT_time = Time_Aeration + T_align;

for ji = 1:length(EIT_time)
    if EIT_time(ji)>=0
        trim1_EIT = ji;
break
    end
end

trim2_EIT = length(EIT_time);
for jii = 1:length(EIT_time)
    if EIT_time(jii)>=RecordingLength
        trim2_EIT = jii;
break
    end
end

EIT_t = EIT_time(trim1_EIT:trim2_EIT);
EIT_A = Aeration(trim1_EIT:trim2_EIT);

% -------------------------------------------------------------------------
% Plots ------------------------------------------------------------------

figure(2)
subplot(7,1,1)
hold on 
plot(PSD_t, PSD_P)
plot(PSD_t(InspInd), PSD_P(InspInd), '.')
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

subplot(7,1,2)
hold on 
plot(PSD_t, PSD_Q)
plot(PSD_t(InspInd), PSD_Q(InspInd), '.')
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

subplot(7,1,3)
hold on 
plot(PSD_t, PSD_V)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

subplot(7,1,4)
hold on 
plot(EIT_t, EIT_A)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

subplot(7,1,5)
hold on 
plot(ECG_t, ECG_trace)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

subplot(7,1,6)
hold on 
plot(PPG_t, PPG_trace0)
plot(PPG_t, PPG_trace1)
plot(PPG_t, PPG_trace2)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

subplot(7,1,7)
hold on 
plot(HRB_t, HRB_HR)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
grid on
grid minor
hold off

%% Saves Data 

csv_outfile_format = 'ProcessedDataset/ProcessedData_Subject%02d_%s.csv';
csv_outfile_name = sprintf(csv_outfile_format, SubjectNumber, Trial);

Output = zeros(length(PPG_t), 18);

Output(1:length(PSD_t),1) = PSD_t;
Output(1:length(PSD_t),2) = PSD_P;
Output(1:length(PSD_t),3) = PSD_DPI;
Output(1:length(PSD_t),4) = PSD_DPE;
Output(1:length(PSD_t),5) = PSD_Q;
Output(1:length(PSD_t),6) = PSD_V;
Output(1:length(InspInd), 7) = InspInd;

Output(1:length(EIT_t), 8) = EIT_t;
Output(1:length(EIT_t), 9) = EIT_A;

Output(1:length(ECG_t), 10) = ECG_t;
Output(1:length(ECG_t), 11) = ECG_trace;

Output(1:length(PPG_t), 12) = PPG_t;
Output(1:length(PPG_t), 13) = PPG_trace0;
Output(1:length(PPG_t), 14) = PPG_trace1;
Output(1:length(PPG_t), 15) = PPG_trace2;

Output(1:length(HRB_t), 16) = HRB_t;
Output(1:length(HRB_t), 17) = HRB_HR;
Output(1:length(HRB_t), 18) = HRB_RR;


OutputTable = array2table(Output);
OutputTable.Properties.VariableNames(1:18) = {'PSD Time [s]', ...
                'PSD Gauge Pressure [cmH2O]', ...
                'PSD Inspiratory Differential Pressure [cmH2O]', ...
                'PSD Expiratory Differential Pressure [cmH2O]', ...
                'PSD Flow [L/s]', ...
                'PSD Tidal Volume [L]', ...
                'PSD Inspiratory Indicies' ...
                ...
                'EIT Time [s]', ...
                'EIT Global Aeration', ...
                ...
                'ECG Time [s]', ...
                'ECG [mV]', ...
                ...
                'PPG Time [s]', ...
                'PPG0', ...
                'PPG1', ...
                'PPG2', ...
                ...
                'HRB Time [s]', ...
                'HRB Heartrate [bpm]', ...
                'HRB RR Interval [ms]'};

% writetable(OutputTable, csv_outfile_name)
