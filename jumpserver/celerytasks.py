#coding=utf-8

import time
import celeryconfig
from celery import Celery

import os,sys
import shlex


celery = Celery('tasks')
celery.config_from_object(celeryconfig)

sys.path.append('../')
os.environ["DJANGO_SETTINGS_MODULE"] = 'jumpserver.settings'

from django.db.models import Q
from django.core.mail import send_mail

from jumpserver.settings import EMAIL_HOST_USER
from jlog.models import SystemLog

from jumpserver.api import CRYPTOR
import paramiko

from django.db import connection

MAIL_FROM = EMAIL_HOST_USER

@celery.task(name='task_mail')
def task_mail(title,msg,mail_from,to):
    connection.close()
    send_mail(title, msg, mail_from, to, fail_silently=False)

from jasset.asset_api import asset_ansible_update

@celery.task(name='task_ansible_update')
def task_ansible_update(user, asset_list, name):
    connection.close()
    result = asset_ansible_update(asset_list, name)
    all_assets = []
    for asset in asset_list:
        all_assets.append(asset.hostname)
    if not result:
        msg = u"更新以下资产%s <br> 全部成功"%(','.join(all_assets))
    else:
        msg = u"更新以下资产%s <br> "%(','.join(all_assets)) + u"资产%s更新失败"%(','.join(result))
    SystemLog.objects.create(user = user, log_type = 'ansible配置更新', info = msg)


from jasset.models import Asset,AssetGroup
from jperm.perm_api import gen_resource
from jperm.ansible_api import MyTask
from jumpserver.api import logger
from jperm.models import PermPush

@celery.task(name='task_ansible_role_push')
def task_ansible_role_push(user,push_task,role):
    connection.close()
    asset_ids = push_task['assets']
    asset_group_ids = push_task['asset_groups']
    assets_obj = [Asset.objects.get(id=asset_id) for asset_id in asset_ids]
    asset_groups_obj = [AssetGroup.objects.get(id=asset_group_id) for asset_group_id in asset_group_ids]
    group_assets_obj = []
    for asset_group in asset_groups_obj:
        group_assets_obj.extend(asset_group.asset_set.all())
    calc_assets = list(set(assets_obj) | set(group_assets_obj))

    push_resource = gen_resource(calc_assets)

    # 调用Ansible API 进行推送
    password_push = True if push_task['use_password'] else False
    key_push = True if push_task['use_publicKey'] else False
    task = MyTask(push_resource)
    ret = {}

    # 因为要先建立用户，而push key是在 password也完成的情况下的 可选项
    # 1. 以秘钥 方式推送角色
    if key_push:
        ret["pass_push"] = task.add_user(role.name)
        ret["key_push"] = task.push_key(role.name, os.path.join(role.key_path, 'id_rsa.pub'))

    # 2. 推送账号密码 <为了安全 系统用户统一使用秘钥进行通信， 不再提供密码方式的推送>
    # elif password_push:
    #     ret["pass_push"] = task.add_user(role.name, CRYPTOR.decrypt(role.password))

    # 3. 推送sudo配置文件
    if key_push:
        sudo_list = set([sudo for sudo in role.sudo.all()])  # set(sudo1, sudo2, sudo3)
        if sudo_list:
            ret['sudo'] = task.push_sudo_file([role], sudo_list)
        else:
            ret['sudo'] = task.recyle_cmd_alias(role.name)

    logger.debug('推送role结果: %s' % ret)
    success_asset = {}
    failed_asset = {}
    logger.debug(ret)
    for push_type, result in ret.items():
        if result.get('failed'):
            for hostname, info in result.get('failed').items():
                if hostname in failed_asset.keys():
                    if info in failed_asset.get(hostname):
                        failed_asset[hostname] += info
                else:
                    failed_asset[hostname] = info

    for push_type, result in ret.items():
        if result.get('ok'):
            for hostname, info in result.get('ok').items():
                if hostname in failed_asset.keys():
                    continue
                elif hostname in success_asset.keys():
                    if str(info) in success_asset.get(hostname, ''):
                        success_asset[hostname] += str(info)
                else:
                    success_asset[hostname] = str(info)

    # 推送成功 回写push表
    for asset in calc_assets:
        push_check = PermPush.objects.filter(role=role, asset=asset)
        if push_check:
            func = push_check.update
        else:
            def func(**kwargs):
                PermPush(**kwargs).save()

        if failed_asset.get(asset.hostname):
            func(is_password=password_push, is_public_key=key_push, role=role, asset=asset, success=False,
                 result=failed_asset.get(asset.hostname))
        else:
            func(is_password=password_push, is_public_key=key_push, role=role, asset=asset, success=True)

    if not failed_asset:
        msg = u'系统用户 %s 推送成功[ %s ]' % (role.name, ','.join(success_asset.keys()))
    else:
        msg = u'系统用户 %s 推送失败 [ %s ], 推送成功 [ %s ] 请点系统用户->点对应名称->点失败，查看失败原因' % (role.name,
                                                            ','.join(failed_asset.keys()),
                                                            ','.join(success_asset.keys()))

    SystemLog.objects.create(user = user, log_type = 'ansible用户推送', info = msg)

from juser.models import User

@celery.task(name='task_root_check')
def task_root_check(user):
    connection.close()
    asset_result = root_all_check()
    if not asset_result['failed']:
        msg = u"root连通性检查全部通过"
    else:
        msg = u"以下资产root账户存在问题:<br>%s"%(','.join(asset_result['failed']))
    if isinstance(user,str):
        SystemLog.objects.create(user = User.objects.get(username=user), log_type = 'root账户连通性检查', info = msg)
    else:
        SystemLog.objects.create(user = user, log_type = 'root账户连通性检查', info = msg)

def root_all_check():
    print '开始检查资产root账户可用性'
    assets = Asset.objects.filter(~Q(group__name__contains='it'))
    asset_result = {}
    asset_result['success'] = []
    asset_result['failed'] = []
    for asset in assets:
        username = asset.username
        password = CRYPTOR.decrypt(asset.password)
        port = asset.port
        result = ssh_connect_check(asset.ip, username, password, port)
        if result:
            asset_result['success'].append(asset.hostname)
        else:
            asset_result['failed'].append(asset.hostname)
    return asset_result

def ssh_connect_check(hostname, username, password, port):
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        s.connect(hostname = hostname, username = username, password = password, port = port)
        s.close()
        print hostname, 'right'
        
    except Exception as e:
        print hostname, e, 'wrong'
        return False
    
    return True

def bash(cmd):
    return shlex.os.system(cmd)

@celery.task(name='task_asset_ping')
def ping(ip):
    asset = Asset.objects.get(ip=ip)
    result = bash('ping -c 5 -i 1 %s'%ip)
    if result:
        asset.status = 2
        asset.save()
    else:
        asset.status = 1
        asset.save()

@celery.task(name='task_start_ping')
def add():
    connection.close()
    ips = Asset.objects.all().values_list('ip',flat=True)
    for ip in ips:
        ping.delay(ip)
