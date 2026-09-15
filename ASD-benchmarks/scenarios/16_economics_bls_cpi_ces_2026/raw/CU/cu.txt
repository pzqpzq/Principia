				Consumer Price Index (CU)
					cu.txt

Section Listing

1. Survey Definition
2. FTP files listed in the survey directory.
3. Time series, series file, data file, & mapping file definitions and relationships
4. Series file format and field definitions
5. Data file format and field definitions
6. Mapping file formats and field definitions
7. Data Element Dictionary
================================================================================
Section 1
================================================================================

The following is a definition of:  CONSUMER PRICE INDEX - All Urban Consumers (CU)

Survey Description: The Consumer Price Index (CPI) is a statistical measure
of change, over time, of the prices of goods and services in major 
expenditure groups--such as food, housing, apparel, transportation, and 
medical care--typically purchased by urban consumers. Essentially, it 
compares the cost of a sample "market basket" of goods and services in a 
specific month relative to the cost of the same "market basket" in an 
earlier reference period. This reference period is designated as the base 
period.

The CPI publishes indexes for two 
populations; all urban consumers (CU) and urban wage earners and clerical workers (CW).  

To construct the two indexes, thousands of prices for commodities and services purchased by consumers 
are collected in a sample of 75 urban places. Rent data is collected in a separate sample of thousands 
of rental units. Comparison of indexes for individual CMSA's or cities show only the relative
change over time in prices between locations. These indexes cannot be used
to measure interarea differences in price levels or living costs.

Summary Data Available: U.S. average indexes for both populations are 
available for several hundred consumer items and groups of items. In addition, 
many of the indexes have been adjusted for seasonality. The indexes are monthly. Different indexes 
go back to different years, with the earliest, including all items, dating to  1913. Semi-annual 
indexes have been calculated for many items for comparison with 
semi-annual areas mentioned below. Semi-annual indexes are available from 1984 forward.

Area indexes for both populations are available for 23 urban places. For 
each area, indexes are published for a subset of items and groups. The indexes
are published monthly for three areas and bimonthly for twenty areas. Regional and division level 
indexes for both populations are available for a subset of items and groups published. Indexes are 
published for four regions and nine divisions. Regional indexes date to 1966; divisional indexes 
are newer, dating to 2018. Indexes are monthly, with  Semi-annual indexes 
also calculated for selected items.  

City-size class indexes for both populations are available for two size classes 
with a similar subset of groups and items. 
Region/city-size indexes (for example, Midwest size class B/C)for both populations are also available monthly. 

Frequency of Observations: U.S. city average indexes, regional indexes, 
division  indexes, size class indexes, and three metro area indexes are monthly. 20 metro area indexes are bimonthly.

Annual Averages: Annual averages are available for all unadjusted series 
in the CW and CU.

Base Periods: Most indexes have a base period of 1982-1984 = 100.  Other 
indexes, mainly newer indexes, are based more recently.  The base period value is generally 100.0, 
with rare exceptions where the base is set to 1000 to avoid loss of precision. The index
for the "Purchasing Power" values (AAOR and SAOR) have a base period value of 1.000.

Data Characteristics: Indexes are published to three decimal places.

Updating Schedule:  Updates become available with the release of new data, typically between the 10th and 14th of the month 
following the reference month.

==================================================================================
Section 2
==================================================================================

The following Consumer Price Index (All Urban Consumers) files are on the BLS 
internet in the sub-directory pub/time.series/cu:

	cu.data.0.Current			-  All current year-to-date 
	cu.data.1.AllItems			-  All items (item_code AA0, SA0)
	cu.data.2.Summaries			-  Summaries (item_code SA0, SAF,
						   SAH, SAA, SAT, SAM, SAR, SAE, SAG,
						   SAS, SAC)
	cu.data.3.AsizeNorthEast		-  A-Size areas in Northeast
						   (area_code A1 ...)
	cu.data.4.AsizeNorthCentral		-  A-size areas in North Central
						   (area_code A2 ...)
	cu.data.5.AsizeSouth			-  A-Size areas in South
						   (area_code A3 ...)
	cu.data.6.AsizeWest			-  A-Size areas in West
						   (area_code A4 ...)
	cu.data.7.OtherNorthEast		-  All other Northeast
						   (area_code 01, X1, D1)
	cu.data.8.OtherNorthCentral		-  All other North Central
						   (area_code 02, X2, D2)
	cu.data.9.OtherSouth			-  All other in South
						   (area_code 03, X3, D3)
	cu.data.10.OtherWest			-  All other in West
						   (area_code 04, X4)  
	cu.data.11.USFoodBeverage		-  All US Food and Beverage
						   (area_code 0000, item_code SAF, SEF)
	cu.data.12.USHousing			-  All US Housing (area_code 0000, 
						   item_code SAH, SEH)
	cu.data.13.USApparel			-  All US Apparel (area_code 0000,
						   item_code SAA, SEA)
	cu.data.14.USTransportation		-  All US Transportation (area_code
						   0000, item_code SAT, SET)
	cu.data.15.USMedical			-  All US Medical (area_code 0000, 
						   item_code SAM, SEM, SS57)
	cu.data.16.USRecreation			-  All US Recreation (area_code 0000,
						   item_code SAR, SER, SS31, SS61, SS62)
	cu.data.17.USEducationAndCommunication	-  All US Education and Communication
						   (area_code 0000, item_code SAE,
						    SEE, SS27)
	cu.data.18.USOtherGoodsAndServices	-  All US Other Goods and Services
						   (area_code 0000, item_code SAG, SEG;
						    SS33)
	cu.data.19.PopulationSize		-  All Population-size (area_code
						   A000, X000, D000)
	cu.data.20.USCommoditiesServicesSpecial	-  All US Commodity and Services and 
						   Special(area_code 0000, item_code 
						   SA0, SAC, SAN, SAS)
	cu.area					-  Area codes		mapping file
	cu.contacts				-  Contacts for cu survey 
	cu.footnote				-  Footnote codes	mapping file
	cu.item					-  Item codes		mapping file
	cu.MapErrors (TBR)			-  Map error codes	mapping file
	cu.period				-  Period codes 	mapping file
	cu.series				-  All series and their beginning and end dates
	cu.txt					-  General information

Note: TBR = File that will be removed.		
=================================================================================
Section 3
=================================================================================
The definition of a time series, its relationship to and the interrelationship
among series, data and mapping files is detailed below:

A time series refers to a set of data observed over an extended period of time
over consistent time intervals (i.e. monthly, quarterly, semi-annually, annually).  
BLS time series data are typically produced at monthly intervals and represent data 
ranging from a specific consumer item in a specific geographical area whose price 
is gathered monthly to a category of worker in a specific industry whose employment
rate is being recorded monthly, etc.

The download.bls.gov files are organized such that data users are provided with the following
set of files to use in their efforts to interpret data files:

a)  a series file (only one series file per survey)
b)  mapping files
c)  data files

The series file contains a set of codes which, together, compose a series 
identification code that serves to uniquely identify a single time series.  
Additionally, the series file also contains the following series-level information:

a) the period and year corresponding to the first data observation 
b) the period and year corresponding to the most recent data observation 

The mapping files are definition files that contain explanatory text descriptions
that correspond to each of the various codes contained within each series
identification code.

The data file contains one line of data for each observation period pertaining to a
specific time series. Each line contains a reference to the following:

a) a series identification code
b) year in which data is observed
c) period for which data is observed (M13, Q05, and S03 indicate annual averages)
d) value
e) footnote code (if available)
=================================================================================
Section 4
=================================================================================
File Structure and Format: The following represents the file format used to define 
cu.series. Note that the Field Numbers are for reference only; they do not exist 
in the database.  Data files are in ASCII text format.  Data elements are separated 
by spaces; the first record of each file contains the column headers for the data
elements stored in each field.  Each record ends with a new line character. 

Field #/Data Element		Length		Value(Example)		

1.  series_id		  	17		CUSR0000SA0

2.  area_code		   	4		0400

3.  item_code		   	8		SA0E

4.  seasonal		   	1		S or U		
						
5.  periodicity_code	   	1		R	
						
6.  base_code		   	1		S

7.  base_period		   	20		1982-84=100		
				
8.  begin_year		   	4		1947		

9.  begin_period   		3		M01		

10. end_year			4		2002

11. end_period			3		M02
				

The series_id (CUSR0000SA0) can be broken out into:

Code					Value

survey abbreviation	=		CU
seasonal(code)		=		S
periodicity_code	=		R
area_code		=		0000
item_code		=		SA0
==================================================================================
Section 5
==================================================================================
File Structure and Format: The following represents the file format used to define
each data file. Note that the field numbers are for reference only; they do not 
exist in the database.  Data files are in ASCII text format.  Data elements are 
separated by spaces; the first record of each file contains the column headers for 
the data elements stored in each field. Each record ends with a new line character.   

The cu.data file is partitioned into a number of separate files:  See Section 2

All of the above-referenced data files have the following format:

Field #/Data Element	Length		Value(Example)		

1. series_id		  17		CUUR0400AA0

2. year			   4		1966	

3. period		   3		M12		

4. value		  12      	53.3	
				 
5. footnote_codes	  10		It varies
				

The series_id (CUUR0400AA0) can be broken out into:

Code					Value

survey abbreviation	=		CU
seasonal(code)		=		U
periodicity_code	=		R
area_code		=		0400
item_code		=		AA0
================================================================================
Section 6
================================================================================
File Structure and Format: The following represents the file format used to define
each mapping file. Note that the field numbers are for reference only; they do not
exist in the database.  Mapping files are in ASCII text format. Data elements are
separated by tabs; the first record of each file contains the column headers for the
data elements stored in each field.  Each record ends with a new line character. 

File Name:  cu.area

Field #/Data Element		Length		Value(Example)

1. area_code			4		0100

2. area_name			80		Text


File Name:  cu.footnote

Field #/Data Element		Length		Value(Example)

1. footnote_code		1		R

2. footnote_text		100		Text


File Name:  cu.item

Field #/Data Element		Length		Value(Example)

1. item_code			8		AA0

2. item_name			100		Text


File Name:  cu.period

Field #/Data Element		Length		Value(Example)

1. period			3		M02

2. period_abbr			5		FEB

3. period_name			20		Text (e.g. February)
=========================================================================================
Section 7
=========================================================================================
CONSUMER PRICE INDEX (CU) DATABASE ELEMENTS

Data Element	Length		Value(Example)			Description

area_code	4		N or S, ,000-999		Unique code used to identify
				Ex: A100 		a specific geographic area.
					
area_name	80		Text 			Name of specific geographic
				Ex: MIAMI, FLA		area.
				
base_code	1		S=Standard reference 	Code identifying the type of
				base			base period used in index.
				A=Alternate reference 
				base	

base_period	20		Identifies the base  	The actual base period used
				period			in calculating the index.
				Ex: 1982-84=100	
				     
begin_period	3		M01-M13 or S01-S03	Identifies first data observation
				Ex: MO6=June		within the first year for which 
				(M=Monthly, M13=Annual	data is available for a given
				Avg, S=Semi-Annually)	time series.
				
begin_year	4		YYYY			Identifies first year for which
				Ex: 1975		data is available for a given
							time series.

end_period	3		M01-M13 or S01-S03	Identifies last data observation
				Ex: M06=June		within the last year for which 
				(M=Monthly, M13=Annual	data is available for a given
				Avg, S=Semi-Annually)	time series.
				
end_year	4		YYYY			Identifies last year for which 
				Ex: 1980		data is available for a given  
							time series.

footnote_code	1		R			Identifies footnote for the data 
							series.

footnote_text	100		Text			Contains the text of the footnote.

item_code	8		SA0E			Identifies item for which 
							data observations pertain.

item_name	100		Text			Full names of items.
				
period_abbr	5		Text	 		Abbreviation of period name.
				Ex: JUN

period		3		M01-M13 or S01-S03	Identifies period for which
				Ex: M06=June		data is observed. 
				(M=Monthly, M13=Annual	
				Avg, S=Semi-Annually)
				
period_name	20		Text		 	Full name of period to which
				Ex: June		the data observation refers.
				
periodicity_	1		S=Semi-Annual		Frequency of data
code				R=Regular		observation.

seasonal	1		S=Seasonally		Code identifying whether the
				  Adjusted 		data are seasonally adjusted.
				U=Unadjusted			  		

series_id	17		CUSR0000SA0		Code identifying the specific 
							series.

value		12		53.3			Price index for item.
	   
year		4		YYYY			Identifies year of observation.
				Ex: 1990		
				




