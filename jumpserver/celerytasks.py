#coding=utf-8

import time
import celeryconfig
from celery import Celery

import os,sys

from django.core.mail import send_mail

celery = Celery('tasks')
celery.config_from_object(celeryconfig)

os.environ["DJANGO_SETTINGS_MODULE"] = 'jumpserver.settings'

sys.path.append('../')
from jumpserver.settings import EMAIL_HOST_USER
from jlog.models import SystemLog


MAIL_FROM = EMAIL_HOST_USER

@celery.task(name='task_mail')
def task_mail(title,msg,mail_from,to):
	send_mail(title, msg, mail_from, to, fail_silently=False)

from jasset.asset_api import asset_ansible_update

@celery.task(name='task_ansible_update')
def task_ansible_update(user, asset_list, name):
	result = asset_ansible_update(asset_list, name)
	SystemLog.objects.create(user = user, log_type = 'ansible配置更新', info = result)