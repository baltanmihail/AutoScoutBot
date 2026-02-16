"""
Continuous Learning - Непрерывное обучение в фоновом режиме
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from services.self_learning import SelfLearningEngine

logger = logging.getLogger(__name__)

class ContinuousLearner:
    """
    Непрерывное обучение в фоновом режиме
    
    Автоматически запускает самообучение:
    - Каждые N запросов
    - Каждые N часов
    - При достижении порогов
    """
    
    def __init__(self, 
                 queries_threshold: int = 20,  # Каждые 20 запросов
                 hours_interval: int = 24):     # Каждые 24 часа
        self.queries_threshold = queries_threshold
        self.hours_interval = hours_interval
        self.last_training_time = datetime.now()
        self.queries_since_training = 0
        self.is_running = False
        self.thread = None
        self.engine = SelfLearningEngine(min_samples=3)
    
    def start(self):
        """Запуск фонового обучения"""
        if self.is_running:
            logger.warning("Continuous learning уже запущен")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._learning_loop, daemon=True)
        self.thread.start()
        logger.info("✅ Continuous learning запущен")
    
    def stop(self):
        """Остановка фонового обучения"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("⏹️ Continuous learning остановлен")
    
    def notify_new_query(self):
        """Уведомление о новом запросе"""
        self.queries_since_training += 1
        
        # Проверяем, пора ли обучаться
        if self.queries_since_training >= self.queries_threshold:
            logger.info(f"🧠 Накоплено {self.queries_since_training} запросов. Запуск обучения...")
            self._train()
    
    def _learning_loop(self):
        """Цикл фонового обучения"""
        while self.is_running:
            try:
                # Проверяем временной интервал
                time_since_training = datetime.now() - self.last_training_time
                
                if time_since_training >= timedelta(hours=self.hours_interval):
                    logger.info(f"⏰ Прошло {self.hours_interval} часов. Запуск обучения...")
                    self._train()
                
                # Спим 1 час
                time.sleep(3600)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле обучения: {e}")
                time.sleep(3600)
    
    def _train(self):
        """Запуск обучения"""
        try:
            report = self.engine.analyze_and_learn()
            
            logger.info(f"📊 Обучение завершено: "
                       f"паттернов={report['patterns_discovered']}, "
                       f"примеров={report['few_shot_created']}")
            
            # Сбрасываем счетчики
            self.queries_since_training = 0
            self.last_training_time = datetime.now()
            
            # Экспортируем для fine-tuning если достаточно данных
            exported = self.engine.export_for_finetuning()
            if exported > 0:
                logger.info(f"💾 Экспортировано {exported} примеров для fine-tuning")
            
        except Exception as e:
            logger.error(f"Ошибка обучения: {e}")

# Глобальный экземпляр
_continuous_learner = None

def get_continuous_learner() -> ContinuousLearner:
    """Получить singleton экземпляр"""
    global _continuous_learner
    if _continuous_learner is None:
        _continuous_learner = ContinuousLearner(
            queries_threshold=20,  # Обучаться каждые 20 запросов
            hours_interval=24      # Или раз в сутки
        )
    return _continuous_learner

