%% Script to plot measurements presented in
% C. Bauer, M. Neher, V. Kamm, L. Steinle, A. Lechler, A. Verl,
% "Lubricant Temperature Observer for Gearboxes in Industrial Robots",
% in IECON 2025 - 51th Annual Conference of the IEEE Industrial Electronics Society,
% Madrid, Spain, 2025
% 
% Replication data: https://doi.org/10.18419/DARUS-5015
% Requirements: MATLAB 2024b

%% Reset MATLAB and set parameter

clear; clc; close all;

% Define a set of distinct colors for plotting
dist_colors = [...
                 0, 190, 255 ; ...
                 0,  81, 158 ; ...
               159, 153, 154 ; ...
            ]./255;

%% Import data

% Load data for identification and validation
data = read_data();

%% Identification

% Plot all identification measurements, using theta_dot from filename
plot_measurements(data.identification, 'Identification', dist_colors, [3, 2], [0, 52]);

%% Validation - Heat-Up

% Plot all heat-up validation measurements, using theta_dot from filename
plot_measurements(data.validation.heat_up, 'Validation: Heat-Up', dist_colors, [3, 2], [0, 52]);

%% Validation - Long-Term

% Plot all long-term validation measurements, using theta_dot_1 and theta_dot_2 from filename
plot_measurements(data.validation.long_term, 'Validation: Long-Term', dist_colors, [1, 2], [0, 52]);

%% Validation - Cool-Down

% Plot the cool-down validation measurement
plot_measurements(data.validation.cool_down, 'Validation: Cool-Down', dist_colors, [1, 1], [0, 52]);

%% Helper Function for Plotting

function plot_measurements(data_struct, plot_title, color_order, tile_shape, y_limits)
% plot_measurements Plots measurement data in a tiled layout.
%   data_struct: struct with measurement tables
%   plot_title:  title for the figure
%   color_order: color order for plots
%   tile_shape:  [rows, cols] for tiledlayout
%   y_limits:    [ymin, ymax] for y-axis

    figure;
    set(groot,'defaultLineLineWidth',1);
    colororder(color_order);
    tiledlayout(tile_shape(1), tile_shape(2));
    sgtitle(plot_title, 'Interpreter', 'latex');
    fields = fieldnames(data_struct);
    for i = 1:length(fields)
        measurement = data_struct.(fields{i});
        nexttile; hold on;
        plot(measurement.t / 60, measurement.T_L, 'DisplayName', 'Lubricant $T_{\mathrm{L}}$');
        plot(measurement.t / 60, measurement.T_H, 'DisplayName', 'Housing $T_{\mathrm{H}}$');
        plot(measurement.t / 60, measurement.T_E, 'DisplayName', 'Environment $T_{\mathrm{E}}$');
        xlabel('Time $t~/~\mathrm{min}$', 'Interpreter', 'latex');
        ylabel({'Temperature', '$T~/~^{\circ}\mathrm{C}$'}, 'Interpreter', 'latex');
        title(extract_title_from_field(fields{i}), 'Interpreter', 'latex');
        box('on'); grid('on');
        xlim([0, max(measurement.t) / 60]);
        ylim([18, y_limits(2)]);
    end
    lgd = legend('Interpreter', 'latex', 'NumColumns', 3);
    lgd.Layout.Tile = 'south';
end

%% Helper Function to Extract Title From Field Name

function title_str = extract_title_from_field(fieldname)
% extract_title_from_field Generates a LaTeX title string from the struct field name
%   Handles cases:
%   - theta_dot_1=XpXXXX_theta_dot_2=XpXXXX
%   - theta_dot=XpXXXX

    % Replace underscores with spaces for parsing
    fname = strrep(fieldname, '_', ' ');
    % Try to match theta_dot_1 and theta_dot_2
    expr_both = 'theta dot 1 ([\d\.p\-]+) theta dot 2 ([\d\.p\-]+)';
    tokens = regexp(fname, expr_both, 'tokens');
    if ~isempty(tokens)
        vals = tokens{1};
        title_str = strrep(strcat("$\dot{\theta}_1 = ", vals{1}, "$ rad/s, $\dot{\theta}_2 = ", vals{2}, "$ rad/s"), "p", ".");
        return;
    end
    % Try to match theta_dot
    expr_single = 'theta dot ([\d\.p\-]+)';
    tokens = regexp(fname, expr_single, 'tokens');
    if ~isempty(tokens)
        val = tokens{1}{1};
        title_str = strrep(strcat("$\dot{\theta} = ", val, "$ rad/s"), "p", ".");
        return;
    end
    % Default: show field name
    title_str = "";
end
