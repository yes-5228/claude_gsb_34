import { useState } from 'react';

import Modal from '../../components/Modal.jsx';

function ImpactRow({ label, value, danger }) {
  return (
    <div className="inline" style={{ justifyContent: 'space-between' }}>
      <span className="hint">{label}</span>
      <strong style={danger && value ? { color: '#dc2626' } : undefined}>{value}</strong>
    </div>
  );
}

/**
 * 删除确认弹窗：先展示影响面（随删数据规模与阻断原因），
 * 存在未闭环问题时禁止删除，只允许返回先处置问题。
 */
export default function RestroomDeleteModal({ restroom, impact, busy, onCancel, onConfirm }) {
  const [reason, setReason] = useState('');
  const blocked = !impact.deletable;

  const footer = blocked ? (
    <button type="button" className="btn btn-primary" onClick={onCancel}>
      知道了
    </button>
  ) : (
    <>
      <button type="button" className="btn" onClick={onCancel}>
        取消
      </button>
      <button
        type="button"
        className="btn btn-danger"
        disabled={busy}
        onClick={() => onConfirm(reason.trim())}
      >
        {busy ? '删除中…' : impact.requires_force ? '强制删除' : '确认删除'}
      </button>
    </>
  );

  return (
    <Modal title={`删除公厕「${restroom.name}」`} width={520} onClose={onCancel} footer={footer}>
      {blocked ? (
        <div className="alert alert-error">
          {impact.blocking_reasons.map((item) => (
            <div key={item}>{item}</div>
          ))}
        </div>
      ) : (
        <div className="alert alert-info">
          删除动作会写入删除审计，看板与报表中减少的数据可据此追溯。
        </div>
      )}

      <div className="card" style={{ padding: 12, marginBottom: 12 }}>
        <ImpactRow label="公厕档案" value={`${impact.name}（${impact.code}）`} />
        <ImpactRow label="巡查记录（随删）" value={`${impact.inspection_count} 条`} />
        <ImpactRow
          label="问题记录（随删）"
          value={`${impact.issue_count} 条`}
          danger={impact.open_issue_count > 0}
        />
        <ImpactRow label="整改流水（随删）" value={`${impact.rectification_count} 条`} />
        <ImpactRow label="现场附件（随删）" value={`${impact.attachment_count} 个`} />
        {impact.open_issue_count > 0 ? (
          <ImpactRow label="其中未闭环问题" value={`${impact.open_issue_count} 条`} danger />
        ) : null}
      </div>

      {blocked ? (
        <p className="hint">请先到「问题上报」模块将未闭环问题完成整改闭环或关闭，再回来删除。</p>
      ) : (
        <div className="field">
          <label>删除原因（选填，写入删除审计）</label>
          <input
            value={reason}
            maxLength={200}
            placeholder="例如：公厕拆除、规划调整"
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      )}
    </Modal>
  );
}
