# coding: utf-8

from __future__ import division
import uuid
import urllib

from django.db.models import Count
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponseNotFound
from django.http import HttpResponse
# from jperm.models import Apply
import paramiko
from jumpserver.api import *
from jumpserver.models import Setting
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from jlog.models import Log, FileLog
from jperm.perm_api import get_group_user_perm, gen_resource
from jasset.models import Asset, IDC
from juser.models import User
from jperm.ansible_api import MyRunner
from juser.user_api import server_add_user,user_add_mail,db_add_user
import zipfile
from settings import URL,PORT
from jlog.models import SystemLog


def getDaysByNum(num):
    """
    输出格式:([datetime.date(2015, 11, 6),  datetime.date(2015, 11, 8)], ['11-06', '11-08'])
    """

    today = datetime.date.today()
    oneday = datetime.timedelta(days=1)
    date_li, date_str = [], []
    for i in range(0, num):
        today = today-oneday
        date_li.append(today)
        date_str.append(str(today)[5:10])
    date_li.reverse()
    date_str.reverse()
    return date_li, date_str


def get_data(x, y, z):
    pass


def get_data_by_day(date_li, item):
    data_li = []
    for d in date_li:
        logs = Log.objects.filter(start_time__year=d.year,
                                  start_time__month=d.month,
                                  start_time__day=d.day)
        if item == 'user':
            data_li.append(set([log.user for log in logs]))
        elif item == 'asset':
            data_li.append(set([log.host for log in logs]))
        elif item == 'login':
            data_li.append(logs)
        else:
            pass
    return data_li


def get_count_by_day(date_li, item):
    data_li = get_data_by_day(date_li, item)
    data_count_li = []
    for data in data_li:
        data_count_li.append(len(data))
    return data_count_li


def get_count_by_date(date_li, item):
    data_li = get_data_by_day(date_li, item)
    data_count_tmp = []
    for data in data_li:
        data_count_tmp.extend(list(data))

    return len(set(data_count_tmp))


@require_role(role='user')
def index_cu(request):
    username = request.user.username
    return HttpResponseRedirect(reverse('user_detail'))

def user_required(func):
    def wrapper(req,*args,**kwargs):
        is_authenticated = req.session.get('is_authenticated','no')
        if is_authenticated == 'yes':
            return func(req,*args,**kwargs)

        code = req.GET.get('code')
        if code:
            req.session['is_authenticated'] = 'yes'
            req.session.set_expiry(31536000) 
            return func(req,*args,**kwargs)
        # is_authenticated = req.session.get('is_authenticated','no')
        else:
            nginx_port = 80
            return HttpResponseRedirect('http://passport.fangdd.com/passport/authorize.do?client_id=workorder&response_type=code&redirect_uri=%s:%s/'%(URL,nginx_port))
    return wrapper

@user_required
@require_role(role='user')
def index(request):
    li_date, li_str = getDaysByNum(7)
    today = datetime.datetime.now().day
    from_week = datetime.datetime.now() - datetime.timedelta(days=7)

    if is_role_request(request, 'user'):
        return index_cu(request)

    elif is_role_request(request, 'super'):
        # dashboard 显示汇总
        users = User.objects.all()
        hosts = Asset.objects.all()
        online = Log.objects.filter(is_finished=0)
        online_host = online.values('host').distinct()
        online_user = online.values('user').distinct()
        active_users = User.objects.filter(is_active=1)
        active_hosts = Asset.objects.filter(is_active=1)

        # 一个月历史汇总
        date_li, date_str = getDaysByNum(30)
        date_month = repr(date_str)
        active_user_per_month = [Log.objects.filter(start_time__startswith=d).values('user').distinct().count() for d in date_li]
        active_asset_per_month = [Log.objects.filter(start_time__startswith=d).values('host').distinct().count() for d in date_li]
        active_login_per_month = [Log.objects.filter(start_time__startswith=d).count() for d in date_li]

        date_to = datetime.datetime.now()
        date_from = date_to - datetime.timedelta(days=30)

        # 活跃用户资产图
        active_user_month = Log.objects.filter(start_time__range=(date_from,date_to)).values('user').distinct().count()
        disabled_user_count = len(users.filter(is_active=False))
        inactive_user_month = len(users) - active_user_month
        active_asset_month = Log.objects.filter(start_time__range=(date_from,date_to)).values('host').distinct().count()
        disabled_asset_count = len(hosts.filter(is_active=False)) if hosts.filter(is_active=False) else 0
        inactive_asset_month = len(hosts) - active_asset_month if len(hosts) > active_asset_month else 0

        # 一周top10用户和主机
        week_data = Log.objects.filter(start_time__range=[from_week, datetime.datetime.now()])
        user_top_ten = week_data.values('user').annotate(times=Count('user')).order_by('-times')[:10]
        host_top_ten = week_data.values('host').annotate(times=Count('host')).order_by('-times')[:10]

        for user_info in user_top_ten:
            username = user_info.get('user')
            last = Log.objects.filter(user=username).latest('start_time')
            user_info['last'] = last
            user_info['username'] = User.objects.get(username=username).name

        for host_info in host_top_ten:
            host = host_info.get('host')
            last = Log.objects.filter(host=host).latest('start_time')
            last_user = User.objects.get(username=last.user).name
            host_info['last'] = last
            host_info['last_user'] = last_user

        # 一周top5
        week_users = week_data.values('user').distinct().count()
        week_hosts = week_data.count()

        user_top_five = week_data.values('user').annotate(times=Count('user')).order_by('-times')[:5]

        for x in user_top_five:
            x['user'] = User.objects.get(username = x['user']).name

        color = ['label-success', 'label-info', 'label-primary', 'label-default', 'label-warnning']

        # 最后10次权限申请
        # perm apply latest 10
        # perm_apply_10 = Apply.objects.order_by('-date_add')[:10]

        # 最后10次登陆
        login_10 = Log.objects.order_by('-start_time')[:10]
        for x in login_10:
            x.username = User.objects.get(username=x.user).name
        login_more_10 = Log.objects.order_by('-start_time')[10:21]
        for x in login_more_10:
            x.username = User.objects.get(username=x.user).name

    return render_to_response('index.html', locals(), context_instance=RequestContext(request))


def skin_config(request):
    return render_to_response('skin_config.html')


def is_latest():
    node = uuid.getnode()
    jsn = uuid.UUID(int=node).hex[-12:]
    with open(os.path.join(BASE_DIR, 'version')) as f:
        current_version = f.read()
    lastest_version = urllib.urlopen('http://www.jumpserver.org/lastest_version.html?jsn=%s' % jsn).read().strip()

    if current_version != lastest_version:
        pass

def Register(request):
    if request.method == 'POST':
        username = request.POST.get('username', '')
        name = request.POST.get('name','')
        email = request.POST.get('email','')      
        password = PyCrypt.gen_rand_pass(16)
        # name = '张雯豪'
        # email = '654610546@qq.com'
        groups = []
        admin_groups = []
        role = 'CU'
        uuid_r = uuid.uuid4().get_hex()
        ssh_key_pwd = PyCrypt.gen_rand_pass(16)
        is_active = True
        send_mail_need = True
        # extra = request.POST.getlist('extra', [])
        # is_active = False if '0' in extra else True
        # send_mail_need = True if '1' in extra else False
        user = db_add_user(username=username, name=name,
                           password=password,
                           email=email, role=role, uuid=uuid_r,
                           groups=groups, admin_groups=admin_groups,
                           ssh_key_pwd=ssh_key_pwd,
                           is_active=is_active,
                           date_joined=datetime.datetime.now())
        server_add_user(username=username, ssh_key_pwd=ssh_key_pwd)
        user_add_mail(user, kwargs=locals())

    return render_to_response('register.html')

@user_required
@defend_attack
def Login(request):
    """登录界面"""
    error = ''
    if request.user.is_authenticated():
        return HttpResponseRedirect(reverse('index'))
    if request.method == 'GET':
        return render_to_response('login.html')
    else:
        username = request.POST.get('username')
        password = request.POST.get('password')
        if username and password:
            user = authenticate(username=username, password=password)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    # c = {}
                    # c.update(csrf(request))
                    # request.session['csrf_token'] = str(c.get('csrf_token'))
        # user_filter = User.objects.filter(username=username)
        # if user_filter:
        #     user = user_filter[0]
        #     if PyCrypt.md5_crypt(password) == user.password:
        #         request.session['user_id'] = user.id
        #         user_filter.update(last_login=datetime.datetime.now())
                    if user.role == 'SU':
                        request.session['role_id'] = 2
                    elif user.role == 'GA':
                        request.session['role_id'] = 1
                    else:
                        request.session['role_id'] = 0
                    return HttpResponseRedirect(request.session.get('pre_url', '/'))
                # response.set_cookie('username', username, expires=604800)
                # response.set_cookie('seed', PyCrypt.md5_crypt(password), expires=604800)
                # return response
                else:
                    error = '用户未激活'
            else:
                error = '用户名或密码错误'
        else:
            error = '用户名或密码错误'
    return render_to_response('login.html', {'error': error})


@require_role('user')
def Logout(request):
    logout(request)
    return HttpResponseRedirect(reverse('index'))


@require_role('admin')
def setting(request):
    header_title, path1 = '项目设置', '设置'
    setting_default = get_object(Setting, name='default')

    if request.method == "POST":
        try:
            setting_raw = request.POST.get('setting', '')
            if setting_raw == 'default':
                username = request.POST.get('username', '')
                port = request.POST.get('port', '')
                password = request.POST.get('password', '')
                private_key = request.POST.get('key', '')

                if len(password) > 30:
                    raise ServerError(u'秘密长度不能超过30位!')

                if '' in [username, port]:
                    return ServerError(u'所填内容不能为空, 且密码和私钥填一个')
                else:
                    private_key_dir = os.path.join(BASE_DIR, 'keys', 'default')
                    private_key_path = os.path.join(private_key_dir, 'admin_user.pem')
                    mkdir(private_key_dir)

                    if private_key:
                        with open(private_key_path, 'w') as f:
                                f.write(private_key)
                        os.chmod(private_key_path, 0600)

                    if setting_default:
                        if password:
                            password_encode = CRYPTOR.encrypt(password)
                        else:
                            password_encode = password
                        Setting.objects.filter(name='default').update(field1=username, field2=port,
                                                                      field3=password_encode,
                                                                      field4=private_key_path)

                    else:
                        password_encode = CRYPTOR.encrypt(password)
                        setting_r = Setting(name='default', field1=username, field2=port,
                                            field3=password_encode,
                                            field4=private_key_path).save()
                        msg = "设置成功"
        except ServerError as e:
            error = e.message
    return my_render('setting.html', locals(), request)


@login_required(login_url='/login')
def upload(request):
    user = request.user
    assets = get_group_user_perm(user).get('asset').keys()
    asset_select = []
    if request.method == 'POST':
        remote_ip = request.META.get('REMOTE_ADDR')
        asset_ids = request.POST.getlist('asset_ids', '')
        upload_files = request.FILES.getlist('file[]', None)
        date_now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        upload_dir = get_tmp_dir()
        # file_dict = {}
        for asset_id in asset_ids:
            asset_select.append(get_object(Asset, id=asset_id))

        if not set(asset_select).issubset(set(assets)):
            illegal_asset = set(asset_select).issubset(set(assets))
            return HttpResponse('没有权限的服务器 %s' % ','.join([asset.hostname for asset in illegal_asset]))

        for upload_file in upload_files:
            file_path = '%s/%s' % (upload_dir, upload_file.name)
            with open(file_path, 'w') as f:
                for chunk in upload_file.chunks():
                    f.write(chunk)

        res = gen_resource({'user': user, 'asset': asset_select})
        runner = MyRunner(res)
        runner.run('copy', module_args='src=%s dest=%s directory_mode'
                                        % (upload_dir, '/tmp'), pattern='*')
        ret = runner.results
        logger.debug(ret)
        FileLog(user=request.user.username, name=request.user.name, host=' '.join([asset.hostname for asset in asset_select]),
                filename=' '.join([f.name for f in upload_files]), type='upload', remote_ip=remote_ip,
                result=ret).save()
        if ret.get('failed'):
            error = u'上传目录: %s <br> 上传失败: [ %s ] <br>上传成功 [ %s ]' % (upload_dir,
                                                                             ', '.join(ret.get('failed').keys()),
                                                                             ', '.join(ret.get('ok').keys()))
            return HttpResponse(error, status=500)
        msg = u'上传目录: %s <br> 传送成功 [ %s ]' % (upload_dir, ', '.join(ret.get('ok').keys()))
        return HttpResponse(msg)
    return my_render('upload.html', locals(), request)


@login_required(login_url='/login')
def download(request):
    user = request.user
    assets = get_group_user_perm(user).get('asset').keys()
    asset_select = []
    if request.method == 'POST':
        remote_ip = request.META.get('REMOTE_ADDR')
        asset_ids = request.POST.getlist('asset_ids', '')
        file_path = request.POST.get('file_path')
        date_now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        upload_dir = get_tmp_dir()
        for asset_id in asset_ids:
            asset_select.append(get_object(Asset, id=asset_id))

        if not set(asset_select).issubset(set(assets)):
            illegal_asset = set(asset_select).issubset(set(assets))
            return HttpResponse(u'没有权限的服务器 %s' % ','.join([asset.hostname for asset in illegal_asset]))

        res = gen_resource({'user': user, 'asset': asset_select})
        runner = MyRunner(res)
        runner.run('fetch', module_args='src=%s dest=%s' % (file_path, upload_dir), pattern='*')
        FileLog(user=request.user.username, name=request.user.name, host=' '.join([asset.hostname for asset in asset_select]),
                filename=file_path, type='download', remote_ip=remote_ip, result=runner.results).save()
        logger.debug(runner.results)
        tmp_dir_name = os.path.basename(upload_dir)
        file_zip = '/tmp/'+tmp_dir_name+'.zip'
        zf = zipfile.ZipFile(file_zip, "w", zipfile.ZIP_DEFLATED)
        for dirname, subdirs, files in os.walk(upload_dir):
            zf.write(dirname)
            for filename in files:
                zf.write(os.path.join(dirname, filename))
        zf.close()
        f = open(file_zip)
        data = f.read()
        f.close()
        response = HttpResponse(data, content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename=%s.zip' % tmp_dir_name
        return response

    return render_to_response('download.html', locals(), context_instance=RequestContext(request))


@login_required(login_url='/login')
def exec_cmd(request):
    role = request.GET.get('role')
    check_assets = request.GET.get('check_assets', '')
    web_terminal_uri = '/ws/exec?role=%s' % (role)
    return my_render('exec_cmd.html', locals(), request)


@require_role('user')
def web_terminal(request):
    asset_id = request.GET.get('id')
    role_name = request.GET.get('role')
    asset = get_object(Asset, id=asset_id)
    if asset:
        hostname = asset.hostname
    return render_to_response('jlog/web_terminal.html', locals())


@require_role('admin')
def system_record(request):

    header_title, path1 = u'操作记录', u'管理员操作'

    logs = SystemLog.objects.all().order_by('-id')

    contact_list, p, contacts, page_range, current_page, show_first, show_end = pages(logs, request)

    return my_render('system_record.html', locals(), request)

def system_record_api(request):

    system_log_id = request.GET.get('id')
    system_log = SystemLog.objects.get(id = system_log_id)

    return HttpResponse(system_log.info)