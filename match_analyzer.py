# match_analyzer.py
import re
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class MatchAnalyzer:
    """Анализатор матчей для группировки по причинам пропуска"""
    
    REASONS = {
        'no_motivation': 'Нет мотивации',
        'low_position': 'Низкая позиция',
        'xg_out_of_range': 'XG вне диапазона 1.8-3.0',
        'passed': 'Пройден фильтр'
    }
    
    @staticmethod
    def parse_log_line(line: str) -> Dict[str, Any]:
        """Парсит одну строку лога"""
        result = {
            'match': '',
            'home': '',
            'away': '',
            'reason': '',
            'reason_detail': '',
            'xg': None,
            'positions': {},
            'league': '',
            'raw': line
        }
        
        # Ищем название матча - разные паттерны
        match_patterns = [
            r'([A-Za-z\s\-\.]+)\s+vs\s+([A-Za-z\s\-\.]+(?:\s+[A-Za-z]+)?)',
            r'([A-Za-z\s\-\.]+)\s+-\s+([A-Za-z\s\-\.]+)',
            r'([A-Za-z\s\-\.]+)\s+/\s+([A-Za-z\s\-\.]+)'
        ]
        
        for pattern in match_patterns:
            match_match = re.search(pattern, line)
            if match_match:
                result['home'] = match_match.group(1).strip()
                result['away'] = match_match.group(2).strip()
                result['match'] = f"{result['home']} vs {result['away']}"
                break
        
        # Если не нашли по паттерну, пробуем извлечь из "Пропускаем (XG вне диапазона):"
        if not result['match']:
            xg_match = re.search(r'Пропускаем\s*\([^)]+\):\s*([^|]+)', line)
            if xg_match:
                match_text = xg_match.group(1).strip()
                result['match'] = match_text
                # Пробуем разделить на home/away
                if ' vs ' in match_text:
                    parts = match_text.split(' vs ')
                    result['home'] = parts[0].strip()
                    result['away'] = parts[1].strip()
        
        # Определяем причину
        line_lower = line.lower()
        
        if 'нет мотивации' in line_lower:
            result['reason'] = 'no_motivation'
            result['reason_detail'] = 'Нет мотивации'
        
        elif 'низкая позиция' in line_lower:
            result['reason'] = 'low_position'
            pos_pattern = r'H: #?(\d+), A: #?(\d+)'
            pos_match = re.search(pos_pattern, line)
            if pos_match:
                result['positions'] = {
                    'home': int(pos_match.group(1)),
                    'away': int(pos_match.group(2))
                }
            result['reason_detail'] = f"Низкая позиция (H: {result['positions'].get('home', '?')}, A: {result['positions'].get('away', '?')})"
        
        elif 'xg вне диапазона' in line_lower or 'xg вне диапазона' in line_lower:
            result['reason'] = 'xg_out_of_range'
            xg_pattern = r'XG:\s*([\d.]+)'
            xg_match = re.search(xg_pattern, line)
            if xg_match:
                result['xg'] = float(xg_match.group(1))
            result['reason_detail'] = f'XG = {result["xg"]} (вне 1.8-3.0)'
        
        # Парсим лигу если есть
        league_match = re.search(r'\[([A-Za-z\s]+)\]', line)
        if league_match:
            result['league'] = league_match.group(1).strip()
        
        return result
    
    @staticmethod
    def analyze_logs(log_text: str) -> Dict[str, Any]:
        """Анализирует лог и возвращает статистику"""
        lines = log_text.split('\n')
        
        stats = {
            'total': 0,
            'categories': {
                'no_motivation': {'count': 0, 'matches': []},
                'low_position': {'count': 0, 'matches': []},
                'xg_out_of_range': {'count': 0, 'matches': []},
                'passed': {'count': 0, 'matches': []}
            },
            'xg_stats': {
                'min': float('inf'),
                'max': float('-inf'),
                'total': 0,
                'count': 0,
                'values': []
            },
            'position_stats': {
                'home_min': 99,
                'home_max': 0,
                'away_min': 99,
                'away_max': 0,
                'home_positions': [],
                'away_positions': []
            },
            'by_league': defaultdict(int),
            'timestamp': datetime.now().isoformat(),
            'all_matches': []
        }
        
        for line in lines:
            if 'Пропускаем' not in line and '⏭️ Пропускаем' not in line:
                continue
            
            parsed = MatchAnalyzer.parse_log_line(line)
            if not parsed['match']:
                continue
            
            stats['total'] += 1
            stats['all_matches'].append(parsed)
            
            # Добавляем в категорию
            if parsed['reason'] in stats['categories']:
                stats['categories'][parsed['reason']]['count'] += 1
                stats['categories'][parsed['reason']]['matches'].append({
                    'match': parsed['match'],
                    'home': parsed['home'],
                    'away': parsed['away'],
                    'xg': parsed['xg'],
                    'positions': parsed['positions'],
                    'league': parsed['league'],
                    'reason_detail': parsed['reason_detail']
                })
            
            # Статистика по XG
            if parsed['xg'] is not None:
                stats['xg_stats']['min'] = min(stats['xg_stats']['min'], parsed['xg'])
                stats['xg_stats']['max'] = max(stats['xg_stats']['max'], parsed['xg'])
                stats['xg_stats']['total'] += parsed['xg']
                stats['xg_stats']['count'] += 1
                stats['xg_stats']['values'].append(parsed['xg'])
            
            # Статистика по позициям
            if parsed['positions']:
                home_pos = parsed['positions'].get('home', 99)
                away_pos = parsed['positions'].get('away', 99)
                if home_pos < 99:
                    stats['position_stats']['home_min'] = min(stats['position_stats']['home_min'], home_pos)
                    stats['position_stats']['home_max'] = max(stats['position_stats']['home_max'], home_pos)
                    stats['position_stats']['home_positions'].append(home_pos)
                if away_pos < 99:
                    stats['position_stats']['away_min'] = min(stats['position_stats']['away_min'], away_pos)
                    stats['position_stats']['away_max'] = max(stats['position_stats']['away_max'], away_pos)
                    stats['position_stats']['away_positions'].append(away_pos)
            
            # По лигам
            if parsed['league']:
                stats['by_league'][parsed['league']] += 1
        
        # Вычисляем средний XG
        if stats['xg_stats']['count'] > 0:
            stats['xg_stats']['avg'] = stats['xg_stats']['total'] / stats['xg_stats']['count']
        else:
            stats['xg_stats']['avg'] = 0
        
        # Добавляем процентное распределение
        for category in stats['categories'].values():
            category['percent'] = (category['count'] / stats['total'] * 100) if stats['total'] > 0 else 0
        
        # Определяем самые частые причины
        stats['top_reasons'] = sorted(
            [{'name': name, 'count': data['count'], 'percent': data['percent']} 
             for name, data in stats['categories'].items()],
            key=lambda x: x['count'],
            reverse=True
        )
        
        return stats
    
    @staticmethod
    def get_recommendations(stats: Dict[str, Any]) -> List[str]:
        """Генерирует рекомендации на основе статистики"""
        recommendations = []
        
        total = stats['total']
        if total == 0:
            return ['📭 Нет данных для анализа. Подождите, пока бот найдет матчи.']
        
        # Проверяем XG
        if stats['xg_stats']['count'] > 0:
            avg_xg = stats['xg_stats']['avg']
            if avg_xg > 3.0:
                recommendations.append(f'⚠️ Средний XG ({avg_xg:.2f}) слишком высокий. Рассмотрите матчи с XG 1.8-3.0')
            elif avg_xg < 1.8:
                recommendations.append(f'⚠️ Средний XG ({avg_xg:.2f}) слишком низкий. Ищите матчи с XG 1.8-3.0')
            else:
                recommendations.append(f'✅ Средний XG ({avg_xg:.2f}) в норме')
        
        # Проверяем категории
        for cat in stats['top_reasons']:
            if cat['name'] != 'passed' and cat['count'] / total > 0.4:
                recommendations.append(f'🔍 {cat["count"]} матчей ({cat["percent"]:.1f}%) пропущено по причине "{cat["name"]}". Проверьте настройки фильтра.')
        
        # Рекомендации по XG > 4
        xg_high_matches = [m for m in stats['all_matches'] if m.get('xg') and m['xg'] > 4]
        if xg_high_matches:
            recommendations.append(f'⚽ Найдено {len(xg_high_matches)} матчей с XG > 4. Возможно, стоит расширить диапазон XG.')
            # Показываем первые 3
            for m in xg_high_matches[:3]:
                recommendations.append(f'  • {m["match"]} (XG: {m["xg"]})')
        
        if not recommendations:
            recommendations.append('✅ Все фильтры работают корректно!')
        
        return recommendations
