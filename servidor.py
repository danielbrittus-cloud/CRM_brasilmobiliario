from flask import Flask, render_template, request, jsonify, send_from_directory, render_template_string
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
import base64
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

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

db_lock = threading.Lock()

# ==============================================================
# 📧 CONFIGURAÇÃO DE E-MAIL AUTOMÁTICO
# ==============================================================
EMAIL_LOJA = "seu_email@gmail.com"
SENHA_LOJA = "sua_senha_de_app"

def enviar_email_contrato(destinatario, nome_cliente, caminho_pdf):
    if not destinatario or "@" not in destinatario: return
    if EMAIL_LOJA == "seu_email@gmail.com":
        print("⚠️ ALERTA: E-mail não configurado. O PDF foi salvo no CRM, mas não enviado por e-mail.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_LOJA
        msg['To'] = destinatario
        msg['Subject'] = "Seu Contrato Assinado - Brasil Mobiliário"
        corpo = f"Olá, {nome_cliente}!\n\nO seu contrato foi assinado digitalmente com sucesso.\nSegue em anexo a sua via oficial do documento, contendo o Certificado de Autenticidade Digital.\n\nAtenciosamente,\nEquipe Brasil Mobiliário."
        msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
        
        with open(caminho_pdf, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(caminho_pdf)}")
        msg.attach(part)
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_LOJA, SENHA_LOJA)
        server.send_message(msg)
        server.quit()
        print(f"📧 E-mail enviado com sucesso para {destinatario}!")
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")

# ==============================================================
# 📱 TELA DO CLIENTE (ESTILO DOCUSIGN)
# ==============================================================
TELA_ASSINATURA_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Assinatura | Brasil Mobiliário</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #f1f5f9; touch-action: manipulation; }
        #signature-pad { border: 2px dashed #cbd5e1; background-color: white; border-radius: 1rem; width: 100%; height: 300px; cursor: crosshair; }
        .pdf-viewer { width: 100%; height: 60vh; border-radius: 0.75rem; border: 1px solid #cbd5e1; background-color: white; overflow: auto; -webkit-overflow-scrolling: touch; }
    </style>
</head>
<body class="flex flex-col items-center justify-start min-h-screen p-4">
    
    <div id="step-leitura" class="bg-white p-5 rounded-3xl shadow-xl w-full max-w-2xl text-center flex flex-col fade-in">
        <div class="flex items-center justify-center gap-3 mb-4">
            <div class="w-10 h-10 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center text-xl shadow-inner"><i class="fa-solid fa-file-contract"></i></div>
            <h2 class="text-xl font-bold text-slate-800">Leia seu Contrato</h2>
        </div>
        <p class="text-sm text-slate-500 mb-4 truncate">Olá, <b>{{ cliente_nome }}</b>. Revise os termos abaixo:</p>
        
        <div class="pdf-viewer shadow-inner mb-6">
            <iframe src="/uploads/{{ arquivo_pdf }}#toolbar=0" class="w-full h-full border-0"></iframe>
        </div>
        
        <button onclick="iniciarAssinatura()" class="w-full bg-blue-600 text-white font-bold py-4 rounded-xl transition-all shadow-md hover:bg-blue-700 hover:shadow-lg flex items-center justify-center gap-2 text-lg">
            <i class="fa-solid fa-pen-nib"></i> Li e Concordo - Assinar Agora
        </button>
    </div>

    <div id="step-assinatura" class="bg-white p-6 rounded-3xl shadow-xl w-full max-w-md text-center flex flex-col hidden fade-in mt-10">
        <i class="fa-solid fa-signature text-4xl text-blue-500 mb-3 drop-shadow-sm"></i>
        <h2 class="text-xl font-bold text-slate-800 leading-tight mb-2">Assinatura Digital</h2>
        <p class="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-4"><i class="fa-solid fa-pen mr-1"></i> Desenhe sua assinatura na caixa abaixo:</p>
        
        <canvas id="signature-pad" class="mb-6"></canvas>
        
        <div class="flex gap-3">
            <button onclick="voltarLeitura()" class="w-1/3 bg-slate-100 text-slate-600 font-bold py-3.5 rounded-xl transition-colors hover:bg-slate-200">Voltar</button>
            <button onclick="clearPad()" class="w-1/3 bg-slate-100 text-slate-600 font-bold py-3.5 rounded-xl transition-colors hover:bg-slate-200">Limpar</button>
            <button onclick="submitSignature()" id="btn-submit" class="w-1/3 bg-emerald-500 text-white font-bold py-3.5 rounded-xl transition-colors shadow-md hover:bg-emerald-600">Finalizar</button>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('signature-pad');
        const ctx = canvas.getContext('2d');
        let isDrawing = false;

        function iniciarAssinatura() {
            document.getElementById('step-leitura').classList.add('hidden');
            document.getElementById('step-assinatura').classList.remove('hidden');
            resizeCanvas();
        }

        function voltarLeitura() {
            document.getElementById('step-assinatura').classList.add('hidden');
            document.getElementById('step-leitura').classList.remove('hidden');
        }

        function resizeCanvas() {
            const rect = canvas.parentElement.getBoundingClientRect();
            canvas.width = rect.width - 48; // Ajusta padding
            canvas.height = 300;
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.strokeStyle = '#0f172a';
        }

        function getPos(e) {
            const rect = canvas.getBoundingClientRect();
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;
            return { x: clientX - rect.left, y: clientY - rect.top };
        }

        function startPosition(e) { e.preventDefault(); isDrawing = true; draw(e); }
        function endPosition() { isDrawing = false; ctx.beginPath(); }
        function draw(e) {
            if (!isDrawing) return;
            e.preventDefault();
            const pos = getPos(e);
            ctx.lineTo(pos.x, pos.y);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(pos.x, pos.y);
        }

        canvas.addEventListener('mousedown', startPosition); canvas.addEventListener('mouseup', endPosition); canvas.addEventListener('mousemove', draw);
        canvas.addEventListener('touchstart', startPosition, {passive: false}); canvas.addEventListener('touchend', endPosition); canvas.addEventListener('touchmove', draw, {passive: false});

        function clearPad() { ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.beginPath(); }

        function submitSignature() {
            const dataUrl = canvas.toDataURL('image/png');
            const blank = document.createElement('canvas');
            blank.width = canvas.width; blank.height = canvas.height;
            if(dataUrl === blank.toDataURL()) { alert("Por favor, assine no quadro tracejado."); return; }

            const btn = document.getElementById('btn-submit');
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>'; 
            btn.disabled = true;

            fetch('/api/assinar/{{ token }}', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ assinatura_b64: dataUrl })
            }).then(r => r.json()).then(res => {
                if(res.status === 'sucesso') {
                    document.body.innerHTML = '<div class="text-center p-8 bg-white rounded-3xl shadow-xl max-w-sm w-full mx-auto mt-20"><i class="fa-solid fa-circle-check text-7xl text-emerald-500 mb-4 drop-shadow-md"></i><h1 class="text-2xl font-bold text-slate-800">Assinado com Sucesso!</h1><p class="text-sm text-slate-500 mt-3">O documento final foi carimbado e enviado para o seu e-mail.<br><br><b>Pode fechar esta página.</b></p></div>';
                } else { alert("Erro: " + res.mensagem); btn.innerHTML = "Finalizar"; btn.disabled = false; }
            }).catch(e => { alert("Erro de conexão."); btn.innerHTML = "Finalizar"; btn.disabled = false; });
        }
    </script>
</body>
</html>
"""

# === FUNÇÕES DE BANCO DE DADOS ===
def ler_banco():
    with db_lock:
        if not os.path.exists(ARQUIVO_BANCO):
            with open(ARQUIVO_BANCO, 'w', encoding='utf-8') as f: json.dump({}, f)
            return {}
        try:
            with open(ARQUIVO_BANCO, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}

def salvar_banco(dados):
    with db_lock:
        try:
            if os.path.exists(ARQUIVO_BANCO): shutil.copy2(ARQUIVO_BANCO, ARQUIVO_BANCO + '.bak')
            with open(ARQUIVO_BANCO + '.tmp', 'w', encoding='utf-8') as f: json.dump(dados, f, indent=4, ensure_ascii=False)
            os.replace(ARQUIVO_BANCO + '.tmp', ARQUIVO_BANCO)
        except Exception as e: print(f"Erro: {e}")

def iniciar_banco_chat():
    conn = sqlite3.connect(ARQUIVO_BANCO_CHAT)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS mensagens_privadas (id INTEGER PRIMARY KEY AUTOINCREMENT, remetente TEXT, destinatario TEXT, texto TEXT, hora TEXT, arquivo TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS roleta (id INTEGER PRIMARY KEY AUTOINCREMENT, fila TEXT, vez_index INTEGER)''')
    cursor.execute("SELECT COUNT(*) FROM roleta")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO roleta (fila, vez_index) VALUES ('[]', 0)")
    conn.commit(); conn.close()

iniciar_banco_chat()

# ==============================================================
# MOTOR DE CONSTRUÇÃO DE PDF COM CARIMBO DE ASSINATURA DA LOJA
# ==============================================================
def criar_pdf_documento(dados, empresa, caminho_salvar, assinatura_cliente=None, usa_carimbo_loja=False, selo_ip=None, selo_data=None):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    def limpa(texto): return str(texto).encode('latin-1', 'replace').decode('latin-1')
    def formatar_data(data_str):
        try: return datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except: return data_str

    data_pedido_br = formatar_data(dados.get('data_pedido', ''))
    
    # Variáveis Dinâmicas para o SaaS (White-Label)
    nome_empresa = empresa.get('nome', 'NOME DA EMPRESA NÃO CONFIGURADO')
    cnpj_empresa = empresa.get('cnpj', '00.000.000/0000-00')

    def desenhar_cabecalho(titulo=""):
        pdf.add_page()
        logo_path = empresa.get('logo_salvo')
        if logo_path and os.path.exists(os.path.join(app.config['PASTA_UPLOADS'], logo_path)):
            try: pdf.image(os.path.join(app.config['PASTA_UPLOADS'], logo_path), 10, 8, 22)
            except: pass
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 5, limpa(nome_empresa), ln=True, align='R')
        pdf.set_font("Arial", '', 8)
        pdf.cell(0, 4, limpa(f"CNPJ: {cnpj_empresa}"), ln=True, align='R')
        pdf.cell(0, 4, limpa(empresa.get('endereco', '')), ln=True, align='R')
        pdf.cell(0, 4, limpa(f"Contato: {empresa.get('telefone', '')}"), ln=True, align='R')
        pdf.ln(12)
        if titulo:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, limpa(titulo), ln=True, align='C')
            pdf.ln(5)

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

    def desenhar_assinaturas(incluir_testemunhas=False):
        if pdf.get_y() + (40 if incluir_testemunhas else 25) > 282: pdf.add_page()
        else: pdf.ln(12)
        
        y_assinaturas = pdf.get_y()
        
        # LINHA E CARIMBO DO CLIENTE (CONTRATANTE)
        pdf.line(20, y_assinaturas, 90, y_assinaturas)
        if assinatura_cliente and os.path.exists(assinatura_cliente):
            pdf.image(assinatura_cliente, x=25, y=y_assinaturas - 16, w=45)

        pdf.set_xy(20, y_assinaturas + 2)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(70, 4, limpa("CONTRATANTE"), ln=True, align='C')
        pdf.set_x(20)
        pdf.set_font("Arial", '', 8)
        pdf.cell(70, 4, limpa(f"{dados.get('nome')}"), ln=True, align='C')
        pdf.set_x(20)
        pdf.cell(70, 4, limpa(f"CPF/CNPJ: {dados.get('cpf')}"), ln=True, align='C')
        
        # LINHA E CARIMBO DA LOJA AUTOMÁTICO (CONTRATADA)
        pdf.line(120, y_assinaturas, 190, y_assinaturas)
        
        if usa_carimbo_loja:
            pdf.set_xy(125, y_assinaturas - 12)
            pdf.set_font("Arial", 'B', 8)
            pdf.set_text_color(0, 102, 204) # Azul carimbo
            pdf.cell(60, 4, limpa("ASSINADO DIGITALMENTE"), align='C', ln=True)
            pdf.set_text_color(0, 0, 0) # Voltar para preto

        pdf.set_xy(120, y_assinaturas + 2)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(70, 4, limpa("CONTRATADA"), ln=True, align='C')
        pdf.set_x(120)
        pdf.set_font("Arial", '', 8)
        pdf.cell(70, 4, limpa(nome_empresa), ln=True, align='C')
        pdf.set_x(120)
        pdf.cell(70, 4, limpa(f"CNPJ: {cnpj_empresa}"), ln=True, align='C')

        if incluir_testemunhas:
            pdf.ln(10)
            y_testemunhas = pdf.get_y()
            pdf.line(20, y_testemunhas, 90, y_testemunhas)
            pdf.set_xy(20, y_testemunhas + 2)
            pdf.set_font("Arial", '', 8)
            pdf.cell(70, 4, limpa("Testemunha 1:"), ln=True, align='C')
            pdf.line(120, y_testemunhas, 190, y_testemunhas)
            pdf.set_xy(120, y_testemunhas + 2)
            pdf.cell(70, 4, limpa("Testemunha 2:"), ln=True, align='C')

    # ==========================================================
    # PARTE 1: CONTRATO MESTRE (MÓVEIS + TURN KEY)
    # ==========================================================
    desenhar_cabecalho("CONTRATO DE PRESTAÇÃO DE SERVIÇOS \"TURN-KEY\" E VENDA DE MÓVEIS PLANEJADOS")
    desenhar_dados_cliente()
    
    def clausula(titulo, texto):
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(0, 5, limpa(titulo), ln=True)
        pdf.set_font("Arial", '', 8)
        pdf.multi_cell(0, 4, limpa(texto))
        pdf.ln(2) 
        
    clausula("CLÁUSULA 1 - OBJETO", "1.1. O presente contrato tem por objeto a execução de projeto na modalidade \"Turn-Key\" (Empreitada Global), que compreende a fabricação, venda e instalação dos bens móveis sob medida, bem como a execução dos serviços de reforma, infraestrutura (elétrica, hidráulica, pintura, gesso, etc.) e o fornecimento de equipamentos e eletrodomésticos, estritamente conforme discriminado na Proposta Comercial e no Memorial Descritivo anexos, que, devidamente aprovados e assinados, passam a integrar este contrato para todos os fins de direito.\nParágrafo único: Os pagamentos deverão ser realizados rigorosamente nas datas estipuladas neste instrumento, não sendo permitida qualquer prorrogação de prazo, sob quaisquer circunstâncias.")
    clausula("CLÁUSULA 2 - APROVAÇÃO DO PROJETO E RESPONSABILIDADES", "2.1. A CONTRATANTE declara que aprovou o esboço do projeto e a proposta comercial apresentada. Considerando que os móveis serão fabricados sob encomenda e a obra executada de forma exclusiva, não será permitida alteração no escopo após a aprovação do Projeto Executivo Final.\n2.2. Quaisquer serviços, obras, adequações de infraestrutura ou itens não expressamente listados na Proposta Comercial e no Memorial Descritivo anexos serão de inteira responsabilidade e custeio exclusivo da CONTRATANTE.\n2.3. A responsabilidade por quaisquer danos aos móveis e serviços já executados que não decorram do uso normal, bem como aqueles ocasionados por terceiros (pedreiros, eletricistas, pintores, etc.) não contratados pela CONTRATADA e que estejam atuando no imóvel, será integralmente da CONTRATANTE.")
    clausula("CLÁUSULA 3 - DESISTÊNCIA E CANCELAMENTO", "3.1. Por se tratar de projeto personalizado e aquisição de materiais específicos para o local projetado, em caso de desistência imotivada por parte da CONTRATANTE, incidirão as seguintes multas compensatórias sobre o valor total do contrato:\na) Desistência antes da assinatura do Projeto Executivo Final e do início da fabricação ou das obras: multa de 10% (dez por cento) do valor total do contrato, para cobrir os custos operacionais e de desenvolvimento do projeto.\nb) Desistência após a assinatura do Projeto Executivo Final, com a fabricação dos móveis ou obras já iniciadas: multa de 30% (trinta por cento) do valor total do projeto, além da retenção dos valores proporcionais e correspondentes aos materiais já adquiridos e serviços já executados pela CONTRATADA até a data do cancelamento.")
    clausula("CLÁUSULA 4 - ANÁLISE DE CRÉDITO E FORMA DE PAGAMENTO", "4.1. O pedido estará sujeito à análise de crédito da CONTRATANTE, podendo ser suspenso pela CONTRATADA, se necessário.\n4.2. Caso a forma de pagamento seja por meio de cheques, a CONTRATANTE declara ciência de que a CONTRATADA poderá negociá-los junto a instituições financeiras, conforme sua conveniência.")
    clausula("CLÁUSULA 5 - OBRIGAÇÕES DA CONTRATADA", "5.1. Constituem obrigações da CONTRATADA:\na) Atender, dentro dos prazos convencionados, às solicitações da CONTRATANTE quanto à execução da obra, entrega, montagem dos móveis e assistência técnica decorrente de defeitos ou vícios;\nb) Sanar eventuais vícios, defeitos de fabricação ou irregularidades na montagem no prazo máximo de 30 (trinta) dias corridos a partir da notificação formal da CONTRATANTE, em estrita observância ao Artigo 18 do Código de Defesa do Consumidor;\nc) Executar os serviços e a montagem dos móveis objeto deste contrato em conformidade com o projeto aprovado.")
    
    prazo_txt = str(dados.get('prazo_entrega', '35 dias corridos'))
    clausula("CLÁUSULA 6 - PRAZO DE ENTREGA E INSTALAÇÃO", f"6.1. O prazo para a conclusão das obras e entrega dos produtos será de {prazo_txt}, contados exclusivamente a partir da assinatura e aprovação do Projeto Executivo Final pela CONTRATANTE. O projeto final será apresentado em até 7 (sete) dias após a medição definitiva do local.\n6.2. Para cumprimento do prazo de montagem dos móveis, é indispensável que a parte civil do imóvel (caso executada por terceiros) esteja concluída, evitando alterações nas medidas.\n6.3. A entrega ocorrerá em horário comercial.\n6.4. O início da montagem ocorrerá em até 1 (um) dia útil após a entrega dos produtos. O prazo de conclusão dependerá da complexidade técnica de cada projeto.\n6.5. O local deverá possuir fornecimento de energia elétrica e iluminação adequados. Na ausência dessas condições, a montagem será reagendada.\n6.6. Paredes de gesso/Drywall: quando houver instalação em paredes desse tipo não executadas pela CONTRATADA, o uso de buchas especiais é obrigatório, devendo ser fornecidas pela CONTRATANTE.\n6.7. Assistência técnica: será prestada nos casos de defeitos ou extravio de peças, restringindo-se à substituição ou reparo do item. O prazo máximo para o atendimento e solução é de 30 (trinta) dias corridos.\n6.8. Multa por atraso na entrega: Caso a CONTRATADA ultrapasse o prazo estabelecido na Cláusula 6.1, sem justificativa devidamente comprovada e aceita pela CONTRATANTE, incidirá multa compensatória equivalente a 10% (dez por cento) do valor total do contrato por mês de atraso, calculada de forma proporcional aos dias de atraso. A multa não será aplicada nos casos de força maior, atraso ocasionado por terceiros, ou quando o atraso decorrer de responsabilidade da CONTRATANTE.")
    clausula("CLÁUSULA 7 - GARANTIAS", "7.1. A CONTRATADA concede as seguintes garantias, contadas a partir da data de conclusão e entrega final:\na) Marcenaria: 10 (dez) anos para os módulos contra defeitos e vícios de fabricação, e 90 (noventa) dias para a mão de obra referente à montagem, regulagens e ajustes de ferragens.\nb) Obras Civis e Instalações: 5 (cinco) anos para a solidez e segurança das instalações estruturais, elétricas e hidráulicas executadas exclusivamente pela CONTRATADA, nos termos do Art. 618 do Código Civil.\nc) Eletrodomésticos, Eletrônicos e Equipamentos de Terceiros: A garantia será a fornecida pelo fabricante original de cada produto, cabendo à CONTRATADA o repasse dos respectivos manuais e notas fiscais à CONTRATANTE no ato da entrega.\n7.2. Estão expressamente excluídas de todas as garantias acima:\n• Desgaste natural decorrente do uso;\n• Danos causados por agentes externos, como água (exceto em vazamentos oriundos de instalação hidráulica feita pela Contratada no prazo de garantia), maresia, ferrugem, incêndio, cupins e pragas em geral;\n• Uso inadequado, sobrecarga de peso, aquecimento excessivo, falta de manutenção, limpeza inadequada ou utilização de produtos de limpeza não recomendados.")
    clausula("CLÁUSULA 8 - LIMPEZA E CONSERVAÇÃO", "8.1. Armários, portas e tampos devem ser limpos com pano macio levemente umedecido em água morna, secando-se em seguida.\n8.2. Utilizar apenas lustra-móveis à base de silicone incolor.\n8.3. Evitar o contato com substâncias ou materiais abrasivos.\n8.4. Recomenda-se a realização periódica de dedetização/descupinização nos ambientes.")
    clausula("CLÁUSULA 9 - RESERVA DE DOMÍNIO", "9.1. Em casos onde o pagamento do projeto seja realizado de forma parcelada, com parcelas a vencer após a entrega dos serviços, a CONTRATADA reserva-se o domínio dos bens fornecidos até a liquidação integral do saldo devedor. Até esse momento, a CONTRATANTE será mera detentora dos bens, assumindo todas as responsabilidades civis na condição de fiel depositária. Caso o pagamento já tenha sido integralmente quitado antes ou no ato da entrega, a propriedade dos bens transfere-se imediatamente e em definitivo à CONTRATANTE.")
    clausula("CLÁUSULA 10 - INADIMPLEMENTO", "10.1. Em caso de inadimplemento das obrigações pela CONTRATANTE, a CONTRATADA poderá reintegrar-se na posse dos bens com reserva de domínio, aliená-los a terceiros e utilizar o valor obtido para abatimento do débito, devolvendo à CONTRATANTE eventual saldo remanescente.")
    clausula("CLÁUSULA 11 - FORO", "11.1. As partes elegem o foro da Comarca da Capital do Estado de São Paulo para dirimir quaisquer controvérsias oriundas deste contrato, com renúncia expressa a qualquer outro, por mais privilegiado que seja.\n\nE, por estarem justas e contratadas, assinam o presente instrumento em duas vias de igual teor, na presença de duas testemunhas.")
    
    desenhar_assinaturas(incluir_testemunhas=True)

    # ==========================================================
    # PARTE 2: PEDIDO E ESPECIFICAÇÕES
    # ==========================================================
    desenhar_cabecalho("PEDIDO E ESPECIFICAÇÕES DO PROJETO E OBRA")
    desenhar_dados_cliente()
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

    turnkey_lista = dados.get('turnkey_lista', [])
    if len(turnkey_lista) > 0:
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(0, 6, limpa(" 2. SERVIÇOS EXTRAS ADICIONAIS E OBRAS (TURN-KEY)"), border=1, ln=True, fill=True)
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
        num_observacoes, num_total = "3", "4"
    else:
        num_observacoes, num_total = "2", "3"

    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 6, limpa(f" {num_observacoes}. DESCRIÇÃO DOS AMBIENTES E COMBINADOS EXTRAS"), border=1, ln=True, fill=True)
    pdf.set_font("Arial", '', 8)
    obs = str(dados.get('observacoes', '')).strip()
    if not obs: obs = "Nenhuma observação extra ou combinado cadastrado."
    pdf.multi_cell(0, 5, limpa(f"{obs}"), border=1)
    pdf.ln(6)

    pdf.set_font("Arial", 'B', 11)
    pdf.cell(130, 8, limpa(f" {num_total}. VALOR TOTAL DO PROJETO (MARCENARIA + TURN-KEY):"), border=1, ln=False, align='R')
    pdf.cell(60, 8, limpa(f" R$ {dados.get('valor_geral_liquido')}"), border=1, ln=True, align='C')
    desenhar_assinaturas(incluir_testemunhas=False)

    # ==========================================================
    # PARTE 3: RECIBO FINANCEIRO E DEMONSTRATIVO
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
            
            # --- LÓGICA AUTOMÁTICA DE STATUS ---
            status_txt = "A VENCER"
            tipo_upper = tipo_limpo.upper()
            
            if "PIX" in tipo_upper or "CARTÃO" in tipo_upper or "CARTAO" in tipo_upper or "DINHEIRO" in tipo_upper or "TRANSF" in tipo_upper:
                try:
                    dt_v = datetime.strptime(data_venc, "%d/%m/%Y").date()
                    dt_hoje = datetime.now().date()
                    if dt_v <= dt_hoje:
                        status_txt = "PAGO"
                except:
                    if data_venc == datetime.now().strftime("%d/%m/%Y"):
                        status_txt = "PAGO"

            pdf.cell(15, 6, limpa(f" {idx+1:02d}"), border=1, ln=False, align='C')
            pdf.cell(40, 6, limpa(f" {data_venc}"), border=1, ln=False, align='C')
            pdf.cell(65, 6, limpa(f" {tipo_limpo}"), border=1, ln=False)
            pdf.cell(35, 6, limpa(f" R$ {pag.get('valor')}"), border=1, ln=False, align='R')
            
            if status_txt == "PAGO":
                pdf.set_text_color(0, 153, 51)
                pdf.set_font("Arial", 'B', 8)
            else:
                pdf.set_text_color(204, 0, 0)
                pdf.set_font("Arial", 'B', 8)
                
            pdf.cell(35, 6, limpa(f" {status_txt}"), border=1, ln=True, align='C')
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", '', 8)

    pdf.ln(8)
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
    # PARTE 4: SELO DE CERTIFICADO DIGITAL
    # ==========================================================
    if selo_ip and selo_data:
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, limpa("CERTIFICADO DE ASSINATURA DIGITAL"), ln=True, align='C')
        pdf.line(10, 20, 200, 20)
        pdf.ln(15)
        pdf.set_font("Arial", '', 11)
        pdf.cell(0, 8, limpa(f"Documentos conferidos e assinados digitalmente pelo Contratante: {dados.get('nome')}"), ln=True)
        pdf.cell(0, 8, limpa(f"CPF / CNPJ: {dados.get('cpf')}"), ln=True)
        pdf.cell(0, 8, limpa(f"Data e Hora da Assinatura: {selo_data}"), ln=True)
        pdf.cell(0, 8, limpa(f"Endereço IP de Registro (Dispositivo): {selo_ip}"), ln=True)
        pdf.ln(20)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 8, limpa("Rubrica Coletada:"), ln=True)
        if assinatura_cliente and os.path.exists(assinatura_cliente):
            pdf.image(assinatura_cliente, x=20, w=60)

    pdf.output(caminho_salvar)

# ==============================================================
# ROTAS DO CRM - PÁGINA INICIAL E BANCO DE DADOS 
# ==============================================================
@app.route('/')
def index():
    return render_template('index.html')

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
# GERAÇÃO INICIAL E PROCESSO DE ASSINATURA
# ==============================================================
@app.route('/api/gerar_contrato', methods=['POST'])
def gerar_contrato():
    try:
        dados = request.json
        db = ler_banco()
        empresa = db.get('empresa_config', {})

        modo = dados.get('modo_assinatura', '')
        usa_carimbo = (modo == 'digital')

        nome_base = "".join(x for x in dados.get('nome', 'Cliente') if x.isalnum() or x in " ").replace(" ", "_")
        nome_arquivo = f"Contrato_Pendente_{nome_base}.pdf"
        nome_salvo = f"{uuid.uuid4().hex}_{nome_arquivo}"
        caminho_pdf = os.path.join(app.config['PASTA_UPLOADS'], nome_salvo)

        # Salva o Payload para recriar o PDF depois
        caminho_payload = os.path.join(app.config['PASTA_UPLOADS'], nome_salvo + ".json")
        with open(caminho_payload, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False)

        criar_pdf_documento(dados, empresa, caminho_pdf, usa_carimbo_loja=usa_carimbo)
        return jsonify({"status": "sucesso", "nome_original": nome_arquivo, "nome_salvo": nome_salvo})
    except Exception as e:
        print("Erro ao gerar PDF:", str(e))
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/assinar/<token>', methods=['GET'])
def assinar_page(token):
    db = ler_banco()
    for usr, usr_data in db.items():
        if isinstance(usr_data, dict) and 'dados' in usr_data:
            for lead in usr_data['dados'].get('leads', []):
                if lead.get('assinatura', {}).get('token') == token:
                    if lead['assinatura'].get('status') == 'Assinado':
                        return "<h2 style='text-align:center; margin-top:50px; font-family:sans-serif; color:#10b981;'>✅ Este contrato já foi assinado e validado!</h2>"
                    nome = lead.get('name', 'Cliente')
                    arquivo = lead['assinatura']['arquivo_pdf']
                    return render_template_string(TELA_ASSINATURA_HTML, token=token, cliente_nome=nome, arquivo_pdf=arquivo)
    return "<h2 style='text-align:center; margin-top:50px; font-family:sans-serif;'>Link inválido ou expirado.</h2>"

@app.route('/api/assinar/<token>', methods=['POST'])
def processar_assinatura(token):
    db = ler_banco()
    data = request.json
    img_b64 = data.get('assinatura_b64', '').split(',')[1]
    
    for usr, usr_data in db.items():
        if isinstance(usr_data, dict) and 'dados' in usr_data:
            for lead in usr_data['dados'].get('leads', []):
                if lead.get('assinatura', {}).get('token') == token:
                    try:
                        pdf_antigo = lead['assinatura']['arquivo_pdf']
                        caminho_payload = os.path.join(app.config['PASTA_UPLOADS'], pdf_antigo + ".json")
                        
                        if not os.path.exists(caminho_payload):
                            return jsonify({"status": "erro", "mensagem": "Dados do contrato perdidos."}), 404
                            
                        with open(caminho_payload, 'r', encoding='utf-8') as f:
                            dados_contrato = json.load(f)

                        # SALVA O CARIMBO DO CLIENTE
                        caminho_img_cliente = os.path.join(app.config['PASTA_UPLOADS'], f"cliente_{token}.png")
                        with open(caminho_img_cliente, "wb") as fh:
                            fh.write(base64.b64decode(img_b64))
                        
                        ip_cliente = request.remote_addr
                        data_hora = datetime.now().strftime("%d/%m/%Y as %H:%M:%S")
                        novo_nome_pdf = f"Contrato_Assinado_e_Validado_{token}.pdf"
                        caminho_novo_pdf = os.path.join(app.config['PASTA_UPLOADS'], novo_nome_pdf)
                        
                        empresa = db.get('empresa_config', {})
                        # RECRIANDO O PDF COM A ASSINATURA DO CLIENTE E O CARIMBO DA LOJA
                        criar_pdf_documento(dados_contrato, empresa, caminho_novo_pdf, 
                                            assinatura_cliente=caminho_img_cliente, 
                                            usa_carimbo_loja=True, 
                                            selo_ip=ip_cliente, 
                                            selo_data=data_hora)
                        
                        # ATUALIZAR STATUS
                        lead['assinatura']['status'] = 'Assinado'
                        lead['assinatura']['arquivo_pdf'] = novo_nome_pdf
                        lead['status'] = 'contrato_assinado'
                        lead['phase'] = 'executivo'
                        
                        # INJETAR PDF FINAL NA FICHA DO CLIENTE
                        if 'files' not in lead: lead['files'] = []
                        lead['files'].append({
                            "name": "Contrato_Assinado_e_Validado.pdf",
                            "savedName": novo_nome_pdf,
                            "icon": "fa-file-signature text-emerald-500",
                            "path": ""
                        })

                        if 'history' not in lead: lead['history'] = []
                        lead['history'].insert(0, {
                            'date': datetime.now().isoformat(),
                            'text': f"✅ Contrato LIDO E ASSINADO Digitalmente pelo cliente! O arquivo final foi anexado à ficha. IP: {ip_cliente}"
                        })
                        salvar_banco(db)
                        
                        email_cliente = lead.get('negociacao',{}).get('dados',{}).get('email','')
                        threading.Thread(target=enviar_email_contrato, args=(email_cliente, lead.get('name'), caminho_novo_pdf)).start()
                        
                        return jsonify({"status": "sucesso"})
                    except Exception as e:
                        print(str(e))
                        return jsonify({"status": "erro", "mensagem": str(e)}), 500

    return jsonify({"status": "erro", "mensagem": "Lead não encontrado"}), 404

# ==============================================================
# OUTROS ENDPOINTS (DRIVE, UPLOAD, CHAT, ROLETA)
# ==============================================================
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
    url_acesso = "http://localhost:5000"
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
    tk.Label(janela, text="⚠️ Feche as abas antigas do 'Live Server'. Use apenas o botão acima.", font=font.Font(family="Helvetica", size=10), fg="#ef4444", bg="#0f172a").pack(side="bottom", pady=20)
    janela.mainloop()