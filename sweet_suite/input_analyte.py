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
        blocks: dict[str, dict[str, float | int]],
        name: str,
        charge_min: int,
        charge_max: int,
        mz_window_coeffs: tuple[float, float, float],
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
                (a, b, c) describing the peak integration window (Th) as a 
                quadratic function of m/z: window = a*(m/z)^2 + b*(m/z) + c. 
                The integration window can be constant setting a = b = 0.
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
        min_prob: float = 1e-12
    ) -> list[dict[str, Any]]:
        """Calculate the isotopic fine structure for one element.

        All possible distributions of `atom_count` atoms over the available 
        isotopes are generated. The exact mass and multinomial probability are 
        calculated for each isotope-count combination. Combinations below 
        `min_prob` are discarded.

        Args:
            element: Element name corresponding to a key in `ISOTOPES`, such as
                `"carbon"` or `"sulfur"`.
            atom_count: Number of atoms of the element.
            min_prob: Minimum probability required to retain an isotope-count
                combination.

        Returns:
            Fine-structure peaks. Each dictionary contains `mass`, `prob`, and
            `isotope_counts`.
        
        Raises:
            KeyError: If `element` is not present in `ISOTOPES`.
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
        pattern_a: list[dict[str, Any]],
        pattern_b: list[dict[str, Any]],
        min_prob: float = 1e-12
    ) -> list[dict[str, Any]]:
        """Convolve two isotopic fine-structure patterns.

        Every peak in `pattern_a` is combined with every peak in `pattern_b`.
        Masses are added, probabilities are multiplied, and isotope counts are
        merged. Combined peaks below `min_prob` are discarded.

        Args:
            pattern_a: First fine-structure pattern.
            pattern_b: Second fine-structure pattern.
            min_prob: Minimum combined probability required to retain a peak.

        Returns:
            Convolved fine-structure pattern containing `mass`, `prob`, and
            `isotope_counts` for each retained peak.
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
        composition: dict[str, int],
        charge: int,
        min_prob: float = 1e-12
    ) -> list[dict]:
        """Calculate the isotopic fine structure for an ion composition.

        Element-specific isotope patterns are generated and successively 
        convolved. Low-probability configurations are discarded both while 
        generating elemental patterns and after each convolution. The ion mass 
        is corrected for the signed charge state by subtracting the 
        corresponding electron mass.

        An empty list is returned if all configurations are removed by
        probability filtering.

        Args:
            composition: Numbers of atoms whose isotopes are allowed to vary.
            charge: Signed charge state of the ion.
            min_prob: Minimum probability required to retain a fine-structure 
                peak.

        Returns:
            Fine-structure peaks sorted by increasing mass. Each dictionary 
            contains `mass`, `prob`, `isotope_counts`, and `relative_prob`. 
            The relative probability is normalized to the most probable retained 
            fine-structure peak.
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
                atom_count=atom_count,
                min_prob=min_prob
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
            Nominal isotope groups sorted by increasing number of extra
            neutrons. Each dictionary contains `isotope_group`, 
            `extra_neutrons`, `prob`, `mass`, `prob_relative`, and 
            `n_fine_structure_peaks`. The mass is the probability-weighted 
            average mass of the fine-structure peaks in the group.
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
    
    @staticmethod
    def calculate_lightest_mass(
        composition: dict[str, int],
        charge: int
    ) -> float:
        """Calculate the mass of the all-lightest-isotope ion composition.

        For each variable element, the mass of its lightest isotope is 
        multiplied by its atom count. The electron-mass correction corresponding 
        to the signed charge state is then applied.

        This function calculates only the mass represented by `composition`.
        Fixed atoms, including fixed stable-isotope labels, must be accounted
        for separately in the externally supplied `base_mass` (based on masses
        specified in block files).

        Args:
            composition: Numbers of atoms whose isotopes are allowed to vary.
                Element names are plural, such as `"carbons"` or `"oxygens"`.
            charge: Signed charge state of the ion. Positive charge removes
                electron mass, whereas negative charge adds electron mass.
        
        Returns:
            Exact mass of the all-lightest-isotope ion composition in Da.
        """
        mass = 0.0

        for element, atom_count in composition.items():
            element_name = element.removesuffix("s")
            isotope_data = ISOTOPES[element_name]

            lightest_isotope_mass = min(
                isotope["mass"]
                for isotope in isotope_data.values()
            )

            mass += atom_count * lightest_isotope_mass
        
        # Same electron-mass correction used for fine-structure peaks.
        mass -= charge * ELECTRON_MASS

        return mass

    def get_monoisotopic_mass(self) -> float:
        """Calculate the analyte base mass from its block definitions.

        The base mass is obtained by summing the mass of each named block and 
        the optional mass modifier. Block masses are expected to represent the 
        lightest isotope composition of all variable atoms while already 
        including any fixed stable-isotope labels.

        Returns:
            Neutral analyte base mass in daltons.
        
        Raises:
            ValueError: If the analyte name does not consist of alternating 
                block names and integer counts.
            KeyError: If an analyte block or mass-modifier block is not defined.
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
            whose isotopes can vary.

        Raises:
            KeyError: If a block referenced by the analyte name or mass modifier
                is not defined.
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
        distribution: list[tuple[float, float, int]]
    ) -> list[tuple[float, float, int]]:
        """Select isotopologues up to a cumulative probability threshold.

        Nominal isotope groups are first ordered by decreasing probability.
        Groups are selected until their cumulative probability reaches or 
        exceeds `self.min_isotopic_fraction`. The selected groups are then 
        returned in increasing mass order.

        Args:
            distribution: Nominal isotope distribution represented as tuples of
                ion mass, probability and number of extra neutrons.

        Returns:
            Selected isotope groups as tuples of ion mass, probability, and 
            number of extra neutrons, sorted by increasing mass. The extra-
            neutron value identifies the nominal isotope group: 0 is M, 1 is
            M+1, 2 is M+2, and so on.
        """
        isotopologues_by_probability = sorted(
            distribution,
            key=lambda isotope: isotope[1],
            reverse=True
        )

        selected = []
        cumulative_probability = 0.0

        for mass, probability, extra_neutrons in isotopologues_by_probability:
            selected.append((mass, probability, extra_neutrons))
            cumulative_probability += probability

            if cumulative_probability >= self.min_isotopic_fraction:
                break
        
        return sorted(selected, key=lambda isotope: isotope[0])

    def compute_distribution(
        self,
        base_mass: float,
        charge: int,
        composition: dict[str, int]
    ) -> list[tuple[float, float, int]]:
        """Compute the nominal isotopic distribution for an ion.

        The isotopic fine structure is calculated from the variable elemental
        composition and collapsed into nominal M, M+1, M+2, ... groups. The
        resulting isotope-dependent mass differences are added to `base_mass`.

        Args:
            base_mass: Mass of the ion containing the lightest isotope of every
                variable atom. Fixed stable-isotope labels are already included
                in this mass.
            charge: Signed charge state of the ion.
            composition: Numbers of atoms whose isotopes are allowed to vary.
        
        Returns:
            A list of tuples containing the ion mass, probability, and number of
            extra neutrons for each retained nominal isotope group. The list is
            sorted by increasing mass.
        
        Raises:
            ValueError: If no isotopic peaks remain after probability filtering.
        """
        fine_pattern = InputAnalyte.calculate_fine_structure(
            composition=composition, 
            charge=charge
        )
        nominal_pattern = InputAnalyte.collapse_to_nominal_pattern(
            fine_structure_pattern=fine_pattern
        )

        # Overly restrictive threshold can make `calculate_fine_structure()`
        # return an empty list, which would lead to IndexError below.
        # Check against this explicitly.
        if not nominal_pattern:
            raise ValueError(
                "The isotopic pattern is empty. "
                "The 'min_prob' threshold may be too high."
            )

        # Calculate the mass represented by zero additional neutrons directly.
        # This mass may not occur in `nominal_pattern` if its probability was
        # below the filtering threshold.
        mass_lightest = InputAnalyte.calculate_lightest_mass(
            composition=composition,
            charge=charge
        )

        distribution = [
            (
                base_mass + peak["mass"] - mass_lightest,
                peak["prob"],
                peak["extra_neutrons"]
            )
            for peak in nominal_pattern
        ]

        # NOTE: `base_mass` is NOT necessarily the same as `mass_lightest`!
        # (E.g., in case of a stable-isotope labeled analyte).

        return distribution

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
        # NOTE: Requires `charge_min <= charge_max` for positive charge
        # and `charge_min >= charge_max` for negative charge.
        for charge in range(
            self.charge_min,
            self.charge_max + charge_unit,
            charge_unit
        ):
            n_carriers = charge // charge_unit

            # Full ion monoisotopic mass and elemental composition.
            ion_mono_mass = self.monoisotopic_mass + n_carriers * carrier_mono_mass
            ion_composition = {
                el: self.variable_composition[el] + n_carriers * carrier_composition[el]
                for el in self.variable_composition
            }

            # Calculate nominal mass-probability distribution.
            distribution = self.compute_distribution(
                base_mass=ion_mono_mass, 
                charge=int(charge),
                composition=ion_composition
            )

            # Select most probable isotopic peaks that together summing to at 
            # least `self.min_isotopic_fraction`.
            per_charge_isotopologues = self.select_isotopologues(distribution)

            # Determine index of most abundant isotopologue for calibrant flag.
            if self.calibrant:
                max_area_idx = max(
                    range(len(per_charge_isotopologues)),
                    key=lambda i: per_charge_isotopologues[i][1],
                )

            # Loop over isotopologues.
            for idx, isotope in enumerate(per_charge_isotopologues):
                ion_mass, probability, extra_neutrons = isotope
                
                # In negative mode, m/z is still reported as a positive number
                # by convention. Hence we use absolute charge here.
                mz = ion_mass / abs(charge) 

                mz_window = (
                    self.mz_window_coeffs[0] * mz**2
                    + self.mz_window_coeffs[1] * mz
                    + self.mz_window_coeffs[2]
                )

                # Create small DataFrame for this isotopologue.
                df = pd.DataFrame([{
                    "peak": f"{self.name}_{charge}_{extra_neutrons}",
                    "charge_carrier": self.charge_carrier,
                    "mass_modifier": mass_modifier_label,
                    "mz": mz,
                    "relative_area": probability,
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
