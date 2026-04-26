import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)

async def find_working_proxy():
    """
    Автоматический поиск бесплатного рабочего HTTP прокси для обхода блокировок Telegram (РФ).
    """
    logger.info("🔍 Поиск бесплатного рабочего HTTP прокси...")
    
    # Популярные репозитории с постоянно обновляемыми бесплатными HTTP прокси
    urls = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/yemreakbulut/pt-proxy-list/main/http.txt"
    ]
    
    proxies = []
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        proxies.extend(text.strip().split('\n')[:300])
            except Exception as e:
                logger.warning(f"Не удалось загрузить список прокси с {url}: {e}")
                continue
                
    if not proxies:
        logger.error("❌ Списки прокси недоступны.")
        return None
        
    # Очищаем пустые строки
    proxies = [p for p in set(proxies) if p.strip()]
    logger.info(f"✅ Загружено {len(proxies)} HTTP прокси для проверки. Тестируем соединение с Telegram API...")
    
    async def check_proxy(proxy_addr):
        proxy_url = f"http://{proxy_addr.strip()}"
        try:
            # Обязательно выставляем timeout, так как 90% бесплатных прокси не работают
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.telegram.org/bot", proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    # 401 или 404 означает, что мы успешно достучались до серверов Telegram!
                    if resp.status in (401, 404, 200):
                        return proxy_url
        except Exception:
            return None

    # Проверяем пачками по 30 штук асинхронно
    for i in range(0, min(150, len(proxies)), 30):
        batch = proxies[i:i+30]
        tasks = [check_proxy(p) for p in batch]
        for future in asyncio.as_completed(tasks):
            result = await future
            if result:
                logger.info(f"🚀 Найден быстрый и рабочий прокси: {result}")
                return result
                
    logger.error("❌ Не удалось найти рабочий прокси.")
    return None