"""Modulo per la comparazione visiva e tipografica (Quality Audit) tra PDF originale e Markdown estratto."""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
import pymupdf

@dataclass
class TypoStats:
    h1: int = 0
    h2: int = 0
    h3: int = 0
    bold: int = 0
    italic: int = 0
    tables: int = 0
    images: int = 0
    characters: int = 0

def analyze_markdown(md_text: str) -> TypoStats:
    """Estrae metriche tipografiche strutturali dal Markdown."""
    stats = TypoStats()
    stats.characters = len(md_text)
    
    # Header counts
    stats.h1 = len(re.findall(r"^#\s", md_text, re.MULTILINE))
    stats.h2 = len(re.findall(r"^##\s", md_text, re.MULTILINE))
    stats.h3 = len(re.findall(r"^###\s", md_text, re.MULTILINE))
    
    # Bold and Italic
    stats.bold = len(re.findall(r"\*\*[^*]+\*\*", md_text))
    # Italic: *text* or _text_ but not inside links or strong
    stats.italic = len(re.findall(r"(?<!\*)\*(?!\*)[^*]+\*(?!\*)", md_text))
    
    # Tables: rough count of markdown table separators
    stats.tables = len(re.findall(r"^\|-", md_text, re.MULTILINE))
    
    # Images
    stats.images = len(re.findall(r"!\[.*?\]\(.*?\)", md_text))
    stats.images += len(re.findall(r"\*Figura:.*?\*", md_text))
    
    return stats

def analyze_pdf(pdf_path: Path) -> TypoStats:
    """Estrae metriche tipografiche approssimate dal PDF tramite PyMuPDF."""
    stats = TypoStats()
    try:
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                text = page.get_text()
                stats.characters += len(text)
                
                # Check for images
                images = page.get_images()
                stats.images += len(images)
                
                # Rough typographic check from textdict
                dict_page = page.get_text("dict")
                for block in dict_page.get("blocks", []):
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                text_span = span.get("text", "").strip()
                                if not text_span: continue
                                fontflags = span.get("flags", 0)
                                size = span.get("size", 10)
                                is_bold = (fontflags & 2 ** 4) != 0 or "bold" in span.get("font", "").lower()
                                is_italic = (fontflags & 2 ** 1) != 0 or "italic" in span.get("font", "").lower()
                                
                                if is_bold:
                                    stats.bold += 1
                                if is_italic:
                                    stats.italic += 1
                                    
                                # Heuristic for headers: bigger sizes and bold
                                if size > 16 and is_bold:
                                    stats.h1 += 1
                                elif size > 14 and is_bold:
                                    stats.h2 += 1
                                elif size > 12 and is_bold:
                                    stats.h3 += 1
    except Exception:
        pass
        
    return stats

def audit_quality(pdf_path: Path, md_path: Path) -> dict:
    """Effettua un audit comparativo."""
    if not pdf_path.exists() or not md_path.exists():
        return {"error": "File sorgente o Markdown non trovato."}
    
    md_text = md_path.read_text(encoding="utf-8")
    md_stats = analyze_markdown(md_text)
    pdf_stats = analyze_pdf(pdf_path)
    
    # Calculate a rough score (0-100) based on length fidelity
    char_ratio = min(md_stats.characters, pdf_stats.characters) / max(max(md_stats.characters, pdf_stats.characters), 1)
    
    return {
        "md_stats": md_stats.__dict__,
        "pdf_stats": pdf_stats.__dict__,
        "layout_score": int(char_ratio * 100),
        "typography_score": min(int((md_stats.bold + md_stats.h1 + md_stats.h2) / max(pdf_stats.bold + pdf_stats.h1 + pdf_stats.h2, 1) * 100), 100),
        "message": "Audit completato"
    }
