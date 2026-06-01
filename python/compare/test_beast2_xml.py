"""Tests for the NEXUS -> BEAST 2.7 XML wrapper."""
from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compare.beast2_xml import nexus_to_beast2_xml, parse_nexus_matrix

NEXUS = (
    "#NEXUS\n\nBEGIN TAXA;\n    DIMENSIONS NTAX=3;\n    TAXLABELS Spk1 Spk2 Spk3 ;\nEND;\n\n"
    "BEGIN CHARACTERS;\n    DIMENSIONS NCHAR=2;\n"
    '    FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";\n'
    "    MATRIX\n"
    "        Spk1    10\n"
    "        Spk2    01\n"
    "        Spk3    ??\n"
    "    ;\nEND;\n"
)


def test_parse_matrix_extracts_sequences():
    seqs, nchar = parse_nexus_matrix(NEXUS)
    assert nchar == 2
    assert dict(seqs) == {"Spk1": "10", "Spk2": "01", "Spk3": "??"}


def test_parse_matrix_rejects_ragged_and_empty():
    with pytest.raises(ValueError):
        parse_nexus_matrix("#NEXUS\nBEGIN CHARACTERS;\n  MATRIX\n  Spk1 10\n  Spk2 0\n  ;\nEND;")
    with pytest.raises(ValueError):
        parse_nexus_matrix("#NEXUS\nno matrix here")


def test_xml_is_well_formed_and_has_expected_structure():
    xml = nexus_to_beast2_xml(NEXUS, chain_length=50000)
    root = ET.fromstring(xml)  # raises if not well-formed
    assert root.tag == "beast"
    assert root.get("version") == "2.7"

    data = root.find("data")
    assert data is not None and data.get("dataType") == "binary"
    assert len(data.findall("sequence")) == 3

    run = root.find("run")
    assert run is not None and run.get("chainLength") == "50000"

    # Tree must use a nested taxonset, never a `taxa` attribute (2.7 requirement).
    tree = root.find(".//tree[@id='Tree']")
    assert tree is not None and tree.get("taxa") is None
    assert tree.find("taxonset") is not None

    # The <map> aliases that let <prior>/<Uniform> resolve must be present.
    assert any(m.get("name") == "prior" for m in root.findall("map"))
    assert any(m.get("name") == "Uniform" for m in root.findall("map"))


def test_chain_length_must_be_positive():
    with pytest.raises(ValueError):
        nexus_to_beast2_xml(NEXUS, chain_length=0)


def test_taxon_names_are_xml_escaped():
    nexus = NEXUS.replace("Spk1", "A&B")
    xml = nexus_to_beast2_xml(nexus)
    assert 'taxon="A&amp;B"' in xml
    ET.fromstring(xml)  # still well-formed
