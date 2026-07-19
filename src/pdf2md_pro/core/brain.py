"""Ottimizzazione Second Brain: markdown pronto per Obsidian/Logseq e affini.

Trasformazioni (`optimize_parts`, per pagina, provenienza preservata):
- de-duplica header/footer ripetuti tra le pagine (righe correnti, numeri pagina)
- ricuce le sillabazioni a cavallo pagina (`paro-` / `la` → `parola`)
- unisce i paragrafi spezzati dal cambio pagina
- normalizza i heading: un solo H1 (il titolo), livelli H2-H4 senza salti

L'attribution (strumento, motore, tempo, configurazione) è aggiunta una sola
volta da `pipeline.convert()` per tutti i file, second brain o meno: non è
responsabilità di questo modulo.

`check_markdown` verifica gli stessi criteri su un file esistente e dice se è
già ottimizzato o da ottimizzare.
"""

from __future__ import annotations

import re

from pdf2md_pro import __version__
from pdf2md_pro.core.naming import derive_topic

MAX_HEADING_LEVEL = 4
REPEAT_RATIO = 0.6  # riga presente in ≥60% delle pagine = header/footer corrente
MIN_REPEAT_PAGES = 3
BRAIN_MARKER = re.compile(r'^optimized:\s*"?second-brain"?\s*$', re.MULTILINE)

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_PAGE_NUMBER = re.compile(r"^\s*(?:pagina|page)?\s*\d+\s*(?:di|of|/)?\s*\d*\s*$", re.IGNORECASE)
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _normalize_line(line: str) -> str:
    """Chiave di confronto per header/footer: senza numeri né spazi extra."""
    return re.sub(r"\d+", "#", line.strip().lower())


def _edge_lines(part: str) -> list[str]:
    """Solo prima e ultima riga non vuota: le posizioni tipiche di header/footer.
    Le righe interne non concorrono mai alla de-duplica (proteggono il contenuto)."""
    lines = [l for l in part.splitlines() if l.strip()]
    if not lines:
        return []
    return [_normalize_line(lines[0])] + ([_normalize_line(lines[-1])] if len(lines) > 1 else [])


def _find_repeated_edges(parts: list[str]) -> set[str]:
    if len(parts) < MIN_REPEAT_PAGES:
        return set()
    counts: dict[str, int] = {}
    for part in parts:
        for key in set(_edge_lines(part)):
            counts[key] = counts.get(key, 0) + 1
    threshold = max(MIN_REPEAT_PAGES, int(len(parts) * REPEAT_RATIO))
    return {k for k, n in counts.items() if n >= threshold and k}


def _strip_repeated(part: str, repeated: set[str]) -> str:
    """Rimuove header/footer solo ai bordi della pagina, mai nel corpo."""
    def is_junk(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if _PAGE_NUMBER.match(line):
            return True
        return _normalize_line(line) in repeated and not _HEADING.match(stripped)

    lines = part.splitlines()
    start, end = 0, len(lines)
    # dal bordo alto: salta vuote e junk finché si incontra contenuto vero
    while start < end and (not lines[start].strip() or is_junk(lines[start])):
        if lines[start].strip() and not is_junk(lines[start]):
            break
        start += 1
    while end > start and (not lines[end - 1].strip() or is_junk(lines[end - 1])):
        if lines[end - 1].strip() and not is_junk(lines[end - 1]):
            break
        end -= 1
    return "\n".join(lines[start:end])


def _reflow_boundary(prev: str, nxt: str) -> tuple[str, str]:
    """Ricuce sillabazione e paragrafo spezzato tra due pagine consecutive."""
    hyphen = re.search(r"(\w+)-\s*$", prev)
    cont = re.match(r"\s*([a-zàèéìòù]\w*)", nxt)
    if hyphen and cont:
        prev = prev[: hyphen.start(1)] + hyphen.group(1) + cont.group(1)
        return prev, nxt[cont.end():].lstrip()
    # paragrafo spezzato: la pagina finisce senza punteggiatura, la successiva
    # riparte in minuscolo → niente riga vuota fra le due
    if re.search(r"[a-zàèéìòù,;]\s*$", prev) and re.match(r"\s*[a-zàèéìòù]", nxt):
        return prev.rstrip() + " ", nxt.lstrip()
    return prev, nxt


def optimize_parts(parts: list[str], title: str) -> list[str]:
    """Ottimizza le pagine (già in markdown) per il second brain.

    Lavora sulla lista di pagine per preservare l'attribuzione di provenienza:
    il chiamante ricalcola le righe dopo la trasformazione."""
    repeated = _find_repeated_edges(parts)
    parts = [_strip_repeated(p, repeated) for p in parts]

    for i in range(len(parts) - 1):
        parts[i], parts[i + 1] = _reflow_boundary(parts[i], parts[i + 1])

    normalized_parts = []
    last_level_holder = {"last": 1}
    for part in parts:
        lines = part.splitlines()
        out = []
        for line in lines:
            m = _HEADING.match(line)
            if not m:
                out.append(line)
                continue
            level = len(m.group(1))
            if level == 1:
                level = 2  # H1 riservato al titolo documento
            level = min(level, MAX_HEADING_LEVEL, last_level_holder["last"] + 1)
            out.append("#" * level + " " + m.group(2))
            last_level_holder["last"] = level
        normalized_parts.append("\n".join(out))
    parts = normalized_parts

    # titolo H1 in testa alla prima pagina; l'attribution la aggiunge pipeline.convert()
    if parts:
        parts[0] = f"# {title}\n\n" + parts[0].lstrip("\n")
    return parts


def brain_frontmatter(frontmatter: dict, body: str) -> dict:
    """Arricchisce il frontmatter con le properties da second brain."""
    topic = derive_topic(body)
    enriched = dict(frontmatter)
    enriched.update(
        type="pdf-import",
        tags=["pdf-import"] + ([topic] if topic and topic != "doc" else []),
        aliases=[frontmatter.get("title", "")],
        optimized="second-brain",
        processed_with=f"pdf2md-pro v{__version__}",
    )
    return enriched


# --- Verifica -----------------------------------------------------------------

def check_markdown(text: str) -> dict:
    """Verifica se un markdown è ottimizzato per il second brain.

    Ritorna {"optimized": bool, "checks": [{id, ok, label, detail}]}."""
    checks = []

    def add(check_id: str, ok: bool, label: str, detail: str = "") -> None:
        checks.append({"id": check_id, "ok": ok, "label": label, "detail": detail})

    fm_match = _FRONTMATTER.match(text)
    fm_text = fm_match.group(0) if fm_match else ""
    body = _FRONTMATTER.sub("", text)

    add("frontmatter", bool(fm_match), "Frontmatter YAML presente")
    add("marker", bool(BRAIN_MARKER.search(fm_text)), "Marcatore 'optimized: second-brain'")
    add("tags", bool(re.search(r"^tags:", fm_text, re.MULTILINE)), "Properties 'tags' nel frontmatter")

    headings = [(len(m.group(1)), m.group(2)) for m in (_HEADING.match(l) for l in body.splitlines()) if m]
    h1_count = sum(1 for level, _ in headings if level == 1)
    add("single_h1", h1_count == 1, "Un solo H1 (titolo)", f"trovati {h1_count} H1")

    too_deep = sum(1 for level, _ in headings if level > MAX_HEADING_LEVEL)
    add("max_depth", too_deep == 0, f"Profondità massima H{MAX_HEADING_LEVEL}",
        f"{too_deep} heading oltre H{MAX_HEADING_LEVEL}" if too_deep else "")

    jumps = 0
    last = None
    for level, _ in headings:
        if last is not None and level > last + 1:
            jumps += 1
        last = level
    add("no_jumps", jumps == 0, "Nessun salto di livello nei heading",
        f"{jumps} salti (es. H2→H4)" if jumps else "")

    hyphen_breaks = len(re.findall(r"\w-\n\s*[a-zàèéìòù]", body))
    add("no_hyphen_breaks", hyphen_breaks == 0, "Nessuna sillabazione spezzata tra pagine",
        f"{hyphen_breaks} occorrenze" if hyphen_breaks else "")

    add("attribution", "pdf2md-pro" in body, "Attribution dello strumento presente")

    return {"optimized": all(c["ok"] for c in checks), "checks": checks}
