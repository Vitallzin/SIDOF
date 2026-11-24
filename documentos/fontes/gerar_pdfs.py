"""Gera os PDFs da documentação a partir dos HTMLs desta pasta, usando o Microsoft Edge.

Rodar da pasta do projeto: .venv\\Scripts\\python documentos\\fontes\\gerar_pdfs.py
"""

import subprocess
from pathlib import Path

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
FONTES = Path(__file__).resolve().parent
DESTINO = FONTES.parent

DOCUMENTOS = {
    "documentacao_tecnica.html": "Documentacao_Tecnica_Diagnostico_Financeiro.pdf",
    "explicacao_simples.html": "Como_Funciona_Explicacao_Simples.pdf",
}


def gerar(html, pdf):
    subprocess.run(
        [
            str(EDGE), "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={DESTINO / pdf}", (FONTES / html).as_uri(),
        ],
        check=True, capture_output=True, timeout=120,
    )
    print(f"Gerado: {DESTINO / pdf}")


if __name__ == "__main__":
    for html, pdf in DOCUMENTOS.items():
        if (FONTES / html).exists():
            gerar(html, pdf)
