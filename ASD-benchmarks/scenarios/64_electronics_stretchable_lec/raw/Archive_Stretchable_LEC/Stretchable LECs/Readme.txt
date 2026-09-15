The photocurrent of the devices were measurend with a SMU-controlled photodiode (V27 BPW21R 148) (data files which end with "pt"). Simultaneaously, the device was controlled by a SMU. Here, a voltage was applied and the current through the device was measured (data files which end with "it").
To calculate the luminance, the photodiode was calibrated with a luminance meter (LS-110, Konica Minolta). The following equation was therefore used:
L = (I_Ph-I_dark)*6.54199E8*(A_OLED/A_LEC,stretch)+2.45461E-9
With 
I_Ph: Photocurrent
I_dark: Darkphotocurrent
A_OLED = 4 mm² (Area of OLED, used for calibration)
A_LEC,stretch: stretched emissive area

Additionally, a corrector factor was calculated for the stretched luminance (here an online-tool ws used: https://phydemo.app/ray-optics/simulator/?de) as the emission Zone shifts with stretching. The following correction values are used for the different elongations:
Stretchin [%]	Correct Factor
0	1
10	0.97723
20	0.87215
30	0.72477
40	0.56392
50	0.41264
