import os
import subprocess
import threading
import wave
import tkinter as tk
from tkinter import scrolledtext
import pyaudio
import speech_recognition as sr
import google.genai as genai
from google.genai import types
from dotenv import load_dotenv

API_KEY = os.getenv("GEMINI_API")

# --- Gemini Configuration ---
# Replace with your actual API Key
client = genai.Client(api_key=os.getenv(API_KEY))

# The System Instruction defines the "Brain's" behavior
def load_prompt(path="system_prompt.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

SYSTEM_INSTRUCTION = load_prompt()

# Low creativity settings for consistent, robotic output
generation_config = types.GenerateContentConfig(
    temperature=0.0,
    top_p=0.1,
    top_k=1,
    system_instruction=SYSTEM_INSTRUCTION # System prompt goes here now
)

MODEL_NAME = 'gemini-2.5-flash'

def get_chat_response(user_input):
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_input,
        config=generation_config
    )
    return response.text

class GeminiVoiceAssistant:
    def __init__(self, root):
        self.root = root
        self.root.title("Gemini Context Assistant")
        self.root.geometry("450x600")
        
        # Initialize Chat Session (This holds the history)
        self.chat = model.start_chat(history=[])
        
        # Audio Setup
        self.p = pyaudio.PyAudio()
        self.is_recording = False
        self.frames = []

        # --- UI Setup ---
        tk.Label(root, text="Gemini Shell Assistant", font=('Segoe UI', 14, 'bold')).pack(pady=10)

        # Command Log
        self.log = scrolledtext.ScrolledText(root, height=15, width=50, state='disabled', font=('Consolas', 9))
        self.log.pack(pady=10, padx=10)

        # Control Buttons
        self.btn = tk.Button(root, text="🎤 HOLD TO TALK", bg="#4CAF50", fg="white", 
                             font=('Segoe UI', 10, 'bold'), width=30, height=2)
        self.btn.pack(pady=5)
        
        self.reset_btn = tk.Button(root, text="🔄 NEW THREAD (Clear History)", 
                                   command=self.reset_thread, bg="#f44336", fg="white")
        self.reset_btn.pack(pady=10)

        # Bindings for Mouse Click
        self.btn.bind("<ButtonPress-1>", self.start_recording)
        self.btn.bind("<ButtonRelease-1>", self.stop_recording)

    def update_log(self, sender, message):
        self.log.config(state='normal')
        self.log.insert(tk.END, f"{sender}: {message}\n\n")
        self.log.see(tk.END)
        self.log.config(state='disabled')

    def reset_thread(self):
        self.chat = model.start_chat(history=[]) # Reset the Gemini session
        self.log.config(state='normal')
        self.log.delete(1.0, tk.END)
        self.log.config(state='disabled')
        self.update_log("SYSTEM", "History cleared. Starting fresh thread.")

    def start_recording(self, event):
        self.is_recording = True
        self.frames = []
        self.btn.config(bg="#f44336", text="LISTENING...")
        threading.Thread(target=self.record_loop).start()

    def record_loop(self):
        stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        while self.is_recording:
            self.frames.append(stream.read(1024))
        stream.stop_stream()
        stream.close()

    def stop_recording(self, event):
        self.is_recording = False
        self.btn.config(bg="#4CAF50", text="PROCESSING...")
        self.process_audio()

    def process_audio(self):
        # Save audio to temp file
        filename = "temp_voice.wav"
        wf = wave.open(filename, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(44100)
        wf.writeframes(b''.join(self.frames))
        wf.close()
        
        threading.Thread(target=self.get_ai_response, args=(filename,)).start()

    def get_ai_response(self, filename):
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(filename) as source:
                audio = recognizer.record(source)
            user_text = recognizer.recognize_google(audio)
            self.update_log("YOU", user_text)

            # Send to Gemini (The session tracks history automatically)
            response = self.chat.send_message(user_text)
            response_text = response.text.strip()

            # Parse language and code
            if "CODE:" in response_text:
                parts = response_text.split("CODE:", 1)
                lang = parts[0].replace("LANGUAGE:", "").strip().lower()
                code = parts[1].strip().replace("```", "") # Clean any backticks
                self.root.after(0, self.show_review_window, lang, code)
            else:
                self.update_log("AI", response_text)

        except Exception as e:
            self.update_log("ERROR", str(e))
        finally:
            self.btn.config(text="🎤 HOLD TO TALK")
            if os.path.exists(filename): os.remove(filename)

    def show_review_window(self, lang, code):
        review = tk.Toplevel(self.root)
        review.title(f"Review {lang.upper()} Script")
        
        lbl = tk.Label(review, text=f"Generated {lang} script. Confirm execution:", pady=5)
        lbl.pack()

        text_area = scrolledtext.ScrolledText(review, height=12, width=60, font=('Consolas', 9))
        text_area.insert(tk.END, code)
        text_area.pack(padx=10, pady=10)
        
        def run_script():
            self.execute_script(lang, code)
            review.destroy()

        exec_btn = tk.Button(review, text="EXECUTE", command=run_script, bg="green", fg="white", width=20)
        exec_btn.pack(side=tk.LEFT, padx=20, pady=10)
        
        cancel_btn = tk.Button(review, text="CANCEL", command=review.destroy, width=20)
        cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10)

    def execute_script(self, lang, code):
        ext_map = {"powershell": ".ps1", "python": ".py", "batch": ".bat"}
        ext = ext_map.get(lang, ".ps1")
        temp_file = f"runner_task{ext}"
        
        with open(temp_file, "w") as f:
            f.write(code)

        try:
            if lang == "powershell":
                # WindowStyle Hidden keeps the background clean
                subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", temp_file])
            elif lang == "batch":
                subprocess.run([temp_file], creationflags=subprocess.CREATE_NO_WINDOW)
            else: # Python
                subprocess.run(["python", temp_file])
            
            self.update_log("SYSTEM", f"Successfully executed {lang} task.")
        except Exception as e:
            self.update_log("SYSTEM ERROR", str(e))
        finally:
            if os.path.exists(temp_file): os.remove(temp_file)

if __name__ == "__main__":
    root = tk.Tk()
    app = GeminiVoiceAssistant(root)
    root.mainloop()