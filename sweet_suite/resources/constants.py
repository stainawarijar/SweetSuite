import re


# Isotopes data for a selection of elements.
# Taken from: https://physics.nist.gov/cgi-bin/Compositions/stand_alone.pl
ISOTOPES = {
    "carbon": {
        "C12": {"mass": 12.000000000, "abundance": 0.9893},
        "C13": {"mass": 13.003354835, "abundance": 0.0107}
    },
    "hydrogen": {
        "H1": {"mass": 1.007825032, "abundance": 0.999885},
        "H2": {"mass": 2.014101778, "abundance": 0.000115}
    },
    "oxygen": {
        "O16": {"mass": 15.994914620, "abundance": 0.99757},
        "O17": {"mass": 16.999131757, "abundance": 0.00038},
        "O18": {"mass": 17.999159613, "abundance": 0.00205}
    },
    "nitrogen": {
        "N14": {"mass": 14.003074004, "abundance": 0.99636},
        "N15": {"mass": 15.000108899, "abundance": 0.00364}
    },
    "sulfur": {
        "S32": {"mass": 31.972071174, "abundance": 0.9499},
        "S33": {"mass": 32.971458910, "abundance": 0.0075},
        "S34": {"mass": 33.967867004, "abundance": 0.0425},
        "S36": {"mass": 35.96708071,  "abundance": 0.0001}
    },
    "sodium": {
        "Na23": {"mass": 22.989769282, "abundance": 1}
    },
    "potassium": {
        "K39": {"mass": 38.963706486, "abundance":  0.93258},
        "K40": {"mass": 39.96399817, "abundance": 0.00012},
        "K41": {"mass": 40.961825258, "abundance": 0.06730}
    },
    "iron": {
        "Fe54": {"mass": 53.9396090, "abundance": 0.05845},
        "Fe56": {"mass": 55.9349363, "abundance": 0.91754},
        "Fe57": {"mass": 56.9353928, "abundance": 0.02119},
        "Fe58": {"mass": 57.9332744, "abundance": 0.00282}
    },
    "fluorine": {
        "F19": {"mass": 18.998403163, "abundance": 1}
    },
    "chlorine": {
        "Cl35": {"mass": 34.96885268, "abundance": 0.7576},
        "Cl37": {"mass": 36.96590260, "abundance": 0.2424}
    }
}

# Masses of particles (Da). 
PROTON_MASS = 1.00727646658  # https://physics.nist.gov/cgi-bin/cuu/Value?mpu
ELECTRON_MASS = 5.4857990904e-4 # https://physics.nist.gov/cgi-bin/cuu/Value?meu


# Create an extra-neutron lookup table.
def isotope_mass_number(isotope_label: str) -> int:
    """Extract the integer mass from an isotope label.
    
    Supports labels such as C12, H1, O18 and and C12.
    """
    match = re.search(r"\d+", isotope_label)

    if match is None:
        raise ValueError(
            f"Could not extract mass number from {isotope_label!r}."
        )

    return int(match.group())

def build_extra_neutron_lookup(
    isotopes: dict[str, dict[str, dict[str, float]]]  
) -> dict[str, int]:
    """Build a lookup table for extra neutrons per isotope label.]
    
    For each element, the isotope with the lowest mass number is treated as 
    having zero extra neutrons. Other isotopes are assigned extra neutrons 
    relative to that isotope.

    Example:
        C12 -> 0
        C13 -> 1
        O16 -> 0
        O17 -> 1
        O18 -> 2

    Args:
        isotopes: Isotope data dictionary, e.g. `ISOTOPES`.

    Returns:
        Dictionary mapping isotope labels to extra neutron counts.
    
    """
    extra_neutron_lookup: dict[str, int] = {}

    for _, isotope_data in isotopes.items():
        isotope_labels = list(isotope_data.keys())

        mass_numbers = {
            isotope_label: isotope_mass_number(isotope_label)
            for isotope_label in isotope_labels
        }

        reference_mass_number = min(mass_numbers.values())

        for isotope_label, mass_number in mass_numbers.items():
            extra_neutron_lookup[isotope_label] = (
                mass_number - reference_mass_number
            )
    
    return extra_neutron_lookup


# Define a lookup table
EXTRA_NEUTRON_LOOKUP = build_extra_neutron_lookup(ISOTOPES)
