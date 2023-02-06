"""
Plugins for custom SMIRNOFF types.
"""
from setuptools import setup

setup(
    name="nonbonded_plugins",
    package_data={
        "nonbonded_plugins": ["py.typed"],
    },
    include_package_data=True,
    entry_points={
        "openff.toolkit.plugins.handlers": [
            "BuckinghamHandler = nonbonded_plugins:BuckinghamHandler",
        ],
        "openff.interchange.plugins.collections": [
            "BuckinghamCollection = nonbonded_plugins:SMIRNOFFBuckinghamCollection",
        ],
    },
)
