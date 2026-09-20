import { restroomApi } from '../../api/restrooms.js';
import DataTable from '../../components/DataTable.jsx';
import Modal from '../../components/Modal.jsx';
import Pagination from '../../components/Pagination.jsx';
import { useListQuery } from '../../hooks/useListQuery.js';
import { formatDateTime } from '../../utils/format.js';

function formatDistribution(dist) {
  const entries = Object.entries(dist || {});
  if (!entries.length) return '-';
  return entries.map(([name, count]) => `${name} ${count}`).join(' / ');
}

/** 公厕删除审计：解释看板与报表中因删除台账而消失的数据。 */
export default function DeletionLogsModal({ onClose }) {
  const logs = useListQuery((params) => restroomApi.deletionLogs(params), {}, 8);

  return (
    <Modal title="公厕删除记录" width={920} onClose={onClose}>
      <p className="hint" style={{ marginTop: 0 }}>
        删除公厕时随删的巡查、问题、整改流水与附件在此留档，统计数字的变化可对照此表解释。
      </p>
      <DataTable
        loading={logs.loading}
        error={logs.error}
        rows={logs.items}
        emptyText="暂无删除记录"
        columns={[
          {
            key: 'created_at',
            title: '删除时间',
            render: (row) => formatDateTime(row.created_at),
          },
          {
            key: 'name',
            title: '公厕',
            wrap: true,
            render: (row) => `${row.name}（${row.code}）`,
          },
          { key: 'district', title: '区域' },
          {
            key: 'scope',
            title: '随删数据',
            render: (row) =>
              `巡查 ${row.inspection_count} · 问题 ${row.issue_count} · 流水 ${row.rectification_count} · 附件 ${row.attachment_count}`,
          },
          {
            key: 'issue_by_status',
            title: '问题状态分布',
            render: (row) => formatDistribution(row.issue_by_status),
          },
          { key: 'operator', title: '操作人', render: (row) => row.operator || '-' },
          { key: 'reason', title: '删除原因', wrap: true, render: (row) => row.reason || '-' },
        ]}
      />
      <Pagination meta={logs.meta} onPageChange={logs.setPage} />
    </Modal>
  );
}
