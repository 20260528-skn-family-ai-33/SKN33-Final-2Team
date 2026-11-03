import type { DraftDoc } from '@/api/types/draft';
import { sortKeys } from '@/shared/lib/format';
export const skillInputKey=(draft: DraftDoc)=>JSON.stringify(sortKeys([draft.goal,draft.project,draft.prefs,draft.doc?.status==='ok'?draft.doc.summary:null]));
export const skillsReady=(draft: DraftDoc)=>!!draft.selectedSkills?.length && draft.skillInputKey===skillInputKey(draft);
