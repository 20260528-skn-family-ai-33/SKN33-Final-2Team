/* 주소 ↔ 화면. handle: 좌측 메뉴 강조(nav)·제목(title)·본문 폭(width)·권한(role) — 5차 화면 정의(scr.*)의 nav·title·width·role 그대로 */
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { ChecksPage } from '@/features/assessment/ChecksPage';
import { PostCheckPage } from '@/features/assessment/PostCheckPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { HomePage } from '@/features/home/HomePage';
import { MePage } from '@/features/profile/MePage';
import { ReportPage } from '@/features/report/ReportPage';
import { ResourcePage, ResourcesPage } from '@/features/resources/ResourcePages';
import { CommentsRoute } from '@/features/roadmap/CommentsRoute';
import { RevisePage } from '@/features/roadmap/RevisePage';
import { ConfirmedPage, RoadmapPage } from '@/features/roadmap/RoadmapPages';
import { DetailsCheck, DetailsStep } from '@/features/draft/details/DetailsStep';
import { DraftScreen, editGate, genGate, optionsGate } from '@/features/draft/DraftScreen';
import { GenerationStep } from '@/features/draft/generation/GenerationStep';
import { GoalStep } from '@/features/draft/goal/GoalStep';
import { OptionsStep } from '@/features/draft/options/OptionsStep';
import { QuizStep } from '@/features/draft/quiz/QuizStep';
import { ResultEdit, ResultStep } from '@/features/draft/result/ResultStep';
import { ReviewStep } from '@/features/draft/review/ReviewStep';
import { AppShell, type ScreenHandle } from './layout/AppShell';
import { Page } from '@/shared/ui/parts';
import { paths } from './paths';

/* 다음 커밋에서 옮길 화면 자리(이슈 #20 PR의 중간 커밋에만 있음) */
const Soon = () => <Page title="다음 커밋에서 옮겨요" lead="이 화면은 이슈 #20 PR의 다음 커밋에서 React로 옮겨요. 커밋을 하나씩 확인할 때만 보이는 자리예요." />;

const r = (path: string, element: React.ReactNode, handle: ScreenHandle): RouteObject => ({ path, element, handle });

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      r(paths.login, <LoginPage />, { title: '로그인', role: 'public' }),
      r(paths.home, <HomePage />, { nav: 'home', title: '홈', width: 'wide' }),
      r(paths.me, <MePage />, { nav: 'me', title: '내 정보', width: 'wide' }),
      // 새 로드맵 작성
      r(paths.newGoal, <DraftScreen><GoalStep /></DraftScreen>, { nav: 'new', title: '새 로드맵 작성', width: 'wide' }),
      r(paths.newDetails, <DraftScreen step="details"><DetailsStep /></DraftScreen>, { nav: 'new', title: '세부 사항', width: 'wide' }),
      r(paths.newDetailsCheck, <DraftScreen step="details"><DetailsCheck /></DraftScreen>, { nav: 'new', title: '세부 사항 확인', width: 'wide' }),
      r(paths.newQuiz, <DraftScreen step="quiz"><QuizStep /></DraftScreen>, { nav: 'new', title: '사전 점검', width: 'wide' }),
      r(paths.newResult, <DraftScreen step="result"><ResultStep /></DraftScreen>, { nav: 'new', title: '점검 결과', width: 'wide' }),
      r(paths.newResultEdit, <DraftScreen step="result" extra={editGate}><ResultEdit /></DraftScreen>, { nav: 'new', title: '점검 결과 수정', width: 'wide' }),
      r(paths.newGen, <DraftScreen extra={genGate} step="goal" remember={false}><GenerationStep /></DraftScreen>, { nav: 'new', title: '로드맵 3안 작성', width: 'wide' }),
      r(paths.newOptions, <DraftScreen extra={optionsGate} step="goal"><OptionsStep /></DraftScreen>, { nav: 'new', title: '로드맵 3안', width: 'xwide' }),
      r(paths.newReview, <DraftScreen step="review"><ReviewStep /></DraftScreen>, { nav: 'new', title: '검토·확정', width: 'wide' }),
      // 내 로드맵
      r(paths.roadmaps, <RoadmapPage />, { nav: 'roadmap', title: '내 로드맵', width: 'wide' }),
      r('/roadmaps/:pid', <RoadmapPage />, { nav: 'roadmap', title: '내 로드맵', width: 'wide' }),
      r('/roadmaps/:pid/confirmed', <ConfirmedPage />, { nav: 'roadmap', title: '로드맵 확정' }),
      r('/roadmaps/:pid/revise', <RevisePage />, { nav: 'roadmap', title: '수정 요청', width: 'wide' }),
      r('/roadmaps/:pid/comments', <CommentsRoute />, { nav: 'roadmap', title: '부서장 코멘트' }),
      r('/roadmaps/:pid/post', <PostCheckPage />, { nav: 'checks', title: '사후 점검', width: 'wide' }),
      // 점검·보고서
      r(paths.checks, <ChecksPage />, { nav: 'checks', title: '점검·보고서', width: 'wide' }),
      r('/reports/:rid', <ReportPage />, { nav: 'checks', title: '결과 보고서', width: 'wide' }),
      // 학습 자료
      r(paths.resources, <ResourcesPage />, { nav: 'resources', title: '학습 자료', width: 'wide' }),
      r('/resources/:id', <ResourcePage />, { nav: 'resources', title: '학습 자료' }),
      // 부서장
      r(paths.team, <Soon />, { nav: 'm-list', title: '소속 직원 계획', width: 'wide', role: 'mgr' }),
      r('/team/:uid', <Soon />, { nav: 'm-list', title: '직원 로드맵', width: 'wide', role: 'mgr' }),
      r('/team/:uid/plans/:pid', <Soon />, { nav: 'm-list', title: '직원 로드맵', width: 'wide', role: 'mgr' }),
      r('/team/:uid/plans/:pid/sent', <Soon />, { nav: 'm-list', title: '코멘트 전달', role: 'mgr' }),
      r('/team/:uid/reports/:rid', <Soon />, { nav: 'm-list', title: '직원 결과 보고서', width: 'wide', role: 'mgr' }),
      // 관리자
      r(paths.admin, <Soon />, { title: '관리자', width: 'wide', role: 'admin' }),
      r('/admin/data/:ds', <Soon />, { title: '관리자', width: 'wide adm-ds', role: 'admin' }),
      r(paths.adminRegulations, <Soon />, { title: '관리자', width: 'wide', role: 'admin' }),
      // 예전 규정 표 주소(2026-10-26 원문 PDF 화면으로 바뀜)
      r(paths.adminData('regulations'), <Soon />, { title: '관리자', role: 'admin' }),
      r('/admin/uploads/:id', <Soon />, { title: '관리자', width: 'wide', role: 'admin' }),
      r(paths.adminHistory, <Soon />, { title: '관리자', width: 'wide', role: 'admin' }),
      r('/admin/*', <Soon />, { title: '관리자', role: 'admin' }),
      { path: '*', element: <Navigate to={paths.home} replace /> },
    ],
  },
]);
