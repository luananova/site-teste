from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello_world():
  return "Olá, mundo! Esse é meu site. (Luana Nova)"
