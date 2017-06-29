#coding=utf-8
from datetime import timedelta
from celery.schedules import crontab

BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
# CELERY_TASK_SERIALIZER = 'json'
# CELERY_RESULT_SERIALIZER = 'json'
# CELERY_ACCEPT_CONTENT=['json']
CELERY_TIMEZONE = 'Asia/Shanghai'
CELERY_ENABLE_UTC = True
BROKER_POOL_LIMIT = 0

CELERYBEAT_SCHEDULE = {
    'add-each-minute':{
        'task': 'task_start_ping',
        'schedule': timedelta(seconds=3600),
    }
}
