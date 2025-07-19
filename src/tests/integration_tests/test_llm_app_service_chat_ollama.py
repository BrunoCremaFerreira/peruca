"""
UserAppService Unit Test
"""

import os
from unittest.mock import patch
import pytest

from application.appservices.view_models import ChatRequest, UserAdd
from infra.ioc import get_llm_app_service, get_user_app_service
from infra.settings import Settings


DB_PATH = "/home/brn/tests/data/tests.db"
@patch.dict(os.environ, {
    "CORS_ORIGIN": "http://localhost:3000",
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://10.10.1.10:11434",
    "LLM_PROVIDER_API_KEY": "fake-api-key",
    "LLM_MAIN_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_MAIN_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_ONLY_TALK_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_ONLY_TALK_GRAPH_CHAT_TEMPERATURE": "0.5",
    "CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0",
    "PERUCA_DB_CONNECTION_STRING": f"sqlite://{DB_PATH}",
})

def setup_app_service():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return get_llm_app_service(), get_user_app_service()

#=====================================
# OnlyTalking Classification Only
#=====================================
def test_chat_only_talking_greetings():
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    message = "Olá Peruca!"

    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    assert "intent': ['only_talking']" in response
    assert "smart_home_lights" not in response
    assert "smart_home_security_cams" not in response
    assert "shopping_list" not in response

@pytest.mark.parametrize("message", [
    "A luz do sol hoje tá tão bonita que nem preciso acender nada.", 
    "Estava pensando em trocar as lâmpadas da sala por umas mais econômicas.",
    "Você sabia que as luzes de LED duram muito mais do que as incandescentes?",
    "Ontem eu deixei a luz da cozinha acesa a noite toda sem querer.",
    "Meu amigo instalou luzes inteligentes em casa, achei incrível.",
    "Sonhei que as luzes da casa acendiam sozinhas quando eu chegava.",
    "Luzes coloridas dão um clima especial, né?",
    "Vi uma promoção de fitas de LED, acho que vou comprar.",
    "A iluminação da minha sala tá péssima, preciso mudar isso.",
    "Se as luzes falassem, o que será que diriam?",
    "Você acha que vale a pena automatizar as luzes da casa toda?",
    "Minha planta fica mais bonita quando deixo perto da janela com bastante luz natural.",
    "Luz baixa me dá sono, por isso gosto de ambientes bem iluminados.",
    "Estava pensando em pintar a parede para refletir melhor a luz.",
    "Quando eu era criança, tinha medo do escuro e dormia com a luz acesa.",
    "Achei incrível como as luzes mudam o ambiente no filme que vi ontem.",
    "Tem gente que coloca luz embaixo da cama pra dar um clima futurista.",
    "Você já viu aquelas casas que sincronizam luzes com música de Natal?",
    "Minha avó dizia que luz forte espanta os maus espíritos.",
    "Estava lembrando de quando faltou luz e a gente teve que jantar à luz de velas."
])
def test_chat_only_talking_not_home_lights(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    assert "intent': ['only_talking']" in response
    assert "smart_home_lights" not in response
    assert "smart_home_security_cams" not in response
    assert "shopping_list" not in response


@pytest.mark.parametrize("message", [
    "Estava lembrando de quando minha mãe esquecia sempre de comprar o leite.",
    "Você também acha que a gente sempre esquece alguma coisa no mercado?",
    "Minha lista de compras vive ficando enorme, mesmo sem eu querer.",
    "Fico impressionado com o preço dos ovos hoje em dia.",
    "Toda vez que passo no mercado, acabo comprando o que não preciso.",
    "Lembro que na infância a gente usava papelzinho pra anotar a lista de compras.",
    "Acho engraçado como a gente sempre compra pão mesmo quando diz que vai evitar.",
    "Vi uma promoção de arroz ontem, mas acabei não comprando.",
    "Você sabia que a palavra 'lista' vem do francês antigo?",
    "Minha avó sempre dizia: nunca vá ao mercado com fome.",
    "Se eu tivesse feito a lista antes, teria lembrado do detergente.",
    "Ficar sem café em casa é desesperador, né?",
    "É curioso como frutas ficam mais caras no inverno.",
    "Toda vez que vejo uma prateleira cheia, lembro da crise de 2020.",
    "Amanhã é dia de feira, sempre tem cheiro bom de fruta no ar.",
    "Meu gato fica maluco quando ouve o som do saco de ração.",
    "Já reparou como supermercados tocam músicas lentas pra gente comprar mais?",
    "A última vez que comprei sabão em pó, peguei a marca errada.",
    "É incrível como a gente acumula coisas inúteis na despensa.",
    "Às vezes penso em como seria viver sem precisar fazer compras."
])
def test_chat_only_talking_not_shopping_list(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    assert "intent': ['only_talking']" in response
    assert "smart_home_lights" not in response
    assert "smart_home_security_cams" not in response
    assert "shopping_list" not in response

@pytest.mark.parametrize("message", [
    "Vi um vídeo engraçado da câmera de segurança de uma loja, parecia cena de filme.",
    "Lembrei da época em que câmera era coisa só de banco.",
    "Já pensou se as câmeras tivessem sentimentos sobre o que veem?",
    "A câmera do meu celular tá melhor que muita câmera profissional hoje em dia.",
    "Sempre me sinto observado quando vejo aquelas câmeras em praça pública.",
    "Tem gente que acha que só porque tem câmera está tudo seguro.",
    "Vi um passarinho pousar bem em frente à câmera da portaria ontem, ficou fofo.",
    "Acho meio assustador quando as câmeras giram sozinhas.",
    "Meu cachorro late sempre que vê o reflexo da câmera de vigilância.",
    "Antigamente era comum colocar câmera só quando algo ruim acontecia.",
    "Assistir gravações antigas às vezes traz umas boas lembranças.",
    "O pessoal do condomínio vive discutindo onde colocar câmera, mas nunca resolve.",
    "Estava vendo um documentário sobre vigilância urbana, é assustador.",
    "As câmeras capturaram a neblina de manhã, parecia cena de terror.",
    "Toda vez que passo pela portaria fico tentando não olhar pra câmera.",
    "A câmera da entrada está apontada para uma árvore cheia de flores agora.",
    "Você já viu aquelas câmeras antigas com fita cassete? Eram enormes!",
    "Lembrei de um vídeo que viralizou com uma câmera pegando um gato roubando sapato.",
    "Parece que hoje tudo é filmado, até espirro em público.",
    "Se as câmeras pudessem falar, contariam cada história inacreditável..."
])
def test_chat_only_talking_not_smart_home_security_cams(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    assert "intent': ['only_talking']" in response
    assert "smart_home_lights" not in response
    assert "smart_home_security_cams" not in response
    assert "shopping_list" not in response     