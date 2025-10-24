# chatbot.py
import os
import pickle
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from PyPDF2 import PdfReader
from langchain_mistralai.chat_models import ChatMistralAI
import re

# --- Initialisation du LLM ---
api_key = "g8An28AzTzSaaou3T8KdNS3E4g1Sd3fw"
model = "mistral-small-latest"
client = ChatMistralAI(api_key=api_key, model=model)

# --- Variables globales pour la mémoire ---
conversation_summary = ""  # Résumé global de la conversation
raw_history = []           # Liste des 10 derniers messages bruts
current_index = 0          # Index courant pour le mode séquentiel

# --- Vectorstores ---
pedagogical_vectorstore = None
course_vectorstore = None
course_chunks = []

# --- Fonctions de gestion de l'historique ---
def append_to_raw_history(role, content):
    """Ajoute un message à l'historique et conserve les 10 derniers éléments"""
    global raw_history
    raw_history.append(f"{role}: {content}")
    if len(raw_history) > 10:
        raw_history = raw_history[-10:]

def get_context():
    """Construit le contexte combinant résumé et historique"""
    return (
        f"Résumé de la conversation: {conversation_summary}\n"
        f"Derniers échanges:\n" + "\n".join(raw_history)
    )

def update_summary():
    """Met à jour le résumé conversationnel"""
    global conversation_summary, raw_history
    if len(raw_history) < 10:
        return
    
    prompt = f"""Synthétise cet échange pédagogique en un résumé concis:
    {conversation_summary}
    Nouveaux échanges:
    {chr(10).join(raw_history)}
    """
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        conversation_summary = extract_response_content(response).strip()
        raw_history = []
    except Exception as e:
        print(f"Erreur mise à jour résumé: {e}")

# --- Fonctions principales améliorées ---
def generate_pedagogical_keywords():
    """Génère des mots-clés pédagogiques contextuels"""
    prompt = f"""Extraits des mots-clés pédagogiques pertinents de ce contexte:
{get_context()}
Réponds uniquement par des mots-clés séparés par des virgules."""
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        return extract_response_content(response).strip()
    except Exception as e:
        print(f"Erreur génération mots-clés: {e}")
        return ""

def get_pedagogical_context(query, k=1):
    """Récupère le contexte pédagogique pertinent"""
    try:
        results = pedagogical_vectorstore.similarity_search(query, k=k)
        return results[0].page_content if results else ""
    except Exception as e:
        print(f"Erreur recherche pédagogique: {e}")
        return ""

# --- Fonctions de génération de contenu ---

def generate_question(course_part):
    # Obtenir un extrait pédagogique pertinent pour enrichir le contexte.
    ped_context = get_pedagogical_context(generate_pedagogical_keywords(), k=1)
    prompt = f"""Tu es un assistant pédagogique expert qui aide un étudiant à mémoriser efficacement son cours. À partir de l'extrait suivant "{course_part}" : 

Formule **une seule question claire, courte et ciblée**, qui pousse l'étudiant à réfléchir et à mieux retenir ce contenu.

Consignes : 
-Ne pose **qu'une seule question**.
- Sois **direct** et **concis** (pas de contexte ou justification).
- Utilise le tutoiement et adresse-toi à l'étudiant de manière engageante.

Contexte de la conversation (résumé, derniers échanges, références pédagogiques) :
{get_context()}

Voici également un extrait d'un document expliquant des méthodes pédagogiques à appliquer :
{ped_context}
"""
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        question = extract_response_content(response)
        append_to_raw_history("Assistant", question)
        update_summary()
        return question
    except Exception as e:
        return f"Erreur lors de la génération de la question : {e}"
    
def correct_exercise(user_answer, question, course_text):
    prompt = f"""Tu es un assistant pédagogique. Voici les éléments à analyser :

- Question : "{question}"
- Réponse de l'étudiant : "{user_answer}"
- Extrait du cours à utiliser : "{course_text}"

Ta tâche :
- Dis si la réponse est correcte ou incorrecte.
- Donne une explication simple (1 ou 2 phrases) pour justifier cette évaluation.
- Si la réponse est partiellement correcte, précise ce qui manque.
- Donne un seul conseil utile et clair pour aider l’étudiant à mieux comprendre ce point du cours.
- Reste factuel, bienveillant, mais **ne félicite pas l'étudiant** s’il n’a pas encore bien répondu.

Contexte fourni (résumé global de la conversation et derniers échanges) :
{get_context()}
Réponds de manière concise et structurée.
"""
    
    try:
        response = client.invoke(prompt)
        correction = response.content.strip()
        append_to_raw_history("Assistant", correction)
        update_summary()
    
        return correction
    except Exception as e:
        print(f"Erreur lors de la correction de l'exercice : {e}")
        return "Impossible de corriger la réponse."
    
def split_questions(exercise_text):
    """
    Découpe l'exercice généré en liste de questions.
    Supposé que chaque question commence par un chiffre ou un tiret.
    """
    prompt = f"""Voici un exercice complet :{exercise_text}

Peux-tu extraire uniquement les énoncés des questions dans une **liste JSON**, sans les réponses, sans numérotation ni balises Markdown ?
Formate la sortie uniquement comme ceci :
[
  "Énoncé de la question 1",
  "Énoncé de la question 2",
  ...
]

"""
    try:
        response = client.invoke(prompt)
        json_text = response.content.strip()

        import json
        questions = json.loads(json_text)
        return questions
    except Exception as e:
        print(f"Erreur lors de l'extraction des questions : {e}")
        return []
    

def generate_exercise(course_text):
    ped_context = get_pedagogical_context(generate_pedagogical_keywords(), k=1)
    
    prompt = f"""Tu es un assistant pédagogique. Créer un exercice interactif et structuré en plusieurs parties 
    pour evaluer la compréhension complète en rapport avec le cours suivant :
"{course_text}"

Consignes : 

-Donne un titre général à l'exercice
- Créer une serie de 3 à 5 questions couvrant les differents aspects du cours. Ne donne pas de reponses.
- Utilise différents formats : QCM, vrai/faux, questions ouvertes, mini-cas pratiques.
- Les questions doivent être claires, simples, et adaptées à un étudiant.
- Commence par des questions faciles (mémorisation), puis plus complexes (compréhension, application).
- Ne donne **aucune réponse**, et **n'encourage pas l'étudiant**.

Contexte fourni (résumé global de la conversation, derniers échanges, et références pédagogiques) :
{get_context()}
Extrait pédagogique pertinent : {ped_context}
"""
    try:
        response = client.invoke(prompt)


        exercise = response.content.strip()
        append_to_raw_history("Assistant", exercise)
        update_summary()
        return exercise
    except Exception as e:
        print(f"Erreur lors de la génération de l'exercice : {e}")
        return None

def check_answer(user_answer, course_part):
    ped_context = get_pedagogical_context(generate_pedagogical_keywords(), k=1)
    prompt = f"""Tu es un assistant pédagogique. Voici un extrait du cours :
"{course_part}"

L'étudiant a répondu : "{user_answer}"

Analyse la réponse de façon factuelle et concise.

Consignes :
- Ne pose pas de nouvelle question.
- Dis si la réponse est correcte ou incorrecte : une réponse peut être correcte sans être totalement parfaite. (Exemple : si l'étudiant répond P=mg sans préciser que m est la masse et g la gravité, la réponse peut être considéré comme correcte)
- Explique en **5 phrases maximum** pourquoi.
- Ne fais pas de digression, ne répète pas le cours.
- Adresse-toi directement à l'étudiant.
- Ne sois pas trop stricte
- Il faut que tu sois toujours dans une démarche encourageante


Contexte de la conversation (résumé, derniers échanges, et références pédagogiques) :
{get_context()}
Voici un extrait de méthode pédagogique pour guider ta formulation : {ped_context}
"""
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        correction = extract_response_content(response)
        append_to_raw_history("Assistant", correction)
        update_summary()
        return correction
    except Exception as e:
        print(f"Erreur lors de la correction : {e}")
        return "Impossible de corriger la réponse."

# --- Fonctions utilitaires ---
def load_file_text(file_path):
    """Charge un fichier PDF/TXT"""
    if file_path.endswith(".pdf"):
        with open(file_path, "rb") as f:
            return "\n".join([page.extract_text() for page in PdfReader(f).pages])
    elif file_path.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    raise ValueError("Format non supporté")

def create_vectorstore(text):
    """Crée un vectorstore FAISS"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300, 
        chunk_overlap=50,
        separators=["\n\n", "\n", ". ", "! ", "? "]
    )
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    chunks = splitter.split_text(text)
    return FAISS.from_texts(chunks, embeddings), chunks

def load_course(file_path):
    """Charge un cours utilisateur (PDF ou TXT) dans la base."""
    return load_file_text(file_path)


def load_pedagogical_docs():
    """Concatène les textes des documents pédagogiques."""
    files = ["doc_rag/0610_staedeli_f.pdf", "doc_rag/demarche-2.pdf", "doc_rag/tutac-s3-06.pdf","doc_rag/Poly_Analogie.pdf"]
    all_text = ""
    for file in files:
        all_text += load_file_text(file) + "\n"
    return all_text

def evaluate_mastery(user_answer, course_part, feedback):
    prompt = f"""Tu es un assistant pédagogique. Évalue la compréhension de l'étudiant concernant l'extrait suivant du cours :
"{course_part}"
L'étudiant a répondu : "{user_answer}"
D'après ton analyse ("{feedback}"), indique simplement "oui" si l'étudiant a bien compris ou "non" s'il doit réviser ce passage.
Contexte fourni (résumé global de la conversation et derniers échanges) :
{get_context()}
"""
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        evaluation = extract_response_content(response).strip().lower()
        return evaluation.startswith("oui")
    except Exception as e:
        print(f"Erreur lors de l'évaluation de la compréhension : {e}")
        return False
    
def pertinence(course_part):
    prompt = f"""Tu es un assistant pédagogique. Ton rôle est de mieux faire maîtriser son cours à un étudiant. 
Voici un extrait du cours : "{course_part}"
Tu dois évaluer si cet extrait est pertinent pour l'étudiant.
Réponds par "oui" si l'extrait est pertinent pour l'étudiant, sinon réponds par "non".
Par exemple, si l'extrait présente un sommaire de la leçon, réponds par "non", car il n'apporte pas de valeur ajoutée.
De même si l'extrait parle des auteurs du cours, réponds par "non", car cela n'apporte pas de valeur ajoutée.
"""
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        evaluation = extract_response_content(response).strip().lower()
        return evaluation.startswith("oui")
    except Exception as e:
        print(f"Erreur lors de l'évaluation de la compréhension : {e}")
        return False
    
def extract_revision_intent(student_input):
    prompt = f"""Tu es un assistant pédagogique. Analyse le message suivant et déduis l'intention de l'étudiant.
Message : "{student_input}"
Si l'étudiant souhaite réviser l'intégralité du cours, réponds par "tout". S'il souhaite se concentrer sur une partie spécifique, réponds par "particulier".
Réponds uniquement par "tout" ou "particulier".
Contexte fourni (résumé global de la conversation et derniers échanges) :
{get_context()}
"""
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        intent = extract_response_content(response).strip().lower()
        return intent
    except Exception as e:
        print(f"Erreur lors de l'extraction de l'intention : {e}")
        return "tout"  # Par défaut

def extract_keywords(query):
    prompt = f"""Tu es un assistant pédagogique. Extrait de manière concise les mots-clés permettant d'identifier la section du cours à réviser à partir du message suivant : "{query}".
Réponds uniquement par les mots-clés, séparés par des virgules.
Si tu constates qu'il n'y a pas de mots-clés, réponds par "aucun".
Par exemple, si l'étidiant parle de simplement réviser une partie spécifique du cours sans spécifier laquelle, réponds par "aucun".
Voici le dernier message de l'étudiant : "{query}", base-toi essentiellement sur ce message pour extraire les mots-clés.
Contexte fourni (résumé global de la conversation et derniers échanges) :
{get_context()}
"""
    try:
        response = client.invoke([{"role": "user", "content": prompt}])
        keywords = extract_response_content(response).strip()
        return keywords
    except Exception as e:
        print(f"Erreur lors de l'extraction des mots-clés : {e}")
        return ""
def extract_response_content(response):
    """Extrait le contenu textuel d'une réponse"""
    return response.content if hasattr(response, "content") else str(response)

# --- Initialisation des ressources pédagogiques ---
def initialize_pedagogical_vectorstore():
    """Charge les documents pédagogiques de référence"""
    global pedagogical_vectorstore
    files = ["doc_rag/0610_staedeli_f.pdf", "doc_rag/demarche-2.pdf", "doc_rag/tutac-s3-06.pdf"]
    all_text = "\n".join(load_file_text(f) for f in files)
    pedagogical_vectorstore, _ = create_vectorstore(all_text)

# Initialisation au démarrage
initialize_pedagogical_vectorstore()