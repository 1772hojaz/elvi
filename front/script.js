document.addEventListener('DOMContentLoaded', () => {
    const voiceButton = document.getElementById('voiceButton');
    const selectedFloorDiv = document.getElementById('selectedFloor');
    let mediaRecorder = null;
    let audioChunks = [];
    let isListening = false;

    // Text-to-speech
    const speak = (text) => {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.8; // Slower for clarity
        utterance.volume = 1.0;
        utterance.lang = 'en-US';
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    };

    // Initialize
    speak('Welcome to the accessible elevator app. Activate the button to start voice input.');

    // Toggle voice input
    voiceButton.addEventListener('click', async () => {
        if (isListening) {
            mediaRecorder.stop();
            isListening = false;
            voiceButton.textContent = 'Start Voice Input';
            voiceButton.setAttribute('aria-pressed', 'false');
            speak('Voice input stopped.');
        } else {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' }); // Use webm or wav
                audioChunks = [];

                mediaRecorder.ondataavailable = (event) => {
                    audioChunks.push(event.data);
                };

                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    sendAudioToAPI(audioBlob);
                };

                mediaRecorder.start();
                isListening = true;
                voiceButton.textContent = 'Stop Listening';
                voiceButton.setAttribute('aria-pressed', 'true');
                speak('Please say the floor number.');
            } catch (e) {
                speak('Error accessing microphone: ' + e.message);
            }
        }
    });

    // Send audio to backend
    async function sendAudioToAPI(audioBlob) {
        try {
            const formData = new FormData();
            formData.append('file', audioBlob, 'audio.webm'); // Use .webm or .m4a

            const response = await fetch('http://127.0.0.1:8000/transcribe', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();
            if (result.floor) {
                selectFloor(result.floor);
            } else {
                speak(result.message || 'No valid floor number recognized.');
            }
        } catch (e) {
            speak('Error processing voice input: ' + e.message);
        }
    }

    // Handle floor selection
    function selectFloor(floor) {
        selectedFloorDiv.textContent = `Selected: Floor ${floor}`;
        selectedFloorDiv.setAttribute('aria-label', `Selected floor: ${floor}`);
        speak(`Selected floor ${floor}`);
        // Simulate Bluetooth command
        console.log(`Simulated Bluetooth command: FLOOR:${floor}`);
    }
});
