#!/usr/bin/env python
from worker.main import worker_app, update_worker_status, WORKER_NAME

if __name__ == '__main__':
    # Обновление статуса при запуске
    update_worker_status()
    
    # Запуск воркера Celery
    argv = [
        'worker',
        '--loglevel=info',
        f'--hostname={WORKER_NAME}@%h',
        f'--queues={WORKER_NAME},control',  # Слушаем очередь с именем воркера и общую очередь control
        '--beat',  # Включаем встроенный scheduler для периодических задач
    ]
    worker_app.worker_main(argv) 