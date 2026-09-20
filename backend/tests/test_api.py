"""接口级测试：覆盖台账、巡查、问题整改与统计看板。"""

from datetime import datetime, timedelta

import pytest

from tests.conftest import full_items


def test_health_and_dictionaries(client):
    assert client.get("/health").json()["status"] == "ok"
    payload = client.get("/api/v1/meta/dictionaries").json()
    assert "待整改" in payload["issue_status"]
    assert len(payload["inspection_check_items"]) == 8
    assert payload["issue_transitions"]["待整改"] == ["整改中", "已关闭"]


def test_restroom_crud_and_delete_guard(client, restroom):
    assert restroom["code"].startswith("WC-")

    listed = client.get("/api/v1/restrooms", params={"district": "测试区"}).json()
    assert listed["meta"]["total"] >= 1

    detail = client.get(f"/api/v1/restrooms/{restroom['id']}").json()
    assert detail["inspection_count"] == 0
    assert detail["open_issue_count"] == 0

    updated = client.patch(
        f"/api/v1/restrooms/{restroom['id']}", json={"status": "维修中", "manager": "新责任人"}
    ).json()
    assert updated["status"] == "维修中"
    assert updated["manager"] == "新责任人"

    # 存在关联数据时不允许直接删除
    client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "测试巡查员",
            "shift": "早班",
            "items": full_items(9),
        },
    )
    blocked = client.delete(f"/api/v1/restrooms/{restroom['id']}")
    assert blocked.status_code == 409

    ok = client.delete(f"/api/v1/restrooms/{restroom['id']}", params={"force": "true"})
    assert ok.status_code == 200
    assert client.get(f"/api/v1/restrooms/{restroom['id']}").status_code == 404


def test_inspection_scoring_and_filter(client, restroom):
    good = client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "李巡查",
            "shift": "中班",
            "items": full_items(9),
            "remark": "整体良好",
        },
    ).json()
    assert good["score"] == 90.0
    assert good["grade"] == "优秀"
    assert good["result"] == "正常"

    bad_items = full_items(9)
    bad_items[0]["score"] = 3
    bad_items[0]["remark"] = "地面污渍"
    bad = client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "李巡查",
            "shift": "晚班",
            "items": bad_items,
        },
    ).json()
    assert bad["result"] == "发现问题"
    assert bad["score"] < 90

    filtered = client.get(
        "/api/v1/inspections", params={"result": "发现问题", "restroom_id": restroom["id"]}
    ).json()
    assert filtered["meta"]["total"] == 1
    assert filtered["items"][0]["id"] == bad["id"]
    assert filtered["items"][0]["restroom"]["name"] == restroom["name"]

    today = datetime.now().date().isoformat()
    ranged = client.get(
        "/api/v1/inspections", params={"date_from": today, "date_to": today}
    ).json()
    assert ranged["meta"]["total"] == 2

    duplicate = full_items(5) + [{"name": "地面与台阶清洁", "score": 4}]
    rejected = client.post(
        "/api/v1/inspections",
        json={"restroom_id": restroom["id"], "inspector": "李巡查", "items": duplicate},
    )
    assert rejected.status_code == 400

    empty = client.post(
        "/api/v1/inspections",
        json={"restroom_id": restroom["id"], "inspector": "李巡查", "items": []},
    )
    assert empty.status_code == 422


def test_issue_lifecycle(client, restroom):
    inspection = client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "王巡查",
            "items": full_items(4),
        },
    ).json()

    issue = client.post(
        "/api/v1/issues",
        json={
            "restroom_id": restroom["id"],
            "inspection_id": inspection["id"],
            "title": "地面污渍未清理",
            "description": "巡查发现地面有明显污渍",
            "category": "保洁不到位",
            "severity": "严重",
            "reporter": "王巡查",
            "assignee": "保洁班组",
            "deadline": (datetime.now() - timedelta(days=1)).isoformat(),
        },
    ).json()
    assert issue["status"] == "待整改"
    assert len(issue["records"]) == 1
    assert issue["records"][0]["action"] == "上报问题"

    # 越级流转被拒绝：待整改 -> 已完成
    invalid = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "已完成", "operator": "值班长"},
    )
    assert invalid.status_code == 400
    assert "不允许流转" in invalid.json()["detail"]

    options = client.get(f"/api/v1/issues/{issue['id']}/transitions").json()
    assert {option["status"] for option in options} == {"整改中", "已关闭"}

    processing = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "整改中", "operator": "保洁班组张伟", "remark": "已安排清洗"},
    ).json()
    assert processing["status"] == "整改中"
    assert processing["assignee"] == "保洁班组"

    reviewing = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "待验收", "operator": "保洁班组张伟", "remark": "整改完成待验收"},
    ).json()
    assert reviewing["status"] == "待验收"

    # 验收驳回回到整改中
    rejected = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "整改中", "operator": "王巡查", "remark": "角落仍有残留"},
    ).json()
    assert rejected["status"] == "整改中"
    assert rejected["records"][-1]["action"] == "验收驳回"

    for target in ("待验收", "已完成", "已关闭"):
        payload = {"to_status": target, "operator": "值班长", "remark": f"流转到{target}"}
        response = client.post(f"/api/v1/issues/{issue['id']}/transitions", json=payload)
        assert response.status_code == 200, response.text
    final = response.json()
    assert final["status"] == "已关闭"
    assert final["closed_at"] is not None
    assert [record["to_status"] for record in final["records"]][-1] == "已关闭"

    closed_record = client.post(
        f"/api/v1/issues/{issue['id']}/records",
        json={"action": "整改进度", "operator": "值班长", "remark": "补充说明"},
    )
    assert closed_record.status_code == 400

    overdue = client.get("/api/v1/issues", params={"overdue": "true"}).json()
    assert overdue["meta"]["total"] == 0

    # 巡查记录可反查关联问题数量
    detail = client.get(f"/api/v1/inspections/{inspection['id']}").json()
    assert detail["issue_count"] == 1


def test_issue_requires_matching_restroom(client, restroom):
    other = client.post(
        "/api/v1/restrooms",
        json={"name": "另一座公厕", "district": "测试区", "address": "测试路 2 号"},
    ).json()
    inspection = client.post(
        "/api/v1/inspections",
        json={"restroom_id": other["id"], "inspector": "周巡查", "items": full_items(9)},
    ).json()
    mismatch = client.post(
        "/api/v1/issues",
        json={
            "restroom_id": restroom["id"],
            "inspection_id": inspection["id"],
            "title": "关联错误",
        },
    )
    assert mismatch.status_code == 400
    assert "不一致" in mismatch.json()["detail"]


def test_restroom_deletion_impact_and_audit(client, restroom):
    # 准备：1 条巡查 + 1 条带附件的问题（初始为未闭环）
    client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "测试巡查员",
            "items": full_items(8),
        },
    )
    issue = client.post(
        "/api/v1/issues",
        json={
            "restroom_id": restroom["id"],
            "title": "水龙头漏水",
            "category": "设施损坏",
            "images": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        },
    ).json()

    # 影响面评估：未闭环问题阻断删除
    impact = client.get(f"/api/v1/restrooms/{restroom['id']}/deletion-impact").json()
    assert impact["requires_force"] is True
    assert impact["deletable"] is False
    assert impact["inspection_count"] == 1
    assert impact["issue_count"] == 1
    assert impact["open_issue_count"] == 1
    assert impact["rectification_count"] == 1  # 上报问题时写入的首条流水
    assert impact["attachment_count"] == 2
    assert impact["issue_by_status"] == {"待整改": 1}
    assert impact["blocking_reasons"]

    # 未闭环问题存在时，force=true 同样被拒绝
    blocked = client.delete(f"/api/v1/restrooms/{restroom['id']}", params={"force": "true"})
    assert blocked.status_code == 409
    assert "未闭环" in blocked.json()["detail"]

    # 缺 force 时拒绝并提示影响面
    need_force = client.delete(f"/api/v1/restrooms/{restroom['id']}")
    assert need_force.status_code == 409
    assert "整改流水" in need_force.json()["detail"]

    # 先处置：关闭问题后再评估，允许删除
    client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "已关闭", "operator": "值班长", "remark": "公厕停用，作废"},
    )
    impact = client.get(f"/api/v1/restrooms/{restroom['id']}/deletion-impact").json()
    assert impact["deletable"] is True
    assert impact["open_issue_count"] == 0
    assert impact["rectification_count"] == 2

    ok = client.delete(
        f"/api/v1/restrooms/{restroom['id']}",
        params={"force": "true", "operator": "测试员", "reason": "公厕拆除"},
    )
    assert ok.status_code == 200
    assert "随删巡查 1 条、问题 1 条、整改流水 2 条、附件 2 个" in ok.json()["message"]

    # 关联数据已级联清除
    assert client.get(f"/api/v1/restrooms/{restroom['id']}").status_code == 404
    assert client.get(f"/api/v1/issues/{issue['id']}").status_code == 404
    inspections = client.get(
        "/api/v1/inspections", params={"restroom_id": restroom["id"]}
    ).json()
    assert inspections["meta"]["total"] == 0

    # 删除审计完整留存，可解释看板与报表中消失的数据
    logs = client.get("/api/v1/restrooms/deletion-logs").json()
    mine = [log for log in logs["items"] if log["restroom_id"] == restroom["id"]]
    assert len(mine) == 1
    log = mine[0]
    assert log["code"] == restroom["code"]
    assert log["district"] == restroom["district"]
    assert log["inspection_count"] == 1
    assert log["issue_count"] == 1
    assert log["rectification_count"] == 2
    assert log["attachment_count"] == 2
    assert log["issue_by_status"] == {"已关闭": 1}
    assert log["issue_by_category"] == {"设施损坏": 1}
    assert log["restroom_snapshot"]["name"] == restroom["name"]
    assert log["operator"] == "测试员"
    assert log["reason"] == "公厕拆除"

    # 看板总览能体现累计删除数
    overview = client.get("/api/v1/stats/overview").json()
    assert overview["restroom_deleted_total"] >= 1


def test_force_delete_rolls_back_on_failure(client, restroom, monkeypatch):
    # 准备：巡查 + 已关闭问题，使强制删除满足前置条件
    client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "测试巡查员",
            "items": full_items(8),
        },
    )
    issue = client.post(
        "/api/v1/issues",
        json={"restroom_id": restroom["id"], "title": "标识牌褪色"},
    ).json()
    client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "已关闭", "operator": "值班长"},
    )

    # 模拟提交阶段故障：删除与审计写入必须整体回退
    from sqlalchemy.orm import Session as OrmSession

    logs_before = client.get("/api/v1/restrooms/deletion-logs").json()["meta"]["total"]

    def boom(self):
        raise RuntimeError("模拟提交失败")

    monkeypatch.setattr(OrmSession, "commit", boom)
    with pytest.raises(RuntimeError):
        client.delete(f"/api/v1/restrooms/{restroom['id']}", params={"force": "true"})
    monkeypatch.undo()

    # 公厕、巡查、问题及整改流水全部完好，且未新增审计记录
    assert client.get(f"/api/v1/restrooms/{restroom['id']}").status_code == 200
    detail = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert detail["status"] == "已关闭"
    assert len(detail["records"]) == 2
    inspections = client.get(
        "/api/v1/inspections", params={"restroom_id": restroom["id"]}
    ).json()
    assert inspections["meta"]["total"] == 1
    logs_after = client.get("/api/v1/restrooms/deletion-logs").json()["meta"]["total"]
    assert logs_after == logs_before


def test_dashboard_stats(client, restroom):
    payload = client.get("/api/v1/stats/dashboard", params={"trend_days": 7}).json()
    overview = payload["overview"]
    assert overview["restroom_total"] >= 1
    assert overview["inspection_total"] >= 1
    assert len(payload["inspection_trend"]) == 7
    assert {item["name"] for item in payload["issue_by_status"]} == {
        "待整改",
        "整改中",
        "待验收",
        "已完成",
        "已关闭",
    }
    assert payload["top_restrooms"]
    assert "rectification_rate" in overview
