import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import queue
import time
import sys
import os
import logging
from datetime import datetime

# Aggiunge la directory parent alla path per importare i moduli del progetto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent_core import AgentCore
from src.config import Config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AgentUI")

class AgentUI:
    """
    Interfaccia utente semplice per interagire con l'agente.
    Permette di inviare comandi all'agente e visualizzare lo stato e le risposte.
    """
    def __init__(self, root, config):
        """
        Inizializza l'interfaccia utente.
        
        Args:
            root: Root della finestra Tkinter
            config: Configurazione dell'agente
        """
        self.root = root
        self.config = config
        self.agent = None
        self.agent_thread = None
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        
        # Configura la finestra
        self.root.title("DjenisAiAgent - Interfaccia di Controllo")
        self.root.geometry("1600x900")  # Finestra molto più grande
        self.root.minsize(1024, 768)     # Dimensione minima
import threading
import queue
import time
import sys
import os
import logging
from datetime import datetime

# Aggiunge la directory parent alla path per importare i moduli del progetto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent_core import AgentCore
from src.config import Config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AgentUI")

class AgentUI:
    """
    Interfaccia utente semplice per interagire con l'agente.
    Permette di inviare comandi all'agente e visualizzare lo stato e le risposte.
    """
    def __init__(self, root, config):
        """
        Inizializza l'interfaccia utente.
        
        Args:
            root: Root della finestra Tkinter
            config: Configurazione dell'agente
        """
        self.root = root
        self.config = config
        self.agent = None
        self.agent_thread = None
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        
        # Configure the window
        self.root.title("DjenisAiAgent - Control Interface")
        self.root.geometry("1400x900")  # Large window size
        self.root.minsize(1200, 800)    # Minimum size
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Add an icon and customize appearance
        self.root.configure(bg="#f0f0f0")
        
        # Configure the base font with larger size
        default_font = ('Segoe UI', 14)  # Large font for better readability
        self.root.option_add('*Font', default_font)
        
        # Create frames
        self.create_frames()
        
        # Inizializza l'agente
        self.initialize_agent()
        
        # Avvia il controllo della coda
        self.check_queue()

    def create_frames(self):
        """Crea i frame e i widget dell'interfaccia."""
        # Frame di stato
        self.status_frame = tk.Frame(self.root, height=60, bd=2, relief=tk.RAISED)
        self.status_frame.pack(fill=tk.X, side=tk.TOP, padx=10, pady=10)
        
        self.status_label = tk.Label(self.status_frame, text="Stato: Inizializzazione...", font=('Segoe UI', 16, 'bold'))
        self.status_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        self.task_label = tk.Label(self.status_frame, text="Task attivo: Nessuno", font=('Segoe UI', 16))
        self.task_label.pack(side=tk.LEFT, padx=30, pady=5)
        
        # Frame dei comandi
        self.command_frame = tk.Frame(self.root)
        self.command_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=15)
        
        self.command_entry = tk.Entry(self.command_frame, font=('Segoe UI', 16))
        self.command_entry.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(10, 5), pady=5)
        self.command_entry.bind("<Return>", self.on_send)
        
        button_style = {'font': ('Segoe UI', 14, 'bold'), 'width': 12, 'height': 1, 'padx': 5, 'pady': 5}
        
        self.send_button = tk.Button(self.command_frame, text="Invia", command=self.on_send, **button_style)
        self.send_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.pause_button = tk.Button(self.command_frame, text="Pausa", command=self.toggle_pause, **button_style)
        self.pause_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.screenshot_button = tk.Button(self.command_frame, text="Screenshot", command=self.take_screenshot, **button_style)
        self.screenshot_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Frame di output
        self.output_frame = tk.Frame(self.root)
        self.output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.output_text = scrolledtext.ScrolledText(self.output_frame, font=('Consolas', 16))
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.output_text.config(state=tk.DISABLED)
        
    def initialize_agent(self):
        """Inizializza l'agente in un thread separato."""
        try:
            self.add_message("Inizializzazione dell'agente...")
            self.agent = AgentCore(self.config)
            self.update_status("Pronto")
            
            # Avvia l'agente in un thread separato
            self.agent_thread = threading.Thread(target=self.run_agent)
            self.agent_thread.daemon = True
            self.agent_thread.start()
            
            self.add_message("Agente inizializzato e pronto.")
        except Exception as e:
            self.add_message(f"Errore nell'inizializzazione dell'agente: {str(e)}")
            logger.error(f"Errore nell'inizializzazione dell'agente: {str(e)}", exc_info=True)
            
    def run_agent(self):
        """Esegue il ciclo principale dell'agente."""
        try:
            if self.agent:
                self.agent.running = True
            else:
                self.queue.put(("error", "Agente non inizializzato"))
                return
            
            while not self.stop_event.is_set():
                if not self.agent.paused:
                    self.agent._process_next_task()
                    
                    # Aggiorna lo stato
                    status_info = self.agent.get_status()
                    self.queue.put(("update_status", status_info))
                    
                time.sleep(0.1)
                
        except Exception as e:
            self.queue.put(("error", str(e)))
            logger.error(f"Errore nell'esecuzione dell'agente: {str(e)}", exc_info=True)
        finally:
            if self.agent:
                self.agent.running = False
            self.queue.put(("status", "Arrestato"))
            
    def check_queue(self):
        """Controlla la coda dei messaggi dal thread dell'agente."""
        try:
            while not self.queue.empty():
                message_type, message = self.queue.get(block=False)
                
                if message_type == "status":
                    self.update_status(message)
                elif message_type == "update_status":
                    self.update_from_status_info(message)
                elif message_type == "message":
                    self.add_message(message)
                elif message_type == "error":
                    self.add_message(f"Errore: {message}")
                    self.update_status("Errore")
                    
        except queue.Empty:
            pass
        finally:
            # Richiama questo metodo ogni 100ms
            self.root.after(100, self.check_queue)
    
    def on_send(self, event=None):
        """Gestisce l'invio di un comando."""
        command = self.command_entry.get().strip()
        if not command:
            return
            
        self.command_entry.delete(0, tk.END)
        self.add_message(f"> {command}")
        
        # Gestisci i comandi speciali
        if command.lower() == "exit" or command.lower() == "quit":
            self.on_close()
            return
        elif command.lower() == "pause":
            self.toggle_pause()
            return
        elif command.lower() == "screenshot":
            self.take_screenshot()
            return
        
        # Invia il comando all'agente in un thread separato
        threading.Thread(target=self.process_command, args=(command,)).start()
    
    def process_command(self, command):
        """Elabora un comando utente."""
        try:
            if not self.agent:
                self.queue.put(("error", "Agente non inizializzato"))
                return
            
            self.queue.put(("message", f"Elaborazione del comando: \"{command}\""))
            self.queue.put(("message", "Cattura dello screenshot in corso..."))
            
            # Cattura uno screenshot prima di inviare il comando
            try:
                screenshot = self.agent.components["screen_capture"].capture_screen()
                path = self.agent.components["screen_capture"].save_capture(screenshot)
                self.queue.put(("message", f"Screenshot catturato: {path}"))
            except Exception as e:
                self.queue.put(("error", f"Errore durante la cattura dello screenshot: {str(e)}"))
                
            # Passa il comando all'agente
            self.queue.put(("message", "Invio della richiesta a Gemini..."))
            response = self.agent.process_user_request(command)
            
            # Mostra la risposta
            if response:
                if isinstance(response, dict) and "error" in response:
                    self.queue.put(("error", response["error"]))
                else:
                    # Estrai il testo della risposta se è un dizionario
                    if isinstance(response, dict) and "text" in response:
                        response_text = response['text']
                        # Dividi il testo in blocchi se è molto lungo
                        if len(response_text) > 500:
                            chunks = [response_text[i:i+500] for i in range(0, len(response_text), 500)]
                            self.queue.put(("message", f"Risposta:"))
                            for i, chunk in enumerate(chunks):
                                self.queue.put(("message", f"[Parte {i+1}/{len(chunks)}] {chunk}"))
                        else:
                            self.queue.put(("message", f"Risposta: {response_text}"))
                    else:
                        self.queue.put(("message", f"Risposta: {response}"))
                    
                    # Se ci sono azioni, crea dei task
                    if isinstance(response, dict) and "actions" in response:
                        for action in response["actions"]:
                            action_type = action.get('type') if isinstance(action, dict) else str(action)
                            self.queue.put(("message", f"Creato task per azione: {action_type}"))
                            
                    # Crea un task demo se non ci sono azioni specifiche
                    elif not self.agent.components["task_memory"].get_active_tasks():
                        task_id = self.agent.components["task_memory"].create_task(
                            description=f"Risposta a: {command}",
                            metadata={
                                "command": command,
                                "response": str(response)
                            }
                        )
                        self.queue.put(("message", f"Creato task dimostrativo con ID: {task_id}"))
            else:
                self.queue.put(("message", "Nessuna risposta dall'agente"))
                
        except Exception as e:
            self.queue.put(("error", str(e)))
            logger.error(f"Errore nell'elaborazione del comando: {str(e)}", exc_info=True)
    
    def toggle_pause(self):
        """Mette in pausa o riprende l'agente."""
        if not self.agent:
            self.add_message("Impossibile mettere in pausa: agente non inizializzato")
            return
            
        if self.agent.paused:
            self.agent.paused = False
            self.pause_button.config(text="Pausa", bg="#f0f0f0")  # Colore normale
            self.add_message("Agente ripreso")
            self.update_status("In esecuzione")
        else:
            self.agent.paused = True
            self.pause_button.config(text="Riprendi", bg="#ffffa0")  # Giallo chiaro
            self.add_message("Agente in pausa")
            self.update_status("In pausa")
    
    def take_screenshot(self):
        """Cattura uno screenshot."""
        if not self.agent or not self.agent.components.get("screen_capture"):
            self.add_message("Impossibile catturare lo screenshot: componente non disponibile")
            return
            
        try:
            screenshot = self.agent.components["screen_capture"].capture_screen()
            path = self.agent.components["screen_capture"].save_capture(screenshot)
            self.add_message(f"Screenshot salvato: {path}")
            
            # Analizza lo screenshot
            if self.agent.components.get("screen_analyzer"):
                analysis = self.agent.components["screen_analyzer"].analyze(screenshot)
                info = self.agent.components["screen_analyzer"].extract_information(analysis)
                self.add_message(f"Analisi: {info}")
        except Exception as e:
            self.add_message(f"Errore nella cattura dello screenshot: {str(e)}")
    
    def add_message(self, message):
        """Aggiunge un messaggio all'output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}\n"
        
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, full_message)
        self.output_text.see(tk.END)
        self.output_text.config(state=tk.DISABLED)
        
        # Aggiorna la finestra per assicurarsi che il messaggio sia immediatamente visibile
        self.root.update_idletasks()
    
    def update_status(self, status):
        """Aggiorna l'etichetta di stato."""
        status_color = {
            "In esecuzione": "#b0ffb0",  # Verde chiaro
            "In pausa": "#ffffa0",       # Giallo chiaro
            "Pronto": "#b0e0ff",         # Blu chiaro
            "Inizializzazione": "#f0f0f0", # Grigio chiaro
            "Errore": "#ffb0b0",         # Rosso chiaro
            "Arrestato": "#ffb0b0"       # Rosso chiaro
        }.get(status, "#f0f0f0")
        
        self.status_label.config(text=f"Stato: {status}", bg=status_color)
        self.status_frame.update()
    
    def update_from_status_info(self, status_info):
        """Aggiorna l'interfaccia con le informazioni di stato dell'agente."""
        if status_info.get("running", False):
            if status_info.get("paused", False):
                self.update_status("In pausa")
            else:
                self.update_status("In esecuzione")
        else:
            self.update_status("Arrestato")
            
        # Aggiorna l'etichetta del task
        task_info = status_info.get("current_task")
        if task_info:
            self.task_label.config(text=f"Task attivo: {task_info.get('description', 'Sconosciuto')}")
        else:
            self.task_label.config(text="Task attivo: Nessuno")
    
    def on_close(self):
        """Gestisce la chiusura dell'applicazione."""
        if messagebox.askokcancel("Esci", "Sei sicuro di voler uscire?"):
            logger.info("Arresto dell'agente e chiusura dell'interfaccia utente")
            self.stop_event.set()
            
            if self.agent:
                self.agent.stop()
                
            # Attendi un po' prima di uscire
            self.root.after(500, self.root.destroy)


def load_config(config_path=None):
    """
    Carica la configurazione da file o crea una configurazione predefinita.
    
    Args:
        config_path: Percorso del file di configurazione
        
    Returns:
        Dizionario di configurazione
    """
    if config_path and os.path.exists(config_path):
        try:
            config = Config(config_path)
            return config.settings
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {str(e)}")
            sys.exit(1)
    else:
        # Usa il percorso predefinito
        default_config_path = "config/default_config.json"
        if os.path.exists(default_config_path):
            try:
                config = Config(default_config_path)
                return config.settings
            except Exception as e:
                logger.error(f"Errore nel caricamento della configurazione predefinita: {str(e)}")
                sys.exit(1)
                
    # Se nessun file di configurazione esiste, mostra un errore
    logger.error("Nessun file di configurazione trovato.")
    sys.exit(1)


def main():
    """Punto di ingresso principale per l'interfaccia utente."""
    import argparse
    
    parser = argparse.ArgumentParser(description='DjenisAiAgent UI - Interfaccia utente per l\'agente MCP')
    parser.add_argument('--config', help='Percorso del file di configurazione')
    parser.add_argument('--debug', action='store_true', help='Abilita la modalità debug')
    args = parser.parse_args()
    
    # Imposta il livello di log
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Modalità debug abilitata")
    
    # Carica la configurazione
    config = load_config(args.config)
    
    # Crea le directory di dati
    os.makedirs(config["memory"].get("task_storage_dir", "data/task_memory"), exist_ok=True)
    os.makedirs(config["perception"].get("screenshot_dir", "data/screenshots"), exist_ok=True)
    
    # Inizializza l'interfaccia utente
    root = tk.Tk()
    app = AgentUI(root, config)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Applicazione terminata dall'utente")
    except Exception as e:
        logger.error(f"Errore nell'esecuzione dell'interfaccia utente: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
