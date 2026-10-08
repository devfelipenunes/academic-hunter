"""O parsing do arXiv, exercitado sem rede.

O único teste que tocava este conector era `assert isinstance(results, list)` —
que aceita `[]`, exatamente o que `fetch` devolve quando a requisição falha. Ele
passava sem executar uma linha do parsing nem da paginação: no run completo,
`arxiv.py` ficava em 60,7% com as duas intactas.

Estes testes alimentam o conector com Atom de verdade, então um namespace que
muda ou um campo que some aparece aqui em vez de na coleta.
"""

import threading

import pytest

from academic_hunter.plugins.connectors.arxiv import ArxivConnector

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2024-01-01T00:00:00Z</published>
    <title>Ledgers at
      scale</title>
    <summary>We study ledgers
      and their throughput.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2402.00002v1</id>
    <published>2023-07-15T00:00:00Z</published>
    <title>Consensus without anchors</title>
    <summary>A survey.</summary>
  </entry>
</feed>
"""

EMPTY = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'


def entry(index):
    return (
        "<entry>"
        f"<id>http://arxiv.org/abs/2401.{index:05d}v1</id>"
        "<published>2024-03-04T00:00:00Z</published>"
        f"<title>Paper {index}</title>"
        f"<summary>Abstract {index}.</summary>"
        "</entry>"
    )


def feed(*entries):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>"
    )


class Response:
    def __init__(self, text):
        self.text = text


@pytest.fixture
def connector(monkeypatch):
    made = ArxivConnector(
        cache=None,
        settings={},
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(1),
        use_cache=False,
    )
    served = []

    def serve(*bodies):
        def request(url, timeout=None):
            served.append(url)
            return Response(bodies[min(len(served) - 1, len(bodies) - 1)])

        monkeypatch.setattr(made, "_raw_request", request)

    made.serve = serve
    made.served = served
    return made


def test_the_entries_become_papers(connector):
    connector.serve(ATOM)

    papers = connector.fetch(["ledger"], ["throughput"], limit=10)

    assert len(papers) == 2
    assert papers[0]["Title"] == "Ledgers at scale", "the title's newline was kept"
    assert papers[0]["Abstract"] == "We study ledgers and their throughput."
    assert papers[0]["Year"] == "2024"
    assert papers[0]["URL"] == "http://arxiv.org/abs/2401.00001v1"
    assert papers[1]["Year"] == "2023"
    assert papers[1]["Title"] == "Consensus without anchors"


def test_every_paper_is_stamped_with_the_source_and_its_preprint_status(connector):
    connector.serve(ATOM)

    papers = connector.fetch(["ledger"], ["throughput"], limit=10)

    for paper in papers:
        assert paper["Source"] == "ArXiv"
        assert paper["Venue"] == "ArXiv"
        assert paper["Peer_Reviewed"] == "No (Preprint)"
        assert paper["Type"] == "preprint"
        assert paper["Citations"] == 0


def test_the_query_reaches_the_history_and_the_url(connector):
    connector.serve(ATOM)

    connector.fetch(["ledger"], ["throughput"], limit=10)

    assert connector.query_history[0]["Source"] == "ArXiv"
    assert "ledger" in connector.query_history[0]["Query"]
    assert "search_query=" in connector.served[0]


def test_an_empty_feed_is_not_an_error(connector):
    connector.serve(EMPTY)

    assert connector.fetch(["ledger"], ["throughput"], limit=10) == []


def test_a_page_that_comes_back_full_is_followed_by_another(connector):
    """Paginates while the page is full, and stops on a short one."""
    connector.serve(feed(*(entry(i) for i in range(100))), feed(entry(100)))

    papers = connector.fetch(["ledger"], ["throughput"], limit=101)

    assert len(papers) == 101
    assert len(connector.served) == 2, "the second page was never requested"
    assert "start=100" in connector.served[1]
    assert papers[100]["Title"] == "Paper 100"


def test_a_failing_request_stops_with_what_it_has(connector, monkeypatch):
    monkeypatch.setattr(connector, "_raw_request", lambda url, timeout=None: None)

    assert connector.fetch(["ledger"], ["throughput"], limit=10) == []


def test_the_query_goes_over_https(connector):
    """A consulta carrega o tópico do pesquisador; `http://` a manda em claro."""
    connector.serve(EMPTY)

    connector.fetch(["ledger"], ["throughput"], limit=5)

    assert connector.served[0].startswith("https://"), connector.served[0]


def test_a_feed_carrying_an_entity_bomb_is_not_expanded(connector):
    """Atom nunca traz DTD, e `ET.fromstring` expande entidades internas.

    Um feed hostil — ou um registro envenenado no cache de requisições, que é lido
    e reparseado sem validação — faz o processo alocar muito mais do que recebeu.
    """
    bomb = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE feed [\n'
        '  <!ENTITY a "lollollollollol">\n'
        '  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n'
        '  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">\n'
        ']>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        '<entry><title>&c;</title><summary>x</summary>'
        '<id>http://arxiv.org/abs/1</id><published>2024-01-01T00:00:00Z</published>'
        '</entry></feed>'
    )
    connector.serve(bomb)

    papers = connector.fetch(["x"], ["y"], limit=5)

    assert not papers or "lollollollol" not in papers[0]["Title"], (
        "the document's internal entities were expanded"
    )


class RecordingCache:
    def __init__(self):
        self.written = {}

    def get(self, key):
        return None

    def set(self, key, value):
        self.written[key] = value


def test_a_page_that_does_not_parse_is_not_cached(connector):
    """A proxy in front of the API answers with an HTML error body and a 200.

    Caching before `parse_xml` accepted the page stored that body under the
    query URL, and every later run read it back and failed in the same place —
    with the network, the one thing that would have fixed it, never consulted
    again, because the cache hit short-circuits the fetch.
    """
    connector.use_cache = True
    connector.cache = RecordingCache()
    connector.serve("<html><body>502 Bad Gateway<br></body></html>")

    papers = connector.fetch(["ledger"], ["throughput"], limit=10)

    assert papers == []
    assert connector.cache.written == {}, "a page that never parsed was cached"


def test_a_page_that_parses_is_cached(connector):
    connector.use_cache = True
    connector.cache = RecordingCache()
    connector.serve(ATOM)

    connector.fetch(["ledger"], ["throughput"], limit=10)

    assert len(connector.cache.written) == 1, "the good page was not cached at all"


def test_a_cached_page_is_reparsed_and_not_refetched(connector):
    """The cache hit is only a hit if its payload is what gets parsed."""
    connector.use_cache = True
    cache = RecordingCache()
    cache.get = lambda key: ATOM
    connector.cache = cache
    connector.serve(EMPTY)

    papers = connector.fetch(["ledger"], ["throughput"], limit=10)

    assert len(papers) == 2, "the cached page was fetched over instead of parsed"
    assert connector.served == [], "the network was consulted for a cached URL"
    assert cache.written == {}, "the cached payload was written back over itself"
