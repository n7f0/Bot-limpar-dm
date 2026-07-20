import asyncio
from datetime import datetime, timedelta
from utils.db import get_connection

async def start_scheduler(bot):
    while True:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute('''
            SELECT * FROM scheduled_tasks 
            WHERE active = 1 AND next_run <= ?
        ''', (now,))
        tasks = cursor.fetchall()
        for task in tasks:
            # Executa a tarefa (ex: chamar a função correspondente)
            if task['task_type'] == 'clean':
                # bot.get_cog('Clean').clean(...)
                pass
            # Atualiza próximo agendamento (ex: + intervalo)
            next_run = now + timedelta(seconds=3600)  # exemplo
            cursor.execute('UPDATE scheduled_tasks SET next_run = ? WHERE id = ?', (next_run, task['id']))
        conn.commit()
        conn.close()
        await asyncio.sleep(60)  # verifica a cada minuto