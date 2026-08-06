import pandas as pd

from ..mass_spectrometry.mass_spectrum import MassSpectrum


def build_quantitation_table(
        filename: str,
        mass_spectra: list[MassSpectrum],
        analytes_ref: pd.DataFrame,
        output_params: list[str],
        use_peak_height: bool = False
) -> pd.DataFrame:
    """Create a table in long format with quantitation results for all 
    sum spectra of an mzXML file.

    Args:
        filename: Name of the mzXML file.
        mass_spectra: A list with instances of MassSpectrum.
        analytes_ref: Analytes reference dataframe.
        output_params: A list with required output parameters.
        use_peak_height: If True, use maximum intensity instead of trapezoidal
            area for quantitation.
    
    Returns:
        A pandas dataframe with the following columns: `file`, `analyte`,
        `charge`, `mz_monoisotopic`, `mz_most_abundant`, `isotopic_fraction` 
        and a column for each specified output parameter.
    """
    # Build dataframe with analyte names, charge, isotopologue number and m/z.
    ref_parts = (
        analytes_ref["peak"]
        .astype(str)
        .str.split("_", n=2, expand=True)
    )
    ref_df = pd.DataFrame({
        "analyte": ref_parts[0],
        "charge": ref_parts[1].astype(int),
        "iso": ref_parts[2].astype(int),
        "mz": analytes_ref["mz"],
        "relative_area": analytes_ref["relative_area"]
    })

    # Create list with order of analytes (dropping duplicates).
    analyte_order = (
        ref_df["analyte"]
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    # Build a dictionary with exact m/z values of the most abundant 
    # isotopic peaks.
    ref_mz_most_abundant = ref_df.loc[
        ref_df.groupby(["analyte", "charge"])["relative_area"].idxmax(),
        ["analyte", "charge", "mz"]
    ]
    mz_most_abundant_lookup = {
        # (analyte, charge): m/z
        (row.analyte, int(row.charge)): row.mz
        for row in ref_mz_most_abundant.itertuples(index=False)
    }

    # Build a dictionary with exact m/z values of the monoisotopic peaks.
    ref_mz_monoisotopic = ref_df.loc[
        ref_df.groupby(["analyte", "charge"])["iso"].idxmin(),
        ["analyte", "charge", "mz"]
    ]
    mz_monoisotopic_lookup = {
        (row.analyte, int(row.charge)): row.mz
        for row in ref_mz_monoisotopic.itertuples(index=False)
    }

    # Build a table with file, analyte and charge columns, ensuring that
    # rows exist even when spectra are uncalibrated.
    ref_pairs = (
        ref_df[["analyte", "charge"]]
        .drop_duplicates(ignore_index=True)
    )
    base_rows = []
    for _, row in ref_pairs.iterrows():
        base_rows.append({
            "file": filename,
            "analyte": row["analyte"],
            "charge": int(row["charge"])
        })
    base = pd.DataFrame(base_rows, columns=["file", "analyte", "charge"])

    # Attach m/z columns to the base grid.
    base["mz_most_abundant"] = [
        mz_most_abundant_lookup.get((analyte, charge), pd.NA)
        for analyte, charge in zip(base["analyte"], base["charge"])
    ]
    base["mz_monoisotopic"] = [
        mz_monoisotopic_lookup.get((analyte, charge), pd.NA)
        for analyte, charge in zip(base["analyte"], base["charge"])
    ]

    # Accumulate first non-empty values for `isotopic_fraction` and all
    # requested extra parameters, per analyte and charge.
    def put_first(d: dict, key: str, val):
        """Store the first non-empty value for a column."""
        if key not in d or pd.isna(d[key]):
            if pd.notna(val):
                d[key] = val
    
    keep = {}  # (filename, analyte, charge): {parameters}
    skipped_labels: set[str] = set()
    for spectrum in mass_spectra:
        analytes = spectrum.quantify_analytes(analytes_ref, use_peak_height=use_peak_height)
        skipped_labels.update(getattr(spectrum, "skipped_analytes", set()))
        if not analytes:
            continue  # Uncalibrated, grid keeps blank row for it.
        for analyte in analytes:
            k = (filename, analyte.name, int(analyte.charge))
            slot = keep.setdefault(k, {})
            put_first(
                slot, "isotopic_fraction",
                getattr(analyte, "isotopic_fraction", pd.NA)
            )
            for param in output_params:
                put_first(slot, param, getattr(analyte, param, pd.NA))
    
    # Convert accumulated values to a DataFrame.
    cols = ["file", "analyte", "charge", "isotopic_fraction", *output_params]
    found_rows = []
    for (f, analyte, charge), vals in keep.items():
        row = {"file": f, "analyte": analyte, "charge": charge}
        row["isotopic_fraction"] = vals.get("isotopic_fraction", pd.NA)
        for param in output_params:
            row[param] = vals.get(param, pd.NA)
        found_rows.append(row)
    
    found = (
        pd.DataFrame(found_rows, columns=cols)
        if found_rows else pd.DataFrame(columns=cols)
    )

    # Remove analytes that were out of range in every spectrum (i.e. skipped
    # but never successfully quantified in any spectrum).
    if skipped_labels:
        found_labels = set(
            (found["analyte"].astype(str) + "_" + found["charge"].astype(str)).tolist()
        )
        labels_to_remove = skipped_labels - found_labels
        if labels_to_remove:
            label_col = base["analyte"].astype(str) + "_" + base["charge"].astype(str)
            base = base[~label_col.isin(labels_to_remove)].reset_index(drop=True)

    # Left-join output parameters onto the base grid.
    out = base.merge(
        found, on=["file", "analyte", "charge"], how="left"
    )

    # Sort rows by analyte and charge.
    out["analyte"] = pd.Categorical(
        out["analyte"],
        categories=analyte_order,
        ordered=True
    )
    out = out.sort_values(["file", "analyte", "charge"]).reset_index(drop=True)

    # Reorder columns.
    final_cols = [
        "file",
        "analyte",
        "charge",
        "mz_most_abundant",
        "mz_monoisotopic",
        "isotopic_fraction",
        *output_params
    ]
    out = out[final_cols]

    return out
