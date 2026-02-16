"""
Анализ конкретного запроса
Запуск: python analyze_query.py <query_id>
"""
import sqlite3
import sys

def analyze_query(query_id):
    conn = sqlite3.connect("query_history.db")
    cursor = conn.cursor()
    
    # Информация о запросе
    cursor.execute("""
        SELECT query_text, model_type, expanded_query, timestamp, filters_used
        FROM queries
        WHERE id = ?
    """, (query_id,))
    
    row = cursor.fetchone()
    if not row:
        print(f"❌ Запрос с ID={query_id} не найден")
        conn.close()
        return
    
    print(f"\n{'='*70}")
    print(f"🔍 АНАЛИЗ ЗАПРОСА #{query_id}")
    print(f"{'='*70}")
    print(f"📝 Запрос: {row[0]}")
    print(f"🎯 Модель: {row[1]}")
    
    if row[2]:
        expanded = row[2][:100] + "..." if len(row[2]) > 100 else row[2]
        print(f"🔄 Расширенный: {expanded}")
    
    print(f"⏰ Время: {row[3]}")
    
    if row[4]:
        print(f"🔧 Фильтры: {row[4]}")
    
    print()
    
    # Результаты
    cursor.execute("""
        SELECT startup_name, rag_similarity, ai_relevance, position, cluster, technologies
        FROM query_results
        WHERE query_id = ?
        ORDER BY position ASC
    """, (query_id,))
    
    rows = cursor.fetchall()
    if not rows:
        print("⚠️ Результаты не найдены")
        conn.close()
        return
    
    print("📊 РЕЗУЛЬТАТЫ:")
    print(f"{'Поз':<4} {'Название':<25} {'Кластер':<15} {'RAG':<8} {'AI':<8} {'Δ':<6}")
    print("-" * 70)
    
    for row in rows:
        name, rag, ai, pos, cluster, technologies = row
        
        # Сравниваем RAG vs AI
        if rag and ai:
            rag_norm = rag * 100
            diff = ai - rag_norm
            
            # Эмодзи для визуализации
            if diff > 10:
                emoji = "📈"
            elif diff < -10:
                emoji = "📉"
            else:
                emoji = "➡️"
            
            print(f"{pos:<4} {name[:25]:<25} {cluster[:15]:<15} "
                  f"{rag_norm:6.1f}% {ai:6.1f}% {emoji} {diff:+5.0f}")
        else:
            print(f"{pos:<4} {name[:25]:<25} {cluster[:15]:<15} "
                  f"{'N/A':<8} {ai if ai else 'N/A':<8} {'N/A':<6}")
    
    print()
    
    # Анализ
    cursor.execute("""
        SELECT AVG(ai_relevance), MIN(ai_relevance), MAX(ai_relevance)
        FROM query_results
        WHERE query_id = ? AND ai_relevance > 0
    """, (query_id,))
    
    avg, min_rel, max_rel = cursor.fetchone()
    
    if avg:
        print("📈 МЕТРИКИ:")
        print(f"  • Средняя AI релевантность: {avg:.1f}/100")
        print(f"  • Минимум: {min_rel:.0f}/100")
        print(f"  • Максимум: {max_rel:.0f}/100")
        
        if avg >= 80:
            print("  ✅ Отличные результаты!")
        elif avg >= 60:
            print("  ✓ Хорошие результаты")
        elif avg >= 40:
            print("  ⚠️ Средние результаты, можно улучшить")
        else:
            print("  ❌ Плохие результаты, нужно улучшение")
    
    print(f"{'='*70}\n")
    
    conn.close()

def list_recent_queries():
    """Показать последние запросы для выбора"""
    conn = sqlite3.connect("query_history.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, query_text, model_type, timestamp
        FROM queries
        ORDER BY timestamp DESC
        LIMIT 20
    """)
    
    print("\n" + "="*70)
    print("📝 ПОСЛЕДНИЕ 20 ЗАПРОСОВ:")
    print("="*70)
    print(f"{'ID':<5} {'Запрос':<45} {'Модель':<10} {'Время':<20}")
    print("-"*70)
    
    for row in cursor.fetchall():
        query_text = row[1][:45] + "..." if len(row[1]) > 45 else row[1]
        print(f"{row[0]:<5} {query_text:<45} {row[2]:<10} {row[3]:<20}")
    
    print("="*70)
    print("\nИспользование: python analyze_query.py <ID>")
    print("Пример: python analyze_query.py 15\n")
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("⚠️ Не указан ID запроса")
        list_recent_queries()
    else:
        try:
            query_id = int(sys.argv[1])
            analyze_query(query_id)
        except ValueError:
            print("❌ ID должен быть числом")
            list_recent_queries()

