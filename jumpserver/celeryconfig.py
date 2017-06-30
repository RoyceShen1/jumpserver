#coding=utf-8
from datetime import timedelta
from celery.schedules import crontab

import os,sys
sys.path.append('../')
os.environ["DJANGO_SETTINGS_MODULE"] = 'jumpserver.settings'
from juser.models import User
admin = User.objects.get(username='admin')

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
    'root-check-each-day':{
    	'task': 'task_root_check',
    	'schedule': timedelta(seconds=86400),
    	'args': (admin),
    }
}
