from typing import List, Optional, Union

from openff.toolkit import ForceField, Molecule, Topology
from openff.units import Quantity
from packaging.version import Version

from openff.interchange import Interchange
from openff.interchange.components.smirnoff import (
    SMIRNOFFAngleHandler,
    SMIRNOFFBondHandler,
    SMIRNOFFConstraintHandler,
    SMIRNOFFElectrostaticsHandler,
    SMIRNOFFImproperTorsionHandler,
    SMIRNOFFProperTorsionHandler,
    SMIRNOFFvdWHandler,
    SMIRNOFFVirtualSiteHandler,
)
from openff.interchange.smirnoff._positions import _infer_positions


def _create_interchange(
    force_field: ForceField,
    topology: Union[Topology, List[Molecule]],
    box: Optional[Quantity] = None,
    positions: Optional[Quantity] = None,
    charge_from_molecules: Optional[List[Molecule]] = None,
    partial_bond_orders_from_molecules: Optional[List[Molecule]] = None,
    allow_nonintegral_charges: bool = False,
) -> Interchange:
    interchange = Interchange()

    _topology = Interchange.validate_topology(topology)

    interchange.positions = _infer_positions(positions, _topology)

    interchange.box = box

    _bonds(interchange, force_field, _topology, partial_bond_orders_from_molecules)
    _constraints(interchange, force_field, _topology)
    _angles(interchange, force_field, _topology)
    _propers(interchange, force_field, _topology, partial_bond_orders_from_molecules)
    _impropers(interchange, force_field, _topology)

    _vdw(interchange, force_field, _topology)
    _electrostatics(
        interchange,
        force_field,
        _topology,
        charge_from_molecules,
        allow_nonintegral_charges,
    )
    _virtual_sites(interchange, force_field, _topology)

    interchange.topology = _topology

    return interchange


def _bonds(
    interchange: Interchange,
    force_field: ForceField,
    _topology: Topology,
    partial_bond_orders_from_molecules: Optional[List[Molecule]] = None,
):
    if "Bonds" not in force_field.registered_parameter_handlers:
        return

    if force_field["Bonds"].version == Version("0.3"):
        from openff.interchange.smirnoff._valence import _upconvert_bondhandler

        _upconvert_bondhandler(force_field["Bonds"])

    interchange.collections.update(
        {
            "Bonds": SMIRNOFFBondHandler._from_toolkit(
                parameter_handler=force_field["Bonds"],
                topology=_topology,
                partial_bond_orders_from_molecules=partial_bond_orders_from_molecules,
            ),
        },
    )


def _constraints(interchange: Interchange, force_field: ForceField, topology: Topology):
    interchange.collections.update(
        {
            "Constraints": SMIRNOFFConstraintHandler._from_toolkit(
                parameter_handler=[
                    handler
                    for handler in [
                        force_field._parameter_handlers.get("Bonds", None),
                        force_field._parameter_handlers.get("Constraints", None),
                    ]
                    if handler is not None
                ],
                topology=topology,
            ),
        },
    )


def _angles(interchange, force_field, _topology):
    if "Angles" not in force_field.registered_parameter_handlers:
        return

    interchange.collections.update(
        {
            "Angles": SMIRNOFFAngleHandler._from_toolkit(
                parameter_handler=force_field["Angles"],
                topology=_topology,
            ),
        },
    )


def _propers(
    interchange,
    force_field,
    _topology,
    partial_bond_orders_from_molecules=None,
):
    if "ProperTorsions" not in force_field.registered_parameter_handlers:
        return

    interchange.collections.update(
        {
            "ProperTorsions": SMIRNOFFProperTorsionHandler._from_toolkit(
                parameter_handler=force_field["ProperTorsions"],
                topology=_topology,
                partial_bond_orders_from_molecules=partial_bond_orders_from_molecules,
            ),
        },
    )


def _impropers(interchange, force_field, _topology):
    if "ImproperTorsions" not in force_field.registered_parameter_handlers:
        return

    interchange.collections.update(
        {
            "ImproperTorsions": SMIRNOFFImproperTorsionHandler._from_toolkit(
                parameter_handler=force_field["ImproperTorsions"],
                topology=_topology,
            ),
        },
    )


def _vdw(interchange: Interchange, force_field: ForceField, topology: Topology):
    if "vdW" not in force_field.registered_parameter_handlers:
        return

    interchange.collections.update(
        {
            "vdW": SMIRNOFFvdWHandler._from_toolkit(
                parameter_handler=force_field["vdW"],
                topology=topology,
            ),
        },
    )


def _electrostatics(
    interchange: Interchange,
    force_field: ForceField,
    topology: Topology,
    charge_from_molecules: Optional[List[Molecule]] = None,
    allow_nonintegral_charges: bool = False,
):
    if "Electrostatics" not in force_field.registered_parameter_handlers:
        return

    interchange.collections.update(
        {
            "Electrostatics": SMIRNOFFElectrostaticsHandler._from_toolkit(
                parameter_handler=[
                    handler
                    for handler in [
                        force_field._parameter_handlers.get(name, None)
                        for name in [
                            "Electrostatics",
                            "ChargeIncrementModel",
                            "ToolkitAM1BCC",
                            "LibraryCharges",
                        ]
                    ]
                    if handler is not None
                ],
                topology=topology,
                charge_from_molecules=charge_from_molecules,
                allow_nonintegral_charges=allow_nonintegral_charges,
            ),
        },
    )


def _virtual_sites(
    interchange: Interchange,
    force_field: ForceField,
    topology: Topology,
):
    if "VirtualSites" not in force_field.registered_parameter_handlers:
        return

    virtual_site_handler = SMIRNOFFVirtualSiteHandler()

    virtual_site_handler.exclusion_policy = force_field["VirtualSites"].exclusion_policy

    virtual_site_handler.store_matches(
        parameter_handler=force_field["VirtualSites"],
        topology=topology,
    )

    virtual_site_handler.store_potentials(
        parameter_handler=force_field["VirtualSites"],
        vdw_handler=interchange["vdW"],
        electrostatics_handler=interchange["Electrostatics"],
    )

    interchange.collections.update({"VirtualSites": virtual_site_handler})
