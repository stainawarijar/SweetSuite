![Experimental](https://img.shields.io/badge/status-experimental-yellow)

# SweetSuite
SweetSuite is a program for processing LC-MS glycoproteomics data. It is based
on [LaCyTools](https://github.com/Tarskin/LaCyTools) and on
[MassyTools](https://github.com/Tarskin/MassyTools).
The software provides options for retention time alignment and for targeted
quantitation of (glyco)peptides.

***Note:*** *This software is still in an experimental stage.*

- [USING SWEETSUITE](#using-sweetsuite)
    - [Retention time alignment](#-retention-time-alignment)
    - [Analyte quantitation](#-analyte-quantitation)
- [INSTALLATION](#️-installation)
- [SYSTEM REQUIREMENTS](#️-system-requirements)
- [CREDITS](#-credits)
    - [Copyright notice](#copyright-notice)
    - [Third-party assets](#third-party-assets)

## USING SWEETSUITE
***Note:*** *A more extensive user guide may be written in the future.*

Before using SweetSuite, raw data files should be converted to mzXML format
using [ProteoWizard MSConvert](https://proteowizard.sourceforge.io/).
<br>(*Recommended settings: 32-bit encoding precision, use zlib compression,
remove zero samples.*)

SweetSuite offers options for retention time alignment and for quantitation of analytes. 
Both are optional and can be skipped by simply not uploading an alignment file or an analytes file (see below).

Alignment and quantitation are performed using algorithms very similar to those in LaCyTools
(see the [publication](https://pubs.acs.org/doi/10.1021/acs.jproteome.6b00171) for details).
See also the [GlYcoLISA protocol](https://www.nature.com/articles/s41596-024-00963-7)
for an explanation of how LaCyTools is used for glycosylation analysis of antigen-specific IgG.

When hovering over settings in the GUI, tooltips with short descriptions are displayed.

### Retention time alignment
Download the alignment template `.xlsx` file from the Toolbar
(`File → Templates → Alignment list`). In this file, enter at least five *m/z* 
values and their expected retention times in the *mz* and *time* columns.

By default, the time window and S/N cut-off shown in the GUI are used for all 
alignment features. You can override these defaults per feature by filling in 
the `mz_window`, `time_window`, and `sn_cutoff` columns.

Use the `required` column to mark features that must be present for a successful 
alignment (typically those with the earliest and latest retention times). 
If the extracted ion chromatogram of a required feature does not meet the S/N 
cut-off, alignment will fail for that mzXML file. 

After alignment, SweetSuite generates a PDF with the alignment fits 
(see the LaCyTools publication for details) and writes new, aligned mzXML files.

Below is an example of a valid alignment file:

|   mz      |  time   | mz_window | time_window | sn_cutoff | required |
|:---------:|:-------:|:---------:|:-----------:|:---------:|:--------:|
| 933.0388  | 109.4   |           |             |           |    x     |
| 987.0564  | 108.4   |           |             |           |          |
| 1084.0882 | 108.4   |           |             |           |          |
| 868.3579  | 188.5   |           |             |           |          |
| 922.3755  | 186.5   |           |             |           |          |
| 976.3931  | 185.4   |           |             |           |          |
| 593.827   | 310.8   |           |             |    9      |    x     |


### Analyte quantitation
Download the analytes template `.xlsx` file from the Toolbar
(`File → Templates → Analyte list`) and fill in at least the following columns: 
`analyte`, `charge_min`, `charge_max`, `time`, and `time_window`.

Entries in `analyte` must be constructed from the `.block` files in the blocks 
folder. For example, the analyte `IgGI1H3N4F1` consists of one `IgGI` block, 
three `H` blocks, four `N` blocks, and one `F` block.

`charge_min` and `charge_max` define the charge states in which each analyte 
will be quantified. `time` and `time_window` define the retention time range 
for generating sum spectra, where the range is [`time` ± `time_window`].

To specify potential calibrants, place an `x` in the calibrant column.
You can override the *m/z* quantitation window for individual analytes by 
entering a value in the `mz_window` column.

After you load the analyte list into SweetSuite, an interactive table appears 
where you can adjust the calibrant S/N cut-off for each retention time range. 
When quantitation is finished, SweetSuite creates an Excel file containing all results.

Below is an example of a valid analytes list:

|  analyte         | charge_min | charge_max | mz_window | calibrant |  time  | time_window |
|:---------------:|:----------:|:----------:|:---------:|:---------:|:------:|:-----------:|
| IgG1H3N4F1      |     2      |     3      |           |     x     |  69    |     10      |
| IgG1H4N4F1      |     2      |     3      |           |     x     |  69    |     10      |
| IgG1H5N4F1      |     2      |     3      |           |           |  69    |     10      |
| IgG1H4N4F1S1    |     2      |     3      |           |           |  69    |     10      |
| IgG1H5N4F1S1    |     2      |     3      |           |     x     |  69    |     10      |
| IgG1H5N4F1S2    |     2      |     3      |           |     x     |  69    |     10      |
| IgGIV1H5N4F1    |     2      |     3      |   0.04    |           | 109    |     10      |
| IgGIV1H4N4F1S1  |     2      |     3      |   0.04    |           | 109    |     10      |
| IgGIV1H5N4F1S1  |     2      |     3      |   0.04    |           | 109    |     10      |
| IgGIV1H5N4F1S2  |     2      |     3      |   0.04    |           | 109    |     10      |

### Data output
After analyte quantitation, an `xlsx` file is generated with results stored
in the "Data" tab. The used settings are listed in separate tabs. 
The "Data" tab contains for each file the following outputs per analyte and per charge state:
- `isotopic_fraction`: <br>Fraction of the theoretical isotopic pattern that was integrated.
- `total_area_background_subtracted`: <br>Summed background subtracted areas of all isotopic peaks.
- `mass_error_ppm`: <Br>Mass error in parts-per-million of the most abundant isotopic peak.
    Calculated as `(observed m/z - exact m/z) / (exact m/z) × 1e6`.
- `isotopic_pattern_quality` (IPQ): <Br>A measure for the quality of the isotopic pattern.
    For each isotopic peak, the absolute difference between the expected
    relative area and the observed relative area is taken. The resulting
    absolute differences are then summed to yield the IPQ. 
- `signal_to_noise`: <br>Signal-to-noise (S/N) of the most abundant isotopic peak.
- `total_area`: <br>Summed total areas of all isotopic peaks without background subtraction.
- `total_background`: <br>Summed background values of all isotopic peaks.
- `total_noise`: <br>Summed noise of all isotopic peaks.

## INSTALLATION
**Microsoft Windows**

- *Recommended*
    - Click on the latest release in the sidebar and download the attached `SweetSuite.zip` file. 
    - Extract the contents of the ZIP file to a folder on your computer.
    You should now have an EXE file and a "blocks" folder in the same directory.
    - Double click the EXE file to run SweetSuite.

- *Alternative*
    - Install [Python 3.14](https://www.python.org/downloads/) on your
    computer.
    - Click on the latest release in the sidebar and download
    `Source code.zip`.
    - Extract the contents of the ZIP file to a folder on your computer.
    - Double-click `SweetSuite.bat`. This will automatically install
    required dependencies and then run the program.

**macOS**: Not tested.

**Linux**: Not tested.

## SYSTEM REQUIREMENTS
16 GB of RAM is recommended.

When performing retention time alignment, ensure you have enough free disk space to create new aligned mzXML files. 
For example, if you have 10 GB of mzXML files, you will need at least 10 GB of additional empty space to generate the aligned versions.

## CREDITS
### Copyright notice
Copyright © 2025 Steinar Gijze <br>
*Center for Proteomics and Metabolomics, 
Leiden University Medical Center,
The Netherlands*

### Third-party assets
Code in this project is partially based on [LaCyTools](https://github.com/Tarskin/LaCyTools) (2016) 
and on [MassyTools](https://github.com/Tarskin/MassyTools) (2015), 
both created by Bas Jansen and released under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).

Icons in this project are sourced from [Google Material Icons](https://fonts.google.com/icons), 
released under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0). 
The icons are located in `sweet_suite/gui/assets/google-material-icons/`, along with the LICENSE file.