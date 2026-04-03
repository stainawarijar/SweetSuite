# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1]
### Changed
- Small GUI improvements.

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
