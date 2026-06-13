import statistics


def detectar_outliers(colunas: list, linhas: list, z_limite: float = 2.0) -> list:
    """Detector DETERMINÍSTICO de outliers por z-score (|z| > z_limite, padrão 2).

    Para cada coluna NUMÉRICA, calcula média e desvio-padrão e sinaliza os
    valores cujo afastamento da média excede `z_limite` desvios. Genérico:
    funciona em qualquer resultado tabular, sem conhecer o domínio. Devolve
    uma lista de dicts {coluna, rotulo, valor, z} — vazia se nada se destaca
    ou se não há amostra suficiente (mín. 3 pontos por coluna).
    """
    achados = []
    if not linhas or len(linhas) < 3:
        return achados
    # a 1ª coluna costuma ser o rótulo (categoria); as numéricas, as métricas.
    for col in range(len(colunas)):
        valores = []
        for linha in linhas:
            try:
                valores.append(float(linha[col]))
            except (TypeError, ValueError, IndexError):
                valores = []
                break                         # coluna não-numérica: pula
        if len(valores) < 3:
            continue
        media = statistics.fmean(valores)
        desvio = statistics.pstdev(valores)
        if desvio == 0:
            continue                          # todos iguais: sem outlier
        for linha, valor in zip(linhas, valores):
            z = (valor - media) / desvio
            if abs(z) > z_limite:
                rotulo = str(linha[0]) if linha else "?"
                achados.append({
                    "coluna": colunas[col], "rotulo": rotulo,
                    "valor": valor, "z": round(z, 2),
                })
    return achados


def texto_dos_outliers(achados: list) -> str:
    """Renderiza os outliers como bloco curto para o prompt do Diretor."""
    if not achados:
        return ""
    linhas = [
        f"- '{a['rotulo']}' em {a['coluna']}: {a['valor']:g} "
        f"(z={a['z']:+.2f}, {'acima' if a['z'] > 0 else 'abaixo'} da média)"
        for a in achados
    ]
    return ("\nVALORES FORA DO PADRÃO (|z|>2, detectados deterministicamente — "
            "destaque-os na conclusão se forem relevantes):\n" + "\n".join(linhas))
