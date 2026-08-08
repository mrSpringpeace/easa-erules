"""EASA Sources Registry."""

REGISTRY = {
    "cs-vla": {
        "title": "Very Light Aeroplanes",
        "authority": "EASA",
        "type": "certification-specification",
        "aliases": ["CS-VLA", "csvla", "vla"],
        "landing_page": "https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-very-light-aeroplanes-cs-vla",
        "preferred_format": "xml",
    },
    "cs-lsa": {
        "title": "Light Sport Aeroplanes",
        "authority": "EASA",
        "type": "certification-specification",
        "aliases": ["CS-LSA", "cslsa", "lsa"],
        "landing_page": "https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-light-sport-aeroplanes-cs-lsa",
        "preferred_format": "xml",
    },
    "cs-22": {
        "title": "Sailplanes and Powered Sailplanes",
        "authority": "EASA",
        "type": "certification-specification",
        "aliases": ["CS-22", "cs22"],
        "landing_page": "https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-sailplanes-and-powered-sailplanes-cs-22",
        "preferred_format": "xml",
    },
    "cs-23": {
        "title": "Normal-Category Aeroplanes",
        "authority": "EASA",
        "type": "certification-specification",
        "aliases": ["CS-23", "CS23", "cs23"],
        "landing_page": "https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-normal-category-aeroplanes-cs-23",
        "preferred_format": "xml",
    },
}


def get_source(doc_id: str) -> dict:
    """Get source by ID or alias."""
    doc_id = doc_id.lower()
    if doc_id in REGISTRY:
        return REGISTRY[doc_id]

    # Check aliases
    for key, source in REGISTRY.items():
        for alias in source.get("aliases", []):
            if alias.lower() == doc_id:
                return source

    raise KeyError(f"Unknown source: {doc_id}")


def list_sources() -> list:
    """List all available sources."""
    return [
        {"id": k, **v}
        for k, v in REGISTRY.items()
    ]