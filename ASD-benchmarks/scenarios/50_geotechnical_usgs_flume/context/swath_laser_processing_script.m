% % This file requires modification 

% Get the list of files in the current folder including the word 'gate';
% adjust it to the name of the swath laser file
files = dir('gate*');
%selects the first file in the list
filename = files(1).name;

fid = fopen(filename, 'r');
count = 0;
while ~feof(fid)
    fgets(fid);
    count = count + 1;
end
fclose(fid);

% Read in data past the headings
fid = fopen(filename, 'r');
for i = 1:30
    fgetl(fid); % Skip the first 30 lines (headings)
end
points = textscan(fid, '%s', 'Delimiter', '\n');
fclose(fid);
points = points{1};

% Read headings
grd = fopen(filename, 'r');
for i = 1:30
    line = fgetl(grd);
    switch i
        case 10, front_step = str2double(line);
        case 12, min_distance = str2double(line);
        case 14, max_distance = str2double(line);
        case 16, motor_speed = str2double(line);
        case 18, total_steps = str2double(line);
        case 22, scan_Msec = str2double(line);
        case 24, start_step = str2double(line);
        case 26, end_step = str2double(line);
        case 28, grouping = str2double(line);
    end
end
fclose(grd);

% Calculate parameters
ctLines = count - 30;
ctSteps = floor(ctLines / 6);

% Initialize arrays
timeStamp = cell(ctSteps, 1);
logTime = cell(ctSteps, 1);
scanSortD = zeros(ctSteps, end_step + 2);
scanSortI = zeros(ctSteps, end_step + 2);

% Process data
lin = 0;
ct = 0;
for i = 1:ctLines
    n = points{i};
    if lin == 0
        if contains(n, '[timestamp]')
            lin = 1;
        elseif contains(n, '[logtime]')
            lin = 2;
        elseif contains(n, '[scan]')
            lin = 3;
        end
    elseif lin == 1
        timeStamp{ct + 1} = n;
        lin = 0;
    elseif lin == 2
        logTime{ct + 1} = n;
        lin = 0;
    elseif lin == 3
        n_split = strsplit(n, '|');
        u = 1;
        m = 1;
        for j = 1:length(n_split)
            if j == 1
                scanSortD(ct + 1, u) = str2double(n_split{j});
                u = u + 1;
            elseif contains(n_split{j}, '&')
                continue;
            elseif contains(n_split{j}, ';')
                s = strsplit(n_split{j}, ';');
                if isnumeric(str2double(s{2}))
                    scanSortD(ct + 1, u) = str2double(s{2});
                    u = u + 1;
                    scanSortI(ct + 1, m) = str2double(s{1});
                    m = m + 1;
                else
                    scanSortD(ct + 1, u) = scanSortD(ct + 1, u - 1);
                    u = u + 1;
                    scanSortI(ct + 1, m) = scanSortI(ct + 1, m - 1);
                    m = m + 1;
                end
            else
                if ismember(i, [210851, 178253, 210797])
                    scanSortI(ct + 1, m) = scanSortD(ct + 1, m - 1);
                elseif ~isempty(n_split{j})
                    scanSortI(ct + 1, m) = str2double(strtrim(n_split{j}));
                end
                m = m + 1;
            end
        end
        lin = 0;
        ct = ct + 1;
    end
end

% Initialize arrays to store log time and time step differences and totals
stepDiff = zeros(ct, 1);
stepTot = zeros(ct, 1);
logDiff = zeros(ct, 1);
logTot = zeros(ct, 1);

% Parse initial log time
f = strsplit(logTime{1}, ' ');
f = strsplit(f{2}, ':');
sec1 = str2double(f{1}) * 3600 + str2double(f{2}) * 60 + str2double(f{3});

% Calculate differences and totals
for i = 2:ct
    stepDiff(i) = str2double(timeStamp{i}) - str2double(timeStamp{i - 1});
    stepTot(i) = stepDiff(i) + stepTot(i - 1);
    
    f = strsplit(logTime{i}, ' ');
    f = strsplit(f{2}, ':');
    sec = str2double(f{1}) * 3600 + str2double(f{2}) * 60 + str2double(f{3});
    logDiff(i) = sec - sec1;
    logTot(i) = logDiff(i) + logTot(i - 1);
    sec1 = sec;
end

% Ensure the first elements of the differences are zero
stepDiff(1) = 0;
stepTot(1) = 0;
logDiff(1) = 0;
logTot(1) = 0;

% Create tables with time values
data = table(timeStamp, stepDiff, stepTot, logTime, logDiff, logTot, ...
    'VariableNames', {'Time_Stamp', 'Time_Stamp_Diff', 'Time_Stamp_Increment', ...
    'Log_Time', 'Log_Time_Diff', 'Log_Time_Increment'});

% Create tables for distance (dfD) and intensity (djI) data
dfD = array2table(scanSortD, 'VariableNames', compose('Var%d', 1:size(scanSortD, 2)));
dfI = array2table(scanSortI, 'VariableNames', compose('Var%d', 1:size(scanSortI, 2)));

% Add time info to data frames
dfD = [data, dfD];
dfI = [data, dfI];
%saves data 
save('extracted_data.mat','dfD','dfI')

% Adjust data frames to include only bounds of measured feature
% and reverse for plotting purposes (adjust as needed)
adjDfDF = dfD(:, [false(1, 6), true(1,end)]);
adjDfDF = adjDfDF(:, end:-1:1); % Reverse columns for distance

%adjust time of observation. In the example below, a maximum depth flow is
%identified in variable 'change', and timing of the dataset is trimmed
%to 5 seconds prior to the peak flow and 30 sec after the peak flow
change = diff(adjDfDF.Var773);
[val,idx] = max(change);
% Adjust time frames of data frames to show time of failure
timeRange = idx-(20*5):idx+(20*30); % there are about 20 observations per second
adjDfDFF = adjDfDF(timeRange, :);

%% clear up some variables before saving
clear points grd ctLines ctLines ctSteps timeStamp logTime scanSortD...
    scanSortI stepDiff StepTot logDiff logTot data lin ct n i idx j m...
    f sec1 change idx val n_split ans timeRange count grouping...
    val idx timeRange adjDfDF change
%% convert polar to cartesian coordinates
% x = r cos0
% y = r sin0

%generate an angle file for the dataset (swath laser reads 190 degrees at
%1520 steps, which is ~0.125 increments

angles = linspace(0, 190, 1520);

%convert polar to cartesian
% Extract the data from the table, ignoring the first 7 columns
distance_data = adjDfDFF{:,:};

[r, c] = size(distance_data);
x = zeros(r, c); % Preallocate x
y = zeros(r, c); % Preallocate y

for i = 1:r
    for j = 1:c
        x(i, j) = distance_data(i, j) * cosd(angles(j));
        y(i, j) = distance_data(i, j) * sind(angles(j));
    end
end
clear i j r c angles
%%
%rotate individual time stamps to a correct orientation (user defined variable theta)
[r,c] = size(x);

for i = 1:r
    x1 = x(i,:);
    y1 = y(i,:);
    v = [x1;y1];

    %choose a rotation origin point
    x_center = x1(1);
    y_center = y1(1);
    center = repmat([x_center; y_center], 1, length(x1));

    %define a counter-clockwise rotational matrix (degrees)
    theta = deg2rad(172.2);
    R = [cos(theta) -sin(theta); sin(theta) cos(theta)];

    s = v - center;     % shift points in the plane so that the center of rotation is at the origin
    so = R*s;           % apply the rotation about the origin
    vo = so + center;

    x_rotated(i,:) = vo(1,:);
    y_rotated(i,:) = vo(2,:);
end
clear distance_data x y s so vo r c i x_center y_center center theta R x1 y1 v


