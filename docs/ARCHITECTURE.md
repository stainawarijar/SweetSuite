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
  - [LC-FLD scaffold](#lc-fld-scaffold)
- [Dependencies](#dependencies)
- [Build and distribution](#build-and-distribution)

---

## Overview

SweetSuite is a PyQt6 desktop application with **LC-MS**, **MS-only**, and
**LC-FLD** settings pages. LC-MS and MS-only processing are implemented;
LC-FLD currently provides GUI wiring and a batch-worker scaffold, without
raw-data processing or results export. Its two implemented processing capabilities are:

1. **Retention time alignment** — corrects systematic RT drift across mzXML files
   using a set of user-defined alignment features.
2. **Targeted analyte quantitation** — integrates isotopic peaks in sum spectra,
   applies polynomial m/z calibration, and reports areas, mass errors, S/N ratios,
   and isotopic pattern quality (IPQ) per analyte per file.

The application is intentionally structured in layers:

```
GUI layer (PyQt6)
     │
     └─ BatchCoordinator (shared progress dialog and QThread lifecycle)
             ├─ FldBatchWorker (LC-FLD scaffold; no analysis yet)
             └─ MsBatchWorker (LC-MS and MS-only processing)
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
│
├── blocks/                        # Block definition files (.block), scanned recursively
├── docs/                          # Documentation (this file)
├── tests/                         # GUI regression tests using unittest
├── logs/                          # Runtime log files (auto-created)
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
    ├── mass_spectrometry/         # Peak quantitation and calibration
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
        ├── processing_mode.py     # ProcessingMode enum: LC-MS, MS-only, LC-FLD
        ├── ms_page.py             # Persistent settings page for both MS modes
        ├── fld_page.py            # LC-FLD settings page and input path selectors
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
        │   ├── gui_ms.ui / .py
        │   ├── gui_lc_fld.ui / .py
        │   ├── gui_chromatogram.ui / .py
        │   ├── gui_advanced_settings.ui / .py
        │   └── batch_status.ui / .py
        ├── ui/                    # Shared UI helpers
        │   └── ui_helpers.py
        ├── widgets/               # Custom PyQt6 widgets
        │   └── scientific_spin_box.py
        ├── workers/               # Background thread workers
        │   ├── ms_batch_worker.py  # MsBatchWorker: implemented MS pipeline
        │   └── fld_batch_worker.py # FldBatchWorker: LC-FLD scaffold
        ├── viewers/               # In-app data viewers
        │   ├── xy_spectrum_viewer.py
        │   └── chromatogram_viewer.py # LC-FLD viewer with synthetic placeholder plot
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
   Before creating the application, configures Chromium logging and enables
   shared OpenGL contexts for Qt WebEngine. On Windows, also sets an explicit
   application ID for the taskbar icon.

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
- **Isotopologue distribution** (`compute_distribution`) — builds an isotopic
  fine-structure pattern by successively convolving element-specific isotope
  patterns. Configurations below the probability threshold are discarded
  while generating elemental patterns and after each convolution. The fine
  structure is then collapsed into nominal `M`, `M+1`, `M+2`, … groups by
  extra-neutron count; each group's mass is its probability-weighted average.
  The signed charge-state electron-mass correction is included.
- **Reference DataFrame** (`get_reference_df`) — for each charge state in
  `[charge_min, charge_max]`, builds the full ion composition (analyte +
  modifier + n × carrier) and calls `compute_distribution` with that
  composition. This ensures the isotopic contribution of the charge carrier
  (e.g. ⁴¹K for potassium) is correctly included per charge state. Produces
  one row per selected isotopologue with the expected m/z, relative abundance,
  retention time window, calibration flag, `charge_carrier`, and
  `mass_modifier` columns. This DataFrame drives peak quantitation in
  `MassSpectrum`.

---

#### `mzxml.py` — `Mzxml`

Interface for reading, processing, and aligning mzXML files.

**Responsibilities:**

- **Parsing** — reads the mzXML XML line by line and creates one
  `MzxmlDataBlock` per scan.
- **Spectrum construction** — `create_mass_spectra()` Base64-decodes the
  selected scans, decompresses zlib data, and unpacks interleaved
  m/z–intensity float arrays into 2D NumPy arrays.
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

Extracts retention time, compression type, byte order, encoding precision, and
the Base64 peak text from the raw XML and stores them in an `encoded_data`
dictionary. Base64 decoding with `pybase64` is deferred until a spectrum is
needed. The raw XML string is discarded after parsing to free memory.

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

Base class for a single isotopic peak in a spectrum. Given an exact m/z and a
quantitation window, it slices the relevant region from the spectrum array and
provides:

- `get_area()` — trapezoidal quantitation over `[mz_exact ± mz_window]`.
- `get_maximum_intensity()` — returns the intensity of the highest local
  maximum within `[mz_exact ± quantitation_mz_window]`. Returns `0.0` if the
  window contains data but no local maximum, and `NaN` if it contains no data.
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

Aggregates the quantitation results for all isotopologue peaks of one analyte
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

The central spectrum-level quantitation object. It stores raw `(m/z, intensity)`
data, creates `Calibrant` observations from the calibrant table supplied for
its retention-time window, fits or applies calibration when calibrants or fit
coefficients are assigned, and quantifies analytes from a reference DataFrame.

1. **Calibration** — `fit_calibration()` fits the required correction
   `mz_exact - mz_observed` as a quadratic function of observed m/z. The fitted
   correction is added to every observed m/z value. In LC-MS mode,
   `MsBatchWorker` applies the per-window S/N thresholds, pools qualifying
   calibrants from all enabled sum spectra in an mzXML file, enforces the
   minimum calibrant count on that pool, fits once, and supplies the resulting
   coefficients to every enabled `MassSpectrum` for that file.
2. **Peak quantitation** — for each row in the reference DataFrame, creates an
   `IsotopicPeak`, computes its area, maximum intensity, mass error, background,
   and noise, and stores the results. An analyte is skipped when its required
   quantitation or background windows extend beyond the spectrum m/z range.
3. **Analyte assembly** — groups peaks by `(analyte, charge)` and creates one
   `Analyte` per group, forwarding the `use_peak_height` flag so the correct
   metric is used for all quantitation calculations.
4. **Output** — `plot_calibration()` creates the active calibration figure,
   displaying either mass errors in ppm or required m/z corrections, and
   `write_xy()` exports calibrated or uncalibrated spectrum data according to
   calibration status.

#### `plotting.py`

Contains the legacy standalone `plot_polynomial()` helper for plotting an
observed-to-exact m/z polynomial and a pre/post-calibration error table. The
current batch pipeline does not call this helper; active calibration figures
are produced by `MassSpectrum.plot_calibration()`.

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
  `MassSpectrum.quantify_analytes()` and from there to each `Analyte`. The
  reference table supplies a base row for every analyte/charge pair, so failed
  calibration leaves blank result fields instead of dropping the row. Analytes
  whose required m/z windows are outside every relevant spectrum are removed
  from the final table.

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
| `lc_ms_alignment_template.xlsx` | LC-MS alignment list template |
| `ms_analytes_template.xlsx` | Analytes list template shared by LC-MS and MS-only |
| `lc_fld_alignment_template.xlsx` | LC-FLD alignment list template |
| `lc_fld_peaks_template.xlsx` | LC-FLD peaks list template |
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
  widths and centred text. DataFrames exceeding Excel's row limit are divided
  across numbered worksheets by `split_excel_sheet()`.

---

### gui

The GUI layer is a PyQt6 application. `MainWindow` acts as a thin coordinator
and delegates all non-trivial behaviour to dedicated manager objects.

#### `main_window.py` — `MainWindow(QMainWindow)`

Initialises and wires together all GUI components:

- Applies main-window menu icons and global widget behaviour.
- Creates manager instances and stores them as attributes.
- Connects Qt signals (button clicks, menu actions) to the appropriate
  manager methods.
- Holds the shared application state: `alignment_list_df`, `analytes_list_df`,
  `analytes_ref_df`, `blocks`, `ms_only_mode`, `ref_file_mode`, and `processing_mode`.
- Hosts persistent MS and FLD forms in the Designer shell's `stackedWidget`.
  The shell UI is `ui`; managers for MS settings receive `ms_ui`, while FLD
  startup reads `fld_ui`. Changing pages preserves their widget values.
- Lazily imports the spectrum and chromatogram viewers when opened, deferring
  Plotly and Qt WebEngine imports until needed.
- Uses the fixed launch size from the Designer shell, with minimize and close
  title-bar controls.

#### Settings pages and processing mode

- **`ProcessingMode`** (`processing_mode.py`) defines `LC_MS`, `MS_ONLY`, and
  `LC_FLD`. The mode selector switches between `MsPage` and `FldPage`.
- **`MsPage`** (`ms_page.py`) wraps `gui_ms.py` and is shared by both MS modes.
  It owns its button icons, tooltips, and calibration-table styling. MS-only
  mode disables alignment and retention-time controls.
- **`FldPage`** (`fld_page.py`) wraps the generated `gui_lc_fld.py` and owns its
  icons and tooltips through dedicated setup methods. `MainWindow` connects its
  folder and Excel-list selectors and clear buttons, consistently with the MS
  page. The page stores paths in widgets; FLD input tables are not parsed or
  validated yet. The inherited widget names `path_mzxml` and
  `open_mzxml_path` refer to the FLD raw-data folder on this page.
- A validated MS analytes or reference file determines the MS mode from its
  retention-time columns and locks the mode selector until the file is cleared.
  Clearing the input restores LC-MS mode. A rejected replacement preserves the
  existing input and mode. A reference file also disables controls whose values
  are supplied by that file.
- LC-FLD mode disables MS settings import/export/reset, advanced settings, the
  mass-spectrum viewer, and MS template actions. FLD templates and the
  chromatogram viewer remain separate menu actions.

#### managers/

Each manager class receives a reference to `MainWindow` (`parent`) and to the
UI object(s) it needs, making them independently testable.

| Class | File | Responsibility |
|---|---|---|
| `BatchCoordinator` | `batch_coordinator.py` | Creates the MS or FLD worker through separate startup methods; shares thread lifecycle, cancellation, progress dialog, and event handling |
| `BlockParser` | `block_parser.py` | Reads all `.block` files in the selected directory and builds the `blocks` dict; validates element names and value types; populates the *Charge carrier* dropdown (`update_charge_carriers`) and the *Mass modifier (optional)* dropdown (`update_mass_modifiers`) from the parsed blocks |
| `CalibrationTableManager` | `calibration_table_manager.py` | Populates the interactive calibration S/N table when an analytes list is loaded |
| `FileHandlers` | `file_handlers.py` | Opens file dialogs; reads and validates alignment and analytes Excel files. When an `.xlsx` file is uploaded as the analytes input, detects automatically whether it is an analytes list or a pre-generated reference file, validates accordingly, and routes to the appropriate handler. Reference file validation includes the `charge_carrier` and `mass_modifier` string columns |
| `SettingsManager` | `settings_manager.py` | Exports/imports MS page and advanced settings as CSV; resets them to defaults |
| `TemplateManager` | `template_manager.py` | Copies LC-MS alignment, MS analytes, LC-FLD alignment/peaks, and block templates to a user-chosen directory |

`start_batch_process()` validates MS inputs and constructs `MsBatchWorker`.
`start_fld_batch_process()` reads paths and alignment settings from `fld_ui`
and constructs `FldBatchWorker`, without parsing MS blocks or reading MS settings.
Both call `start_worker()` to move the worker to a `QThread` and connect signals.
`finished(bool)` and `aborted()` stop the thread and schedule worker deletion;
`error(...)` displays a message, with the worker subsequently emitting a terminal
signal for cleanup. Both workers expose `run()` and cooperative `stop()` methods.

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
  batch start and persisted via `SettingsManager`. A further checkbox controls
  whether calibration figures display required m/z corrections instead of
  mass errors in ppm. When `save_xy` is enabled,
  `MsBatchWorker` calls `MassSpectrum.write_xy()` after quantitation, writing
  tab-delimited `.xy` files into a dedicated `xy_<timestamp>/` subdirectory
  inside the batch folder. The written data is the (potentially calibrated)
  `MassSpectrum` content. In MS-only mode the file is only written when at
  least one calibrant is present.

#### ui/

- **`UIHelpers`** — stateless helper methods: `show_message_box()`,
  `disable_spinbox_scroll()`.

#### widgets/

- **`ScientificSpinBox`** — a `QDoubleSpinBox` subclass that accepts and
  displays values in scientific notation (e.g. `1.23e-08`). Currently not
  used by any dialog, but retained for potential future use.

#### qtdesigner_files/

Contains the `.ui` files (Qt Designer XML) and the corresponding generated
Python classes (`Ui_MainWindow`, settings-page `Ui_Form` classes,
`Ui_advanced_settings`, `Ui_batch_status`). The main form supplies the shell;
MS, LC-FLD, and chromatogram layouts live in their own forms.
These files should not be edited by hand; re-generate them with
`pyuic6 <file>.ui -o <file>.py` after modifying layouts in Qt Designer.

#### viewers/

- **`xy_spectrum_viewer.py`** — `launch_xy_viewer(parent)` opens a
  `QFileDialog` to select up to ten `.xy` files, loads and validates it with
  `numpy.loadtxt`, sorts by m/z, and displays the spectrum using
  `plotly.express.line` in a non-modal Qt dialog with `QWebEngineView`.
  Self-contained HTML is loaded from a temporary file and removed on close.
  Min/max sampling limits rendering to 10,000 points per spectrum. A `QWebChannel`
  bridge resamples the visible range on zoom, pan, and reset, retaining
  the original data in Python. SVG rendering avoids requiring WebGL. The plot uses a distinct color and filename legend entry for each spectrum,
  the `simple_white` template, and m/z and Intensity axis labels. Plotly
  provides zoom, pan, reset, and image export controls. Triggered by
  `Tools → View '.xy' mass spectrum` in `MainWindow.connect_signals()`.

- **`chromatogram_viewer.py`** — `launch_chromatogram_viewer(parent)` opens a
  non-modal `ChromatogramWindow` using `gui_chromatogram.py`. A Plotly figure
  embedded in `QWebEngineView` displays a labelled synthetic chromatogram.
  File loading, peak detection, export, and clear controls are disabled pending
  processing implementation. HTML is stored in a `QTemporaryDir`; open windows
  are retained in a module-level set until destroyed.

#### workers/

- **`MsBatchWorker(QObject)`** (`ms_batch_worker.py`) — the MS processing engine. Instantiated and
  moved to a `QThread` by `BatchCoordinator`. The `run()` method executes the
  full pipeline sequentially and emits `ref_progress`, `alignment_progress`,
  and `quantitation_progress` signals to drive the progress bar in the UI.
  Accepts `charge_carrier`, `mass_modifier`, and `save_xy` parameters.
  `mass_modifier` defaults to `None` when no modifier is selected.
  `save_xy` (default `False`) triggers `MassSpectrum.write_xy()` after
  quantitation of each spectrum, writing the (potentially calibrated) spectrum
  as a tab-delimited `.xy` file into a `xy_<timestamp>/` subdirectory. In
  MS-only mode this only fires when calibrants are present.
  In LC-MS mode, each enabled sum spectrum creates observations for the
  calibrants assigned to its RT window. The worker pools observations that pass
  their window-specific S/N thresholds across all enabled sum spectra in an
  mzXML file. If the global pool meets the minimum calibrant count, one
  quadratic fit is calculated and applied to every enabled sum spectrum in
  that file. Disabled windows neither contribute calibrants nor receive the
  global fit.
  When a pre-loaded reference DataFrame (`analytes_ref_df`) is available,
  the reference generation step is skipped and the DataFrame is written
  directly to disk via `write_ref_df()`.

- **`FldBatchWorker(QObject)`** (`fld_batch_worker.py`) — scaffold that stores
  the raw-data folder, optional peaks/alignment list paths, alignment time
  window, S/N threshold, minimum peak count, and aligned-only quantitation flag.
  It exposes the same completion, abort, error, and progress signals as the MS
  worker. `run()` checks cancellation and folder existence, then reports that
  LC-FLD processing is not implemented and emits `finished(False)`. It does not
  load chromatograms, align, integrate peaks, or write output. The coordinator
  marks all three progress bars as *Not performed* for this scaffold.

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
  └─ MsBatchWorker(run in QThread)

  1. Build reference table
     [skipped if a reference file was uploaded directly]
     InputAnalyte(blocks, row)   → reference_df (per analyte)

  2. For each mzXML file:
     a. Read file
        Mzxml(path)
          └─ MzxmlDataBlock (per scan) → encoded scan data
          └─ create_mass_spectra()    → list of (RT, ndarray)

     b. Retention time alignment  [if alignment list provided]
        AlignmentFeature.create_eic(Mzxml) → Eic
        Eic: compute maximum, S/N
        Mzxml.get_alignment_fit_eics(features, min_peaks) → fit_eics
        Mzxml.plot_alignment_fit(fit_eics)  → alignment PDF (matplotlib)
        Mzxml.align_retention_times(fit_eics) → rewrite RT values in XML

     c. Sum spectra generation  [if analytes or reference input provided]
        Mzxml.create_sum_spectrum(time, time_window, resolution)
          └─ SumSpectrum (per RT window)

     d. Calibration + quantitation  [one global fit per mzXML file]
        MassSpectrum(
            name, file_raw, data_uncalibrated,
            background_mass_window, calibrate,
            calibration_mass_window, calibrants_df, ...
        )
          └─ Calibrant (per locally available calibrant peak)
               └─ IsotopicPeak: extract data, spline max → mz_observed
        MsBatchWorker:
          └─ pool calibrants from enabled sum spectra
          └─ filter each window's calibrants by its S/N threshold
          └─ enforce the minimum count on the global pool
          └─ assign the pool once to MassSpectrum.calibrants_to_fit
        MassSpectrum:
          └─ numpy.polyfit(...) once → global correction coefficients
          └─ apply the same correction to every enabled sum spectrum
          └─ IsotopicPeak (per reference row): area, background, noise
          └─ Analyte (per analyte+charge): aggregate metrics
          └─ plot_calibration() → calibration PDF figure

     e. Reporting
        ms_tables.build_quantitation_table(mass_spectra)
        accumulate results in a temporary CSV across files

  Final export after processing:
    utils.write_to_excel() → results .xlsx with results and settings

  BatchCoordinator: update progress bar, show completion message
```

The worker performs alignment across the batch before starting quantitation;
the diagram above groups the operations by input file for readability. With
aligned-only quantitation enabled, only mzXML files whose basenames start with `aligned` are
used for quantitation.

### MS-only mode

The MS-only mode skips mzXML parsing and alignment entirely.
The user provides `.xy` files (two-column tab-delimited m/z and intensity).
`MsBatchWorker` reads each `.xy` file directly into a NumPy array and constructs
one `MassSpectrum` per file without an intermediate `SumSpectrum`. Calibrants
are filtered using the global S/N cut-off and calibration is applied when the
minimum count is met; m/z-coverage and retention-time-group rules do not apply.
XY export in this mode occurs only when calibrants were supplied, avoiding an
unchanged copy when calibration was not attempted.

### LC-FLD scaffold

```
FldPage: select raw-data folder and optional peaks/alignment Excel paths
  └─ Start processing button
       └─ BatchCoordinator.start_fld_batch_process()
            └─ snapshot fld_ui paths and alignment settings
            └─ start_worker(): FldBatchWorker.run() in QThread
                 ├─ cancellation requested → aborted()
                 ├─ missing folder → error(...) + finished(False)
                 └─ valid folder → "not implemented" message + finished(False)
            └─ close progress dialog, restore GUI, clean up thread
```

No FLD data format is loaded and no results are produced. The separate
chromatogram viewer also uses synthetic data and is not connected to batch
analysis yet.

---

## Dependencies

Runtime dependencies are pinned in `requirements.txt` for Python 3.14.

| Package | Purpose |
|---|---|
| `PyQt6` | GUI framework |
| `PyQt6-WebEngine` | Embedded browser for Plotly viewers |
| `plotly` | Interactive spectrum and placeholder chromatogram plots |
| `numpy` | Numerical arrays, signal processing |
| `scipy` | Curve fitting (`curve_fit`), spline interpolation |
| `pandas` | Tabular data (analyte lists, results) |
| `matplotlib` | Alignment PDF report, calibration plots |
| `openpyxl` | Reading `.xlsx` template and input files |
| `xlsxwriter` | Writing `.xlsx` output files |
| `pybase64` | Fast base64 decoding of mzXML peak data |

PyInstaller is a build-only dependency installed by `compile_to_exe.sh`; it is
not part of `requirements.txt`.

---

## Build and distribution

- **`SweetSuite.bat`** — activates the local virtual environment and runs
  `main.py` directly.
- **`compile_to_exe.sh`** — builds a standalone Windows executable using
  [PyInstaller](https://pyinstaller.org/) in one-file mode. The script creates
  a Python 3.14 virtual environment, installs runtime dependencies and
  PyInstaller, and passes GUI assets and resource templates through
  `--add-data`. It does not use a maintained `.spec` file or bundle a splash
  screen. The `blocks/` directory is copied beside the generated executable so
  users can inspect and organize block definitions independently.
  Pillow is installed for converting the bundled PNG logo to an ICO during the
  build.
- **`build/`** — PyInstaller build artefacts (`.toc`, `.pyz`, intermediate
  files); not committed to version control.
- **`dist/`** — versioned executable output and the accompanying copied
  `blocks/` directory; not committed to version control.
