NIST Data Publication:
Dataset in support of publication : Sensitivity Comparison of Rydberg Atom-Based
Radio-Frequency Electric Field Detection: Ionization Current Versus Optical
Readout
Version 1.0.0
DOI: https://doi.org/10.18434/mds2-3951

Authors:
  Dangka  Shylla
    National Institute o
    University of Colorado - Boulder
  Rajavardhan  Talashila
    Associate, National Institute of Standards and Technology
    University of Colorado
  Alexandra  Artusio-Glimpse
    National Institute of Standards and Technology
  Adil  Meraki
    Associate, National Institute of Standards and Technology
    University of Colorado -  Boulder
  Dixith  Manchaiah
    Associate, National Institute of Standards and Technology
    University of Colorado
  Noah  Schlossberger
    National Institute of Standards and Technology
  Samuel  Berweger
    National Institute of Standards and Technology
  Matthew T. Simons
    National Institute of Standards and Technology
  Christopher L. Holloway
    National Institute of Standards and Technology
  Nikunjkumar  Prajapati
    National Institute of Standards and Technology

Contact:
  Dangka Shylla
    dangka.shylla@nist.gov

Description:

We investigate a technique for detecting radio-frequency (RF) electric fields in
a Cesium (Cs) vapor cell at room temperature by collecting charge from ionized
Rydberg atoms and compare its performance with the established method of
electromagnetically induced transparency (EIT). By applying a known RF field, we
measure the response from both the electrical (ionization current-based) and
optical (EIT-based) readouts. The ionization current-based method yields a
sensitivity of 22.4~$\mu$Vm$^{-1}$Hz$^{-1/2}$, while the EIT-based method
achieves 3.7~$\mu$Vm$^{-1}$Hz$^{-1/2}$. The sensitivity of the ionization
current-based method is limited by thermal noise arising from a 2.2~k$\Omega$
resistance between the collection electrodes, attributed to a thin Cs film on
the inner surfaces of the vapor cell. Controlling or eliminating the Cs layer
can significantly improve the sensitivity of this ionization approach.


--------------
Data Use Notes
--------------

This data is publicly available according to the NIST statements of
copyright, fair use and licensing; see
https://www.nist.gov/director/copyright-fair-use-and-licensing-statements-srd-data-and-software

You may cite the use of this data as follows:
Shylla, Dangka, Talashila, Rajavardhan, Artusio-Glimpse, Alexandra, Meraki,
Adil, Manchaiah, Dixith, Schlossberger, Noah, Berweger, Samuel, Simons, Matthew
T., Holloway, Christopher L., Prajapati, Nikunjkumar (2025), Dataset in support
of publication : Sensitivity Comparison of Rydberg Atom-Based Radio-Frequency
Electric Field Detection: Ionization Current Versus Optical Readout, Version
1.0.0, National Institute of Standards and Technology,
https://doi.org/10.18434/mds2-3951 (Accessed: [give download date])

-------------
Data Overview
-------------

Files included in this publication:

  FIG1c_ExampleSpectraEIT_AT_Ion.csv

    EIT-AT and Ionization Spectra at Various RF Signal Powers
    Example traces of EIT-AT and ionization spectra as a function of coupling
      laser detuning for various injected RF powers (in dBm) applied to the
      cable feeding the horn antenna: RF off, 0, 8, and 14 dBm. The probe and
      coupling Rabi frequencies were fixed at 3 MHz and 2.83 MHz, respectively.
      EIT signals were obtained from a balanced photodetector measuring
      transmitted probe light, while ionization signals were collected
      simultaneously using a current amplifier.
    Format: 9 column data: coupling laser detuning (MHz), 4 columns of EIT
      signal amplitude (arb. units) at different RF signal powers, 4 columns of
      ionization signal amplitude (arb. units) at the same RF signal powers
  
   FIG2a_EITSpectra_with_CouplingRabiFrequency.csv

    EIT Spectra for Varying Coupling Rabi Frequencies
    Electromagnetically Induced Transparency (EIT) spectra of the 43D_3/2 and
      43D_5/2 Rydberg state measured as a function of coupling laser detuning
      for various coupling Rabi frequencies, with the probe Rabi frequency fixed
      at 3 MHz. Each spectrum corresponds to a different value of the coupling
      Rabi frequency.
    Format: 3 column data: coupling laser detuning (MHz), coupling Rabi
      frequency (MHz), EIT signal amplitude (arb. units)

   FIG2b_EITSpectra_with_ProbeRabiFrequency.csv

    EIT Spectra for Varying Probe Rabi Frequencies
    Electromagnetically Induced Transparency (EIT) spectra of the 43D_3/2 and
      43D_5/2 Rydberg state measured as a function of coupling laser detuning
      for various probe Rabi frequencies, with the coupling Rabi frequency fixed
      at 2.8 MHz. Each spectrum corresponds to a different value of the probe
      Rabi frequency.
    Format: 3 column data: coupling laser detuning (MHz), probe Rabi frequency
      (MHz), EIT signal amplitude (arb. units)

   FIG3a_IonSpectra_with_CouplingRabiFrequency.csv

    Ionization Spectra for Varying Coupling Rabi Frequencies
    Ionization spectra of the 43D_3/2 and 43D_5/2 Rydberg state measured as a
      function of coupling laser detuning for various coupling Rabi frequencies,
      with the probe Rabi frequency fixed at 3 MHz. Each spectrum corresponds to
      a different value of the coupling Rabi frequency.
    Format: 3 column data: coupling laser detuning (MHz), coupling Rabi
      frequency (MHz), EIT signal amplitude (arb. units)

   FIG3b_IonSpectra_with_ProbeRabiFrequency.csv

    Ionization Spectra for Varying Probe Rabi Frequencies
    Ionization spectra of the 43D_3/2 and 43D_5/2 Rydberg state measured as a
      function of coupling laser detuning for various probe Rabi frequencies,
      with the coupling Rabi frequency fixed at 2.8 MHz. Each spectrum
      corresponds to a different value of the probe Rabi frequency.
    Format: 3 column data: coupling laser detuning (MHz), probe Rabi frequency
      (MHz), EIT signal amplitude (arb. units)

   FIG4a_EIT_ION_WidthandAmplitude_with_CouplingRabiFrequency.csv

    EIT and Ionization Full Width at Half Maximum (FWHM) and Amplitude vs.
      Coupling Rabi Frequency
    Full width at half maximum (FWHM) and amplitude of both EIT and ionization
      signals measured as a function of coupling Rabi frequency, with the probe
      Rabi frequency fixed at 3 MHz. Uncertainties represent standard deviations
      extracted from the fit to each individual spectrum.
    Format: 9 column data: coupling Rabi frequency (MHz), EIT FWHM (MHz), EIT
      FWHM standard deviation from fit (MHz), EIT amplitude (arb. units), EIT
      amplitude standard deviation from fit (arb. units), ionization FWHM (MHz),
      ionization FWHM standard deviation from fit (MHz), ionization amplitude
      (arb. units), ionization amplitude standard deviation from fit (arb.
      units)

   FIG4b_EIT_ION_WidthandAmplitude_with_ProbeRabiFrequency.csv

    EIT and Ionization Full Width at Half Maximum (FWHM) and Amplitude vs.
      Probe Rabi Frequency
    Full width at half maximum (FWHM) and amplitude of both EIT and ionization
      signals measured as a function of probe Rabi frequency, with the coupling
      Rabi frequency fixed at 2.8 MHz. Uncertainties represent standard
      deviations extracted from the fit to each individual spectrum.
    Format: 9 column data: probe Rabi frequency (MHz), EIT FWHM (MHz), EIT
      FWHM standard deviation from fit (MHz), EIT amplitude (arb. units), EIT
      amplitude standard deviation from fit (arb. units), ionization FWHM (MHz),
      ionization FWHM standard deviation from fit (MHz), ionization amplitude
      (arb. units), ionization amplitude standard deviation from fit (arb.
      units)

 
   FIG5a_Measured_Efield_vs_AppliedSignalRFPower_for_EIT_ION.csv

    Measured RF Electric Field Amplitude vs. Square Root of Input Signal RF
      Power
    Measured RF electric field amplitude as a function of the square root of
      the input RF signal power applied to the horn antenna, based on EIT and
      ionization measurements. This dataset is used to extract the electric
      field calibration factor via linear fitting for both measurement methods.
    Format: 8 column data: square root of input RF signal power for EIT
      measurement (mW^0.5), electric field extracted from EIT spectra (V/m),
      square root of input RF signal power for EIT fit (mW^0.5), fitted electric
      field from EIT (V/m), square root of input RF signal power for ionization
      measurement (mW^0.5), electric field extracted from ionization spectra
      (V/m), square root of input RF signal power for ionization fit (mW^0.5),
      fitted electric field from ionization (V/m)


   FIG5b_BeatnoteAmp_vs_AppliedSignalRFPower_EIT.csv

    Beat Note Amplitude vs. Input Signal RF Power from EIT
    Beat note amplitude extracted from the EIT signal as a function of input
      RF signal power in dBm. The dataset includes measured beat note
      amplitudes, the measured noise floor, and fit data for beat note
      amplitude.
    Format: 6 column data: input signal power P_sig (dBm), measured beat note
      amplitude (dBm), input signal power for noise floor measurement (dBm),
      measured noise floor (dBm), input signal power for fit (dBm), fitted beat
      note amplitude (dBm)

   FIG5c_BeatnoteAmp_vs_AppliedSignalRFPower_Ion.csv

    Beat Note Amplitude vs. Input Signal RF Power from Ionization
    Beat note amplitude extracted from the EIT signal as a function of input
      RF signal power in dBm. The dataset includes measured beat note
      amplitudes, the measured noise floor, and fit data for beat note
      amplitude.
    Format: 6 column data: input signal power P_sig (dBm), measured beat note
      amplitude (dBm), input signal power for noise floor measurement (dBm),
      measured noise floor (dBm), input signal power for fit (dBm), fitted beat
      note amplitude (dBm)

   FIG5d_NoiseSpectra_EIT.csv

    Noise Spectra for EIT Measurements
    Noise spectra relevant to EIT measurements. Data includes the spectrum
      analyzer (SA) noise floor, the noise from the balanced photodetector
      during EIT measurement, probe laser noise alone, probe laser noise with
      the coupling laser present, and probe laser noise with both the coupling
      laser and RF field applied.
    Format: 6 column data: frequency (kHz), spectrum analyzer noise (dBm),
      photodetector noise (dBm), probe laser noise (dBm), probe plus coupling
      laser noise (dBm), probe plus coupling plus RF field noise (dBm)
  
   FIG5e_NoiseSpectra_Ion.csv

    Noise Spectra for Ionization Measurements
    Noise spectra relevant to ionization measurements. Data includes spectrum
      analyzer  noise floor, current amplifier noise with input open, current
      amplifier noise with the vapor cell connected, probe laser noise alone,
      probe laser noise with the coupling laser present, and probe laser noise
      with both coupling laser and RF field applied.
    Format: 7 column data: frequency (kHz), spectrum analyzer noise (dBm),
      current amplifier noise open input (dBm), current amplifier noise cell
      connected (dBm), probe laser noise (dBm), probe plus coupling laser noise
      (dBm), probe plus coupling plus RF field noise (dBm)

  
  FIG6a_Sensitivity_with_CouplingRabiFrequency.csv

    Sensitivity as a Function of Coupling Rabi Frequency
    Sensitivity in microvolts per meter per square root hertz (µV/m/Hz^0.5)
      measured as a function of coupling Rabi frequency, with the probe Rabi
      frequency fixed at 2.5 MHz. Each data point represents the average of
      three independent measurements, with error bars indicating the standard
      deviation.
    Format: 5 column data: coupling Rabi frequency (MHz), averaged EIT
      sensitivity (µV/m/Hz^0.5), standard deviation of EIT sensitivity, averaged
      ionization sensitivity (µV/m/Hz^0.5), standard deviation of ionization
      sensitivity

   FIG6b_Sensitivity_with_ProbeRabiFrequency.csv

    Sensitivity as a Function of Probe Rabi Frequency
    Sensitivity in microvolts per meter per square root hertz (µV/m/Hz^0.5)
      measured as a function of probe Rabi frequency, with the coupling Rabi
      frequency fixed at 2.8 MHz. Each data point represents the average of
      three independent measurements, with error bars indicating the standard
      deviation.
    Format: 5 column data:probe Rabi frequency (MHz), averaged EIT sensitivity
      (µV/m/Hz^0.5), standard deviation of EIT sensitivity, averaged ionization
      sensitivity (µV/m/Hz^0.5), standard deviation of ionization sensitivity
 


---------------
Version History
---------------

1.0.0 (this version)
  initial release


