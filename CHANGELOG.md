# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.4.0]
### Added
- New calibration method (NEED TO DESCRIBE THIS...)

### Changed
- Improved performance in processing mzXML files.
- Minor GUI improvements.


## [0.3.6]
### Changed
- The output `xlsx` results file now contains an extra column `mz_monoisotopic`, 
listing the monoisotopic m/z values of all analytes. 
- The column containing m/z values of the most abundant isotopic peak for each analyte 
has been renamed from `mz_exact` to `mz_most_abundant`.


## [0.3.5]
### Changed
- Improved the accuracy of theoretical isotopic peak relative abundances.
- When trying to determine the height of a peak in a region of the mass spectrum but no local maximum can be found, 
0 is now reported instead of the global maximum of that region. 

### Fixed
- Fixed minor bugs in user interface.


## [0.3.4]
### Fixed
- When the output dataframe contains more than $2^{20}$ rows, the data is now split across multiple sheets in the `xlsx` file. Previously this caused the program to crash and the `xlsx` file to be empty, because a sheet can contain a maximum of $2^{20}$ rows.


## [0.3.3]
### Changed
- Improved the GUI for quadratic m/z-window input under `Advanced settings`.
- Block files can now be organized in subdirectories within the blocks folder.

### Fixed
- Analyte names that do not end with a number (e.g. `IgGI1H3N4F` instead of
  `IgGI1H3N4F1`) now produce a clear error message instead of a generic crash.


## [0.3.2]
### Fixed
- Fixed mass error calculation in calibration figures: errors are now correctly computed as `(observed m/z - exact m/z) / exact m/z * 1e6` (ppm).


## [0.3.1]
### Changed
- Small GUI improvements.
- Add the used analytes list and/or alignment list to separate sheets in the
output `xlsx` file.

### Fixed
- Handle cases where the quantitation calibration/background window 
around the theoretical m/z value of an isotopic peak falls outside the m/z range of the mass spectrum. 
Calibrants for which this occurs are not used for calibration. Analytes for which this occurs are not quantified. 
In both cases a warning message is logged.


## [0.3.0]
### Added
- Option to save calibrated mass spectra as `.xy` files.
- Built-in `.xy` spectrum viewer: opens an interactive plot with zoom, pan, and save controls.

### Changed
- Added `OK` and `Cancel` buttons to the `Advanced settings` window.

### Fixed
- Allow a reference `xlsx` file to contain `None` entries in the `mass_modifier` column.


## [0.2.2]
### Fixed
- Fixed a bug where aligning a chromatogram based on a linear fit caused the program to give an error message.


## [0.2.1]
### Fixed
- Implemented a check against empty `.mzXML` and `.xy` files to prevent crashes.


## [0.2.0]
### Added
- Option to process MS-only data in the form of `.xy` files.
- Option to upload an analytes reference `.xlsx` file directly, instead of supplying an analytes list. 
- Display pre- and post-calibration mass errors (ppm) of calibrants in the calibration figures. Plots are also generated for spectra where calibration failed.
- Option to report peak heights instead of areas. When enabled, backgrounds are reported as average background intensities (instead of background areas).
- Support for adding a mass modifier on top of each analyte (e.g., a label for released glycans). The modifier's elemental composition is considered when calculating theoretical isotopologue distributions.
- Charge carrier isotopes are now considered when calculating theoretical relative isotopologue distributions.

### Changed
- The method for determining peak heights (used for S/N determination and optionally for quantitation) now reports the highest-intensity local maximum within the specified quantitation window, instead of the global maximum. If no local maximum is detected, the global maximum is still reported as a fallback.
- The `InputAnalyte.get_isotopologues()` method was replaced. Previously it used `itertools.product` to enumerate all combinations of heavy isotopes (combinatorial explosion). It now delegates to a new `compute_distribution()` method that uses sequential convolution, which is algorithmically more efficient.
  
### Fixed
- Minor bug fixes in logging.


## [0.1.1]
### Added
- Block file for Neu5Gc.

### Fixed
- Fix the `Revert to default settings` option when using the executable file.
- Fix double confirmation requirement when exiting the program via `File → Exit`.


## [0.1.0]
Initial experimental release of SweetSuite.
