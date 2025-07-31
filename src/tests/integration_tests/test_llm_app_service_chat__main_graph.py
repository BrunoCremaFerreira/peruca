"""
UserAppService Unit Test - Main Graph Classification Tests
"""

import os
from unittest.mock import patch
import pytest

from application.appservices.view_models import ChatRequest
from domain.commands import UserAdd
from infra.ioc import get_llm_app_service, get_user_app_service
from infra.settings import Settings


DB_PATH = "/home/brn/tests/data/tests.db"
@patch.dict(os.environ, {
    "CORS_ORIGIN": "http://localhost:3000",
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://172.16.1.107:11434",
    "LLM_PROVIDER_API_KEY": "fake-api-key",
    "LLM_MAIN_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_MAIN_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_ONLY_TALK_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_ONLY_TALK_GRAPH_CHAT_TEMPERATURE": "0.5",
    "NLP_SPACY_MODEL": "pt_core_news_sm",
    "CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0",
    "PERUCA_DB_CONNECTION_STRING": f"sqlite://{DB_PATH}",
})

def setup_app_service():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return get_llm_app_service(), get_user_app_service()

#======================================================
# OnlyTalking Classification Only
#======================================================
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
    intents = response.get("intents")
    output = response.get("output")
    assert  intents == ["only_talking"]
    assert output

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
    intents = response.get("intents")
    output = response.get("output")
    assert  intents == ["only_talking"]
    assert output

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
    intents = response.get("intents")
    output = response.get("output")
    assert  intents == ["only_talking"]
    assert output

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
    intents = response.get("intents")
    output = response.get("output")
    assert  intents == ["only_talking"]
    assert output

#======================================================
# Smart Home Lights Classification Only
#======================================================

@pytest.mark.parametrize("message", [
    "Ligue a luz da sala.",
    "Apague as luzes do quarto.",
    "Aumente a intensidade da luz da cozinha.",
    "Diminua a iluminação do corredor.",
    "Mude a cor da luz da sala para azul.",
    "Deixe as luzes da varanda no modo noturno.",
    "Acenda todas as luzes da casa.",
    "Desligue as luzes da área externa.",
    "Coloque a luz da mesa em 50% de brilho.",
    "Ative o modo relax nas luzes da sala.",
    "Troque a cor das luzes do quarto para verde.",
    "Apague todas as luzes agora.",
    "Deixe a iluminação da cozinha mais quente.",
    "Configure a luz da sala para cor branca.",
    "Ligue apenas as luzes do banheiro.",
    "Coloque as luzes da casa no modo festa.",
    "Apague a luz da escada.",
    "Ative a luz da garagem.",
    "Mude a iluminação do escritório para modo leitura.",
    "Acenda a luz do jardim por 10 minutos."
])
def test_chat_smart_home_lights_only(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    intents = response.get("intents")
    output = response.get("output")
    assert  intents == ["smart_home_lights"]
    assert output

#======================================================
# Smart Home Security Classification Only
#======================================================

@pytest.mark.parametrize("message", [
    "Mostre a câmera da garagem.",
    "Quero ver a câmera da entrada agora.",
    "Ative a câmera do portão.",
    "Me mostra o que a câmera da sala está vendo.",
    "Ligue a câmera da varanda.",
    "O que a câmera do corredor está gravando neste momento?",
    "Exiba a gravação de hoje da câmera da frente.",
    "Consigo ver a imagem da câmera dos fundos agora?",
    "Verifique a câmera do quintal para mim.",
    "Quero revisar as imagens da câmera da cozinha.",
    "Me avise se a câmera detectar algum movimento.",
    "Tem algo sendo captado pela câmera do escritório?",
    "Mostre a última gravação da câmera da garagem.",
    "Abra o vídeo ao vivo da câmera do portão.",
    "A câmera do hall está online?",
    "Quero acessar a câmera da área externa.",
    "Ative a visualização noturna da câmera da frente.",
    "Consigo ver a câmera da entrada pelo celular?",
    "Quero ver o que as câmeras estão captando agora.",
    "A câmera detectou algum movimento esta noite?"
])
def test_chat_smart_home_security_cams_only(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    intents = response.get("intents")
    output = response.get("output")
    assert  intents == ["smart_home_security_cams"]
    assert output

#======================================================
# Shopping List Classification Only
#======================================================

@pytest.mark.parametrize("message", [
    "Adicione leite na minha lista de compras.",
    "Preciso comprar ovos e pão.",
    "Coloque arroz e feijão na lista, por favor.",
    "Adiciona sabão em pó na minha lista.",
    "Tira o macarrão da lista de compras.",
    "Quero lembrar de comprar café amanhã.",
    "Anota papel higiênico na lista.",
    "Acrescente queijo e presunto na lista.",
    "Me mostra o que tem na minha lista de compras.",
    "Pode colocar cenoura e batata na lista?",
    "Adicione ração para o cachorro na lista.",
    "Preciso comprar frutas e legumes.",
    "Coloca leite condensado e creme de leite na lista.",
    "Adiciona detergente e esponja na lista de compras.",
    "Remova refrigerante da lista.",
    "Verifique o que já tem na lista de mercado.",
    "Adiciona produtos de limpeza na lista.",
    "Preciso de sabonete e pasta de dente, adiciona aí.",
    "Coloca chocolate e biscoito na lista pra mim.",
    "Tira o açúcar da lista, já comprei."
])
def test_chat_shopping_list_only(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    intents = response.get("intents")
    output = response.get("output")
    assert  intents == ["shopping_list"]
    assert output

#======================================================
# Shopping List And Smart Home Lights
#======================================================

@pytest.mark.parametrize("message", [
    "Ligue a luz da cozinha e adicione arroz na lista.",
    "Apague as luzes da sala e coloque sabão em pó na lista de compras.",
    "Coloca leite na lista e acenda a luz do quarto.",
    "Quero que desligue as luzes e adicione papel toalha na lista.",
    "Acenda a luz da varanda e me lembre de comprar pão.",
    "Diminua a intensidade da luz e adicione café e açúcar na lista.",
    "Adicione frutas na lista e mude a cor da luz da sala para azul.",
    "Ative o modo noturno nas luzes e coloque leite condensado na lista.",
    "Acenda a luz do escritório e adicione canetas na lista.",
    "Adicione ração na lista e ligue as luzes da garagem.",
    "Quero comprar sabão líquido, e também acender a luz da lavanderia.",
    "Adiciona ovos e queijo na lista e muda a luz do quarto para cor quente.",
    "Apaga a luz do corredor e adiciona detergente na lista.",
    "Acende a luz do banheiro e coloca papel higiênico na lista.",
    "Coloque biscoitos na lista e ilumine melhor a cozinha.",
    "Ligue a iluminação principal e adicione shampoo e sabonete na lista.",
    "Acenda as luzes da casa e adicione velas e fósforos na lista.",
    "Desliga as luzes do andar de cima e adiciona vinho tinto na lista.",
    "Diminui a luz do ambiente e acrescenta suco de laranja na lista.",
    "Adiciona água com gás na lista e muda a luz da sala para o modo relax."
])
def test_chat_shopping_list_and_smart_home_lights(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    intents = response.get("intents")
    output = response.get("output")
    assert "shopping_list" in intents
    assert "smart_home_lights" in intents
    assert "only_talking" not in intents
    assert "smart_home_security_cams" not in intents
    assert output

#=============================================================
# Shopping List And Only Talking but Shopping List required
#=============================================================

@pytest.mark.parametrize("message", [
    "Acho que vou precisar de mais arroz essa semana, pode adicionar na lista?",
    "Ontem fiz uma lasanha deliciosa, preciso lembrar de comprar queijo.",
    "Falando nisso, coloca sabão em pó na lista porque o meu acabou.",
    "Nossa, como o tempo passou rápido... coloca café na lista pra mim?",
    "Fiquei pensando em fazer bolo no fim de semana, adiciona farinha e ovos aí.",
    "Estava lembrando da receita da minha avó, coloca leite condensado na lista.",
    "Depois daquela bagunça, preciso de mais papel toalha — adiciona na lista.",
    "Adiciona desinfetante na lista, essa casa precisa de um bom faxinão!",
    "Ontem sonhei que a geladeira estava vazia... coloca leite e iogurte na lista.",
    "Falando em churrasco, coloca carvão e linguiça na lista de compras.",
    "Essa semana foi corrida demais, adiciona miojo na lista.",
    "Me bateu uma vontade de cozinhar... coloca azeite e alho na lista.",
    "Você acredita que esqueci de comprar sabonete? Adiciona aí, por favor.",
    "Lembrei da festa do João — coloca refrigerante e salgadinho na lista.",
    "Fiquei com saudade da casa da minha mãe, coloca feijão preto na lista.",
    "Nossa, hoje tá um dia ótimo pra cozinhar... põe batata e cebola na lista.",
    "Fiquei sem ideias de almoço... adiciona macarrão e molho de tomate.",
    "Ontem fiz uma limpa na despensa, coloca arroz integral e óleo na lista.",
    "Lembrei que o vizinho recomendou aquele sabão, põe ele na lista também.",
    "Sabe aquele cheiro de bolo no forno? Me inspirou — coloca fermento na lista."
])
def test_chat_shopping_list_and_only_talking_bu_shopping_list_required(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    intents = response.get("intents")
    output = response.get("output")
    assert "shopping_list" in intents
    assert "smart_home_lights" not in intents
    assert "smart_home_security_cams" not in intents
    assert output

#======================================================
# Smart Home Security Cams And Smart Home Lights
#======================================================

@pytest.mark.parametrize("message", [
    "Acenda a luz da entrada e mostre a câmera da porta agora.",
    "Ligue as luzes do quintal e veja se a câmera captou algum movimento.",
    "Apague a luz da sala e mostre o que a câmera da sala está gravando.",
    "Quero ver a câmera da garagem e acender a luz de lá também.",
    "Mostre a câmera da cozinha e ligue as luzes do ambiente.",
    "Ligue a luz da frente e veja se tem alguém na câmera da entrada.",
    "Mude a cor da luz da varanda e abra a câmera do jardim.",
    "Apague as luzes externas e mostre a câmera do quintal.",
    "Acenda as luzes da garagem e veja se o portão está fechado na câmera.",
    "Ative as luzes do corredor e abra a câmera do andar de cima.",
    "Desligue as luzes da casa e me mostre a câmera da frente.",
    "Mostre a câmera da sala e ajuste a luz para o modo relax.",
    "Veja se há movimento na câmera dos fundos e acenda a luz lá.",
    "Ligue a luz da varanda e veja se a câmera detectou algo estranho.",
    "Mostre a câmera da escada e aumente a intensidade da luz no local.",
    "Quero ver a câmera da frente enquanto você acende a luz do portão.",
    "Abaixe a luz do quarto e abra a câmera do corredor.",
    "Ilumine o jardim e veja a última gravação da câmera de segurança.",
    "Desligue a luz da garagem e verifique se a câmera captou algo ontem à noite.",
    "Acenda as luzes do hall de entrada e mostre a visão da câmera nesse local."
])
def test_chat_smart_home_security_cams_and_smart_home_lights(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    intents = response.get("intents")
    output = response.get("output")
    assert "smart_home_security_cams" in intents
    assert "smart_home_lights" in intents
    assert "only_talking" not in intents
    assert "shopping_list" not in intents
    assert output