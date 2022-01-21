"""Temporary utilities to use an MDTraj Trajectory with an OpenFF Trajectory."""
import copy
from typing import TYPE_CHECKING, Any, Generator, List, Tuple

import mdtraj as md
from openff.toolkit.topology import Molecule, Topology

if TYPE_CHECKING:
    from mdtraj import Atom


class _OFFBioTop(Topology):
    """A subclass of an OpenFF Topology that carries around an MDTraj topology."""

    def __init__(self, mdtop: md.Topology, *args: Any, **kwargs: Any) -> None:
        self.mdtop = mdtop
        super().__init__(*args, **kwargs)

    def copy_initializer(self, other: Topology) -> None:
        # TODO: The OFFBioTop cannot use the `other` kwarg until TK 946 is resolved.
        self._aromaticity_model = other.aromaticity_model
        self._constrained_atom_pairs = copy.deepcopy(other.constrained_atom_pairs)
        self._box_vectors = copy.deepcopy(other.box_vectors)
        # self._reference_molecule_dicts = set()
        # TODO: Look into weakref and what it does. Having multiple topologies might cause a memory leak.
        self._reference_molecule_to_topology_molecules = copy.deepcopy(
            other._reference_molecule_to_topology_molecules
        )
        self._topology_molecules = copy.deepcopy(other.topology_molecules)

    @classmethod
    def from_molecules(cls, mdtop: md.Topology, molecules: List[Molecule]):
        topology = cls(mdtop=mdtop)
        for molecule in molecules:
            topology.add_molecule(molecule)

        return topology


def _store_bond_partners(mdtop: md.Topology) -> None:
    for atom in mdtop.atoms:
        atom._bond_partners = []
    for bond in mdtop.bonds:
        bond.atom1._bond_partners.append(bond.atom2)
        bond.atom2._bond_partners.append(bond.atom1)


def _iterate_angles(
    mdtop: md.Topology,
) -> Generator[Tuple["Atom", "Atom", "Atom"], None, None]:
    for atom1 in mdtop.atoms:
        for atom2 in atom1._bond_partners:
            for atom3 in atom2._bond_partners:
                if atom1 == atom3:
                    continue
                if atom1.index < atom3.index:
                    yield (atom1, atom2, atom3)
                else:
                    # Do not duplicate
                    pass  # yield (atom3, atom2, atom1)


def _iterate_propers(
    mdtop: md.Topology,
) -> Generator[Tuple["Atom", "Atom", "Atom", "Atom"], None, None]:
    for atom1 in mdtop.atoms:
        for atom2 in atom1._bond_partners:
            for atom3 in atom2._bond_partners:
                if atom1 == atom3:
                    continue
                for atom4 in atom3._bond_partners:
                    if atom4 in (atom1, atom2):
                        continue

                    if atom1.index < atom4.index:
                        yield (atom1, atom2, atom3, atom4)
                    else:
                        # Do no duplicate
                        pass  # yield (atom4, atom3, atom2, atom1)


def _iterate_impropers(
    mdtop: md.Topology,
) -> Generator[Tuple["Atom", "Atom", "Atom", "Atom"], None, None]:
    for atom1 in mdtop.atoms:
        for atom2 in atom1._bond_partners:
            for atom3 in atom2._bond_partners:
                if atom1 == atom3:
                    continue
                for atom4 in atom2._bond_partners:
                    if atom4 in (atom3, atom1):
                        continue

                    # Central atom first
                    yield (atom2, atom1, atom3, atom4)


def _iterate_pairs(mdtop: md.Topology) -> Generator[Tuple["Atom", "Atom"], None, None]:
    # TODO: Replace this with Topology.nth_degree_neighbors after
    # OpenFF Toolkit 0.9.3 or later
    for bond in mdtop.bonds:
        atom_i = bond.atom1
        atom_j = bond.atom2
        for atom_i_partner in atom_i._bond_partners:
            for atom_j_partner in atom_j._bond_partners:
                if atom_i_partner == atom_j_partner:
                    continue

                if atom_i_partner in atom_j_partner._bond_partners:
                    continue

                if atom_j_partner in atom_i_partner._bond_partners:
                    continue

                if {*atom_i_partner._bond_partners}.intersection(
                    {*atom_j_partner._bond_partners}
                ):
                    continue

                else:
                    if atom_i_partner.index > atom_j_partner.index:
                        yield (atom_j_partner, atom_i_partner)
                    else:
                        yield (atom_i_partner, atom_j_partner)


def _get_num_h_bonds(mdtop: md.Topology) -> int:
    """Get the number of (covalent) bonds containing a hydrogen atom."""
    if not isinstance(mdtop, md.Topology):
        raise Exception(
            "Bad topology argument passed to _get_num_h_bonds, expected mdtraj.Topology"
        )

    n_bonds_containing_hydrogen = 0
    for bond in mdtop.bonds:
        if (bond.atom1.element.atomic_number == 1) or (
            bond.atom2.element.atomic_number == 1
        ):
            n_bonds_containing_hydrogen += 1

    return n_bonds_containing_hydrogen


def _combine_topologies(topology1: _OFFBioTop, topology2: _OFFBioTop) -> _OFFBioTop:
    """
    Experimental shim for combining _OFFBioTop objects.

    Note that this really only operates on the mdtops.
    """
    mdtop1 = copy.deepcopy(topology1.mdtop)
    mdtop2 = copy.deepcopy(topology2.mdtop)

    mdtop = md.Topology()
    first_topology_chain = mdtop.add_chain()
    second_topology_chain = mdtop.add_chain()

    for residue in mdtop1.residues:
        this_residue = mdtop.add_residue(
            name=residue.name,
            chain=first_topology_chain,
            resSeq=residue.resSeq,
            segment_id=residue.segment_id,
        )
        for atom in residue.atoms:
            mdtop.add_atom(atom.name, atom.element, this_residue)

    for residue in mdtop2.residues:
        this_residue = mdtop.add_residue(
            name=residue.name,
            chain=second_topology_chain,
            resSeq=residue.resSeq,
            segment_id=residue.segment_id,
        )
        for atom in residue.atoms:
            mdtop.add_atom(atom.name, atom.element, this_residue)

    atom_offset = mdtop1.n_atoms

    for bond in mdtop1.bonds:
        mdtop.add_bond(
            atom1=mdtop.atom(bond.atom1.index),
            atom2=mdtop.atom(bond.atom2.index),
        )

    for bond in mdtop2.bonds:
        mdtop.add_bond(
            atom1=mdtop.atom(bond.atom1.index + atom_offset),
            atom2=mdtop.atom(bond.atom2.index + atom_offset),
        )

    combined_topology = _OFFBioTop(mdtop=mdtop)

    return combined_topology
