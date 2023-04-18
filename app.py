import os
import requests
import telegram
import shutil
import asyncio
import logging
import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler

from telegram import Bot, Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackContext, Dispatcher, Filters
from telegram.error import TelegramError

TELEGRAM_API_KEY = os.environ["TELEGRAM_API_KEY"]
TELEGRAM_ADMIN_ID = os.environ["TELEGRAM_ADMIN_ID"]
TELEGRAM_BOT_ID = os.environ["TELEGRAM_BOT_ID"]

GOOGLE_SHEETS_CREDENTIALS = os.environ["GOOGLE_SHEETS_CREDENTIALS"]
with open("credenciais.json", mode="w") as arquivo:
  arquivo.write(GOOGLE_SHEETS_CREDENTIALS)
  
conta = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json")
api = gspread.authorize(conta)
planilha = api.open_by_key('1eIEraunbWiChEgcgIVfGjdFkFaw2ZWAnNAaPAIopgrY')
sheet = planilha.worksheet('Subscribers')

# Criando a rota da aplicação Flask
app = Flask(__name__)
# Configurando o webhook
app.config.from_object(__name__)

# Configurando o bot e o dispatcher
bot = Bot(token=TELEGRAM_API_KEY)
dispatcher = Dispatcher(bot, None, workers=0)

def raspar_vagas():
    link = 'https://workingincontent.com/content-jobs/'
    requisicao = requests.get(link)
    html = BeautifulSoup(requisicao.content, 'html.parser')

    bloco = html.findAll('div', {'class': 'jobs ajax-jobs-container'})[0]
    jobs = bloco.findAll('div', {'class': ['job-card  salary-transparency', 'job-card  ', 'job-card featured ', 'job-card featured salary-transparency']})

    vagas = []
    for x in jobs:
        titulo = x.find('a', {'class': 'job-title'}).text + ' | '
        empresa = x.find('span', {'class': 'company-name'}).text + ' | '
        categoria = x.find('span', {'class': 'job-detail category-name'}).text + ' | '
        publicacao = x.find('span', {'class': 'job-date'}).text.strip().replace('Yesterday', 'Ontem').replace('Today', 'Hoje').replace('th', '').replace('Featured', 'Patrocinado') + ' | '
        detalhes = x.find('span', {'class': 'job-details'}).text.replace(categoria, '').strip().replace('\n', ' - ') + ' | '
        link = 'https://workingincontent.com' + x.find('a', {'class': 'job-title'}).get('href') + ' // '
        vagas.append([titulo, empresa, categoria, publicacao, detalhes, link, '\n'])
        
    vagas_separadas = []
    for lista_interna in vagas:
        vagas_separadas.append(' '.join(lista_interna))

    vagas_final = '\n'.join(vagas_separadas)

    # Salvando as vagas da semana atual
    with open('vagas_da_semana.txt', 'w') as f:
        for item in vagas_final:
            f.write("%s\n" % item)
    return vagas_final
        
def get_chat_id_by_username(username):
    rows = sheet.get_all_values()
    for row in rows[1:]:
        if row[1] == username:
            return row[0]  # Retorna o chat_id associado ao username
    return None

def get_chat_ids():
    chat_ids = []
    rows = sheet.get_all_values()
    for row in rows[1:]:
        chat_ids.append(row[0])  # Adiciona o chat_id à lista
    return chat_ids
    
    
def enviar_vagas(bot: Bot):
    try:
        # Lê vagas da semana atual
        with open("vagas_da_semana.txt", "r") as f:
            vagas_semana_atual = f.read().splitlines()

        # Lê vagas da semana anterior
        try:
            with open("vagas_semana_anterior.txt", "r") as f:
                vagas_semana_anterior = f.read().splitlines()
        except FileNotFoundError:
            vagas_semana_anterior = []

        # Compara as vagas da semana atual com as da semana anterior
        vagas_novas = []
        for vaga in vagas_semana_atual:
            if hashlib.sha256(vaga.encode('utf-8')).hexdigest() not in [hashlib.sha256(v.encode('utf-8')).hexdigest() for v in vagas_semana_anterior]:
                vagas_novas.append(vaga)

        # Verifica se há vagas novas e envia as mensagens apropriadas para os usuários cadastrados na planilha
        for row in sheet.get_all_values()[1:]:
            chat_id = row[2]  # Obtém o chat_id a partir da planilha
            if vagas_novas:
                vagas_texto = "\n\n".join(vagas_novas)
                bot.send_message(chat_id=chat_id, text=f"Olá! Seguem as vagas novas desta semana:\n\n{vagas_texto}")
            else:
                bot.send_message(chat_id=chat_id, text="Não há vagas novas nesta semana. Mas não desanima, o que é teu tá guardado.")

    except Exception as e:
        bot.send_message(chat_id=TELEGRAM_ADMIN_ID, text="Desculpe, rolou um erro ao buscar as vagas. Guenta aí, robôzinhos também erram.")
        print(str(e))
        
    shutil.move("vagas_da_semana.txt", "vagas_semana_anterior.txt")  # Movendo os arquivos para que possamos compará-los semana a semana
    
# Configurando o webhook do Telegram
def set_webhook():
    bot_token = os.getenv('TELEGRAM_API_KEY')
    bot = Updater(bot_token, use_context=True).bot
    app_url = 'https://site-teste-luana.onrender.com/telegram-bot'
    webhook_url = f'{app_url}:{os.getenv("PORT")}/{bot_token}'
    return bot.set_webhook(url=webhook_url)  
  
def agendar_raspagem():
    scheduler = BackgroundScheduler()
    scheduler.add_job(raspar_vagas, 'interval', weeks=1)
    scheduler.add_job(lambda: enviar_vagas(bot), trigger="interval", days=7, start_date=datetime.datetime.now())
    scheduler.start()

agendar_raspagem()
set_webhook()
    
# Criando a parte visual com HTML

menu = """
<a href="/">Página inicial</a> | <a href="/inscrever">Receba vagas de Content</a>
<br>
"""

inscrever_html = """
<html>
  <div class="container">
    <h1>{{title}}</h1>
    <p>{{subtitle}}</p>
    <form method="post" action="/inscrever">
      <div class="form-group">
        <label for="name">Seu nome</label>
        <input type="text" class="form-control" id="name" name="name" required>
      </div>
      <div class="form-group">
        <label for="username">Seu usuário do Telegram (com o '@')</label>
        <input type="text" class="form-control" id="username" name="username" required>
      </div>
      <button type="submit" class="btn btn-primary">Quero vaguinhas</button>
    </form>
    <a href="/">Voltar para a página inicial</a>
  </div>
</html>
"""

sucesso_html = """
<html>
  <body>
    <h1>Sucesso!</h1>
    <p>{{message}}</p>
  </body>
</html>
"""

erro_html = """
<html>
  <body>
    <h1>Erro!</h1>
    <p>{{message}}</p>
  </body>
</html>
"""

# Adicionando uma rota para a página inicial
@app.route("/")
def index():
    return menu + "Apenas mais um bot latino-americano tentando fazer o povo de Conteúdo encontrar oportunidades. Se inscreva e ganhe o mundo mais cedo do que Belchior."

# Adicionando uma rota para o formulário de inscrição de usuários
@app.route("/inscrever", methods=["GET", "POST"])
def inscrever():
    try:
        if request.method == "POST":
            name = request.form["name"]
            username = request.form["username"]

            # Verificando se o username já está cadastrado
            usernames_cadastrados = sheet.col_values(2)[1:]
            if username in usernames_cadastrados:
                return menu + render_template_string(erro_html, message="Você já se cadastrou pras vaguinhas! Agora é só aguardar as atualizações no seu Telegram.")

            # Inserindo nova linha na planilha com as informações do novo usuário
            row = [name, username]
            sheet.append_row(row)

            return menu + render_template_string(sucesso_html, message="Se prepare para receber vaguinhas de um jeito prático semanalmente.")

        return menu + render_template_string(inscrever_html, title="Quer receber vagas de Content semanalmente?", subtitle="Inscreva-se e receba as vagas mais interessantes do mercado semanalmente. Vou enviar as mensagens pra você pelo Telegram @robo_de_lua_bot.")

    except:
        return menu + render_template_string(erro_html, message="Poxa, não consegui processar as informações. Tente novamente mais tarde.")

      
# Lidando com as mensagerias no Telegram

def get_usernames_from_spreadsheet():
    usernames_cadastrados = sheet.col_values(2)[1:]
    return usernames_cadastrados  

  
def get_vagas_novas():
    try:
        with open("vagas_da_semana.txt", "r") as f:
            vagas_semana_atual = f.read().splitlines()

        with open("vagas_semana_anterior.txt", "r") as f:
            vagas_semana_anterior = f.read().splitlines()
    except FileNotFoundError:
        vagas_semana_anterior = []

    vagas_novas = []
    for vaga in vagas_semana_atual:
        if hashlib.sha256(vaga.encode('utf-8')).hexdigest() not in [hashlib.sha256(v.encode('utf-8')).hexdigest() for v in vagas_semana_anterior]:
            vagas_novas.append(vaga)

    return vagas_novas
  
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    username = update.message.from_user.username

    if username in get_usernames_from_spreadsheet():
        context.bot.send_message(chat_id=update.effective_chat.id, text="Olá! Para ver as vagas disponíveis, envie 'vagas'.")
    else:
        reply_markup = telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("Inscreva-se aqui", url="https://site-teste-luana.onrender.com/inscrever")]])
        context.bot.send_message(chat_id=update.effective_chat.id, text="Olá! Se inscreva para receber vagas em Conteúdo semanalmente.", reply_markup=reply_markup)

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    username = update.message.from_user.username

    if chat_id not in get_chat_ids():
        context.bot.send_message(chat_id=update.effective_chat.id, text="Você ainda não está cadastrado para receber vagas. Cadastre-se no site para começar a receber!")
    else:
        if not update.message:
            return

        message_text = update.message.text
        if message_text == "vagas" or message_text == "Vagas":
            vagas_novas = get_vagas_novas()
            message = "\n\n".join(vagas_novas) if vagas_novas else "Não há novas vagas no momento. Verifique novamente mais tarde ou aguarde as próximas atualizações semanais."
            context.bot.send_message(chat_id=update.effective_chat.id, text="Olha o bonde da vaguinha passando:\n\n{}".format(message))
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Desculpe, não entendi o que você quis dizer. Por favor, envie 'vagas' para ver as vagas disponíveis.")

# Adicionando o handler ao dispatcher
dispatcher.run_async = True
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))  

# Agendando o envio de vagas
scheduler = BackgroundScheduler()
scheduler.start()

@app.route('/telegram-bot', methods=['POST'])
def webhook_handler():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
    return 'ok'

if __name__ == '__main__':
    app.run
