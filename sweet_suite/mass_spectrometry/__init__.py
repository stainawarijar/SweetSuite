"""Peak extraction, calibrant observations, and analyte quantitation.

`IsotopicPeak` integrates individual peaks and estimates background/noise;
`Calibrant` adds spline-derived observations and S/N for calibration;
`Analyte` aggregates selected isotopologues at one charge state; and
`MassSpectrum` applies quadratic m/z corrections and orchestrates quantitation.
Batch-level calibrant pooling and S/N thresholds live in the GUI batch worker.
"""
