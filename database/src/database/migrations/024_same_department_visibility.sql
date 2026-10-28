-- A department head may read only members of the same department.
-- Organization hierarchy is descriptive and grants no additional access.
CREATE OR REPLACE FUNCTION public.employee_can_read_employee(actor integer, target integer)
RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS (
  SELECT 1
  FROM public.employees viewer
  JOIN public.employees owner ON owner.employee_id=target
  WHERE viewer.employee_id=actor AND (
   owner.employee_id=viewer.employee_id OR
   (viewer.is_department_head
    AND viewer.institution_id=owner.institution_id
    AND viewer.department_id=owner.department_id)
  )
 )
$$;

COMMENT ON FUNCTION public.employee_can_read_employee(integer,integer) IS
 '본인 또는 같은 기관·같은 부서의 부서장만 조회 허용. 부서 상하 관계는 조회 권한에 사용하지 않음.';
COMMENT ON FUNCTION public.employee_can_read_project(integer,uuid) IS
 '프로젝트 소유자 본인 또는 소유자와 같은 기관·같은 부서의 부서장만 조회 허용.';
