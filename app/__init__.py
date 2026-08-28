from app.config import Config

# Проверка конфигурации при запуске
try:
    Config.check()
    print("✅ Конфигурация загружена успешно")
except ValueError as e:
    print(f"❌ Ошибка конфигурации:\n{e}")
    exit(1)  # ← exit() только здесь, если ошибка
