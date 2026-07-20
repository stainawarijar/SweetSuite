import math
import re
from typing import Any

import numpy as np
import pandas as pd

from .resources.constants import ISOTOPES, ELECTRON_MASS, EXTRA_NEUTRON_LOOKUP


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
        monoisotopic_mass (float): Theoretical monoisotopic mass (amu) of the
            neutral analyte, including the mass modifier if specified.
        variable_composition (dict[str, int]): Number of atoms of each element
            whose isotopes can vary (C, H, O, N, S, Na, K, Fe).
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
        charge_carrier: str,
        mass_modifier: str | None = None
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
            mass_modifier: Block name of the mass modifier (e.g. 'water'), or
                None if no modifier is applied.
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
        self.mass_modifier = mass_modifier
        self.monoisotopic_mass = self.get_monoisotopic_mass()
        self.variable_composition = self.get_variable_composition()
        self.reference_df = self.get_reference_df()

    @staticmethod
    def multinomial_prob(
        counts: tuple[int, ...],
        probs: tuple[float, ...]
    ) -> float:
        """Calculate the multinomial probability for a set of isotope counts.

        Computes the multinomial probability for a given set of isotope counts 
        and their natural abundance probabilities. For example, for carbon 
        with counts `(5, 1)`:
            
            probability = 6! / (5! * 1!) * P(C12)^5 * P(C13)^1

        Computation is performed in log-space for numerical stability with 
        large molecules.

        Args:
            counts: Isotope atom counts, summing to the total number of atoms
                for the element.
            probs: Natural abundance probabilities for each isotope, in the 
                same order as `counts`.

        Returns:
            The multinomial probability.
        """
        total = sum(counts)

        # The gamma function generalizes factorials.
        # `math.lgamma(n + 1)` is therefore log(n!).
        log_prob = math.lgamma(total + 1)

        # Subtract the log-factorials of the isotope counts.
        log_prob -= sum(math.lgamma(count + 1) for count in counts)

        # Add the probability terms.
        # Only include counts > 0 to avoid problems such as 0 * log(0).
        for count, prob in zip(counts, probs):
            if count > 0:
                log_prob += count * math.log(prob)
        
        return math.exp(log_prob)

    @staticmethod
    def isotope_count_combis(
        n: int,
        k: int
    ) -> list[tuple[int, ...]]:
        """ Generate all non-negative integer tuples of length `k` 
        that sum to `n`.

        These represent every way to distribute `n` identical atoms of `k` 
        isotopes. For example, `n = 2, k = 3` could represent two oxygen atoms 
        for which there are three stable isotopes (O16, O17, O18), and would 
        produce `(2, 0, 0)`, (1, 1, 0)`, `(0, 0, 2)`, etc.

        Args:
            n: Total number of atoms to distribute.
            k: Number of possible isotopes.
        
        Returns:
            A list of integer tuples of length `k`, each summing to `n`.
        """
        # Base case: only one isotope.
        if k == 1:
            return [(n,)]
        
        # Store all combinations here.
        combinations = []

        # Try every possible count for the first isotope.
        for first_count in range(0, n + 1):
            # Distribute remaining atoms of the remaining isotopes.
            remaining_combis = InputAnalyte.isotope_count_combis(
                n = n - first_count,
                k = k - 1
            )

            # Add `first_count` in front of each remaining combination.
            for remaining_counts in remaining_combis:
                new_combination = (first_count,) + remaining_counts
                combinations.append(new_combination)

        return combinations    

    @staticmethod
    def element_fine_structure(
        element: str,
        atom_count: int,
        min_prob: float = 1e-16
    ):
        """Calculate the isotopic fine structure for a single element.

        Computes all isotope peaks for a given element and atom count by 
        evaluating every combination of isotopes. Peaks with probability at 
        or below `min_prob` are skipped to reduce computation.

        Args:
            element: Name of element, e.g. "carbon".
            atom_count: Number of atoms of this element.
            min_prob: Probability threshold. Peaks with probability at or 
                below this value are excluded.
        
        Returns:
            A list of dictionaries. Each dictionary contains:
                - "mass": exact mass of the peak (Da).
                - "prob": probability of the peak.
                - "isotope_counts": a dictionary of non-zero isotope counts.
        """
        isotope_data = ISOTOPES[element]
        isotope_labels = list(isotope_data.keys())

        isotope_masses = tuple(
            isotope_data[label]["mass"]
            for label in isotope_labels
        )

        isotope_probs = tuple(
            isotope_data[label]["abundance"]
            for label in isotope_labels
        )

        pattern = []

        for counts in InputAnalyte.isotope_count_combis(
            n=atom_count, k=len(isotope_labels)
        ):
            prob = InputAnalyte.multinomial_prob(counts, isotope_probs)

            # Skip masses with very low probabilities, to reduce computation.
            if prob < min_prob:
                continue

            mass = sum(
                count * isotope_mass
                for count, isotope_mass in zip(counts, isotope_masses)
            )

            isotope_counts = {
                isotope_label: count
                for isotope_label, count in zip(isotope_labels, counts)
                if count > 0
            }

            pattern.append({
                "mass": mass,
                "prob": prob,
                "isotope_counts": isotope_counts
            })

        return pattern
    
    @staticmethod
    def convolve_patterns(
        pattern_a: list[dict],
        pattern_b: list[dict],
        min_prob: float = 1e-16
    ) -> list:
        """Convolve two isotope patterns.

        Combines two isotope peak lists by convolving them. Every peak from
        `pattern_a` is paired with every peak from `pattern_b`. Resulting peak
        masses are summed and probabilities are multiplied. Pairs whose combined
        probability falls below `min_prob` are discarded to reduce computation.

        Args:
            pattern_a: List of isotope peaks. Each peak is a dictionary with 
                "mass", "prob" and "isotope_counts".
            pattern_b: List of isotope peaks in the same format as `pattern_a`.
            min_prob: Probability threshold. Combined peaks with probability below
                this value are excluded.
        
        Returns:
            A list of combined isotope peaks in the same format as the inputs.
        """
        combined_pattern = []

        for peak_a in pattern_a:
            for peak_b in pattern_b:
                prob = peak_a["prob"] * peak_b["prob"]

                if prob < min_prob:
                    continue

                isotope_counts = peak_a["isotope_counts"].copy()

                for isotope_label, count in peak_b["isotope_counts"].items():
                    isotope_counts[isotope_label] = (
                        isotope_counts.get(isotope_label, 0) + count
                    )
                
                combined_pattern.append({
                    "mass": peak_a["mass"] + peak_b["mass"],
                    "prob": prob,
                    "isotope_counts": isotope_counts
                })
        
        return combined_pattern

    @staticmethod
    def calculate_fine_structure(
        composition,
        charge: int,
        min_prob: float = 1e-16
    ) -> list[dict]:
        """Calculate the isotopic fine structure for an elemental composition.

        Computes the full isotopic fine structure for a molecule by successively
        convolving the elemental fine-structure patterns for every element in 
        the composition. Corrects for electron mass based on the charge state.
        The resulting peaks are sorted by mass and annotated with relative 
        probabilities.

        Args:
            composition: A dictionary containing the elemental composition.
            charge: Charge state. May be positive or negative.
            min_prob: Probability threshold. Peaks below this value are
                excluded at each convolution step.
        
        Returns:
            A list of fine-structure peaks sorted by mass. Each peak is a
            dictionary with "mass", "prob", "isotope_counts", "relative_prob".
        """
        molecular_pattern = [{
            "mass": 0.0,
            "prob": 1.0,
            "isotope_counts": {}
        }]

        for element, atom_count in composition.items():
            element_pattern = InputAnalyte.element_fine_structure(
                # Remove trailing "s" from element before passing on,
                # for subsetting of `ISOTOPES` dictionary.
                # E.g., "carbons" -> "carbon"
                element=element.removesuffix("s"),
                atom_count=atom_count
            )

            molecular_pattern = InputAnalyte.convolve_patterns(
                pattern_a=molecular_pattern,
                pattern_b=element_pattern,
                min_prob=min_prob
            )

            if len(molecular_pattern) == 0:
                return []
            
        # Correct for electron masses based on charge state.
        mass_correction = int(charge) * ELECTRON_MASS
        for peak in molecular_pattern:
            peak["mass"] -= mass_correction
        
        molecular_pattern = sorted(
            molecular_pattern,
            key=lambda peak: peak["mass"]
        )

        max_prob = max(peak["prob"] for peak in molecular_pattern)

        for peak in molecular_pattern:
            peak["relative_prob"] = peak["prob"] / max_prob
        
        return molecular_pattern
    
    @staticmethod
    def collapse_to_nominal_pattern(
        fine_structure_pattern: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Collapse fine-structure peaks into nominal M, M+1, M+2, ... groups.

        Fine-structure peaks are grouped by their total number of extra neutrons
        compared to the lightest-mass isotopologue. For each group, 
        probabilities are summed and the representative mass is the probability-
        weighted average mass.

        Args:
            fine_structure_pattern: List of fine-structure peaks. Each peak
            should contain "mass", "prob" and "isotope_counts".
        
        Returns:
            A list of nominal isotope peaks by extra neutron count. Each group
            contains: "isotope_group", "extra_neutrons", "prob", "mass", 
            "prob_relative" and "n_fine_structure_peaks".
        """
        grouped_pattern: dict[str, dict[str, Any]] = {}

        for peak in fine_structure_pattern:
            # Determine how many extra neutrons this fine-structure peak has.
            extra_neutrons = 0

            for isotope_label, isotope_count in peak["isotope_counts"].items():
                isotope_extra_neutrons = EXTRA_NEUTRON_LOOKUP[isotope_label]
                extra_neutrons += isotope_count * isotope_extra_neutrons

            if extra_neutrons > 0:
                group_name = f"M+{extra_neutrons}"
            else:
                group_name = "M"
            
            # If this M+n group does not exist yet, create it.
            if group_name not in grouped_pattern:
                grouped_pattern[group_name] = {
                    "isotope_group": group_name,
                    "extra_neutrons": extra_neutrons,
                    "prob": 0.0,
                    "weighted_mass_sum": 0.0,
                    "n_fine_structure_peaks": 0
                }
            
            # Sum probabilities
            grouped_pattern[group_name]["prob"] += peak["prob"]

            # Store sum(mass * probability), so we can calculate the
            # probability-weighted average mass later.
            grouped_pattern[group_name]["weighted_mass_sum"] += (
                peak["mass"] * peak["prob"]
            )

            grouped_pattern[group_name]["n_fine_structure_peaks"] += 1
        
        if len(grouped_pattern) == 0:
            return []
        
        # Convert weighted mass sums into weighted average masses.
        for group in grouped_pattern.values():
            group["mass"] = group["weighted_mass_sum"] / group["prob"]
            del group["weighted_mass_sum"]
        
        # Sort by M, M+1, M+2, ...
        nominal_pattern = sorted(
            grouped_pattern.values(),
            key=lambda group: group["extra_neutrons"]
        )

        # Add probabilities relative to the most probable nominal group.
        max_prob = max(group["prob"] for group in nominal_pattern)

        for group in nominal_pattern:
            group["prob_relative"] = group["prob"] / max_prob

        return nominal_pattern
        
    def get_monoisotopic_mass(self) -> float:
        """Return lightest-isotope mass (amu) of the neutral analyte based on 
        the block composition. In almost all cases this will be the equal
        to the monoisotopic mass, which is the mass of the molecule containing
        the most probable isotopes for each element.
        
        Includes the mass modifier if one is specified.
        """
        # Break analyte name up into parts.
        analyte_parts = re.findall(r"\d+|\D+", self.name)

        # Validate: every block name must be followed by a count.
        if len(analyte_parts) % 2 != 0:
            raise ValueError(
                f"Analyte name '{self.name}' is invalid."
            )

        # Calculate mass using block files.
        mass = 0
        for i, unit in enumerate(analyte_parts):
            if i % 2 == 0:
                block = self.blocks[unit]
                number = int(analyte_parts[i + 1])
                mass += float(block["mass"]) * number

        # Add mass modifier if present.
        if self.mass_modifier is not None:
            mass += float(self.blocks[self.mass_modifier]["mass"])

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

        # Add mass modifier composition if present.
        if self.mass_modifier is not None:
            block = self.blocks[self.mass_modifier]
            for element in composition.keys():
                try:
                    composition[element] += int(block[element])
                except KeyError:
                    continue

        return composition

    def select_isotopologues(
        self,
        merged_mass_probs: list[tuple[float, float]]
    ) -> list[tuple[float, float, int]]:
        """Select most probable isotopologues until a cumulative threshold 
            is met.

        Args:
            merged_mass_probs: List of (mass, probability) tuples, 
                sorted from low to high mass.

        Returns:
            A reduced list of isotopologues as (mass, probability, index) 
            tuples, sorted by increasing mass. The index represents the 
            isotopologue number (0 being lowest-mass, 1 meaning one extra 
            neutron, etc.). Note that the lowest-mass is not necessarily
            the monoisotopic one, as this depends on its theoretical 
            relative abundance which may be very low for large analytes.
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

    def compute_distribution(
        self,
        base_mass: float,
        charge: int,
        composition: dict[str, int]
    ) -> list[tuple[float, float]]:
        """Compute the isotopic distribution for a given monoisotopic mass
        and elemental composition using sequential convolution.
        """
        fine_pattern = InputAnalyte.calculate_fine_structure(
            composition, charge
        )
        nominal_pattern = InputAnalyte.collapse_to_nominal_pattern(fine_pattern)

        # TODO From nominal pattern, convert (mass, prob) combinations to 
        # (mass_diff, prob) combinations where mass_diff is with respect to
        # lightest mass calculated based on composition. Then apply these 
        # (mass_dif, prob) combinations to `base_mass` which is based on the
        # block files.
        # NOTE: base_mass is not necessarily the same as calculated lightest
        # mass!

        return 

    def get_reference_df(self) -> pd.DataFrame:
        """Create a reference DataFrame for the analyte.

        Per charge state, the following properties are added for the
        most abundant isotopologues:
        - `peak`: formatted as *AnalyteName_ChargeState_IsotopologueNumber*.
        - `charge_carrier`: the name of the charge carrier block used.
        - `mass_modifier`: the name of the mass modifier block used, or 'None'.
        - `mz`: m/z value of the isotopologue ion.
        - `relative_area`: theoretical relative abundance of the isotopologue,
            as a fraction.
        - `mz_window`: integration window (Th) to be used around the exact m/z
            value of the isotopologue.
        - `time`: retention time of the corresponding cluster for which a
            sum spectrum will be created (LC-MS data), or `np.nan` (MS-only data).
        - `time_window`: retention time window for the sum spectrum
            (LC-MS data), or `np.nan` (MS-only data).
        - `calibrant`: whether the isotopologue should be used as a calibrant.
            If an analyte was specified as a calibrant in the provided analyte 
            list, the isotopologue with the highest relative abundance will be 
            used as a calibrant in all charge states.

        Returns:
            A DataFrame with the following columns:
            `peak`, `charge_carrier`, `mass_modifier`, `mz`, `relative_area`,
            `mz_window`, `time`, `time_window`, `calibrant`.
        """
        # Initiate empty DataFrame.
        reference = pd.DataFrame()

        # Determine charge unit and monoisotopic mass of the charge carrier.
        charge_unit = int(self.blocks[self.charge_carrier]["charge"])
        carrier_mono_mass = float(self.blocks[self.charge_carrier]["mass"])

        # Elemental composition of one charge carrier unit.
        carrier_composition = {
            el: int(self.blocks[self.charge_carrier].get(el, 0))
            for el in self.variable_composition
        }

        # Determine mode: MS-only or LC-MS data.
        ms_only = (self.time is None or self.time_window is None)

        # Set time values based on mode.
        time_val = np.nan if ms_only else self.time
        time_window_val = np.nan if ms_only else self.time_window

        # Mass modifier label for the output column.
        mass_modifier_label = (
            self.mass_modifier if self.mass_modifier is not None else "None"
        )

        # Loop over charge states (in steps of charge unit).
        for charge in range(self.charge_min, self.charge_max + 1, charge_unit):
            n_carriers = charge // charge_unit

            # Full ion monoisotopic mass and elemental composition.
            ion_mono_mass = self.monoisotopic_mass + n_carriers * carrier_mono_mass
            ion_composition = {
                el: self.variable_composition[el] + n_carriers * carrier_composition[el]
                for el in self.variable_composition
            }

            # TODO: Correct isotope calculation here.
            # 1. Compute nominal pattern
            distribution = self.compute_distribution(
                base_mass=ion_mono_mass, 
                charge=int(charge),
                composition=ion_composition
            )

            # Compute full ion isotopologue distribution and select peaks.
            per_charge_isotopologues = self.select_isotopologues(
                distribution
                # self.compute_distribution(ion_mono_mass, ion_composition)
            )

            # Determine index of most abundant isotopologue for calibrant flag.
            if self.calibrant:
                max_area_idx = max(
                    range(len(per_charge_isotopologues)),
                    key=lambda i: per_charge_isotopologues[i][1],
                )

            # Loop over isotopologues.
            for idx, iso in enumerate(per_charge_isotopologues):
                # iso[0] is the full ion mass; divide by charge for m/z.
                mz = iso[0] / charge
                mz_window = (
                    self.mz_window_coeffs[0] * mz**2
                    + self.mz_window_coeffs[1] * mz
                    + self.mz_window_coeffs[2]
                )
                # Create small DataFrame for this isotopologue.
                df = pd.DataFrame([{
                    "peak": f"{self.name}_{charge}_{iso[2]}",
                    "charge_carrier": self.charge_carrier,
                    "mass_modifier": mass_modifier_label,
                    "mz": mz,
                    "relative_area": iso[1],
                    "mz_window": mz_window,
                    "time": time_val,
                    "time_window": time_window_val,
                    "calibrant": self.calibrant and idx == max_area_idx,
                }])

                # Add to larger `reference` DataFrame.
                if not reference.empty:
                    reference = pd.concat(
                        [reference, df], ignore_index=True
                    )
                else:
                    # Needed for first step in loop, because we start
                    # with an empty dataframe.
                    reference = df

        return reference

