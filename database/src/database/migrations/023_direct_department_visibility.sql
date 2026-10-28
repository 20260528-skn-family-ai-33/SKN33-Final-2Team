-- Read access follows direct reports, not every descendant department.
-- Existing employee/project IDs and all stored data remain unchanged.
CREATE OR REPLACE FUNCTION public.employee_can_read_employee(actor integer, target integer)
RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS (
  SELECT 1
  FROM public.employees viewer
  JOIN public.employees owner ON owner.employee_id=target
  LEFT JOIN public.departments owned_department ON owned_department.department_id=owner.department_id
  WHERE viewer.employee_id=actor AND (
   owner.employee_id=viewer.employee_id OR
   (viewer.is_department_head
    AND viewer.institution_id=owner.institution_id
    AND (
     owner.department_id=viewer.department_id OR
     (owner.is_department_head AND owned_department.parent_department_id=viewer.department_id)
    ))
  )
 )
$$;

CREATE OR REPLACE FUNCTION public.employee_can_read_project(actor integer, target uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS (
  SELECT 1 FROM public.projects project
  WHERE project.project_id=target
    AND public.employee_can_read_employee(actor,project.employee_id)
 )
$$;

COMMENT ON FUNCTION public.employee_can_read_employee(integer,integer) IS
 '본인 또는 같은 기관의 부서장: 자기 부서 구성원과 바로 아래 부서의 부서장만 조회 허용. 재귀적 하위 부서 조회는 허용하지 않음.';
COMMENT ON FUNCTION public.employee_can_read_project(integer,uuid) IS
 '프로젝트 소유자에 대해 employee_can_read_employee의 직속 보고 범위로 조회 가능 여부를 반환.';
