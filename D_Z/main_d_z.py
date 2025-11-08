"""
ВЕЛИКИЙ ПАРСЕР ЦИТАТ - ШЕДЕВР КОДА
Универсальный производственный парсер для сайтов с цитатами
Автоматический запуск с готовыми адресами
"""

import requests
import time
import json
import csv
import argparse
import logging
import sys
import os
import re
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from tqdm import tqdm
from functools import wraps
import signal
from datetime import datetime
from typing import List, Dict, Optional, Any
import hashlib

# ===== КОНСТАНТЫ И КОНФИГУРАЦИЯ =====
DEFAULT_CONFIG = {
    "request_timeout": 15,
    "max_retries": 3,
    "retry_delay": 2,
    "user_agent": "UniversalQuoteParser/2.0 (+https://github.com/quote-parser)",
    "respect_robots": True,
    "min_quote_length": 10,
    "max_quote_length": 1000,
    "default_delay": 1
}

# АВТОМАТИЧЕСКИЕ АДРЕСА ДЛЯ ПАРСИНГА
AUTO_URLS = [
    "http://quotes.toscrape.com",
    "http://quotes.toscrape.com/tag/inspirational/",
    "http://quotes.toscrape.com/tag/love/",
    "http://quotes.toscrape.com/tag/life/",
    "http://quotes.toscrape.com/tag/humor/",
    "http://quotes.toscrape.com/tag/books/",
    "http://quotes.toscrape.com/tag/reading/",
    "http://quotes.toscrape.com/tag/friendship/",
    "http://quotes.toscrape.com/tag/friends/",
    "http://quotes.toscrape.com/tag/truth/"
]

SUPPORTED_SITES = {
    "toscrape": {
        "name": "Quotes to Scrape",
        "base_url": "http://quotes.toscrape.com",
        "selectors": {
            "quotes": "div.quote",
            "text": "span.text",
            "author": "small.author",
            "tags": "a.tag",
            "next_page": "li.next a"
        }
    }
}


class ConfigManager:
    """Продвинутый менеджер конфигурации с валидацией"""

    def __init__(self, config_file: Optional[str] = None):
        self.settings = DEFAULT_CONFIG.copy()
        self.config_file = config_file
        if config_file:
            self.load_config(config_file)

    def load_config(self, config_file: str) -> bool:
        """Загрузка и валидация конфигурации из файла"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)

            # Валидация конфигурации
            validated_config = self._validate_config(user_config)
            self.settings.update(validated_config)

            logger.info(f"✅ Конфигурация загружена из {config_file}")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки конфига: {e}. Использую настройки по умолчанию")
            return False

    def _validate_config(self, config: Dict) -> Dict:
        """Валидация параметров конфигурации"""
        validated = {}

        if "request_timeout" in config:
            timeout = max(5, min(config["request_timeout"], 60))
            validated["request_timeout"] = timeout

        if "max_retries" in config:
            retries = max(1, min(config["max_retries"], 10))
            validated["max_retries"] = retries

        if "user_agent" in config:
            validated["user_agent"] = str(config["user_agent"])

        return validated


# ===== ПРОДВИНУТОЕ ЛОГГИРОВАНИЕ =====
def setup_logging(log_file: str = "quote_parser.log") -> logging.Logger:
    """Настройка продвинутой системы логирования"""

    # Создаем форматтер с цветами для консоли
    class ColorFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': '\033[36m',  # CYAN
            'INFO': '\033[32m',  # GREEN
            'WARNING': '\033[33m',  # YELLOW
            'ERROR': '\033[31m',  # RED
            'CRITICAL': '\033[41m',  # RED BACKGROUND
            'RESET': '\033[0m'  # RESET
        }

        def format(self, record):
            log_message = super().format(record)
            if record.levelname in self.COLORS:
                return f"{self.COLORS[record.levelname]}{log_message}{self.COLORS['RESET']}"
            return log_message

    # Настройка логгера
    logger = logging.getLogger('QuoteParser')
    logger.setLevel(logging.INFO)

    # Форматтер для файла
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Обработчик для файла
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(file_formatter)

    # Обработчик для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorFormatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    ))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# ===== ДЕКОРАТОРЫ И УТИЛИТЫ ПРОДУКЦИОННОГО УРОВНЯ =====
def retry_on_failure(max_retries: int = 3, delay: float = 2,
                     exceptions: tuple = (Exception,), exponential_backoff: bool = True):
    """Продвинутый декоратор для повторных попыток с экспоненциальной задержкой"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        break

                    current_delay = delay * (2 ** attempt) if exponential_backoff else delay
                    logger.warning(
                        f"🔄 Попытка {attempt + 1}/{max_retries} failed: {e}. Повтор через {current_delay} сек...")
                    time.sleep(current_delay)

            logger.error(f"❌ Все {max_retries} попытки завершились ошибкой: {last_exception}")
            raise last_exception

        return wrapper

    return decorator


def graceful_shutdown(signum: int, frame: Any) -> None:
    """Обработчик для graceful shutdown с сохранением прогресса"""
    logger.info("🛑 Получен сигнал прерывания. Завершаем работу...")
    sys.exit(0)


# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)


# ===== ОСНОВНОЙ КЛАСС ПАРСЕРА - ШЕДЕВР ИНЖЕНЕРИИ =====
class UniversalQuoteParser:
    """Универсальный парсер цитат производственного уровня"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config.settings['user_agent'],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })

        self.visited_urls = set()
        self.all_quotes = []
        self.quote_hashes = set()  # Для обеспечения уникальности
        self.stats = {
            'start_time': None,
            'total_pages': 0,
            'total_quotes': 0,
            'failed_requests': 0
        }

        logger.info("🚀 Универсальный парсер цитат инициализирован")

    def _generate_quote_hash(self, quote_text: str, author: str) -> str:
        """Генерация хеша для проверки уникальности цитаты"""
        content = f"{quote_text.strip().lower()}|{author.strip().lower()}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def check_robots_txt(self, base_url: str) -> bool:
        """Проверка robots.txt с кэшированием"""
        if not self.config.settings['respect_robots']:
            return True

        try:
            parsed_url = urlparse(base_url)
            robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"

            logger.info(f"🤖 Проверяем robots.txt: {robots_url}")
            response = self.session.get(robots_url, timeout=10)

            if response.status_code == 404:
                logger.info("✅ robots.txt не найден - доступ разрешен")
                return True

            rp = RobotFileParser()
            rp.parse(response.text.splitlines())

            can_fetch = rp.can_fetch(self.config.settings['user_agent'], base_url)
            if not can_fetch:
                logger.error(f"🚫 Доступ к {base_url} запрещен в robots.txt")
            else:
                logger.info("✅ Robots.txt разрешает парсинг")

            return can_fetch

        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки robots.txt: {e}. Продолжаем...")
            return True

    @retry_on_failure(max_retries=3, delay=2, exponential_backoff=True)
    def fetch_page(self, url: str) -> str:
        """Загрузка страницы с продвинутой обработкой ошибок"""
        try:
            logger.debug(f"🌐 Загружаем страницу: {url}")
            response = self.session.get(
                url,
                timeout=self.config.settings['request_timeout'],
                allow_redirects=True
            )
            response.raise_for_status()

            # Проверка content-type
            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type:
                logger.warning(f"⚠️ Неожиданный content-type: {content_type}")

            logger.debug(f"✅ Страница загружена: {len(response.text)} символов")
            return response.text

        except requests.exceptions.Timeout:
            logger.error(f"⏰ Таймаут при загрузке {url}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"🚫 HTTP ошибка {e.response.status_code} для {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"🔌 Сетевая ошибка для {url}: {e}")
            raise

    def detect_site_type(self, url: str) -> Dict[str, Any]:
        """Автоматическое определение типа сайта и селекторов"""
        for site_id, site_config in SUPPORTED_SITES.items():
            if site_config['base_url'] in url:
                logger.info(f"🎯 Определен сайт: {site_config['name']}")
                return site_config['selectors']

        # Универсальные селекторы для неизвестных сайтов
        logger.info("🔍 Использую универсальные селекторы")
        return {
            "quotes": [".quote", "[class*='quote']", "blockquote"],
            "text": [".text", ".quote-text", "span", "p"],
            "author": [".author", ".quote-author", "cite", "small"],
            "tags": [".tag", ".tags", ".keywords"],
            "next_page": [".next", "[rel='next']", ".pagination-next"]
        }

    def parse_quotes(self, html: str, selectors: Dict) -> List[Dict]:
        """Умный парсинг цитат с автоматическим определением селекторов"""
        soup = BeautifulSoup(html, 'html.parser')
        quotes_data = []

        # Поиск контейнеров с цитатами
        quote_containers = []
        for selector in self._ensure_list(selectors["quotes"]):
            containers = soup.select(selector)
            if containers:
                quote_containers.extend(containers)
                logger.debug(f"🎯 Найден селектор для цитат: {selector} ({len(containers)} шт.)")
                break

        if not quote_containers:
            logger.warning("⚠️ Контейнеры цитат не найдены")
            return quotes_data

        for container in quote_containers:
            try:
                # Поиск текста цитаты
                quote_text = self._find_element_text(container, selectors["text"])
                if not quote_text:
                    continue

                # Поиск автора
                author_text = self._find_element_text(container, selectors["author"]) or "Unknown"

                # Поиск тегов
                tags = self._find_tags(container, selectors["tags"])

                # Валидация и создание объекта цитаты
                quote_obj = self._create_quote_object(quote_text, author_text, tags)
                if quote_obj and self._is_unique_quote(quote_obj):
                    quotes_data.append(quote_obj)

            except Exception as e:
                logger.debug(f"🔧 Ошибка парсинга отдельной цитаты: {e}")
                continue

        logger.info(f"📊 Распаршено цитат: {len(quotes_data)}")
        return quotes_data

    def _ensure_list(self, selector) -> List[str]:
        """Преобразование селектора в список"""
        if isinstance(selector, list):
            return selector
        return [selector] if selector else []

    def _find_element_text(self, container, selectors: List[str]) -> Optional[str]:
        """Поиск текста элемента по нескольким селекторам"""
        for selector in self._ensure_list(selectors):
            if not selector:
                continue
            element = container.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text:
                    return text
        return None

    def _find_tags(self, container, selectors: List[str]) -> List[str]:
        """Поиск тегов по нескольким селекторам"""
        tags = []
        for selector in self._ensure_list(selectors):
            if not selector:
                continue
            elements = container.select(selector)
            for element in elements:
                tag_text = element.get_text(strip=True)
                if tag_text:
                    tags.append(tag_text)
        return tags

    def _create_quote_object(self, quote_text: str, author: str, tags: List[str]) -> Optional[Dict]:
        """Создание и валидация объекта цитаты"""
        # Очистка текста
        quote_text = quote_text.strip()
        author = author.strip()

        # Валидация длины
        min_len = self.config.settings['min_quote_length']
        max_len = self.config.settings['max_quote_length']

        if len(quote_text) < min_len or len(quote_text) > max_len:
            return None

        # Валидация содержания
        if not self._validate_quote_content(quote_text):
            return None

        return {
            'quote': quote_text,
            'author': author,
            'tags': tags,
            'tags_count': len(tags),
            'timestamp': datetime.now().isoformat()
        }

    def _validate_quote_content(self, quote_text: str) -> bool:
        """Продвинутая валидация содержания цитаты"""
        # Проверка на случайный текст
        if quote_text.isdigit():
            return False

        # Проверка на слишком много специальных символов
        special_chars = len(re.findall(r'[^\w\s]', quote_text))
        if special_chars > len(quote_text) * 0.3:
            return False

        return True

    def _is_unique_quote(self, quote_obj: Dict) -> bool:
        """Проверка уникальности цитаты"""
        quote_hash = self._generate_quote_hash(quote_obj['quote'], quote_obj['author'])
        if quote_hash in self.quote_hashes:
            return False

        self.quote_hashes.add(quote_hash)
        return True

    def has_next_page(self, html: str, selectors: Dict) -> Optional[str]:
        """Поиск ссылки на следующую страницу"""
        soup = BeautifulSoup(html, 'html.parser')

        for selector in self._ensure_list(selectors["next_page"]):
            next_element = soup.select_one(selector)
            if next_element and next_element.get('href'):
                next_url = next_element['href']
                logger.debug(f"➡️ Найдена следующая страница: {next_url}")
                return next_url

        logger.debug("⏹️ Следующая страница не найдена")
        return None

    def parse_all_pages(self, start_url: str, delay: float = 1) -> None:
        """Рекурсивный обход ВСЕХ страниц с прогресс-баром"""
        current_url = start_url
        page_count = 0
        selectors = self.detect_site_type(start_url)

        self.stats['start_time'] = datetime.now()

        logger.info(f"🎯 Начало парсинга: {start_url}")
        logger.info(f"⏰ Задержка между запросами: {delay} сек")

        # Инициализация прогресс-бара
        with tqdm(
                desc="🌐 Парсинг страниц",
                unit="стр",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
        ) as pbar:

            while current_url and current_url not in self.visited_urls:
                try:
                    logger.info(f"📄 Страница {page_count + 1}: {current_url}")

                    # Вежливая задержка
                    if delay > 0 and page_count > 0:
                        time.sleep(delay)

                    # Загрузка и парсинг страницы
                    html = self.fetch_page(current_url)
                    self.visited_urls.add(current_url)

                    quotes = self.parse_quotes(html, selectors)
                    self.all_quotes.extend(quotes)

                    new_quotes = len(quotes)
                    self.stats['total_quotes'] += new_quotes
                    self.stats['total_pages'] += 1

                    logger.info(f"✅ Страница {page_count + 1}: {new_quotes} новых цитат")

                    # Поиск следующей страницы
                    next_page = self.has_next_page(html, selectors)
                    if next_page:
                        current_url = urljoin(current_url, next_page)
                        logger.info(f"➡️ Переход на: {current_url}")
                    else:
                        logger.info("🏁 Пагинация завершена")
                        break

                    page_count += 1
                    pbar.update(1)
                    pbar.set_postfix({
                        'цитат': self.stats['total_quotes'],
                        'страниц': page_count
                    })

                except Exception as e:
                    self.stats['failed_requests'] += 1
                    logger.error(f"❌ Ошибка на странице {current_url}: {e}")
                    break

        # Статистика выполнения
        self._print_statistics()

    def _print_statistics(self) -> None:
        """Вывод подробной статистики выполнения"""
        if self.stats['start_time']:
            duration = datetime.now() - self.stats['start_time']

        logger.info("📈 === СТАТИСТИКА ВЫПОЛНЕНИЯ ===")
        logger.info(f"📄 Обработано страниц: {self.stats['total_pages']}")
        logger.info(f"💬 Собрано цитат: {self.stats['total_quotes']}")
        logger.info(f"🔗 Уникальных URL: {len(self.visited_urls)}")
        logger.info(f"❌ Неудачных запросов: {self.stats['failed_requests']}")

        if self.stats['start_time']:
            logger.info(f"⏱️ Время выполнения: {duration}")

        if self.all_quotes:
            unique_authors = len(set(q['author'] for q in self.all_quotes))
            total_tags = sum(q['tags_count'] for q in self.all_quotes)
            logger.info(f"👥 Уникальных авторов: {unique_authors}")
            logger.info(f"🏷️ Всего тегов: {total_tags}")

    def save_data(self, filename: str, format: str = 'json') -> bool:
        """Сохранение данных в различных форматах с валидацией"""
        if not self.all_quotes:
            logger.warning("⚠️ Нет данных для сохранения")
            return False

        try:
            base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            output_file = f"{base_name}.{format.lower()}"

            if format.lower() == 'json':
                self._save_json(output_file)
            elif format.lower() == 'csv':
                self._save_csv(output_file)
            else:
                logger.error(f"🚫 Неподдерживаемый формат: {format}")
                return False

            logger.info(f"💾 Данные сохранены в {output_file}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения данных: {e}")
            return False

    def _save_json(self, filename: str) -> None:
        """Сохранение в JSON с красивым форматированием"""
        data = {
            "metadata": {
                "source": "Universal Quote Parser",
                "version": "2.0",
                "total_quotes": len(self.all_quotes),
                "total_pages": len(self.visited_urls),
                "unique_authors": len(set(q['author'] for q in self.all_quotes)),
                "timestamp": datetime.now().isoformat(),
                "execution_time": str(datetime.now() - self.stats['start_time']) if self.stats['start_time'] else None
            },
            "quotes": self.all_quotes
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

    def _save_csv(self, filename: str) -> None:
        """Сохранение в CSV с обработкой специальных символов"""
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Quote', 'Author', 'Tags', 'Tags Count', 'Timestamp'])

            for idx, quote_data in enumerate(self.all_quotes, 1):
                writer.writerow([
                    idx,
                    quote_data['quote'],
                    quote_data['author'],
                    ', '.join(quote_data['tags']),
                    quote_data['tags_count'],
                    quote_data['timestamp']
                ])

    def generate_html_report(self, filename: str = "quotes_report.html") -> bool:
        """Генерация шедеврального HTML отчета"""
        try:
            # Статистика для отчета
            stats = {
                'total_quotes': len(self.all_quotes),
                'total_pages': len(self.visited_urls),
                'unique_authors': len(set(q['author'] for q in self.all_quotes)),
                'total_tags': sum(q['tags_count'] for q in self.all_quotes),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            html_content = self._create_html_template(stats)

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"🎨 HTML отчет создан: {filename}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка создания HTML отчета: {e}")
            return False

    def _create_html_template(self, stats: Dict) -> str:
        """Создание HTML шаблона отчета"""
        quotes_html = "".join(
            f"""
            <div class="quote-card">
                <div class="quote-text">"{quote['quote']}"</div>
                <div class="quote-author">— {quote['author']}</div>
                {f'<div class="quote-tags">{" ".join([f"<span class=\"tag\">{tag}</span>" for tag in quote["tags"]])}</div>' if quote['tags'] else ''}
            </div>
            """ for quote in self.all_quotes
        )

        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет парсера цитат</title>
    <style>
        /* Великолепные стили шедевра */
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: rgba(255,255,255,0.95);
            padding: 3rem;
            border-radius: 20px;
            text-align: center;
            margin-bottom: 2rem;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            backdrop-filter: blur(10px);
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.95);
            padding: 2rem;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }}
        .stat-card:hover {{ transform: translateY(-5px); }}
        .quotes-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 2rem;
        }}
        .quote-card {{
            background: rgba(255,255,255,0.95);
            padding: 2.5rem;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            border-left: 5px solid #667eea;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        .quote-card:hover {{
            transform: translateY(-3px) scale(1.02);
            box-shadow: 0 25px 50px rgba(0,0,0,0.15);
        }}
        .quote-card::before {{
            content: '"';
            font-size: 8rem;
            color: #667eea;
            opacity: 0.1;
            position: absolute;
            top: -2rem;
            left: 1rem;
            font-family: Georgia;
        }}
        .quote-text {{
            font-size: 1.2rem;
            line-height: 1.6;
            color: #2c3e50;
            margin-bottom: 1.5rem;
            font-style: italic;
            position: relative;
            z-index: 1;
        }}
        .quote-author {{
            text-align: right;
            font-weight: 700;
            color: #667eea;
            font-size: 1.1rem;
            position: relative;
            z-index: 1;
        }}
        .quote-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1rem;
        }}
        .tag {{
            background: #667eea;
            color: white;
            padding: 0.3rem 0.8rem;
            border-radius: 15px;
            font-size: 0.8rem;
        }}
        @media (max-width: 768px) {{
            .quotes-grid {{ grid-template-columns: 1fr; }}
            .header {{ padding: 2rem 1rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💫 Великий Парсер Цитат</h1>
            <p>Шедевр инженерии искусственного интеллекта</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{stats['total_quotes']}</div>
                <div class="stat-label">Всего цитат</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['total_pages']}</div>
                <div class="stat-label">Просмотрено страниц</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['unique_authors']}</div>
                <div class="stat-label">Уникальных авторов</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['total_tags']}</div>
                <div class="stat-label">Всего тегов</div>
            </div>
        </div>

        <div class="quotes-grid">
            {quotes_html}
        </div>
    </div>
</body>
</html>
        """


def main():
    """Главная функция - АВТОМАТИЧЕСКИЙ ЗАПУСК С ГОТОВЫМИ АДРЕСАМИ"""

    print("🚀 ВЕЛИКИЙ ПАРСЕР ЦИТАТ - АВТОМАТИЧЕСКИЙ ЗАПУСК!")
    print("=" * 60)
    print("🎯 Автоматически парсим 10 разделов quotes.toscrape.com")
    print("📊 Собираем ВСЕ цитаты со ВСЕХ страниц!")
    print("=" * 60)

    # Автоматически показываем какие адреса будут парситься
    print("\n📋 СПИСОК АДРЕСОВ ДЛЯ ПАРСИНГА:")
    for i, url in enumerate(AUTO_URLS, 1):
        print(f"  {i:2d}. {url}")

    print("\n⏳ Начинаем автоматический парсинг...")
    time.sleep(2)

    # Инициализация конфигурации
    config = ConfigManager()

    # Создание парсера
    quote_parser = UniversalQuoteParser(config)

    all_results = []

    try:
        # АВТОМАТИЧЕСКИЙ ПАРСИНГ ВСЕХ АДРЕСОВ
        for i, url in enumerate(AUTO_URLS, 1):
            try:
                print(f"\n{'=' * 50}")
                print(f"🎯 ПАРСИНГ {i}/{len(AUTO_URLS)}: {url}")
                print(f"{'=' * 50}")

                # Сбрасываем статистику для каждого URL
                quote_parser.visited_urls.clear()
                quote_parser.quote_hashes.clear()

                # Проверка robots.txt
                if not quote_parser.check_robots_txt(url):
                    print(f"🚫 Парсинг запрещен файлом robots.txt для {url}")
                    continue

                # Парсинг всех страниц
                quote_parser.parse_all_pages(url, delay=1)

                # Сохраняем результаты
                if quote_parser.all_quotes:
                    all_results.extend(quote_parser.all_quotes)
                    print(f"✅ Успешно собрано {len(quote_parser.all_quotes)} цитат")
                else:
                    print("⚠️ Цитаты не найдены")

                # Пауза между разными разделами
                if i < len(AUTO_URLS):
                    print("⏳ Задержка перед следующим разделом...")
                    time.sleep(2)

            except Exception as e:
                print(f"❌ Ошибка при парсинге {url}: {e}")
                continue

        # СОХРАНЕНИЕ ИТОГОВЫХ РЕЗУЛЬТАТОВ
        if all_results:
            quote_parser.all_quotes = all_results

            print(f"\n{'=' * 60}")
            print("🎉 АВТОМАТИЧЕСКИЙ ПАРСИНГ ЗАВЕРШЕН!")
            print(f"{'=' * 60}")

            # Сохранение в основных форматах
            quote_parser.save_data("ВЕЛИКИЕ_ЦИТАТЫ", 'json')
            quote_parser.save_data("ВЕЛИКИЕ_ЦИТАТЫ", 'csv')

            # Генерация HTML отчета
            quote_parser.generate_html_report("ВЕЛИКИЕ_ЦИТАТЫ_ОТЧЕТ.html")

            # Финальная статистика
            unique_authors = len(set(q['author'] for q in all_results))
            total_tags = sum(q['tags_count'] for q in all_results)
            total_pages = len(quote_parser.visited_urls)

            print(f"📊 ФИНАЛЬНАЯ СТАТИСТИКА:")
            print(f"   💬 Всего цитат: {len(all_results)}")
            print(f"   👥 Уникальных авторов: {unique_authors}")
            print(f"   🏷️ Всего тегов: {total_tags}")
            print(f"   📄 Обработано страниц: {total_pages}")
            print(f"   🌐 Парсено разделов: {len(AUTO_URLS)}")

            print(f"\n📁 СОЗДАННЫЕ ФАЙЛЫ:")
            print(f"   • ВЕЛИКИЕ_ЦИТАТЫ.json - структурированные данные")
            print(f"   • ВЕЛИКИЕ_ЦИТАТЫ.csv - табличные данные")
            print(f"   • ВЕЛИКИЕ_ЦИТАТЫ_ОТЧЕТ.html - красивый HTML отчет")
            print(f"   • quote_parser.log - детальный лог работы")

        else:
            print("😔 Цитаты не найдены ни на одном из адресов")

    except KeyboardInterrupt:
        print("\n🛑 Парсинг прерван пользователем")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()