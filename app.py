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

load_dotenv()

API_KEY = os.getenv("GEMINI_API")

# --- Gemini Configuration ---
# Replace with your actual API Key
client = genai.Client(api_key=API_KEY)

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

        # 1. Initialize the Client
        # Ensure you have 'from google import genai' and 'from google.genai import types' at the top
        self.client = genai.Client(api_key=os.getenv("GEMINI_API"))
        self.model_id = MODEL_NAME # Upgraded to the 2026 standard

        # 2. Define the behavior in a Config object
        # This replaces the old generation_config and model-level instructions
        self.chat_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.0,
            top_p=0.1,
            top_k=1
        )

        # 3. Initialize Chat Session with the config
        self.chat = self.client.chats.create(
            model=self.model_id,
            config=self.chat_config
        )

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
        # 3. Reset the session by creating a new chat object
        self.chat = self.client.chats.create(model=self.model_id)
        
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
            blocks = self.parse_runnable_blocks(response_text)
            if blocks:
                # Show any text outside blocks as AI message
                clean_text = response_text
                for b in blocks:
                    clean_text = clean_text.replace(b['raw'], '').strip()
                if clean_text:
                    self.update_log("AI", clean_text)
                self.root.after(0, self.show_review_window, blocks)
            else:
                self.update_log("AI", response_text)

        except Exception as e:
            self.update_log("ERROR", str(e))
        finally:
            self.btn.config(text="🎤 HOLD TO TALK")
            if os.path.exists(filename): os.remove(filename)

    def parse_runnable_blocks(self, text):
        import re
        blocks = []
        pattern = r'(<<<RUNNABLE>>>\s*LANG:\s*(\w+)\s*PRIORITY:\s*(\d+)\s*<<<CODE>>>(.*?)<<<END>>>)'
        matches = re.findall(pattern, text, re.DOTALL)
        for raw, lang, priority, code in matches:
            blocks.append({
                'raw': raw,
                'lang': lang.strip().lower(),
                'priority': int(priority.strip()),
                'code': code.strip()
            })
        blocks.sort(key=lambda x: x['priority'])
        return blocks

    def show_review_window(self, blocks):
        review = tk.Toplevel(self.root)
        review.title("Review Scripts")

        tk.Label(review, text=f"{len(blocks)} block(s) found. PRIORITY 1 runs first, fallback on failure.", pady=5).pack()

        notebook_frame = tk.Frame(review)
        notebook_frame.pack(fill='both', expand=True, padx=10, pady=5)

        text_areas = {}
        for b in blocks:
            lbl = tk.Label(notebook_frame, text=f"[PRIORITY {b['priority']}] {b['lang'].upper()}", anchor='w', font=('Consolas', 9, 'bold'))
            lbl.pack(fill='x')
            ta = scrolledtext.ScrolledText(notebook_frame, height=10, width=60, font=('Consolas', 9))
            ta.insert(tk.END, b['code'])
            ta.pack(pady=2)
            text_areas[b['priority']] = (b['lang'], ta)

        def run_scripts():
            # Read edited code from text areas before closing
            final_blocks = []
            for priority, (lang, ta) in sorted(text_areas.items()):
                final_blocks.append({'lang': lang, 'priority': priority, 'code': ta.get("1.0", tk.END).strip()})
            review.destroy()
            threading.Thread(target=self.execute_with_fallback, args=(final_blocks,)).start()

        tk.Button(review, text="EXECUTE", command=run_scripts, bg="green", fg="white", width=20).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(review, text="CANCEL", command=review.destroy, width=20).pack(side=tk.RIGHT, padx=20, pady=10)

    def execute_with_fallback(self, blocks):
        ext_map = {"powershell": ".ps1", "python": ".py", "batch": ".bat"}
        for b in blocks:
            lang = b['lang']
            code = b['code']
            ext = ext_map.get(lang, ".py")
            temp_file = f"runner_task{ext}"

            with open(temp_file, "w") as f:
                f.write(code)

            try:
                self.update_log("SYSTEM", f"Trying PRIORITY {b['priority']} ({lang.upper()})...")
                if lang == "powershell":
                    result = subprocess.run(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", temp_file],
                        capture_output=True, text=True
                    )
                elif lang == "batch":
                    result = subprocess.run([temp_file], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    result = subprocess.run(["python", temp_file], capture_output=True, text=True)

                if result.returncode == 0:
                    self.update_log("SYSTEM", f"[OK] PRIORITY {b['priority']} ({lang.upper()}) succeeded.")
                    return  # Stop here, don't try fallback
                else:
                    self.update_log("WARN", f"PRIORITY {b['priority']} failed (code {result.returncode}): {result.stderr.strip()[:200]}")

            except Exception as e:
                self.update_log("WARN", f"PRIORITY {b['priority']} exception: {str(e)}")
            finally:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

        self.update_log("ERROR", "All blocks failed. No fallback remaining.")
    
    
if __name__ == "__main__":
    root = tk.Tk()
    app = GeminiVoiceAssistant(root)
    root.mainloop()