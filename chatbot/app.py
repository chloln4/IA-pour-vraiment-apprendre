from flask import Flask, request, jsonify, render_template, session, send_from_directory
from flask_cors import CORS
from flask_session import Session
import os
import chatbot
from werkzeug.utils import secure_filename
from flask import make_response
from chatbot import (
    load_course, create_vectorstore,
    generate_question, check_answer, evaluate_mastery,
    append_to_raw_history, update_summary,
    extract_revision_intent, extract_keywords, correct_exercise,
    split_questions, generate_exercise,pertinence
  
)
current_course_text = None
app = Flask(__name__)
UPLOAD_FOLDER = './uploaded_courses'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
app.secret_key = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'
Session(app)

# Configuration initiale

@app.route('/')
def home():
    # Si un cours est déjà chargé, on affiche le chat
    if session.get('course_loaded'):
        return render_template('index.html')
    # Sinon on affiche la page d’accueil
    return render_template('accueil.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/api/init', methods=['POST'])
def init_conversation():
    """Réinitialise complètement la conversation"""
    session.clear()
    session['current_index'] = 0
    session['raw_history'] = []
    session['conversation_summary'] = ""
    session['step'] = 'intent'
    return jsonify({"status": "ok"})

current_vectorstore = None
current_chunks = None

@app.route('/upload_course', methods=['POST'])
def upload_course():
    global current_vectorstore, current_chunks
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier envoyé'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier invalide'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Charge le nouveau cours
    course_text = load_course(filepath)
    current_course_text = load_course(filepath)  # Ajouter cette ligne
    current_vectorstore, current_chunks = create_vectorstore(course_text)

    # Réinitialise la session et indique qu’un cours est chargé
    session.clear()
    session['course_loaded'] = True

    # Retourne un JSON explicite
    resp = make_response(jsonify({'status': 'ok'}), 200)
    return resp

@app.route('/reset_course', methods=['POST'])
def reset_course():
    global current_vectorstore, current_chunks
    # Vide la mémoire serveur
    current_vectorstore = None
    current_chunks = None

    # Vide la session utilisateur
    session.clear()
    # Indique qu’aucun cours n’est chargé
    session['course_loaded'] = False

    return jsonify({'status': 'ok'})

@app.route('/api/detect_intent', methods=['POST'])
def detect_intent():
    data = request.get_json()
    user_input = data.get('user_input', '')
    append_to_raw_history("Étudiant", user_input)
    
    intent = extract_revision_intent(user_input)
    session['intent'] = intent
    
    # initialisons toujours keywords à une chaîne vide
    session['keywords'] = ""
    
    if intent == 'particulier':
        keywords = extract_keywords(user_input)
        session['keywords'] = keywords
        
        if not keywords or keywords.lower() == 'aucun':
            session['step'] = 'clarify_keywords'
            return jsonify({
                "step": "clarify_keywords",
                "message": "Quelle partie spécifique souhaitez-vous réviser ?",
                "keywords": keywords
            })
    
    # cas "tout" ou mot-clé valide
    session['step'] = 'generate_question'
    return jsonify({
        "intent": intent,
        "keywords": session.get('keywords', "")
    })

@app.route('/api/clarify_keywords', methods=['POST'])
def clarify_keywords():
    try:
        data = request.get_json()
        user_input = data.get('user_input', '')
        append_to_raw_history("Étudiant", user_input)
        
        keywords = extract_keywords(user_input)
        if not keywords or keywords.lower() == 'aucun':
            return jsonify({
                "step": "clarify_keywords",
                "message": "Je n'ai pas compris. Pouvez-vous reformuler ?"
            })
        
        session['keywords'] = keywords
        session['step'] = 'generate_question'
        return jsonify({"status": "ok"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/get_question', methods=['GET'])
def get_question():
    try:
        if 'intent' not in session:
            return jsonify({"error": "Intent non détecté"}), 400
            
        if session['intent'] == 'tout':
            if 'current_index' not in session:
                session['current_index'] = 0
                
            if not current_chunks or session['current_index'] >= len(current_chunks):
                return jsonify({"status": "complete"})
            
            while session['current_index'] < len(current_chunks):
                passage_candidate = current_chunks[session['current_index']]
                session['current_index'] += 1

                if pertinence(passage_candidate):
                    passage = passage_candidate
                    break
            else:
                return jsonify({"status": "complete"})

        else:
            if 'keywords' not in session:
                return jsonify({"error": "Mots-clés manquants"}), 400
                
            results = current_vectorstore.similarity_search(session['keywords'], k=1)
            passage = results[0].page_content if results else None
        
        if not passage:
            return jsonify({"error": "Aucun passage trouvé"}), 404
        
        question = generate_question(passage)
        append_to_raw_history("Assistant", question)
        session['current_passage'] = passage
        
        return jsonify({
            "passage": passage,
            "question": question
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/check_answer', methods=['POST'])
def check_answer_route():
    try:
        data = request.get_json()
        user_answer = data.get('user_answer', '')
        passage = session.get('current_passage')
        
        if not passage:
            return jsonify({"error": "Aucun passage en cours"}), 400
        
        correction = check_answer(user_answer, passage)
        mastery = evaluate_mastery(user_answer, passage, correction)
        
        append_to_raw_history("Assistant", correction)
        update_summary()
        
        if not mastery and session['intent'] == 'tout':
            session['current_index'] -= 1
        
        return jsonify({
            "correction": correction,
            "mastery": mastery
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/append_history', methods=['POST'])
def append_history():
    try:
        data = request.get_json()
        append_to_raw_history(data['role'], data['content'])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/chat')
def chat_page():
    if not session.get('course_loaded'):
        return "Veuillez d'abord charger un cours via la page d'accueil.", 400
    return render_template('index.html')

# Ajouter ces routes après la route /api/check_answer dans app.py

@app.route('/api/generate_exercise', methods=['POST'])
def generate_exercise_route():
    try:
        # Récupérer le cours actuellement chargé
        global current_course_text
        if not current_course_text:
            return jsonify({"error": "Aucun cours chargé"}), 400

        # Générer l'exercice complet
        exercise = generate_exercise(current_course_text)
        if not exercise:
            return jsonify({"error": "Échec de génération de l'exercice"}), 500

        # Découper en questions individuelles
        questions = split_questions(exercise)
        if not questions:
            return jsonify({"error": "Échec du découpage des questions"}), 500

        # Stocker l'état dans la session
        session['current_exercise'] = {
            'full_text': exercise,
            'questions': questions,
            'current_index': 0
        }

        return jsonify({
            "exercise": exercise,
            "first_question": questions[0]
        }), 200, {'Content-Type': 'application/json'}

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/split_questions', methods=['POST'])
def split_questions_route():
    try:
        data = request.get_json()
        exercise_text = data.get('exercise_text', '')
        
        if not exercise_text:
            return jsonify({"error": "Texte d'exercice manquant"}), 400

        questions = split_questions(exercise_text)
        return jsonify({"questions": questions}), 200, {'Content-Type': 'application/json'}

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/correct_exercise', methods=['POST'])
def correct_exercise_route():
    try:
        data = request.get_json()
        user_answer = data.get('user_answer', '')
        question = data.get('question', '')
        
        if not user_answer or not question:
            return jsonify({"error": "Données manquantes"}), 400

        # Correction avec le contexte du cours
        correction = correct_exercise(user_answer, question)
        
        # Mise à jour de l'historique
        append_to_raw_history("Étudiant", f"Réponse à: {question} -> {user_answer}")
        append_to_raw_history("Assistant", correction)
        update_summary()

        return jsonify({
            "correction": correction,
            "next_question": session['current_exercise']['questions'].get(session['current_exercise']['current_index'] + 1)
        }), 200, {'Content-Type': 'application/json'}

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Ajouter cette route pour la navigation dans les questions
@app.route('/api/next_question', methods=['POST'])
def next_question_route():
    try:
        if 'current_exercise' not in session:
            return jsonify({"error": "Aucun exercice en cours"}), 400

        session['current_exercise']['current_index'] += 1
        current_index = session['current_exercise']['current_index']
        
        if current_index >= len(session['current_exercise']['questions']):
            return jsonify({"status": "complete"}), 200

        return jsonify({
            "question": session['current_exercise']['questions'][current_index]
        }), 200, {'Content-Type': 'application/json'}

    except Exception as e:
        return jsonify({"error": str(e)}), 500
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)