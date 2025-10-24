# PRONTO 21 : IA pour vraiment apprendre

## Présentation du projet

L'objectif du projet est de permettre à un étudiant d'interagir avec un chatbot pour apprendre efficacement son cours. Le chatbot s'appuie sur le LLM de MistralAI pour générer des questions, corriger les réponses et proposer des exercices adaptés. Le projet met l'accent sur la compréhension réelle des notions, et non sur la simple restitution de connaissances.

## Structure du code

- **branche main**
  - **chatbot/** : dossier principal de l'application
    - **doc_rag/** : stocke les documents pédagogiques utilisés pour le RAG (Retrieval Augmented Generation)
    - **static/css/** : contient les fichiers de style CSS des pages du site
    - **static/js/** : contient les fichiers JavaScript du site
    - **template/** : contient les pages HTML du site
    - **uploaded_courses/** : dossier où sont stockés les PDF de cours déposés via le site web
    - **app.py** : fichier principal contenant les différentes routes Flask du site
    - **Chatbot.py** : contient les fonctions pour interagir avec le LLM de Mistral
    - **requirements.txt** : liste des bibliothèques Python nécessaires au fonctionnement du site
    - **UE_Electrical_Engineering_support_de_cours_traitement_du_signal** : Le cours de traitement du signal

## Utilisation du site

1. Installez les dépendances nécessaires :
   ```
   pip install -r chatbot/requirements.txt
   ```
2. Placez-vous dans le dossier `chatbot/` :
   ```
   cd chatbot
   ```
3. Lancez l'application :
   ```
   python app.py
   ```
4. Attendez le lancement, puis ouvrez [http://127.0.0.1:5000](http://127.0.0.1:5000) dans votre navigateur.
5. Déposez un cours au format PDF ou TXT.
6. Attendez le chargement du cours.

### Fonctionnement du chatbot

Le chatbot propose deux modes de fonctionnement :
- **Mode ciblé** : L'utilisateur peut demander de réviser une partie précise du cours (ex : "Pose-moi une question sur la transformée de Fourier"). Le chatbot identifie la section correspondante et génère une question adaptée.
- **Mode non ciblé** : Le chatbot parcourt l'ensemble du cours, pose des questions sur chaque partie, puis propose une série d'exercices simples (questions ou QCM) pour vérifier la compréhension globale.

## Auteurs

- Aleian Nada
- Aubou Chrissy
- Fomba Kani
- Gingelwein Cyprien
- Le Niniven Chloé

## Encadrant du projet

- Gilliot Jean-Marie

## Licence

Ce projet est mis à disposition sous la licence Creative Commons BY-NC-SA 4.0
Vous êtes libre de partager et d’adapter le code, à condition de citer les auteurs, de ne pas en faire un usage commercial, et de le redistribuer sous la même licence.