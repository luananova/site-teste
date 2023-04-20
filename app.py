import os
import json
import requests
import telegram
import asyncio
import logging
import datetime
import hashlib

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from google.cloud import storage
from google.api_core.exceptions import NotFound

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

# Carregando as credenciais do Google Cloud Storage
credentials_json = os.environ['GOOGLE_APPLICATION_CREDENTIALS']
credentials_info = json.loads(credentials_json)
credentials = Credentials.from_service_account_info(credentials_info)

client = storage.Client(credentials=credentials)

# Criando a rota da aplicação Flask
app = Flask(__name__)
# Configurando o webhook
app.config.from_object(__name__)

# Configurando o bot e o dispatcher
bot = Bot(token=TELEGRAM_API_KEY)
dispatcher = Dispatcher(bot, None, workers=2)

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
    
    return vagas_final
  
# Salvando as raspagens no Google Cloud Storage
def upload_to_gcs(bucket_name, vagas_final, client):
  bucket = client.get_bucket(bucket_name)
  blob_name = "vagas_da_semana.txt"
  my_data = vagas_final
  
  blob = bucket.blob(blob_name)
  blob.upload_from_string(my_data)

vagas_final = raspar_vagas()
bucket_name = "vagas"
upload_to_gcs(bucket_name, vagas_final, client)

def get_usernames_from_spreadsheet():
    usernames_cadastrados = sheet.col_values(2)[1:]
    return usernames_cadastrados   
  
def get_chat_ids():
    chat_ids = []
    rows = sheet.get_all_values()
    for row in rows[1:]:
        chat_ids.append(row[2])  # Adiciona o chat_id à lista, na coluna 3
    return chat_ids

def download_from_gcs(bucket_name, blob_name, client):
    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_text()
  
def enviar_vagas(bot: Bot):
    try:
        # Lê vagas da semana atual
        vagas_semana_atual = download_from_gcs("vagas", "vagas_da_semana.txt", client).splitlines()

        # Lê vagas da semana anterior
        try:
            vagas_semana_anterior = download_from_gcs("vagas", "vagas_semana_anterior.txt", client).splitlines()
        except NotFound: # google.api_core.exceptions.NotFound
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

    # Copiando o conteúdo do blob vagas_da_semana.txt para vagas_semana_anterior.txt
    content = download_from_gcs("vagas", "vagas_da_semana.txt", client)
    upload_to_gcs("vagas", content, "vagas_semana_anterior.txt", client)

def agendar_raspagem():
    scheduler = BackgroundScheduler()
    scheduler.add_job(raspar_vagas, 'interval', weeks=1)
    scheduler.add_job(lambda: enviar_vagas(bot), trigger="interval", days=7, start_date=datetime.datetime.now())
    scheduler.start()
    
# Configurando o webhook do Telegram
def set_webhook():
    bot = Updater(TELEGRAM_API_KEY, use_context=True).bot
    app_url = 'https://site-teste-luana.onrender.com/telegram-bot'
    webhook_url = f'{app_url}/{TELEGRAM_API_KEY}'
    return bot.set_webhook(url=webhook_url)

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
        <label for="username">Seu usuário do Telegram (sem o '@')</label>
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
    <h1>Legal, agora é só enviar uma mensagem para finalizar seu cadastro!</h1>
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
            
            return menu + render_template_string(sucesso_html, message='É só <a href="https://t.me/robo_de_lua_bot" target="_blank">acessar o bot</a>, mandar um Oi e aguardar as vagas! ;)')

        return menu + render_template_string(inscrever_html, title="Quer receber vagas de Content semanalmente?", subtitle="Inscreva-se e receba as vagas mais interessantes do mercado semanalmente. Vou enviar as mensagens pra você pelo Telegram @robo_de_lua_bot.")

    except:
        return menu + render_template_string(erro_html, message="Poxa, não consegui processar as informações. Tente novamente mais tarde.")
      
# Lidando com as mensagerias no Telegram
def get_chat_id_by_username(username):
    rows = sheet.get_all_values()
    for index, row in enumerate(rows[1:], start=2):  # Começa a contar a partir da linha 2, ignorando o cabeçalho
        if row[1] == username:
            return index  # Retorna o índice da linha onde o username foi encontrado
    return None
  
def update_chat_id(row_index, chat_id):
    sheet.update_cell(row_index, 3, chat_id)  # Atualiza a coluna 3 (chat_id) da linha especificada
  
def get_name_by_username(username):
    rows = sheet.get_all_values()
    for row in rows[1:]:
        if row[1] == username:
            return row[0]  # Retorna o nome na primeira coluna
    return None

def get_vagas_novas(bucket):
    # Baixar os blobs do Google Cloud Storage
    blob_semana_atual = bucket.blob("vagas_da_semana.txt")
    blob_semana_anterior = bucket.blob("vagas_semana_anterior.txt")

    # Ler o conteúdo dos blobs
    vagas_semana_atual = blob_semana_atual.download_as_text().splitlines()

    try:
        vagas_semana_anterior = blob_semana_anterior.download_as_text().splitlines()
    except google.api_core.exceptions.NotFound:
        vagas_semana_anterior = []

    vagas_novas = []
    for vaga in vagas_semana_atual:
        if hashlib.sha256(vaga.encode('utf-8')).hexdigest() not in [hashlib.sha256(v.encode('utf-8')).hexdigest() for v in vagas_semana_anterior]:
            vagas_novas.append(vaga)

    return vagas_novas

vagas_novas = get_vagas_novas(bucket, client)

def start(update: Update, context: CallbackContext):
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    chat_id = update.effective_chat.id

    # Verificando se o usuário já está cadastrado
    rows = sheet.get_all_values()
    user_exists = False
    row_number = 0
    for row in rows:
        row_number += 1
        if first_name in row and username in row:
            user_exists = True
            break

    if user_exists:
        # Verificando se o chat_id já está registrado
        if str(chat_id) == row[row_number - 1][2]:
            context.bot.send_message(chat_id=chat_id, text=f"Olá, {first_name}! Seu cadastro já foi realizado. Envie 'vagas' para ver as oportunidades disponíveis ou aguarde novas atualizações.")
        else:
            # Atualizando o chat_id na planilha
            sheet.update_cell(row_number, 3, chat_id)
            context.bot.send_message(chat_id=chat_id, text=f"Olá, {first_name}! Tudo certo com seu cadastro! Envie 'vagas' para ver as oportunidades disponíveis ou aguarde novas atualizações.")
    else:
        reply_markup = telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("Inscreva-se aqui", url="https://site-teste-luana.onrender.com/inscrever")]])
        context.bot.send_message(chat_id=update.effective_chat.id, text="Olá! Se inscreva para receber vagas em Conteúdo semanalmente.", reply_markup=reply_markup)

def handle_message(update: Update, context: CallbackContext):
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    chat_id = update.effective_chat.id

    # Verificando se o usuário já está cadastrado
    rows = sheet.get_all_values()
    user_exists = False
    row_number = 0
    for row in rows:
        row_number += 1
        if first_name in row and username in row:
            user_exists = True
            break

    if user_exists:
        if sheet.cell(row_number, 3).value:  # Verifica se o chat_id já está na planilha
            message_text = update.message.text.lower()
            if message_text == "vagas":
                vagas_novas = get_vagas_novas(bucket, client)
                message = "\n\n".join(vagas_novas) if vagas_novas else "Não há novas vagas no momento. Verifique novamente mais tarde ou aguarde as próximas atualizações semanais."
                context.bot.send_message(chat_id=chat_id, text="Olha o bonde da vaguinha passando:\n\n{}".format(message))
            else:
                context.bot.send_message(chat_id=chat_id, text=f"Oi de novo, {first_name}! Aguarde as novas mensagens ou envie 'vagas' para conferir se há atualizações.")
        else:
            sheet.update_cell(row_number, 3, chat_id)  # Atualiza o chat_id na planilha
            context.bot.send_message(chat_id=chat_id, text="Valeu, deu tudo certo! Agora é só aguardar as vagas de conteúdo chegarem semanalmente por aqui.")
    else:
        reply_markup = telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("Inscreva-se aqui", url="https://site-teste-luana.onrender.com/inscrever")]])
        context.bot.send_message(chat_id=chat_id, text="Você ainda não se cadastrou para receber vagas. Se inscreva no site para começar a receber!", reply_markup=reply_markup)      

# Adicionando o handler ao dispatcher
dispatcher.run_async = True
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))  

# Agendando o envio de vagas
scheduler = BackgroundScheduler()
scheduler.start()

@app.route(f'/telegram-bot/{TELEGRAM_API_KEY}', methods=['POST'])
def webhook_handler():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
    return 'ok'

if __name__ == '__main__':
    app.run
