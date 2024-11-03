from flask import Flask
from flask_restx import Api  # type: ignore

app = Flask(__name__)

api = Api(
    app,
    version="1.0",
    title="Peruca LLM Assistant API",
    description="",
)


if __name__ == "__main__":
    app.run(debug=True)
