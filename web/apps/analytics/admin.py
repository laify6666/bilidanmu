# -*- coding: utf-8 -*-
"""Django 管理后台注册。

TODO（）：models.py 建好后在这里注册，例如
from django.contrib import admin
from .models import DanmakuRecord, DanmakuVideo

admin.site.register(DanmakuVideo)
admin.site.register(DanmakuRecord)
"""
from django.contrib import admin
from .models import DanmakuAnalysis, DanmakuRecord, DanmakuVideo

admin.site.register(DanmakuVideo)
admin.site.register(DanmakuRecord)
admin.site.register(DanmakuAnalysis)