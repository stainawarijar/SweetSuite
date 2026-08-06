# SweetSuite — Architecture

This document describes the structure of the SweetSuite codebase to help
contributors understand how the components fit together.

---

## Table of contents

- [Overview](#overview)
- [Directory layout](#directory-layout)
- [Entry point](#entry-point)
- [Package: `sweet_suite`](#package-sweet_suite)
  - [Top-level modules](#top-level-modules)
  - [chromatography](#chromatography)
  - [mass\_spectrometry](#mass_spectrometry)
  - [reporting](#reporting)
  - [resources](#resources)
  - [utils](#utils)
  - [gui](#gui)
- [Block files](#block-files)
- [Key data flows](#key-data-flows)
  - [LC-MS mode](#lc-ms-mode)
  - [MS-only mode](#ms-only-mode)
- [Dependencies](#dependencies)
- [Build and distribution](#build-and-distribution)

---

## Overview

SweetSuite is a PyQt6 desktop application for processing **LC-MS** and **MS-only**
glycoproteomics data. Its two main capabilities are:

1. **Retention time alignment** — corrects systematic RT drift across mzXML files
   using a set of user-defined alignment features.
2. **Targeted analyte quantitation** — integrates isotopic peaks in sum spectra,
   applies polynomial m/z calibration, and reports areas, mass errors, S/N ratios,
   and isotopic pattern quality (IPQ) per analyte per file.

The application is intentionally structured in layers:

```
GUI layer (PyQt6)
     │
     └─ Batch orchestration (BatchWorker, QThread)
             │
             ├─ Input parsing   (InputAnalyte, BlockParser)
             ├─ Data I/O        (Mzxml, MzxmlDataBlock, SumSpectrum)
             ├─ Chromatography  (AlignmentFeature, Eic, alignment)
             ├─ Mass spectrometry (MassSpectrum, Analyte, IsotopicPeak, Calibrant)
             └─ Reporting       (ms_tables, write_to_excel)
```

---

## Directory layout

```
SweetSuite/
│
├── main.py                        # Application entry point
├── requirements.txt               # Python dependencies
├── SweetSuite.bat                 # Windows launcher
├── compile_to_exe.sh              # PyInstaller build script
├── main.spec                      # PyInstaller spec file
│
├── blocks/                        # Block definition files (.block), scanned recursively
├── docs/                          # Documentation (this file)
├── logs/                          # Runtime log files (auto-created)
├── tests/                         # Test suite (currently a stub)
│
└── sweet_suite/                   # Main Python package
    ├── __init__.py                # Version metadata
    ├── input_analyte.py           # Analyte composition + isotopologue computation
    ├── mzxml.py                   # mzXML file reader, alignment, sum spectra
    ├── mzxml_data_block.py        # Single mzXML scan decoder
    ├── sum_spectrum.py            # Summed spectrum over an RT window
    │
    ├── chromatography/            # Retention time alignment
    │   ├── alignment.py           # Curve fitting and alignment plotting
    │   ├── alignment_feature.py   # One alignment target (m/z + required RT)
    │   └── eic.py                 # Extracted ion chromatogram (EIC)
    │
    ├── mass_spectrometry/         # Peak integration and calibration
    │   ├── isotopic_peak.py       # Single isotopic peak extraction + background
    │   ├── calibrant.py           # Calibrant peak (spline-based m/z refinement)
    │   ├── analyte.py             # Aggregated analyte result (area, S/N, IPQ)
    │   ├── mass_spectrum.py       # Full spectrum: calibration + quantitation
    │   └── plotting.py            # Calibration curve and failure plots
    │
    ├── reporting/
    │   └── ms_tables.py           # Build long-format quantitation DataFrames
    │
    ├── resources/
    │   ├── constants.py           # ISOTOPES table (masses + natural abundances)
    │   └── templates/             # Excel templates, default settings CSV, block template
    │
    ├── utils/
    │   └── utils.py               # Shared helpers (resource_path, write_to_excel, …)
    │
    └── gui/                       # PyQt6 GUI layer
        ├── main_window.py         # MainWindow: thin coordinator
        ├── dialogs/               # Modal dialogs
        │   └── advanced_settings_handler.py
        ├── managers/              # Business-logic managers
        │   ├── batch_coordinator.py
        │   ├── block_parser.py
        │   ├── calibration_table_manager.py
        │   ├── file_handlers.py
        │   ├── settings_manager.py
        │   └── template_manager.py
        ├── qtdesigner_files/      # Qt Designer .ui files + generated Python
        │   ├── gui_main.ui / .py
        │   ├── gui_advanced_settings.ui / .py
        │   └── batch_status.ui / .py
        ├── ui/                    # UI helpers and setup
        │   ├── ui_helpers.py
        │   └── ui_setup.py
        ├── widgets/               # Custom PyQt6 widgets
        │   └── scientific_spin_box.py
        ├── workers/               # Background thread workers
        │   └── batch_worker.py
        ├── viewers/               # In-app data viewers
        │   └── xy_spectrum_viewer.py
        └── assets/                # SVG icons (Google Material Icons)
```

---

## Entry point

**`main.py`**

Responsible for bootstrapping the application:

1. Installs a Qt message handler to suppress noisy `qt.qpa` platform warnings
   (relevant for RDP sessions).
2. Creates the `logs/` directory and configures a global
   `logging.basicConfig` that writes to both a timestamped log file and
   `stdout`.
3. Creates the `QApplication`, applies a custom Fusion-based light palette,
   and shows `MainWindow`.
4. When running as a frozen PyInstaller executable, opens and closes the splash
   screen via `pyi_splash`.

---

## Package: `sweet_suite`

### Top-level modules

#### `__init__.py`
Exposes version metadata used throughout the application:
`__version__`, `__year__`, `__authors__`, `__organization__`.

---

#### `input_analyte.py` — `InputAnalyte`

Translates a user-supplied analyte name (e.g. `IgGI1H3N4F1`) into a fully
described analyte object ready for quantitation.

**Responsibilities:**

- **Name parsing** — uses a regex to split the analyte name into
  `(block_name, count)` pairs and looks up each block in the blocks dictionary.
- **Elemental composition** (`get_variable_composition`) — sums the elemental
  counts (`carbons`, `hydrogens`, etc.) of all constituent blocks, plus the
  counts from the optional mass modifier block (if one is selected).
- **Monoisotopic mass** (`get_monoisotopic_mass`) — sums the block masses,
  plus the mass modifier block mass if applicable.
- **Isotopologue distribution** (`compute_distribution`) — uses sequential
  convolution over elements rather than enumerating all combinations at once.
  Starting from a delta distribution at the monoisotopic mass, the method
  folds one element's heavy-isotope distribution at a time into the running
  list, merging peaks within instrument resolution after each step. This is
  O(n_elements × n_peaks) rather than O(product of per-element distribution
  sizes), making it fast even for large glycans with heavy charge carriers
  such as potassium.
- **Reference DataFrame** (`get_reference_df`) — for each charge state in
  `[charge_min, charge_max]`, builds the full ion composition (analyte +
  modifier + n × carrier) and calls `compute_distribution` with that
  composition. This ensures the isotopic contribution of the charge carrier
  (e.g. ⁴¹K for potassium) is correctly included per charge state. Produces
  one row per selected isotopologue with the expected m/z, relative abundance,
  retention time window, calibration flag, `charge_carrier`, and
  `mass_modifier` columns. This DataFrame drives peak integration in
  `MassSpectrum`.

---

#### `mzxml.py` — `Mzxml`

Interface for reading, processing, and aligning mzXML files.

**Responsibilities:**

- **Parsing** — reads the mzXML XML as a string, splits on `<scan` boundaries,
  and creates one `MzxmlDataBlock` per scan.
- **Spectrum construction** — `create_mass_spectra()` decompresses zlib data
  and unpacks interleaved m/z–intensity float arrays into 2D NumPy arrays.
- **Sum spectra** — `create_sum_spectrum(time, time_window, resolution)` accumulates
  all scans within `[time ± time_window]` into a `SumSpectrum`, merging data
  points within the given resolution tolerance.
- **Retention time alignment** — three methods orchestrate the full alignment
  workflow for one file:
  1. `get_alignment_fit_eics(alignment_features, min_peaks)` — extracts EICs for
     each `AlignmentFeature` and returns those that pass the S/N cut-off.
  2. `plot_alignment_fit(fit_eics)` — fits the time-mapping function and returns a
     `matplotlib` figure for the PDF alignment report.
  3. `align_retention_times(fit_eics)` — rewrites the mzXML XML with adjusted
     `retentionTime` attributes.

---

#### `mzxml_data_block.py` — `MzxmlDataBlock`

Parses one `<scan>` element from an mzXML file.

Extracts retention time, compression type, byte order, and encoding precision
from the raw XML, then base64-decodes the peak data using
`pybase64` (a C-backed base64 library), and stores the result as a
`decoded_data` dictionary. The raw XML string is discarded after parsing
to free memory.

---

#### `sum_spectrum.py` — `SumSpectrum`

A lightweight container for a summed mass spectrum:

- Stores the source file name, center time, time window, and a 2D NumPy array
  of m/z–intensity pairs.
- `write_xy()` — exports the spectrum to a tab-delimited `.xy` file.

---

### chromatography

#### `alignment.py`

Module-level functions (no class):

- **`fit_power(eics, min_peaks)`** — collects `(observed_RT, required_RT)` pairs
  from a list of `Eic` objects and fits a power function
  $Y = a X^b + c$ using `scipy.optimize.curve_fit`. Falls back to a linear fit
  if the power fit fails. Returns `None` if there are fewer than `min_peaks`
  valid features.
- **`plot_fit(...)`** — produces a matplotlib figure that visualises the
  alignment fit, including the data points, the fitted curve, and a 1:1
  reference line. This figure is saved to the alignment PDF report.

#### `alignment_feature.py` — `AlignmentFeature`

Represents one entry in the alignment list (one row in the alignment `.xlsx`).
Stores its exact m/z, required RT, search windows, S/N cut-off, and
`required` flag. Provides:

- `get_intensity()` — maximum intensity within the m/z window in one spectrum.
- `create_eic()` — builds an `Eic` from all scans of an `Mzxml` file.

#### `eic.py` — `Eic`

An extracted ion chromatogram for one alignment feature. Computes:

- **`peak_data`** — subset of the chromatogram within the alignment time window.
- **`maximum`** — `(time, intensity)` at the peak apex.
- **`background_and_noise`** — mean and standard deviation of the background
  region outside the peak window.
- **`signal_to_noise`** — `(max_intensity − background) / noise`.

Whether an `Eic` is considered usable for alignment depends on its S/N
exceeding `alignment_sn_cutoff`.

---

### mass\_spectrometry

#### `isotopic_peak.py` — `IsotopicPeak`

Base class for a single isotopic peak in a spectrum. Given an exact m/z and an
integration window, it slices the relevant region from the spectrum array and
provides:

- `get_area()` — trapezoidal integration over `[mz_exact ± mz_window]`.
- `get_maximum_intensity()` — returns the intensity of the highest local
  maximum within `[mz_exact ± integration_mz_window]`. Falls back to the
  highest intensity point in the window if no local maximum is found.
- `get_spline_maximum()` — fits a cubic spline over `[mz_exact ± mz_window]`
  and returns the `(m/z, intensity)` of the highest local maximum. Falls back
  to raw data if fewer than 4 points or spline fitting fails. If no local
  maximum is found in either case, returns the highest intensity point.
  Used for mass error calculation and calibration.
- `get_mass_error_ppm()` — calculates the mass error by comparing the
  spline-derived observed m/z to `mz_exact`.
- `get_background_and_noise()` — defines evenly-spaced m/z bins around
  `target_mz` (bin centers separated by the ¹³C–¹²C mass difference / charge).
  Evaluates all windows of 5 consecutive bins and selects the one with the
  lowest average intensity as the background region. Background is the mean
  area / intensity of those 5 bins; noise is their standard deviation.

#### `calibrant.py` — `Calibrant(IsotopicPeak)`

Extends `IsotopicPeak` with spline-based m/z refinement for calibration.
Calls `get_spline_maximum()` to locate the highest local maximum and obtain
a sub-data-point `mz_observed`. This observed m/z is compared against the
theoretical `mz_exact` to produce one calibration data point.

#### `analyte.py` — `Analyte`

Aggregates the integration results for all isotopologue peaks of one analyte
at one charge state into high-level metrics:

| Attribute | Description |
|---|---|
| `total_area` | Sum of per-peak trapezoidal areas (or maximum intensities when `use_peak_height=True`) |
| `total_background` | Sum of background areas (or average background intensities when `use_peak_height=True`) |
| `total_noise` | Sum of per-peak noise values |
| `total_area_background_subtracted` | `total_area − total_background` |
| `signal_to_noise` | S/N of the most abundant isotopologue |
| `mass_error_ppm` | ppm error of the most abundant isotopologue |
| `isotopic_pattern_quality` | IPQ: similarity of observed to theoretical isotope ratios |

Accepts an optional `use_peak_height: bool` flag (default `False`). When `True`, all
area-based calculations switch to using the `maximum_intensity` column from the peaks
DataFrame, and per-peak background subtraction uses `background_and_noise[0]` (average
background intensity) instead of `background_and_noise[1]` (background area).
S/N computation is intensity-based regardless of this flag.

#### `mass_spectrum.py` — `MassSpectrum`

The central quantitation object. Given raw `(m/z, intensity)` data and a
reference DataFrame (from `InputAnalyte`), it:

1. **Calibration** — instantiates `Calibrant` objects for each flagged
   calibrant peak, checks their S/N against `min_calibrant_sn`, fits a
   second-degree polynomial to `(observed_mz → required_mz)` with
   `numpy.polyfit`, then applies the polynomial to shift all m/z values.
   Calibration fails (and is skipped) when fewer than `min_calibrant_number`
   calibrants pass the S/N cut-off.
2. **Peak integration** — for each row in the reference DataFrame, creates an
   `IsotopicPeak`, computes its area, maximum intensity, and background, and stores the results.
3. **Analyte assembly** — groups peaks by `(analyte, charge)` and creates one
   `Analyte` per group, forwarding the `use_peak_height` flag so the correct
   metric is used for all quantitation calculations.

#### `plotting.py`

Standalone plotting functions used by `MassSpectrum`:

- **`plot_polynomial()`** — side-by-side calibration plot (scatter + polynomial
  curve) and error table (pre/post calibration ppm errors, colour-coded).
- **`plot_calibration_failure()`** — simplified plot shown when calibration
  was skipped or failed.

---

### reporting

#### `ms_tables.py`

- **`build_quantitation_table()`** — iterates over a list of `MassSpectrum`
  objects and their `Analyte` children to produce a long-format `DataFrame`
  with one row per `(file, analyte, charge)` combination. Columns include
  `file`, `analyte`, `charge`, `mz_monoisotopic`, `mz_most_abundant`, 
  `isotopic_fraction`, `total_area_background_subtracted`, `mass_error_ppm`,
  `isotopic_pattern_quality`, `signal_to_noise`, `total_area`, 
  `total_background` and `total_noise`.
  Accepts a `use_peak_height: bool` parameter that is forwarded to
  `MassSpectrum.quantify_analytes()` and from there to each `Analyte`.

---

### resources

#### `constants.py`

Defines the `ISOTOPES` dictionary: masses and natural abundances for C, H, O,
N, S, Na, K, Fe, F, and Cl, sourced from the NIST Atomic Weights database.
This is the single authoritative source of isotope data used by both
`InputAnalyte` and `IsotopicPeak`.

#### `templates/`

| File | Purpose |
|---|---|
| `alignment_template.xlsx` | Template Excel file for the alignment list |
| `analytes_template.xlsx` | Template Excel file for the analytes list |
| `template.block` | Template block file with comments explaining the format |
| `default_settings.csv` | Default GUI settings loaded on first run / settings reset |

---

### utils

#### `utils.py`

General-purpose helpers:

- **`resource_path(relative_path)`** — resolves a path relative to the project
  root in development mode, or to `sys._MEIPASS` in a PyInstaller executable.
  Used everywhere a bundled resource (template, icon) is accessed.
- **`format_execution_time(start, end)`** — formats an elapsed time as a
  human-readable `H hours, M minutes, S seconds` string.
- **`write_to_excel(out_path, data_dict)`** — writes one or more `DataFrame`
  objects to an `.xlsx` file using `xlsxwriter`, with auto-adjusted column
  widths and centred text.

---

### gui

The GUI layer is a PyQt6 application. `MainWindow` acts as a thin coordinator
and delegates all non-trivial behaviour to dedicated manager objects.

#### `main_window.py` — `MainWindow(QMainWindow)`

Initialises and wires together all GUI components:

- Calls `UISetup` to apply icons, tooltips, and table styling.
- Creates manager instances and stores them as attributes.
- Connects Qt signals (button clicks, menu actions) to the appropriate
  manager methods.
- Holds the shared application state: `alignment_list_df`, `analytes_list_df`,
  `analytes_ref_df`, `blocks`, and `ms_only_mode`.

#### managers/

Each manager class receives a reference to `MainWindow` (`parent`) and to the
UI object(s) it needs, making them independently testable.

| Class | File | Responsibility |
|---|---|---|
| `BatchCoordinator` | `batch_coordinator.py` | Starts/stops the batch worker thread; shows the progress dialog; routes `pyqtSignal` callbacks to the UI |
| `BatchWorker` | `workers/batch_worker.py` | Runs the complete processing pipeline in a `QThread`; emits progress/finished/error signals |
| `BlockParser` | `block_parser.py` | Reads all `.block` files in the selected directory and builds the `blocks` dict; validates element names and value types; populates the *Charge carrier* dropdown (`update_charge_carriers`) and the *Mass modifier (optional)* dropdown (`update_mass_modifiers`) from the parsed blocks |
| `CalibrationTableManager` | `calibration_table_manager.py` | Populates the interactive calibration S/N table when an analytes list is loaded |
| `FileHandlers` | `file_handlers.py` | Opens file dialogs; reads and validates alignment and analytes Excel files. When an `.xlsx` file is uploaded as the analytes input, detects automatically whether it is an analytes list or a pre-generated reference file, validates accordingly, and routes to the appropriate handler. Reference file validation includes the `charge_carrier` and `mass_modifier` string columns |
| `SettingsManager` | `settings_manager.py` | Exports all GUI settings to CSV; imports settings from CSV; resets to defaults |
| `TemplateManager` | `template_manager.py` | Copies template files (alignment list, analytes list, block) to a user-chosen directory |

#### dialogs/

- **`AdvancedSettingsHandler`** — manages the advanced settings `QDialog`.
  The quadratic m/z-window is entered via six plain `QDoubleSpinBox` widgets:
  a significand (5-decimal coefficient) and an integer exponent for each of
  the three polynomial terms ((m/z)², (m/z), and constant). All six inputs
  are greyed out while the *Use quadratic quantitation m/z window* checkbox
  is unchecked. Also manages
  the *Use peak heights instead of areas for quantitation* checkbox
  (`checkBox_peakHeights`) and the *Save sum spectra as .xy files* checkbox
  (`checkBox_save_xy`), both of which are read by `BatchCoordinator` at
  batch start and persisted via `SettingsManager`. When `save_xy` is enabled,
  `BatchWorker` calls `MassSpectrum.write_xy()` after quantitation, writing
  tab-delimited `.xy` files into a dedicated `xy_<timestamp>/` subdirectory
  inside the batch folder. The written data is the (potentially calibrated)
  `MassSpectrum` content. In MS-only mode the file is only written when at
  least one calibrant is present.

#### ui/

- **`UIHelpers`** — stateless helper methods: `show_message_box()`,
  `disable_spinbox_scroll()`.
- **`UISetup`** — stateless setup methods called once during window
  initialisation: `setup_menu_icons()`, `setup_button_icons()`,
  `setup_tooltips()`, `setup_table_styling()`.

#### widgets/

- **`ScientificSpinBox`** — a `QDoubleSpinBox` subclass that accepts and
  displays values in scientific notation (e.g. `1.23e-08`). Currently not
  used by any dialog, but retained for potential future use.

#### qtdesigner_files/

Contains the `.ui` files (Qt Designer XML) and the corresponding generated
Python classes (`Ui_MainWindow`, `Ui_advanced_settings`, `Ui_batch_status`).
These files should not be edited by hand; re-generate them with
`pyuic6 <file>.ui -o <file>.py` after modifying layouts in Qt Designer.

#### viewers/

- **`xy_spectrum_viewer.py`** — `launch_xy_viewer(parent)` opens a
  `QFileDialog` to select a `.xy` file, loads it with `numpy.loadtxt`, and
  shows a non-modal `QDialog` (`_XYSpectrumDialog`) with an embedded
  `FigureCanvasQTAgg` (matplotlib Qt backend). Large files remain interactive
  through dynamic resampling: an `xlim_changed` callback triggers
  `_minmax_downsample` on every zoom or pan event, capping the number of
  rendered points at `MAX_POINTS` (5 000) while always preserving per-bucket
  min and max so no peaks are dropped. Memory is freed immediately on window
  close via `WA_DeleteOnClose`. Triggered by `Tools → View '.xy' mass
  spectrum` in `MainWindow.connect_signals()`.

#### workers/

- **`BatchWorker(QObject)`** — the core processing engine. Instantiated and
  moved to a `QThread` by `BatchCoordinator`. The `run()` method executes the
  full pipeline sequentially and emits `ref_progress`, `alignment_progress`,
  and `quantitation_progress` signals to drive the progress bar in the UI.
  Accepts `charge_carrier`, `mass_modifier`, and `save_xy` parameters.
  `mass_modifier` defaults to `None` when no modifier is selected.
  `save_xy` (default `False`) triggers `MassSpectrum.write_xy()` after
  quantitation of each spectrum, writing the (potentially calibrated) spectrum
  as a tab-delimited `.xy` file into a `xy_<timestamp>/` subdirectory. In
  MS-only mode this only fires when calibrants are present.
  When a pre-loaded reference DataFrame (`analytes_ref_df`) is available,
  the reference generation step is skipped and the DataFrame is written
  directly to disk via `write_ref_df()`.

---

## Block files

Block files (`.block`) in the `blocks/` directory define the molecular building
blocks from which analyte names are composed. The directory is scanned
recursively, so block files can be organized freely in subdirectories.

**Format** (plain text, `#` for comments):
```
# IgG1 N297 EEQYNSTYR
mass: 1188.5047307674
charge: 0
carbons: 50
hydrogens: 72
nitrogens: 14
oxygens: 20
sulfurs: 0
```

`mass` is the monoisotopic mass contribution of the block (Da).
`charge` is the fixed charge contribution (e.g. `1` for a proton carrier).
`mass_modifier: 1` marks a block as a selectable mass modifier (e.g. water
loss, derivatisation reagent). Such blocks appear in the *Mass modifier
(optional)* dropdown in the GUI. When selected, the block's mass and elemental
counts are added on top of the analyte before any isotopologue calculations.
Elemental counts (`carbons`, `hydrogens`, `nitrogens`, `oxygens`, `sulfurs`,
and additional element keys) are used by `InputAnalyte` to compute the
isotopologue distribution.

Analyte names are formed by concatenating block names with integer
multipliers, e.g. `IgGI1H3N4F1` resolves to one `IgGI` block, three `H`
(hexose) blocks, four `N` (HexNAc) blocks, and one `F` (fucose) block.
The charge carrier block (e.g. `proton`, `potassium`) and the optional mass
modifier block are specified separately in the GUI.

---

## Key data flows

### LC-MS mode

```
User uploads:
  - mzXML files (folder)
  - alignment list (.xlsx)       [optional]
  - analytes list (.xlsx)        [optional]
      OR reference file (.xlsx)  [optional, skips step 1]

BatchCoordinator.start_batch_process()
  └─ BlockParser.parse_blocks()  → blocks dict
  └─ BatchWorker(run in QThread)

  1. Build reference table
     [skipped if a reference file was uploaded directly]
     InputAnalyte(blocks, row)   → reference_df (per analyte)

  2. For each mzXML file:
     a. Read file
        Mzxml(path)
          └─ MzxmlDataBlock (per scan) → decoded bytes
          └─ create_mass_spectra()    → list of (RT, ndarray)

     b. Retention time alignment  [if alignment list provided]
        AlignmentFeature.create_eic(Mzxml) → Eic
        Eic: compute maximum, S/N
        Mzxml.get_alignment_fit_eics(features, min_peaks) → fit_eics
        Mzxml.plot_alignment_fit(fit_eics)  → alignment PDF (matplotlib)
        Mzxml.align_retention_times(fit_eics) → rewrite RT values in XML

     c. Sum spectra generation  [if analytes list provided]
        Mzxml.create_sum_spectrum(time, time_window, resolution)
          └─ SumSpectrum (per RT window)

     d. Calibration + quantitation  [per SumSpectrum]
        MassSpectrum(SumSpectrum.data, calibrants_list, reference_df)
          └─ Calibrant (per calibrant peak)
               └─ IsotopicPeak: extract data, spline max → mz_observed
          └─ numpy.polyfit(mz_observed, mz_exact) → polynomial
          └─ apply polynomial → data_calibrated
          └─ IsotopicPeak (per reference row): area, background, noise
          └─ Analyte (per analyte+charge): aggregate metrics

     e. Reporting
        ms_tables.build_quantitation_table(mass_spectra)
        utils.write_to_excel()  → results .xlsx

  BatchCoordinator: update progress bar, show completion message
```

### MS-only mode

The MS-only mode skips mzXML parsing and alignment entirely.
The user provides `.xy` files (two-column tab-delimited m/z and intensity).
`BatchWorker` reads each `.xy` file directly into a NumPy array, wraps it
in a `SumSpectrum`, and proceeds with the same calibration and quantitation
steps as LC-MS mode.

---

## Dependencies

| Package | Purpose |
|---|---|
| `PyQt6` | GUI framework |
| `numpy` | Numerical arrays, signal processing |
| `scipy` | Curve fitting (`curve_fit`), spline interpolation |
| `pandas` | Tabular data (analyte lists, results) |
| `matplotlib` | Alignment PDF report, calibration plots |
| `openpyxl` | Reading `.xlsx` template and input files |
| `xlsxwriter` | Writing `.xlsx` output files |
| `pybase64` | Fast base64 decoding of mzXML peak data |

---

## Build and distribution

- **`SweetSuite.bat`** — activates the local virtual environment and runs
  `main.py` directly.
- **`compile_to_exe.sh`** — builds a standalone Windows executable using
  [PyInstaller](https://pyinstaller.org/) with the `main.spec` spec file.
  The spec file bundles all `blocks/`, `sweet_suite/resources/templates/`,
  and GUI assets. A splash screen image is also bundled.
- **`build/`** — PyInstaller build artefacts (`.toc`, `.pyz`, intermediate
  files); not committed to version control.
