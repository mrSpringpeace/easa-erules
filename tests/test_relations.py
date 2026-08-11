from __future__ import annotations

from easa_erules.model import (
    AcceptableMeansOfComplianceNode,
    RegulationDocument,
    RegulationRequirement,
)
from easa_erules.relations import build_relationship_map


def test_metadata_multi_rule_relation_preserves_all_targets_and_deduplicates_erules_id():
    doc = RegulationDocument(id="doc")
    one = RegulationRequirement(id="r1", erules_id="r1", designation="CS-23.1")
    two = RegulationRequirement(id="r2", erules_id="r2", designation="CS-23.2")
    meta = {"easa": {"related_requirements": ["CS 23.1 One", "CS 23.2 Two"]}}
    amc1 = AcceptableMeansOfComplianceNode(
        id="a1", erules_id="same", designation="AMC CS-23.1", metadata=meta
    )
    amc2 = AcceptableMeansOfComplianceNode(
        id="a2", erules_id="same", designation="AMC CS-23.2", metadata=meta
    )
    doc.add_children([one, amc1, two, amc2])
    relations = build_relationship_map(doc)
    assert relations.targets["same"] == {"r1", "r2"}
    assert len(relations.related_for(one)["amc"]) == 1
