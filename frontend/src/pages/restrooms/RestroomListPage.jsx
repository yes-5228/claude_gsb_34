import { useState } from 'react';
import { Link } from 'react-router-dom';

import { restroomApi } from '../../api/restrooms.js';
import DataTable from '../../components/DataTable.jsx';
import Field from '../../components/Field.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import Pagination from '../../components/Pagination.jsx';
import { StatusTag } from '../../components/Tags.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { useListQuery } from '../../hooks/useListQuery.js';
import RestroomFormModal from './RestroomFormModal.jsx';

const DEFAULT_FILTERS = { keyword: '', district: '', status: '', grade: '' };

export default function RestroomListPage() {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [editing, setEditing] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const list = useListQuery((params) => restroomApi.list(params), DEFAULT_FILTERS, 10);
  const { data: districts } = useAsync(() => restroomApi.districts(), []);

  const remove = async (row) => {
    let impact;
    try {
      impact = await restroomApi.deleteImpact(row.id);
    } catch (err) {
      toast.error(err.message);
      return;
    }

    const summary = [
      `公厕：${impact.name}（${impact.code} / ${impact.district}）`,
      `巡查记录：${impact.inspection_count} 条`,
      `问题记录：${impact.issue_count} 条（未闭环 ${impact.open_issue_count} 条）`,
      `整改流水：${impact.rectification_record_count} 条；附件：${impact.attachment_count} 个`,
      '',
      impact.action === 'archive'
        ? '强制确认后只会归档公厕台账，巡查、问题、整改流水和附件全部保留，历史报表仍可追溯。'
        : impact.message,
    ].join('\n');

    if (!impact.can_delete) {
      window.alert(`无法删除：\n${summary}\n\n需先处置：\n${impact.blockers.join('\n')}`);
      return;
    }
    if (!window.confirm(`${summary}\n\n确认继续？`)) return;

    const params = {};
    if (impact.action === 'archive') {
      const reason = window.prompt('请填写归档原因（用于审计和月报差异说明）');
      if (reason === null) return;
      params.force = true;
      params.reason = reason || '公厕档案强制归档';
      params.operator = window.prompt('请填写操作人', '管理员') || '管理员';
    }

    try {
      const result = await restroomApi.remove(row.id, params);
      toast.success(result.message || '删除成功');
      list.reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <>
      <PageHeader
        title="公厕台账"
        description="维护全市公厕基础档案、责任人与设施配置"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setEditing(null);
              setShowForm(true);
            }}
          >
            + 新增公厕
          </button>
        }
      />
      <div className="content">
        <section className="card">
          <div className="filter-bar">
            <Field label="关键字" full>
              <input
                value={list.filters.keyword}
                placeholder="名称 / 编号 / 地址 / 责任人"
                onChange={(event) => list.updateFilter('keyword', event.target.value)}
              />
            </Field>
            <Field label="所属区域">
              <select
                value={list.filters.district}
                onChange={(event) => list.updateFilter('district', event.target.value)}
              >
                <option value="">全部</option>
                {(districts || []).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="开放状态">
              <select
                value={list.filters.status}
                onChange={(event) => list.updateFilter('status', event.target.value)}
              >
                <option value="">全部</option>
                {(dictionaries?.restroom_status || []).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="等级">
              <select
                value={list.filters.grade}
                onChange={(event) => list.updateFilter('grade', event.target.value)}
              >
                <option value="">全部</option>
                {(dictionaries?.restroom_grade || []).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <button type="button" className="btn" onClick={list.resetFilters}>
              重置
            </button>
          </div>
        </section>

        <section className="card">
          <DataTable
            loading={list.loading}
            error={list.error}
            rows={list.items}
            emptyText="暂无公厕档案"
            columns={[
              { key: 'code', title: '编号' },
              {
                key: 'name',
                title: '公厕名称',
                render: (row) => <Link to={`/restrooms/${row.id}`}>{row.name}</Link>,
              },
              { key: 'district', title: '区域' },
              { key: 'grade', title: '等级' },
              { key: 'status', title: '状态', render: (row) => <StatusTag status={row.status} /> },
              { key: 'manager', title: '责任人' },
              { key: 'manager_phone', title: '联系电话' },
              { key: 'open_hours', title: '开放时间' },
              {
                key: 'facility',
                title: '设施',
                render: (row) => `${row.stall_count} 蹲位 / ${row.basin_count} 盆`,
              },
              {
                key: 'actions',
                title: '操作',
                render: (row) => (
                  <div className="inline">
                    <Link className="btn-link" to={`/restrooms/${row.id}`}>
                      详情
                    </Link>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() => {
                        setEditing(row);
                        setShowForm(true);
                      }}
                    >
                      编辑
                    </button>
                    <button type="button" className="btn-link danger" onClick={() => remove(row)}>
                      删除
                    </button>
                  </div>
                ),
              },
            ]}
          />
          <Pagination meta={list.meta} onPageChange={list.setPage} />
        </section>
      </div>

      {showForm ? (
        <RestroomFormModal
          restroom={editing}
          onClose={() => setShowForm(false)}
          onSaved={list.reload}
        />
      ) : null}
    </>
  );
}
