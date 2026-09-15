%% Function to read the measurement data in
% C. Bauer, M. Neher, V. Kamm, L. Steinle, A. Lechler, A. Verl,
% "Lubricant Temperature Observer for Gearboxes in Industrial Robots",
% in IECON 2025 - 51th Annual Conference of the IEEE Industrial Electronics Society,
% Madrid, Spain, 2025
% 
% Replication data: https://doi.org/10.18419/DARUS-5015
% Requirements: MATLAB 2024b

function data = read_data()
% READ_DATA Reads CSV and TAB files from all folders and subfolders in the current directory.
% Stores them in a struct using folder and filename as field names.
%
% OUTPUT:
%   data - Struct containing data tables from all folders and subfolders

    % Get all folders in the current directory (excluding . and ..)
    main_dirs = dir();
    is_folder = [main_dirs.isdir];
    folder_names = {main_dirs(is_folder).name};
    folder_names = folder_names(~ismember(folder_names, {'.', '..'}));

    % Supported file extensions
    file_extensions = {'*.tab', '*.csv'};
    data = struct();

    for f = 1:length(folder_names)
        folder = folder_names{f};
        % Get all subfolders (including the main folder itself)
        subdirs = dir(folder);
        isub = [subdirs(:).isdir];
        subfolder_names = {subdirs(isub).name};
        subfolder_names = subfolder_names(~ismember(subfolder_names, {'.', '..'}));
        folder_list = [{folder}, cellfun(@(s) fullfile(folder, s), subfolder_names, 'UniformOutput', false)];

        for ff = 1:length(folder_list)
            current_folder = folder_list{ff};
            for ext = 1:length(file_extensions)
                files = dir(fullfile(current_folder, file_extensions{ext}));
                for i = 1:length(files)
                    filename = files(i).name;
                    filepath = fullfile(current_folder, filename);
                    [~, name, ~] = fileparts(filename);
                    % Make valid field names for folder and file
                    folder_field = matlab.lang.makeValidName(folder);
                    if ff > 1
                        subfolder = subfolder_names{ff-1};
                        subfolder_field = matlab.lang.makeValidName(subfolder);
                        field_path = sprintf('%s.%s.%s', folder_field, subfolder_field, matlab.lang.makeValidName(name));
                    else
                        field_path = sprintf('%s.%s', folder_field, matlab.lang.makeValidName(name));
                    end
                    % Read file into table
                    T = readtable(filepath, 'FileType', 'text');
                    % Assign to struct using dynamic field names
                    parts = strsplit(field_path, '.');
                    switch numel(parts)
                        case 2
                            data.(parts{1}).(parts{2}) = T;
                        case 3
                            data.(parts{1}).(parts{2}).(parts{3}) = T;
                    end
                end
            end
        end
    end
end
