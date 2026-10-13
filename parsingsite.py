import argparse
import asyncio
import os
import re
from urllib.parse import unquote, urlparse
from playwright.async_api import async_playwright
from tqdm import tqdm


class WebsiteDownloader:

    def __init__(self, target_url, output_dir=None):
        self.target_url = target_url
        self.target_domain = urlparse(target_url).netloc
        self.output_dir = output_dir or self.target_domain
        self.downloaded_count = 0
        self.pbar = None

    def clean_filename(self, path):
        """Очищает путь от запрещенных символов Windows, сохраняя структуру папок."""
        # Декодируем URL-символы вроде %20 в пробелы
        path = unquote(path)
        # Удаляем GET-параметры из имени файла (все что после '?')
        if "?" in path:
            path = path.split("?")[0]

        segments = path.split("/")
        cleaned_segments = []
        for seg in segments:
            # Очищаем каждый сегмент пути от запрещенных в Windows символов
            clean_seg = re.sub(r'[\\*?:"<>|]', "", seg).strip()
            if clean_seg:
                cleaned_segments.append(clean_seg)

        return "/".join(cleaned_segments)

    async def save_file(self, url, response):
        """Перехватывает и сохраняет файл на диск."""
        try:
            parsed_url = urlparse(url)

            # Скачиваем файлы только с целевого домена (чтобы не качать рекламу и метрики)
            if parsed_url.netloc != self.target_domain:
                return

            # Игнорируем пустые или некорректные ответы
            if response.status < 200 or response.status >= 300:
                return

            body = await response.body()
            if not body:
                return

            # Формируем путь для сохранения внутри папки проекта
            local_path = parsed_url.path
            if not local_path or local_path.endswith("/"):
                local_path += "index.html"

            # Очищаем путь под требования Windows
            clean_local_path = self.clean_filename(local_path)
            full_path = os.path.join(self.output_dir, clean_local_path)

            # Создаем необходимые подпапки
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            # Сохраняем файл
            with open(full_path, "wb") as f:
                f.write(body)

            self.downloaded_count += 1
            if self.pbar:
                self.pbar.update(1)
                self.pbar.set_postfix_str(
                    f"Файлов: {self.downloaded_count}", refresh=True
                )

        except Exception:
            # Тихо пропускаем ошибки чтения битых или заблокированных запросов
            pass

    async def download_site(self):
        """Запуск браузера и сбор всех ресурсов сайта."""
        print(f"[INFO] Запуск мощного скачивания для сайта: {self.target_url}")
        print(f"[INFO] Локальная копия будет сохранена в папку: {self.output_dir}")

        self.pbar = tqdm(
            desc="Загрузка ресурсов сайта", unit=" файл", leave=True
        )

        async with async_playwright() as p:
            # Запуск Chrome в фоновом режиме
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            # Вешаем обработчик на ЛЮБОЙ сетевой ответ от сервера
            page.on(
                "response",
                lambda response: asyncio.create_task(
                    self.save_file(response.url, response)
                ),
            )

            try:
                # Переходим на сайт
                await page.goto(
                    self.target_url, timeout=60000, wait_until="commit"
                )

                # Медленный умный скролл вниз, чтобы активировать все скрипты и Lazy-Load картинки
                print("\n[INFO] Сканируем и прокручиваем страницу до низа...")
                current_scroll = 0
                max_scroll = await page.evaluate("document.body.scrollHeight")

                while current_scroll < max_scroll:
                    current_scroll += 300
                    await page.evaluate(f"window.scrollTo(0, {current_scroll})")
                    await asyncio.sleep(0.2)  # Даем время на подгрузку
                    max_scroll = await page.evaluate(
                        "document.body.scrollHeight"
                    )

                # Финальное ожидание завершения фоновых запросов
                await asyncio.sleep(5)

                # Принудительно сохраняем финальный отрендеренный HTML-код главной страницы
                final_html = await page.content()
                index_file = os.path.join(self.output_dir, "index.html")
                os.makedirs(os.path.dirname(index_file), exist_ok=True)
                with open(index_file, "w", encoding="utf-8") as f:
                    f.write(final_html)

            except Exception as e:
                print(f"\n[ERROR] Ошибка во время выполнения: {e}")
            finally:
                await context.close()
                await browser.close()

        self.pbar.close()
        print(
            f"\n[SUCCESS] Готово! Всего успешно скачано файлов: {self.downloaded_count}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Мощный дампер сайтов (HTML, CSS, JS, Картинки, Шрифты)"
    )
    parser.add_argument("url", help="URL сайта, который нужно выкачать целиком.")
    parser.add_argument(
        "-p",
        "--path",
        help="Путь к папке сохранения (по умолчанию имя домена)",
    )

    args = parser.parse_args()

    # Запуск асинхронного движка
    downloader = WebsiteDownloader(args.url, args.path)
    asyncio.run(downloader.download_site())
