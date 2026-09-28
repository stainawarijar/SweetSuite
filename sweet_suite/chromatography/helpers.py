import numpy as np


def parse_number(value: str) -> float:
    """Replaces comma used as decimal separator by a point.

    Used when reading LC-FLD data.

    Args:
        value: Value as a string, using either comma (e.g. `1.259,25`) or point
        (`1259.25`) as decimal separator.
    
    Returns:
        The number as a float.
    """
    value = value.strip()
    # A comma marks European formatting: 1.259,25 -> 1259.25.
    # Without a comma, retain the dot as the decimal separator.
    if "," in value:
        value = value.replace(".", "").replace(",", ".")

    return float(value)


def parse_fld_txt_file(path: str) -> np.ndarray:
    """Read in HPLC-FLD data from a `.txt` file.

    Args:
        path: Path to text file containing data.
    """
    with open(path, encoding="utf-8-sig") as file:
        for line in file:
            if line.strip() in {"Raw Data:", "Chromatogram Data:"}:
                break
        else:
            raise ValueError("Chromatogram Data section not found")

    next(file)  # Time, step and value column names

    rows = []
    for line in file:
        columns = line.rstrip().split("\t")
        if len(columns) >= 3:
            rows.append((
                parse_number(columns[0]),
                parse_number(columns[2]),
            ))

    return np.asarray(rows, dtype=float)



    