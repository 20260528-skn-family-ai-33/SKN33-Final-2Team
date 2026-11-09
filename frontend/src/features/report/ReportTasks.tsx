/* 결과 보고서 과제 (#96) — 부서장: 보고서를 보고 과제를 써서 보낸다. 직원: 받은 과제에 글·파일로 결과를 낸다.
   로드맵 계획을 조정하는 코멘트와는 별개다. 과제 목록은 작업 공간이 아니라 서버에서 바로 받는다(상대방이 바꾼 내용을 알림으로 새로 받기 위해) */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { taskFileUrl, tasksApi } from '@/api/endpoints/tasks';
import type { ReportTask } from '@/api/types/task';
import { failToast } from '@/shared/lib/fail';
import { toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { putTasks, TASK_ANSWER_MAX, TASK_BODY_MAX, TASK_FILE_MAX, taskKey } from './taskData';

function TaskItem({ task, asHead, children }: { task: ReportTask; asHead: boolean; children?: React.ReactNode }) {
  return (
    <div className="card rtask">
      <div className="rtask-h">
        <span className="small muted">
          {task.head.name} · {task.createdAt}
        </span>
        <span className={`tag${task.submittedAt ? ' acc' : ''}`}>{task.submittedAt ? `제출함 · ${task.submittedAt}` : '제출 전'}</span>
      </div>
      <p className="rtask-b">{task.body}</p>
      {task.submittedAt ? (
        <div className="rtask-a">
          <b>제출한 결과</b>
          {task.answer ? <p className="rtask-b">{task.answer}</p> : null}
          {task.file ? (
            <a className="link" href={taskFileUrl(task.planId, task.id, asHead)} download={task.file.name}>
              {task.file.name}
            </a>
          ) : null}
        </div>
      ) : (
        children
      )}
    </div>
  );
}

/** 불러오기 실패 안내(다시 시도 버튼) */
function LoadFailed({ retry }: { retry: () => void }) {
  return (
    <p className="small muted" role="alert">
      과제를 불러오지 못했어요.{' '}
      <button type="button" className="link" onClick={retry}>
        다시 시도
      </button>
    </p>
  );
}

/** 부서장의 직원 결과 보고서 화면 */
export function HeadReportTasks({ planId, memberName }: { planId: string; memberName: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: taskKey(planId), queryFn: () => tasksApi.ofMember(planId).then((r) => r.tasks) });
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);

  const send = async () => {
    setSending(true);
    try {
      const res = await tasksApi.send(planId, text.trim());
      await putTasks(qc, planId, res.tasks);
      setText('');
      toast(`${memberName} 님에게 과제를 보냈어요`);
    } catch (err) {
      failToast(err, '과제를 보내지 못했어요');
    } finally {
      setSending(false);
    }
  };

  const tasks = q.data || [];
  return (
    <div className="sec">
      <div className="sec-h">
        <h2 className="st">후속 과제{tasks.length ? ` ${tasks.length}` : ''}</h2>
      </div>
      {q.isError ? <LoadFailed retry={() => void q.refetch()} /> : null}
      <div className="stack">
        {tasks.map((task) => (
          <TaskItem key={task.id} task={task} asHead />
        ))}
        <div className="card">
          <label className="small muted" htmlFor="report-task-body">
            보고서를 보고 {memberName} 님에게 낼 과제를 적어 주세요. 로드맵 계획을 바꾸는 코멘트와는 별개예요.
          </label>
          <textarea
            id="report-task-body"
            className="textarea"
            rows={5}
            maxLength={TASK_BODY_MAX}
            value={text}
            disabled={sending}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="actions rtask-act">
            <button type="button" className="btn pri sm" disabled={sending || !text.trim()} onClick={() => void send()}>
              {sending ? '보내는 중…' : '과제 보내기'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SubmitForm({ task }: { task: ReportTask }) {
  const qc = useQueryClient();
  const [answer, setAnswer] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const pick = (picked: File | null) => {
    if (picked && picked.size > TASK_FILE_MAX) {
      toast('파일이 너무 커요(15MB까지)');
      return;
    }
    setFile(picked);
  };

  const submit = async () => {
    setBusy(true);
    try {
      const res = await tasksApi.submit(task.planId, task.id, answer.trim(), file);
      await putTasks(qc, task.planId, res.tasks);
      toast('과제 결과를 제출했어요 · 부서장에게 알림이 갔어요');
    } catch (err) {
      failToast(err, '과제 결과를 제출하지 못했어요');
    } finally {
      setBusy(false);
    }
  };

  const inputId = `report-task-answer-${task.id}`;
  return (
    <div className="rtask-form">
      <label className="small muted" htmlFor={inputId}>
        결과를 글로 적거나 파일을 붙여 주세요. 제출한 뒤에는 고칠 수 없어요.
      </label>
      <textarea id={inputId} className="textarea sm" maxLength={TASK_ANSWER_MAX} value={answer} disabled={busy} onChange={(e) => setAnswer(e.target.value)} />
      {file ? (
        <div className="file-on">
          <Icon name="file" />
          <div className="tx">
            <b>{file.name}</b>
          </div>
          <button type="button" className="link" disabled={busy} onClick={() => setFile(null)}>
            빼기
          </button>
        </div>
      ) : (
        <label className="drop">
          <input type="file" disabled={busy} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
          <span className="ico">
            <Icon name="file" />
          </span>
          <span>
            <b>결과물 파일 고르기</b>
            <small>15MB까지 · 내지 않아도 돼요</small>
          </span>
        </label>
      )}
      <div className="actions rtask-act">
        <button type="button" className="btn pri sm" disabled={busy || (!answer.trim() && !file)} onClick={() => void submit()}>
          {busy ? '제출하는 중…' : '결과 제출'}
        </button>
      </div>
    </div>
  );
}

/** 직원의 결과 보고서 화면. 받은 과제가 없으면 아무것도 그리지 않는다 */
export function MemberReportTasks({ planId }: { planId: string }) {
  const q = useQuery({ queryKey: taskKey(planId), queryFn: () => tasksApi.mine(planId).then((r) => r.tasks) });
  // 이미 받은 목록이 있으면 다시 받기가 실패해도 목록을 유지한다. 폼이 사라지면 쓰던 답변과 고른 파일을 잃는다(PR #140 리뷰)
  const failed = q.isError ? <LoadFailed retry={() => void q.refetch()} /> : null;
  const tasks = q.data || [];
  if (!tasks.length) return failed;
  return (
    <div className="sec">
      <div className="sec-h">
        <h2 className="st">부서장 과제 {tasks.length}</h2>
      </div>
      {failed}
      <div className="stack">
        {tasks.map((task) => (
          <TaskItem key={task.id} task={task} asHead={false}>
            <SubmitForm task={task} />
          </TaskItem>
        ))}
      </div>
    </div>
  );
}
