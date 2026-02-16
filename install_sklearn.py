"""
Скрипт для установки scikit-learn
Запустите: python install_sklearn.py
"""
import subprocess
import sys

print("🔄 Установка scikit-learn...")
print("=" * 50)

try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "scikit-learn"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    if result.returncode == 0:
        print("=" * 50)
        print("✅ scikit-learn успешно установлен!")
        print("\nТеперь можно:")
        print("1. Перезапустить бота")
        print("2. RAG-система автоматически активируется")
        print("3. При первом запуске создастся индекс (5-10 минут)")
    else:
        print("=" * 50)
        print("❌ Ошибка установки")
        print(f"Код возврата: {result.returncode}")
except Exception as e:
    print(f"❌ Ошибка: {e}")

input("\nНажмите Enter для выхода...")

