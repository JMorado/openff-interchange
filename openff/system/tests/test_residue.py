import mdtraj as md
from openff.toolkit.topology import Molecule
from simtk.openmm import app

from openff.system.components.misc import OFFBioTop
from openff.system.stubs import ForceField
from openff.system.tests.energy_tests.openmm import get_openmm_energies
from openff.system.utils import get_test_file_path


def test_residues():
    pdb = app.PDBFile(get_test_file_path("ALA_GLY/ALA_GLY.pdb"))
    traj = md.load(get_test_file_path("ALA_GLY/ALA_GLY.pdb"))
    mol = Molecule(get_test_file_path("ALA_GLY/ALA_GLY.sdf"), file_format="sdf")

    top = OFFBioTop.from_openmm(pdb.topology, unique_molecules=[mol])
    top.mdtop = traj.top

    assert top.n_topology_atoms == 29
    assert top.mdtop.n_residues == 4
    assert [r.name for r in top.mdtop.residues] == ["ACE", "ALA", "GLY", "NME"]

    ff = ForceField("openff-1.3.0.offxml")
    off_sys = ff.create_openff_system(top)

    # Assign positions and box vectors in order to run MM
    off_sys.positions = pdb.positions
    off_sys.box = [4.8, 4.8, 4.8]

    # Just ensure that a single-point energy can be obtained without error
    get_openmm_energies(off_sys)

    assert len(top.mdtop.select("resname ALA")) == 10
    assert [*off_sys.topology.mdtop.residues][-1].n_atoms == 6
