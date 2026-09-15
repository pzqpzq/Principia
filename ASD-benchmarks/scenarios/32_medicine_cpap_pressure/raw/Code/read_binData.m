%
% Author: Rongqing Chen
% Date: 22-Apr-2020
%
% Script overview: 
% This script reads reconstructed EIT images from the .bin file generated
% by the Dr?ger Tool. The images are shown as the view of caudal-cranial
% projection. Keep in mind that the pixel value only means the conductivity
% change in the arbitrary unit (AU), and in no condition is inter-patient 
% comparable.
%

function binData = read_binData(patientData)

    % open .bin file
    fid=fopen(patientData,'r');
    try
        getarray=fread(fid, [1 inf],'int8');
        len=length(getarray);
        frame_length=len/4358;
        clear getarray;
    catch ME
        prompt={'Please enter the number of frames manually'}; % mostly won't happen, but in case
        name='file length';
        numlines=1;
        defaultanswer={'24000'};
        answer=inputdlg(prompt,name,numlines,defaultanswer);
        if isempty(answer)
            return;
        end
        frame_length=str2double(answer{1});
    end
    fclose(fid);
    binData1024=zeros(1024,frame_length);
    fid=fopen(patientData,'r');
    
    % the data structure of the .bin file
    for i=1:frame_length
        time_stamp=fread(fid, [1 2],'float32');  %read time stamp
        dummy=fread(fid, [1],'float32');   %read dummy
        binData1024(:,i)=fread(fid, [1 1024],'float32');%read pixel values for each frame
        int_value=fread(fid, [1 2],'int32');  %read MinMax, Event Marker,
        EventText=fread(fid,[1 30],'int8');
        int_Time=fread(fid, [1 ],'int32'); %Timing Error
        Medibus=fread(fid, [1 52],'float32');
    end
    binData = reshape(binData1024,32,32,frame_length);
    
    % rotate the image to the caudal cranial projection
    binData = rot90(binData);
    binData = flipud(binData);
    
    % release the .bin file
    fclose('all');

end
