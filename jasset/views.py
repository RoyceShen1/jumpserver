# coding:utf-8

from django.db.models import Q
from jasset.asset_api import *
from jumpserver.api import *
from jumpserver.models import Setting
from jasset.forms import AssetForm, IdcForm
from jasset.models import Asset, IDC, AssetGroup, ASSET_TYPE, ASSET_STATUS
from jperm.perm_api import get_group_asset_perm, get_group_user_perm
import json, ast
from datetime import datetime
from django.forms.models import model_to_dict

from jumpserver.celerytasks import task_ansible_update,task_root_check

class MyEncoder(json.JSONEncoder):  
    def default(self, obj):   
        if isinstance(obj, datetime):  
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        else:  
            return json.JSONEncoder.default(self, obj)

@require_role('admin')
def group_add(request):
    """
    Group add view
    添加资产组
    """
    header_title, path1, path2 = u'添加资产组', u'资产管理', u'添加资产组'
    asset_all = Asset.objects.all()

    if request.method == 'POST':
        name = request.POST.get('name', '')
        asset_select = request.POST.getlist('asset_select', [])
        comment = request.POST.get('comment', '')

        try:
            if not name:
                emg = u'组名不能为空'
                raise ServerError(emg)

            asset_group_test = get_object(AssetGroup, name=name)
            if asset_group_test:
                emg = u"该组名 %s 已存在" % name
                raise ServerError(emg)

        except ServerError:
            pass

        else:
            db_add_group(name=name, comment=comment, asset_select=asset_select)
            smg = u"主机组 %s 添加成功" % name

    return my_render('jasset/group_add.html', locals(), request)


@require_role('admin')
def group_edit(request):
    """
    Group edit view
    编辑资产组
    """
    header_title, path1, path2 = u'编辑主机组', u'资产管理', u'编辑主机组'
    group_id = request.GET.get('id', '')
    group = get_object(AssetGroup, id=group_id)

    asset_all = Asset.objects.all()
    asset_select = Asset.objects.filter(group=group)
    asset_no_select = [a for a in asset_all if a not in asset_select]

    if request.method == 'POST':
        name = request.POST.get('name', '')
        asset_select = request.POST.getlist('asset_select', [])
        comment = request.POST.get('comment', '')

        try:
            if not name:
                emg = u'组名不能为空'
                raise ServerError(emg)

            if group.name != name:
                asset_group_test = get_object(AssetGroup, name=name)
                if asset_group_test:
                    emg = u"该组名 %s 已存在" % name
                    raise ServerError(emg)

        except ServerError:
            pass

        else:
            group.asset_set.clear()
            db_update_group(id=group_id, name=name, comment=comment, asset_select=asset_select)
            smg = u"主机组 %s 添加成功" % name

        return HttpResponseRedirect(reverse('asset_group_list'))

    return my_render('jasset/group_edit.html', locals(), request)


@require_role('admin')
def group_list(request):
    """
    list asset group
    列出资产组
    """
    header_title, path1, path2 = u'查看资产组', u'资产管理', u'查看资产组'
    keyword = request.GET.get('keyword', '')
    asset_group_list = AssetGroup.objects.all()
    group_id = request.GET.get('id')
    if group_id:
        asset_group_list = asset_group_list.filter(id=group_id)
    if keyword:
        asset_group_list = asset_group_list.filter(Q(name__contains=keyword) | Q(comment__contains=keyword))

    asset_group_list, p, asset_groups, page_range, current_page, show_first, show_end = pages(asset_group_list, request)
    return my_render('jasset/group_list.html', locals(), request)


@require_role('admin')
def group_del(request):
    """
    Group delete view
    删除主机组
    """
    group_ids = request.GET.get('id', '')
    group_id_list = group_ids.split(',')

    for group_id in group_id_list:
        AssetGroup.objects.filter(id=group_id).delete()

    return HttpResponse(u'删除成功')


@require_role('admin')
def asset_add(request):
    """
    Asset add view
    添加资产
    """
    header_title, path1, path2 = u'添加资产', u'资产管理', u'添加资产'
    asset_group_all = AssetGroup.objects.all()
    af = AssetForm()
    default_setting = get_object(Setting, name='default')
    default_port = default_setting.field2 if default_setting else ''
    if request.method == 'POST':
        af_post = AssetForm(request.POST)
        ip = request.POST.get('ip', '')
        hostname = request.POST.get('hostname', '')

        is_active = True if request.POST.get('is_active') == '1' else False
        use_default_auth = request.POST.get('use_default_auth', '')
        try:
            if Asset.objects.filter(hostname=unicode(hostname)):
                error = u'该主机名 %s 已存在!' % hostname
                raise ServerError(error)
            if len(hostname) > 54:
                error = u"主机名长度不能超过53位!"
                raise ServerError(error)
        except ServerError:
            pass
        else:
            if af_post.is_valid():
                asset_save = af_post.save(commit=False)
                if not use_default_auth:
                    password = request.POST.get('password', '')
                    password_encode = CRYPTOR.encrypt(password)
                    asset_save.password = password_encode
                if not ip:
                    asset_save.ip = hostname
                asset_save.is_active = True if is_active else False
                asset_save.save()
                af_post.save_m2m()

                msg = u'主机 %s 添加成功' % hostname
            else:
                esg = u'主机 %s 添加失败' % hostname

    return my_render('jasset/asset_add.html', locals(), request)


@require_role('admin')
def asset_add_batch(request):
    header_title, path1, path2 = u'添加资产', u'资产管理', u'批量添加'
    return my_render('jasset/asset_add_batch.html', locals(), request)


@require_role('admin')
def asset_del(request):
    """
    del a asset
    删除主机
    """
    asset_id = request.GET.get('id', '')
    if asset_id:
        Asset.objects.filter(id=asset_id).delete()

    if request.method == 'POST':
        asset_batch = request.GET.get('arg', '')
        asset_id_all = str(request.POST.get('asset_id_all', ''))

        if asset_batch:
            for asset_id in asset_id_all.split(','):
                asset = get_object(Asset, id=asset_id)
                asset.delete()

    return HttpResponse(u'删除成功')


@require_role(role='super')
def asset_edit(request):
    """
    edit a asset
    修改主机
    """
    header_title, path1, path2 = u'修改资产', u'资产管理', u'修改资产'

    asset_id = request.GET.get('id', '')
    username = request.user.username
    asset = get_object(Asset, id=asset_id)

    if asset:
        password_old = asset.password
    # asset_old = copy_model_instance(asset)
    af = AssetForm(instance=asset)
    if request.method == 'POST':

        af_post = AssetForm(request.POST, instance=asset)
        ip = request.POST.get('ip', '')
        hostname = request.POST.get('hostname', '')
        password = request.POST.get('password', '')
        is_active = True if request.POST.get('is_active') == '1' else False
        use_default_auth = request.POST.get('use_default_auth', '')
        try:
            asset_test = get_object(Asset, hostname=hostname)
            if asset_test and asset_id != unicode(asset_test.id):
                emg = u'该主机名 %s 已存在!' % hostname
                raise ServerError(emg)
            if len(hostname) > 54:
                emg = u'主机名长度不能超过54位!'
                raise ServerError(emg)
            else:
                if af_post.is_valid():
                    af_save = af_post.save(commit=False)
                    if use_default_auth:
                        af_save.username = ''
                        af_save.password = ''
                        # af_save.port = None
                    else:
                        if password:
                            password_encode = CRYPTOR.encrypt(password)
                            af_save.password = password_encode
                        else:
                            af_save.password = password_old
                    af_save.is_active = True if is_active else False
                    af_save.save()
                    af_post.save_m2m()
                    # asset_new = get_object(Asset, id=asset_id)
                    # asset_diff_one(asset_old, asset_new)
                    info = asset_diff(af_post.__dict__.get('initial'), request.POST)
                    db_asset_alert(asset, username, info)

                    smg = u'主机 %s 修改成功' % ip
                else:
                    emg = u'主机 %s 修改失败' % ip
                    raise ServerError(emg)

            host_machine_ip = request.POST.get('host_machine_ip','')
            if host_machine_ip:
                host_machine = Asset.objects.get(ip = host_machine_ip)
                asset.host_machine = host_machine
                asset.save()

        except ServerError as e:
            error = e.message
            return my_render('jasset/asset_edit.html', locals(), request)

        return HttpResponseRedirect(reverse('asset_detail')+'?id=%s' % asset_id)

    return my_render('jasset/asset_edit.html', locals(), request)


@require_role('user')
def asset_list(request):
    """
    asset list view
    """
    header_title, path1, path2 = u'查看资产', u'资产管理', u'查看资产'
    username = request.user.username
    user_perm = request.session['role_id']
    idc_all = IDC.objects.filter()
    asset_group_all = AssetGroup.objects.all()
    asset_types = ASSET_TYPE
    asset_status = ASSET_STATUS
    idc_name = request.GET.get('idc', '')
    group_name = request.GET.get('group', '')
    asset_type = request.GET.get('asset_type', '')
    status = request.GET.get('status', '')
    keyword = request.GET.get('keyword', '')
    export = request.GET.get("export", False)
    group_id = request.GET.get("group_id", '')
    idc_id = request.GET.get("idc_id", '')
    asset_id_all = request.GET.getlist("id", '')

    if group_id:
        group = get_object(AssetGroup, id=group_id)
        if group:
            asset_find = Asset.objects.filter(group=group)
    elif idc_id:
        idc = get_object(IDC, id=idc_id)
        if idc:
            asset_find = Asset.objects.filter(idc=idc)
    else:
        if user_perm != 0:
            asset_find = Asset.objects.all()
        else:
            asset_id_all = []
            user = get_object(User, username=username)
            asset_perm = get_group_user_perm(user) if user else {'asset': ''}
            user_asset_perm = asset_perm['asset'].keys()
            for asset in user_asset_perm:
                asset_id_all.append(asset.id)
            asset_find = Asset.objects.filter(pk__in=asset_id_all)
            asset_group_all = list(asset_perm['asset_group'])

    if idc_name:
        if idc_name == 'none':
            asset_find = asset_find.filter(idc=None)
        else:
            asset_find = asset_find.filter(idc__name__contains=idc_name)

    if group_name:
        if group_name == 'none':
            asset_find = asset_find.filter(group=None)
        else:
            asset_find = asset_find.filter(group__name__contains=group_name)

    if asset_type:
        asset_find = asset_find.filter(asset_type__contains=asset_type)

    if status:
        asset_find = asset_find.filter(status__contains=status)

    if keyword:
        asset_find = asset_find.filter(
            Q(hostname__contains=keyword) |
            Q(other_ip__contains=keyword) |
            Q(ip__contains=keyword) |
            Q(remote_ip__contains=keyword) |
            Q(comment__contains=keyword) |
            Q(username__contains=keyword) |
            Q(group__name__contains=keyword) |
            Q(cpu__contains=keyword) |
            Q(memory__contains=keyword) |
            Q(disk__contains=keyword) |
            Q(brand__contains=keyword) |
            Q(cabinet__contains=keyword) |
            Q(sn__contains=keyword) |
            Q(system_type__contains=keyword) |
            Q(system_version__contains=keyword))

    if export:
        import traceback
        try:
            if asset_id_all:
                asset_find = []
                for asset_id in asset_id_all:
                    asset = get_object(Asset, id=asset_id)
                    if asset:
                        asset_find.append(asset)
            asset_find = asset_find.distinct()
            asset_find = sorted(asset_find, key=lambda ip: long(''.join(["%02X" % long(i) for i in ip.ip.split('.')]), 16))
            s = write_excel(asset_find)
            if s[0]:
                file_name = s[1]
            smg = u'excel文件已生成，请点击下载!'
            return my_render('jasset/asset_excel_download.html', locals(), request)
        except:
            traceback.print_exc()
    # 去重,按ip排序
    asset_find = asset_find.distinct()
    asset_find = sorted(asset_find, key=lambda ip: long(''.join(["%02X" % long(i) for i in ip.ip.split('.')]), 16))

    # ip排序
    if 'ip' in request.GET:
        ip = request.GET.get('ip')
        if ip == '0':
            asset_find.reverse()
    else:
        ip = '1'

    assets_list, p, assets, page_range, current_page, show_first, show_end = pages(asset_find, request)
    
    contact_list = assets_list
    contacts = assets    

    if user_perm != 0:
        return my_render('jasset/asset_list.html', locals(), request)
    else:
        return my_render('jasset/asset_cu_list.html', locals(), request)


@require_role('admin')
def asset_edit_batch(request):
    af = AssetForm()
    name = request.user.username
    asset_group_all = AssetGroup.objects.all()

    if request.method == 'POST':
        env = request.POST.get('env', '')
        idc_id = request.POST.get('idc', '')
        port = request.POST.get('port', '')
        use_default_auth = request.POST.get('use_default_auth', '')
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        group = request.POST.getlist('group', [])
        cabinet = request.POST.get('cabinet', '')
        position = request.POST.get('position', '')
        comment = request.POST.get('comment', '')
        asset_id_all = unicode(request.GET.get('asset_id_all', ''))
        asset_id_all = asset_id_all.split(',')
        for asset_id in asset_id_all:
            alert_list = []
            asset = get_object(Asset, id=asset_id)
            if asset:
                if env:
                    if asset.env != env:
                        asset.env = env
                        alert_list.append([u'运行环境', asset.env, env])
                if idc_id:
                    idc = get_object(IDC, id=idc_id)
                    name_old = asset.idc.name if asset.idc else u''
                    if idc and idc.name != name_old:
                        asset.idc = idc
                        alert_list.append([u'机房', name_old, idc.name])
                if port:
                    if unicode(asset.port) != port:
                        asset.port = port
                        alert_list.append([u'端口号', asset.port, port])

                if use_default_auth:
                    if use_default_auth == 'default':
                        asset.use_default_auth = 1
                        asset.username = ''
                        asset.password = ''
                        alert_list.append([u'使用默认管理账号', asset.use_default_auth, u'默认'])
                    elif use_default_auth == 'user_passwd':
                        asset.use_default_auth = 0
                        asset.username = username
                        password_encode = CRYPTOR.encrypt(password)
                        asset.password = password_encode
                        alert_list.append([u'使用默认管理账号', asset.use_default_auth, username])
                if group:
                    group_new, group_old, group_new_name, group_old_name = [], asset.group.all(), [], []
                    for group_id in group:
                        g = get_object(AssetGroup, id=group_id)
                        if g:
                            group_new.append(g)
                    if not set(group_new) < set(group_old):
                        group_instance = list(set(group_new) | set(group_old))
                        for g in group_instance:
                            group_new_name.append(g.name)
                        for g in group_old:
                            group_old_name.append(g.name)
                        asset.group = group_instance
                        alert_list.append([u'主机组', ','.join(group_old_name), ','.join(group_new_name)])
                if cabinet:
                    if asset.cabinet != cabinet:
                        asset.cabinet = cabinet
                        alert_list.append([u'机柜号', asset.cabinet, cabinet])
                # 新增机架号修改
                if position:
                    if asset.position != position:
                        asset.position = position
                        alert_list.append([u'机架号', asset.position, position])
                if comment:
                    if asset.comment != comment:
                        asset.comment = comment
                        alert_list.append([u'备注', asset.comment, comment])
                asset.save()

            if alert_list:
                recode_name = unicode(name) + ' - ' + u'批量'
                AssetRecord.objects.create(asset=asset, username=recode_name, content=alert_list)
        return my_render('jasset/asset_update_status.html', locals(), request)

    return my_render('jasset/asset_edit_batch.html', locals(), request)


@require_role('admin')
def asset_detail(request):
    """
    Asset detail view
    """
    header_title, path1, path2 = u'主机详细信息', u'资产管理', u'主机详情'
    asset_id = request.GET.get('id', '')
    asset = get_object(Asset, id=asset_id)
    perm_info = get_group_asset_perm(asset)
    log = Log.objects.filter(host=asset.hostname)
    if perm_info:
        user_perm = []
        for perm, value in perm_info.items():
            if perm == 'user':
                for user, role_dic in value.items():
                    user_perm.append([user, role_dic.get('role', '')])
            elif perm == 'user_group' or perm == 'rule':
                user_group_perm = value
    print perm_info

    asset_record = AssetRecord.objects.filter(asset=asset).order_by('-alert_time')

    return my_render('jasset/asset_detail.html', locals(), request)


@require_role('admin')
def asset_update(request):
    """
    Asset update host info via ansible view
    """
    asset_id = request.GET.get('id', '')
    asset = get_object(Asset, id=asset_id)
    name = request.user.username
    if not asset:
        return HttpResponseRedirect(reverse('asset_detail')+'?id=%s' % asset_id)
    else:
        asset_ansible_update([asset], name)
    return HttpResponseRedirect(reverse('asset_detail')+'?id=%s' % asset_id)


@require_role('admin')
def asset_update_batch(request):
    user = request.user
    if request.method == 'POST':
        arg = request.GET.get('arg', '')
        name = unicode(request.user.username) + ' - ' + u'自动更新'
        if arg == 'all':
            asset_list = Asset.objects.all()
        else:
            asset_list = []
            asset_id_all = unicode(request.POST.get('asset_id_all', ''))
            asset_id_all = asset_id_all.split(',')
            for asset_id in asset_id_all:
                asset = get_object(Asset, id=asset_id)
                if asset:
                    asset_list.append(asset)
        task_ansible_update.delay(user, asset_list, name)
        # asset_ansible_update(asset_list, name)
        return HttpResponse(u'正在更新中,请稍后查看!')
    return HttpResponse(u'正在更新中,请稍后查看!')


@require_role('admin')
def idc_add(request):
    """
    IDC add view
    """
    header_title, path1, path2 = u'添加IDC', u'资产管理', u'添加IDC'
    if request.method == 'POST':
        idc_form = IdcForm(request.POST)
        if idc_form.is_valid():
            idc_name = idc_form.cleaned_data['name']

            if IDC.objects.filter(name=idc_name):
                emg = u'添加失败, 此IDC %s 已存在!' % idc_name
                return my_render('jasset/idc_add.html', locals(), request)
            else:
                idc_form.save()
                smg = u'IDC: %s添加成功' % idc_name
            return HttpResponseRedirect(reverse('idc_list'))
    else:
        idc_form = IdcForm()
    return my_render('jasset/idc_add.html', locals(), request)


@require_role('admin')
def idc_list(request):
    """
    IDC list view
    """
    header_title, path1, path2 = u'查看IDC', u'资产管理', u'查看IDC'
    posts = IDC.objects.all()
    keyword = request.GET.get('keyword', '')
    if keyword:
        posts = IDC.objects.filter(Q(name__contains=keyword) | Q(comment__contains=keyword))
    else:
        posts = IDC.objects.exclude(name='ALL').order_by('id')
    contact_list, p, contacts, page_range, current_page, show_first, show_end = pages(posts, request)
    return my_render('jasset/idc_list.html', locals(), request)


@require_role('admin')
def idc_edit(request):
    """
    IDC edit view
    """
    header_title, path1, path2 = u'编辑IDC', u'资产管理', u'编辑IDC'
    idc_id = request.GET.get('id', '')
    idc = get_object(IDC, id=idc_id)
    if request.method == 'POST':
        idc_form = IdcForm(request.POST, instance=idc)
        if idc_form.is_valid():
            idc_form.save()
            return HttpResponseRedirect(reverse('idc_list'))
    else:
        idc_form = IdcForm(instance=idc)
        return my_render('jasset/idc_edit.html', locals(), request)


@require_role('admin')
def idc_del(request):
    """
    IDC delete view
    """
    idc_ids = request.GET.get('id', '')
    idc_id_list = idc_ids.split(',')

    for idc_id in idc_id_list:
        IDC.objects.filter(id=idc_id).delete()

    return HttpResponseRedirect(reverse('idc_list'))


@require_role('admin')
def asset_upload(request):
    """
    Upload asset excel file view
    """
    if request.method == 'POST':
        excel_file = request.FILES.get('file_name', '')
        ret = excel_to_db(excel_file)
        if ret:
            smg = u'批量添加成功'
        else:
            emg = u'批量添加失败,请检查格式.'
    return my_render('jasset/asset_add_batch.html', locals(), request)

@require_role('admin')
def asset_upload_to_update(request):
    if request.method == 'POST':
        import xlrd
        excel_file = request.FILES.get('file_name', '')
        data = xlrd.open_workbook(filename=None, file_contents=excel_file.read())
        table = data.sheets()[0]
        rows = table.nrows
        for row_num in range(1, rows):
            row = table.row_values(row_num)
            ip = row[1]
            a = Asset.objects.get(ip = ip)
            
            idc_name = row[2]
            if IDC.objects.filter(name = idc_name):
                a.idc = IDC.objects.get(name = idc_name)

            remote_ip = row[9]
            other_ip = row[10]
            status = row[11]
            comment = row[12]
            if status == '已使用':
                status = 1
            elif status == '未使用':
                status = 2
            elif status == '报废':
                status = 3
            number = row[16]
            cabinet = row[17]
            position = row[18]
            asset_type = row[19]
            host_machine_ip = row[22]
            if asset_type == '物理机':
                asset_type = 1
            elif asset_type == '虚拟机':
                asset_type = 2
            elif asset_type == '交换机':
                asset_type = 3
            elif asset_type == '路由器':
                asset_type = 4
            elif asset_type == '防火墙':
                asset_type = 5
            elif asset_type == 'Docker':
                asset_type = 6
            elif asset_type == '其他':
                asset_type = 7
            env = row[20]
            if env == '生产环境':
                env = 1
            elif env == '测试环境':
                env = 2
            is_active = row[21]
            if is_active == '已激活':
                is_active = True
            else:
                is_active = False

            if remote_ip:
                a.remote_ip = remote_ip
            if other_ip:
                a.other_ip = other_ip
            if status:
                a.status = status
            if number:
                a.number = number
            if cabinet:
                a.cabinet = cabinet
            if position:
                a.position = position
            if asset_type:
                a.asset_type = asset_type
            if env:
                a.env = env
            if is_active:
                a.is_active = is_active
            if comment:
                a.comment = comment
            if host_machine_ip:
                a.host_machine = Asset.objects.get(ip = host_machine_ip)
            a.save()

    return my_render('jasset/asset_update_from_excel.html', locals(), request)

def asset_info(request):
    key = request.GET.get('key','')
    if key == '0b28251e684dfbd9102f8b6f0281c0c5':
        asset = Asset.objects.all()
        asset_list = []
        for a in asset:
            asset_dict = model_to_dict(a)
            asset_list.append(asset_dict)
        return HttpResponse(json.dumps(asset_list, cls=MyEncoder))
    else:
        return HttpResponse('error')

@require_role('admin')
def asset_update_from_excel(request):
    header_title, path1, path2 = u'更新资产', u'资产管理', u'批量更新'
    return my_render('jasset/asset_update_from_excel.html', locals(), request)

@require_role('admin')
def asset_check(request):
    header_title, path1, path2 = u'资产检测', u'资产管理', u'资产检测'
    return my_render('jasset/asset_check.html', locals(), request)

def root_check(request):
    user = request.user
    task_root_check.delay(user)
    return HttpResponse("已经开始检查,请稍后查看结果")

def relation_list(request):
    header_title, path1, path2 = u'物理资产', u'资产管理', u'资产关系'
    return my_render('jasset/asset_relation_list.html', locals(), request)

def relation_api(request):

    search_content = request.POST.get('search_content','')
    search_field = int(request.POST.get('field',''))

    physical_machines = Asset.objects.filter(asset_type=1)
    if search_field == 1:
        physical_machines = physical_machines.filter(group__name__contains = search_content)
    elif search_field == 2:
        physical_machines = physical_machines.filter(ip__contains = search_content)
    elif search_field == 3:
        physical_machines = physical_machines.filter(virtual_machine__ip__contains = search_content)
    elif search_field == 4:
        physical_machines = physical_machines.filter(virtual_machine__hostname__contains = search_content)

    physical_machines = physical_machines.distinct()
    physical_machines_list1 = []
    physical_machines_list2 = []
    for p in physical_machines:
        if p.virtual_machine.all().count() == 0:
            physical_machines_list2.append(p)
        else:
            physical_machines_list1.append(p)
    physical_machines_list = physical_machines_list1 + physical_machines_list2

    relationship = []
    for each_machine in physical_machines_list:
        m_list = []
        for v in each_machine.virtual_machine.all():
            m = {'ip':v.ip, 'hostname':v.hostname, 'comment':v.comment}
            m_list.append(m)

        r = {}
        r['physical_machine'] = each_machine.ip
        r['virtual_machine'] = m_list
        relationship.append(r)


    return HttpResponse(json.dumps(relationship), content_type = "application/json")

def xenserver_list(request):
    header_title, path1, path2 = u'物理资产', u'XenServer管理', u'物理资源'

    # group = request.GET.get('group',0)
    # xens = Asset.objects.filter(system_type__contains='XenServer')
    # if group == '1':
    #     xens = xens.filter(group__name__contains='二手房')
    # if group == '2':
    #     xens = xens.filter(group__name__contains='新房')
    # if group == '3':
    #     xens = xens.filter(group__name__contains='基础')
    # if group == '4':
    #     xens = xens.filter(group__name__contains='流量')
    # if group == '5':
    #     xens = xens.filter(group__name__contains='金融')
    # if group == '6':
    #     xens = xens.filter(group__name__contains='DEVOPS')
    # xens = xens.distinct()

    return my_render('jasset/xenserver_list.html', locals(), request)

def xenserver_api(request):

    xens = Asset.objects.filter(Q(system_type__contains='XenServer')&~Q(group__name__contains='it'))

    xen_info_list = []
    for xen in xens:
        xen_info_dict = {}
        xen_info_dict['ip'] = xen.ip
        xen_info_dict['cpu_all'] = xen.res_cpu
        xen_info_dict['mem_all'] = xen.res_mem
        xen_info_dict['disk_all'] = xen.res_disk

        vms = xen.virtual_machine.all()
        used_cpu_core = 0
        for vm in vms:
            used_cpu_core = used_cpu_core + int(vm.cpu.split(' ')[-1])

        xen_info_dict['cpu_used'] = used_cpu_core

        used_mem = 0
        for vm in vms:
            used_mem = used_mem + int(vm.memory)

        xen_info_dict['mem_used'] = used_mem

        used_disk = 0
        for vm in vms:
            vm_disk = 0
            disk_dic = ast.literal_eval(vm.disk)
            for disk, size in disk_dic.items():
                vm_disk = vm_disk + size
            used_disk = used_disk + int(vm_disk)

        xen_info_dict['disk_used'] = used_disk

        xen_info_dict['cpu_rest'] = xen_info_dict['cpu_all'] - xen_info_dict['cpu_used']
        xen_info_dict['mem_rest'] = xen_info_dict['mem_all'] - xen_info_dict['mem_used']
        xen_info_dict['disk_rest'] = xen_info_dict['disk_all'] - xen_info_dict['disk_used']

        xen_info_list.append(xen_info_dict)

    return HttpResponse(json.dumps(xen_info_list), content_type = "application/json")

def group_info(request):
    key = request.GET.get('q','')
    groups = AssetGroup.objects.filter(name__contains=key)
    group_hosts = {}
    for group in groups:
        hosts = []
        for asset in group.asset_set.all():
            hosts.append(asset.ip)
        group_hosts[group.name] = {'hosts':hosts}
    return HttpResponse(json.dumps(group_hosts), content_type = "application/json")
