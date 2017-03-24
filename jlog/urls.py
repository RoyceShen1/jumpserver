# coding:utf-8
from django.conf.urls import patterns, include, url
from jlog.views import *

urlpatterns = patterns('',
                       url(r'^list/(\w+)/$', log_list, name='log_list'),
                       url(r'^detail/(\w+)/$', log_detail, name='log_detail'),
                       url(r'^history/$', log_history, name='log_history'),
                       url(r'^log_kill/', log_kill, name='log_kill'),
                       url(r'^record/$', log_record, name='log_record'),
                       url(r'^report/$', log_report, name='log_report'),
                       url(r'^report_asset/$', log_report_asset, name='log_report_asset'),
                      )