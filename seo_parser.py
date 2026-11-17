import requests
from bs4 import BeautifulSoup, NavigableString
from readability import Document
import re

def analyze_seo(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
        
        # 1. Собираем метаданные со всей страницы
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title_tag = soup.find('title')
        title = title_tag.string.strip() if title_tag and title_tag.string else 'No title found'
        
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        meta_desc = meta_desc_tag['content'].strip() if meta_desc_tag and 'content' in meta_desc_tag.attrs else ''
        
        meta_keys_tag = soup.find('meta', attrs={'name': 'keywords'})
        meta_keys = meta_keys_tag['content'].strip() if meta_keys_tag and 'content' in meta_keys_tag.attrs else ''
        
        canonical_tag = soup.find('link', attrs={'rel': 'canonical'})
        canonical = canonical_tag['href'].strip() if canonical_tag and 'href' in canonical_tag.attrs else ''
        
        headings = {}
        for i in range(1, 7):
            headings[f'H{i}'] = [tag.get_text(strip=True) for tag in soup.find_all(f'h{i}') if tag.get_text(strip=True)]
        
        # 2. МАГИЯ: Извлекаем ТОЛЬКО основную статью (как режим "Чтения" в браузере)
        doc = Document(response.text)
        main_html = doc.summary() 
        
        content_soup = BeautifulSoup(main_html, 'html.parser')
        for tag in content_soup(["script", "style", "noscript", "iframe", "svg"]):
            tag.decompose()
        
        # 3. Преобразуем в текст с сохранением абзацев
        page_text = extract_structured_text(content_soup)
        
        return {
            'url': url, 'status': 'success', 'Title': title, 'Title_length': len(title),
            'Meta description': meta_desc, 'Meta_description_length': len(meta_desc),
            'Meta keywords': meta_keys, 'Canonical': canonical, 'Headings': headings, 'page_text': page_text
        }
    except Exception as e:
        return {'status': 'error', 'error': f'Ошибка: {str(e)}'}

def extract_structured_text(element):
    lines = []
    for child in element.children:
        if isinstance(child, NavigableString):
            text = child.strip()
            if text: lines.append(text)
        elif child.name in ['p', 'div', 'section', 'blockquote', 'pre']:
            text = child.get_text(strip=True)
            if text:
                lines.append(text)
                lines.append('')
        elif child.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text = child.get_text(strip=True)
            if text:
                lines.append(text)
                lines.append('')
        elif child.name == 'ul':
            for li in child.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                if text: lines.append(f'• {text}')
            lines.append('')
        elif child.name == 'ol':
            for i, li in enumerate(child.find_all('li', recursive=False), 1):
                text = li.get_text(strip=True)
                if text: lines.append(f'{i}. {text}')
            lines.append('')
        elif child.name == 'br':
            lines.append('')
        elif child.name in ['table', 'figure', 'img']:
            continue
        else:
            text = extract_structured_text(child)
            if text.strip(): lines.append(text)
    
    result = '\n'.join(lines)
    return re.sub(r'\n{3,}', '\n\n', result).strip()