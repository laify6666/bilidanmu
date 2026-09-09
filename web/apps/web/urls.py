# -*- coding: utf-8 -*-
"""弹幕分析页面路由。"""
from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(url="/danmaku/", permanent=False), name="home"),  # / -> 输入页
    path("danmaku/", views.danmaku_index, name="danmaku_index"),
    path("danmaku/analyze/", views.danmaku_analyze, name="danmaku_analyze"),
]