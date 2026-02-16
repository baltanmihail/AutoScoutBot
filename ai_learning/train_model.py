"""
Скрипт для запуска самообучения
Запуск: python ai_learning/train_model.py
"""
import logging
import sys
import os

# Добавляем родительскую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_learning.self_learning import SelfLearningEngine

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("=" * 70)
    print("🧠 САМООБУЧЕНИЕ AUTOSCOUTBOT")
    print("=" * 70)
    print()
    
    # Проверяем наличие БД
    if not os.path.exists("query_history.db"):
        print("❌ База данных query_history.db не найдена!")
        print("📝 Сделайте несколько запросов в боте, чтобы создать БД.")
        return
    
    # Инициализация
    engine = SelfLearningEngine(min_samples=3)  # Минимум 3 запроса для паттерна
    
    print("📊 Анализирую накопленные данные...")
    print()
    
    # Запуск самообучения
    report = engine.analyze_and_learn()
    
    # Вывод отчета
    print("=" * 70)
    print("📈 ОТЧЕТ О САМООБУЧЕНИИ")
    print("=" * 70)
    
    if "error" in report:
        print(f"❌ Ошибка: {report['error']}")
        return
    
    print(f"🔍 Выявлено паттернов: {report['patterns_discovered']}")
    print(f"📝 Обновлено паттернов: {report['patterns_updated']}")
    print(f"🔤 Сгенерировано синонимов: {report['synonyms_generated']}")
    print(f"📚 Создано few-shot примеров: {report['few_shot_created']}")
    print()
    
    if report["recommendations"]:
        print("💡 РЕКОМЕНДАЦИИ:")
        print("-" * 70)
        for i, rec in enumerate(report["recommendations"], 1):
            print(f"{i}. {rec}")
        print()
    
    # Экспорт для fine-tuning
    print("=" * 70)
    print("🚀 ЭКСПОРТ ДЛЯ FINE-TUNING")
    print("=" * 70)
    
    exported = engine.export_for_finetuning()
    
    if exported > 0:
        print(f"✅ Экспортировано {exported} примеров в finetuning_dataset.jsonl")
        print()
        print("📖 Следующие шаги для fine-tuning GigaChat:")
        print("1. Проверьте документацию GigaChat про fine-tuning")
        print("2. Загрузите finetuning_dataset.jsonl через API")
        print("3. Дождитесь завершения обучения")
        print("4. Обновите model_name в config.py")
    else:
        print(f"⚠️ Недостаточно данных для fine-tuning ({exported}/100)")
        print("📝 Накопите минимум 100 качественных примеров")
    
    print()
    print("=" * 70)
    print("✅ САМООБУЧЕНИЕ ЗАВЕРШЕНО")
    print("=" * 70)
    print()
    print("💡 Рекомендация: Запускайте этот скрипт раз в неделю")
    print("   для автоматического улучшения системы!")
    print()

if __name__ == "__main__":
    main()

