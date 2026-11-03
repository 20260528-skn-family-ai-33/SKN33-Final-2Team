import type { DraftDoc } from '@/api/types/draft';
import type { Stored } from './surveyRequest';
export function surveyState(previous: DraftDoc['v2Assessment'], survey: Stored, dirty: boolean): NonNullable<DraftDoc['v2Assessment']> {
  const keep = previous?.generationId === survey.generationId && !dirty;
  return { ...(keep ? previous : {}), generationId: survey.generationId, completed: survey.completed && !dirty,
    materialsReady: keep ? previous.materialsReady : false, activitiesReady: keep ? previous.activitiesReady : false };
}
