from easa_erules.model import (
    FigureNode,
    HyperlinkNode,
    InternalReferenceNode,
    ParagraphNode,
    RegulationRequirement,
    TextNode,
)
from easa_erules.render import render_html_fragment


def test_fragment_escapes_text_validates_links_and_hides_asset_paths():
    rule = RegulationRequirement(id="rule", designation="CS-X.1", title="Unsafe <title>")
    paragraph = ParagraphNode()
    paragraph.add_children(
        [
            TextNode(text="<script>alert(1)</script>"),
            HyperlinkNode(text="bad", url="javascript:alert(1)"),
            InternalReferenceNode(text="next", target_id="rule-2", target_designation="CS-X.2"),
        ]
    )
    rule.add_children([paragraph, FigureNode(image_path="../../secret.png", alt_text="x")])
    fragment = render_html_fragment(rule)
    assert "<script>" not in fragment
    assert "javascript:" not in fragment
    assert 'data-erules-target-id="rule-2"' in fragment
    assert 'data-erules-asset=""' in fragment
    assert "secret.png" not in fragment
    assert "src=" not in fragment
    assert "<html" not in fragment and "<style" not in fragment
