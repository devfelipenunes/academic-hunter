"""O port tem de descrever o conector que existe.

`ConnectorPort` é `runtime_checkable`, e isso só verifica que o método **existe** —
nunca a assinatura. Um port que descrevia `fetch(anchors: Dict[str, List[str]])`
passava por todas as verificações enquanto cada implementação, e o próprio caller,
usavam uma lista plana de termos. Nada em execução distingue as duas formas; só a
anotação estava errada, e é ela que um leitor segue.
"""

from typing import List, get_type_hints

from academic_hunter.core.ports import ConnectorPort
from academic_hunter.plugins.connectors import CONNECTORS


def _fetch_annotations(target):
    """``fetch``'s annotations, with the module's string forms resolved."""
    return get_type_hints(target.fetch)


def test_the_port_describes_the_fetch_every_connector_implements():
    port = _fetch_annotations(ConnectorPort)

    assert port, "the port's fetch carries no annotations at all"

    for name, connector in CONNECTORS.items():
        annotations = _fetch_annotations(connector)
        assert annotations == port, f"{name}.fetch is annotated {annotations}, but the port says {port}"


def test_the_port_promises_a_flat_term_list():
    """The shape, pinned: a category map here is the defect, not a style choice.

    The pipeline's worker iterates the categories itself and calls `fetch` once
    per pair, so a connector never sees the config's grouping.
    """
    hints = _fetch_annotations(ConnectorPort)

    assert hints["anchors"] == List[str]
    assert hints["tech_strings"] == List[str]
