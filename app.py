import os
import requests
import telegram

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler

from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackContext

from dotenv import load_dotenv

load_dotenv()

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
bot.setWebhook(url='https://site-teste-luana.onrender.com/{}'.format(TELEGRAM_API_KEY))

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

    # Salvando as vagas da semana atual
    with open("vagas_da_semana.txt", "w") as f:
        f.write(vagas_final)
        
        
def enviar_vagas():
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
            if hashlib.md5(vaga.encode('utf-8')).hexdigest() not in [hashlib.md5(v.encode('utf-8')).hexdigest() for v in vagas_semana_anterior]:
                vagas_novas.append(vaga)

        # Verfica se há vagas novas e envia as mensagens apropriadas
        usernames = get_usernames_from_spreadsheet()
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

def get_usernames_from_spreadsheet():
    # Lê os usernames da planilha
    usernames = []
    for row in sheet.get_all_values()[1:]:
        usernames.append(row[1])
    return usernames

  
def agendar_envio_vagas():
    # Chama as funções para raspar as vagas e enviar para os usuários
    raspar_vagas()
    enviar_vagas()

    
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
def start(update: Update, context: CallbackContext) -> None:
    # Obtendo o username do usuário que enviou a mensagem
    username = get_username(update)
    
    # Mensagem de boas-vindas e opções de ação para usuários cadastrados
    if username in get_usernames_from_spreadsheet():
        context.bot.send_message(chat_id=update.effective_chat.id, text="Olá! Para ver as vagas disponíveis, envie 'vagas'.")
        
    # Mensagem para usuários não cadastrados
    else:
        reply_markup = telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("Inscreva-se aqui", url="https://site-teste-luana.onrender.com/inscrever")]])
        context.bot.send_message(chat_id=update.effective_chat.id, text="Olá! Se inscreva para receber vagas em Conteúdo semanalmente.", reply_markup=reply_markup)
      
      
def handle_message(update: Update, context: CallbackContext) -> None:
    # Obtendo o username do usuário que enviou a mensagem
    username = get_username(update)

    # Verificando se o usuário está cadastrado na planilha
    if username not in get_usernames_from_spreadsheet():
        context.bot.send_message(chat_id=update.effective_chat.id, text="Você ainda não está cadastrado para receber vagas. Cadastre-se no site para começar a receber!")
    else:
        # Verificando se o usuário enviou alguma mensagem
        if not update.message:
            return

        message_text = update.message.text
        if message_text == "vagas" or message_text == "Vagas":
            # Verificando se há vagas novas
            vagas_novas = comparar_vagas(raspar_vagas(), get_vagas_da_semana_anterior())
          
            # Enviando as vagas novas para o usuário
            message = "\n\n".join(vagas_novas) if vagas_novas else "Não há novas vagas no momento. Verifique novamente mais tarde ou aguarde as próximas atualizações semanais."
            context.bot.send_message(chat_id=update.effective_chat.id, text="Olha o bonde da vaguinha passando:\n\n{}".format(message))
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Desculpe, não entendi o que você quis dizer. Por favor, envie 'vagas' para ver as vagas disponíveis.")


if __name__ == "__main__":
    # Finalmente, o BOT
    dispatcher = Dispatcher(bot, None, workers=0)
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Configurando o webhook
    app.config.from_object(__name__)

    @app.route('/{}'.format(TELEGRAM_API_KEY), methods=['POST'])
    def webhook():
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
        return 'ok'

    # Iniciando a aplicação
    if 'DYNO' in os.environ:
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port)
    else:
        app.run(debug=True)

    # Agendando o envio de vagas
    scheduler = BackgroundScheduler()
    scheduler.add_job(agendar_envio_vagas, trigger='interval', days=7)
    scheduler.start()
