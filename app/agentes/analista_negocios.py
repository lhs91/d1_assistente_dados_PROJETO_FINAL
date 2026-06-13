# -*- coding: utf-8 -*-
"""
analista_negocios.py — Agente: Analista de Negócios (cargo com 2 funções).

1ª função (entrada): interpreta a pergunta do diretor, decompõe em passos,
declara premissas e decide se há ambiguidade MATERIAL (que mudaria a
resposta) — nesse caso formula a pergunta de esclarecimento (interrupt).

2ª função (saída): redige a resposta de NEGÓCIO a partir dos resultados —
é o papel business-facing nas duas pontas do fluxo (decisão da SPEC).
"""
from app.analise_outliers import detectar_outliers, texto_dos_outliers
from app.config import criar_llm
from app.estado import AnaliseDaPergunta, RespostaDeNegocio


def _prompt_de_analise(pergunta: str, dossie: str, esclarecimentos: list,
                       dialogo: list | None = None) -> str:
    # V3.6 — REFRAMING DETERMINÍSTICO (correção do loop do interrupt): se já
    # houve diálogo, o prompt apresenta os PARES completos (pergunta do
    # Analista ↔ resposta do usuário) e promove a ÚLTIMA resposta a PERGUNTA
    # EFETIVA — a original vira contexto. A causa do loop era o diálogo
    # unilateral: o LLM via respostas soltas e seguia preso à pergunta
    # original (irrespondível), reoferecendo as mesmas opções para sempre.
    bloco_dialogo = ""
    pergunta_apresentada = f"PERGUNTA DO DIRETOR: {pergunta}"
    if dialogo:
        pares = "\n".join(
            f"[Você perguntou]: {p['pergunta_do_analista']}\n"
            f"[Usuário respondeu]: {p['resposta_do_usuario']}"
            for p in dialogo
        )
        ultima = dialogo[-1]["resposta_do_usuario"]
        bloco_dialogo = (
            "\nDIÁLOGO DE ESCLARECIMENTO (na ordem; a resposta do usuário "
            "tem AUTORIDADE MÁXIMA):\n" + pares + "\n"
            "PROIBIDO REPERGUNTAR: havendo pelo menos uma resposta no "
            "diálogo acima, é PROIBIDO marcar precisa_esclarecimento=true "
            "para reformular a MESMA dúvida ou reoferecer as MESMAS opções "
            "— PRODUZA O PLANO para a PERGUNTA EFETIVA abaixo. Só pergunte "
            "de novo se a resposta introduzir uma ambiguidade NOVA e "
            "diferente.\n"
        )
        pergunta_apresentada = (
            f"PERGUNTA EFETIVA DO DIRETOR (a escolha dele no diálogo acima "
            f"— monte o plano para ELA): {ultima}\n"
            f"(Contexto, já superado pelo diálogo: a pergunta original era "
            f"'{pergunta}'.)"
        )
    bloco_esclarecimentos = ""
    if esclarecimentos:
        itens = "\n".join(f"- {e}" for e in esclarecimentos)
        bloco_esclarecimentos = (
            "\nESCLARECIMENTOS JÁ DADOS PELO USUÁRIO — AUTORIDADE MÁXIMA:\n"
            f"{itens}\n"
            "Se uma resposta acima REDEFINE, substitui ou aceita uma alternativa "
            "à pergunta original (ex.: 'quero a receita total de 2025'), trate-a "
            "como a NOVA PERGUNTA EFETIVA e monte o plano para ELA — a pergunta "
            "original fica superada. É PROIBIDO repetir uma pergunta de "
            "esclarecimento já feita ou perguntar sobre algo que o usuário "
            "acabou de responder.\n"
        )
    return (
        "Você é um Analista de Negócios. Sua tarefa: decompor a pergunta do "
        "diretor em um plano de 1 a N consultas SQL (passos), declarar as "
        "premissas assumidas e decidir se precisa de esclarecimento.\n\n"
        "REGRAS DE AMBIGUIDADE (siga à risca):\n"
        "00. TIPO DE GRÁFICO NÃO É DA SUA ALÇADA — NUNCA RECUSE POR CAUSA "
        "DELE: você cuida dos DADOS, não da visualização. O tipo, o nome "
        "ou a técnica de gráfico (dispersão, regressão polinomial, "
        "tendência, heatmap, 3D, etc.) é decidido e construído por OUTRO "
        "agente (o Designer) mais adiante. Se a pergunta pede um gráfico e "
        "as colunas para os eixos/medidas EXISTEM no dossiê, então HÁ "
        "PLANO: monte os passos para BUSCAR esses dados (ex.: data, valor "
        "e canal de cada compra) e ignore a parte estatística/visual do "
        "pedido — ela será resolvida ou adaptada pelo Designer. É PROIBIDO "
        "marcar pedido_fora_de_escopo ou pedir esclarecimento alegando que "
        "um cálculo estatístico (regressão, suavização) ou um tipo de "
        "gráfico está 'além da capacidade de consulta': sua tarefa é só "
        "entregar as colunas certas.\n"
        "0a. DADO INEXISTENTE → ESCLARECIMENTO ANCORADO NO SCHEMA, NUNCA "
        "RECUSA DIRETA: se a pergunta exige um dado que NÃO existe no dossiê "
        "(ex.: 'quantidade de itens' quando a tabela só tem o valor total), "
        "NÃO recuse e NÃO invente o dado — marque precisa_esclarecimento=true "
        "e faça UMA pergunta de esclarecimento que: (1) diga explicitamente "
        "que o dado não existe, citando as colunas REAIS da tabela; e "
        "(2) ofereça 2 a 3 alternativas CONCRETAS e úteis construídas "
        "SOMENTE com colunas que existem no dossiê (ex.: valor × canal, "
        "valor × data da compra). O usuário escolhe e a análise segue. "
        "Reserve pedido_fora_de_escopo=true APENAS para pedidos de ESCRITA "
        "(regra 0) ou quando NENHUMA coluna do banco permitir qualquer "
        "análise relacionada ao tema.\n"
        "0b. PERGUNTA DE ESCLARECIMENTO ANCORADA NO SCHEMA: toda alternativa "
        "oferecida na pergunta de esclarecimento DEVE existir no dossiê "
        "(tabela + coluna + valores do dicionário). PROIBIDO sugerir dados "
        "inexistentes (ex.: 'categoria do produto' se não há tal coluna) — "
        "isso prende o usuário num ciclo de perguntas irrespondíveis.\n"
        "0. PEDIDO DE ESCRITA NÃO É AMBIGUIDADE: se a pergunta pede ALTERAR "
        "dados (atualizar/inserir/apagar/criar — UPDATE/INSERT/DELETE/ALTER), "
        "NÃO peça esclarecimento e NÃO ofereça alternativas: marque "
        "pedido_fora_de_escopo=true E pedido_de_escrita=true, com motivo "
        "curto. O sistema é SOMENTE LEITURA e responderá com a recusa "
        "honesta. (pedido_de_escrita fica FALSE em qualquer outra recusa — "
        "ele distingue a mensagem de segurança das demais.)\n"
        "1. ANTES de declarar ambiguidade, verifique a ÂNCORA TEMPORAL e o "
        "dicionário de valores do dossiê. Ex.: um mês sem ano que só existe em "
        "UM ano na base NÃO é ambíguo — é premissa verificada (declare-a).\n"
        "2. Janelas relativas ('último ano') ancoram na âncora temporal do "
        "dossiê — isso é premissa, não ambiguidade.\n"
        "3. PERÍODO NÃO ESPECIFICADO não é ambiguidade material: assuma todo o "
        "histórico disponível e DECLARE a premissa (não pergunte).\n"
        "4. Peça esclarecimento APENAS se a dúvida mudaria materialmente a "
        "resposta (ex.: a pergunta não diz qual métrica ou qual assunto).\n"
        "5. Cada passo do plano tem UM objetivo claro e verificável. Prefira o "
        "menor número de passos que responda bem.\n"
        f"{bloco_esclarecimentos}"
        f"{bloco_dialogo}\n"
        f"{dossie}\n\n"
        f"{pergunta_apresentada}"
    )


def analisar(
    pergunta: str,
    dossie: str,
    esclarecimentos: list | None = None,
    dialogo: list | None = None,
    llm=None,
) -> AnaliseDaPergunta:
    """Decompõe a pergunta em plano + premissas; sinaliza ambiguidade material."""
    if llm is None:
        llm = criar_llm()
    estruturado = llm.with_structured_output(AnaliseDaPergunta)
    return estruturado.invoke(
        _prompt_de_analise(pergunta, dossie, esclarecimentos or [],
                           dialogo or [])
    )


def _prompt_de_redacao(
    pergunta: str, analise: AnaliseDaPergunta, resultados: list, dossie: str
) -> str:
    blocos = []
    for indice, resultado in enumerate(resultados, start=1):
        truncado = " [DADOS TRUNCADOS — amostra parcial]" if resultado["truncado"] else ""
        blocos.append(
            f"Passo {indice} — {resultado['objetivo']}{truncado}\n"
            f"SQL: {resultado['sql']}\n"
            f"Colunas: {resultado['colunas']}\n"
            f"Linhas ({resultado['n_linhas']}): {resultado['linhas']}"
        )
    premissas = "\n".join(f"- {p}" for p in analise.premissas) or "- (nenhuma)"
    # Outliers (z>2) do ÚLTIMO resultado — base determinística para o Diretor
    # destacar conclusões sobre valores fora do padrão.
    bloco_outliers = ""
    if resultados:
        ultimo = resultados[-1]
        achados = detectar_outliers(ultimo["colunas"], ultimo["linhas"])
        bloco_outliers = texto_dos_outliers(achados)
    return (
        "Você é um Analista de Negócios redigindo a resposta final para um "
        "diretor (linguagem clara, sem jargão técnico).\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Use APENAS os números e fatos dos RESULTADOS abaixo. É PROIBIDO "
        "inventar, extrapolar ou 'completar' valores.\n"
        "2. Se os resultados estiverem vazios, diga honestamente que não há "
        "dados para responder — não invente.\n"
        "3. Liste em premissas_destacadas TODAS as premissas assumidas.\n"
        "4. Dados truncados: deixe claro que a leitura é sobre uma amostra.\n"
        "5. CONCLUSÃO EXECUTIVA (campo impactos_e_acoes): escreva EXATAMENTE "
        "2 parágrafos, fundamentados NOS DADOS desta resposta. O parágrafo 1 "
        "COMEÇA com o prefixo 'IMPACTOS PARA O NEGÓCIO:' (em maiúsculas) "
        "seguido do texto em CAPITALIZAÇÃO NORMAL (não use CAIXA ALTA no "
        "corpo) sobre os impactos que esses números revelam (riscos, "
        "oportunidades, o que está em jogo). O parágrafo 2 COMEÇA com o "
        "prefixo 'AÇÕES:' (em maiúsculas) seguido do texto em capitalização "
        "normal sobre as ações concretas para amenizar consequências "
        "negativas e impulsionar os resultados. Em CADA parágrafo, destaque "
        "as frases mais importantes envolvendo-as em **negrito markdown** "
        "(ex.: **risco de dependência**), mesmo em minúsculas. Linguagem de "
        "diretor, acionável, sem jargão. Se os resultados forem "
        "insuficientes, diga-o com honestidade (não invente impacto sem "
        "dado).\n\n"
        "6. VALORES FORA DO PADRÃO: se o bloco abaixo apontar valores com "
        "|z|>2 (outliers detectados deterministicamente), comente-os na "
        "conclusão executiva — são o que mais merece a atenção do diretor "
        "(uma concentração, um desvio, uma exceção). Não invente outliers "
        "além dos listados.\n\n"
        f"PERGUNTA ORIGINAL: {pergunta}\n\n"
        f"PREMISSAS DA ANÁLISE:\n{premissas}\n"
        f"{bloco_outliers}\n\n"
        f"RESULTADOS:\n" + "\n\n".join(blocos)
    )


def redigir_resposta(
    pergunta: str,
    analise: AnaliseDaPergunta,
    resultados: list,
    dossie: str,
    llm=None,
) -> RespostaDeNegocio:
    """Transforma os resultados em resposta de negócio, premissas em destaque."""
    if llm is None:
        llm = criar_llm()
    estruturado = llm.with_structured_output(RespostaDeNegocio)
    return estruturado.invoke(
        _prompt_de_redacao(pergunta, analise, resultados, dossie)
    )
