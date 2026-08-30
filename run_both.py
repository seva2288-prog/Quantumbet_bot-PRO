#!/usr/bin/env python3
"""
Запускает бота и веб-интерфейс одновременно
"""

import subprocess
import sys
import time
import os
import signal
import platform

def print_banner():
    """Печатает баннер"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🚀 QUANTUM BET BOT - ЗАПУСК                               ║
║                                                              ║
║   Бот:            http://localhost:5000                     ║
║   Веб-интерфейс:  http://localhost:5001                     ║
║                                                              ║
║   Нажмите Ctrl+C для остановки                              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)

def run_apps():
    """Запускает оба приложения"""
    print_banner()
    
    # Проверяем наличие файлов
    if not os.path.exists('main.py'):
        print("❌ Ошибка: main.py не найден!")
        sys.exit(1)
    
    if not os.path.exists('web_app.py'):
        print("❌ Ошибка: web_app.py не найден!")
        sys.exit(1)
    
    # Определяем команду python
    python_cmd = sys.executable
    
    print(f"🐍 Python: {python_cmd}")
    print(f"📁 Директория: {os.getcwd()}")
    print()
    
    # Запускаем бота
    print("📡 Запуск бота (порт 5000)...")
    bot_process = subprocess.Popen(
        [python_cmd, 'main.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    time.sleep(1)
    
    # Запускаем веб-интерфейс
    print("🌐 Запуск веб-интерфейса (порт 5001)...")
    web_process = subprocess.Popen(
        [python_cmd, 'web_app.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print()
    print("✅ Оба приложения запущены!")
    print("📊 Бот: http://localhost:5000")
    print("🌐 Веб-интерфейс: http://localhost:5001")
    print()
    print("🛑 Нажмите Ctrl+C для остановки")
    print("-" * 60)
    
    # Функция для чтения логов
    def print_logs(process, name):
        while True:
            try:
                line = process.stdout.readline()
                if line:
                    print(f"[{name}] {line.strip()}")
            except:
                break
    
    # Запускаем чтение логов в отдельных потоках
    import threading
    bot_thread = threading.Thread(target=print_logs, args=(bot_process, "BOT"))
    web_thread = threading.Thread(target=print_logs, args=(web_process, "WEB"))
    bot_thread.daemon = True
    web_thread.daemon = True
    bot_thread.start()
    web_thread.start()
    
    try:
        # Ждем завершения процессов
        while True:
            time.sleep(1)
            # Проверяем, живы ли процессы
            if bot_process.poll() is not None:
                print("⚠️ Бот остановился!")
                break
            if web_process.poll() is not None:
                print("⚠️ Веб-интерфейс остановился!")
                break
    except KeyboardInterrupt:
        print()
        print("🛑 Останавливаем приложения...")
    
    # Останавливаем процессы
    print("🛑 Завершение процессов...")
    
    # Пытаемся завершить gracefully
    if bot_process.poll() is None:
        bot_process.terminate()
    
    if web_process.poll() is None:
        web_process.terminate()
    
    time.sleep(1)
    
    # Если не завершились, убиваем
    if bot_process.poll() is None:
        bot_process.kill()
    
    if web_process.poll() is None:
        web_process.kill()
    
    print("✅ Все процессы остановлены")
    print("👋 До свидания!")

if __name__ == '__main__':
    try:
        run_apps()
    except KeyboardInterrupt:
        print()
        print("🛑 Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
