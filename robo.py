from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
from urllib.parse import parse_qs, urlparse
from tqdm import tqdm
import time
import re
import sys

def check_api_key(api_key):
    """Verifica se a chave API está funcionando."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.channels().list(
            part='id',
            id='UC_x5XG1OV2P6uZZ5FSM9Ttw'  # Canal do Google Developers
        )
        request.execute()
        return True, youtube
    except HttpError as e:
        if e.resp.status == 403:
            print("Erro: Chave API inválida ou sem permissões adequadas.")
        else:
            print(f"Erro ao verificar a chave API: {str(e)}")
        return False, None
    except Exception as e:
        print(f"Erro inesperado ao verificar a chave API: {str(e)}")
        return False, None

def get_channel_info(youtube, channel_url):
    """Obtém ID e nome do canal."""
    try:
        print("Analisando URL do canal...")
        
        if '@' in channel_url:
            handle = channel_url.split('@')[-1]
            print(f"Buscando canal pelo handle: @{handle}")
            
            try:
                request = youtube.channels().list(
                    part='snippet',
                    forHandle=handle
                )
                response = request.execute()
                
                if 'items' in response and len(response['items']) > 0:
                    channel_id = response['items'][0]['id']
                    channel_name = response['items'][0]['snippet']['title']
                    print(f"Canal encontrado: {channel_name}")
                    return channel_id, channel_name
                else:
                    raise Exception("Canal não encontrado com este handle")
                    
            except HttpError:
                print("Erro ao buscar pelo handle, tentando método alternativo...")
                request = youtube.search().list(
                    part='snippet',
                    q=handle,
                    type='channel',
                    maxResults=1
                )
                response = request.execute()
                
                if 'items' in response and len(response['items']) > 0:
                    channel_id = response['items'][0]['snippet']['channelId']
                    channel_name = response['items'][0]['snippet']['title']
                    print(f"Canal encontrado: {channel_name}")
                    return channel_id, channel_name
                else:
                    raise Exception("Canal não encontrado")
        
        raise Exception("Formato de URL não suportado")
        
    except Exception as e:
        print(f"Erro ao obter informações do canal: {str(e)}")
        sys.exit(1)

def get_video_ids(youtube, channel_id):
    """Obtém IDs dos vídeos usando um método alternativo."""
    try:
        videos = []
        next_page_token = None
        page_count = 0
        
        print("\nColetando lista de vídeos do canal...")
        
        while True:
            page_count += 1
            print(f"Buscando página {page_count} de vídeos...")
            
            request = youtube.search().list(
                part='id',
                channelId=channel_id,
                maxResults=50,
                pageToken=next_page_token,
                type='video',
                order='date'
            )
            response = request.execute()
            
            for item in response['items']:
                if item['id']['kind'] == 'youtube#video':
                    videos.append(item['id']['videoId'])
            
            print(f"Encontrados {len(videos)} vídeos até agora...")
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
            
            time.sleep(0.5)
            
        return videos
    except Exception as e:
        print(f"Erro ao obter lista de vídeos: {str(e)}")
        return []

def get_video_title(youtube, video_id):
    """Obtém o título do vídeo pelo ID."""
    request = youtube.videos().list(
        part='snippet',
        id=video_id
    )
    response = request.execute()
    return response['items'][0]['snippet']['title']

def sanitize_folder_name(name):
    """Remove caracteres inválidos do nome da pasta."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def save_transcript_single(video_id, title, output_dir):
    """Salva a transcrição de um vídeo em um arquivo txt individual."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        try:
            transcript = transcript_list.find_transcript(['pt'])
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_transcript(['pt-BR'])
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_transcript(['en'])
                    transcript = transcript.translate('pt')
                except NoTranscriptFound:
                    try:
                        transcript = next(iter(transcript_list._manually_created_transcripts.values()))
                        transcript = transcript.translate('pt')
                    except:
                        transcript = next(iter(transcript_list._generated_transcripts.values()))
                        transcript = transcript.translate('pt')

        transcript_data = transcript.fetch()
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        valid_title = "".join(c for c in title if c.isalnum() or c in (' ','-','_')).rstrip()
        valid_title = valid_title[:150]
        
        filename = os.path.join(output_dir, f"{valid_title}.txt")
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Título: {title}\n")
            f.write(f"ID do Vídeo: {video_id}\n")
            f.write(f"URL: https://www.youtube.com/watch?v={video_id}\n")
            f.write("\nTRANSCRIÇÃO:\n\n")
            
            transcript_data.sort(key=lambda x: x['start'])
            
            for entry in transcript_data:
                text = entry['text'].replace('\n', ' ')
                start_time = int(entry['start'])
                minutes = start_time // 60
                seconds = start_time % 60
                timestamp = f"{minutes:02d}:{seconds:02d}"
                f.write(f"[{timestamp}] {text}\n")
        
        return True, "Sucesso"
        
    except TranscriptsDisabled:
        return False, "Transcrições desativadas"
    except NoTranscriptFound:
        return False, "Nenhuma transcrição encontrada"
    except Exception as e:
        return False, str(e)

def save_transcript_combined(video_id, title, combined_file, first_video=False):
    """Salva a transcrição em um arquivo combinado."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        try:
            transcript = transcript_list.find_transcript(['pt'])
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_transcript(['pt-BR'])
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_transcript(['en'])
                    transcript = transcript.translate('pt')
                except NoTranscriptFound:
                    try:
                        transcript = next(iter(transcript_list._manually_created_transcripts.values()))
                        transcript = transcript.translate('pt')
                    except:
                        transcript = next(iter(transcript_list._generated_transcripts.values()))
                        transcript = transcript.translate('pt')

        transcript_data = transcript.fetch()
        
        mode = 'w' if first_video else 'a'
        with open(combined_file, mode, encoding='utf-8') as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"Título: {title}\n")
            f.write(f"ID do Vídeo: {video_id}\n")
            f.write(f"URL: https://www.youtube.com/watch?v={video_id}\n")
            f.write("\nTRANSCRIÇÃO:\n\n")
            
            transcript_data.sort(key=lambda x: x['start'])
            
            for entry in transcript_data:
                text = entry['text'].replace('\n', ' ')
                start_time = int(entry['start'])
                minutes = start_time // 60
                seconds = start_time % 60
                timestamp = f"{minutes:02d}:{seconds:02d}"
                f.write(f"[{timestamp}] {text}\n")
            
            f.write(f"\n{'='*50}\n")
        
        return True, "Sucesso"
        
    except TranscriptsDisabled:
        return False, "Transcrições desativadas"
    except NoTranscriptFound:
        return False, "Nenhuma transcrição encontrada"
    except Exception as e:
        return False, str(e)

def main():
    API_KEY = 'AIzaSyCItptfGsY26-Ux94bH2-FpfyO5VpoDxhs'
    
    print("Verificando chave API...")
    api_valid, youtube = check_api_key(API_KEY)
    
    if not api_valid:
        print("Falha na verificação da chave API.")
        sys.exit(1)
    
    try:
        print("Digite a URL do canal do YouTube: ", end='')
        channel_url = input().strip()
        
        if not channel_url:
            print("URL não pode estar vazia!")
            sys.exit(1)
            
        print(f"URL recebida: {channel_url}")
        
        # Obtém informações do canal
        channel_id, channel_name = get_channel_info(youtube, channel_url)
        
        # Cria pasta com nome do canal
        channel_folder = sanitize_folder_name(channel_name)
        output_dir = os.path.join(os.getcwd(), channel_folder)
        
        # Pergunta ao usuário sobre o formato de salvamento
        while True:
            print("\nComo você deseja salvar as transcrições?")
            print("1 - Um arquivo para cada vídeo")
            print("2 - Todas as transcrições em um único arquivo")
            opcao = input("Escolha (1 ou 2): ").strip()
            
            if opcao in ['1', '2']:
                break
            print("Opção inválida! Por favor, escolha 1 ou 2.")
        
        # Cria diretório se necessário
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"\nCriando pasta para o canal: {channel_folder}")
        
        # Obtém a lista de vídeos
        videos = get_video_ids(youtube, channel_id)
        
        if not videos:
            print("Nenhum vídeo encontrado no canal.")
            sys.exit(1)
        
        total_videos = len(videos)
        print(f"\nTotal de vídeos encontrados: {total_videos}")
        
        # Contadores para estatísticas
        sucessos = 0
        falhas = 0
        erros = {}
        
        # Nome do arquivo combinado se necessário
        combined_file = os.path.join(output_dir, f"{channel_folder}_todas_transcricoes.txt")
        
        # Processa cada vídeo com barra de progresso
        print("\nBaixando transcrições...")
        for idx, video_id in enumerate(tqdm(videos, desc="Progresso", unit="vídeo")):
            title = get_video_title(youtube, video_id)
            
            if opcao == '1':
                success, error_message = save_transcript_single(video_id, title, output_dir)
            else:
                success, error_message = save_transcript_combined(video_id, title, combined_file, idx == 0)
            
            if success:
                sucessos += 1
            else:
                falhas += 1
                print(f"\nVídeo sem transcrição disponível: {title}")
                print(f"Motivo: {error_message}")
                
                if error_message not in erros:
                    erros[error_message] = 0
                erros[error_message] += 1
            
            time.sleep(0.5)
        
        # Relatório final
        print("\n=== Relatório Final ===")
        print(f"Canal: {channel_name}")
        print(f"Total de vídeos processados: {total_videos}")
        print(f"Transcrições baixadas com sucesso: {sucessos}")
        print(f"Vídeos sem transcrição disponível: {falhas}")
        print(f"Taxa de sucesso: {(sucessos/total_videos)*100:.2f}%")
        
        if erros:
            print("\nTipos de erro encontrados:")
            for erro, quantidade in erros.items():
                print(f"- {erro}: {quantidade} vídeos")
        
        print(f"\nTranscrições salvas na pasta: {output_dir}")
        if opcao == '2':
            print(f"Arquivo único: {combined_file}")
        
    except Exception as e:
        print(f"Erro inesperado: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()