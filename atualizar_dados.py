#!/usr/bin/env python3
"""Gera dados/UF.json (despesas por candidato) a partir do CSV de prestação de contas do TSE.

Uso:
  python3 atualizar_dados.py               # baixa o ZIP do TSE e gera a pasta dados/
  python3 atualizar_dados.py arquivo.zip   # usa um ZIP já baixado
Variáveis de ambiente:
  TSE_DESPESAS_ZIP  URL do ZIP (copie o link do recurso "Prestação de contas de candidatos"
                    em https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais-2026)
  SAIDA             pasta de saída (padrão: dados)
"""
import csv, io, json, os, sys, tempfile, urllib.request, zipfile
from collections import defaultdict
from datetime import datetime, timezone

URL = (os.environ.get("TSE_DESPESAS_ZIP") or
    "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2026.zip")
SAIDA = os.environ.get("SAIDA", "dados")
CARGOS = {"PRESIDENTE": "pres", "SENADOR": "sen", "DEPUTADO FEDERAL": "fed",
          "DEPUTADO ESTADUAL": "est", "DEPUTADO DISTRITAL": "est"}
OBRIG = ["SG_UF", "DS_CARGO", "NR_CANDIDATO", "NM_CANDIDATO", "SG_PARTIDO", "DS_ORIGEM_DESPESA"]


def valor(txt):
    t = (txt or "").strip().replace('"', "")
    if not t:
        return 0.0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def baixa():
    if len(sys.argv) > 1:
        return sys.argv[1]
    destino = os.path.join(tempfile.gettempdir(), "tse_despesas_2026.zip")
    req = urllib.request.Request(URL, headers={"User-Agent": "colinha-eleitoral/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return destino


def main():
    cand = defaultdict(lambda: {"nome": "", "partido": "", "g": defaultdict(float)})
    with zipfile.ZipFile(baixa()) as z:
        nomes = [n for n in z.namelist()
                 if "despesas_contratadas_candidatos" in n.lower() and n.lower().endswith(".csv")]
        nomes = [n for n in nomes if "brasil" in n.lower()] or nomes  # prefere o arquivo nacional
        if not nomes:
            sys.exit("Não achei 'despesas_contratadas_candidatos*.csv' no ZIP. Arquivos: "
                     + ", ".join(z.namelist()[:20]))
        for nome in nomes:
            with z.open(nome) as bruto:
                leitor = csv.DictReader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""),
                                        delimiter=";", quotechar='"')
                cols = leitor.fieldnames or []
                col_valor = next((c for c in cols if c.startswith("VR_DESPESA")), None)
                falta = [c for c in OBRIG if c not in cols]
                if falta or not col_valor:
                    sys.exit(f"Colunas inesperadas em {nome}. Faltam: {falta or 'VR_DESPESA*'}. "
                             f"Colunas do arquivo: {cols}. Ajuste OBRIG/CARGOS no script.")
                for l in leitor:
                    cargo = CARGOS.get(l["DS_CARGO"].strip().upper())
                    if not cargo:
                        continue
                    c = cand[(l["SG_UF"].strip(), cargo, l["NR_CANDIDATO"].strip())]
                    c["nome"] = l["NM_CANDIDATO"].strip().title()
                    c["partido"] = l["SG_PARTIDO"].strip()
                    c["g"][l["DS_ORIGEM_DESPESA"].strip() or "Não informado"] += valor(l[col_valor])

    por_uf = defaultdict(lambda: defaultdict(dict))
    for (uf, cargo, num), c in cand.items():
        por_uf[uf][cargo][num] = [c["nome"], c["partido"], {k: round(v, 2) for k, v in c["g"].items()}]

    os.makedirs(SAIDA, exist_ok=True)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for uf, dados in por_uf.items():
        saida = dict(dados)
        saida["_atualizado"] = agora
        tmp = os.path.join(SAIDA, f".{uf}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, os.path.join(SAIDA, f"{uf}.json"))  # troca atômica
    print(f"OK: {len(cand)} candidatos em {len(por_uf)} arquivos ({agora})")


if __name__ == "__main__":
    main()
