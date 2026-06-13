# -*- coding: utf-8 -*-
"""
diagnostico_studio.py — Descobre por que o LangGraph Studio não carrega o grafo.

Rode da RAIZ do projeto, com o .venv ativo:
    python diagnostico_studio.py

Ele reproduz, passo a passo, o que o 'langgraph dev' faz ao ler o
langgraph.json — e imprime o erro EXATO se algo falhar (a mesma causa que
aparece no alerta do Studio).
"""
import json
import sys
import traceback
from pathlib import Path

print("=" * 70)
print("DIAGNÓSTICO DO LANGGRAPH STUDIO")
print("=" * 70)
print(f"Python: {sys.version.split()[0]}")
print(f"Diretório atual: {Path.cwd()}")

# 1. langgraph.json existe e é válido?
print("\n[1] langgraph.json")
caminho_json = Path("langgraph.json")
if not caminho_json.exists():
    print("  ERRO: langgraph.json NÃO está na pasta atual.")
    print("  → Você não está na raiz do projeto. Faça 'cd' até a pasta que o contém.")
    raise SystemExit(1)
try:
    cfg = json.loads(caminho_json.read_text(encoding="utf-8"))
    print(f"  OK: {cfg.get('graphs')}")
except Exception as e:
    print(f"  ERRO de JSON: {e}")
    raise SystemExit(1)

# 2. O .env existe e tem a chave?
print("\n[2] .env / GOOGLE_API_KEY")
env = Path(cfg.get("env", ".env"))
if not env.exists():
    print(f"  AVISO: {env} não encontrado — o Studio não terá a chave do Gemini.")
else:
    conteudo = env.read_text(encoding="utf-8", errors="ignore")
    tem_chave = "GOOGLE_API_KEY" in conteudo
    print(f"  {env} existe; contém GOOGLE_API_KEY: {tem_chave}")
    if not tem_chave:
        print("  → Sem a chave, o grafo até desenha, mas falha ao EXECUTAR.")

# 3. O alvo do grafo importa? (a causa nº 1 do alerta)
print("\n[3] Importar o grafo declarado no langgraph.json")
alvo = cfg["graphs"]["assistente"]
caminho_mod, nome_var = alvo.split(":")
print(f"  alvo: arquivo '{caminho_mod}', variável '{nome_var}'")
try:
    import importlib.util
    arquivo = Path(caminho_mod.lstrip("./"))
    if not arquivo.exists():
        print(f"  ERRO: o arquivo {arquivo} não existe a partir daqui.")
        raise SystemExit(1)
    spec = importlib.util.spec_from_file_location("studio_alvo", arquivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    grafo = getattr(mod, nome_var)
    nos = sorted(n for n in grafo.get_graph().nodes if not n.startswith("__"))
    print(f"  OK — grafo '{type(grafo).__name__}' com {len(nos)} nós:")
    print(f"  {nos}")
    print("\n" + "=" * 70)
    print("RESULTADO: o grafo carrega SEM erro. Se o Studio ainda mostra o")
    print("exemplo de 4 nós, o problema é a CLI (versão/cache do servidor),")
    print("não o seu código. Veja as instruções abaixo.")
    print("=" * 70)
except SystemExit:
    raise
except Exception:
    print("\n  ★★★ ESTA É A CAUSA DO ALERTA NO STUDIO ★★★")
    print("  O grafo FALHOU ao importar:\n")
    traceback.print_exc()
    print("\n  → Copie o erro acima: é exatamente o que o Studio está engolindo.")
