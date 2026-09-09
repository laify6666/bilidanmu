from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.web.urls")),          # 弹幕分析页面
    path("api/", include("apps.fetcher.urls")),  # 弹幕爬取接口
]