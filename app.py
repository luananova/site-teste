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
    
# Se o usuário chegar primeiro ao bot do que ao site, levá-lo para o site para se inscrever
def start(update, context):
    message = "message = "Olá! Se inscreva [aqui](https://site-teste-luana.onrender.com/inscrever) para receber vagas em Conteúdo semanalmente."
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

# Adicionando uma função para ler as informações dos usuários da planilha do Google Sheets  
def get_usernames():
    usernames = sheet.col_values(2)[1:]
    return usernames

# Criando a função enviar_vagas para enviar somente as vagas novas da semana atual para os usuários
def enviar_vagas():
    try:
        # Lê vagas da semana atual
        with open("vagas_da_semana.txt", "r") as f:
            vagas_semana_atual = f.read().splitlines()

        # Lê vagas da semana anterior
        with open("vagas_semana_anterior.txt", "r") as f:
            vagas_semana_anterior = f.read().splitlines()

        # Compara as vagas da semana atual com as da semana anterior
        vagas_novas = []
        for vaga in vagas_semana_atual:
            if hashlib.md5(vaga.encode('utf-8')).hexdigest() not in [hashlib.md5(v.encode('utf-8')).hexdigest() for v in vagas_semana_anterior]:
                vagas_novas.append(vaga)

        # Verfica se há vagas novas e envia as mensagens apropriadas
        usernames = get_usernames()        
        if vagas_novas:
            vagas_texto = "\n\n".join(vagas_novas)
            for username in usernames:
                bot.send_message(chat_id=username, text=f"Olá! Seguem as vagas novas desta semana:\n\n{vagas_texto}")
        else:
            for username in usernames:
                bot.send_message(chat_id=chat_username, text="Não há vagas novas nesta semana. Mas não desanima, o que é teu tá guardado.")

    except Exception as e:
        bot.send_message(chat_id=chat_username, text="Desculpe, rolou um erro ao buscar as vagas. Guenta aí, robôzinhos também erram.")
        print(str(e))
            
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
    try:
        if request.method == "POST":
            name = request.form["name"]
            username = request.form["username"]

            # Verificando se o username já está cadastrado
            usernames_cadastrados = sheet.col_values(2)[1:]
            if username in usernames_cadastrados:
                return render_template("error.html", message="Ei, você já se cadastrou pras vaguinhas!")

            # Inserindo nova linha na planilha com as informações do novo usuário
            row = [name, username]
            sheet.append_row(row)

            return render_template("success.html", message="Boa, se prepare para receber vaguinhas de um jeito prático semanalmente.")

        return render_template("inscrever.html", title="Quer receber vagas de Content semanalmente?", subtitle="Inscreva-se e receba as vagas mais interessantes do mercado semanalmente via Telegram.")

    except:
        return render_template("error.html", message="Poxa, não consegui processar as informações. Tente novamente mais tarde.")

# Adicionando uma rota para a página inicial
@app.route("/")
def index():
    return "Apenas mais um bot latino-americano tentando fazer o povo de Conteúdo encontrar oportunidades. Se inscreva e ganhe o mundo mais cedo do que Belchior."

  
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
      

# Criando a função principal que vai rodar a raspagem de vagas, comparar com as vagas da semana anterior e enviar as vagas novas para os usuários. Essa função deve ser chamada semanalmente, utilizando o BackgroundScheduler.
def main():
    # Raspagem de vagas
    vagas_da_semana = raspar_vagas()

    # Ler vagas da semana anterior
    with open("vagas_da_semana_anterior.txt", "r") as f:
        vagas_da_semana_anterior = f.read()

    # Comparar vagas e salvar as novas
    vagas_novas = comparar_vagas(vagas_da_semana, vagas_da_semana_anterior)

    # Enviar vagas novas para usuários
    enviar_vagas_novas()

    # Salvar as vagas da semana atual para comparar na próxima semana
    with open("vagas_da_semana_anterior.txt", "w") as f:
        f.write(vagas_da_semana)

# Finalmente, agendando a execução da função principal semanalmente
if __name__ == "__main__":
    # Agendando a função principal para rodar toda segunda-feira às 10:00
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=main, trigger="cron", day_of_week="mon", hour=10, minute=0)
    scheduler.start()

    # Iniciando o bot do Telegram
    updater = Updater(token=TELEGRAM_API_KEY)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

  
  <!DOCTYPE html>
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
