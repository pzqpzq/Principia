
ALPHA_MULTILAYER

start_Model Version
	1	
end_Model Version

start_Model Parms
	2	0	
	0.0	F	-5.0	5.0	F	'Angle Offset'	F	F	0.0	0.0	100000.0	F	100.0	
	F	
	17.15824452520317	F	-200.0	500.0	F	'Roughness'	F	F	0.0	0.0	100000.0	F	100.0	
	T	
	20	
	'A'	
	1.3	
	3.0	
	30	
	
	'(none)'	
	0.0	
	0.0	
	0	
	
	'(none)'	
	0.0	
	0.0	
	0	
	
	F	
	5.0	F	0.0	20.0	F	'# Back Reflections'	F	F	0.0	0.0	100000.0	F	100.0	
	100.0	F	0.0	100.0	F	'% 1st Reflection'	F	F	0.0	0.0	100000.0	F	100.0	
	
	T	
	3000.0	10000.0	
	F	
	'N,C,S'	
	T	
	T	
	20	
	0.0	F	0.0	50.0	F	'Bandwidth (eV)'	F	F	0.0	0.0	100000.0	F	100.0	
	9	
	F	
	T	
	F	
	F	
	5000.0	9000.0	
	F	
	5	
	F	
	F	
	'Ideal'	
	0.0	F	0.0	100.0	F	'% Thickness Non-uniformity'	F	F	0.0	0.0	100000.0	F	100.0	
	0.0	F	0.0	30.0	F	'Bandwidth (nm)'	F	F	0.0	0.0	100000.0	F	100.0	
	F	
	F	
	'All'	
	100.0	
	
	start_Ambient
		F	
		'(Not Specified)'	
		
	end_Ambient
	
	start_ScatteringFactor
		F	
		'(Not Specified)'	
		
	end_ScatteringFactor
	F	
	F	
	100.0	
	100.0	
	0.0	F	-5.0	5.0	F	'Wvl. Shift (nm)'	F	F	0.0	0.0	100000.0	F	100.0	
	1.0E-4	
	
	start_Simulation
		250.0	1000.0	5.0	45.0	75.0	10.0	100.0	F	0.5	
		F	
		1	
		0.0	F	0.0	10.0	F	'Angular Spread'	F	F	0.0	0.0	100000.0	F	100.0	
		'None'	
		0.0	F	-20.0	20.0	F	'#1'	F	F	0.0	0.0	100000.0	F	100.0	
		0.0	F	-20.0	20.0	F	'#2'	F	F	0.0	0.0	100000.0	F	100.0	
		0.0	F	-20.0	20.0	F	'#3'	F	F	0.0	0.0	100000.0	F	100.0	
		0.0	F	-20.0	20.0	F	'#4'	F	F	0.0	0.0	100000.0	F	100.0	
		0.0	F	-180.0	180.0	F	'Source Rot.'	F	F	0.0	0.0	100000.0	F	100.0	
		0.0	F	-180.0	180.0	F	'Receiver Rot.'	F	F	0.0	0.0	100000.0	F	100.0	
		F	
	end_Simulation
	
	start_MultiSamp
		0	0	
		
		start_DS Weighting
			
		end_DS Weighting
		
	end_MultiSamp
	
	start_ParmCoupling
		0	
		
		start_ParmCouplingFitParms
			0	
		end_ParmCouplingFitParms
		
	end_ParmCoupling
	0.5	
	'Standard Ellipsometric'	
	0	
	50	
	F	
	'(none)'	
	5	
	0.0	F	0.0	1000.0	F	'Smear Width'	F	F	0.0	0.0	100000.0	F	100.0	
	F	
	0	
	
	start_BW Conv
		'Gaussian'	
		0.0	F	0.0	1.0	F	'Exp. Relative Amp.'	F	F	0.0	0.0	100000.0	F	100.0	
		1.0	F	0.0	50.0	F	'Exp. Relative Width'	F	F	0.0	0.0	100000.0	F	100.0	
		F	
		0.0	F	0.0	30.0	F	'Bandwidth (nm) IR'	F	F	0.0	0.0	100000.0	F	100.0	
		1000.0	
		
	end_BW Conv
	
	start_Patterning
		F	
		0	
		0.0	F	0.0	100.0	F	'% Patterned'	F	F	0.0	0.0	100000.0	F	100.0	
		
	end_Patterning
	
	start_Color Calc
		F	
		346	164	540	447	
		0	1	2	'0'	
	end_Color Calc
	'(none)'	
	5	
	0.0	F	0.0	1000.0	F	'Smear Width #2'	F	F	0.0	0.0	100000.0	F	100.0	
	'(none)'	
	5	
	0.0	F	0.0	1000.0	F	'Smear Width #3'	F	F	0.0	0.0	100000.0	F	100.0	
	
	start_MultiModel
		0	2	
		
		50.0	F	0.0	100.0	F	'mWt1'	F	F	0.0	0.0	100000.0	F	100.0	
		50.0	F	0.0	100.0	F	'mWt2'	F	F	0.0	0.0	100000.0	F	100.0	
		
	end_MultiModel
	F	
	0.0	F	-20.0	20.0	F	'PsiOffset'	F	F	0.0	0.0	100000.0	F	100.0	
	0.0	F	-20.0	20.0	F	'PsiOff #1'	F	F	0.0	0.0	100000.0	F	100.0	
	0.0	F	-20.0	20.0	F	'PsiOff #2'	F	F	0.0	0.0	100000.0	F	100.0	
	0.0	F	-20.0	20.0	F	'PsiOff #3'	F	F	0.0	0.0	100000.0	F	100.0	
	0.0	F	-20.0	20.0	F	'PsiOff #4'	F	F	0.0	0.0	100000.0	F	100.0	
	
	start_LAB MSE
		F	
		
	end_LAB MSE
	
	start_LAB MSE
		F	
		
	end_LAB MSE
	
end_Model Parms

start_Derived Parms
	T	
	
end_Derived Parms

start_Derived Parms 2
	'n'	1	6328.0	0.0	0.0	F	F	
	
end_Derived Parms 2

start_Previous Results
	F	
	''	
	
end_Previous Results

start_Selected Options
	
	start_Options_Model Options
		F	
		F	
		F	
		F	
		F	
		F	
		F	
		F	
		F	
		F	
		F	
		F	
		F	
		
	end_Options_Model Options
	
	start_Options_Fit Options
		F	
		F	
		F	
		F	
		F	
		F	
		
	end_Options_Fit Options
	
	start_Options_Other Options
		F	
		F	
		F	
		
	end_Options_Other Options
	
end_Selected Options

start_Prefit Stage Options
	F	
	
	start_Prefit Fit Parms
		0	
	end_Prefit Fit Parms
	
	start_Prefit Global Parms
		F	
		3700.0	50000.0	
		5	
		100	
		F	
		'All'	
		F	
		'N,C,S'	
		0	
		50	
		
	end_Prefit Global Parms
	
end_Prefit Stage Options

start_Model Structure
	
	start_Layer0
		5000000.0	F	-10.0	100000.0	F	'Substrate Thickness'	F	F	0.0	0.0	100000.0	F	100.0	
		'Layer'	'SI_JAW'	'EV'	''	'SI_JAW'	
		start_File Info
			'Si substrate, Herzinger et.al., JAP v83p3323y1998, (multi-wavelength, multi-sample analysis)'	
			1	
			
		end_File Info
		
		start_Mat Table
			636	
			
			start_Wvl Array
				'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'	
			end_Wvl Array
			
			start_e1 Array
				'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'	
			end_e1 Array
			
			start_e2 Array
				'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'	
			end_e2 Array
			
		end_Mat Table
		
		start_SI_JAW Fit Parms
			
		end_SI_JAW Fit Parms
		
		start_SL Parms
			0	1	
			
		end_SL Parms
		
	end_Layer0
	
	start_Layer1
		133.91025963196023	T	-10.0	100000.0	F	'Thickness # 1'	F	T	0.0	0.0	100000.0	F	100.0	
		'Layer'	'Cauchy'	'CAUCHY'	''	'Cauchy'	
		start_Cauchy Fit Parms
			2.110070557546401	T	1.3	3.0	F	'A'	F	F	0.0	0.0	100000.0	F	100.0	
			-0.01959861988118561	T	-2.0	2.0	F	'B'	F	F	0.0	0.0	100000.0	F	100.0	
			0.0018931231533651778	T	-1.0	1.0	F	'C'	F	F	0.0	0.0	100000.0	F	100.0	
			0.0	F	0.0	10.0	F	'k Amplitude'	F	F	0.0	0.0	100000.0	F	100.0	
			1.5	F	0.0	10.0	F	'Exponent'	F	F	0.0	0.0	100000.0	F	100.0	
			4000.0	
			
		end_Cauchy Fit Parms
		
		start_SL Parms
			0	1	
			
		end_SL Parms
		
	end_Layer1
	
end_Model Structure
