let chatState = {
  step: 'start',
  intent: null,
  keywords: null,
  currentPassage: null,
  currentIndex: 0,
  exercise: null,
  currentQuestionIndex: 0,
  questions: []
};
  
  document.addEventListener("DOMContentLoaded", () => {
    const sendButton = document.getElementById("send-button");
    const userInput = document.getElementById("user-input");
    const chatWindow = document.getElementById("chat-window");
    const newConvBtn = document.getElementById("new-conversation-btn");
  
    function displayMessage(sender, message) {
      // Crée un élément de message et l'ajoute à la fenêtre de chat
  const div = document.createElement("div");
  div.className = "message";
  
  // Conversion basique du Markdown/LaTeX
  let formattedMessage = message
    .replace(/### (.*?)(\n|$)/g, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
    // Remplacer les lignes de remplacement LaTeX
  .replace(/\\\\((.*?)\\\\)/g, '<span class="math">\\($1\\)</span>') // LaTeX inline
  .replace(/\\\\\[(.*?)\\\\]/g, '<div class="math">\\[$1\\]</div>') // Equations bloquées

  div.innerHTML = `
    <div class="message-header">
      <strong>${sender}:</strong>
    </div>
    <div class="message-content">
      ${formattedMessage}
    </div>
  `;

  chatWindow.appendChild(div);
  
  // Re-process MathJax après l'insertion
  if (window.MathJax) {
    window.MathJax.typesetPromise([div]).catch((err) => console.log('MathJax error:', err));
  }
  
  chatWindow.scrollTop = chatWindow.scrollHeight;
}
  
    async function handleApiCall(url, options, errorMsg) {
      try {
        const response = await fetch(url, options);
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.error || errorMsg);
        }
        return await response.json();
      } catch (error) {
        displayMessage("Erreur", error.message);
        throw error;
      }
    }
  
    async function processStep(userResponse = null) {
      // Gères les différentes étapes de la conversation et les appels API associés
      try {
        if (userResponse) {
          displayMessage("Vous", userResponse);
          await handleApiCall('/api/append_history', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({role: 'user', content: userResponse})
          }, "Erreur d'enregistrement");
        }
  
        switch(chatState.step) {
          case 'start':
            await handleApiCall('/api/init', {
              method: 'POST',
              credentials: 'include'
            }, "Erreur d'initialisation");
            displayMessage("Assistant", "Bonjour ! Prêt à réviser ?");
            displayMessage("Assistant", "Souhaitez-vous réviser le cours en entier ou une partie spécifique ?");
            chatState.step = 'detect_intent';
            break;
  
          case 'detect_intent': {
            const data = await handleApiCall(
              '/api/detect_intent',
              {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({user_input: userResponse})
              },
              "Erreur de détection d'intention"
            );
            console.log("[DEBUG client] detect_intent response:", data);
  
            if (data.step === 'clarify_keywords') {
              chatState.step = 'clarify_keywords';
              displayMessage("Assistant", data.message);
              return;
            }
  
            chatState.intent = data.intent;
            chatState.step = 'get_question';
            await processStep();
            break;
          }
  
          case 'clarify_keywords': {
            const data = await handleApiCall(
              '/api/clarify_keywords',
              {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({user_input: userResponse})
              },
              "Erreur de clarification"
            );
  
            if (data.step === 'clarify_keywords') {
              displayMessage("Assistant", data.message);
              return;
            }
  
            chatState.keywords = data.keywords;
            chatState.step = 'get_question';
            await processStep();
            break;
          }
  
          case 'get_question': {
            const data = await handleApiCall(
              '/api/get_question',
              {
                method: 'GET',
                credentials: 'include'
              },
              "Erreur de génération de question"
            );
  
            if (data.status === "complete") {
              displayMessage("Assistant", "Bravo ! Tu as terminé les questions de révision, passons à quelques exercices portant sur ton cours.");

              chatState.step = 'generate_exercise';
              await processStep(); //  appel récursif pour enchaîner automatiquement
              return;
            }

  
            chatState.currentPassage = data.passage;
            displayMessage("Assistant", data.question);
            chatState.step = 'check_answer';
            break;
          }
  
          case 'check_answer': {
            const data = await handleApiCall(
              '/api/check_answer',
              {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({
                  user_answer: userResponse,
                  passage: chatState.currentPassage
                })
              },
              "Erreur d'évaluation"
            );
  
            displayMessage("Assistant", data.correction);
  
            if (data.mastery) {
              chatState.step = 'get_question';
              await processStep();
            } else {
              displayMessage("Assistant", "Essayez à nouveau !");
            }
            break;
          }
          case 'generate_exercise': {
            const data = await handleApiCall(
                '/api/generate_exercise',
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    credentials: 'include',
                    body: JSON.stringify({course_text: chatState.currentPassage})
                },
                "Erreur de génération d'exercice"
            );
            
            const splitData = await handleApiCall(
                '/api/split_questions',
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({exercise_text: data.exercise})
                },
                "Erreur de découpage"
            );
            
            chatState.exercise = data.exercise;
            chatState.questions = splitData.questions;
            chatState.currentQuestionIndex = 0;
            
            displayMessage("Assistant", data.exercise);
            displayMessage("Assistant", "Commencez par la première question :");
            displayMessage("Assistant", chatState.questions[0]);
            chatState.step = 'handle_exercise';
            break;
        }
        
        case 'handle_exercise': {
            const data = await handleApiCall(
                '/api/correct_exercise',
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_answer: userResponse,
                        question: chatState.questions[chatState.currentQuestionIndex]
                    })
                },
                "Erreur de correction"
            );
            
            displayMessage("Assistant", data.correction);
            chatState.currentQuestionIndex++;
            
            if(chatState.currentQuestionIndex < chatState.questions.length) {
                displayMessage("Assistant", "Question suivante :");
                displayMessage("Assistant", chatState.questions[chatState.currentQuestionIndex]);
            } else {
                displayMessage("Assistant", "Exercice terminé ! Bien joué !");
                chatState.step = 'start';
            }
            break;
        }
        }
      } catch (error) {
        console.error(error);
        chatState.step = 'start';
      }
    }
  
    // Gestion du bouton "Nouvelle conversation"
    newConvBtn.addEventListener("click", async () => {
      console.log('[Client] Demande de nouvelle conversation…');
      try {
        const resp = await fetch('/reset_course', {
          method: 'POST',
          credentials: 'include'
        });
        console.log('[Client] reset_course status:', resp.status);
        const data = await resp.json();
        console.log('[Client] reset_course JSON:', data);
  
        if (!resp.ok) {
          alert(data.error || 'Impossible de réinitialiser la conversation');
          return;
        }
        // Redirection vers la page d'accueil
        window.location.href = '/';
      } catch (err) {
        console.error('[Client] Erreur reset_course:', err);
        alert('Erreur de connexion au serveur');
      }
    });
  
    sendButton.addEventListener("click", async () => {
      const text = userInput.value.trim();
      if (!text) return;
      userInput.value = "";
      await processStep(text);
    });
  
    userInput.addEventListener("keypress", async (e) => {
      if (e.key === "Enter") {
        const text = userInput.value.trim();
        if (!text) return;
        userInput.value = "";
        await processStep(text);
      }
    });
  
    // Initialisation
    processStep();
  });
  