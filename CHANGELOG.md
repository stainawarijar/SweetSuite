# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0]
### Added
- Option to process MS-only data in the form of `.xy` files.
- Option to upload an analytes reference `xlsx` file directly, instead of 
supplying an analytes list. 
- Display pre- and post-calibration mass errors (ppm) of calibrants in the
calibration figures.
- Option to report peak heights instead of areas.
- Support for adding a mass modifier on top of each analyte (e.g., a label
  for released glycans). The modifier's elemental composition is considered
  when calculating theoretical isotopologue distributions.
- Charge carrier isotopes are now considered when calculating theoretical
  relative isotopologue distributions.

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
