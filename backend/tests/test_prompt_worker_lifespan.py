import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch


class PromptWorkerLifespanTests(IsolatedAsyncioTestCase):
    async def test_disabled_worker_does_not_schedule_or_load_cases(self):
        from app.main import lifespan, app
        with patch('app.jobs.mark_lost', return_value=0), patch.dict('os.environ', {'PROMPT_IMPROVEMENT_ENABLED': '0'}), patch('app.services.prompt_evaluation_replay.load_cases') as load, patch('app.services.prompt_improvement_worker.serve', new_callable=AsyncMock) as serve:
            async with lifespan(app):
                await asyncio.sleep(0)
        load.assert_not_called()
        serve.assert_not_called()

    async def test_explicit_enable_validates_cases_and_starts_cancellable_task(self):
        from app.main import lifespan, app
        entered = asyncio.Event()
        async def background(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        with patch('app.jobs.mark_lost', return_value=0), patch.dict('os.environ', {'PROMPT_IMPROVEMENT_ENABLED': '1', 'PROMPT_IMPROVEMENT_CASES': 'reviewed.json', 'PROMPT_IMPROVEMENT_AUTO_APPLY': '0'}), patch('app.services.prompt_evaluation_replay.load_cases', return_value=[]) as load, patch('app.services.prompt_improvement_worker.serve', side_effect=background) as serve:
            async with lifespan(app):
                await asyncio.wait_for(entered.wait(), timeout=1)
            self.assertEqual(serve.call_args.args[0], 'reviewed.json')
            self.assertFalse(serve.call_args.kwargs['apply'])
        load.assert_called_once_with('reviewed.json')
