
import re
import spacy
from unidecode import unidecode
from infra.settings import Settings


settings = Settings()
nlp = spacy.load(settings.nlp_spacy_model)

def normalize(text):
    if not isinstance(text, str):
        return ""
    text = unidecode(text.lower())
    text = re.sub(r'\s+', ' ', text)  # Remove extra spaces
    text = re.sub(r'[^\w\s]', '', text)  # Remove acents
    return text.strip()


def get_lemmas_doc(text):
    normalized = normalize(text)
    return nlp(normalized)

def are_similar(text1, text2, threshold=0.9):
    """
    Check similarity between two strings by lemmas
    """
    if not text1 or not text2:
        return False
    doc1 = get_lemmas_doc(text1)
    doc2 = get_lemmas_doc(text2)
    return doc1.similarity(doc2) >= threshold
