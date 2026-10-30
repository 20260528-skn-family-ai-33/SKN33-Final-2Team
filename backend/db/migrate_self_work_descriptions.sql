-- 선택적 구판 데이터 이관. 앱을 배포하기 전 백업한 별도 DB에서 먼저 확인한다.
-- 새 앱은 구판 edited.workDesc도 읽으므로 즉시 일괄 실행할 필요는 없다.
-- 충돌 시 전체 롤백한다. 직원별 원하는 값을 확인한 뒤 앱에서 명시적으로 저장한다.
BEGIN;
LOCK TABLE public.employees, app_ext.employee_self_inputs IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE conflicts integer;
BEGIN
  SELECT count(*) INTO conflicts
  FROM public.employees e
  JOIN app_ext.employee_self_inputs s USING (employee_id)
  WHERE s.edited ? 'workDesc'
    AND e.planned_project_description IS NOT NULL
    AND btrim(e.planned_project_description) IS DISTINCT FROM nullif(btrim(s.edited->>'workDesc'), '');
  IF conflicts > 0 THEN
    RAISE EXCEPTION 'Conflicting work descriptions: %. Review the values before migration.', conflicts;
  END IF;
END $$;

UPDATE public.employees e
SET planned_project_description = nullif(btrim(s.edited->>'workDesc'), ''), updated_at = now()
FROM app_ext.employee_self_inputs s
WHERE e.employee_id = s.employee_id AND s.edited ? 'workDesc'
  AND e.planned_project_description IS DISTINCT FROM nullif(btrim(s.edited->>'workDesc'), '');

-- 구판 baseline에 없던 처음 설명은 추정하지 않는다. 되돌려도 현재 팀 열을 보존한다.
UPDATE app_ext.employee_self_inputs
SET edited = edited - 'workDesc' - 'workDescHash'
WHERE edited ? 'workDesc';
COMMIT;
