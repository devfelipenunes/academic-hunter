"""Build the grading page for a pool of candidates.

The pool lists the documents; a human still has to say how relevant each one is
to the query the run was ordered by, and the judged collection is what turns a
score threshold into precision and recall. This renders the pool as a page a
person can work through, and writes back the grade file in the shape
``qrels.py`` loads.

The page is self-contained: the documents are embedded, grades live in the
browser's own storage between visits, and the export button produces the qrels
JSON. Nothing is sent anywhere, and no server is involved.

Usage::

    python evaluation/build_pool_grading_page.py \\
        evaluation/pool_candidates_blockchain_ai.json \\
        evaluation/pool_grading_page.html
"""

import argparse
import json
from pathlib import Path


def load_pool(path):
    """The pool and the query it was selected for.

    The query is not optional. Grading without it means grading against
    whatever the judge remembers of the topic, and the judged collection then
    measures agreement with a different information need from the one the run
    was ordered by.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    query = str(data.get("ranking_query") or "").strip()
    if not query:
        raise SystemExit(
            f"{path} carries no ranking_query, so there is nothing to grade "
            "against. The pool of a run ordered by a query has to record it."
        )
    documents = data.get("documents")
    if not isinstance(documents, dict) or not documents:
        raise SystemExit(f"{path} carries no documents.")
    return data, query, documents


def as_rows(documents):
    """One row per document, in a fixed order that hides the pipeline's own.

    The pool file is written as ``top-25-by-score`` followed by the random 25,
    so its order states the answer: the first half is the papers the pipeline
    liked most. Rendering that order invites a judge to agree with the ranking
    they are supposed to be testing, and the agreement would then be measured
    and reported as accuracy. Sorted by a hash of the id instead — arbitrary,
    but the same on every build, and the same for every reader.
    """
    rows = []
    for doc_id, doc in documents.items():
        rows.append({
            "id": doc_id,
            "title": str(doc.get("title") or ""),
            "doi": str(doc.get("doi") or ""),
            "year": str(doc.get("year") or ""),
            "source": str(doc.get("source") or ""),
            "citations": str(doc.get("citations") or "0"),
            "score": doc.get("pipeline_relevance_score"),
            "abstract": str(doc.get("abstract") or ""),
        })
    rows.sort(key=lambda row: (_stable_key(row["id"]), row["id"]))
    return rows


def _stable_key(text):
    """A hash that does not move between interpreter runs.

    ``hash()`` is salted per process, so a page rebuilt from the same pool
    would come out in a different order — and two readers comparing notes would
    be looking at two different documents.
    """
    return sum((i + 1) * ord(ch) for i, ch in enumerate(text)) % 100003


TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pool de Julgamento</title>
<style>
  :root {
    --bg: #f6f6f4;
    --surface: #ffffff;
    --ink: #1c1c1a;
    --muted: #6b6b66;
    --line: #deded8;
    --accent: #2f5d50;
    --g0: #b04a3f;
    --g1: #b5852f;
    --g2: #2f6b4f;
    --shadow: 0 1px 2px rgba(0,0,0,.06), 0 8px 24px rgba(0,0,0,.05);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #16181a;
      --surface: #1f2226;
      --ink: #e8e8e4;
      --muted: #9a9a94;
      --line: #32363b;
      --accent: #7fb8a5;
      --g0: #d9736a;
      --g1: #d6ac5c;
      --g2: #6fbf95;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
    }
  }
  :root[data-theme="dark"] {
    --bg: #16181a;
    --surface: #1f2226;
    --ink: #e8e8e4;
    --muted: #9a9a94;
    --line: #32363b;
    --accent: #7fb8a5;
    --g0: #d9736a;
    --g1: #d6ac5c;
    --g2: #6fbf95;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 0 16px 96px;
  }
  .wrap { max-width: 860px; margin: 0 auto; }
  header { padding: 40px 0 8px; }
  h1 { font-size: 1.6rem; margin: 0 0 6px; letter-spacing: -.01em; }
  .sub { color: var(--muted); font-size: .9rem; margin: 0 0 24px; }
  .need {
    background: var(--surface); border: 1px solid var(--line);
    border-left: 3px solid var(--accent); border-radius: 8px;
    padding: 16px 18px; box-shadow: var(--shadow); margin-bottom: 8px;
  }
  .need h2 {
    font-size: .72rem; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); margin: 0 0 8px; font-weight: 600;
  }
  .need p { margin: 0; font-size: 1rem; }
  .scale { color: var(--muted); font-size: .86rem; margin: 14px 0 28px; }
  .scale b { color: var(--ink); font-weight: 600; }
  .bar {
    position: sticky; top: 0; z-index: 20; background: var(--bg);
    padding: 12px 0; margin: 0 0 8px; border-bottom: 1px solid var(--line);
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  }
  .count { font-variant-numeric: tabular-nums; font-weight: 600; }
  button {
    font: inherit; color: var(--ink); background: var(--surface);
    border: 1px solid var(--line); border-radius: 6px;
    padding: 6px 12px; cursor: pointer;
  }
  button:hover { border-color: var(--accent); }
  button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .spacer { flex: 1 1 auto; }
  .card {
    background: var(--surface); border: 1px solid var(--line); border-radius: 8px;
    padding: 18px; margin-bottom: 14px; box-shadow: var(--shadow);
  }
  .card.graded { border-left: 3px solid var(--accent); }
  .meta { color: var(--muted); font-size: .82rem; display: flex; flex-wrap: wrap; gap: 4px 14px; margin-bottom: 10px; }
  .meta .num { font-variant-numeric: tabular-nums; }
  h3 { font-size: 1.02rem; margin: 0 0 8px; line-height: 1.35; }
  h3 a { color: inherit; text-decoration: none; border-bottom: 1px solid var(--line); }
  h3 a:hover { border-color: var(--accent); }
  .abstract { color: var(--muted); font-size: .9rem; margin: 0 0 14px; }
  .abstract.clamped {
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .more { background: none; border: 0; padding: 0; color: var(--accent); font-size: .85rem; cursor: pointer; text-decoration: underline; }
  .grades { display: flex; gap: 8px; flex-wrap: wrap; }
  .grades button { min-width: 92px; text-align: center; }
  .grades button[data-grade="0"][aria-pressed="true"] { color: var(--g0); border-color: var(--g0); }
  .grades button[data-grade="1"][aria-pressed="true"] { color: var(--g1); border-color: var(--g1); }
  .grades button[data-grade="2"][aria-pressed="true"] { color: var(--g2); border-color: var(--g2); }
  .hint { color: var(--muted); font-size: .8rem; margin-top: 10px; }
  .score { display: none; }
  body.show-scores .score { display: inline; }
  .hidden { display: none !important; }
  dialog {
    border: 1px solid var(--line); border-radius: 8px; background: var(--surface);
    color: var(--ink); max-width: 640px; width: calc(100% - 32px); padding: 22px;
    box-shadow: var(--shadow);
  }
  dialog::backdrop { background: rgba(0,0,0,.45); }
  textarea {
    width: 100%; height: 200px; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
    background: var(--bg); color: var(--ink); border: 1px solid var(--line);
    border-radius: 6px; padding: 12px; resize: vertical;
  }
  @media (max-width: 520px) {
    .grades button { flex: 1 1 100%; }
    .bar { position: static; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Pool de Julgamento</h1>
    <p class="sub">__N__ documentos &middot; run __RUN__ &middot; __SELECTION__</p>
    <div class="need">
      <h2>A consulta que ordenou estes documentos</h2>
      <p>__QUERY__</p>
    </div>
    <p class="scale">
      Julgue cada resumo contra essa consulta, não contra o tema em geral:
      <b>0</b> = fora do assunto &middot; <b>1</b> = parcialmente relevante &middot;
      <b>2</b> = diretamente relevante. A mesma escala do
      <code>qrels_pilot_genre_analysis.json</code>.
    </p>
  </header>

  <div class="bar">
    <span class="count" id="count">0 de __N__ julgados</span>
    <span class="spacer"></span>
    <button id="hide-graded" aria-pressed="false">Ocultar julgados</button>
    <button id="toggle-scores" aria-pressed="false">Mostrar pontuação</button>
    <button id="expand-all">Expandir resumos</button>
    <button id="export">Exportar qrels</button>
  </div>

  <div class="card hidden" id="nostore" style="border-left:3px solid var(--g1)">
    <strong>Os julgamentos não estão sendo guardados.</strong>
    Este navegador recusou o armazenamento local, o que acontece quando a página
    é aberta direto de um arquivo (<code>file://</code>). Os julgamentos valem
    enquanto a aba estiver aberta e o botão <em>Exportar qrels</em> continua
    funcionando, mas um recarregamento perde tudo. Para guardar de verdade,
    sirva a pasta e abra por <code>http://localhost:8000/...</code>.
  </div>

  <div id="cards"></div>
</div>

<dialog id="export-dialog">
  <h2 style="margin:0 0 6px;font-size:1.1rem">Coleção julgada</h2>
  <p style="color:var(--muted);font-size:.88rem;margin:0 0 12px">
    Salve como <code>evaluation/qrels_blockchain_ai.json</code>. É este arquivo
    que o <code>calibrate_inclusion_threshold</code> lê.
  </p>
  <textarea id="export-text" readonly></textarea>
  <div style="display:flex;gap:8px;margin-top:14px">
    <button id="copy">Copiar</button>
    <button id="download">Baixar arquivo</button>
    <span class="spacer"></span>
    <button id="close">Fechar</button>
  </div>
</dialog>

<script>
const DOCS = __DOCS__;
const QUERY = __QUERY__;
const RUN = __RUN_JSON__;
const KEY = "__STORAGE_KEY__";

function readGrades() {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (e) {
    return {};
  }
}

const grades = readGrades();

function storageWorks() {
  try {
    const probe = KEY + ":probe";
    localStorage.setItem(probe, "1");
    const ok = localStorage.getItem(probe) === "1";
    localStorage.removeItem(probe);
    return ok;
  } catch (e) {
    return false;
  }
}

function saveGrades() {
  try {
    localStorage.setItem(KEY, JSON.stringify(grades));
  } catch (e) {
    void e;
  }
}

const labels = {0: "Fora", 1: "Parcial", 2: "Direto"};
const cards = document.getElementById("cards");

if (!storageWorks()) {
  document.getElementById("nostore").classList.remove("hidden");
}

function render() {
  cards.textContent = "";
  DOCS.forEach((doc, i) => {
    const grade = grades[doc.id];
    const card = document.createElement("article");
    card.className = "card" + (grade === undefined ? "" : " graded");
    card.dataset.id = doc.id;

    const meta = document.createElement("div");
    meta.className = "meta";
    const bits = [doc.year, doc.source, doc.citations + " citações"];
    if (doc.doi) bits.push(doc.doi);
    bits.push("#" + (i + 1));
    bits.forEach((text, k) => {
      const span = document.createElement("span");
      span.textContent = text;
      if (k === 2) span.className = "num";
      meta.appendChild(span);
    });
    const score = document.createElement("span");
    score.className = "score num";
    score.textContent = "score " + doc.score;
    meta.appendChild(score);
    card.appendChild(meta);

    const title = document.createElement("h3");
    const text = document.createElement("a");
    text.textContent = doc.title;
    text.href = doc.doi ? "https://doi.org/" + doc.doi : "#";
    text.target = "_blank";
    text.rel = "noopener noreferrer";
    title.appendChild(text);
    card.appendChild(title);

    const abstract = document.createElement("p");
    abstract.className = "abstract clamped";
    abstract.textContent = doc.abstract;
    card.appendChild(abstract);
    const more = document.createElement("button");
    more.className = "more";
    more.textContent = "Ler tudo";
    more.addEventListener("click", () => {
      const clamped = abstract.classList.toggle("clamped");
      more.textContent = clamped ? "Ler tudo" : "Recolher";
    });
    card.appendChild(more);

    const row = document.createElement("div");
    row.className = "grades";
    [0, 1, 2].forEach((value) => {
      const button = document.createElement("button");
      button.dataset.grade = String(value);
      button.textContent = value + " — " + labels[value];
      button.setAttribute("aria-pressed", String(grade === value));
      button.addEventListener("click", () => {
        if (grades[doc.id] === value) delete grades[doc.id];
        else grades[doc.id] = value;
        saveGrades();
        render();
      });
      row.appendChild(button);
    });
    card.appendChild(row);
    cards.appendChild(card);
  });
  updateCount();
  applyFilters();
}

function updateCount() {
  const done = Object.keys(grades).length;
  document.getElementById("count").textContent = done + " de " + DOCS.length + " julgados";
}

function applyFilters() {
  const hidden = document.getElementById("hide-graded").getAttribute("aria-pressed") === "true";
  cards.querySelectorAll(".card").forEach((card) => {
    const graded = Object.prototype.hasOwnProperty.call(grades, card.dataset.id);
    card.classList.toggle("hidden", hidden && graded);
  });
}

document.getElementById("hide-graded").addEventListener("click", (e) => {
  const on = e.currentTarget.getAttribute("aria-pressed") === "true";
  e.currentTarget.setAttribute("aria-pressed", String(!on));
  applyFilters();
});

document.getElementById("toggle-scores").addEventListener("click", (e) => {
  const on = e.currentTarget.getAttribute("aria-pressed") === "true";
  e.currentTarget.setAttribute("aria-pressed", String(!on));
  document.body.classList.toggle("show-scores", !on);
});

document.getElementById("expand-all").addEventListener("click", (e) => {
  const expand = e.currentTarget.textContent === "Expandir resumos";
  e.currentTarget.textContent = expand ? "Recolher resumos" : "Expandir resumos";
  cards.querySelectorAll(".abstract").forEach((a) => a.classList.toggle("clamped", !expand));
  cards.querySelectorAll(".more").forEach((b) => { b.textContent = expand ? "Recolher" : "Ler tudo"; });
});

function payload() {
  const judgments = {};
  DOCS.map((d) => d.id).sort().forEach((id) => {
    if (Object.prototype.hasOwnProperty.call(grades, id)) judgments[id] = grades[id];
  });
  return {
    description: "Julgamento humano do pool de blockchain x IA (run " + RUN + "). Escala 0/1/2 contra a consulta registrada abaixo.",
    provenance: {
      pool: __POOL_JSON__,
      run: RUN,
      source_csv: __SOURCE_CSV_JSON__,
      selection: __SELECTION_JSON__,
      grader: "humano, um julgador",
      judged: Object.keys(judgments).length,
      of: DOCS.length,
      note: "Os documentos foram apresentados em ordem fixa derivada do id, e a pontuação do pipeline ficou oculta por omissão, para o julgamento não ser ancorado pela ordenação que ele existe para medir. Quem exportar depois de revelar a pontuação deve dizê-lo aqui."
    },
    queries: {
      "blockchain_ai": {
        text: QUERY,
        topic: "blockchain_ai",
        pool: DOCS.map((d) => d.id),
        judgments: judgments
      }
    }
  };
}

document.getElementById("export").addEventListener("click", () => {
  document.getElementById("export-text").value = JSON.stringify(payload(), null, 2);
  document.getElementById("export-dialog").showModal();
});
document.getElementById("close").addEventListener("click", () => document.getElementById("export-dialog").close());
document.getElementById("copy").addEventListener("click", async (e) => {
  const text = document.getElementById("export-text");
  try {
    await navigator.clipboard.writeText(text.value);
    e.currentTarget.textContent = "Copiado";
  } catch (err) {
    text.select();
    e.currentTarget.textContent = "Selecione e copie";
  }
  setTimeout(() => { e.currentTarget.textContent = "Copiar"; }, 1600);
});
document.getElementById("download").addEventListener("click", () => {
  const blob = new Blob([document.getElementById("export-text").value], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "qrels_blockchain_ai.json";
  a.click();
  URL.revokeObjectURL(url);
});

render();
</script>
</body>
</html>
"""


def render(pool, query, rows, pool_path):
    html = TEMPLATE
    html = html.replace("__DOCS__", json.dumps(rows, ensure_ascii=False))
    html = html.replace("__QUERY__", json.dumps(query, ensure_ascii=False))
    html = html.replace("__RUN_JSON__", json.dumps(run_of(pool), ensure_ascii=False))
    html = html.replace("__POOL_JSON__", json.dumps(str(pool_path), ensure_ascii=False))
    html = html.replace("__SELECTION_JSON__", json.dumps(str(pool.get("selection") or ""), ensure_ascii=False))
    html = html.replace("__SOURCE_CSV_JSON__", json.dumps(str(pool.get("source_csv") or ""), ensure_ascii=False))
    html = html.replace("__SELECTION__", str(pool.get("selection") or ""))
    html = html.replace("__RUN__", run_of(pool))
    html = html.replace("__STORAGE_KEY__", "grades:" + run_of(pool))
    html = html.replace("__N__", str(len(rows)))
    return html


def run_of(pool):
    """The run timestamp, read off the source CSV name rather than retyped."""
    csv = str(pool.get("source_csv") or "")
    return csv.rsplit("_", 1)[-1][:-4] if csv else "desconhecido"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pool", help="the pool_candidates_*.json to render")
    parser.add_argument("output", help="the .html to write")
    args = parser.parse_args()

    pool_path = Path(args.pool)
    pool, query, documents = load_pool(pool_path)
    rows = as_rows(documents)

    if len(rows) != len(documents):
        raise SystemExit("a document was lost building the rows")

    output = Path(args.output)
    output.write_text(render(pool, query, rows, pool_path), encoding="utf-8")
    print(f"{output}: {len(rows)} documents, run {run_of(pool)}")


if __name__ == "__main__":
    main()
