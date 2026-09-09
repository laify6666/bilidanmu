# -*- coding: utf-8 -*-
"""按用户提交的视频号（BV号）爬取全量弹幕并入库。

用法: python manage.py bili_fetch_danmaku --bvid BV15BuR6MEeR
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "按 BV 号爬取全量弹幕并入库"

    def add_arguments(self, parser):
        parser.add_argument("--bvid", required=True, help="B站视频 BV 号")

    def handle(self, *args, **options):
        bvid = options["bvid"]
        from apps.fetcher.bili_api import BiliApiError
        from apps.fetcher.danmaku import fetch_and_save

        try:
            video, created, dms = fetch_and_save(bvid)
        except BiliApiError as e:
            self.stderr.write(self.style.ERROR(f"B站接口失败: {e}"))
            return
        except ValueError as e:
            self.stderr.write(self.style.WARNING(str(e)))
            return

        self.stdout.write(self.style.SUCCESS(
            f"视频 {bvid} 弹幕入库完成：{len(dms)} 条，视频行{'新建' if created else '已更新'}"))
