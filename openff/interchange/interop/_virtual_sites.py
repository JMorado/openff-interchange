"""
Common helpers for exporting virtual sites.
"""
from collections import defaultdict
from collections.abc import Iterable

import numpy
from openff.units import Quantity, unit

from openff.interchange import Interchange
from openff.interchange.exceptions import (
    MissingPositionsError,
    MissingVirtualSitesError,
    VirtualSiteTypeNotImplementedError,
)
from openff.interchange.models import VirtualSiteKey


def _virtual_site_parent_molecule_mapping(
    interchange: Interchange,
) -> dict[VirtualSiteKey, int]:
    mapping: dict[VirtualSiteKey, int] = dict()

    if "VirtualSites" not in interchange.collections:
        return mapping

    for virtual_site_key in interchange["VirtualSites"].key_map:
        assert isinstance(virtual_site_key, VirtualSiteKey)
        parent_atom_index = virtual_site_key.orientation_atom_indices[0]
        parent_atom = interchange.topology.atom(parent_atom_index)
        parent_molecule = parent_atom.molecule
        mapping[virtual_site_key] = interchange.topology.molecule_index(parent_molecule)

    return mapping


def get_positions_with_virtual_sites(
    interchange: Interchange,
    use_zeros: bool = False,
) -> Quantity:
    """Return the positions of all particles (atoms and virtual sites)."""
    if interchange.positions is None:
        raise MissingPositionsError(
            f"Positions are required, found {interchange.positions=}.",
        )

    if "VirtualSites" not in interchange.collections:
        raise MissingVirtualSitesError()

    if len(interchange["VirtualSites"].key_map) == 0:
        raise MissingVirtualSitesError()

    molecule_virtual_site_map = defaultdict(list)

    virtual_site_molecule_map = _virtual_site_parent_molecule_mapping(interchange)

    for virtual_site, molecule_index in virtual_site_molecule_map.items():
        molecule_virtual_site_map[molecule_index].append(virtual_site)

    particle_positions = Quantity(
        numpy.empty(shape=(0, 3)),
        unit.nanometer,
    )

    for molecule in interchange.topology.molecules:
        molecule_index = interchange.topology.molecule_index(molecule)

        atom_indices = [
            interchange.topology.atom_index(atom) for atom in molecule.atoms
        ]
        this_molecule_atom_positions = interchange.positions[atom_indices, :]

        n_virtual_sites_in_this_molecule: int = len(
            molecule_virtual_site_map[molecule_index],
        )

        if use_zeros:
            this_molecule_virtual_site_positions = Quantity(
                numpy.zeros((n_virtual_sites_in_this_molecule, 3)),
                unit.nanometer,
            )

        else:
            this_molecule_virtual_site_positions = Quantity(
                numpy.asarray(
                    [
                        _get_virtual_site_positions(
                            virtual_site_key,
                            interchange,
                        ).m_as(unit.nanometer)
                        for virtual_site_key in molecule_virtual_site_map[
                            molecule_index
                        ]
                    ],
                ),
                unit.nanometer,
            )

        particle_positions = numpy.concatenate(
            [
                particle_positions,
                this_molecule_atom_positions,
                this_molecule_virtual_site_positions,
            ],
        )

    return particle_positions


def _get_virtual_site_positions(
    virtual_site_key: VirtualSiteKey,
    interchange: Interchange,
) -> Quantity:
    # TODO: Move this behavior elsewhere, possibly to a non-GROMACS location
    if virtual_site_key.type == "BondCharge":
        return _get_bond_charge_virtual_site_positions(virtual_site_key, interchange)
    elif virtual_site_key.type == "DivalentLonePair":
        return _get_divalent_lone_pair_virtual_site_positions(
            virtual_site_key,
            interchange,
        )
    elif virtual_site_key.type == "TrivalentLonePair":
        return _get_trivalent_lone_pair_virtual_site_positions(
            virtual_site_key,
            interchange,
        )
    else:
        raise VirtualSiteTypeNotImplementedError(
            f"Virtual site type {virtual_site_key.type} not implemented.",
        )


def _get_bond_charge_virtual_site_positions(
    virtual_site_key,
    interchange,
) -> Quantity:
    potential_key = interchange["VirtualSites"].key_map[virtual_site_key]
    potential = interchange["VirtualSites"].potentials[potential_key]
    distance = potential.parameters["distance"]

    # r1 and r2 are positions of atom1 and atom2 in the convention of
    # these diagrams:
    # https://docs.openforcefield.org/projects/toolkit/en/stable/users/virtualsites.html#applying-virtual-site-parameters
    r1 = interchange.positions[virtual_site_key.orientation_atom_indices[0]]
    r2 = interchange.positions[virtual_site_key.orientation_atom_indices[1]]

    separation = _get_separation_by_atom_indices(
        interchange,
        atom_indices=tuple(
            (
                virtual_site_key.orientation_atom_indices[0],
                virtual_site_key.orientation_atom_indices[1],
            ),
        ),
    )

    # The virtual site is placed at a distance opposite the r1 -> r2 vector
    return r1 - (r2 - r1) * distance / separation


def _get_monovalent_lone_pair_virtual_site_positions(
    virtual_site_key,
    interchange,
) -> Quantity:
    # r1 and r2 are positions of atom1 and atom2 in the convention of
    # these diagrams:
    # https://docs.openforcefield.org/projects/toolkit/en/stable/users/virtualsites.html#applying-virtual-site-parameters
    r1 = interchange.positions[virtual_site_key.orientation_atom_indices[0]]
    r2 = interchange.positions[virtual_site_key.orientation_atom_indices[1]]

    potential_key = interchange["VirtualSites"].key_map[virtual_site_key]
    potential = interchange["VirtualSites"].potentials[potential_key]
    distance = potential.parameters["distance"]
    in_plane_angle = potential.parameters["inPlaneAngle"]
    out_of_plane_angle = potential.parameters["outOfPlaneAngle"]

    if out_of_plane_angle.m != 0.0:
        raise NotImplementedError(
            "Only planar `MonovalentLonePairType` is currently supported.",
        )

    if in_plane_angle.m != 0.0:
        raise NotImplementedError(
            "Only linear `MonovalentLonePairType` is currently supported.",
        )

    # r1 and r2 are positions of atom1 and atom2 in the convention of
    # these diagrams:
    # https://docs.openforcefield.org/projects/toolkit/en/stable/users/virtualsites.html#applying-virtual-site-parameters
    r1 = interchange.positions[virtual_site_key.orientation_atom_indices[0]]
    r2 = interchange.positions[virtual_site_key.orientation_atom_indices[1]]

    r2_r1_norm = numpy.linalg.norm((r2 - r1).m_as(unit.angstrom)) * unit.angstrom

    # The virtual site is placed at a distance opposite the r1 -> r2 vector
    return r1 - (r2 - r1) * (distance / r2_r1_norm)


def _get_divalent_lone_pair_virtual_site_positions(
    virtual_site_key,
    interchange,
) -> Quantity:
    r0 = interchange.positions[virtual_site_key.orientation_atom_indices[0]]
    r1 = interchange.positions[virtual_site_key.orientation_atom_indices[1]]
    r2 = interchange.positions[virtual_site_key.orientation_atom_indices[2]]

    r0_r1_bond_length = _get_separation_by_atom_indices(
        interchange,
        atom_indices=tuple(
            (
                virtual_site_key.orientation_atom_indices[0],
                virtual_site_key.orientation_atom_indices[1],
            ),
        ),
    )
    r0_r2_bond_length = _get_separation_by_atom_indices(
        interchange,
        atom_indices=tuple(
            (
                virtual_site_key.orientation_atom_indices[0],
                virtual_site_key.orientation_atom_indices[2],
            ),
        ),
    )

    if abs(r0_r1_bond_length - r0_r2_bond_length) > Quantity(1e-3, unit.nanometer):
        raise VirtualSiteTypeNotImplementedError(
            "Only symmetric geometries (i.e. r2 - r0 = r1 - r0) are currently supported",
        )

    potential_key = interchange["VirtualSites"].key_map[virtual_site_key]
    potential = interchange["VirtualSites"].potentials[potential_key]
    distance = potential.parameters["distance"]
    out_of_plane_angle = potential.parameters["outOfPlaneAngle"]

    if out_of_plane_angle.m_as(unit.degree) != 0.0:
        raise VirtualSiteTypeNotImplementedError(
            "Only planar `DivalentLonePairType` is currently supported.",
        )

    theta = _get_angle_by_atom_indices(
        interchange,
        atom_indices=tuple(
            (
                virtual_site_key.orientation_atom_indices[1],
                virtual_site_key.orientation_atom_indices[0],
                virtual_site_key.orientation_atom_indices[2],
            ),
        ),
    )

    rmid_distance = r0_r1_bond_length * numpy.cos(theta.m_as(unit.radian) * 0.5)
    rmid = (r1 + r2) / 2

    return r0 + (r0 - rmid) * (distance) / (rmid_distance)


def _get_trivalent_lone_pair_virtual_site_positions(
    virtual_site_key,
    interchange,
):
    potential_key = interchange["VirtualSites"].key_map[virtual_site_key]
    distance = (
        interchange["VirtualSites"]
        .potentials[potential_key]
        .parameters["distance"]
        .m_as(unit.nanometer)
    )

    center, a, b, c = (
        interchange.positions[index].m_as(unit.nanometer)
        for index in virtual_site_key.orientation_atom_indices
    )

    # clockwise vs. counter-clockwise matters here - manually correcting it later
    dir = numpy.cross(b - a, c - a)
    dir /= numpy.linalg.norm(dir)

    # if adding a differential of the (normalized) normal vector to the midpoint
    # of (a, b, c) ends up closer to the center
    if numpy.linalg.norm(
        center - (numpy.cross(b - a, c - a) + dir * 0.001),
    ) < numpy.linalg.norm(center - (numpy.cross(b - a, c - a) - dir * 0.001)):
        # then this vector is pointing _toward_ the central atom, or "above" in the spec
        pass
    else:
        # otherwise, this vector is pointing _away_ from the central atom, so we need to point it the other way
        dir *= -1

    return Quantity(center + dir * distance, unit.nanometer)


def _get_separation_by_atom_indices(
    interchange: Interchange,
    atom_indices: Iterable[int],
) -> Quantity:
    """
    Given indices of (two?) atoms, return the distance between them.

    A constraint distance is first searched for, then an equilibrium bond length.

    This is slow, but often necessary for converting virtual site "distances" to weighted
    averages (unitless) of orientation atom positions.
    """
    if "Constraints" in interchange.collections:
        collection = interchange["Constraints"]

        for key in collection.key_map:
            if (key.atom_indices == atom_indices) or (
                key.atom_indices[::-1] == atom_indices
            ):
                return collection.potentials[collection.key_map[key]].parameters[
                    "distance"
                ]

    if "Bonds" in interchange.collections:
        collection = interchange["Bonds"]

        for key in collection.key_map:
            if (key.atom_indices == atom_indices) or (
                key.atom_indices[::-1] == atom_indices
            ):
                return collection.potentials[collection.key_map[key]].parameters[
                    "length"
                ]

    raise ValueError(f"Could not find distance between atoms {atom_indices}")


def _get_angle_by_atom_indices(
    interchange: Interchange,
    atom_indices: Iterable[int],
) -> Quantity:
    """
    Given indices of three atoms, return the angle between them using the law of cosines.

    Distances are defined by the force field, not the positions.

    It is assumed that the second atom is the central atom of the angle.

            b
          /   \
         /     \
        a ----- c

    angle abc = arccos((ac^2 - ab^2 - bc^2) / (-2 * ab * bc)
    """
    ab = _get_separation_by_atom_indices(
        interchange,
        (atom_indices[0], atom_indices[1]),
    ).m_as(unit.nanometer)

    ac = _get_separation_by_atom_indices(
        interchange,
        (atom_indices[0], atom_indices[2]),
    ).m_as(unit.nanometer)

    bc = _get_separation_by_atom_indices(
        interchange,
        (atom_indices[1], atom_indices[2]),
    ).m_as(unit.nanometer)

    return Quantity(
        numpy.arccos(
            (ac**2 - ab**2 - bc**2) / (-2 * ab * bc),
        ),
        unit.radian,
    )
