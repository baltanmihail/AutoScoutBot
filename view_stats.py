"""
Просмотр статистики AutoScoutBot
Запуск: python view_stats.py
"""
import sqlite3
from services.query_history import QueryHistory
import os

def main():
    # Проверяем существование БД
    if not os.path.exists("query_history.db"):
        print("⚠️ База данных query_history.db не найдена.")
        print("📝 БД будет создана автоматически при первом запросе в боте.")
        return
    
    # Инициализация
    qh = QueryHistory()
    
    # Общая статистика
    stats = qh.get_statistics()
    
    print("=" * 60)
    print("📊 СТАТИСТИКА AUTOSCOUTBOT")
    print("=" * 60)
    print(f"Всего запросов: {stats['total_queries']}")
    print(f"Всего результатов: {stats['total_results']}")
    
    if stats['total_results'] > 0:
        print(f"Средняя AI релевантность: {stats['avg_relevance']:.2f}/100")
    else:
        print("Средняя AI релевантность: Нет данных")
    print()
    
    if stats['top_clusters']:
        print("🔥 ТОП-5 КЛАСТЕРОВ:")
        for item in stats['top_clusters']:
            print(f"  • {item['cluster']}: {item['count']} результатов")
        print()
    
    # Последние 10 запросов
    conn = sqlite3.connect("query_history.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, query_text, model_type, timestamp
        FROM queries
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    
    rows = cursor.fetchall()
    if rows:
        print("📝 ПОСЛЕДНИЕ 10 ЗАПРОСОВ:")
        for row in rows:
            query_text = row[1][:50] + "..." if len(row[1]) > 50 else row[1]
            print(f"  [{row[0]:3d}] {query_text:50s} ({row[2]}, {row[3][:16]})")
        print()
    
    # Лучшие результаты (AI relevance > 80)
    cursor.execute("""
        SELECT q.query_text, r.startup_name, r.ai_relevance, r.cluster
        FROM queries q
        JOIN query_results r ON q.id = r.query_id
        WHERE r.ai_relevance >= 80
        ORDER BY r.ai_relevance DESC
        LIMIT 10
    """)
    
    rows = cursor.fetchall()
    if rows:
        print("⭐ ТОП-10 ЛУЧШИХ СОВПАДЕНИЙ (AI ≥ 80):")
        for row in rows:
            query_text = row[0][:40] + "..." if len(row[0]) > 40 else row[0]
            print(f"  • {row[1]:30s} → \"{query_text}\" (AI={row[2]:.0f}, {row[3]})")
        print()
    
    # Худшие результаты (для анализа)
    cursor.execute("""
        SELECT q.query_text, r.startup_name, r.ai_relevance, r.cluster
        FROM queries q
        JOIN query_results r ON q.id = r.query_id
        WHERE r.ai_relevance > 0 AND r.ai_relevance < 50
        ORDER BY r.ai_relevance ASC
        LIMIT 5
    """)
    
    rows = cursor.fetchall()
    if rows:
        print("⚠️ ХУДШИЕ СОВПАДЕНИЯ (AI < 50) - Нужно улучшить:")
        for row in rows:
            query_text = row[0][:40] + "..." if len(row[0]) > 40 else row[0]
            print(f"  • {row[1]:30s} → \"{query_text}\" (AI={row[2]:.0f}, {row[3]})")
        print()
    
    conn.close()
    print("=" * 60)

if __name__ == "__main__":
    main()

