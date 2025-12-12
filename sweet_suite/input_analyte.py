import itertools
import math
import re

import numpy as np
import pandas as pd

from .resources.constants import ISOTOPES


class InputAnalyte:
    """Represents an analyte and computes its theoretical isotopic properties.

    An `InputAnalyte` stores all relevant information about a molecule
    (e.g. name, charge state range, retention time, calibration flag) and
    computes theoretical isotopologue distributions based on elemental
    composition. It provides methods to calculate the monoisotopic mass,
    determine isotopic variation, generate isotopologues, and build a
    reference DataFrame for downstream analysis.

    Attributes:
        name (str): Name of the analyte (must correspond to block definitions).
        charge_min (int): Minimum charge state to consider.
        charge_max (int): Maximum charge state to consider.
        mz_window_coeffs (tuple[float, float, float]): Coefficients (a, b, c) 
            describing the peak integration window (Th) as a quadratic 
            function of m/z: window = a*(m/z)^2 + b*(m/z) + c. 
            The integration window can be constant setting a = b = 0.
        time (float | None): Retention time of the analyte (for LC-MS data).
        time_window (float | None): Retention time window around `time`
            (for LC-MS data).
        calibrant (bool): Whether this analyte should be used as a calibrant.
        min_isotopic_fraction (float): Minimum cumulative isotopic fraction
            required when selecting isotopologues.
        charge_carrier (str): Name of the block representing the charge carrier
            (e.g. 'proton').
        monoisotopic_mass (float): Theoretical monoisotopic mass (amu).
        variable_composition (dict[str, int]): Number of atoms of each element
            whose isotopes can vary (carbons, hydrogens, nitrogens, oxygens, 
            sulfurs).
        isotopologues (list[tuple[float, float, int]]): Selected isotopologues,
            each as a tuple of (mass, probability, index).
        reference_df (pd.DataFrame): Reference DataFrame with expected peaks,
            m/z values, abundances, retention times, and calibration flags.
    """

    def __init__(
        self,
        blocks: dict[dict],
        name: str,
        charge_min: int,
        charge_max: int,
        mz_window_coeffs: float,
        time: float | None,
        time_window: float | None,
        calibrant: bool,
        min_isotopic_fraction: float,
        charge_carrier: str
    ):
        """Initialize an analyte and compute its isotopic properties.

        Args:
            blocks: A dictionary with mass, charge and variable elements for 
                all block files.
            name: Name of the analyte, which must match entries in the block 
                definitions.
            charge_min: Minimum charge state to include.
            charge_max: Maximum charge state to include.
            mz_window_coeffs (tuple[float, float, float]): Coefficients 
            (a, b, c) describing the peak integration window (Th) as a quadratic 
            function of m/z: window = a*(m/z)^2 + b*(m/z) + c. The integration 
            window can be constant setting a = b = 0.
            time: Retention time (LC-MS data), or None for non-LC data.
            time_window: Retention time window around `time`, or None for 
                non-LC data.
            calibrant: Whether this analyte is designated as a calibrant.
            min_isotopic_fraction: Minimum cumulative isotopic fraction used 
                when selecting isotopologues.
            charge_carrier: Block name of the charge carrier, e.g. 'proton'.
        """
        self.blocks = blocks
        self.name = name
        self.charge_min = charge_min
        self.charge_max = charge_max
        self.mz_window_coeffs = mz_window_coeffs
        self.time = time
        self.time_window = time_window
        self.calibrant = calibrant
        self.min_isotopic_fraction = min_isotopic_fraction
        self.charge_carrier = charge_carrier
        self.monoisotopic_mass = self.get_monoisotopic_mass()
        self.variable_composition = self.get_variable_composition()
        self.isotopologues = self.get_isotopologues()
        self.reference_df = self.get_reference_df()

    @staticmethod
    def get_heavy_isotope_distributions(
        element: str,
        number: int
    ) -> dict[str, list[tuple[float, float]]]:
        """Calculate the distribution of heavy isotope incorporation for a 
        given element.

        For a selected element and a number of atoms, this function computes 
        the probability that 0, 1, ..., n heavy isotopes are present among the 
        given atoms. The calculation uses a binomial distribution, based on the 
        natural abundance of the heavier stable isotopes of the element. 
        Probabilities below 0.1% are considered negligible and are omitted.

        Args:
            element: Element for which to calculate isotope distributions.
                Must be one of: 'carbon', 'hydrogen', 'oxygen', 'nitrogen',
                'sulfur', 'potassium', 'iron', 'chlorine'. Sodium and fluorine
                are also allowed but will have no effect, as they have only 
                one naturally occuring isotope.
            number: Number of atoms of the given element whose isotopes can 
                naturally vary.

        Returns:
            A dictionary mapping each heavy isotope of the element (as a string 
            identifier, e.g. 'C13') to a list of tuples of the form 
            `(mass_diff, prob)`, where `mass_diff` is the mass difference 
            relative to the monoisotopic mass based on the number `n` of 
            incorporated heavy isotopes, and `prob` is the probability of having 
            exactly `n` heavy isotopes among the total number of atoms.
        """
        # Initiate empty dictionary to store distributions.
        isotope_distributions = {}

        # Determine mass of lightest isotope.
        lightest_isotope = next(iter(ISOTOPES[element]))
        lightest_isotope_mass = ISOTOPES[element][lightest_isotope]["mass"]

        # Loop over the stable isotopes.
        for idx, isotope in enumerate(ISOTOPES[element]):
            if idx == 0:  # Skip the lightest isotope.
                continue

            # Extract mass and abundance of isotope.
            mass = ISOTOPES[element][isotope]["mass"]
            abundance = ISOTOPES[element][isotope]["abundance"]

            # Initiate values before loop starts.
            n = 0  # Number of heavy isotopes incorporated among all atoms.
            probs = []
            last_prob = 0

            # Loop over possible numbers of heavy isotopes.
            while n <= number:
                # Calculate binomial coefficient and probability.
                abundance = ISOTOPES[element][isotope]["abundance"]
                coeff = math.comb(number, n)
                prob = coeff * abundance ** n * (1 - abundance) ** (number - n)

                # Append tuple (mass_diff, prob) to probs.
                mass_diff = (mass - lightest_isotope_mass) * n
                probs.append((mass_diff, prob))

                # Check if probability is below 0.1% and still decreasing.
                if prob <= 0.001 and prob < last_prob:
                    break
                else:
                    n += 1

                # Update last_prob to last calculated probability.
                last_prob = prob

            # Add probability list to dictionary.
            isotope_distributions[isotope] = probs

        return isotope_distributions

    @staticmethod
    def merge_isotopic_masses(
        mass_probs: list[tuple[float, float]],
        epsilon: float = 0.5  # Set constant for now.
    ) -> list[tuple[float, float]]:
        """Merge probabilities for isotopic masses within the instrument's 
        resolution using NumPy for vectorized operations.

        Each group of (mass, probability) tuples with indistinguishable masses
        is collapsed into a single weighted-average mass with a total combined
        probability.

        Args:
            mass_probs: List of (mass, probability) tuples.
            epsilon: Tuples whose masses fall within this tolerance are pooled 
                and merged.

        Returns:
            A list of merged (mass, probability) tuples, ordered from low to 
                high mass.
        """
        # Sort by mass using NumPy (vectorized sort)
        sorted_mass_probs = sorted(mass_probs, key=lambda x: x[0])
        masses = np.array([m for m, _ in sorted_mass_probs])
        probs = np.array([p for _, p in sorted_mass_probs])

        # Find where mass differences exceed epsilon (group boundaries).
        diff = np.diff(masses)
        group_boundaries = np.where(diff >= epsilon)[0] + 1
        group_starts = np.concatenate([[0], group_boundaries, [len(masses)]])

        # Vectorized merging for each group.
        merged = []
        for i in range(len(group_starts) - 1):
            start = group_starts[i]
            end = group_starts[i + 1]
            group_masses = masses[start:end]
            group_probs = probs[start:end]
            
            # Vectorized weighted average and sum.
            total_prob = np.sum(group_probs)
            avg_mass = np.sum(group_masses * group_probs) / total_prob
            merged.append((avg_mass, total_prob))

        return merged

    def get_monoisotopic_mass(self) -> float:
        """Return monoisotopic mass (amu) based on block composition."""
        # Break analyte name up into parts.
        analyte_parts = re.findall(r"\d+|\D+", self.name)

        # Calculate mass using block files.
        mass = 0
        for i, unit in enumerate(analyte_parts):
            if i % 2 == 0:
                block = self.blocks[unit]
                number = int(analyte_parts[i + 1])
                mass += float(block["mass"]) * number

        return mass

    def get_variable_composition(self) -> dict[str, int]:
        """Determine number of atoms whose isotopes can vary for the following
        elements: C, H, O, N, S, Na, K, Fe.

        For natural analytes, this should simply be the elemental composition
        of the molecule. When an analyte is labeled using heavy isotopes,
        those fixed heavy isotopes should be subtracted.

        The numbers are read from the '.block' files. If an element is not
        specified in the block file, it is equivalent to setting it to 0.

        Returns:
            A dictionary containing the number of C, H, O, N, S, Na, K and Fe
            whose isotopes can vary. Returns `None` when there are missing
            block files.
        """
        # Break analyte name up into parts.
        analyte_parts = re.findall(r"\d+|\D+", self.name)

        # Determine composition based on block files.
        composition = {
            "carbons": 0,
            "hydrogens": 0,
            "nitrogens": 0,
            "oxygens": 0,
            "sulfurs": 0,
            "sodiums": 0,
            "potassiums": 0,
            "irons": 0
        }
        
        for i, unit in enumerate(analyte_parts):
            if i % 2 == 0:
                block = self.blocks[unit]
                number = int(analyte_parts[i + 1])
                for element in composition.keys():
                    try:
                        composition[element] += int(block[element]) * number
                    except KeyError:
                        # Element is not specified in block file, assume 0.
                        continue

        return composition

    def select_isotopologues(
        self,
        merged_mass_probs: list[tuple[float, float]]
    ) -> list[tuple[float, float, int]]:
        """Select most probable isotopologues until a cumulative threshold 
            is met.

        This function is called from `get_isotopologues`.

        Args:
            merged_mass_probs: List of (mass, probability) tuples, 
                sorted from low to high mass.

        Returns:
            A reduced list of isotopologues as (mass, probability, index) 
            tuples, sorted by increasing mass. The index represents the 
            isotopologue number (0 being monoisotopic, 1 meaning one extra 
            neutron, etc.).
        """
        # Create list with tuples (mass, prob, idx).
        masses_probs_idxs = []
        for idx, (mass, prob) in enumerate(merged_mass_probs):
            masses_probs_idxs.append((mass, prob, idx))

        # Sort by decreasing probability.
        masses_probs_idxs.sort(key=lambda x: x[1], reverse=True)

        # Keep isotopes until cumulative probability exceeds minimum
        # isotopic fraction to be integrated.
        selected = []
        contribution = 0
        for mass, prob, idx in masses_probs_idxs:
            contribution += prob
            selected.append((mass, prob, idx))
            if contribution > self.min_isotopic_fraction:
                break

        # Return final selection sorted by mass.
        return sorted(selected, key=lambda x: x[0])

    def get_isotopologues(self) -> list[tuple[float, float, int]]:
        """Generate isotopologue distribution of the neutral molecule.

        Starting from the molecule's variable composition, this method combines
        the per-element heavy isotope options to estimate which molecular
        variants (isotopologues) can occur and how likely they are. Results
        with nearly the same mass are grouped to reflect instrument resolution,
        and only the most probable isotopologues are returned.

        Returns:
            A list of (mass, probability, index) tuples for the selected
            isotopologues, sorted by increasing mass.
        """
        # Initiate empty dictionary.
        # `all_distributions` will contain for each heavy isotope a list
        # of 2-tuples, each tuple having the form (mass_diff, prob).
        all_distributions = {}

        # Loop over elements in composition and extend dictionary.
        for element in self.variable_composition:
            distributions = self.get_heavy_isotope_distributions(
                element=element[:-1],  # Removes 's' from end of string.
                number=self.variable_composition[element],
            )
            all_distributions.update(distributions)

        # Determine for each possible combination of heavy isotopes the
        # total mass of the molecule, and the corresponding probability.
        combis = np.array(list(
            itertools.product(*all_distributions.values())
        ))
        masses = self.monoisotopic_mass + np.sum(combis[:, :, 0], axis=1)
        probs = np.prod(combis[:, :, 1], axis=1)
        mass_probs = list(zip(masses, probs))

        # Merge isotopic masses that are closer together than the
        # instrument's resolution (specified by epsilon, default 0.5).
        merged_mass_probs = self.merge_isotopic_masses(mass_probs)

        # Select most probable isotopologues until cumulative probability
        # exceeds `min_isotopic_fraction`. Results in a list with tuples
        # of the form (mass, probability, isotopologue number).
        isotopologues = self.select_isotopologues(merged_mass_probs)

        return isotopologues

    def get_reference_df(self) -> pd.DataFrame:
        """Create a reference DataFrame for the analyte.

        Per charge state, the following properties are added for the
        most abundant isotopologues:
        - `peak`: formatted as *AnalyteName_ChargeState_IsotopologueNumber*.
        - `charge_carrier`: the name of the charge carrier block used.
        - `mz`: m/z value of the isotopologue ion.
        - `relative_area`: theoretical relative abundance of the isotopologue,
            as a fraction.
        - `mz_window`: integration window (Th) to be used around the exact m/z
            value of the isotopologue.
        - `time`: retention time of the corresponding cluster for which a
            sum spectrum will be created. Applicable only to LC-MS data; set to
            `None` otherwise.
        - `time_window`: retention time window for the sum spectrum.
            Applicable only to LC-MS data; set to `None` otherwise.
        - `calibrant`: whether the isotopologue should be used as a calibrant.
            If an analyte was specified as a calibrant in the provided analyte 
            list, the isotopologue with the highest relative abundance will be 
            used as a calibrant in all charge states.

        Returns:
            A DataFrame with the following columns:
            `peak`, `charge_carrier`, `mz`, `relative_area`, `mz_window`,
            `time` (for LC data), `time_window` (for LC data), `calibrant`.

            Note: For non-LC data (when `time` or `time_window` is `None`),
            the current implementation returns an empty DataFrame until
            non-LC handling is implemented.
        """
        # Initiate empty DataFrame
        reference = pd.DataFrame()

        # Determine the mass and charge number of the charge carrier.
        charge_carrier_mass = self.blocks[self.charge_carrier]["mass"]
        charge_unit = int(self.blocks[self.charge_carrier]["charge"])

        # Determine index of isotopologue with highest relative area,
        # if the analyte is marked as a calibrant.
        if self.calibrant:
            max_area_idx = max(
                range(len(self.isotopologues)),
                key=lambda i: self.isotopologues[i][1],
            )

        # Determine if data contains retention times or not.
        is_lc_data = (self.time is not None and self.time_window is not None)

        # Loop over charge states and isotopologues and build
        # a DataFrame. Structure will depend on type of data
        # (LC-MS or MALDI).
        if is_lc_data:
            # Loop over charge states (in steps of charge unit).
            for charge in range(self.charge_min, self.charge_max + 1, charge_unit):
                # Loop over isotopologues.
                for idx, iso in enumerate(self.isotopologues):
                    # Calculate m/z and m/z integration window.
                    mz = (
                        (iso[0] + (charge / charge_unit) * charge_carrier_mass) 
                        / charge
                    )
                    mz_window = (
                        self.mz_window_coeffs[0] * mz**2
                        + self.mz_window_coeffs[1] * mz
                        + self.mz_window_coeffs[2]
                    )
                    # Create small DataFrame for this isotopologue
                    df = pd.DataFrame([{
                        "peak": f"{self.name}_{charge}_{iso[2]}",
                        "charge_carrier": self.charge_carrier,
                        "mz": mz,
                        "relative_area": iso[1],
                        "mz_window": mz_window,
                        "time": self.time,
                        "time_window": self.time_window,
                        "calibrant": self.calibrant and idx == max_area_idx,
                    }])

                    # Add to larger `reference` DataFrame.
                    if not reference.empty:
                        reference = pd.concat(
                            [reference, df], ignore_index = True
                        )
                    else:
                        # Needed for first step in loop, because we start
                        # with an empty dataframe.
                        reference = df
        else:
            # NOTE: Write code for non-LC data (e.g., MALDI).
            pass

        return reference

