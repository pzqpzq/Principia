%% Figure Generation Code for 2023 ARM Trial 
% Ella Guy 
% Last Updated: 23DEC2023

clear all, close all, clc

%--------------------------------------------------------------------------
% Inputs ------------------------------------------------------------------

SubjectNumber = 3; % de-identifyed subject number
TestNumber = 3; % test reference (1: increasing PEEP,
                                % 2: Breath-holds with increasing PEEP, and 
                                % 3: Forced Expiratory Manuevers)

%--------------------------------------------------------------------------

% Loads Data --------------------------------------------------------------
Trials = {'PEEP', 'PEEP_BH', 'FEM'};
Trial = Trials{TestNumber};

RecordingLengths = [350, 350, 60];
RecordingLength = RecordingLengths(TestNumber);

infile_format = 'ProcessedDataset/ProcessedData_Subject%02d_%s.csv';
infile = sprintf(infile_format, SubjectNumber, Trial);

Data = readtable(infile,'NumHeaderLines',1); 

PSD_t = table2array(Data(:,1)); %
PSD_P = table2array(Data(:,2)); %
PSD_DPI = table2array(Data(:,3)); %
PSD_DPE = table2array(Data(:,4)); %
PSD_Q = table2array(Data(:,5)); %
PSD_V = table2array(Data(:,6)); %
InspInd = table2array(Data(:,7)); %

EIT_t = table2array(Data(:,8)); %
EIT_A = table2array(Data(:,9)); %

ECG_t = table2array(Data(:,10)); %
ECG_trace = table2array(Data(:,11)); %

PPG_t = table2array(Data(:,12)); %
PPG_trace0 = table2array(Data(:,13)); %
PPG_trace1 = table2array(Data(:,14)); %
PPG_trace2 = table2array(Data(:,15)); %

HRB_t = table2array(Data(:,16)); %
HRB_HR = table2array(Data(:,17)); %
HRB_RR = table2array(Data(:,18)); %

%% Trims Data

for ai = 300:length(PSD_t)
    if PSD_t(ai) == 0
        PSD_length = ai-1;
        break
    end
end

PSD_t = PSD_t(1:PSD_length);
PSD_P = PSD_P(1:PSD_length);
PSD_DPI = PSD_DPI(1:PSD_length);
PSD_DPE = PSD_DPE(1:PSD_length);
PSD_Q = PSD_Q(1:PSD_length);
PSD_V = PSD_V(1:PSD_length);


for bi = 2:length(InspInd)
    if InspInd(bi) == 0
        Breaths = bi-1;
        break
    end
end

InspInd = InspInd(1:Breaths);

for ci = 2:length(EIT_t)
    if EIT_t(ci) == 0
        EIT_length = ci-1;
        break
    end
end

EIT_t = EIT_t(1:EIT_length);
EIT_A = EIT_A(1:EIT_length); %


for di = 2:length(ECG_t)
    if ECG_t(di) == 0
        ECG_length = di-1;
        break
    else 
        ECG_length = length(ECG_t);
    end
end

ECG_t = ECG_t(1:ECG_length);
ECG_trace = ECG_trace(1:ECG_length);


for ei = 2:length(HRB_t)
    if HRB_t(ei) == 0
        HRB_length = ei-1;
        break
    end
end

HRB_t = HRB_t(1:HRB_length);
HRB_HR = HRB_HR(1:HRB_length);
HRB_RR = HRB_RR(1:HRB_length);

%% Volume 
V_working = 0;
PSD_V_corrected = [V_working];
base = 0;

for hi = 2:length(PSD_Q)
    if  ismember(hi, InspInd) == 0
        V_working = V_working + trapz(0.01, PSD_Q(hi-1:hi)-base);
    else 
        V_working = 0;
        base = PSD_Q(hi);
    end
    PSD_V_corrected  = [PSD_V_corrected ; V_working];
end

%% Plots Data

figure(1)

subplot(7,1,1)
hold on 
plot(PSD_t, PSD_P)
plot(PSD_t(InspInd), PSD_P(InspInd), '.')
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
title("Gauge Pressure [cmH_2O]")
grid on
grid minor
hold off

subplot(7,1,2)
hold on 
plot(PSD_t, PSD_Q)
plot(PSD_t(InspInd), PSD_Q(InspInd), '.')
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
title("Flow [L/s]")
grid on
grid minor
hold off

subplot(7,1,3)
hold on 
plot(PSD_t, PSD_V_corrected)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
title("Volume [L]")
grid on
grid minor
hold off

subplot(7,1,4)
hold on 
plot(EIT_t, EIT_A)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
title("Global Aeration (EIT)")
grid on
grid minor
hold off

subplot(7,1,5)
hold on 
plot(ECG_t, ECG_trace)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
title("ECG [mV]")
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
title("PPG")
grid on
grid minor
hold off

subplot(7,1,7)
hold on 
plot(HRB_t, HRB_HR)
xline(PSD_t(InspInd), '--')
xlim([0 RecordingLength])
title("Heart Rate [bpm]")
grid on
grid minor
hold off

