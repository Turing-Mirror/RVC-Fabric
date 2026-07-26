# -*- coding: utf-8 -*-
"""launcher/online/download_queue — 社区下载并发队列状态机."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.online.download_queue import (
    STATE_ACTIVE,
    STATE_IDLE,
    STATE_QUEUED,
    DownloadQueue,
)


def test_request_starts_until_cap_then_waits():
    q = DownloadQueue(max_active=2)
    assert q.request("a") == "start"
    assert q.request("b") == "start"
    assert q.request("c") == "wait"
    assert q.state("a") == STATE_ACTIVE
    assert q.state("c") == STATE_QUEUED
    assert q.state("x") == STATE_IDLE


def test_duplicate_request_is_busy():
    q = DownloadQueue(max_active=1)
    assert q.request("a") == "start"
    assert q.request("a") == "busy"
    assert q.request("b") == "wait"
    assert q.request("b") == "busy"


def test_finish_promotes_fifo():
    q = DownloadQueue(max_active=1)
    q.request("a")
    q.request("b")
    q.request("c")
    assert q.finish("a") == ["b"]
    assert q.state("b") == STATE_ACTIVE
    assert q.state("c") == STATE_QUEUED
    assert q.finish("b") == ["c"]
    assert q.finish("c") == []
    assert not q.has_work()


def test_finish_waiting_item_removes_without_promotion():
    q = DownloadQueue(max_active=1)
    q.request("a")
    q.request("b")
    assert q.finish("b") == []  # 从等待队列移除，不影响 active
    assert q.state("a") == STATE_ACTIVE
    assert q.state("b") == STATE_IDLE


def test_percent_tracking():
    q = DownloadQueue(max_active=1)
    q.request("a")
    assert q.percent("a") == -1  # 未收到进度前 = 未知
    q.set_percent("a", 37)
    assert q.percent("a") == 37
    q.set_percent("a", 999)
    assert q.percent("a") == 100
    q.set_percent("zzz", 50)  # 非 active 静默忽略
    assert q.percent("zzz") == 0


def test_finish_unknown_id_is_noop():
    q = DownloadQueue(max_active=2)
    q.request("a")
    assert q.finish("nope") == []
    assert q.state("a") == STATE_ACTIVE


def test_max_active_floor_is_one():
    q = DownloadQueue(max_active=0)
    assert q.request("a") == "start"
    assert q.request("b") == "wait"
