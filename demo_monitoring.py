"""
Демонстрация работы системы мониторинга
"""
import sqlite3
import os

def demo():
    print("\n" + "="*70)
    print("🎓 ДЕМОНСТРАЦИЯ СИСТЕМЫ МОНИТОРИНГА")
    print("="*70)
    
    # Проверяем БД
    if not os.path.exists("query_history.db"):
        print("\n⚠️ База данных еще не создана.")
        print("📝 Сделайте запрос в боте, чтобы создать БД.")
        return
    
    conn = sqlite3.connect("query_history.db")
    cursor = conn.cursor()
    
    # 1. Общая статистика
    print("\n📊 1. ОБЩАЯ СТАТИСТИКА")
    print("-"*70)
    
    cursor.execute("SELECT COUNT(*) FROM queries")
    total_queries = cursor.fetchone()[0]
    print(f"Всего запросов: {total_queries}")
    
    cursor.execute("SELECT COUNT(*) FROM query_results")
    total_results = cursor.fetchone()[0]
    print(f"Всего результатов: {total_results}")
    
    cursor.execute("""
        SELECT AVG(ai_relevance) 
        FROM query_results 
        WHERE ai_relevance > 0
    """)
    avg_rel = cursor.fetchone()[0]
    if avg_rel:
        print(f"Средняя AI релевантность: {avg_rel:.2f}/100")
        
        if avg_rel >= 80:
            print("✅ Отлично! Система работает идеально")
        elif avg_rel >= 60:
            print("🟡 Хорошо, есть что улучшить")
        else:
            print("🔴 Нужны улучшения")
    
    # 2. Детали последнего запроса
    print("\n🔍 2. ПОСЛЕДНИЙ ЗАПРОС (ДЕТАЛИ)")
    print("-"*70)
    
    cursor.execute("""
        SELECT id, query_text, model_type, expanded_query, timestamp
        FROM queries
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    if row:
        query_id, query_text, model_type, expanded_query, timestamp = row
        
        print(f"ID: {query_id}")
        print(f"Запрос: {query_text[:60]}...")
        print(f"Модель: {model_type}")
        print(f"Время: {timestamp}")
        
        if expanded_query:
            print(f"Расширенный запрос: {expanded_query[:80]}...")
        
        # Результаты
        cursor.execute("""
            SELECT startup_name, rag_similarity, ai_relevance, cluster
            FROM query_results
            WHERE query_id = ?
            ORDER BY position ASC
        """, (query_id,))
        
        results = cursor.fetchall()
        if results:
            print(f"\n📊 Результаты ({len(results)} стартапов):")
            print(f"{'#':<3} {'Название':<30} {'RAG':<8} {'AI':<8} {'Δ':<10}")
            print("-"*70)
            
            for i, (name, rag, ai, cluster) in enumerate(results, 1):
                if rag and ai:
                    rag_norm = rag * 100
                    diff = ai - rag_norm
                    
                    if diff > 10:
                        emoji = "📈 Улучш"
                    elif diff < -10:
                        emoji = "📉 Исправ"
                    else:
                        emoji = "➡️ Совпад"
                    
                    print(f"{i:<3} {name[:30]:<30} {rag_norm:6.1f}% {ai:6.1f}% "
                          f"{emoji} {diff:+5.0f}")
                else:
                    print(f"{i:<3} {name[:30]:<30} {'N/A':<8} "
                          f"{ai if ai else 'N/A':<8}")
            
            # Анализ
            ai_scores = [ai for _, _, ai, _ in results if ai]
            if ai_scores:
                avg_ai = sum(ai_scores) / len(ai_scores)
                print(f"\nСредняя AI релевантность этого запроса: {avg_ai:.1f}/100")
    
    # 3. Объяснение метрик
    print("\n📖 3. ОБЪЯСНЕНИЕ МЕТРИК")
    print("-"*70)
    print("""
RAG Similarity (0.000 - 1.000):
  • Сходство текстов по embeddings (векторам)
  • Быстрый, но не всегда точный
  • Пример: "переработка древесины" ≈ "переработка пластика" (0.87)

AI Relevance (0 - 100):
  • GigaChat оценивает контекст и смысл
  • Медленный, но точный
  • Пример: "переработка древесины" для запроса "пластик" → 55

Δ (Дельта) = AI - RAG:
  📈 +10 и выше = Re-ranking улучшил оценку
  📉 -10 и ниже = Re-ranking исправил ошибку RAG
  ➡️ -5 до +5   = Оценки совпали

ВЫВОД:
  Если видите 📉 с большим числом → Это ХОРОШО!
  Значит Re-ranking исправил ошибку RAG.
    """)
    
    # 4. Рекомендации
    print("\n💡 4. РЕКОМЕНДАЦИИ")
    print("-"*70)
    
    if avg_rel and avg_rel < 60:
        print("🔴 Низкая средняя релевантность!")
        print("   Действия:")
        print("   1. Проверьте логи: notepad terminals\\11.txt")
        print("   2. Добавьте few-shot примеры в services/few_shot_examples.py")
        print("   3. Уточните запросы (добавьте контекст)")
    elif avg_rel and avg_rel < 80:
        print("🟡 Хорошая релевантность, но можно улучшить:")
        print("   1. Накапливайте больше запросов (цель: 50+)")
        print("   2. Добавляйте специфические few-shot примеры")
        print("   3. Анализируйте худшие совпадения")
    else:
        print("✅ Отличная релевантность!")
        print("   Система работает идеально. Продолжайте в том же духе.")
    
    print("\n📚 Дополнительная информация:")
    print("   • QUICK_START.md - Быстрый старт за 60 секунд")
    print("   • HOW_IT_WORKS.md - Подробное объяснение")
    print("   • README_MONITORING.md - Полное руководство по мониторингу")
    
    conn.close()
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    demo()

