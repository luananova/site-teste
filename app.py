import os
import requests
import hashlib

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

TELEGRAM_API_KEY = os.environ["TELEGRAM_API_KEY"]
TELEGRAM_ADMIN_ID = os.environ["TELEGRAM_ADMIN_ID"]

GOOGLE_SHEETS_CREDENTIALS = os.environ["GOOGLE_SHEETS_CREDENTIALS"]
with open("credenciais.json", mode="w") as arquivo:
  arquivo.write(GOOGLE_SHEETS_CREDENTIALS)
  
conta = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json")
api = gspread.authorize(conta)
planilha = api.open_by_key('1eIEraunbWiChEgcgIVfGjdFkFaw2ZWAnNAaPAIopgrY')
sheet = planilha.worksheet('Subscribers')

bot = Bot(token=TELEGRAM_API_KEY)

app = Flask(__name__)

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
  
# Salvando o resultado em um arquivo txt para efeito comparativo posterior e prevenção de duplicidades
with open("vagas_da_semana.txt", "w") as f:
    f.write(vagas_final)

# Adicionando uma função para ler as informações dos usuários da planilha do Google Sheets  
def get_users():
    users = sheet.get_all_records()
    return users

# Criando a função enviar_vagas para enviar somente as vagas novas da semana atual para os usuários
def enviar_vagas(update: Update, context: CallbackContext):
    # Ler vagas da semana atual
    with open("vagas_da_semana.txt", "r") as f:
        vagas_semana_atual = f.read().splitlines()

    # Ler vagas da semana anterior
    with open("vagas_semana_anterior.txt", "r") as f:
        vagas_semana_anterior = f.read().splitlines()

    # Compara as vagas da semana atual com as da semana anterior
    vagas_novas = []
    for vaga in vagas_semana_atual:
        if hashlib.md5(vaga.encode('utf-8')).hexdigest() not in [hashlib.md5(v.encode('utf-8')).hexdigest() for v in vagas_semana_anterior]:
            vagas_novas.append(vaga)

    # Envia as vagas novas para os usuários
    users = get_users()
    for user in users:
        chat_id = user["Chat ID"]
        for vaga in vagas_novas:
            bot.send_message(chat_id=chat_id, text=vaga)
            
# Criando uma função para agendar a execução da função raspar_vagas() e atualizar os arquivos de vagas semanalmente
def agendar_raspagem():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=raspar_vagas, trigger="interval", days=7)
    scheduler.add_job(func=atualizar_vagas_semanais, trigger="interval", days=7)
    scheduler.start()

# Adicionando uma função para atualizar as vagas semanais
def atualizar_vagas_semanais():
    # Ler vagas da semana atual
    with open("vagas_da_semana.txt", "r") as f:
        vagas_semana_atual = f.read()

    # Salva as vagas da semana atual para comparar na próxima semana
    with open("vagas_semana_anterior.txt", "w") as f:
        f.write(vagas_semana_atual)

# Adicionando uma rota para o formulário de inscrição de usuários
@app.route("/inscrever", methods=["GET", "POST"])
def inscrever():
    if request.method == "POST":
        chat_id = request.form["chat_id"]
        username = request.form["username"]
        name = request.form["name"]
        adicionar_usuario(chat_id, username, name)
        return render_template("sucesso.html")
    return render_template("inscrever.html", title="Quer receber vagas de Content semanalmente?", subtitle="É só informar seu usuário do Telegram e aguardar as mensagens do robôzinho com a curadoria.", button_text="Quero vagas"))

# Adicionando uma rota para a página inicial
@app.route("/")
def index():
    return "Apenas mais um bot latino-americano tentando fazer o povo de Conteúdo encontrar oportunidades. Se inscreva e ganhe o mundo mais cedo do que Belchior."

# Criando a função adicionar_usuario() para guardar os dados no Google Sheets
def adicionar_usuario(chat_id, username, name):
    try:
        sheet.append_row([chat_id, username, name])
    except:
        pass

# Modificando a função enviar_vagas() para utilizar o Google Sheets
def enviar_vagas(update: Update, context: CallbackContext):
    try:
        chat_id = update.message.chat_id
        nome = update.message.chat.first_name

        # Lendo as vagas da semana atual
        with open("vagas_da_semana.txt", "r") as f:
            vagas = f.read()

        if vagas:
            bot.send_message(chat_id=chat_id, text="Olá {}, seguem as vagas da semana:\n\n{}".format(nome, vagas))
        else:
            bot.send_message(chat_id=chat_id, text="Não há vagas novas nesta semana. Mas não desanima, o que é teu tá guardado.")
            
    except Exception as e:
    bot.send_message(chat_id=chat_id, text="Desculpe, rolou um erro ao buscar as vagas. Guenta aí, robôzinhos também erram.")
    print(str(e))

# Agora, vamos criar uma função para enviar as vagas novas para os usuários cadastrados. Essa função vai ser chamada no final da função que faz a comparação das vagas.
def enviar_vagas_novas():
    try:
        # Lendo as vagas da semana atual
        with open("vagas_da_semana.txt", "r") as f:
            vagas_semana_atual = f.read().split('\n')

        # Lendo as vagas da semana anterior
        with open("vagas_da_semana_anterior.txt", "r") as f:
            vagas_semana_anterior = f.read().split('\n')

        # Compara as vagas da semana atual com as da semana anterior
        vagas_novas = []
        for vaga in vagas_semana_atual:
            if hashlib.md5(vaga.encode('utf-8')).hexdigest() not in [hashlib.md5(v.encode('utf-8')).hexdigest() for v in vagas_semana_anterior]:
                vagas_novas.append(vaga)

        # Envia as vagas novas para os usuários
        if vagas_novas:
            for chat_id in sheet.col_values(1)[1:]:
                nome = sheet.cell(int(chat_id), 3).value
                bot.send_message(chat_id=chat_id, text="Olá {}, temos novas vagas disponíveis:\n\n{}".format(nome, '\n'.join(vagas_novas)))
        else:
            for chat_id in sheet.col_values(1)[1:]:
                bot.send_message(chat_id=chat_id, text="Não há vagas novas nesta semana. Mas não desanima, o que é teu tá guardado.")

        # Salva as vagas da semana atual para comparar na próxima semana
        with open("vagas_da_semana_anterior.txt", "w") as f:
            f.write('\n'.join(vagas_semana_atual))

    except Exception as e:
        for chat_id in sheet.col_values(1)[1:]:
            bot.send_message(chat_id=chat_id, text="Desculpe, rolou um erro ao buscar as vagas. Guenta aí, robôzinhos também erram.")
        print(str(e))


  
  <!DOCTYPE html>
<html>
  <head>
    <title>{{ title }}</title>
  </head>
  <body>
    <h1>{{ title }}</h1>
    <p>{{ subtitle }}</p>
    <form action="/inscrever" method="post">
      <input type="text" name="chat_id" placeholder="Seu ID do Telegram">
      <input type="text" name="username" placeholder="Seu nome de usuário do Telegram">
      <input type="text" name="name" placeholder="Seu nome">
      <button type="submit">{{ button_text }}</button>
    </form>
  </body>
</html>
