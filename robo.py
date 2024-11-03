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
BASE_SAVE_DIR = "dist/MeusSalvamentos"

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
    """Obtém lista de IDs dos vídeos usando a playlist de uploads do canal."""
    try:
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
            request = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response['items']:
                video_ids.append(item['snippet']['resourceId']['videoId'])
                total_processed += 1
                if total_processed % 50 == 0:
                    print(f"Encontrados {total_processed} vídeos...")
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
            
            time.sleep(0.5)
        
        print(f"Total de vídeos encontrados: {len(video_ids)}")
        return video_ids
    except Exception as e:
        print(f"Erro ao obter lista de vídeos: {str(e)}")
        return []

def get_video_details(youtube, video_id):
    """Obtém detalhes do vídeo."""
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
    """Obtém os top comentários ordenados por likes."""
    try:
        all_comments = []
        next_page_token = None
        
        while len(all_comments) < 500:
            try:
                request = youtube.commentThreads().list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=100,
                    pageToken=next_page_token,
                    textFormat="plainText",
                    order="relevance"
                )
                response = request.execute()
                
                for item in response['items']:
                    comment = item['snippet']['topLevelComment']['snippet']
                    all_comments.append({
                        'author': comment['authorDisplayName'],
                        'text': comment['textDisplay'],
                        'likes': int(comment.get('likeCount', 0)),
                        'date': comment['publishedAt'].split('T')[0]
                    })
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                    
            except Exception as e:
                print(f"Erro ao obter página de comentários: {str(e)}")
                break
        
        all_comments.sort(key=lambda x: x['likes'], reverse=True)
        top_comments = all_comments[:max_comments]
        
        for i, comment in enumerate(top_comments, 1):
            comment['ranking'] = i
        
        return top_comments
        
    except Exception as e:
        print(f"Erro ao obter comentários: {str(e)}")
        return []

def get_transcript(video_id):
    """Obtém a transcrição do vídeo."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        languages = ['en', 'en-US', 'pt', 'pt-BR', 'es', 'fr', 'de']
        
        # Tenta transcrições manuais
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
        
        # Última tentativa: qualquer transcrição disponível
        if not transcript:
            try:
                available_transcripts = transcript_list.manual + transcript_list.generated
                if available_transcripts:
                    transcript = available_transcripts[0]
            except:
                pass
        
        if transcript:
            if transcript.language_code != 'en':
                try:
                    transcript = transcript.translate('en')
                except:
                    pass
            
            return transcript.fetch()
        
        return None
    except:
        return None

def save_video_content(video_id, video_details, comments, channel_folder, include_description, include_comments):
    """Salva o conteúdo do vídeo em arquivo."""
    try:
        # Obtém a transcrição
        transcript_data = get_transcript(video_id)

        # Define a pasta de destino
        output_dir = os.path.join(channel_folder, "Com Transcrição" if transcript_data else "Sem Transcrição")
        os.makedirs(output_dir, exist_ok=True)
        
        # Prepara o nome do arquivo
        valid_title = "".join(c for c in video_details['title'] if c.isalnum() or c in (' ','-','_')).rstrip()
        valid_title = valid_title[:150]
        output_file = os.path.join(output_dir, f"{valid_title}.txt")

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
            if transcript_data:
                f.write("TRANSCRIÇÃO:\n")
                transcript_data.sort(key=lambda x: x['start'])
                seen_texts = set()
                
                for entry in transcript_data:
                    text = entry['text'].strip()
                    if text and text not in seen_texts:
                        seen_texts.add(text)
                        start_time = int(entry['start'])
                        minutes = start_time // 60
                        seconds = start_time % 60
                        f.write(f"[{minutes:02d}:{seconds:02d}] {text}\n")
            else:
                f.write("TRANSCRIÇÃO: Não disponível para este vídeo\n\n")

            # Comentários
            if include_comments and comments:
                f.write("\nTOP 100 COMENTÁRIOS (Por número de likes):\n")
                for comment in comments:
                    f.write(f"\n#{comment['ranking']} - {comment['likes']} likes\n")
                    f.write(f"Autor: {comment['author']}\n")
                    f.write(f"Data: {comment['date']}\n")
                    f.write(f"Comentário: {comment['text']}\n")
                    f.write("-" * 50 + "\n")

        return True, "Sucesso", "Com Transcrição" if transcript_data else "Sem Transcrição"
        
    except Exception as e:
        return False, str(e), None
    
def generate_channel_analysis(video_details_list, channel_name, sucessos_com_transcricao, sucessos_sem_transcricao, output_dir):
    """Gera um relatório detalhado de análise do canal em formato Markdown."""
    try:
        # Coleta dados para análise
        total_videos = len(video_details_list)
        total_views = sum(int(v['views']) for v in video_details_list)
        total_likes = sum(int(v['likes']) for v in video_details_list)
        total_comments = sum(int(v['comments_count']) for v in video_details_list)
        
        # Calcula médias
        avg_views = total_views / total_videos if total_videos > 0 else 0
        avg_likes = total_likes / total_videos if total_videos > 0 else 0
        avg_comments = total_comments / total_videos if total_videos > 0 else 0
        
        # Análise temporal
        dates = [v['publish_date'] for v in video_details_list]
        dates.sort()
        oldest_date = dates[0]
        newest_date = dates[-1]
        
        # Calcula frequência de postagem
        from datetime import datetime
        date_format = "%Y-%m-%d"
        first_date = datetime.strptime(oldest_date, date_format)
        last_date = datetime.strptime(newest_date, date_format)
        days_between = (last_date - first_date).days
        posts_per_week = (total_videos * 7) / days_between if days_between > 0 else 0
        
        # Análise de palavras (títulos e descrições)
        import re
        from collections import Counter
        
        def clean_text(text):
            # Remove caracteres especiais e converte para minúsculas
            text = re.sub(r'[^\w\s]', '', text.lower())
            # Remove palavras comuns em inglês
            stop_words = {'the', 'and', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'a', 'by', 'an', 'is', 'are'}
            return ' '.join(word for word in text.split() if word not in stop_words and len(word) > 2)
        
        # Análise de títulos
        all_titles = ' '.join(v['title'] for v in video_details_list)
        clean_titles = clean_text(all_titles)
        title_words = Counter(clean_titles.split()).most_common(20)
        
        # Análise de descrições
        if any(v.get('description') for v in video_details_list):
            all_descriptions = ' '.join(v.get('description', '') for v in video_details_list)
            clean_descriptions = clean_text(all_descriptions)
            desc_words = Counter(clean_descriptions.split()).most_common(20)
        
        # Gera o relatório em Markdown
        report = f"""# 📊 Análise do Canal {channel_name}

## 📈 Estatísticas Gerais

### 🎥 Vídeos
- Total de Vídeos: **{total_videos}**
- Com Transcrição: **{sucessos_com_transcricao}** 📝
- Sem Transcrição: **{sucessos_sem_transcricao}** ❌
- Taxa de Vídeos com Transcrição: **{(sucessos_com_transcricao/total_videos)*100:.2f}%** 📊

### 👁️ Visualizações
- Total de Views: **{total_views:,}**
- Média de Views por Vídeo: **{int(avg_views):,}**

### ❤️ Engajamento
- Total de Likes: **{total_likes:,}**
- Média de Likes por Vídeo: **{int(avg_likes):,}**
- Total de Comentários: **{total_comments:,}**
- Média de Comentários por Vídeo: **{int(avg_comments):,}**

## ⏰ Análise Temporal

### 📅 Período de Atividade
- Primeiro Vídeo: **{oldest_date}**
- Vídeo Mais Recente: **{newest_date}**
- Tempo de Canal: **{days_between} dias**

### 📊 Frequência de Postagem
- Média de **{posts_per_week:.1f}** vídeos por semana
- Aproximadamente **{posts_per_week * 4:.1f}** vídeos por mês

## 🔍 Análise de Conteúdo

### 📝 Palavras Mais Frequentes nos Títulos
"""
        
        # Adiciona as palavras mais frequentes dos títulos
        for word, count in title_words:
            report += f"- {word}: {count} vezes\n"
        
        if any(v.get('description') for v in video_details_list):
            report += "\n### 📄 Palavras Mais Frequentes nas Descrições\n"
            for word, count in desc_words[:10]:  # Limita a 10 palavras das descrições
                report += f"- {word}: {count} vezes\n"
        
        # Adiciona gráfico de distribuição temporal (ASCII art simples)
        report += "\n## 📊 Distribuição de Vídeos ao Longo do Tempo\n```\n"
        
        # Agrupa vídeos por ano
        from collections import defaultdict
        videos_by_year = defaultdict(int)
        for date in dates:
            year = date[:4]
            videos_by_year[year] += 1
        
        # Cria gráfico ASCII simples
        max_videos = max(videos_by_year.values())
        for year, count in sorted(videos_by_year.items()):
            bar_length = int((count / max_videos) * 50)
            report += f"{year} | {'█' * bar_length} {count}\n"
        
        report += "```\n"
        
        # Adiciona insights finais
        report += f"""
## 💡 Insights

1. **Crescimento do Canal** 🚀
   - O canal tem mantido uma presença ativa por {days_between//365} anos e {(days_between%365)//30} meses
   - Média de {int(avg_views):,} visualizações por vídeo demonstra uma audiência consistente

2. **Engajamento da Audiência** 👥
   - Taxa média de {(avg_likes/avg_views)*100:.2f}% de likes por visualização
   - Aproximadamente {(avg_comments/avg_views)*100:.2f}% dos espectadores comentam nos vídeos

3. **Consistência de Conteúdo** 📈
   - Mantém uma frequência regular de {posts_per_week:.1f} vídeos por semana
   - {sucessos_com_transcricao/total_videos*100:.1f}% dos vídeos possuem transcrição disponível

## 🏆 Recordes do Canal

- Vídeo Mais Antigo: {oldest_date} 📅
- Vídeo Mais Recente: {newest_date} 🆕

---
*Relatório gerado automaticamente em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}* ⚡
"""
        
        # Salva o relatório
        report_file = os.path.join(output_dir, f"{channel_name}_analise.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        return True
    except Exception as e:
        print(f"Erro ao gerar análise do canal: {str(e)}")
        return False

def main():
    API_KEY = 'AIzaSyCItptfGsY26-Ux94bH2-FpfyO5VpoDxhs'
    youtube = check_api_key(API_KEY)
    
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
    
    include_description = (incluir_descricao == '1')
    include_comments = (incluir_comentarios == '1')
    
    # Obtém informações do canal e vídeos
    channel_id, channel_name = get_channel_info(youtube, channel_url)
    channel_folder = re.sub(r'[<>:"/\\|?*]', '', channel_name)
    output_dir = os.path.join(os.getcwd(), channel_folder)
    
    # Cria estrutura de pastas
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "Com Transcrição"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "Sem Transcrição"), exist_ok=True)
    
    # Obtém e processa vídeos
    videos = get_video_ids(youtube, channel_id)
    total_videos = len(videos)
    
    # Lista para armazenar detalhes de todos os vídeos
    all_video_details = []
    
    # Contadores
    sucessos_com_transcricao = 0
    sucessos_sem_transcricao = 0
    falhas = 0
    erros = {}
    
    print("\nProcessando vídeos...")
    for video_id in tqdm(videos, desc="Progresso", unit="vídeo"):
        try:
            video_details = get_video_details(youtube, video_id)
            if not video_details:
                continue
            
            # Adiciona à lista de detalhes
            all_video_details.append(video_details)
            
            comments = get_video_comments(youtube, video_id) if include_comments else []
            
            success, error, status = save_video_content(
                video_id,
                video_details,
                comments,
                output_dir,
                include_description,
                include_comments
            )
            
            if success:
                if status == "Com Transcrição":
                    sucessos_com_transcricao += 1
                else:
                    sucessos_sem_transcricao += 1
            else:
                falhas += 1
                print(f"\nErro no vídeo {video_details['title']}: {error}")
                
                if error not in erros:
                    erros[error] = 0
                erros[error] += 1
            
        except Exception as e:
            falhas += 1
            print(f"\nErro inesperado no vídeo {video_id}: {str(e)}")
        
        time.sleep(0.5)
    
    # Gera análise detalhada do canal
    print("\nGerando análise detalhada do canal...")
    generate_channel_analysis(
        all_video_details,
        channel_name,
        sucessos_com_transcricao,
        sucessos_sem_transcricao,
        output_dir
    )
    
    # Relatório final
    print("\n=== Relatório Final ===")
    print(f"Canal: {channel_name}")
    print(f"Total de vídeos processados: {total_videos}")
    print(f"Vídeos com transcrição: {sucessos_com_transcricao}")
    print(f"Vídeos sem transcrição: {sucessos_sem_transcricao}")
    print(f"Falhas no processamento: {falhas}")
    print(f"Taxa de sucesso total: {((sucessos_com_transcricao + sucessos_sem_transcricao)/total_videos)*100:.2f}%")
    print(f"Taxa de vídeos com transcrição: {(sucessos_com_transcricao/total_videos)*100:.2f}%")
    
    if erros:
        print("\nTipos de erro encontrados:")
        for erro, quantidade in erros.items():
            print(f"- {erro}: {quantidade} vídeos")
    
    print(f"\nArquivos salvos em: {output_dir}")
    print(f"- Vídeos com transcrição: {os.path.join(output_dir, 'Com Transcrição')}")
    print(f"- Vídeos sem transcrição: {os.path.join(output_dir, 'Sem Transcrição')}")
    print(f"- Análise detalhada: {os.path.join(output_dir, f'{channel_name}_analise.md')}")

if __name__ == "__main__":
    main()