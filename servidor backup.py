from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import json
import os
import sys
import uuid
import socket
import threading
import webbrowser
import tkinter as tk
from tkinter import font
import sqlite3
import shutil
from datetime import datetime

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    pasta_raiz = os.path.dirname(sys.executable)
else:
    template_folder = 'templates'
    pasta_raiz = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=template_folder)

ARQUIVO_BANCO = os.path.join(pasta_raiz, 'dados_crm.json')
ARQUIVO_BANCO_CHAT = os.path.join(pasta_raiz, 'chat_loja.db')
PASTA_UPLOADS = os.path.join(pasta_raiz, 'uploads')
PASTA_DRIVE = os.path.join(pasta_raiz, 'Drive_Loja')

if not os.path.exists(PASTA_UPLOADS): os.makedirs(PASTA_UPLOADS)
if not os.path.exists(PASTA_DRIVE): os.makedirs(PASTA_DRIVE)

app.config['PASTA_UPLOADS'] = PASTA_UPLOADS
app.config['PASTA_DRIVE'] = PASTA_DRIVE

# === MOTOR DE BANCO DE DADOS BLINDADO ===
db_lock = threading.Lock()

def ler_banco():
    with db_lock:
        if not os.path.exists(ARQUIVO_BANCO):
            with open(ARQUIVO_BANCO, 'w', encoding='utf-8') as f: 
                json.dump({}, f)
            return {}
        try:
            with open(ARQUIVO_BANCO, 'r', encoding='utf-8') as f: 
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erro ao ler banco de dados: {e}")
            if os.path.exists(ARQUIVO_BANCO) and os.path.getsize(ARQUIVO_BANCO) > 0:
                backup_path = ARQUIVO_BANCO + '.bak'
                if os.path.exists(backup_path):
                    with open(backup_path, 'r', encoding='utf-8') as f_bak:
                        return json.load(f_bak)
            return {}

def salvar_banco(dados):
    with db_lock:
        try:
            if os.path.exists(ARQUIVO_BANCO) and os.path.getsize(ARQUIVO_BANCO) > 0:
                shutil.copy2(ARQUIVO_BANCO, ARQUIVO_BANCO + '.bak')
            temp_file = ARQUIVO_BANCO + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f: 
                json.dump(dados, f, indent=4, ensure_ascii=False)
            os.replace(temp_file, ARQUIVO_BANCO)
        except Exception as e:
            print(f"🚨 Erro crítico ao salvar no banco de dados: {e}")

def iniciar_banco_chat():
    conn = sqlite3.connect(ARQUIVO_BANCO_CHAT)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS mensagens_privadas (id INTEGER PRIMARY KEY AUTOINCREMENT, remetente TEXT, destinatario TEXT, texto TEXT, hora TEXT)''')
    try: cursor.execute("ALTER TABLE mensagens_privadas ADD COLUMN arquivo TEXT")
    except: pass
    cursor.execute('''CREATE TABLE IF NOT EXISTS roleta (id INTEGER PRIMARY KEY AUTOINCREMENT, fila TEXT, vez_index INTEGER)''')
    cursor.execute("SELECT COUNT(*) FROM roleta")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO roleta (fila, vez_index) VALUES ('[]', 0)")
    conn.commit()
    conn.close()

iniciar_banco_chat()

@app.route('/')
def home(): return render_template('index.html')

@app.route('/api/usuarios', methods=['GET'])
def listar_usuarios(): 
    db = ler_banco()
    usuarios = []
    for k, v in db.items():
        if k == 'empresa_config': continue
        if isinstance(v, dict): usuarios.append({"nome": k, "role": v.get("role", "vendedor")})
        else: usuarios.append({"nome": k, "role": "vendedor"})
    return jsonify(usuarios)

@app.route('/api/login', methods=['POST'])
def login():
    req = request.json
    usuario, senha, cargo = req.get('usuario'), req.get('senha'), req.get('role', 'vendedor')
    db = ler_banco()
    if usuario in db and usuario != 'empresa_config':
        v = db[usuario]
        if isinstance(v, dict):
            if v.get('senha') == senha: return jsonify({"status": "sucesso", "role": v.get('role', 'vendedor')})
            else: return jsonify({"status": "erro", "mensagem": "Senha incorreta!"}), 401
        else:
            db[usuario] = {"senha": senha, "role": "vendedor", "dados": v}
            salvar_banco(db)
            return jsonify({"status": "sucesso", "role": "vendedor"})
    else:
        db[usuario] = {"senha": senha, "role": cargo, "dados": {"leads": [], "settings": {"monthlyGoal": 50000}}}
        salvar_banco(db)
        return jsonify({"status": "sucesso", "mensagem": "Novo usuário criado!", "role": cargo})

@app.route('/api/ler_dados', methods=['GET'])
def ler_dados():
    usuario = request.args.get('usuario')
    db = ler_banco()
    if usuario in db: 
        v = db[usuario]
        if isinstance(v, dict) and "dados" in v: return jsonify(v["dados"])
        else: return jsonify(v) 
    return jsonify({"leads": [], "settings": {}}), 404

@app.route('/api/ler_tudo', methods=['GET'])
def ler_tudo():
    db = ler_banco()
    dados_seguros = {}
    for k, v in db.items():
        if k == 'empresa_config': continue
        if isinstance(v, dict): dados_seguros[k] = {"role": v.get("role", "vendedor"), "dados": v.get("dados", {})}
        else: dados_seguros[k] = {"role": "vendedor", "dados": v}
    return jsonify(dados_seguros)

@app.route('/api/salvar_dados', methods=['POST'])
def salvar_dados():
    usuario = request.args.get('usuario')
    db = ler_banco()
    if usuario in db and usuario != 'empresa_config':
        if isinstance(db[usuario], dict): db[usuario]['dados'] = request.json
        else: db[usuario] = {"senha": "", "role": "vendedor", "dados": request.json}
        salvar_banco(db)
        return jsonify({"status": "sucesso"})
    return jsonify({"status": "erro"}), 404

@app.route('/api/empresa', methods=['GET', 'POST'])
def config_empresa():
    db = ler_banco()
    if request.method == 'POST':
        db['empresa_config'] = request.json
        salvar_banco(db)
        return jsonify({"status": "sucesso"})
    return jsonify(db.get('empresa_config', {}))

# ==============================================================
# NOVO GERADOR DE CONTRATOS - PADRÃO "BRASIL MOBILIÁRIO"
# ==============================================================
@app.route('/api/gerar_contrato', methods=['POST'])
def gerar_contrato():
    try:
        from fpdf import FPDF
        dados = request.json
        db = ler_banco()
        empresa = db.get('empresa_config', {})

        def limpa(texto):
            if texto is None: return ""
            return str(texto).encode('latin-1', 'replace').decode('latin-1')

        def formatar_data(data_str):
            try:
                dt = datetime.strptime(data_str, "%Y-%m-%d")
                return dt.strftime("%d/%m/%Y")
            except:
                return data_str

        data_pedido_br = formatar_data(dados.get('data_pedido', ''))

        pdf = FPDF()
        # Margens e quebra de página automática para o contrato longo
        pdf.set_auto_page_break(auto=True, margin=15)

        # --- CABEÇALHO PADRÃO ---
        def desenhar_cabecalho(titulo=""):
            pdf.add_page()
            logo_path = empresa.get('logo_salvo')
            if logo_path and os.path.exists(os.path.join(app.config['PASTA_UPLOADS'], logo_path)):
                try: pdf.image(os.path.join(app.config['PASTA_UPLOADS'], logo_path), 10, 8, 22)
                except: pass

            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 5, limpa(empresa.get('nome', 'BRASIL MOBILIÁRIO')), ln=True, align='R')
            pdf.set_font("Arial", '', 8)
            pdf.cell(0, 4, limpa(f"CNPJ: {empresa.get('cnpj', '')}"), ln=True, align='R')
            pdf.cell(0, 4, limpa(empresa.get('endereco', '')), ln=True, align='R')
            pdf.cell(0, 4, limpa(f"Contato: {empresa.get('telefone', '')}"), ln=True, align='R')
            pdf.ln(12)
            
            if titulo:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 8, limpa(titulo), ln=True, align='C')
                pdf.ln(5)

        # --- DADOS DO CLIENTE PADRÃO ---
        def desenhar_dados_cliente():
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 6, limpa(" DADOS DO CLIENTE E DO PROJETO"), border=1, ln=True, fill=True)
            pdf.set_font("Arial", '', 8)
            
            pdf.cell(100, 6, limpa(f" Nome: {dados.get('nome')}"), border='L', ln=False)
            pdf.cell(45, 6, limpa(f" CPF/CNPJ: {dados.get('cpf')}"), ln=False)
            pdf.cell(0, 6, limpa(f" RG: {dados.get('rg')}"), border='R', ln=True)
            
            pdf.cell(100, 6, limpa(f" Endereço Atual: {dados.get('endereco_atual')} - CEP: {dados.get('cep_atual')}"), border='L', ln=False)
            pdf.cell(0, 6, limpa(f" Telefone: {dados.get('telefone')}"), border='R', ln=True)
            
            pdf.cell(0, 6, limpa(f" End. de Entrega/Obra: {dados.get('endereco_entrega')} - CEP: {dados.get('cep_entrega')}"), border='LR', ln=True)
            
            pdf.cell(90, 6, limpa(f" Condomínio: {dados.get('empreendimento')}"), border='LB', ln=False)
            pdf.cell(60, 6, limpa(f" Vendedor: {dados.get('vendedor')}"), border='B', ln=False)
            pdf.cell(0, 6, limpa(f" Data: {data_pedido_br}"), border='RB', ln=True)
            pdf.ln(6)

        # --- ASSINATURAS PADRÃO AJUSTADAS ---
        def desenhar_assinaturas(incluir_testemunhas=False):
            # Calcula matematicamente se as assinaturas cabem na página atual
            espaco_necessario = 40 if incluir_testemunhas else 25
            if pdf.get_y() + espaco_necessario > 282: 
                pdf.add_page()
            else:
                pdf.ln(12) # Reduzido para encaixar melhor
            
            y_assinaturas = pdf.get_y()
            
            pdf.line(20, y_assinaturas, 90, y_assinaturas)
            pdf.set_xy(20, y_assinaturas + 2)
            pdf.set_font("Arial", '', 8)
            pdf.cell(70, 5, limpa(f"{dados.get('nome')}"), ln=True, align='C')
            pdf.set_x(20)
            pdf.set_font("Arial", 'B', 8)
            pdf.cell(70, 5, limpa("Comprador(a) / Contratante"), ln=False, align='C')
            
            pdf.line(120, y_assinaturas, 190, y_assinaturas)
            pdf.set_xy(120, y_assinaturas + 2)
            pdf.set_font("Arial", '', 8)
            pdf.cell(70, 5, limpa(f"{empresa.get('nome', 'Brasil Mobiliário')}"), ln=True, align='C')
            pdf.set_x(120)
            pdf.set_font("Arial", 'B', 8)
            pdf.cell(70, 5, limpa("Vendedor(a) Representante"), ln=True, align='C')

            if incluir_testemunhas:
                pdf.ln(12)
                y_testemunhas = pdf.get_y()
                pdf.line(20, y_testemunhas, 90, y_testemunhas)
                pdf.set_xy(20, y_testemunhas + 2)
                pdf.set_font("Arial", '', 8)
                pdf.cell(70, 5, limpa("Testemunha 1:"), ln=True, align='C')
                
                pdf.line(120, y_testemunhas, 190, y_testemunhas)
                pdf.set_xy(120, y_testemunhas + 2)
                pdf.cell(70, 5, limpa("Testemunha 2:"), ln=True, align='C')


        # ==========================================================
        # PARTE 1: CONTRATO JURÍDICO (PÁGINAS 1 E 2)
        # ==========================================================
        desenhar_cabecalho("CONTRATO DE VENDA E INSTALAÇÃO DE MÓVEIS PLANEJADOS")
        desenhar_dados_cliente()

        pdf.set_font("Arial", '', 9)
        linha_h = 4

        def clausula(titulo, texto):
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 5, limpa(titulo), ln=True)
            pdf.set_font("Arial", '', 8)
            pdf.multi_cell(0, linha_h, limpa(texto))
            pdf.ln(2) # Reduzido de 4 para 2 para economizar espaço e caber na página 2

        clausula("CLÁUSULA 1 - OBJETO", "A CONTRATADA compromete-se a fabricar e vender à CONTRATANTE os bens móveis discriminados no pedido e nos projetos anexos, devidamente aprovados e assinados pela CONTRATANTE, os quais passam a integrar o presente contrato para todos os fins de direito.\nParágrafo único: Os pagamentos deverão ser realizados rigorosamente nas datas estipuladas neste instrumento, não sendo permitida qualquer prorrogação de prazo, sob quaisquer circunstâncias.")

        clausula("CLÁUSULA 2 - APROVAÇÃO DO PROJETO E RESPONSABILIDADES", "2.1. A CONTRATANTE declara que aprovou o esboço do projeto apresentado. Considerando que os móveis serão fabricados sob encomenda, de forma exclusiva e personalizada, não será permitida qualquer alteração, cancelamento ou desistência após a aprovação do projeto, sob pena de caracterização de grave violação contratual.\n2.2. O projeto não inclui instalações de qualquer natureza, exceto a instalação dos próprios móveis, ficando expressamente excluídos serviços como adequações elétricas, hidráulicas, tomadas, encanamentos, entre outros.\n2.3. A responsabilidade por quaisquer danos aos móveis adquiridos que não decorram do uso normal, bem como aqueles ocasionados por terceiros (pedreiros, eletricistas, pintores, etc.) que estejam atuando no imóvel, será integralmente da CONTRATANTE.")

        clausula("CLÁUSULA 3 - DESISTÊNCIA OU DEVOLUÇÃO", "3.1. Por se tratar de produtos confeccionados sob encomenda e com exclusividade para o local projetado, não será possível a devolução ou desistência do pedido após a assinatura deste contrato.\n3.2. Em caso de desistência, a CONTRATANTE responderá civilmente pelos prejuízos causados, ficando desde já estabelecida multa compensatória correspondente a 30% (trinta por cento) do valor total do projeto, autorizando a CONTRATADA a emitir letra de câmbio no referido valor.")

        clausula("CLÁUSULA 4 - ANÁLISE DE CRÉDITO E FORMA DE PAGAMENTO", "4.1. O pedido estará sujeito à análise de crédito da CONTRATANTE, podendo ser suspenso pela CONTRATADA, se necessário.\n4.2. Caso a forma de pagamento seja por meio de cheques, a CONTRATANTE declara ciência de que a CONTRATADA poderá negociá-los junto a instituições financeiras, conforme sua conveniência.")

        clausula("CLÁUSULA 5 - OBRIGAÇÕES DA CONTRATADA", "5.1. Constituem obrigações da CONTRATADA:\na) Atender, dentro dos prazos convencionados, às solicitações da CONTRATANTE quanto à entrega, montagem dos móveis e assistência técnica decorrente de defeitos de fabricação;\nb) Sanar eventuais defeitos ou irregularidades no prazo máximo de 55 (cinquenta e cinco) dias, sem que isso configure descumprimento contratual;\nc) Executar a montagem dos móveis objeto deste contrato.")

        prazo_txt = str(dados.get('prazo_entrega', '35 dias corridos'))
        clausula("CLÁUSULA 6 - PRAZO DE ENTREGA E INSTALAÇÃO", f"6.1. O prazo de entrega dos produtos será de {prazo_txt} contados a partir da assinatura do projeto final, o qual será apresentado em até 7 (sete) dias após a medição definitiva do local.\n6.2. Para cumprimento do prazo, é indispensável que a parte civil do imóvel esteja concluída, evitando alterações nas medidas.\n6.3. A entrega ocorrerá em horário comercial.\n6.4. O início da montagem ocorrerá em até 1 (um) dia útil após a entrega dos produtos. O prazo de conclusão dependerá da complexidade técnica de cada projeto.\n6.5. O local deverá possuir fornecimento de energia elétrica e iluminação adequados. Na ausência dessas condições, a montagem será cancelada.\n6.6. Paredes de gesso/Drywall: quando houver instalação em paredes desse tipo, o uso de buchas especiais é obrigatório, devendo ser fornecidas pela CONTRATANTE.\n6.7. Assistência técnica: será prestada nos casos de defeitos de fabricação ou extravio de peças, restringindo-se à substituição da peça danificada. O prazo para atendimento é de até 30 (trinta) dias úteis.\n6.8. Multa por atraso na entrega: Caso a CONTRATADA ultrapasse o prazo de entrega estabelecido neste contrato, sem justificativa devidamente comprovada e aceita pela CONTRATANTE, incidirá multa compensatória equivalente a 10% (dez por cento) do valor total do contrato por mês de atraso. A multa não será aplicada nos casos de força maior, atraso ocasionado por terceiros, ou responsabilidade da CONTRATANTE.")

        clausula("CLÁUSULA 7 - GARANTIA", "7.1. A CONTRATADA concede garantia de 10 (dez) anos para os módulos, contra defeitos e vícios de fabricação, contados a partir da data da conclusão da montagem.\n7.2. Nos termos do Código de Defesa do Consumidor, a mão de obra referente à montagem, regulagens e ajustes, sem fornecimento de material, possui garantia de 90 (noventa) dias após a conclusão da montagem.\n7.3. Estão excluídas da garantia: Desgaste natural decorrente do uso; Danos causados por agentes externos, como água, maresia, ferrugem, incêndio, cupins e pragas em geral; Uso inadequado, aquecimento excessivo, falta de manutenção, limpeza inadequada ou utilização de produtos de limpeza não recomendados.")

        clausula("CLÁUSULA 8 - LIMPEZA E CONSERVAÇÃO", "8.1. Armários, portas e tampos devem ser limpos com pano macio levemente umedecido em água morna, secando-se em seguida.\n8.2. Utilizar apenas lustra-móveis à base de silicone incolor.\n8.3. Evitar o contato com substâncias ou materiais abrasivos.\n8.4. Recomenda-se a realização periódica de dedetização/descupinização nos ambientes.")

        clausula("CLÁUSULA 9 - RESERVA DE DOMÍNIO", "9.1. A CONTRATADA reserva-se o domínio dos bens móveis até a quitação integral do preço. Até esse momento, a CONTRATANTE será mera detentora dos bens, assumindo todas as responsabilidades civis, na condição de fiel depositária.")

        clausula("CLÁUSULA 10 - INADIMPLEMENTO", "10.1. Em caso de inadimplemento das obrigações pela CONTRATANTE, a CONTRATADA poderá reintegrar-se na posse dos bens, aliená-los a terceiros e utilizar o valor obtido para abatimento do débito, devolvendo à CONTRATANTE eventual saldo remanescente.")

        clausula("CLÁUSULA 11 - FORO", "11.1. As partes elegem o foro da Comarca da Capital do Estado de São Paulo para dirimir quaisquer controvérsias oriundas deste contrato, com renúncia expressa a qualquer outro, por mais privilegiado que seja.\n\nE, por estarem justas e contratadas, assinam o presente instrumento em duas vias de igual teor, na presença de duas testemunhas.")

        # Assinaturas da Parte Jurídica (com testemunhas) agora devem caber perfeitamente na página 2!
        desenhar_assinaturas(incluir_testemunhas=True)


        # ==========================================================
        # PARTE 2: PEDIDO E ESPECIFICAÇÕES TÉCNICAS
        # ==========================================================
        desenhar_cabecalho("PEDIDO E ESPECIFICAÇÕES DO PROJETO")
        desenhar_dados_cliente()

        # Tabela de Ambientes
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 6, limpa(" 1. AMBIENTES CONTRATADOS (MARCENARIA)"), border=1, ln=True, fill=True)
        
        ambientes = dados.get('ambientes_lista', [])
        if len(ambientes) == 0:
            pdf.set_font("Arial", '', 8)
            pdf.cell(0, 6, limpa(" Nenhum ambiente discriminado."), border=1, ln=True)
        else:
            pdf.set_font("Arial", 'B', 8)
            pdf.cell(60, 6, limpa(" AMBIENTE"), border=1, ln=False)
            pdf.cell(45, 6, limpa(" CAIXARIA"), border=1, ln=False)
            pdf.cell(45, 6, limpa(" PORTAS / PUXADORES"), border=1, ln=False)
            pdf.cell(40, 6, limpa(" VALOR"), border=1, ln=True, align='C')
            pdf.set_font("Arial", '', 8)
            for amb in ambientes:
                pdf.cell(60, 6, limpa(f" {amb.get('nome')}"), border=1, ln=False)
                pdf.cell(45, 6, limpa(" Conforme Projeto 3D"), border=1, ln=False)
                pdf.cell(45, 6, limpa(" A Definir"), border=1, ln=False)
                pdf.cell(40, 6, limpa(f" R$ {amb.get('valor')}"), border=1, ln=True, align='R')
        pdf.ln(4)

        # Tabela Turn Key
        turnkey_lista = dados.get('turnkey_lista', [])
        if len(turnkey_lista) > 0:
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 6, limpa(" 2. SERVIÇOS EXTRAS ADICIONAIS (TURN KEY)"), border=1, ln=True, fill=True)
            pdf.set_font("Arial", 'B', 8)
            pdf.cell(110, 6, limpa(" DESCRIÇÃO DO SERVIÇO / ITEM"), border=1, ln=False)
            pdf.cell(40, 6, limpa(" QUANTIDADE / DIMENSÃO"), border=1, ln=False, align='C')
            pdf.cell(40, 6, limpa(" VALOR"), border=1, ln=True, align='C')
            pdf.set_font("Arial", '', 8)
            for tk_item in turnkey_lista:
                pdf.cell(110, 6, limpa(f" {tk_item.get('nome')}"), border=1, ln=False)
                pdf.cell(40, 6, limpa(f" {tk_item.get('qtd')}"), border=1, ln=False, align='C')
                pdf.cell(40, 6, limpa(f" R$ {tk_item.get('total_item')}"), border=1, ln=True, align='R')
            pdf.ln(4)
            num_observacoes = "3"
            num_total = "4"
        else:
            num_observacoes = "2"
            num_total = "3"

        # Observações (Combinados Extras)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(0, 6, limpa(f" {num_observacoes}. DESCRIÇÃO DOS AMBIENTES E COMBINADOS EXTRAS"), border=1, ln=True, fill=True)
        pdf.set_font("Arial", '', 8)
        obs = str(dados.get('observacoes', '')).strip()
        if not obs: obs = "Nenhuma observação extra ou combinado cadastrado."
        pdf.multi_cell(0, 5, limpa(f"{obs}"), border=1)
        pdf.ln(6)

        # Valor Total do Projeto
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(130, 8, limpa(f" {num_total}. VALOR TOTAL DO PROJETO (MARCENARIA + EXTRAS):"), border=1, ln=False, align='R')
        pdf.cell(60, 8, limpa(f" R$ {dados.get('valor_geral_liquido')}"), border=1, ln=True, align='C')

        desenhar_assinaturas(incluir_testemunhas=False)


        # ==========================================================
        # PARTE 3: RECIBO FINANCEIRO
        # ==========================================================
        desenhar_cabecalho("RECIBO DE PAGAMENTO")
        
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(25, 6, limpa(" VENDEDOR:"), border=1, ln=False, fill=True)
        pdf.set_font("Arial", '', 9)
        pdf.cell(80, 6, limpa(f" {dados.get('vendedor')}"), border=1, ln=False)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(25, 6, limpa(" DATA:"), border=1, ln=False, fill=True)
        pdf.set_font("Arial", '', 9)
        pdf.cell(60, 6, limpa(f" {data_pedido_br}"), border=1, ln=True)

        pdf.set_font("Arial", 'B', 9)
        pdf.cell(25, 6, limpa(" CLIENTE:"), border=1, ln=False, fill=True)
        pdf.set_font("Arial", '', 9)
        pdf.cell(165, 6, limpa(f" {dados.get('nome')}"), border=1, ln=True)
        pdf.ln(8)

        # Tabela de Recibo (Padrão Original da Loja)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(0, 6, limpa(" DEMONSTRATIVO DE PARCELAS"), border=1, ln=True, align='C', fill=True)
        
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(15, 6, limpa(" N.º"), border=1, ln=False, align='C')
        pdf.cell(40, 6, limpa(" DATA (VENCIMENTO)"), border=1, ln=False, align='C')
        pdf.cell(65, 6, limpa(" FORMA DE PAGAMENTO"), border=1, ln=False)
        pdf.cell(35, 6, limpa(" VALOR DA PARCELA"), border=1, ln=False, align='R')
        pdf.cell(35, 6, limpa(" STATUS"), border=1, ln=True, align='C')

        pdf.set_font("Arial", '', 8)
        pagamentos = dados.get('pagamentos_lista', [])
        
        if len(pagamentos) == 0:
            pdf.cell(0, 6, limpa(" Nenhuma forma de pagamento registrada."), border=1, ln=True, align='C')
        else:
            for idx, pag in enumerate(pagamentos):
                tipo_limpo = str(pag.get('tipo', '')).replace(f"{idx+1}ª Parc. ", "").strip()
                venc_raw = pag.get('parcelas', '')
                data_venc = venc_raw.replace("(Vencimento: ", "").replace(")", "").strip() if "Vencimento" in venc_raw else data_pedido_br

                pdf.cell(15, 6, limpa(f" {idx+1:02d}"), border=1, ln=False, align='C')
                pdf.cell(40, 6, limpa(f" {data_venc}"), border=1, ln=False, align='C')
                pdf.cell(65, 6, limpa(f" {tipo_limpo}"), border=1, ln=False)
                pdf.cell(35, 6, limpa(f" R$ {pag.get('valor')}"), border=1, ln=False, align='R')
                pdf.cell(35, 6, limpa(" A VENCER"), border=1, ln=True, align='C')

        pdf.ln(8)

        # Quadro de Totais
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(120, 7, limpa(" VALOR TOTAL DA VENDA / RECEBIDO:"), border=1, ln=False, align='R')
        pdf.cell(70, 7, limpa(f" R$ {dados.get('valor_geral_liquido')}"), border=1, ln=True, align='C')
        pdf.cell(120, 7, limpa(" VALOR PENDENTE:"), border=1, ln=False, align='R')
        pdf.cell(70, 7, limpa(f" R$ {dados.get('valor_geral_liquido')}"), border=1, ln=True, align='C')
        
        pdf.ln(12)
        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 5, limpa(f"São Paulo, {data_pedido_br}."), ln=True, align='R')

        desenhar_assinaturas(incluir_testemunhas=False)

        # ==========================================================
        # SALVAMENTO FINAL DO ARQUIVO PDF E RESPOSTA PARA O JAVASCRIPT
        # ==========================================================
        nome_base = "".join(x for x in dados.get('nome', 'Cliente') if x.isalnum() or x in " ").replace(" ", "_")
        nome_arquivo = f"Contrato_Completo_{nome_base}.pdf"
        nome_salvo = f"{uuid.uuid4().hex}_{nome_arquivo}"
        caminho = os.path.join(app.config['PASTA_UPLOADS'], nome_salvo)

        pdf.output(caminho)
        return jsonify({"status": "sucesso", "nome_original": nome_arquivo, "nome_salvo": nome_salvo})
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Erro ao gerar PDF:", str(e))
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

# === MANUTENÇÃO DOS OUTROS ENDPOINTS (DRIVE, UPLOAD, CHAT, ROLETA) ===
@app.route('/api/drive/listar', methods=['POST'])
def listar_drive():
    subpath = request.json.get('path', '')
    query = request.json.get('search', '').lower().strip()
    
    if '..' in subpath: return jsonify([])
    target = os.path.join(app.config['PASTA_DRIVE'], subpath.lstrip('/\\'))
    if not os.path.exists(app.config['PASTA_DRIVE']): return jsonify([])
    
    itens = []
    if query:
        for root, dirs, files in os.walk(app.config['PASTA_DRIVE']):
            for d in dirs:
                if query in d.lower():
                    rel_path = os.path.relpath(os.path.join(root, d), app.config['PASTA_DRIVE']).replace('\\', '/')
                    itens.append({"nome": d, "is_dir": True, "path": rel_path})
            for f in files:
                if query in f.lower():
                    caminho_completo = os.path.join(root, f)
                    rel_path = os.path.relpath(caminho_completo, app.config['PASTA_DRIVE']).replace('\\', '/')
                    itens.append({"nome": f, "is_dir": False, "path": rel_path, "tamanho": os.path.getsize(caminho_completo)})
    else:
        if not os.path.exists(target): return jsonify([])
        for nome in os.listdir(target):
            caminho_completo = os.path.join(target, nome)
            is_dir = os.path.isdir(caminho_completo)
            rel_path = os.path.relpath(caminho_completo, app.config['PASTA_DRIVE']).replace('\\', '/')
            itens.append({"nome": nome, "is_dir": is_dir, "path": rel_path, "tamanho": os.path.getsize(caminho_completo) if not is_dir else 0})
            
    itens.sort(key=lambda x: (not x['is_dir'], x['nome'].lower()))
    return jsonify(itens)

@app.route('/api/drive/criar_pasta', methods=['POST'])
def criar_pasta_drive():
    subpath = request.json.get('path', '')
    nome = request.json.get('nome', '').strip()
    if '..' in subpath or '..' in nome or '/' in nome or '\\' in nome or not nome: return jsonify({"status": "erro"})
    target = os.path.join(app.config['PASTA_DRIVE'], subpath.lstrip('/\\'), nome)
    if not os.path.exists(target): os.makedirs(target)
    return jsonify({"status": "sucesso"})

@app.route('/api/drive/upload', methods=['POST'])
def upload_drive():
    subpath = request.form.get('path', '')
    if '..' in subpath: return jsonify({"status": "erro"}), 400
    if 'file' not in request.files: return jsonify({"status": "erro"}), 400
    arquivo = request.files['file']
    if arquivo.filename == '': return jsonify({"status": "erro"}), 400
    target_dir = os.path.join(app.config['PASTA_DRIVE'], subpath.lstrip('/\\'))
    if not os.path.exists(target_dir): os.makedirs(target_dir)
    nome_seguro = secure_filename(arquivo.filename)
    arquivo.save(os.path.join(target_dir, nome_seguro))
    return jsonify({"status": "sucesso"})

@app.route('/api/drive/deletar', methods=['POST'])
def deletar_drive():
    subpath = request.json.get('path', '')
    nome = request.json.get('nome', '')
    if '..' in subpath or '..' in nome or '/' in nome or '\\' in nome: return jsonify({"status": "erro"})
    target = os.path.join(app.config['PASTA_DRIVE'], subpath.lstrip('/\\'), nome)
    if os.path.exists(target):
        if os.path.isdir(target): shutil.rmtree(target)
        else: os.remove(target)
    return jsonify({"status": "sucesso"})

@app.route('/drive_files/<path:filename>')
def servir_drive(filename):
    if '..' in filename: return "Erro", 400
    return send_from_directory(app.config['PASTA_DRIVE'], filename)

@app.route('/api/upload', methods=['POST'])
def fazer_upload():
    if 'file' not in request.files: return jsonify({"status": "erro", "mensagem": "Nenhum arquivo"}), 400
    arquivo = request.files['file']
    if arquivo.filename == '': return jsonify({"status": "erro"}), 400
    nome_unico = f"{uuid.uuid4().hex}_{secure_filename(arquivo.filename)}"
    arquivo.save(os.path.join(app.config['PASTA_UPLOADS'], nome_unico))
    return jsonify({"status": "sucesso", "nome_original": arquivo.filename, "nome_salvo": nome_unico})

@app.route('/uploads/<path:filename>')
def acessar_arquivo(filename): return send_from_directory(app.config['PASTA_UPLOADS'], filename)

@app.route('/api/apagar_arquivo', methods=['POST'])
def apagar_arquivo():
    caminho = os.path.join(app.config['PASTA_UPLOADS'], request.json.get('nome_salvo', ''))
    if os.path.exists(caminho): os.remove(caminho)
    return jsonify({"status": "sucesso"})

@app.route('/api/chat', methods=['GET'])
def get_chat():
    remetente = request.args.get('remetente')
    destinatario = request.args.get('destinatario')
    try:
        conn = sqlite3.connect(ARQUIVO_BANCO_CHAT)
        cursor = conn.cursor()
        cursor.execute("SELECT remetente, texto, hora, arquivo FROM mensagens_privadas WHERE (remetente=? AND destinatario=?) OR (remetente=? AND destinatario=?) ORDER BY id ASC", (remetente, destinatario, destinatario, remetente))
        mensagens_db = cursor.fetchall()
        conn.close()
        return jsonify([{"usuario": m[0], "texto": m[1], "hora": m[2], "arquivo": m[3]} for m in mensagens_db])
    except: return jsonify([])

@app.route('/api/chat', methods=['POST'])
def post_chat():
    try:
        msg = request.json
        conn = sqlite3.connect(ARQUIVO_BANCO_CHAT)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO mensagens_privadas (remetente, destinatario, texto, hora, arquivo) VALUES (?, ?, ?, ?, ?)", (msg['remetente'], msg['destinatario'], msg['texto'], msg['hora'], msg.get('arquivo', '')))
        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso"})
    except: return jsonify({"status": "erro"}), 500

@app.route('/api/roleta', methods=['GET'])
def get_roleta():
    try:
        db = ler_banco()
        vendedores_ativos = []
        for k, v in db.items():
            if k == 'empresa_config': continue
            if isinstance(v, dict):
                if v.get("role", "vendedor") == "vendedor": vendedores_ativos.append(k)
            else: vendedores_ativos.append(k)
        
        conn = sqlite3.connect(ARQUIVO_BANCO_CHAT)
        cursor = conn.cursor()
        cursor.execute("SELECT fila, vez_index FROM roleta WHERE id = 1")
        fila_str, vez_index = cursor.fetchone()
        fila_salva = json.loads(fila_str)
        
        fila_atualizada = [u for u in fila_salva if u in vendedores_ativos]
        for u in vendedores_ativos:
            if u not in fila_atualizada: fila_atualizada.append(u)
                
        if len(fila_atualizada) > 0: vez_index = vez_index % len(fila_atualizada)
        else: vez_index = 0
            
        cursor.execute("UPDATE roleta SET fila = ?, vez_index = ? WHERE id = 1", (json.dumps(fila_atualizada), vez_index))
        conn.commit()
        conn.close()
        return jsonify({"fila": fila_atualizada, "vez_index": vez_index})
    except: return jsonify({"fila": [], "vez_index": 0})

@app.route('/api/roleta/avancar', methods=['POST'])
def avancar_roleta():
    try:
        conn = sqlite3.connect(ARQUIVO_BANCO_CHAT)
        cursor = conn.cursor()
        cursor.execute("SELECT fila, vez_index FROM roleta WHERE id = 1")
        fila_str, vez_index = cursor.fetchone()
        fila = json.loads(fila_str)
        if len(fila) > 0:
            cursor.execute("UPDATE roleta SET vez_index = ? WHERE id = 1", ((vez_index + 1) % len(fila),))
            conn.commit()
        conn.close()
        return jsonify({"status": "sucesso"})
    except: return jsonify({"status": "erro"}), 500

def iniciar_servidor(): app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    nome_do_pc = socket.gethostname()
    url_acesso = f"http://{nome_do_pc}:5000"
    caminho_atalho = os.path.join(pasta_raiz, 'Acesso_Equipe_CRM.url')
    with open(caminho_atalho, 'w') as f:
        f.write("[InternetShortcut]\n")
        f.write(f"URL={url_acesso}\n")

    thread_servidor = threading.Thread(target=iniciar_servidor)
    thread_servidor.daemon = True
    thread_servidor.start()

    janela = tk.Tk()
    janela.title("Painel de Controle - CRM")
    janela.geometry("550x380")
    janela.configure(bg="#0f172a")
    janela.resizable(False, False)
    fonte_titulo = font.Font(family="Helvetica", size=22, weight="bold")
    fonte_normal = font.Font(family="Helvetica", size=12)
    fonte_url = font.Font(family="Helvetica", size=16, weight="bold")
    tk.Label(janela, text="Brasil Mobiliário", font=fonte_titulo, fg="#eab308", bg="#0f172a").pack(pady=(30, 5))
    tk.Label(janela, text="🟢 Servidor Central Ativo e Rodando", font=fonte_normal, fg="#4ade80", bg="#0f172a").pack()
    frame_link = tk.Frame(janela, bg="#1e293b", padx=20, pady=20, highlightbackground="#334155", highlightthickness=1)
    frame_link.pack(pady=25, fill="x", padx=40)
    tk.Label(frame_link, text="Link de Acesso para a Equipe:", font=fonte_normal, fg="#94a3b8", bg="#1e293b").pack(pady=(0, 5))
    lbl_link = tk.Label(frame_link, text=url_acesso, font=fonte_url, fg="#eab308", bg="#1e293b", cursor="hand2")
    lbl_link.pack()
    def abrir_navegador(event=None): webbrowser.open(url_acesso)
    lbl_link.bind("<Button-1>", abrir_navegador)
    tk.Button(janela, text="ABRIR O MEU CRM", font=font.Font(family="Helvetica", size=12, weight="bold"), bg="#eab308", fg="#000000", activebackground="#ca8a04", relief="flat", padx=30, pady=10, command=abrir_navegador).pack(pady=10)
    tk.Label(janela, text="⚠️ Não feche esta janela enquanto a loja estiver usando o sistema.", font=font.Font(family="Helvetica", size=10), fg="#ef4444", bg="#0f172a").pack(side="bottom", pady=20)
    janela.mainloop()