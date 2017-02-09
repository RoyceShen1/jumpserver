#coding=utf-8

import time
import celeryconfig
from celery import Celery

celery = Celery('tasks')
celery.config_from_object(celeryconfig)

import os,sys
sys.path.append('../')
os.environ["DJANGO_SETTINGS_MODULE"] = 'jumpserver.settings'

from django.core.mail import send_mail
from jumpserver.settings import EMAIL_HOST_USER

MAIL_FROM = EMAIL_HOST_USER

@celery.task(name='task_mail')
def task_mail(title,msg,mail_from,to):
	send_mail(title, msg, mail_from, to, fail_silently=False)

from jasset.asset_api import asset_ansible_update

@celery.task(name='task_ansible_update')
def task_ansible_update(asset_list, name):
	asset_ansible_update(asset_list, name)

