from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def update_results_job():
    """Задача для обновления результатов"""
    try:
        from app.database.storage import storage
        from app.api.football import football_api
        from app.config import Config
        import requests
        
        logger.info("🔄 Автоматическое обновление результатов в 07:00...")
        
        history = storage.load_history()
        updated = 0
        
        for bet in history:
            if bet.get('result') == 'pending' or bet.get('result') is None:
                fixture_id = bet.get('fixture_id')
                
                if not fixture_id:
                    home = bet.get('home', '')
                    away = bet.get('away', '')
                    if home and away:
                        fixture_id = football_api.find_fixture_by_teams(home, away)
                        if fixture_id:
                            bet['fixture_id'] = fixture_id
                
                if fixture_id:
                    match_data = football_api.get_match_result(fixture_id)
                    if match_data:
                        home_goals = match_data['goals']['home']
                        away_goals = match_data['goals']['away']
                        
                        if home_goals is not None and away_goals is not None:
                            bet_type = bet.get('bet', '')
                            
                            total = home_goals + away_goals
                            bet_type_lower = bet_type.lower()
                            
                            if 'тм 2.5' in bet_type_lower or 'under' in bet_type_lower:
                                result = 'win' if total < 2.5 else 'loss'
                            elif 'тб 2.5' in bet_type_lower or 'over' in bet_type_lower:
                                result = 'win' if total > 2.5 else 'loss'
                            else:
                                result = 'pending'
                            
                            if result != 'pending':
                                bet['result'] = result
                                bet['home_goals'] = home_goals
                                bet['away_goals'] = away_goals
                                
                                if result == 'win':
                                    bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                                elif result == 'loss':
                                    bet['profit'] = -bet['stake']
                                else:
                                    bet['profit'] = 0
                                
                                updated += 1
                                logger.info(f"✅ Обновлена ставка: {bet['home']} vs {bet['away']} → {result} ({home_goals}-{away_goals})")
        
        if updated > 0:
            storage.save_history(history)
            
            stats = storage.load_stats()
            total = len(history)
            wins = sum(1 for b in history if b.get('result') == 'win')
            losses = sum(1 for b in history if b.get('result') == 'loss')
            pushes = sum(1 for b in history if b.get('result') == 'push')
            total_profit = sum(b.get('profit', 0) for b in history)
            total_stake = sum(b.get('stake', 0) for b in history)
            
            stats['total'] = total
            stats['wins'] = wins
            stats['losses'] = losses
            stats['pushes'] = pushes
            stats['total_profit'] = round(total_profit, 2)
            stats['winrate'] = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
            stats['roi'] = round((total_profit / total_stake * 100), 1) if total_stake > 0 else 0
            
            storage.save_stats(stats)
            
            logger.info(f"✅ Автоматически обновлено {updated} результатов!")
            
            # Отправляем уведомление в Telegram
            try:
                msg = f"✅ <b>АВТО-ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ</b>\n"
                msg += f"📊 Обновлено: {updated} ставок\n"
                msg += f"📈 Прибыль: ${stats['total_profit']}\n"
                msg += f"🎯 Проходимость: {stats['winrate']}%"
                
                url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
                data = {
                    'chat_id': Config.ADMIN_CHAT_ID,
                    'text': msg,
                    'parse_mode': 'HTML'
                }
                requests.post(url, json=data, timeout=5)
            except:
                pass
        else:
            logger.info("📭 Нет pending ставок для обновления")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обновления: {e}")

def start_scheduler():
    """Запуск шедулера"""
    try:
        # Обновление результатов каждый день в 07:00
        scheduler.add_job(
            update_results_job,
            trigger=CronTrigger(hour=7, minute=0),
            id='update_results',
            name='Обновление результатов',
            replace_existing=True
        )
        scheduler.start()
        logger.info("⏰ Шедулер запущен (обновление результатов ежедневно в 07:00)")
        logger.info("📋 Для ручного обновления используйте /update_results")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска шедулера: {e}")

def stop_scheduler():
    """Остановка шедулера"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("⏹️ Шедулер остановлен")
