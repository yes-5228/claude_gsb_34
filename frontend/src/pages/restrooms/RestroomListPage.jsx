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
import DeletionLogsModal from './DeletionLogsModal.jsx';
import RestroomDeleteModal from './RestroomDeleteModal.jsx';
import RestroomFormModal from './RestroomFormModal.jsx';

const DEFAULT_FILTERS = { keyword: '', district: '', status: '', grade: '' };

export default function RestroomListPage() {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [editing, setEditing] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const list = useListQuery((params) => restroomApi.list(params), DEFAULT_FILTERS, 10);
  const { data: districts } = useAsync(() => restroomApi.districts(), []);

  // 删除前先拉取影响面：随删多少数据、是否被未闭环问题阻断，在弹窗中明示
  const askRemove = async (row) => {
    try {
      const impact = await restroomApi.deletionImpact(row.id);
      setDeleting({ row, impact });
    } catch (err) {
      toast.error(err.message);
    }
  };

  const confirmRemove = async (reason) => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      const { row, impact } = deleting;
      const result = await restroomApi.remove(row.id, {
        force: impact.requires_force ? true : undefined,
        reason: reason || undefined,
      });
      toast.success(result.message || '删除成功');
      setDeleting(null);
      list.reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="公厕台账"
        description="维护全市公厕基础档案、责任人与设施配置"
        actions={
          <div className="inline">
            <button type="button" className="btn" onClick={() => setShowLogs(true)}>
              删除记录
            </button>
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
          </div>
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
                    <button type="button" className="btn-link danger" onClick={() => askRemove(row)}>
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

      {deleting ? (
        <RestroomDeleteModal
          restroom={deleting.row}
          impact={deleting.impact}
          busy={deleteBusy}
          onCancel={() => setDeleting(null)}
          onConfirm={confirmRemove}
        />
      ) : null}

      {showLogs ? <DeletionLogsModal onClose={() => setShowLogs(false)} /> : null}
    </>
  );
}
