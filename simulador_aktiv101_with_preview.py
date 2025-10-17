# simulador_aktiv101_with_preview.py
# Simulador de Desconto – Energia Solar (Grupo AKTI)
# Requisitos:
#   pip install streamlit pillow
# Execução:
#   streamlit run simulador_aktiv101_with_preview.py

from dataclasses import dataclass, field
from typing import Dict, List
from io import BytesIO

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ==============================
# CONFIG
# ==============================
st.set_page_config(page_title="Cálculo de Desconto - Grupo AKTI ", page_icon="⚡", layout="wide")
MESES_PTB = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho",
             "Agosto","Setembro","Outubro","Novembro","Dezembro"]


# ==============================
# MODELOS DE DADOS
# ==============================
@dataclass
class Bandeira:
    nome: str                 # "Amarela", "Vermelha", "Vermelha P1", "Vermelha P2"
    ativo: bool
    tarifa_rs_kwh: float = 0.0
    dias_leitura: int = 30
    dias_bandeira: int = 0
    mes_ref: str = "Junho"

@dataclass
class ATV:
    kwh: float = 0.0
    rs: float = 0.0

@dataclass
class Entradas:
    consumo_kwh: float
    valor_consumo_reais: float
    iluminacao_publica_reais: float
    atvs: List[ATV] = field(default_factory=list)
    bonus_itaipu_ativo: bool = False
    bonus_itaipu_rs: float = 0.0
    comp_indic_ativo: bool = False
    comp_indic_rs: float = 0.0
    amarela: Bandeira = None
    vermelha: Bandeira = None
    vermelha_p1: Bandeira = None
    vermelha_p2: Bandeira = None
    desconto_pct: float = 20.0                 # % editável

@dataclass
class Saidas:
    kwh_bandeiras: Dict[str, float]
    rs_bandeiras_bruto: Dict[str, float]
    rs_bandeiras_liquido: Dict[str, float]
    custo_sem_solar: float
    desconto_injetada_rs: float
    desconto_bandeiras_rs: float
    valor_boleto: float
    energia_injetada_kwh: float
    energia_injetada_rs: float

# ==============================
# FUNÇÕES AUX
# ==============================
def fmt_rs(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")
def fmt_kwh(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")
def fmt_pct(p: float, casas: int = 1) -> str:
    s = f"{p:.{casas}f}"        # ex.: 17.5 -> "17.5"
    s = s.replace(".", ",")     # usa vírgula no PT-BR
    return s
def font_bold(sz: int):
    for f in ["DejaVuSans-Bold.ttf","Arial Bold.ttf","arialbd.ttf","DejaVuSans.ttf"]:
        try: return ImageFont.truetype(f, sz)
        except: pass
    return ImageFont.load_default()

# ==============================
# CÁLCULO
# ==============================
def kwh_da_bandeira(consumo_kwh: float, b: Bandeira) -> float:
    if not b or not b.ativo or b.dias_leitura <= 0 or b.dias_bandeira <= 0:
        return 0.0
    return (consumo_kwh / float(b.dias_leitura)) * float(b.dias_bandeira)

def calcular(e: Entradas) -> Saidas:
    inj_kwh = sum(a.kwh for a in e.atvs)
    inj_rs  = sum(a.rs  for a in e.atvs)

    def kwh_b(b: Bandeira) -> float:
        if not b or not b.ativo or b.dias_leitura <= 0 or b.dias_bandeira <= 0:
            return 0.0
        return (e.consumo_kwh / float(b.dias_leitura)) * float(b.dias_bandeira)

    kwh_flags = {
        "Amarela":     kwh_b(e.amarela),
        "Vermelha":    kwh_b(e.vermelha),
        "Vermelha P1": kwh_b(e.vermelha_p1),
        "Vermelha P2": kwh_b(e.vermelha_p2),
    }

    rs_flags_bruto = {
        "Amarela":     kwh_flags["Amarela"]     * (e.amarela.tarifa_rs_kwh     if (e.amarela and e.amarela.ativo)     else 0.0),
        "Vermelha":    kwh_flags["Vermelha"]    * (e.vermelha.tarifa_rs_kwh    if (e.vermelha and e.vermelha.ativo)    else 0.0),
        "Vermelha P1": kwh_flags["Vermelha P1"] * (e.vermelha_p1.tarifa_rs_kwh if (e.vermelha_p1 and e.vermelha_p1.ativo) else 0.0),
        "Vermelha P2": kwh_flags["Vermelha P2"] * (e.vermelha_p2.tarifa_rs_kwh if (e.vermelha_p2 and e.vermelha_p2.ativo) else 0.0),
    }

    d = max(0.0, min(100.0, e.desconto_pct)) / 100.0

    # Calcula o desconto das bandeiras (para exibição/abate no boleto), mas NÃO altera o custo_sem (que é BRUTO)
    rs_flags_liquido = {k: v * (1.0 - d) for k, v in rs_flags_bruto.items()}
    desconto_bandeiras = sum(rs_flags_bruto.values()) - sum(rs_flags_liquido.values())

    desconto_injetada = inj_rs * d

    # Custo sem solar usa bandeiras BRUTAS (sem desconto)
    custo_sem = e.valor_consumo_reais + e.iluminacao_publica_reais + sum(rs_flags_bruto.values())
    if e.bonus_itaipu_ativo:
        custo_sem -= e.bonus_itaipu_rs
    if e.comp_indic_ativo:
        custo_sem -= e.comp_indic_rs

    # Boleto subtrai desconto da injetada + desconto das bandeiras
    valor_boleto = custo_sem - desconto_injetada - desconto_bandeiras

    return Saidas(
        kwh_bandeiras=kwh_flags,
        rs_bandeiras_bruto=rs_flags_bruto,
        rs_bandeiras_liquido=rs_flags_liquido,
        custo_sem_solar=custo_sem,
        desconto_injetada_rs=desconto_injetada,
        desconto_bandeiras_rs=desconto_bandeiras,
        valor_boleto=valor_boleto,
        energia_injetada_kwh=inj_kwh,
        energia_injetada_rs=inj_rs
    )

# ==============================
# PNG (layout clássico)
# ==============================
def exportar_png(titulo_mes: str, titulo_ano: int, e: Entradas, out: Saidas) -> bytes:
    VERDE=(23,145,23); VERDE_CLARO=(0,153,0); LARANJA=(237,114,44); PRETO=(0,0,0); BG_TOP=(250,228,214)
    f36=font_bold(36); f28=font_bold(28); f22=font_bold(22)
    STEP = 38
    W = 1280

    linhas = []
    consumo_label = f"Consumo  {fmt_kwh(e.consumo_kwh)}  kWh (em reais   "
    linhas.append({"label": consumo_label, "valor": e.valor_consumo_reais, "calc": None})
    linhas.append({"label": "Valor Iluminação Pública:", "valor": e.iluminacao_publica_reais, "calc": None})

    def add_flag(lbl, chave, b: Bandeira):
        if b and b.ativo:
            kwh_val = out.kwh_bandeiras.get(chave, 0.0)
            calc = f"(Calculado   {fmt_kwh(kwh_val)}   kWh   {b.dias_bandeira}   Dias de {b.mes_ref})" if (b.dias_bandeira>0 and kwh_val>0) else None
            # Mostrar no topo: BRUTO (sem desconto)
            valor_mostrar = out.rs_bandeiras_bruto.get(chave, 0.0)
            linhas.append({"label": lbl, "valor": valor_mostrar, "calc": calc})

    add_flag("Bandeira Amarela:", "Amarela", e.amarela)
    add_flag("Bandeira Vermelha:", "Vermelha", e.vermelha)
    add_flag("Bandeira Vermelha P1:", "Vermelha P1", e.vermelha_p1)
    add_flag("Bandeira Vermelha P2:", "Vermelha P2", e.vermelha_p2)

    if e.comp_indic_ativo and abs(e.comp_indic_rs)>1e-9:
        linhas.append({"label":"Compensação por indicador", "valor": -abs(e.comp_indic_rs), "calc": None})
    if e.bonus_itaipu_ativo and abs(e.bonus_itaipu_rs)>1e-9:
        linhas.append({"label":"Bônus Itaipu", "valor": -abs(e.bonus_itaipu_rs), "calc": None})

    header_h = 24 + STEP*len(linhas) + 60
    H = max(620, header_h + 360)

    img = Image.new("RGB", (W,H), (255,255,255))
    d = ImageDraw.Draw(img)
    d.rectangle([0,0,W,header_h], fill=BG_TOP)

    x_label=22
    x_amount = x_label + d.textlength(consumo_label, font=f28)
    y=16

    for idx,row in enumerate(linhas):
        lbl=row["label"]; valor=row["valor"]; calc=row["calc"]
        d.text((x_label,y), lbl, fill=VERDE, font=f28)
        d.text((x_amount,y), fmt_rs(valor), fill=VERDE, font=f28)
        if idx==0:
            close_x = x_amount + d.textlength(fmt_rs(valor), font=f28) + 6
            d.text((close_x,y), ")", fill=VERDE, font=f28)
        if calc:
            PADDING=22
            calc_x = x_amount + d.textlength(fmt_rs(valor), font=f28) + PADDING
            max_w = W - calc_x - 20
            if d.textlength(calc, font=f22) <= max_w:
                d.text((calc_x,y), calc, fill=PRETO, font=f22)
            else:
                words=calc.split(); line=""; yy=y
                for w in words:
                    test=(line+" "+w).strip()
                    if d.textlength(test, font=f22) <= max_w:
                        line=test
                    else:
                        d.text((calc_x,yy), line, fill=PRETO, font=f22)
                        yy += int(STEP*0.8)
                        line=w
                if line:
                    d.text((calc_x,yy), line, fill=PRETO, font=f22)
        y += STEP

    # Custo sem a solar (laranja) — soma BRUTA das bandeiras
    y_orange = y + 6
    d.text((x_label + 60, y_orange), "Custo sem a Solar:", fill=LARANJA, font=f36)
    d.text((x_amount,      y_orange), fmt_rs(out.custo_sem_solar), fill=LARANJA, font=f36)

    # Parte branca inferior
    y2 = header_h + 24
    d.text((20, y2), f"Compensação {titulo_mes}/{titulo_ano}", fill=LARANJA, font=f36)
    y2 += 48

    def linha_baixo(txt, valor_str):
        nonlocal y2
    # desloca um pouco o valor para a direita (melhor espaçamento)
        deslocamento_valor = 80
        d.text((20, y2), txt, fill=(0,0,0), font=f28)
        d.text((x_amount + deslocamento_valor, y2), valor_str, fill=(0,0,0), font=f28)
        y2 += STEP


    linha_baixo("Custo sem a solar:", fmt_rs(out.custo_sem_solar))
    linha_baixo("Energia injetada kWh (AKTI):", f"{fmt_kwh(out.energia_injetada_kwh)}   kWh")
    linha_baixo("Energia injetada R$ (AKTI):", fmt_rs(out.energia_injetada_rs))
    linha_baixo(f"Desconto {fmt_pct(e.desconto_pct)}% da energia injetada:", fmt_rs(out.desconto_injetada_rs))
    if out.desconto_bandeiras_rs > 0:
        linha_baixo(f"Desconto {fmt_pct(e.desconto_pct)}% nas bandeiras:", fmt_rs(out.desconto_bandeiras_rs))

    # alinha o valor final com os demais da parte branca
    deslocamento_valor = 80
    d.text((20, y2+16), "Valor a ser pago via boleto:", fill=(0,153,0), font=f36)
    d.text((x_amount + deslocamento_valor, y2+16), fmt_rs(out.valor_boleto), fill=(0,153,0), font=f36)



    buf=BytesIO(); img.save(buf,"PNG"); buf.seek(0); return buf.getvalue()

# ==============================
# UI
# ==============================
st.title("⚡ Cálculo de Desconto nas Faturas - Grupo AKTI")
st.caption("Desconto ajustável, bandeiras exibidas brutas no topo e descontos abatidos no boleto.")

# — DESCONTO —
st.subheader("Informe o Desconto")
desconto_pct = st.number_input("Percentual de desconto (%)", min_value=0.0, max_value=100.0,
                               step=0.5, value=20.0, format="%.1f")

st.divider()

col1, col2 = st.columns([1.1,1])

with col1:
    st.subheader("Entradas da fatura")
    consumo_kwh = st.number_input("Consumo do período (kWh):", min_value=0.0, step=1.0, value= 0.0, format="%.2f")
    valor_consumo = st.number_input("Valor do consumo (R$):", min_value=0.0, step=0.01, value= 0.0, format="%.2f")
    ip_reais = st.number_input("Valor da Iluminação Pública (R$):", min_value=0.0, step=0.01, value= 0.0, format="%.2f")

    st.markdown("#### Energia injetada (GDII / ATVs)")
    n_gdii = st.number_input("Quantas GDII (ATVs) existem?", min_value=0, max_value=12, step=1, value=1)
    atvs: List[ATV] = []
    if n_gdii>0:
        with st.expander("Preencher cada GDII / ATV", expanded=True):
            for i in range(int(n_gdii)):
                c1, c2 = st.columns(2)
                kwh = c1.number_input(f"GDII #{i+1} – kWh", min_value=0.0, step=0.01, value=0.0 if i==0 else 0.0, format="%.2f", key=f"gdii_{i}_kwh")
                rs  = c2.number_input(f"GDII #{i+1} – Valor (R$)", min_value=0.0, step=0.01, value=0.0 if i==0 else 0.0, format="%.2f", key=f"gdii_{i}_rs")
                atvs.append(ATV(kwh=kwh, rs=rs))

    st.divider()
    st.markdown("#### Opções (aparecem no PNG se marcadas)")
    comp_on = st.checkbox("Tem **Compensação por Indicador**?", value=True)
    comp_rs = st.number_input("Compensação por Indicador (R$)", min_value=0.0, step=0.01, value= 0.0, format="%.2f", disabled=not comp_on)
    bonus_on = st.checkbox("Tem **Bônus Itaipu**?", value=True)
    bonus_rs = st.number_input("Bônus Itaipu (R$)", min_value=0.0, step=0.01, value= 0.0, format="%.2f", disabled=not bonus_on)

    st.divider()
    st.markdown("#### Bandeiras (ativar somente as que existiram)")
    def ui_bandeira(label, default_mes, def_tarifa, def_dias_ban, keyprefix):
        ativo = st.checkbox(f"{label} ativa?", value=False, key=f"{keyprefix}_on")
        colb1, colb2, colb3, colb4 = st.columns([1.2, 1, 1, 1])
        mes = colb1.selectbox(f"Mês ({label})", MESES_PTB, index=MESES_PTB.index(default_mes), key=f"{keyprefix}_mes", disabled=not ativo)
        tarifa = colb2.number_input(f"Tarifa {label} (R$/kWh)", min_value=0.0, step=0.00001, value=def_tarifa, format="%.5f", key=f"{keyprefix}_tar")
        d_leit = colb3.number_input(f"Dias da leitura ({label})", min_value=1, step=1, value=30, key=f"{keyprefix}_dl", disabled=not ativo)
        d_ban = colb4.number_input(f"Dias com bandeira ({label})", min_value=0, step=1, value=def_dias_ban, key=f"{keyprefix}_db", disabled=not ativo)
        return Bandeira(label, ativo, float(tarifa), int(d_leit), int(d_ban), mes)

    # Padrões Tarifa Energisa 2025:
    amarela = ui_bandeira("Amarela", "Junho", 0.01885, 0, "am")
    vermelha = ui_bandeira("Vermelha", "Junho", 0.04463, 0, "ve")            
    vermelha_p1 = ui_bandeira("Vermelha P1", "Julho", 0.04463, 24, "vp1")
    vermelha_p2 = ui_bandeira("Vermelha P2", "Agosto", 0.07877, 6, "vp2")

with col2:
    st.subheader("PNG do período")
    c1, c2 = st.columns([2,1])
    mes_png = c1.selectbox("Mês do título do PNG", MESES_PTB, index=MESES_PTB.index("Agosto"))
    ano_png = c2.number_input("Ano", min_value=2000, max_value=2100, value=2025, step=1)

    e = Entradas(
        consumo_kwh=consumo_kwh,
        valor_consumo_reais=valor_consumo,
        iluminacao_publica_reais=ip_reais,
        atvs=atvs,
        bonus_itaipu_ativo=bonus_on, bonus_itaipu_rs=bonus_rs,
        comp_indic_ativo=comp_on, comp_indic_rs=comp_rs,
        amarela=amarela, vermelha=vermelha, vermelha_p1=vermelha_p1, vermelha_p2=vermelha_p2,
        desconto_pct=desconto_pct
    )
    out = calcular(e)

    st.markdown("##### Resumo")
    st.write("Custo sem a Solar:", fmt_rs(out.custo_sem_solar))
    st.write("Energia injetada (kWh):", fmt_kwh(out.energia_injetada_kwh))
    st.write("Energia injetada (R$):", fmt_rs(out.energia_injetada_rs))
    st.write(f"Desconto {fmt_pct(desconto_pct)}% (injetada R$):", fmt_rs(out.desconto_injetada_rs))
    if out.desconto_bandeiras_rs > 0:
        st.write(f"Desconto {fmt_pct(desconto_pct)}% nas bandeiras:", fmt_rs(out.desconto_bandeiras_rs))
    st.write("**Valor a pagar via boleto:**", fmt_rs(out.valor_boleto))

   # Gera PNG
    png = exportar_png(titulo_mes=mes_png, titulo_ano=int(ano_png), e=e, out=out)

    # Mostra direto abaixo do resumo (sem precisar rolar pra baixo)
    fname = f"compensacao_{mes_png}_{int(ano_png)}.png"
    st.divider()
    st.download_button("⬇️ Baixar PNG", data=png, file_name=fname, mime="image/png")

    # Exibe automaticamente a prévia logo após o resumo
    st.image(png, caption=fname, use_column_width=True)



st.divider()
st.caption("Criado por Magnon R.A.S Faria — Grupo AKTI.")
