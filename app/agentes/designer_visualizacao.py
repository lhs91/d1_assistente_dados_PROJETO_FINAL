# -*- coding: utf-8 -*-
"""
designer_visualizacao.py — Agente: Designer de Visualização (4º cargo).

Autora o option ECharts COMPLETO — não escolhe entre 4 opções: escreve o
gráfico (tipo, eixos, séries, título, tooltip) que melhor serve a pergunta.
A liberdade tem uma cerca dura: JSON PURO, validado pelo Guardrail de
Visualização antes de qualquer renderização. No retry, o motivo da reprova
entra no prompt.
"""
from app.config import criar_llm
from app.estado import PropostaDoDesigner


def _prompt_do_designer(
    pergunta: str,
    resultado: dict,
    justificativa_da_resposta: str,
    motivo_da_reprova: str | None,
) -> str:
    bloco_reprova = ""
    if motivo_da_reprova:
        bloco_reprova = (
            "\nATENÇÃO — sua proposta anterior foi REPROVADA pelo guardrail. "
            f"Corrija exatamente isto:\nMOTIVO: {motivo_da_reprova}\n"
        )
    return (
        "Você é um Designer de Visualização de dados. Crie UM gráfico ECharts "
        "que melhor comunique o resultado abaixo a um diretor.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. option_json deve ser JSON PURO e completo (title, xAxis/yAxis "
        "quando aplicável, series com os dados EMBUTIDOS). É PROIBIDO "
        "qualquer código executável: function, arrow (=>), eval, new "
        "Function, JsCode, <script>, javascript:. 'formatter' só como "
        "template string (ex.: '{b}: {c}').\n"
        "2. Apenas UM gráfico — jamais composições lado a lado.\n"
        "3. Use SOMENTE os dados do RESULTADO abaixo — não invente valores.\n"
        "4. Se a pergunta do usuário pediu um formato explícito (ex.: 'me "
        "mostre em pizza'), OBEDEÇA ao formato pedido.\n"
        "5. Título e nomes de eixos em português, claros para leigos.\n"
        "6. Escolha o tipo MAIS EXPRESSIVO e visualmente SINGULAR para a forma "
        "dos dados — VARIE entre: rosca/donut, radar, dispersão, heatmap, "
        "barras horizontais, área empilhada, funil, gauge, treemap, "
        "sunburst, linha multi-série, barras com gradiente... Fuja do "
        "óbvio quando outro tipo comunicar melhor. PROIBIDO map/geo (não "
        "suportados pelo renderizador).\n"
        "6z. PEDIDO EXPLÍCITO DE TABELA: se a pergunta pede o resultado EM "
        "TABELA (ex.: 'mostre em tabela', 'formato de tabela'), "
        "responda com tipo_grafico='tabela' e option_json='{}' (vazio) "
        "— a interface renderiza a tabela nativa com os dados. NÃO force "
        "um gráfico nesse caso.\n"
        "6c. GALERIA PREFERENCIAL: quando a pergunta fizer SENTIDO MATEMÁTICO "
        "para um destes, PRIORIZE-O (todos em JSON puro do ECharts):\n"
        "- Variação ao longo do tempo (estilo 'Temperature Change in the "
        "Coming Week'): line multi-série com markPoint/markLine;\n"
        "- Punch card (intensidade em 2 dimensões discretas): scatter "
        "cartesiano com symbolSize proporcional (o bar3D clássico exige "
        "echarts-gl, INDISPONÍVEL no runtime — use esta forma);\n"
        "- Pie with padAngle: pie com padAngle e itemStyle.borderRadius;\n"
        "- Scatter Polynomial Regression (relação entre 2 métricas "
        "numéricas): scatter; se houver até ~60 pontos, adicione uma série "
        "line suave (smooth) com os pontos ordenados pelo eixo X como "
        "tendência aproximada (o plugin ecStat NÃO existe no runtime);\n"
        "- Heatmap on Cartesian: heatmap com visualMap;\n"
        "- Tree From Left to Right / Right to Left: tree com orient 'LR' "
        "ou 'RL' (hierarquias);\n"
        "- Treemap (partes de um todo com pesos); Sunburst (hierarquia "
        "radial); Sankey (fluxos origem→destino); Funnel (etapas que "
        "afunilam); Gauge (um indicador contra meta); PictorialBar "
        "(contagens com symbolRepeat);\n"
        "- Calendar Graph: coordenada calendar com heatmap/scatter "
        "(valores por dia);\n"
        "- Matrix: matriz densa como heatmap cartesiano;\n"
        "- Chord (relações entre categorias): series graph com layout "
        "'circular' (o chord clássico não existe no ECharts 5).\n"
        "Se NENHUM da galeria fizer sentido matemático para a pergunta, "
        "escolha LIVREMENTE qualquer tipo da biblioteca que comunique "
        "melhor. PROIBIDO: map/geo, bar3D/scatter3D (exigem extensões "
        "ausentes) e qualquer código executável.\n"
        "6b. CAPRICHE NA ESTÉTICA: paleta harmoniosa no option (campo 'color'), "
        "borderRadius nas barras, rótulos legíveis, tooltip configurado.\n"
        "7. ARREDONDE valores numéricos exibidos nos dados do option para 2 "
        "casas decimais — nunca embuta floats crus (ex.: 1.8823529...).\n"
        f"{bloco_reprova}\n"
        f"PERGUNTA DO USUÁRIO: {pergunta}\n"
        f"OBJETIVO RESPONDIDO: {justificativa_da_resposta}\n\n"
        "RESULTADO (dados a visualizar):\n"
        f"Colunas: {resultado['colunas']}\n"
        f"Linhas ({resultado['n_linhas']}): {resultado['linhas']}"
    )


def propor_visualizacao(
    pergunta: str,
    resultado: dict,
    justificativa_da_resposta: str,
    motivo_da_reprova: str | None = None,
    llm=None,
) -> PropostaDoDesigner:
    """Propõe o option ECharts (estruturado). Retry carrega o motivo."""
    if llm is None:
        llm = criar_llm()
    estruturado = llm.with_structured_output(PropostaDoDesigner)
    return estruturado.invoke(
        _prompt_do_designer(
            pergunta, resultado, justificativa_da_resposta, motivo_da_reprova
        )
    )
