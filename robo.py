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
import json

def check_api_key(api_key):
    """Verifica se a chave API está funcionando."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.channels().list(
            part='id',
            id='UC_x5XG1OV2P6uZZ5FSM9Ttw'
        )
        request.execute()
        return youtube
    except HttpError as e:
        print(f"Erro na API do YouTube: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"Erro inesperado: {str(e)}")
        sys.exit(1)

def get_channel_info(youtube, channel_url):
    """Obtém ID e nome do canal."""
    try:
        print("\nObtendo informações do canal...")
        if '@' in channel_url:
            handle = channel_url.split('@')[1]
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
                raise Exception("Canal não encontrado")
    except Exception as e:
        print(f"Erro ao obter informações do canal: {str(e)}")
        sys.exit(1)

def get_video_ids(youtube, channel_id):
    """Obtém lista de IDs dos vídeos do canal usando playlists de uploads."""
    try:
        # Primeiro, obtém a playlist de uploads do canal
        request = youtube.channels().list(
            part='contentDetails',
            id=channel_id
        )
        response = request.execute()
        
        playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        print("\nObtendo lista de vídeos do canal...")
        video_ids = []
        next_page_token = None
        total_processed = 0
        
        while True:
            # Obtém vídeos da playlist de uploads
            request = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,  # Máximo permitido por requisição
                pageToken=next_page_token
            )
            response = request.execute()
            
            # Adiciona IDs dos vídeos à lista
            for item in response['items']:
                video_ids.append(item['snippet']['resourceId']['videoId'])
                total_processed += 1
                if total_processed % 50 == 0:
                    print(f"Encontrados {total_processed} vídeos...")
            
            # Verifica se há mais páginas
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
            
            time.sleep(0.5)  # Pequena pausa para evitar atingir limites da API
        
        print(f"Total de vídeos encontrados: {len(video_ids)}")
        return video_ids
    except Exception as e:
        print(f"Erro ao obter lista de vídeos: {str(e)}")
        return []

def get_video_details(youtube, video_id):
    """Obtém detalhes completos do vídeo."""
    try:
        video_response = youtube.videos().list(
            part='snippet,statistics',
            id=video_id
        ).execute()
        
        video = video_response['items'][0]
        snippet = video['snippet']
        statistics = video['statistics']
        
        return {
            'title': snippet['title'],
            'description': snippet['description'],
            'publish_date': snippet['publishedAt'].split('T')[0],
            'views': statistics.get('viewCount', '0'),
            'likes': statistics.get('likeCount', '0'),
            'comments_count': statistics.get('commentCount', '0')
        }
    except Exception as e:
        print(f"Erro ao obter detalhes do vídeo: {str(e)}")
        return None

def get_video_comments(youtube, video_id, max_comments=100):
    """Obtém os top comentários do vídeo ordenados por likes."""
    try:
        all_comments = []
        next_page_token = None
        
        # Coleta todos os comentários disponíveis (até um limite razoável)
        while len(all_comments) < 500:  # Limitamos a 500 para não sobrecarregar
            try:
                request = youtube.commentThreads().list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=100,  # Máximo permitido pela API
                    pageToken=next_page_token,
                    textFormat="plainText",
                    order="relevance"  # Ordena por relevância
                )
                response = request.execute()
                
                # Processa os comentários
                for item in response['items']:
                    comment = item['snippet']['topLevelComment']['snippet']
                    all_comments.append({
                        'author': comment['authorDisplayName'],
                        'text': comment['textDisplay'],
                        'likes': int(comment.get('likeCount', 0)),
                        'date': comment['publishedAt'].split('T')[0]
                    })
                
                # Verifica se há mais páginas
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                    
            except Exception as e:
                print(f"Erro ao obter página de comentários: {str(e)}")
                break
        
        # Ordena os comentários por número de likes (decrescente)
        all_comments.sort(key=lambda x: x['likes'], reverse=True)
        
        # Retorna apenas os top 100 comentários
        top_comments = all_comments[:max_comments]
        
        # Adiciona ranking aos comentários
        for i, comment in enumerate(top_comments, 1):
            comment['ranking'] = i
        
        return top_comments
        
    except Exception as e:
        print(f"Erro ao obter comentários: {str(e)}")
        return []

def save_video_content(video_id, video_details, comments, output_file, include_description, include_comments):
    """Função atualizada para incluir ranking nos comentários."""
    try:
        # [Código anterior permanece igual até a parte dos comentários]

        # Comentários
        if include_comments and comments:
            f.write("\nTOP 100 COMENTÁRIOS (Por número de likes):\n")
            for comment in comments:
                f.write(f"\n#{comment['ranking']} - {comment['likes']} likes\n")
                f.write(f"Autor: {comment['author']}\n")
                f.write(f"Data: {comment['date']}\n")
                f.write(f"Comentário: {comment['text']}\n")
                f.write("-" * 50 + "\n")

        # [Resto do código permanece igual]

    except Exception as e:
        return False, str(e)

def save_video_content(video_id, video_details, comments, output_file, include_description, include_comments):
    """Salva conteúdo do vídeo em arquivo com melhor tratamento de transcrições."""
    try:
        # Tenta obter a transcrição em diferentes formatos
        transcript_data = None
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Tenta diferentes idiomas e tipos de transcrição
            transcript = None
            
            # Lista de idiomas para tentar
            languages = ['en', 'en-US', 'pt', 'pt-BR', 'es', 'fr', 'de']
            
            # Primeiro tenta transcrições manuais
            for lang in languages:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    break
                except:
                    continue
            
            # Se não encontrou manual, tenta as geradas automaticamente
            if not transcript:
                for lang in languages:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang])
                        break
                    except:
                        continue
            
            # Se ainda não encontrou, tenta qualquer transcrição disponível
            if not transcript:
                try:
                    # Pega a primeira transcrição disponível, seja manual ou gerada
                    available_transcripts = transcript_list.manual + transcript_list.generated
                    if available_transcripts:
                        transcript = available_transcripts[0]
                except:
                    pass
            
            if not transcript:
                return False, f"Nenhuma transcrição encontrada (ID: {video_id})"
            
            # Se encontrou em outro idioma, traduz para inglês
            if transcript.language_code != 'en':
                try:
                    transcript = transcript.translate('en')
                except:
                    pass  # Se não conseguir traduzir, usa a transcrição original
            
            transcript_data = transcript.fetch()
            
        except Exception as e:
            return False, f"Erro ao obter transcrição: {str(e)}"

        if not transcript_data:
            return False, "Sem transcrição disponível"

        with open(output_file, 'w', encoding='utf-8') as f:
            # Informações básicas
            f.write(f"Título: {video_details['title']}\n")
            f.write(f"URL: https://www.youtube.com/watch?v={video_id}\n")
            f.write(f"Data de Publicação: {video_details['publish_date']}\n")
            f.write(f"Visualizações: {video_details['views']}\n")
            f.write(f"Likes: {video_details['likes']}\n")
            f.write(f"Quantidade de Comentários: {video_details['comments_count']}\n\n")

            # Descrição
            if include_description:
                f.write("DESCRIÇÃO:\n")
                f.write(f"{video_details['description']}\n\n")

            # Transcrição
            f.write("TRANSCRIÇÃO:\n")
            
            # Ordena por tempo e remove duplicatas
            transcript_data.sort(key=lambda x: x['start'])
            seen_texts = set()
            unique_transcript = []
            
            for entry in transcript_data:
                text = entry['text'].strip()
                if text and text not in seen_texts:
                    seen_texts.add(text)
                    unique_transcript.append(entry)
            
            # Escreve a transcrição sem duplicatas
            for entry in unique_transcript:
                start_time = int(entry['start'])
                minutes = start_time // 60
                seconds = start_time % 60
                text = entry['text'].replace('\n', ' ').strip()
                if text:  # Só escreve se tiver texto
                    f.write(f"[{minutes:02d}:{seconds:02d}] {text}\n")

            # Comentários
            if include_comments and comments:
                f.write("\nCOMENTÁRIOS:\n")
                for comment in comments:
                    f.write(f"\nAutor: {comment['author']}\n")
                    f.write(f"Data: {comment['date']}\n")
                    f.write(f"Likes: {comment['likes']}\n")
                    f.write(f"Comentário: {comment['text']}\n")
                    f.write("-" * 50 + "\n")

        return True, "Sucesso"
        
    except Exception as e:
        return False, str(e)

def main():
    # Sua chave API
    API_KEY = 'AIzaSyCItptfGsY26-Ux94bH2-FpfyO5VpoDxhs'
    
    # Inicializa API
    youtube = check_api_key(API_KEY)
    
    # Obtém URL do canal
    print("Digite a URL do canal do YouTube: ", end='')
    channel_url = input().strip()
    
    # Obtém opções do usuário
    while True:
        print("\nComo você deseja salvar as transcrições?")
        print("1 - Um arquivo para cada vídeo")
        print("2 - Todas as transcrições em um único arquivo")
        opcao = input("Escolha (1 ou 2): ").strip()
        if opcao in ['1', '2']:
            break
    
    while True:
        print("\nDeseja incluir a descrição dos vídeos?")
        print("1 - Sim")
        print("2 - Não")
        incluir_descricao = input("Escolha (1 ou 2): ").strip()
        if incluir_descricao in ['1', '2']:
            break
    
    while True:
        print("\nDeseja incluir os comentários dos vídeos?")
        print("1 - Sim")
        print("2 - Não")
        incluir_comentarios = input("Escolha (1 ou 2): ").strip()
        if incluir_comentarios in ['1', '2']:
            break
    
    # Processa opções
    include_description = (incluir_descricao == '1')
    include_comments = (incluir_comentarios == '1')
    
    # Obtém informações do canal
    channel_id, channel_name = get_channel_info(youtube, channel_url)
    
    # Cria pasta para o canal
    channel_folder = re.sub(r'[<>:"/\\|?*]', '', channel_name)
    output_dir = os.path.join(os.getcwd(), channel_folder)
    os.makedirs(output_dir, exist_ok=True)
    
    # Obtém lista de vídeos
    print("\nObtendo lista de vídeos...")
    videos = get_video_ids(youtube, channel_id)
    total_videos = len(videos)
    print(f"Total de vídeos encontrados: {total_videos}")
    
    # Processa vídeos
    sucessos = 0
    falhas = 0
    
    print("\nProcessando vídeos...")
    for i, video_id in enumerate(tqdm(videos)):
        try:
            # Obtém detalhes do vídeo
            video_details = get_video_details(youtube, video_id)
            if not video_details:
                continue
                
            # Obtém comentários se necessário
            comments = get_video_comments(youtube, video_id) if include_comments else []
            
            # Define nome do arquivo
            filename = f"{re.sub(r'[<>:"/\\|?*]', '', video_details['title'])[:150]}.txt"
            output_file = os.path.join(output_dir, filename)
            
            # Salva conteúdo
            success, error = save_video_content(
                video_id,
                video_details,
                comments,
                output_file,
                include_description,
                include_comments
            )
            
            if success:
                sucessos += 1
            else:
                falhas += 1
                print(f"\nErro no vídeo {video_details['title']}: {error}")
            
        except Exception as e:
            falhas += 1
            print(f"\nErro inesperado no vídeo {video_id}: {str(e)}")
        
        time.sleep(0.5)  # Evita sobrecarga da API
    
    # Relatório final
    print("\n=== Relatório Final ===")
    print(f"Canal: {channel_name}")
    print(f"Total de vídeos: {total_videos}")
    print(f"Sucessos: {sucessos}")
    print(f"Falhas: {falhas}")
    print(f"Taxa de sucesso: {(sucessos/total_videos)*100:.2f}%")
    print(f"\nArquivos salvos em: {output_dir}")

if __name__ == "__main__":
    main()