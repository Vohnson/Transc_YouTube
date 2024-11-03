# Salve como gui.py
import customtkinter as ctk
import json
import os
from robo import check_api_key, get_channel_info, get_video_ids, get_video_details
from robo import get_video_comments, save_video_content, generate_channel_analysis

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configurações da janela
        self.title("YouTube Transcriber")
        self.geometry("600x800")
        
        # Carrega configurações salvas
        self.settings = self.load_settings()
        
        # Tema
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        
        # Frame principal
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # API Key
        self.api_label = ctk.CTkLabel(self.main_frame, text="API Key do YouTube:")
        self.api_label.pack(pady=5)
        
        self.api_entry = ctk.CTkEntry(self.main_frame, width=400)
        self.api_entry.pack(pady=5)
        self.api_entry.insert(0, self.settings.get('api_key', ''))
        
        # URL do Canal
        self.url_label = ctk.CTkLabel(self.main_frame, text="URL do Canal:")
        self.url_label.pack(pady=5)
        
        self.url_entry = ctk.CTkEntry(self.main_frame, width=400)
        self.url_entry.pack(pady=5)
        
        # Opções
        self.options_frame = ctk.CTkFrame(self.main_frame)
        self.options_frame.pack(pady=20, fill="x")
        
        self.desc_var = ctk.BooleanVar(value=self.settings.get('include_description', True))
        self.desc_check = ctk.CTkCheckBox(self.options_frame, 
                                        text="Incluir descrição dos vídeos",
                                        variable=self.desc_var)
        self.desc_check.pack(pady=5)
        
        self.comments_var = ctk.BooleanVar(value=self.settings.get('include_comments', True))
        self.comments_check = ctk.CTkCheckBox(self.options_frame, 
                                            text="Incluir comentários dos vídeos",
                                            variable=self.comments_var)
        self.comments_check.pack(pady=5)
        
        # Botão Processar
        self.process_button = ctk.CTkButton(self.main_frame, 
                                          text="Processar Canal",
                                          command=self.process_channel)
        self.process_button.pack(pady=20)
        
        # Barra de Progresso
        self.progress_bar = ctk.CTkProgressBar(self.main_frame)
        self.progress_bar.pack(pady=10, fill="x")
        self.progress_bar.set(0)
        
        # Log de Status
        self.status_text = ctk.CTkTextbox(self.main_frame, height=300)
        self.status_text.pack(pady=10, fill="both", expand=True)
    
    def load_settings(self):
        try:
            if os.path.exists('settings.json'):
                with open('settings.json', 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def save_settings(self):
        settings = {
            'api_key': self.api_entry.get(),
            'include_description': self.desc_var.get(),
            'include_comments': self.comments_var.get()
        }
        try:
            with open('settings.json', 'w') as f:
                json.dump(settings, f)
        except:
            pass
    
    def log_status(self, message):
        self.status_text.insert("end", f"{message}\n")
        self.status_text.see("end")
        self.update()
    
    def process_channel(self):
        # Validações
        api_key = self.api_entry.get()
        if not api_key:
            self.log_status("❌ Erro: Insira a chave API do YouTube!")
            return
            
        channel_url = self.url_entry.get()
        if not channel_url:
            self.log_status("❌ Erro: Insira a URL do canal!")
            return
        
        # Desabilita botão durante processamento
        self.process_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_text.delete("1.0", "end")
        
        try:
            # Inicializa API
            self.log_status("📡 Conectando à API do YouTube...")
            youtube = check_api_key(api_key)
            
            # Obtém informações do canal
            self.log_status("🔍 Obtendo informações do canal...")
            channel_id, channel_name = get_channel_info(youtube, channel_url)
            
            # Prepara diretórios
            base_dir = "MeusSalvamentos"
            channel_folder = channel_name.replace(" ", "_")
            output_dir = os.path.join(os.getcwd(), base_dir, channel_folder)
            
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(os.path.join(output_dir, "Com Transcrição"), exist_ok=True)
            os.makedirs(os.path.join(output_dir, "Sem Transcrição"), exist_ok=True)
            
            # Obtém lista de vídeos
            self.log_status("📚 Obtendo lista de vídeos...")
            videos = get_video_ids(youtube, channel_id)
            total_videos = len(videos)
            
            if not videos:
                self.log_status("❌ Nenhum vídeo encontrado!")
                return
                
            self.log_status(f"🎥 Total de vídeos encontrados: {total_videos}")
            
            # Processa vídeos
            all_video_details = []
            sucessos_com_transcricao = 0
            sucessos_sem_transcricao = 0
            falhas = 0
            
            for i, video_id in enumerate(videos):
                try:
                    progress = (i + 1) / total_videos
                    self.progress_bar.set(progress)
                    self.log_status(f"🎬 Processando vídeo {i+1} de {total_videos}")
                    
                    video_details = get_video_details(youtube, video_id)
                    if video_details:
                        all_video_details.append(video_details)
                        
                        comments = []
                        if self.comments_var.get():
                            comments = get_video_comments(youtube, video_id)
                        
                        success, _, status = save_video_content(
                            video_id,
                            video_details,
                            comments,
                            output_dir,
                            self.desc_var.get(),
                            self.comments_var.get()
                        )
                        
                        if success:
                            if status == "Com Transcrição":
                                sucessos_com_transcricao += 1
                            else:
                                sucessos_sem_transcricao += 1
                        else:
                            falhas += 1
                            
                except Exception as e:
                    falhas += 1
                    self.log_status(f"❌ Erro no vídeo: {str(e)}")
                
                self.update()
            
            # Gera análise
            self.log_status("\n📊 Gerando análise detalhada...")
            generate_channel_analysis(
                all_video_details,
                channel_name,
                sucessos_com_transcricao,
                sucessos_sem_transcricao,
                output_dir
            )
            
            # Relatório final
            self.log_status("\n=== Relatório Final ===")
            self.log_status(f"Canal: {channel_name}")
            self.log_status(f"Total de vídeos: {total_videos}")
            self.log_status(f"Com transcrição: {sucessos_com_transcricao}")
            self.log_status(f"Sem transcrição: {sucessos_sem_transcricao}")
            self.log_status(f"Falhas: {falhas}")
            
            self.log_status(f"\nArquivos salvos em: {output_dir}")
            
        except Exception as e:
            self.log_status(f"❌ Erro: {str(e)}")
        
        finally:
            self.process_button.configure(state="normal")
            self.save_settings()

if __name__ == "__main__":
    app = App()
    app.mainloop()