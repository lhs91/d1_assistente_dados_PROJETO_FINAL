# -*- coding: utf-8 -*-
"""
auditor_dados.py — Agente: Auditor de Dados (autocorreção nível 2).

A pergunta do cargo: "o resultado responde DE FATO a pergunta?" — SQL válido
que responde a pergunta errada é o erro mais perigoso, porque falha em
silêncio. O checklist de 5 pontos transforma as armadilhas conhecidas em
verificação de rotina, sem citar nenhum nome de coluna deste banco.
"""
from app.config import criar_llm
from app.estado import AnaliseDaPergunta, ParecerDoAuditor


def _prompt_do_auditor(
    pergunta: str,
    analise: AnaliseDaPergunta,
    resultados: list,
    dossie: str,
    dialogo: list | None = None,
) -> str:
    # V3.6.1 — REFRAMING PARA O AUDITOR (correção do loop do 'lucro'): se
    # houve esclarecimento, a pergunta a auditar é a ESCOLHA DO USUÁRIO, não
    # a pergunta original. Sem isto, o Auditor reprovava eternamente um
    # resultado correto por compará-lo com a pergunta original já superada.
    bloco_dialogo = ""
    pergunta_a_auditar = pergunta
    if dialogo:
        pares = "\n".join(
            f"[Analista perguntou]: {p['pergunta_do_analista']}\n"
            f"[Usuário respondeu]: {p['resposta_do_usuario']}"
            for p in dialogo
        )
        pergunta_a_auditar = dialogo[-1]["resposta_do_usuario"]
        bloco_dialogo = (
            "\nDIÁLOGO DE ESCLARECIMENTO JÁ OCORRIDO (a resposta do usuário "
            "tem AUTORIDADE MÁXIMA e DEFINE o que deve ser auditado):\n"
            + pares + "\n"
            "AUDITE CONTRA A ESCOLHA DO USUÁRIO, NÃO A PERGUNTA ORIGINAL: o "
            "usuário JÁ foi avisado de que a pergunta original não era "
            "respondível e ESCOLHEU a alternativa acima. Avalie se o "
            "resultado responde a ESSA ESCOLHA. É PROIBIDO reprovar alegando "
            "que o resultado não atende à pergunta original — ela foi "
            "conscientemente substituída pela escolha do usuário.\n"
        )
    blocos = []
    for indice, resultado in enumerate(resultados):
        truncado = ""
        blocos.append(
            f"Passo {indice} — {resultado['objetivo']}{truncado}\n"
            f"SQL executado: {resultado['sql']}\n"
            f"Colunas: {resultado['colunas']}\n"
            f"Linhas ({resultado['n_linhas']} no total; exibindo as "
            f"{min(20, resultado['n_linhas'])} primeiras por espaço — recorte "
            f"de EXIBIÇÃO, não truncamento de dados): {resultado['linhas'][:20]}"
        )
    premissas = "\n".join(f"- {p}" for p in analise.premissas) or "- (nenhuma)"
    return (
        "Você é um Auditor de Dados. Avalie se os resultados abaixo respondem "
        "DE FATO a pergunta do diretor. SQL válido com resposta errada é o "
        "pior erro possível — seja rigoroso.\n\n"
        "CHECKLIST OBRIGATÓRIO (verifique TODOS os pontos):\n"
        "1. FONTE TRANSACIONAL: se o dossiê tem ALERTAS DE QUALIDADE sobre "
        "colunas divergentes, a consulta usou a fonte transacional recomendada "
        "(e NÃO a coluna denormalizada)?\n"
        "2. ÂNCORA TEMPORAL: janelas relativas e meses sem ano foram ancorados "
        "na âncora temporal do dossiê (não na data de hoje)?\n"
        "3. DOMÍNIOS CATEGÓRICOS: os filtros usam valores que EXISTEM na "
        "tabela consultada (mesma coluna pode ter domínios diferentes em "
        "tabelas diferentes)?\n"
        "4. RESULTADO VAZIO: se vazio, é legítimo (não há mesmo dados) ou é "
        "sintoma de filtro/grafia errada? Confira contra o dicionário.\n"
        "5. RECORTE DE EXIBIÇÃO: as linhas mostradas neste prompt são apenas "
        "um RECORTE para leitura — o resultado COMPLETO já está com o "
        "sistema e será usado integralmente no gráfico e na resposta. "
        "n_linhas informa o total real. NÃO devolva pedindo 'mais linhas' "
        "ou 'todas as linhas': elas JÁ estão completas.\n"
        "6. EMPATES NO CORTE: em rankings top-N, verifique se há valores "
        "empatados na última posição que ficaram FORA do corte — se houver, "
        "a resposta deve revelar o empate, não escondê-lo.\n\n"
        "Se reprovar: preencha problema, instrucao_de_correcao (clara e "
        "acionável) e indice_passo_a_refazer (0-based).\n\n"
        f"{dossie}\n"
        f"{bloco_dialogo}\n"
        f"PERGUNTA A AUDITAR (efetiva): {pergunta_a_auditar}\n\n"
        f"PREMISSAS DECLARADAS:\n{premissas}\n\n"
        f"RESULTADOS A AUDITAR:\n" + "\n\n".join(blocos)
    )


def auditar(
    pergunta: str,
    analise: AnaliseDaPergunta,
    resultados: list,
    dossie: str,
    dialogo: list | None = None,
    llm=None,
) -> ParecerDoAuditor:
    """Audita semanticamente o conjunto de resultados (nível 2).
    `dialogo`: pares pergunta↔resposta do esclarecimento — quando presente,
    a auditoria é feita contra a ESCOLHA do usuário, não a pergunta original."""
    if llm is None:
        llm = criar_llm()
    estruturado = llm.with_structured_output(ParecerDoAuditor)
    return estruturado.invoke(
        _prompt_do_auditor(pergunta, analise, resultados, dossie,
                           dialogo or [])
    )
